import os
import re
import sys
import json
import subprocess
import hashlib
import shutil
import argparse
import urllib.request
import zipfile
import tarfile
import time
import tempfile
import platform
from datetime import datetime
from pathlib import Path
from markdown_it import MarkdownIt
# タスクリスト(- [ ]/- [x])はGFM拡張のためcommonmarkプリセットに含まれず、mdit-py-pluginsの
# プラグインとして追加する（#48）。
from mdit_py_plugins.tasklists import tasklists_plugin
# 文字色指定（#46）。[text]{color=red}というPandoc由来のブラケット+属性記法をパースする
# （spans=Trueでspan_open/span_closeトークンとして出力される。既定では無効なので明示的に有効化）。
from mdit_py_plugins.attrs import attrs_plugin
# PyPIの typst パッケージ(typst-py)はコンパイラ本体をプラットフォーム別ホイールに同梱しているため、
# tools/typst.exe のような実行バイナリをリポジトリに持たずに済む（pipがOSごとに正しい版を入れてくれる）
import typst as typst_lib

try:
    import yaml
except ImportError:
    yaml = None

# ローカル環境やGitHub Actionsランナー(ubuntu-latest)に標準搭載されているChrome/Edgeの
# インストール先候補。見つかればmermaidレンダリング用にそのまま起動して再利用し、
# ブラウザの自動ダウンロード（実測699MB。#34）を回避する（仕様書11章、#35）。
SYSTEM_BROWSER_PATHS = {
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "linux": [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/microsoft-edge",
        "/usr/bin/microsoft-edge-stable",
    ],
}
SYSTEM_BROWSER_COMMANDS = [
    "google-chrome", "google-chrome-stable", "chromium-browser", "chromium",
    "msedge", "microsoft-edge", "microsoft-edge-stable",
]

def find_system_browser():
    """既存のChrome/Edgeの実行ファイルパスを探す。見つからなければNone。"""
    platform_key = "darwin" if sys.platform == "darwin" else ("linux" if sys.platform.startswith("linux") else "win32")
    for path in SYSTEM_BROWSER_PATHS.get(platform_key, []):
        if os.path.exists(path):
            return path
    for cmd in SYSTEM_BROWSER_COMMANDS:
        found = shutil.which(cmd)
        if found:
            return found
    return None

def find_system_java():
    """PATH上のjavaコマンドを探し、PlantUML（最新版はJava 11+要求）を実行できるバージョンか
    確認する。見つからない、またはバージョンが古い場合はNoneを返す（#22）。
    見つかった場合はensure_temurin_jre()によるJRE取得を回避できる（2章の最小限のダウンロード）。"""
    java_path = shutil.which("java")
    if not java_path:
        return None
    try:
        result = subprocess.run([java_path, "-version"], capture_output=True, text=True, timeout=10)
    except OSError:
        return None
    # java -version は慣習的にstderrへ出力される（stdoutは空のことが多い）
    output = result.stderr or result.stdout
    m = re.search(r'version "([\d.]+)', output)
    if not m:
        return None
    parts = m.group(1).split('.')
    major = int(parts[0])
    if major == 1 and len(parts) > 1:
        # 旧来の "1.8.0_xxx" 形式（Java 8以前）。実質バージョンは2つ目の要素。
        major = int(parts[1])
    return java_path if major >= 11 else None

class TypstRenderer:
    """
    markdown-it-py が生成したAST（構文木）を走査し、
    安全かつ正確にTypst構文へ変換するカスタムレンダラー
    """
    # 行頭に来るとTypstのブロック記法（見出し/リスト/用語リスト）として解釈される記号
    BLOCK_HEAD_RE = re.compile(r'^([ \t]*)(=+|[-+/]|[0-9]+[.)])(?=\s|$)')

    # 冒頭のfront-matter（Marp/Jekyll形式）。CommonMarkでは水平線+段落に見えてしまうため先に切り離す
    FRONT_MATTER_RE = re.compile(
        r'\A﻿?---[ \t]*\r?\n(.*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)', re.DOTALL)

    # front-matter のうちMarp固有で本ツールでは意味を持たないキー。
    # header/footer/paginateは#42でlandscape/paper_sizeと同じ弱い優先順位で適用する対象に昇格した
    # （chapters[]の明示指定が無い場合のみ使われる）ため、ここには含めない。
    MARP_ONLY_KEYS = {'marp', 'theme', 'size', 'class', 'style', 'backgroundColor'}

    # ::: layout-right / layout-left / layout-compare / layout-feature / layout-columns[-N] ... :::
    # ブロック。
    # - layout-right: 中の図（mermaid/plantuml/dot/graphvizフェンス、または単独行のMarkdown画像）
    #   を右、それ以外のテキストを左に配置する。末尾に`-N:M`（例: `layout-right-30:70`）を付けると
    #   左:右の比率（Typstのfr単位。合計100である必要はない）を指定できる。省略時は35:65（#81）。
    # - layout-left: layout-rightの左右反転版（図を左、テキストを右）。比率記法は同じで、省略時は
    #   65:35（#81）。
    # - layout-compare: 中の2つの図を左右に並べる（横長の図同士の比較用）。図の種類は混在可（例:
    #   片方mermaid・もう片方は写真）。
    # - layout-feature: 写真（または図）をフルブリードで敷き、下部にキャッチコピーを重ねる（#78）。
    # - layout-columns[-N]: 中身（任意のMarkdown）をN列（省略時2列）のcolumns()に流し込む（#78）。
    # markdown-it の通常のASTフローでは「直前・直後のテキストと図をまとめて2カラム化する」表現が
    # 難しいため、通常のトークン処理に入る前の生テキスト段階で切り出して個別に処理する（#11）。
    # 対応する図の種類をmermaidだけに限らず一般化したもの（#77）。
    LAYOUT_BLOCK_RE = re.compile(
        r'^::: *((?:layout-right|layout-left)(?:-[0-9]+:[0-9]+)?|layout-compare|layout-feature|'
        r'layout-columns(?:-[0-9]+)?) *\r?\n(.*?)\r?\n::: *\r?$',
        re.MULTILINE | re.DOTALL)
    # フェンス（mermaid/plantuml/dot/graphviz）か、単独行のMarkdown画像（`![alt](src)`のみの行）の
    # いずれかにマッチする。画像側は行全体にアンカーし、文中に埋め込まれたインライン画像を誤って
    # 抜き出さないようにする（テキストの前後を単純に連結する都合上、行の一部だけを抜くと文が壊れる）。
    DIAGRAM_OR_IMAGE_RE = re.compile(
        r'```(?P<lang>mermaid|plantuml|dot|graphviz)\r?\n(?P<code>.*?)\r?\n```'
        r'|^[ \t]*(?P<image>!\[[^\]]*\]\([^)\n]+\))[ \t]*\r?$',
        re.MULTILINE | re.DOTALL)

    # Marpディレクティブコメント。7章の要件（Marp原稿との共用）を満たすため認識はするが、
    # 何も反映しない（#41、_handle_html_tokenを参照）。#42でheader/footer/paginateがfront-matter/
    # chapters[]経由では適用対象になったが、このインラインHTMLコメント形式は意図的に対象外のまま
    # （ファイル内の任意の位置から「以降に持続する」という#16と同種の危険な性質を持つため）。
    DIRECTIVE_RE = re.compile(r'^<!--\s*(header|footer|paginate)\s*:.*-->\s*$')

    # GitHub Wiki拡張の用語索引記法（#47、#48）。[[用語]]の素の形のみ対応し、区切り記法
    # （[[表示|ページ]]）は使い方が分かりにくいとして不採用（#48）。[[/]]は空にならないよう
    # 中身を1文字以上必須にし、ネストした角括弧（通常の[link]記法との衝突）は対象外にする。
    WIKILINK_RE = re.compile(r'\[\[([^\[\]]+)\]\]')

    # 文字色指定（#46）。<span style="color:...">は「閉じた許可リスト」への1パターン追加として
    # 狭く特別扱いする（それ以外のHTMLタグは従来どおり非対応・警告のまま）。もう1つの記法
    # （[text]{color=red}、Pandoc由来）はmdit_py_plugins.attrsのspan機能で処理する。
    HTML_SPAN_COLOR_OPEN_RE = re.compile(r'^<span\s+style\s*=\s*["\']color\s*:\s*([^;"\']+?)\s*;?\s*["\']\s*>$', re.IGNORECASE)
    HTML_SPAN_CLOSE_RE = re.compile(r'^</span\s*>$', re.IGNORECASE)

    # GitHub形式のalert記法（#61）。`> [!NOTE]`のように、blockquoteの最初の行がこのマーカーだけの
    # ときだけ発動する。テンプレート側は@preview/note-me（MIT、#63でライセンス確認済み）が持つ
    # note/tip/important/warning/cautionをcallout()でラップして呼び出す。
    ALERT_MARKER_RE = re.compile(r'^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$')

    def __init__(self, base_dir=None, typst_root=None, mermaid_enabled=True, mermaid_auto_download=False,
                 plantuml_enabled=True, plantuml_auto_download=True, glossary_enabled=False, tool_dir=None):
        # 対応するMarkdown記法のスコープはGFM + GitHub Wiki（#48）。table/strikethroughはGFM拡張だが
        # commonmarkプリセットにコアルールとして同梱されており、enable()するだけで使える。
        self.md = (MarkdownIt("commonmark").enable("table").enable("strikethrough")
                   .use(tasklists_plugin)
                   .use(attrs_plugin, spans=True, span_after="link", allowed=["color"]))
        self.list_stack = []
        self.current_file = ""
        self.current_dir = ""
        # base_dir: プロジェクト側の基準ディレクトリ（画像・mermaidキャッシュの相対パス解決に使う）
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        # typst_root: typst compile の --root と同じ値。base_dirとツール本体(templates/)の
        # 両方を跨いでも解決できるよう、image()呼び出しはこれを起点にルート絶対パスで組み立てる
        self.typst_root = typst_root or os.path.dirname(self.base_dir)
        self.allow_exec = False
        self.front_matter = {}
        # plugins.mermaid: false（6章、#21）。falseなら```mermaidフェンスをヘッドレスブラウザで
        # 描画せず、他の未対応言語と同じく素のコード表示にフォールバックする。
        self.mermaid_enabled = mermaid_enabled
        self._mermaid_disabled_warned = False
        # plugins.mermaid_auto_download: false（既定。#22の設計議論を踏まえて追加）。システムに
        # Chrome/Edgeが無い場合、falseならFail-fast（従来どおり）、trueならPlaywright自身の
        # Chromiumをダウンロードして使う（実測約700MB。#34/#35で避けた重いダウンロードそのものなので
        # 既定はfalseのまま。手元にどうしても持っていない場合の最後の手段として明示的に選ばせる）。
        self.mermaid_auto_download = mermaid_auto_download
        # tool_dir: mermaid.min.jsのキャッシュ場所（tool_dir/.mermaid-cache/）の解決に使う（#35）。
        self.tool_dir = tool_dir or os.path.dirname(os.path.abspath(__file__))
        # Mermaidレンダリング用ヘッドレスブラウザのライフサイクル状態。最初のmermaid図を描画する
        # ときに遅延起動し、ビルド終了時にclose()で片付ける（複数の図で1つのブラウザ・ページを
        # 使い回し、図ごとに起動し直さない）。
        self._mermaid_page = None
        self._mermaid_browser = None
        self._mermaid_playwright = None
        self._mermaid_chrome_proc = None
        self._mermaid_profile_dir = None
        # document.table_header / chapters[].table_headerのマージ結果（#45）。
        # _render_markdown_chapterが章ごとに設定する。bold/background/colorいずれも
        # 未指定なら従来どおり無装飾（キーが無ければ何もしない）。
        self.table_header_style = {}
        # document.glossary: false（既定。#47）。falseなら[[用語]]は素の文字列としてそのまま通す
        # （trueの場合のみWIKILINK_REで検出・登録する）。用語ごとの出現ラベルID一覧を、全チャプター
        # を跨いで蓄積する（dict、Python 3.7+で挿入順を保持。ビルド末尾で巻末索引の生成に使う）。
        self.glossary_enabled = glossary_enabled
        self.glossary_terms = {}
        self._glossary_label_counter = 0
        # plugins.plantuml: true（既定。#22）。falseなら```plantumlフェンスをローカルのjava+
        # plantuml.jarで描画せず、他の未対応言語と同じく素のコード表示にフォールバックする。
        self.plantuml_enabled = plantuml_enabled
        self._plantuml_disabled_warned = False
        # plugins.plantuml_auto_download: true（既定）。システムにJava 11+が無い場合、trueなら
        # Eclipse Temurin JREを自動取得（実測約49.7MB。Chromiumの約700MBと違い許容できる規模）、
        # falseならFail-fast。mermaidと非対称な既定値なのは意図的（ダウンロードされる実体の
        # サイズが1桁違うため。#22の設計議論を参照）。
        self.plantuml_auto_download = plantuml_auto_download
        # java実行ファイル・plantuml.jarのパスは初回の```plantuml描画時に遅延解決する
        # （mermaidのヘッドレスブラウザと異なり常駐プロセスではないため、都度subprocessで起動する）。
        self._plantuml_java_bin = None
        self._plantuml_jar_path = None

    # 拡張子ごとの構造化データ言語（Typstのraw()に渡すシンタックスハイライト名）。
    # コンテキストとなるテキストファイルはMarkdownに限らない（1章、#15）。
    STRUCTURED_TEXT_LANGS = {'.yaml': 'yaml', '.yml': 'yaml', '.json': 'json'}

    # 図表ソースファイルそのものをchaptersに直接指定できる拡張子（#53）。Markdown内の
    # フェンスコードブロックと同じ描画機構をそのまま流用する（新しい描画ロジックは書かない）。
    # .iumlはPlantUMLの!includeで取り込む断片ファイル用の慣習であり、単体の図として
    # 使われないため対象外。
    DIAGRAM_FILE_EXTS = {
        '.dot': 'graphviz', '.gv': 'graphviz',
        '.mmd': 'mermaid',
        '.puml': 'plantuml', '.plantuml': 'plantuml', '.pu': 'plantuml',
    }

    def render_chapter(self, text, filepath="", drop_leading_title=False):
        """chaptersの1ファイルを拡張子に応じて変換する（1章、#15）。
        .md/.markdown以外はmarkdown-itに一切通さない。素のテキストやYAML/JSON中の
        行頭記号（#, -, [ 等）がMarkdown構文として誤解釈され、静かに壊れるのを防ぐため。"""
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ('.md', '.markdown'):
            return self.render(text, filepath=filepath, drop_leading_title=drop_leading_title)

        self.current_file = filepath
        self.current_dir = os.path.dirname(os.path.abspath(filepath)) if filepath else self.base_dir
        self.front_matter = {}

        diagram_kind = self.DIAGRAM_FILE_EXTS.get(ext)
        if diagram_kind == 'graphviz':
            return self._render_raw_text(text, 'dot')
        elif diagram_kind == 'mermaid':
            return self._render_mermaid(text)
        elif diagram_kind == 'plantuml':
            return self._render_plantuml(text)

        return self._render_raw_text(text, self.STRUCTURED_TEXT_LANGS.get(ext))

    def _render_raw_text(self, text, lang=None):
        """Markdown以外のテキスト（プレーンテキスト・コード・YAML/JSON等）を、markdown-itを一切
        通さずTypstのraw()で等幅表示する。通常の段落として流し込むとTypstのテキストモードが
        連続する空白を折りたたみ、コードのインデント等が失われるため、raw()で改行・空白とも
        そのまま保持する。lang未指定時（プレーンテキスト・未知拡張子）はシンタックスハイライトなし。
        ```` ``` ````フェンス構文だと本文中に```が含まれた場合に壊れるため、文字列リテラルとして渡す。"""
        escaped = (text.replace('\\', '\\\\').replace('"', '\\"')
                       .replace('\r\n', '\n').replace('\n', '\\n'))
        lang_arg = f'lang: "{lang}", ' if lang else ''
        return f'#raw("{escaped}", {lang_arg}block: true)\n\n'

    def render(self, text, filepath="", drop_leading_title=False):
        self.current_file = filepath
        self.current_dir = os.path.dirname(os.path.abspath(filepath)) if filepath else self.base_dir
        # 【修正】typst-exec は「人間レビュー済み (reviewed/)」配下のみ許可するホワイトリスト方式
        self.allow_exec = "reviewed" in Path(os.path.abspath(filepath)).parts if filepath else False
        text, self.front_matter = self.strip_front_matter(text)

        output = []
        pos = 0
        first_segment = True
        for m in self.LAYOUT_BLOCK_RE.finditer(text):
            md_before = text[pos:m.start()]
            if md_before.strip() or first_segment:
                output.append(self._render_markdown_segment(md_before, drop_leading_title and first_segment))
                first_segment = False
            block_kind, block_body = m.group(1), m.group(2)
            if block_kind == 'layout-right' or block_kind.startswith('layout-right-'):
                output.append(self._render_layout_block(block_body, flip=False,
                                                          ratio=self._parse_layout_ratio(block_kind, (35, 65))))
            elif block_kind == 'layout-left' or block_kind.startswith('layout-left-'):
                output.append(self._render_layout_block(block_body, flip=True,
                                                          ratio=self._parse_layout_ratio(block_kind, (65, 35))))
            elif block_kind == 'layout-compare':
                output.append(self._render_compare_block(block_body))
            elif block_kind == 'layout-feature':
                output.append(self._render_feature_block(block_body))
            else:
                output.append(self._render_columns_block(block_kind, block_body))
            pos = m.end()
        md_after = text[pos:]
        if md_after.strip() or first_segment:
            output.append(self._render_markdown_segment(md_after, drop_leading_title and first_segment))
        return "".join(output)

    def _render_markdown_segment(self, text, drop_leading_title):
        """通常のMarkdown断片をASTベースでTypstへ変換する（layout-rightブロックの前後の地の文用）"""
        self.list_stack = []
        tokens = self.md.parse(text)
        start = self._skip_leading_title(tokens) if drop_leading_title else 0
        return self.render_tokens(tokens, start)

    def _render_diagram_fence(self, lang, code):
        """```mermaid/```plantuml/```dot/```graphvizフェンスの内容をTypstコードへ変換する。
        通常のMarkdownフロー（render_tokens）とlayout-right/layout-compareブロックの双方から
        共通で呼べるようにした処理（#77）。mermaid/plantumlはPython側でSVGを事前生成して
        画像として埋め込むが、dot/graphvizはTypstテンプレート側のshowルール（diagraph）が
        コンパイル時に遅延描画するため、ここでは素のraw()化（_render_raw_text）に任せればよい。"""
        if lang == 'mermaid':
            return self._render_mermaid(code)
        elif lang == 'plantuml':
            return self._render_plantuml(code)
        return self._render_raw_text(code, lang)

    def _render_diagram_or_image_match(self, m):
        """DIAGRAM_OR_IMAGE_REの1マッチをTypstコードへ変換する。フェンスは_render_diagram_fenceへ、
        単独行のMarkdown画像は通常の画像処理（alt|width=/height=構文込み）をそのまま再利用するため
        _render_markdown_segmentに委譲する（#77）。"""
        if m.group('lang'):
            return self._render_diagram_fence(m.group('lang'), m.group('code'))
        return self._render_markdown_segment(m.group('image'), False).strip()

    def _parse_layout_ratio(self, block_kind, default):
        """'layout-right-30:70'のようなブロック名末尾の`-N:M`から(左, 右)のfr比率を取り出す。
        末尾指定が無ければdefaultをそのまま返す（#81）。数値の妥当性チェックは行わない
        （LAYOUT_BLOCK_REの正規表現`[0-9]+:[0-9]+`に一致した時点で構文的には十分なため、
        layout-columns-Nと同様バリデーションは追加しない）。"""
        m = re.search(r'-([0-9]+):([0-9]+)$', block_kind)
        return (int(m.group(1)), int(m.group(2))) if m else default

    def _render_layout_block(self, inner_text, flip=False, ratio=(35, 65)):
        """::: layout-right / layout-left ... ::: ブロックを、テキストと図（mermaid/plantuml/dot/
        graphvizまたはMarkdown画像）の2カラムgridへ変換する。flip=Trueならlayout-leftとして
        図を左・テキストを右に配置する（#81）。ratioは(左, 右)のfr比率"""
        block_name = 'layout-left' if flip else 'layout-right'
        match = self.DIAGRAM_OR_IMAGE_RE.search(inner_text)
        if not match:
            print(f"[Error] '{block_name}' block in {self.current_file} must contain exactly one "
                  "```mermaid/```plantuml/```dot/```graphviz fence or a standalone image.")
            sys.exit(1)
        surrounding_md = (inner_text[:match.start()] + inner_text[match.end():]).strip()
        text_typst = self._render_markdown_segment(surrounding_md, False).strip()
        image_typst = self._render_diagram_or_image_match(match).strip()
        left_fr, right_fr = ratio
        cells = [image_typst, text_typst] if flip else [text_typst, image_typst]
        align = "(center + horizon, left + top)" if flip else "(left + top, center + horizon)"
        return (
            "#grid(\n"
            f"  columns: ({left_fr}fr, {right_fr}fr),\n"
            "  column-gutter: 1.5em,\n"
            f"  align: {align},\n"
            f"  [{cells[0]}],\n"
            f"  [{cells[1]}],\n"
            ")\n\n"
        )

    def _render_compare_block(self, inner_text):
        """::: layout-compare ... ::: ブロックを、2つの図（mermaid/plantuml/dot/graphvizまたは
        Markdown画像。種類は混在可）を左右に並べた2カラムgridへ変換する。
        各図の直前にあるテキスト（キャプション）は、その図と同じ列にまとめて配置する。"""
        matches = list(self.DIAGRAM_OR_IMAGE_RE.finditer(inner_text))
        if len(matches) != 2:
            print(f"[Error] 'layout-compare' block in {self.current_file} must contain exactly two "
                  f"```mermaid/```plantuml/```dot/```graphviz fences or images (found {len(matches)}).")
            sys.exit(1)
        cells = []
        prev_end = 0
        for i, m in enumerate(matches):
            caption_md = inner_text[prev_end:m.start()].strip()
            # 2番目以降の図の後ろに残ったテキストは、最後の列にまとめて含める
            trailing_md = inner_text[matches[-1].end():].strip() if i == len(matches) - 1 else ""
            caption_typst = self._render_markdown_segment(caption_md, False).strip() if caption_md else ""
            image_typst = self._render_diagram_or_image_match(m).strip()
            trailing_typst = self._render_markdown_segment(trailing_md, False).strip() if trailing_md else ""
            cell = "\n\n".join(t for t in [caption_typst, image_typst, trailing_typst] if t)
            cells.append(cell)
            prev_end = m.end()
        columns_typst = ",\n".join(f"  [{cell}]" for cell in cells)
        return (
            "#grid(\n"
            "  columns: (1fr, 1fr),\n"
            "  column-gutter: 1.5em,\n"
            "  align: (left + top, left + top),\n"
            f"{columns_typst},\n"
            ")\n\n"
        )

    # layout-featureの写真枠の高さ（スライド本文領域に対する割合）。#78の実機確認で判明した通り、
    # width:100%だけだと縦長写真が大幅にはみ出す（枠の高さが写真任せになるため）。CSSの
    # background-size:coverと同じ考え方で、高さを固定しfit:"cover"で余分をトリミングすることで、
    # 縦長・横長どちらの写真でも枠からはみ出さないようにする。
    FEATURE_IMG_HEIGHT = "70%"

    def _render_feature_image(self, match):
        """layout-feature内の図/画像を、フルブリード表示用のTypstコードへ変換する（#78）。
        「写真が主役」という趣旨に合わせ、Markdown画像はalt側のwidth/height指定（あれば）を
        無視してwidth/height: 100%・fit: "cover"で枠いっぱいに敷き詰める（枠の高さ自体は
        FEATURE_IMG_HEIGHTで固定するため、はみ出しはfit:coverのトリミングで吸収される）。
        mermaid/plantuml/dot/graphvizフェンスは想定外の使い方だが、#77の汎用抽出をそのまま通し、
        既存のfit-image表示（高さ上限あり・cover表示ではない）に委ねる。"""
        if match.group('lang'):
            return self._render_diagram_fence(match.group('lang'), match.group('code')).strip()
        src_match = re.match(r'!\[[^\]]*\]\(([^)]+)\)', match.group('image'))
        return f'#image("{self._resolve_asset(src_match.group(1))}", width: 100%, height: 100%, fit: "cover")'

    def _render_feature_block(self, inner_text):
        """::: layout-feature ... ::: ブロックを、写真（または図）をフルブリードで敷き、
        下部に半透明の帯とキャッチコピーを重ねるレイアウトへ変換する（#78）。
        図/画像の抽出はlayout-right/layout-compareと同じDIAGRAM_OR_IMAGE_REを再利用する（#77）。"""
        match = self.DIAGRAM_OR_IMAGE_RE.search(inner_text)
        if not match:
            print(f"[Error] 'layout-feature' block in {self.current_file} must contain exactly one "
                  "```mermaid/```plantuml/```dot/```graphviz fence or a standalone image.")
            sys.exit(1)
        catchcopy_md = (inner_text[:match.start()] + inner_text[match.end():]).strip()
        catchcopy_typst = self._render_markdown_segment(catchcopy_md, False).strip()
        image_typst = self._render_feature_image(match)
        return (
            f'#box(width: 100%, height: {self.FEATURE_IMG_HEIGHT})[\n'
            f"  {image_typst}\n"
            "  #place(bottom + left)[\n"
            "    #block(width: 100%, inset: (x: 1.5em, y: 1em), "
            "fill: gradient.linear(rgb(\"#00000000\"), rgb(\"#000000B3\"), angle: 90deg))[\n"
            f"      #text(fill: white, size: 24pt, weight: \"bold\")[{catchcopy_typst}]\n"
            "    ]\n"
            "  ]\n"
            "]\n\n"
        )

    def _render_columns_block(self, block_kind, inner_text):
        """::: layout-columns ... ::: (または layout-columns-N) ブロックを、TypstのN列columns()
        コンテナへ流し込む（省略時2列、#78）。layout-right/layout-compareと違い中身の種類を
        判別する必要がなく「N列に流し込む」という見た目の指定に過ぎないため、Fail-fastの
        バリデーションは設けず任意のMarkdownを許す。
        columns()はコンテナの高さを超えて初めて次列へあふれる仕組みのため、スライドのように
        本文が短く1列の高さに収まってしまう場合は素朴に#columns(N)[...]と書いても分割されない
        （実機確認で判明）。measure()で中身の自然な高さを測り、その1/N（+わずかな余裕）を
        コンテナの高さとして明示することで、あふれを強制してN列に均等分割する。"""
        n_match = re.match(r'layout-columns(?:-([0-9]+))?$', block_kind)
        count = int(n_match.group(1)) if n_match.group(1) else 2
        content_typst = self._render_markdown_segment(inner_text, False).strip()
        return (
            f'#let _columns_content = [{content_typst}]\n'
            "#layout(size => {\n"
            "  let h = measure(_columns_content, width: size.width).height\n"
            f"  block(height: h / {count} + 1pt)[\n"
            f"    #columns({count}, gutter: 1.5em, _columns_content)\n"
            "  ]\n"
            "})\n\n"
        )

    def _consume_heading(self, tokens, pos):
        """posがheading_open（H1/H2まで）ならそのブロックを読み飛ばし、(次の位置, 見出しテキスト)を返す。
        該当しなければ (pos, None)。"""
        if pos >= len(tokens) or tokens[pos].type != 'heading_open' or int(tokens[pos].tag[1:]) > 2:
            return pos, None
        j = pos
        text_parts = []
        while j < len(tokens) and tokens[j].type != 'heading_close':
            if tokens[j].type == 'inline':
                text_parts.append(tokens[j].content)
            j += 1
        return j + 1, ' '.join(text_parts)

    def _consume_lead_image(self, tokens, pos):
        """posが「画像1個だけの段落」（タイトルスライドの図版）ならそのブロックを読み飛ばし、
        次の位置を返す。該当しなければposをそのまま返す。"""
        if (pos + 2 >= len(tokens)
                or tokens[pos].type != 'paragraph_open'
                or tokens[pos + 1].type != 'inline'
                or tokens[pos + 2].type != 'paragraph_close'):
            return pos
        children = tokens[pos + 1].children or []
        if len(children) == 1 and children[0].type == 'image':
            return pos + 3
        return pos

    def _skip_leading_title(self, tokens):
        """cover: replace/none 用に、先頭のタイトルブロック（画像1枚 + H1/H2と直後の区切り線）を読み飛ばす"""
        i = 0
        dropped = []
        # 先頭のHTMLコメント（Marpのディレクティブ等）は読み飛ばす。ただし警告は従来どおり出す
        while i < len(tokens) and tokens[i].type in ['html_block', 'html_inline']:
            self._handle_html_token(tokens[i])
            i += 1

        # タイトルの前に図版が1枚だけ置かれているタイトルスライド（画像 + H1 + H2）に対応する。
        # ただしこの時点では見出しが続くかどうか未確定なので、実際に見出しが見つかったときだけ
        # 画像も含めて読み飛ばす（見出しが無ければ画像はそのまま本文として残す）。
        image_end = self._consume_lead_image(tokens, i)
        title_start, title = self._consume_heading(tokens, image_end)
        if title is None:
            return 0
        i = title_start
        dropped.append(title)

        # 直後がさらに見出し(H1/H2)の場合、それをサブタイトルとして一緒に読み飛ばすのは、
        # そのすぐ後にhr（---）が続くか、そこでこのチャプター（ファイル）が終わっているとき
        # に限る。それ以外（続けて本文の段落が来る等）は、本文側の実見出し（例: "## 1. はじめに"）
        # であり、タイトルスライドの一部ではないため触らない。
        next_pos, subtitle = self._consume_heading(tokens, i)
        if subtitle is not None and (next_pos >= len(tokens) or tokens[next_pos].type == 'hr'):
            dropped.append(subtitle)
            i = next_pos
            if i < len(tokens) and tokens[i].type == 'hr':
                i += 1
            print(f"[Info] Cover: replaced the leading title slide of {self.current_file} ({' / '.join(dropped)})")
            return i

        if i < len(tokens) and tokens[i].type == 'hr':
            i += 1
        # サイレントに本文を捨てないよう、取り除いた内容は必ずログに出す
        print(f"[Info] Cover: replaced the leading title slide of {self.current_file} ({' / '.join(dropped)})")
        return i

    def strip_front_matter(self, text):
        """冒頭のfront-matterを本文から除去し、設定として返す。行番号は空行で維持する"""
        m = self.FRONT_MATTER_RE.match(text)
        if not m:
            return text, {}
        meta = {}
        if yaml is None:
            print(f"[Warning] PyYAML is not installed; front-matter in {self.current_file} is ignored.")
        else:
            try:
                loaded = yaml.safe_load(m.group(1))
                if isinstance(loaded, dict):
                    meta = loaded
                else:
                    print(f"[Warning] Front-matter in {self.current_file} is not a mapping; ignored.")
            except Exception as e:
                print(f"[Warning] Failed to parse front-matter in {self.current_file}: {e}")
        for key in meta:
            if key not in self.MARP_ONLY_KEYS and key not in ('title', 'subtitle', 'author', 'date',
                                                              'paper_size', 'landscape', 'font_size',
                                                              'header', 'footer', 'paginate'):
                print(f"[Warning] Unknown front-matter key '{key}' in {self.current_file}")
        if 'font_size' in meta and not re.match(r'^\d+(\.\d+)?pt$', str(meta['font_size'])):
            print(f"[Warning] front-matter 'font_size' in {self.current_file} should look like '16pt'; got {meta['font_size']!r}. Ignoring.")
            del meta['font_size']
        # 除去した行数ぶん改行を残し、以降の警告メッセージの行番号がずれないようにする
        return '\n' * m.group(0).count('\n') + text[m.end():], meta
        
    def _detect_alert_kind(self, tokens, i):
        """tokens[i]がblockquote_openのとき、直後の段落が`[!NOTE]`等のマーカーだけの行なら
        種別（小文字）を返す。マッチした場合、マーカーのテキストトークン（と直後のsoftbreak）を
        その場で取り除く（以降のinlineレンダリングに影響しないようにするため）。"""
        if i + 2 >= len(tokens):
            return None
        if tokens[i + 1].type != 'paragraph_open' or tokens[i + 2].type != 'inline':
            return None
        children = tokens[i + 2].children
        if not children or children[0].type != 'text':
            return None
        m = self.ALERT_MARKER_RE.match(children[0].content.strip())
        if not m:
            return None
        children.pop(0)
        if children and children[0].type == 'softbreak':
            children.pop(0)
        return m.group(1).lower()

    def render_tokens(self, tokens, start=0):
        result = []
        i = start
        while i < len(tokens):
            t = tokens[i]
            if t.type == 'heading_open':
                level = int(t.tag[1:])
                result.append('=' * level + ' ')
            elif t.type == 'heading_close':
                result.append('\n\n')
            elif t.type == 'paragraph_open':
                pass
            elif t.type == 'paragraph_close':
                # 【修正】タイトなリスト内の暗黙段落(hidden)で空行を出さない（loose化防止）
                if not t.hidden:
                    result.append('\n\n')
            elif t.type == 'blockquote_open':
                alert_kind = self._detect_alert_kind(tokens, i)
                if alert_kind:
                    result.append(f'#callout(kind: "{alert_kind}")[\n')
                else:
                    result.append('#quote(block: true)[\n')
            elif t.type == 'blockquote_close':
                result.append(']\n\n')
            elif t.type == 'inline':
                result.append(self.render_inline(t.children))
            # 【修正】ネストしたリストを階層のままインデント付きで出力する
            elif t.type in ['bullet_list_open', 'ordered_list_open']:
                if self.list_stack and not self._ends_with_newline(result):
                    result.append('\n')
                self.list_stack.append('ordered' if t.type == 'ordered_list_open' else 'bullet')
            elif t.type in ['bullet_list_close', 'ordered_list_close']:
                if self.list_stack:
                    self.list_stack.pop()
                if not self.list_stack:
                    result.append('\n')
            elif t.type == 'list_item_open':
                indent = '  ' * max(0, len(self.list_stack) - 1)
                marker = '+ ' if self.list_stack and self.list_stack[-1] == 'ordered' else '- '
                result.append(indent + marker)
            elif t.type == 'list_item_close':
                if not self._ends_with_newline(result):
                    result.append('\n')
            elif t.type == 'table_open':
                cols = self._count_table_cols(tokens, i)
                result.append(f'#table(\n  columns: {cols}{self._table_header_fill_arg()},\n  ')
            elif t.type == 'table_close':
                result.append('\n)\n\n')
            elif t.type == 'hr':
                result.append('#pagebreak()\n\n')
            elif t.type == 'fence':
                lang = t.info.strip()
                if lang == 'typst-exec':
                    if not self.allow_exec:
                        print(f"[Error] Security: 'typst-exec' is allowed only under a 'reviewed/' directory ({self.current_file}).")
                        sys.exit(1)
                    result.append(f"{t.content}\n\n")
                elif lang in ('mermaid', 'plantuml'):
                    result.append(self._render_diagram_fence(lang, t.content))
                else:
                    # ```` ``` ````フェンス構文で直接組み立てると、コード内容自体に```が
                    # 含まれる場合にTypst側のフェンスが早期に閉じて壊れる。文字列リテラルとして
                    # 渡すraw()なら安全（#15の_render_raw_textと同じ理由）。
                    result.append(self._render_raw_text(t.content, lang or None))
            elif t.type in ['html_inline', 'html_block']:
                result.append(self._handle_html_token(t))
            elif t.type == 'th_open':
                open_wrap, _ = self._table_header_open_close()
                result.append('[' + open_wrap)
            elif t.type == 'th_close':
                _, close_wrap = self._table_header_open_close()
                result.append(close_wrap + '], ')
            elif t.type == 'td_open':
                result.append('[')
            elif t.type == 'td_close':
                result.append('], ')
            elif t.type == 'tr_close':
                result.append('\n  ')
            i += 1
        return "".join(result)
        
    def _warn_html(self, t):
        line_no = t.map[0] + 1 if t.map else '?'
        print(f"[Warning] HTML tag detected at {self.current_file}:{line_no} : {t.content.strip()}. HTML is not supported and will be ignored in Typst output.")

    def _task_checkbox_glyph(self, html):
        """tasklists_pluginが出力する<input class="task-list-item-checkbox" ...>だけを認識し、
        Unicodeのチェックボックス記号を返す（PDFは非対話的なので実際のcheckboxウィジェットは不要）。
        該当しなければNone（呼び出し側で通常のHTML警告にフォールバックする）。"""
        if 'task-list-item-checkbox' not in html:
            return None
        return '☑' if 'checked="checked"' in html else '☐'

    def _handle_html_token(self, t):
        """Marpのディレクティブコメント（<!-- header: X -->等）は、Marp原稿との共用時に不要な
        警告が出ないよう認識はするが、何も反映しない（値を読み捨てる）。実際に反映する機能は
        一度実装した（#16）が、チャプター（ファイル）をまたいで状態が持続する設計が、この
        ツールの売りである「章の並べ替え」と衝突する（並べ替えると意図しないヘッダーが
        混入しうる）ため撤回した（#41）。それ以外（未対応のディレクティブ・生のHTMLタグ）は
        従来どおり警告のみでビルドを継続する。"""
        if self.DIRECTIVE_RE.match(t.content.strip()):
            return ""
        self._warn_html(t)
        return ""

    def _ends_with_newline(self, result):
        for s in reversed(result):
            if s:
                return s.endswith('\n')
        return True

    def _resolve_asset(self, src):
        """画像の相対パスをMarkdownファイル基準から、typst_root起点のルート絶対パスへ変換する。
        temp_build.typ の実際の置き場所（.context-compositor/ 配下）に依存させないため。"""
        if not src or src.startswith('/') or re.match(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://', src):
            return escape_string_literal(src)
        abs_path = os.path.normpath(os.path.join(self.current_dir, src))
        # 仕様9章: 画像パス欠損はフォールバックせず即エラー (Fail-fast)
        if not os.path.exists(abs_path):
            print(f"[Error] Image not found: {abs_path} (referenced from {self.current_file})")
            sys.exit(1)
        root_rel_path = "/" + os.path.relpath(abs_path, self.typst_root).replace(os.sep, '/')
        return escape_string_literal(root_rel_path)

    def _ensure_mermaid_page(self):
        """Mermaidレンダリング用のヘッドレスブラウザ・ページを遅延起動する（初回のみ）。
        Node.js/npxを介さず、mermaid.min.js（実測約3.4MB）を直接ヘッドレスブラウザへ読み込ませて
        mermaid.render()を呼ぶ（仕様書11章、#35。mermaid-cli丸ごとの約396MBを回避する）。
        既存のシステムChrome/Edge（#34の検出ロジック）が見つかればPlaywrightのCDP接続で繋ぐだけで、
        ブラウザの追加ダウンロードは発生しない。見つからない場合、plugins.mermaid_auto_downloadが
        trueならPlaywright自身のChromium（実測約700MB）をその場で取得して使う。既定はfalseで、
        Fail-fastでエラー終了する（#22の設計議論。700MBは#34/#35がまさに避けた規模のため、
        既定で自動取得はしない）。"""
        if self._mermaid_page is not None:
            return self._mermaid_page

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[Error] The 'playwright' package is required for mermaid rendering (plugins.mermaid: true). "
                  "Install it with: pip install playwright==1.62.0")
            sys.exit(1)

        browser_path = find_system_browser()
        self._mermaid_playwright = sync_playwright().start()

        if browser_path:
            print(f"[Info] Reusing system browser for mermaid rendering: {browser_path}")
            self._mermaid_profile_dir = tempfile.mkdtemp(prefix="cc-mermaid-")
            self._mermaid_chrome_proc, port = _launch_headless_chrome(browser_path, self._mermaid_profile_dir)
            try:
                self._mermaid_browser = self._mermaid_playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            except Exception as e:
                print(f"[Error] Failed to connect to headless browser for mermaid rendering: {e}")
                sys.exit(1)
        elif self.mermaid_auto_download:
            print("[Info] No system Chrome/Edge found; plugins.mermaid_auto_download is true, so Playwright "
                  "will download its own Chromium (one-time; approx. 700MB; cached under Playwright's "
                  "browser cache, typically ~/.cache/ms-playwright)...")
            try:
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            except (subprocess.CalledProcessError, OSError) as e:
                print(f"[Error] Failed to download Playwright's Chromium: {e}")
                sys.exit(1)
            try:
                self._mermaid_browser = self._mermaid_playwright.chromium.launch(headless=True)
            except Exception as e:
                print(f"[Error] Failed to launch the downloaded Chromium for mermaid rendering: {e}")
                sys.exit(1)
        else:
            print("[Error] No system Chrome/Edge found; required to render mermaid diagrams locally. "
                  "Install Google Chrome or Microsoft Edge, or set plugins.mermaid_auto_download: true "
                  "(downloads Playwright's own Chromium, approx. 700MB), or set plugins.mermaid: false.")
            sys.exit(1)

        mermaid_js_path = ensure_mermaid_js(self.tool_dir)

        context = self._mermaid_browser.contexts[0] if self._mermaid_browser.contexts else self._mermaid_browser.new_context()
        page = context.new_page()
        page.set_content("<div id='container'></div>")
        with open(mermaid_js_path, "r", encoding="utf-8") as f:
            page.add_script_tag(content=f.read())
        # Typstのraw SVGレンダラーは<foreignObject>内のHTMLを描画できないため、mermaid既定の
        # HTMLラベルを無効化し、通常のSVG<text>要素で出力させる（トップレベルとflowchart配下
        # 両方に指定する必要がある。PoCで確認済み）
        page.evaluate("mermaid.initialize({ startOnLoad: false, htmlLabels: false, flowchart: { htmlLabels: false } })")
        self._mermaid_page = page
        return page

    def close(self):
        """ビルド終了時に呼び出し、_ensure_mermaid_pageで起動したヘッドレスブラウザを片付ける
        （mermaidを一度も描画していなければ何もしない）。"""
        if self._mermaid_browser is not None:
            try:
                self._mermaid_browser.close()
            except Exception:
                pass
        if self._mermaid_playwright is not None:
            self._mermaid_playwright.stop()
        if self._mermaid_chrome_proc is not None:
            self._mermaid_chrome_proc.terminate()
            try:
                self._mermaid_chrome_proc.wait(timeout=5)
            except Exception:
                self._mermaid_chrome_proc.kill()
        if self._mermaid_profile_dir and os.path.exists(self._mermaid_profile_dir):
            shutil.rmtree(self._mermaid_profile_dir, ignore_errors=True)

    def _render_mermaid(self, code):
        """mermaidブロックをヘッドレスブラウザ上のmermaid.render()でSVG化し、Typstのimage呼び出しに
        変換する。外部APIへの通信は行わず、ローカルのブラウザで完結させる（仕様書10章・11章、#35）。"""
        if not self.mermaid_enabled:
            if not self._mermaid_disabled_warned:
                print(f"[Info] plugins.mermaid is disabled; leaving ```mermaid fences as plain code (first seen in {self.current_file}).")
                self._mermaid_disabled_warned = True
            return f"```mermaid\n{code}```\n\n"

        cache_dir = os.path.join(self.base_dir, ".context-compositor", "cache")
        os.makedirs(cache_dir, exist_ok=True)
        digest = hashlib.sha256(code.encode('utf-8')).hexdigest()[:16]
        svg_path = os.path.join(cache_dir, f"mermaid_{digest}.svg")

        if not os.path.exists(svg_path):
            print(f"[Info] Rendering mermaid diagram via headless browser -> {os.path.basename(svg_path)}")
            page = self._ensure_mermaid_page()
            try:
                svg = page.evaluate(
                    """async ([id, code]) => {
                        const { svg } = await mermaid.render(id, code);
                        return svg;
                    }""",
                    [f"mermaid-{digest}", code],
                )
            except Exception as e:
                # 仕様9章のFail-fast方針: 描画失敗時はテキストへフォールバックせず即エラー
                print(f"[Error] mermaid rendering failed for {self.current_file}:\n{e}")
                sys.exit(1)
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(svg)

        # fit-image() は templates/slide.typ 側で定義されているため、image() の相対パス解決基準は
        # base_dir ではなく templates/ になってしまう。ファイルの置き場所に依存しない
        # ルート絶対パス（--root 起点の "/..." 形式）にして、どこから呼んでも解決できるようにする。
        root_rel_path = escape_string_literal("/" + os.path.relpath(svg_path, self.typst_root).replace(os.sep, '/'))
        return f'#align(center)[#fit-image("{root_rel_path}")]\n\n'

    def _ensure_plantuml_tools(self):
        """PlantUML実行に必要なjava実行ファイルとplantuml.jarを遅延解決する（初回のみ）。
        システムJava（11+）があればそのまま再利用する（2章の最小限のダウンロード）。無い場合、
        plugins.plantuml_auto_download（既定true）ならEclipse Temurin JREを自動取得し、falseなら
        Fail-fastでエラー終了する。mermaidのブラウザ自動取得（既定false）と非対称な既定値なのは、
        ダウンロードされる実体のサイズが一桁違うため（JRE約49.7MB対Chromium約700MB。#22の設計議論）。"""
        if self._plantuml_java_bin is None:
            java_bin = find_system_java()
            if java_bin:
                print(f"[Info] Reusing system Java for PlantUML rendering: {java_bin}")
            elif self.plantuml_auto_download:
                java_bin = ensure_temurin_jre(self.tool_dir)
            else:
                print("[Error] No local Java 11+ found; required to render PlantUML diagrams. "
                      "Install Java 11+, or set plugins.plantuml_auto_download: true "
                      "(downloads Eclipse Temurin JRE, approx. 50MB), or set plugins.plantuml: false.")
                sys.exit(1)
            self._plantuml_java_bin = java_bin
        if self._plantuml_jar_path is None:
            self._plantuml_jar_path = ensure_plantuml_jar(self.tool_dir)
        return self._plantuml_java_bin, self._plantuml_jar_path

    def _render_plantuml(self, code):
        """```plantumlブロックをローカルのjava+plantuml.jar（Smetanaレイアウトエンジン。dot等の
        外部バイナリに依存しない）でSVG化し、Typstのimage呼び出しに変換する。外部APIへの通信は
        行わない（仕様書10章・11章、#22）。コードは実際のPlantUML構文どおり@startuml/@enduml
        込みで書く必要がある（暗黙の補完はしない。9章の決定論的出力・明示性の方針に沿う）。"""
        if not self.plantuml_enabled:
            if not self._plantuml_disabled_warned:
                print(f"[Info] plugins.plantuml is disabled; leaving ```plantuml fences as plain code (first seen in {self.current_file}).")
                self._plantuml_disabled_warned = True
            return f"```plantuml\n{code}```\n\n"

        cache_dir = os.path.join(self.base_dir, ".context-compositor", "cache")
        os.makedirs(cache_dir, exist_ok=True)
        digest = hashlib.sha256(code.encode('utf-8')).hexdigest()[:16]
        svg_path = os.path.join(cache_dir, f"plantuml_{digest}.svg")

        if not os.path.exists(svg_path):
            print(f"[Info] Rendering PlantUML diagram via local Java -> {os.path.basename(svg_path)}")
            java_bin, jar_path = self._ensure_plantuml_tools()
            try:
                result = subprocess.run(
                    [java_bin, "-jar", jar_path, "-tsvg", "-pipe", "-Playout=smetana"],
                    input=code, capture_output=True, text=True, encoding="utf-8", timeout=60)
            except OSError as e:
                print(f"[Error] Failed to run PlantUML for {self.current_file}:\n{e}")
                sys.exit(1)
            if result.returncode != 0:
                # 仕様9章のFail-fast方針: 描画失敗時はテキストへフォールバックせず即エラー
                print(f"[Error] PlantUML rendering failed for {self.current_file}:\n{result.stderr}")
                sys.exit(1)
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(result.stdout)

        root_rel_path = escape_string_literal("/" + os.path.relpath(svg_path, self.typst_root).replace(os.sep, '/'))
        return f'#align(center)[#fit-image("{root_rel_path}")]\n\n'

    def escape_typst(self, text, at_line_start=False):
        text = text.replace('\\', '\\\\')
        # 【修正】テーブルセル破壊等のサイレントバグを防ぐため [ および ] もエスケープ対象に追加
        for c in ['#', '$', '<', '>', '@', '*', '_', '`', '~', '[', ']']:
            text = text.replace(c, '\\' + c)
        # 【修正】行頭の = - + / 1. がTypstの見出し・リスト記法に化けるのを防ぐ
        if at_line_start:
            text = self.BLOCK_HEAD_RE.sub(lambda m: m.group(1) + '\\' + m.group(2), text)
        return text

    def _register_glossary_term(self, term):
        """[[用語]]の1出現を登録し、Typstの#metadata(none)<gloss-N>ラベルを埋め込むコード片を
        返す（#47）。metadata()は見た目に影響しない不可視要素で、目次のoutline()と同じ
        「context+query()でレイアウト後にページ番号を取得する」パターンで巻末索引を組み立てる。"""
        label_id = f"gloss-{self._glossary_label_counter}"
        self._glossary_label_counter += 1
        self.glossary_terms.setdefault(term, []).append(label_id)
        return f'{self.escape_typst(term)}#metadata(none)<{label_id}>'

    def _render_text_with_glossary(self, content, at_line_start):
        """textトークンの中身から[[用語]]を検出して登録しつつ、それ以外は通常どおりエスケープする。
        code_inline/fence等はrender_inlineに来ないtextトークンとして独立に処理されるため、
        ここで正規表現置換してもコードブロックの中身を巻き込む心配はない。"""
        parts = []
        last_end = 0
        first_segment = True
        for m in self.WIKILINK_RE.finditer(content):
            plain = content[last_end:m.start()]
            if plain:
                parts.append(self.escape_typst(plain, at_line_start=(at_line_start and first_segment)))
                first_segment = False
            term = m.group(1).strip()
            parts.append(self._register_glossary_term(term))
            first_segment = False
            last_end = m.end()
        remaining = content[last_end:]
        if remaining or not parts:
            parts.append(self.escape_typst(remaining, at_line_start=(at_line_start and first_segment)))
        return "".join(parts)

    def render_inline(self, tokens):
        res = []
        at_line_start = True
        # 文字色指定（#46）。<span style="color:...">はhtml_inlineの開き/閉じが独立したトークン
        # として出てくるため、段落内でスタック管理して対応させる。閉じずに段落が終わった場合は
        # 壊れたTypstコードを生成しないよう自動で閉じ、警告を出す。
        html_span_depth = 0
        # [text]{color=red}（attrs_pluginのspan_open/span_close）は既に開閉が対になった
        # トークンとして出てくるため、各span_openが実際にラップを出力したかどうかだけ
        # スタックで覚えておけばよい（span_close側は自分でattrsを持たないため）。
        span_wrap_stack = []
        for t in tokens:
            if t.type == 'text':
                if self.glossary_enabled and '[[' in t.content:
                    res.append(self._render_text_with_glossary(t.content, at_line_start))
                else:
                    res.append(self.escape_typst(t.content, at_line_start=at_line_start))
            elif t.type == 'strong_open':
                res.append('#strong[')
            elif t.type == 'strong_close':
                res.append(']')
            elif t.type == 'em_open':
                res.append('#emph[')
            elif t.type == 'em_close':
                res.append(']')
            elif t.type == 's_open':
                res.append('#strike[')
            elif t.type == 's_close':
                res.append(']')
            elif t.type == 'code_inline':
                # `` `text` ``のように直接バッククォートで組み立てると、text自体にバッククォートが
                # 含まれる場合（例: 4バッククォートのインラインコードスパンの中身が```を含む）に
                # Typst側のraw構文が早期に閉じて壊れる。文字列リテラルとして渡すraw()なら安全
                # （#15の_render_raw_text・フェンスのelse分岐と同じ理由。実測で発覚したバグ）。
                res.append(f'#raw("{escape_string_literal(t.content)}")')
            elif t.type in ['softbreak', 'hardbreak']:
                res.append('#linebreak()\n')
            elif t.type == 'image':
                src = dict(t.attrs).get('src', '')
                alt_text = t.content or ""
                width_opt = ""
                height_opt = ""
                
                # alt_textからサイズ指定 (例: alt|width=50%|height=30%) を解析
                if "|" in alt_text:
                    parts = alt_text.split("|")
                    for p in parts[1:]:
                        p = p.strip()
                        if p.startswith("width="):
                            w = p.split("=", 1)[1]
                            width_opt = f', width: {w}'
                        elif p.startswith("height="):
                            h = p.split("=", 1)[1]
                            height_opt = f', height: {h}'
                
                res.append(f'#image("{self._resolve_asset(src)}"{width_opt}{height_opt})')
            elif t.type == 'link_open':
                href = dict(t.attrs).get('href', '')
                res.append(f'#link("{escape_string_literal(href)}")[')
            elif t.type == 'link_close':
                res.append(']')
            elif t.type == 'span_open':
                # [text]{color=red}（#46）。attrs_pluginにallowed=["color"]を指定しているため、
                # color以外の属性は既にパース段階で取り除かれている。colorが無ければ何もラップしない。
                color = dict(t.attrs).get('color')
                if color:
                    res.append(f'#text(fill: {self._color_to_typst(color)})[')
                    span_wrap_stack.append(True)
                else:
                    span_wrap_stack.append(False)
            elif t.type == 'span_close':
                if span_wrap_stack and span_wrap_stack.pop():
                    res.append(']')
            elif t.type == 'html_inline':
                content = t.content.strip()
                span_color_match = self.HTML_SPAN_COLOR_OPEN_RE.match(content)
                # tasklists_pluginはチェックボックスを生HTML(<input class="task-list-item-checkbox" ...>)
                # として出力する。<span style="color:...">とあわせ、#46で決めた「閉じた許可リスト」の
                # 考え方に沿い、このパターンだけを特別扱いする（#48）。それ以外のHTMLは従来どおり警告。
                if span_color_match:
                    color = span_color_match.group(1).strip()
                    res.append(f'#text(fill: {self._color_to_typst(color)})[')
                    html_span_depth += 1
                elif self.HTML_SPAN_CLOSE_RE.match(content) and html_span_depth > 0:
                    res.append(']')
                    html_span_depth -= 1
                else:
                    checkbox = self._task_checkbox_glyph(t.content)
                    if checkbox is not None:
                        res.append(checkbox)
                    else:
                        self._warn_html(t)
            else:
                line_no = t.map[0] + 1 if t.map else '?'
                print(f"[Warning] Unhandled inline token '{t.type}' at {self.current_file}:{line_no}")
            # 改行直後のテキストのみ行頭エスケープの対象にする
            at_line_start = t.type in ['softbreak', 'hardbreak']
        if html_span_depth > 0:
            # 壊れたTypstコード（閉じ角括弧の不足）を生成しないよう自動で閉じ、書き忘れに気付けるよう警告する
            print(f"[Warning] Unclosed <span style=\"color:...\"> in {self.current_file}; closing it automatically.")
            res.append(']' * html_span_depth)
        return "".join(res)
        
    def _count_table_cols(self, tokens, start_idx):
        cols = 0
        for i in range(start_idx, len(tokens)):
            if tokens[i].type in ['th_open', 'td_open']:
                cols += 1
            if tokens[i].type == 'tr_close':
                break
        return max(1, cols)

    # 単純な英数字+ハイフンの識別子（例: "red"）のみ、Typstの色定数名として安全に生コード注入できる
    # と判断する。それ以外（"#eeeeee"のようなhex形式や、記号を含む不正な値）はrgb()の文字列引数
    # として渡す（Typstのコンパイルエラーとして安全に失敗する。文字列リテラル内なのでコード注入の
    # 心配もない）。
    COLOR_IDENTIFIER_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9\-]*$')

    def _color_to_typst(self, value):
        """config.yamlやMarkdownの色文字列をTypstの色表現へ変換する（#45、#46）。
        Typstのrgb()は"red"のような色名文字列を受け付けないため（hex文字列のみ）、"#rrggbb"形式は
        rgb()に、"red"のような単純な識別子はTypstの色定数名としてそのまま渡す。"""
        value = str(value).strip()
        if self.COLOR_IDENTIFIER_RE.match(value):
            return value
        return f'rgb("{escape_string_literal(value)}")'

    def _table_header_fill_arg(self):
        """table_header.backgroundが指定されていれば、#table()のfill:引数（1行目のみ着色）を返す。
        未指定なら空文字列（従来どおり無装飾）。"""
        background = self.table_header_style.get('background')
        if not background:
            return ''
        return f',\n  fill: (col, row) => if row == 0 {{ {self._color_to_typst(background)} }} else {{ none }}'

    def _table_header_open_close(self):
        """table_header.bold/colorに応じた、ヘッダセルの開き/閉じラッパー文字列のペアを返す。
        いずれも未指定なら空文字列（従来どおり無装飾）。スタイルはセル内で変化しないため、
        th_open/th_closeそれぞれで独立に呼び出しても一貫した結果になる。"""
        open_parts = []
        close_parts = []
        if self.table_header_style.get('bold'):
            open_parts.append('#strong[')
            close_parts.append(']')
        color = self.table_header_style.get('color')
        if color:
            open_parts.append(f'#text(fill: {self._color_to_typst(color)})[')
            close_parts.append(']')
        return ''.join(open_parts), ''.join(reversed(close_parts))

def deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict):
            d[k] = deep_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d

def default_config():
    return {
        "document": {
            "title": "System_Specification",
            "subtitle": "自動生成ドキュメント",
            "author": "開発チーム",
            "date": "auto"
        },
        "output": {
            "filename": "System_Specification.pdf",
            "dir": "outputs"
        },
        "template": {
            "path": "template"
        },
        "inputs": {
            "dir": "inputs",
            "files": None
        }
    }

def resolve_template_path(template_path_value, tool_dir, project_dir):
    """template.pathを「名前」と「パス」で区別して解決する（5章、#23）。
    拡張子(.typ)を含まない値（例: template, slide）は「名前」とみなし、ツール同梱の
    tool_dir/templates/<name>.typ から解決する。.typで終わる値は「パス」とみなし、
    他の相対パスと同じ規則（5章）でproject_dir基準で解決し、プロジェクト独自の
    テンプレートを持ち込めるようにする（サブディレクトリの有無を問わない）。
    絶対パスはos.path.joinの挙動によりそのまま使われる。"""
    if template_path_value.endswith('.typ'):
        return os.path.normpath(os.path.join(project_dir, template_path_value))
    return os.path.join(tool_dir, "templates", template_path_value + ".typ")

# CJKフォント(Noto Sans JP)の取得元。バイナリはリポジトリに同梱せず、初回ビルド時にのみ
# ここから取得しtool_dir/.fonts-cache/に保存する（2章の「最小限のダウンロード」方針）。
# 版とSHA256を固定し、同梱バイナリと違って取得結果が変わらないようにする（9章の決定論的出力）。
NOTO_SANS_JP_RELEASE_URL = "https://github.com/notofonts/noto-cjk/releases/download/Sans2.004/16_NotoSansJP.zip"
NOTO_SANS_JP_FILES = {
    "NotoSansJP-Regular.otf": "dff723ba59d57d136764a04b9b2d03205544f7cd785a711442d6d2d085ac5073",
    "NotoSansJP-Bold.otf": "1b0edfb500b73a4fa8a4fcaae1bbbd403994e08e73e3e0da37e70d3853f42c5f",
}

def ensure_fonts(tool_dir):
    """Noto Sans JP（Regular/Bold）が tool_dir/.fonts-cache/NotoSansJP/ になければダウンロードする。
    2回目以降のビルドはキャッシュを使い、ネットワークアクセスなしで完結する。"""
    font_dir = os.path.join(tool_dir, ".fonts-cache", "NotoSansJP")
    os.makedirs(font_dir, exist_ok=True)

    missing = [name for name in NOTO_SANS_JP_FILES if not os.path.exists(os.path.join(font_dir, name))]
    if not missing:
        return font_dir

    print("[Info] Downloading Noto Sans JP font (one-time; cached under .fonts-cache/)...")
    zip_path = os.path.join(font_dir, "_download.zip")
    try:
        urllib.request.urlretrieve(NOTO_SANS_JP_RELEASE_URL, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            for name in missing:
                data = zf.read(name)
                digest = hashlib.sha256(data).hexdigest()
                if digest != NOTO_SANS_JP_FILES[name]:
                    print(f"[Error] Checksum mismatch for {name}: expected {NOTO_SANS_JP_FILES[name]}, got {digest}")
                    sys.exit(1)
                with open(os.path.join(font_dir, name), "wb") as f:
                    f.write(data)
    except zipfile.BadZipFile as e:
        print(f"[Error] Failed to download fonts (bad zip): {e}")
        sys.exit(1)
    except OSError as e:
        print(f"[Error] Failed to download fonts: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

    return font_dir

# Mermaid公式配布の単一バンドルJS（UMD形式、全図種込み）。mermaid-cli丸ごと（npm依存ツリー約396MB）
# ではなくこのファイル単体（実測約3.4MB）だけを取得し、Playwright経由でヘッドレスブラウザに
# 読み込ませてmermaid.render()を直接呼び出す（仕様書11章、#35）。バージョン・SHA256を固定し、
# Noto Sans JPと同様に決定論的な取得結果にする（9章）。
MERMAID_JS_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.16.1/dist/mermaid.min.js"
MERMAID_JS_SHA256 = "18327bef70d96fb505fe7287d9f6a7362ebf07ff6576ddfaffb1a06f3e1a2954"

def ensure_mermaid_js(tool_dir):
    """mermaid.min.jsが tool_dir/.mermaid-cache/ になければダウンロードする。
    2回目以降のビルドはキャッシュを使い、ネットワークアクセスなしで完結する。"""
    cache_dir = os.path.join(tool_dir, ".mermaid-cache")
    os.makedirs(cache_dir, exist_ok=True)
    js_path = os.path.join(cache_dir, "mermaid.min.js")
    if os.path.exists(js_path):
        return js_path

    print("[Info] Downloading mermaid.min.js (one-time; cached under .mermaid-cache/)...")
    try:
        urllib.request.urlretrieve(MERMAID_JS_URL, js_path)
    except OSError as e:
        print(f"[Error] Failed to download mermaid.min.js: {e}")
        sys.exit(1)

    with open(js_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != MERMAID_JS_SHA256:
        os.remove(js_path)
        print(f"[Error] Checksum mismatch for mermaid.min.js: expected {MERMAID_JS_SHA256}, got {digest}")
        sys.exit(1)

    return js_path

# ローカルにJava 11+が見つからない場合のみ取得するEclipse Temurin JRE（Adoptium配布、
# GPLv2+Classpath Exception。OpenJDK本体と同じライセンス系統で安心度が高い）。CI
# （GitHub Actions ubuntu-latest等）はJavaが標準搭載されているためこの取得は発生しない（#22）。
# バージョン・プラットフォーム別にURL・SHA256を固定し、決定論的な取得結果にする（9章）。
TEMURIN_JRE_RELEASE = "jdk-21.0.12+8"
TEMURIN_JRE_BASE_URL = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12%2B8/"
TEMURIN_JRE_TOP_DIR = "jdk-21.0.12+8-jre"
# キー: (sys.platform判定用キー, platform.machine()正規化キー)。
# 値: (アーカイブファイル名, SHA256, アーカイブ形式, TEMURIN_JRE_TOP_DIR配下のjava実行ファイルへの相対パス)
TEMURIN_JRE_ASSETS = {
    ("win32", "x86_64"): ("OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip",
                           "b8aa18fef5edb69bee8618f99677d66d0873d22cb40d974c15ac9ffcdecf73ba",
                           "zip", ("bin", "java.exe")),
    ("win32", "aarch64"): ("OpenJDK21U-jre_aarch64_windows_hotspot_21.0.12_8.zip",
                            "a50ed83b6a88d3127d406713f5057d78f845c3412d59e201dac6db37714af85c",
                            "zip", ("bin", "java.exe")),
    ("linux", "x86_64"): ("OpenJDK21U-jre_x64_linux_hotspot_21.0.12_8.tar.gz",
                           "8a379a67c91a3ae61ffb33d46e0a40c7ba35e70713c4db31cfca30492f792eff",
                           "tar.gz", ("bin", "java")),
    ("linux", "aarch64"): ("OpenJDK21U-jre_aarch64_linux_hotspot_21.0.12_8.tar.gz",
                            "5f9c96b656827b9d14ebeda7739e25be554fa6d25669b03847c1df6e869c0679",
                            "tar.gz", ("bin", "java")),
    ("darwin", "x86_64"): ("OpenJDK21U-jre_x64_mac_hotspot_21.0.12_8.tar.gz",
                            "539706197baea8189c9a677aea5bf44671b74a71baa42dde436e312f2158fa3a",
                            "tar.gz", ("Contents", "Home", "bin", "java")),
    ("darwin", "aarch64"): ("OpenJDK21U-jre_aarch64_mac_hotspot_21.0.12_8.tar.gz",
                             "36bb71d6fa5184e12a6483e7662783c2cbd383f5dca8034140f0a84dd5aa797d",
                             "tar.gz", ("Contents", "Home", "bin", "java")),
}

def _temurin_platform_key():
    if sys.platform == "darwin":
        os_key = "darwin"
    elif sys.platform.startswith("linux"):
        os_key = "linux"
    else:
        os_key = "win32"
    machine = platform.machine().lower()
    arch_key = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    return os_key, arch_key

def ensure_temurin_jre(tool_dir):
    """tool_dir/.jre-cache/ にEclipse Temurin JREが無ければダウンロード・展開する。java実行
    ファイルの絶対パスを返す。2回目以降のビルドはキャッシュを使い、ネットワークアクセスなしで
    完結する（find_system_java()でシステムJavaが見つからなかった場合のみ呼ばれる、#22）。"""
    key = _temurin_platform_key()
    asset = TEMURIN_JRE_ASSETS.get(key)
    if asset is None:
        print(f"[Error] No Eclipse Temurin JRE build available for this platform ({key[0]}/{key[1]}). "
              "Install Java 11+ manually and ensure it is on PATH, or set plugins.plantuml: false.")
        sys.exit(1)
    filename, sha256, archive_type, java_rel_parts = asset

    cache_root = os.path.join(tool_dir, ".jre-cache")
    java_bin_path = os.path.join(cache_root, TEMURIN_JRE_TOP_DIR, *java_rel_parts)
    if os.path.exists(java_bin_path):
        return java_bin_path

    os.makedirs(cache_root, exist_ok=True)
    archive_path = os.path.join(cache_root, filename)
    print(f"[Info] No local Java 11+ found; downloading Eclipse Temurin JRE {TEMURIN_JRE_RELEASE} "
          "(one-time; cached under .jre-cache/)...")
    try:
        urllib.request.urlretrieve(TEMURIN_JRE_BASE_URL + filename, archive_path)
    except OSError as e:
        print(f"[Error] Failed to download Eclipse Temurin JRE: {e}")
        sys.exit(1)

    with open(archive_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != sha256:
        os.remove(archive_path)
        print(f"[Error] Checksum mismatch for {filename}: expected {sha256}, got {digest}")
        sys.exit(1)

    if archive_type == "zip":
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(cache_root)
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(cache_root)
    os.remove(archive_path)

    if not os.path.exists(java_bin_path):
        print(f"[Error] Eclipse Temurin JRE extraction did not produce the expected binary: {java_bin_path}")
        sys.exit(1)
    if key[0] != "win32":
        os.chmod(java_bin_path, 0o755)

    return java_bin_path

# PlantUML本体（MIT版。GPL/LGPL/Apache/EPL版と機能差はDITAA等ごく一部のみで、UML図生成は
# 100%対応。#22の調査でmit-light版はstdlib/クラウドアイコン素材と絵文字データのみが欠けることが
# 分かったが、Markdown原稿（GitHub管理・AI生成）には絵文字が含まれ得るため、フル機能のmit版を
# 採用する）。レイアウトエンジンはSmetana（純Java実装）を明示指定し、Graphviz(dot)実行ファイルへの
# 依存を避ける（-Playout=smetana）。バージョン・SHA256を固定し、決定論的な取得結果にする（9章）。
PLANTUML_JAR_URL = "https://github.com/plantuml/plantuml/releases/download/v1.2026.6/plantuml-mit-1.2026.6.jar"
PLANTUML_JAR_SHA256 = "5814ab31dd569f3772747c3a0c1b52fd3bf2996b8132c62d17006d758c2d3fe3"

def ensure_plantuml_jar(tool_dir):
    """plantuml.jarがtool_dir/.plantuml-cache/になければダウンロードする。
    2回目以降のビルドはキャッシュを使い、ネットワークアクセスなしで完結する。"""
    cache_dir = os.path.join(tool_dir, ".plantuml-cache")
    os.makedirs(cache_dir, exist_ok=True)
    jar_path = os.path.join(cache_dir, "plantuml-mit.jar")
    if os.path.exists(jar_path):
        return jar_path

    print("[Info] Downloading plantuml.jar (one-time; cached under .plantuml-cache/)...")
    try:
        urllib.request.urlretrieve(PLANTUML_JAR_URL, jar_path)
    except OSError as e:
        print(f"[Error] Failed to download plantuml.jar: {e}")
        sys.exit(1)

    with open(jar_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != PLANTUML_JAR_SHA256:
        os.remove(jar_path)
        print(f"[Error] Checksum mismatch for plantuml.jar: expected {PLANTUML_JAR_SHA256}, got {digest}")
        sys.exit(1)

    return jar_path

def _launch_headless_chrome(browser_path, user_data_dir):
    """browser_pathをリモートデバッグ有効・ヘッドレスで起動し、(Popen, ポート番号)を返す。
    ポートは0（OSに自動割当させる）を指定し、Chromeがuser_data_dir/DevToolsActivePortに
    書き出す実際のポートを読み取る（固定ポートによる競合を避けるため）。"""
    os.makedirs(user_data_dir, exist_ok=True)
    port_file = os.path.join(user_data_dir, "DevToolsActivePort")
    if os.path.exists(port_file):
        os.remove(port_file)

    proc = subprocess.Popen(
        [browser_path, "--remote-debugging-port=0", "--headless=new", "--disable-gpu",
         "--no-first-run", f"--user-data-dir={user_data_dir}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(80):
        if os.path.exists(port_file):
            with open(port_file, "r", encoding="utf-8") as f:
                port = int(f.readline().strip())
            return proc, port
        if proc.poll() is not None:
            break
        time.sleep(0.25)

    proc.terminate()
    print("[Error] Headless browser did not become ready in time (needed for mermaid rendering).")
    sys.exit(1)

def load_config_file(config_path):
    """指定された1ファイル(yaml/json)から設定を読み込む。存在しなければFail-fast。"""
    config = default_config()
    if not os.path.exists(config_path):
        print(f"[Error] Config file not found: {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        if config_path.endswith(('.yaml', '.yml')):
            if yaml is None:
                print("[Error] PyYAML is not installed; cannot read a .yaml config file.")
                sys.exit(1)
            loaded = yaml.safe_load(f) or {}
        else:
            loaded = json.load(f) or {}
    deep_update(config, loaded)
    return config

def escape_string_literal(text):
    return str(text).replace('\\', '\\\\').replace('"', '\\"')

def _typst_str_or_none(value):
    """PythonのNone/文字列をTypstの`none`/文字列リテラルへ変換する（#42のheader/footer等）。"""
    if value is None:
        return "none"
    return f'"{escape_string_literal(str(value))}"'

def _resolve_project_image_path(path, base_dir, typst_root, label):
    """document.background/chapters[].background（#55）、document.logo/chapters[].logo（#54）の
    相対パスを、project_dir基準からtypst_root起点のルート絶対パスへ変換する（5章: config.yaml内の
    相対パスはproject_dir基準。Markdown内画像の_resolve_asset()とは基準ディレクトリが異なる）。
    仕様9章のFail-fast方針に従い、画像欠損は即エラーとする。"""
    if not path:
        return None
    abs_path = os.path.normpath(os.path.join(base_dir, path))
    if not os.path.exists(abs_path):
        print(f"[Error] {label} image not found: {abs_path}")
        sys.exit(1)
    return "/" + os.path.relpath(abs_path, typst_root).replace(os.sep, '/')

def _page_set_fragment(paper, landscape, header, footer, paginate, background, logo):
    """paper/landscape/header/footer/paginate/background/logoをまとめた#set page(...)断片を
    組み立てる（#42、#17、#55、#54）。headerがNone（chapters[]/front-matterで明示的にnullを
    指定した場合のみ起こりうる。グローバルの既定値は常にtitleへフォールバック済みでNoneにならない）
    ならheader自体を非表示にする（logoも一緒に消える。ヘッダーごと消す指定のため妥当）。
    footerはrender-footer()側でNone/paginateの組み合わせを判定するため、常にrender-footer()を
    呼ぶ。backgroundも同様にrender-background()側でNone判定する。"""
    header_expr = ("none" if header is None
                    else f'render-header({_typst_str_or_none(header)}, {_typst_str_or_none(logo)})')
    footer_expr = f'render-footer({_typst_str_or_none(footer)}, {str(paginate).lower()})'
    background_expr = f'render-background({_typst_str_or_none(background)})'
    return (f'#set page(paper: "{paper}", flipped: {str(landscape).lower()}, '
            f'header: {header_expr}, footer: {footer_expr}, background: {background_expr})\n')

def _build_glossary_section(glossary_terms):
    """document.glossary: trueの場合、全チャプター処理後にTypstRenderer.glossary_terms
    （term -> [label_id, ...]）から巻末の用語索引ページを組み立てる（#47）。文字コード順
    （Pythonのsorted()）で並べ、同じ用語の全出現ページ番号を重複除去のうえ昇順で列挙する。
    定義文は持たない索引型（本の巻末索引と同じ形）。"""
    entries = []
    for term in sorted(glossary_terms.keys()):
        label_ids = glossary_terms[term]
        label_list = ", ".join(f'"{escape_string_literal(lbl)}"' for lbl in label_ids)
        safe_term = escape_string_literal(term)
        entries.append(f'  ("{safe_term}", ({label_list},)),')
    entries_block = "\n".join(entries)

    static_part = """
#context {
  for (term, label_ids) in __glossary_entries {
    let pages = ()
    for lbl in label_ids {
      let found = query(label(lbl))
      if found.len() > 0 {
        pages.push(found.first().location().page())
      }
    }
    pages = pages.sorted().dedup()
    let page-str = pages.map(str).join(", ")
    [#term #box(width: 1fr, repeat[.]) #page-str]
    linebreak()
  }
}
"""
    return (
        "\n#pagebreak(weak: true)\n"
        "= 用語索引\n\n"
        "#let __glossary_entries = (\n"
        f"{entries_block}\n"
        ")\n"
        + static_part
    )

def extract_md_string(data, key):
    """YAMLからテキストを抽出。リスト形式の場合は改行で結合して単一文字列にする"""
    val = data.get(key, "")
    if isinstance(val, list):
        return "\n".join(str(v) for v in val)
    return str(val)

def find_config_in_cwd():
    """--config省略時、カレントディレクトリ直下の推奨ファイル名を探す（ツール本体ディレクトリは見ない）。"""
    for name in ("context-compositor.config.yaml", "context-compositor.config.json"):
        path = os.path.join(os.getcwd(), name)
        if os.path.exists(path):
            return path
    return None

def parse_args():
    parser = argparse.ArgumentParser(description="Markdown -> Typst -> PDF ドキュメントビルダー")
    parser.add_argument("--config", help="設定ファイル(yaml/json)へのパス。省略時はカレントディレクトリの context-compositor.config.yaml/.json を探す。")
    parser.add_argument("--config-list", help="ビルド対象のconfigファイルパスを1行1件で列挙したテキストファイル。空行と'#'で始まる行は無視される。--configとは同時指定できない。相対パスはこのファイル自身の置き場所が基準。")
    args = parser.parse_args()
    if args.config and args.config_list:
        parser.error("--config と --config-list は同時に指定できません。")
    return args

def _read_config_list(list_path):
    """--config-listのファイルを読み、configファイルパスのリストを返す（コメント行・空行を除く）。"""
    list_path = os.path.abspath(list_path)
    base_dir = os.path.dirname(list_path)
    paths = []
    with open(list_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            paths.append(line if os.path.isabs(line) else os.path.join(base_dir, line))
    return paths

def _load_project_config(config_path):
    """configパス（Noneならカレントディレクトリから探索）から設定ファイルを読み込み、(project_dir, config, chapters)を返す。"""
    if config_path:
        config_path = os.path.abspath(config_path)
    else:
        config_path = find_config_in_cwd()
        if not config_path:
            print("[Error] --config not specified, and no context-compositor.config.yaml/.json found in the current directory.")
            sys.exit(1)
    project_dir = os.path.dirname(config_path)
    config = load_config_file(config_path)

    chapters = config.get("chapters", [])
    # 【修正】章が空の場合は正常終了せずFail-fastでエラー終了させる
    if not chapters:
        print("[Error] No chapters configured in config.yaml. Aborting.")
        sys.exit(1)
    return project_dir, config, chapters

def _resolve_project_dirs(project_dir, config):
    """出力先・入力元・作業ディレクトリと、それらを跨ぐ--root（typst_root）を解決する。"""
    outputs_dir = os.path.normpath(os.path.join(project_dir, config["output"]["dir"]))
    os.makedirs(outputs_dir, exist_ok=True)
    # 【修正】ハードコードをやめ config の inputs.dir を実際に使用する
    inputs_dir = os.path.normpath(os.path.join(project_dir, config.get("inputs", {}).get("dir") or "inputs"))

    work_dir = os.path.join(project_dir, ".context-compositor")
    os.makedirs(work_dir, exist_ok=True)

    # project_dir・inputs_dir・outputs_dir・work_dirすべてを跨いでtypstから参照できるよう、
    # それら全ての共通の親ディレクトリを --root にする（tool_dirは含めない）
    typst_root = os.path.commonpath([project_dir, inputs_dir, outputs_dir, work_dir])
    return outputs_dir, inputs_dir, work_dir, typst_root

def _prepare_template(config, tool_dir, project_dir, work_dir, typst_root):
    """template.pathを解決してwork_dir配下へコピーし、(コピー先の絶対パス, --root起点の
    ルート絶対パス文字列)を返す。8章のセキュリティ要件（tool_dirを--rootにしない）を満たす
    ため、テンプレートは元の置き場所に関わらずwork_dir（--rootの内側）へコピーしてから参照する。"""
    template_abs_path = resolve_template_path(config["template"]["path"], tool_dir, project_dir)
    if not os.path.exists(template_abs_path):
        print(f"[Error] Template not found: {template_abs_path}")
        sys.exit(1)
    template_copy_path = os.path.join(work_dir, "_template" + os.path.splitext(template_abs_path)[1])
    shutil.copyfile(template_abs_path, template_copy_path)

    # 生成コード(temp_build.typ)の実際の置き場所に依存させないよう、typst_root起点の
    # ルート絶対パスに変換する（.context-compositor/等サブディレクトリに置いても解決できる）。
    template_root_rel_path = "/" + os.path.relpath(template_copy_path, typst_root).replace(os.sep, '/')
    return template_copy_path, template_root_rel_path

def _build_document_preamble(config, template_root_rel_path, graphviz_enabled, project_dir, typst_root):
    """document:設定からtypst_codeの冒頭（テンプレートのimportとconf()呼び出し）を組み立てる。
    戻り値は (preamble文字列, global_landscape, global_paper, cover_mode, global_table_header,
    global_header, global_footer, global_paginate, global_background, global_logo)。"""
    doc_config = config.get("document", {})
    global_landscape = str(doc_config.get('landscape', False)).lower() == 'true'
    global_paper = doc_config.get('paper_size', 'a4')
    # 通常のMarkdownテーブルのヘッダ行スタイル（#45）。未指定なら従来どおり無装飾。
    global_table_header = doc_config.get('table_header') or {}
    # 本文ページのヘッダー・フッター・ページ番号表示（#42）。header/footerは未指定ならNone
    # （テンプレート側でheaderはtitleへフォールバックする。footerはページ番号のみの従来動作）。
    global_header = doc_config.get('header')
    global_footer = doc_config.get('footer')
    global_paginate = str(doc_config.get('paginate', True)).lower() == 'true'
    # 本文ページの背景画像（#55）。header/footerと同じ「常にconf()へ渡す必須引数」パターンで、
    # chapters[]単位の上書きにも対応する（_page_set_fragment）。
    global_background = _resolve_project_image_path(doc_config.get('background'), project_dir, typst_root, "Background")
    # ヘッダーのロゴ画像（#54）。backgroundと全く同じパターン。
    global_logo = _resolve_project_image_path(doc_config.get('logo'), project_dir, typst_root, "Logo")

    # 表紙の扱い: template=テンプレートの表紙のみ / replace=テンプレートの表紙でMarkdown先頭の
    # タイトルスライドを置き換える / markdown=Markdown側のみ / none=表紙なし。既定はnone（安定版前の
    # ため、表紙の要否を明示させる方針。#58の目次デフォルト変更と合わせた判断）
    cover_mode = doc_config.get('cover', 'none')
    if isinstance(cover_mode, bool):
        cover_mode = 'template' if cover_mode else 'none'
    cover_mode = str(cover_mode).lower()
    if cover_mode not in ('template', 'replace', 'markdown', 'none'):
        print(f"[Error] Invalid document.cover: {cover_mode!r} (expected template / replace / markdown / none)")
        sys.exit(1)
    # template/replaceのときだけ引数を渡さず、cover引数を持たない既存テンプレートとの互換を保つ
    cover_arg = '' if cover_mode in ('template', 'replace') else '  cover: false,\n'

    # 表紙のページ番号表示。未指定ならテンプレート自身の既定値に任せ、引数自体を渡さない
    cover_page_number = doc_config.get('cover_page_number')
    cover_page_number_arg = (
        f'  cover_page_number: {str(bool(cover_page_number)).lower()},\n'
        if cover_page_number is not None else ''
    )

    # 目次の表示有無（#58）。未指定ならテンプレート自身の既定値（false）に任せ、引数自体を渡さない
    toc = doc_config.get('toc')
    toc_arg = f'  toc: {str(bool(toc)).lower()},\n' if toc is not None else ''

    date_str = doc_config.get("date", "")
    if date_str == "auto":
        date_str = datetime.now().strftime("%Y-%m-%d")

    safe_title = escape_string_literal(doc_config.get('title', 'Untitled'))
    safe_subtitle = escape_string_literal(doc_config.get('subtitle', ''))
    safe_author = escape_string_literal(doc_config.get('author', ''))
    safe_date = escape_string_literal(date_str)

    preamble = f"""
#import "{template_root_rel_path.replace(os.sep, '/')}": conf, fit-image, render-header, render-footer, render-background, callout
#show: doc => conf(
  title: "{safe_title}",
  subtitle: "{safe_subtitle}",
  author: "{safe_author}",
  date: "{safe_date}",
  paper_size: "{global_paper}",
  landscape: {str(global_landscape).lower()},
{cover_arg}{cover_page_number_arg}{toc_arg}  graphviz: {str(graphviz_enabled).lower()},
  header: {_typst_str_or_none(global_header)},
  footer: {_typst_str_or_none(global_footer)},
  paginate: {str(global_paginate).lower()},
  background: {_typst_str_or_none(global_background)},
  logo: {_typst_str_or_none(global_logo)},
  doc,
)

"""
    return (preamble, global_landscape, global_paper, cover_mode, global_table_header,
            global_header, global_footer, global_paginate, global_background, global_logo)

def _parse_chapter_entry(ch):
    """chaptersの1エントリを解析し、(ファイル/ディレクトリ名, 章固有設定のdict, 種別)を返す。
    種別は"file"（Markdown等の通常章）または"aggregate"（YAML/JSON集約）。"""
    if isinstance(ch, str):
        return ch, {}, "file"
    if not isinstance(ch, dict):
        print(f"[Error] Invalid chapter entry (must be a string or a mapping): {ch!r}")
        sys.exit(1)
    if "aggregate" in ch:
        ch_file = ch["aggregate"]
        ch_type = "aggregate"
    else:
        ch_file = ch.get("file")
        ch_type = "file"
    if not ch_file:
        print(f"[Error] Invalid chapter entry (no 'file' or 'aggregate' key): {ch!r}")
        sys.exit(1)
    return ch_file, ch, ch_type

def _render_aggregate_chapter(ch_dict, ch_file, inputs_dir, renderer, current_landscape, current_paper,
                               global_landscape, global_paper, current_header, current_footer, current_paginate,
                               global_header, global_footer, global_paginate, current_background, global_background,
                               current_logo, global_logo):
    """aggregate: チャプター（YAML/JSONファイル群のテーブル集約）をTypstへ変換する。
    aggregateはYAML/JSONのテストケース集約であり、front-matter（Markdown固有の概念）は関係しない。
    戻り値は (typst断片, 更新後のcurrent_landscape, 更新後のcurrent_paper, 更新後のcurrent_header,
    更新後のcurrent_footer, 更新後のcurrent_paginate, 更新後のcurrent_background, 更新後のcurrent_logo)。"""
    typst_code = ""
    ch_landscape = str(ch_dict.get("landscape", global_landscape)).lower() == 'true'
    ch_paper = ch_dict.get("paper_size", global_paper)
    ch_header = ch_dict.get("header", global_header)
    ch_footer = ch_dict.get("footer", global_footer)
    ch_paginate = str(ch_dict.get("paginate", global_paginate)).lower() == 'true'
    ch_background = (_resolve_project_image_path(ch_dict["background"], renderer.base_dir, renderer.typst_root, "Background")
                      if "background" in ch_dict else global_background)
    ch_logo = (_resolve_project_image_path(ch_dict["logo"], renderer.base_dir, renderer.typst_root, "Logo")
               if "logo" in ch_dict else global_logo)
    if (ch_landscape, ch_paper, ch_header, ch_footer, ch_paginate, ch_background, ch_logo) != (
            current_landscape, current_paper, current_header, current_footer, current_paginate, current_background, current_logo):
        typst_code += _page_set_fragment(ch_paper, ch_landscape, ch_header, ch_footer, ch_paginate, ch_background, ch_logo)
        current_landscape, current_paper = ch_landscape, ch_paper
        current_header, current_footer, current_paginate = ch_header, ch_footer, ch_paginate
        current_background, current_logo = ch_background, ch_logo

    agg_path = os.path.join(inputs_dir, ch_file)
    typst_code += f'= {renderer.escape_typst(ch_dict.get("title", "Test Cases"))}\n\n'

    if os.path.exists(agg_path) and os.path.isdir(agg_path):
        # 【修正】YAMLだけでなくJSONファイルも読み込み対象に含める
        tc_files = sorted([f for f in os.listdir(agg_path) if f.endswith(('.yaml', '.yml', '.json'))])

        typst_code += '#table(\n  columns: (auto, auto, auto, 1fr, 1fr),\n'
        typst_code += '  align: (center, left, center, left, left),\n'
        typst_code += '  stroke: 0.5pt + luma(150),\n'
        typst_code += '  fill: (col, row) => if row == 0 { luma(240) } else { none },\n'
        typst_code += '  [*ID*], [*Title*], [*Priority*], [*Steps*], [*Expected*],\n'

        for tc_file in tc_files:
            tc_path = os.path.join(agg_path, tc_file)
            with open(tc_path, "r", encoding="utf-8") as f:
                try:
                    if tc_file.endswith('.json'):
                        tc_data = json.load(f) or {}
                    else:
                        tc_data = yaml.safe_load(f) or {}
                except Exception as e:
                    print(f"[Warning] Failed to parse {tc_file}: {e}")
                    continue

            tc_id = renderer.escape_typst(str(tc_data.get("id", "")))
            tc_title = renderer.escape_typst(str(tc_data.get("title", "")))
            tc_priority = renderer.escape_typst(str(tc_data.get("priority", "")))

            # 【修正】YAMLでリスト形式で書かれていた場合も結合して安全に処理する
            steps_md = extract_md_string(tc_data, "steps")
            expected_md = extract_md_string(tc_data, "expected")
            steps_typst = renderer.render(steps_md, filepath=tc_path).strip()
            expected_typst = renderer.render(expected_md, filepath=tc_path).strip()

            typst_code += f'  [{tc_id}], [{tc_title}], [{tc_priority}], [{steps_typst}], [{expected_typst}],\n'

        typst_code += ')\n\n#pagebreak(weak: true)\n'
    else:
        # 仕様9章: 入力欠損は黙って飛ばさず即エラー (Fail-fast)
        print(f"[Error] Aggregate directory not found: {agg_path}")
        sys.exit(1)

    return typst_code, current_landscape, current_paper, current_header, current_footer, current_paginate, current_background, current_logo

def _render_markdown_chapter(ch_dict, ch_file, inputs_dir, renderer, current_landscape, current_paper,
                              global_landscape, global_paper, is_first_chapter, cover_mode, global_table_header,
                              current_header, current_footer, current_paginate,
                              global_header, global_footer, global_paginate, current_background, global_background,
                              current_logo, global_logo):
    """通常のチャプター（Markdown/YAML/JSON/プレーンテキスト等、#15の拡張子ディスパッチ対象）を
    Typstへ変換する。戻り値は (typst断片, 更新後のcurrent_landscape, 更新後のcurrent_paper,
    更新後のcurrent_header, 更新後のcurrent_footer, 更新後のcurrent_paginate, 更新後のcurrent_background,
    更新後のcurrent_logo)。"""
    md_path = os.path.join(inputs_dir, ch_file)
    if not os.path.exists(md_path):
        print(f"[Error] Chapter file not found: {md_path}")
        sys.exit(1)

    # テーブルヘッダのスタイル（#45）。chapters[].table_headerはdocument.table_headerに対する
    # キー単位の上書き（chapters[].landscape/paper_sizeと同じ優先順位）。前後関係上、
    # front-matterはrender_chapter()実行後にしかわからないため、front-matterでの上書きは
    # サポートしない（#41以降、front-matterはlandscape/paper_size/font_sizeのみ反映する方針）。
    ch_table_header = dict(global_table_header)
    ch_table_header.update(ch_dict.get("table_header") or {})
    renderer.table_header_style = ch_table_header

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    chapter_typst = renderer.render_chapter(
        md_text, filepath=md_path,
        drop_leading_title=is_first_chapter and cover_mode in ('replace', 'none'))
    front_matter = renderer.front_matter

    # front-matterのpaper_size/landscapeは、config.yamlのチャプター個別設定より弱い
    # 優先順位で適用する（7章、#17）。config.yaml側に明示指定が無い場合のみ使う。
    # front-matterはファイルを読んで初めてわかるため、#set pageの要否判定もここで行う
    # （aggregateには front-matter の概念が無く、判定をchapters読み込み前に済ませられる）。
    ch_landscape = str(ch_dict.get("landscape", front_matter.get("landscape", global_landscape))).lower() == 'true'
    ch_paper = ch_dict.get("paper_size", front_matter.get("paper_size", global_paper))
    # header/footer/paginateも同じ優先順位（chapters[]の明示指定＞front-matter＞グローバル）で
    # 解決する（#42）。state()は使わず、landscape/paper_sizeと同じ「変化した時だけ#set pageを
    # 出し直す」パターンで、章の並べ替えに対して安全にする。
    ch_header = ch_dict.get("header", front_matter.get("header", global_header))
    ch_footer = ch_dict.get("footer", front_matter.get("footer", global_footer))
    ch_paginate = str(ch_dict.get("paginate", front_matter.get("paginate", global_paginate))).lower() == 'true'
    # 背景画像（#55）・ロゴ（#54）。パス値のためfront-matter経由の上書きはサポートしない
    # （table_headerと同じ判断）。
    ch_background = (_resolve_project_image_path(ch_dict["background"], renderer.base_dir, renderer.typst_root, "Background")
                      if "background" in ch_dict else global_background)
    ch_logo = (_resolve_project_image_path(ch_dict["logo"], renderer.base_dir, renderer.typst_root, "Logo")
               if "logo" in ch_dict else global_logo)
    typst_code = ""
    if (ch_landscape, ch_paper, ch_header, ch_footer, ch_paginate, ch_background, ch_logo) != (
            current_landscape, current_paper, current_header, current_footer, current_paginate, current_background, current_logo):
        typst_code += _page_set_fragment(ch_paper, ch_landscape, ch_header, ch_footer, ch_paginate, ch_background, ch_logo)
        current_landscape, current_paper = ch_landscape, ch_paper
        current_header, current_footer, current_paginate = ch_header, ch_footer, ch_paginate
        current_background, current_logo = ch_background, ch_logo

    font_size = front_matter.get('font_size')
    if font_size:
        # スコープを#[...]で閉じ、このチャプターだけにフォントサイズ指定を適用する
        typst_code += f"#[\n#set text(size: {font_size})\n{chapter_typst}\n]\n"
    else:
        typst_code += chapter_typst
    # front-matterのtitle/subtitle/author/dateは認識はするが、何も反映しない（#41）。
    # 文書全体の表紙（title/subtitle/author/date）は常にconfig.yaml側のみが正。
    typst_code += "\n#pagebreak(weak: true)\n"

    return typst_code, current_landscape, current_paper, current_header, current_footer, current_paginate, current_background, current_logo

def _compile_and_cleanup(typst_code, work_dir, outputs_dir, config, typst_root, font_dir, template_copy_path):
    """temp_build.typへ書き出してtypstコンパイルし、成功時は使い捨ての中間ファイルを削除する。"""
    temp_typ_path = os.path.join(work_dir, "temp_build.typ")
    with open(temp_typ_path, "w", encoding="utf-8") as f:
        f.write(typst_code)

    out_pdf = os.path.join(outputs_dir, config["output"]["filename"])

    try:
        typst_lib.compile(temp_typ_path, output=out_pdf, root=typst_root, font_paths=[font_dir])
        print(f"[Success] Generated PDF: {out_pdf}")
    except typst_lib.TypstError as e:
        print(f"[Error] Compile failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[Error] Execution failed: {e}")
        sys.exit(1)

    # ビルド成功後、使い捨ての中間ファイルを削除する（12章、#20）。
    # mermaidキャッシュ(cache/)は次回以降のビルドで再利用するため対象外。
    # 失敗時は温存し、生成されたTypstコードをそのままデバッグに使えるようにする。
    os.remove(temp_typ_path)
    os.remove(template_copy_path)

def build():
    tool_dir = os.path.dirname(os.path.abspath(__file__))
    args = parse_args()
    font_dir = ensure_fonts(tool_dir)

    if args.config_list:
        config_paths = _read_config_list(args.config_list)
        if not config_paths:
            print(f"[Error] --config-list {args.config_list} に有効なconfigパスがありません。")
            sys.exit(1)
        # いずれかのビルドが失敗した時点でsys.exit(1)により停止する（_load_project_config等が担う）。
        for config_path in config_paths:
            print(f"[Build] {config_path}")
            _build_one(tool_dir, font_dir, config_path)
    else:
        _build_one(tool_dir, font_dir, args.config)

def _build_one(tool_dir, font_dir, config_path):
    # 汎用ツールとして、呼び出し元プロジェクトが持つ設定ファイルを指定できるようにする。
    # inputs.dir/output.dir などプロジェクト固有の相対パスは、このconfigファイルの
    # 置き場所(project_dir)を基準に解決する。templates/等ツール自身のリソースはtool_dir基準のまま。
    project_dir, config, chapters = _load_project_config(config_path)

    # plugins: Graphviz/PlantUML/Mermaidの有効・無効切り替え（6章、#21）。未指定時は既存動作を
    # 維持する既定値（graphviz/mermaid/plantumlはいずれも常時有効）。
    # *_auto_download は、システムに必要なツール（ブラウザ/Java）が無い場合の振る舞いを制御する
    # 別軸のフラグ（#22の設計議論）。既定値が非対称なのは、ダウンロードされる実体のサイズが
    # 一桁違うため（Playwright自身のChromium: 約700MB対Eclipse Temurin JRE: 約49.7MB）。
    plugins_config = config.get("plugins") or {}
    graphviz_enabled = bool(plugins_config.get("graphviz", True))
    mermaid_enabled = bool(plugins_config.get("mermaid", True))
    mermaid_auto_download = bool(plugins_config.get("mermaid_auto_download", False))
    plantuml_enabled = bool(plugins_config.get("plantuml", True))
    plantuml_auto_download = bool(plugins_config.get("plantuml_auto_download", True))
    # document.glossary: false（既定。#47）。trueなら[[用語]]を検出し、巻末に索引ページを生成する。
    glossary_enabled = bool(config.get("document", {}).get("glossary", False))

    outputs_dir, inputs_dir, work_dir, typst_root = _resolve_project_dirs(project_dir, config)
    template_copy_path, template_root_rel_path = _prepare_template(config, tool_dir, project_dir, work_dir, typst_root)

    (typst_code, global_landscape, global_paper, cover_mode, global_table_header,
     global_header, global_footer, global_paginate, global_background, global_logo) = _build_document_preamble(
        config, template_root_rel_path, graphviz_enabled, project_dir, typst_root)

    # headerの実効グローバル既定値。document.headerが未指定ならテンプレート側と同じくtitleへ
    # フォールバックする（#42）。章ごとの解決(chapters[]/front-matter)は、この実効値を起点にする。
    doc_title = config.get("document", {}).get("title", "Untitled")
    effective_global_header = global_header if global_header is not None else doc_title

    renderer = TypstRenderer(project_dir, typst_root=typst_root,
                              mermaid_enabled=mermaid_enabled, mermaid_auto_download=mermaid_auto_download,
                              plantuml_enabled=plantuml_enabled, plantuml_auto_download=plantuml_auto_download,
                              glossary_enabled=glossary_enabled, tool_dir=tool_dir)
    current_landscape, current_paper = global_landscape, global_paper
    current_header, current_footer, current_paginate = effective_global_header, global_footer, global_paginate
    current_background = global_background
    current_logo = global_logo
    is_first_chapter = True

    try:
        for ch in chapters:
            ch_file, ch_dict, ch_type = _parse_chapter_entry(ch)
            if ch_type == "aggregate":
                (fragment, current_landscape, current_paper,
                 current_header, current_footer, current_paginate,
                 current_background, current_logo) = _render_aggregate_chapter(
                    ch_dict, ch_file, inputs_dir, renderer, current_landscape, current_paper,
                    global_landscape, global_paper, current_header, current_footer, current_paginate,
                    effective_global_header, global_footer, global_paginate, current_background, global_background,
                    current_logo, global_logo)
            else:
                (fragment, current_landscape, current_paper,
                 current_header, current_footer, current_paginate,
                 current_background, current_logo) = _render_markdown_chapter(
                    ch_dict, ch_file, inputs_dir, renderer, current_landscape, current_paper,
                    global_landscape, global_paper, is_first_chapter, cover_mode, global_table_header,
                    current_header, current_footer, current_paginate,
                    effective_global_header, global_footer, global_paginate, current_background, global_background,
                    current_logo, global_logo)
            typst_code += fragment
            is_first_chapter = False
    finally:
        # mermaidレンダリング用に起動したヘッドレスブラウザを、エラー終了時も含め必ず片付ける（#35）。
        renderer.close()

    if (current_landscape, current_paper, current_header, current_footer, current_paginate, current_background, current_logo) != (
            global_landscape, global_paper, effective_global_header, global_footer, global_paginate, global_background, global_logo):
        typst_code += _page_set_fragment(
            global_paper, global_landscape, effective_global_header, global_footer, global_paginate, global_background, global_logo)

    # 巻末の用語索引（#47）。全チャプター処理後、実際に[[用語]]が使われていた場合のみ追加する。
    if glossary_enabled and renderer.glossary_terms:
        typst_code += _build_glossary_section(renderer.glossary_terms)

    _compile_and_cleanup(typst_code, work_dir, outputs_dir, config, typst_root, font_dir, template_copy_path)

if __name__ == "__main__":
    build()
