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
from datetime import datetime
from pathlib import Path
from markdown_it import MarkdownIt
# PyPIの typst パッケージ(typst-py)はコンパイラ本体をプラットフォーム別ホイールに同梱しているため、
# tools/typst.exe のような実行バイナリをリポジトリに持たずに済む（pipがOSごとに正しい版を入れてくれる）
import typst as typst_lib

try:
    import yaml
except ImportError:
    yaml = None

# ローカル環境やGitHub Actionsランナー(ubuntu-latest)に標準搭載されているChrome/Edgeの
# インストール先候補。見つかればPUPPETEER_EXECUTABLE_PATHに指定し、Puppeteerによる
# Chromiumの自動ダウンロード（実測699MB。#34）を回避する（仕様書11章）。
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

    # front-matter のうちMarp固有で本ツールでは意味を持たないキー
    MARP_ONLY_KEYS = {'marp', 'theme', 'paginate', 'header', 'footer', 'size', 'class', 'style', 'backgroundColor'}

    # ::: layout-right / layout-compare ... ::: ブロック。
    # - layout-right: 中のmermaid図を右、それ以外のテキストを左に配置する。
    # - layout-compare: 中の2つのmermaid図を左右に並べる（横長の図同士の比較用）。
    # markdown-it の通常のASTフローでは「直前・直後のテキストと図をまとめて2カラム化する」表現が
    # 難しいため、通常のトークン処理に入る前の生テキスト段階で切り出して個別に処理する。
    LAYOUT_BLOCK_RE = re.compile(r'^::: *(layout-right|layout-compare) *\r?\n(.*?)\r?\n::: *\r?$', re.MULTILINE | re.DOTALL)
    MERMAID_FENCE_RE = re.compile(r'```mermaid\r?\n(.*?)\r?\n```', re.DOTALL)

    def __init__(self, base_dir=None, typst_root=None, mermaid_enabled=True):
        self.md = MarkdownIt("commonmark").enable("table")
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
        # plugins.mermaid: false（6章、#21）。falseなら```mermaidフェンスをmmdcで描画せず、
        # 他の未対応言語と同じく素のコード表示にフォールバックする。
        self.mermaid_enabled = mermaid_enabled
        self._mermaid_disabled_warned = False

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
            if block_kind == 'layout-right':
                output.append(self._render_layout_block(block_body))
            else:
                output.append(self._render_compare_block(block_body))
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

    def _render_layout_block(self, inner_text):
        """::: layout-right ... ::: ブロックを、左=テキスト／右=画像の2カラムgridへ変換する"""
        fence_match = self.MERMAID_FENCE_RE.search(inner_text)
        if not fence_match:
            print(f"[Error] 'layout-right' block in {self.current_file} must contain exactly one ```mermaid fence.")
            sys.exit(1)
        surrounding_md = (inner_text[:fence_match.start()] + inner_text[fence_match.end():]).strip()
        text_typst = self._render_markdown_segment(surrounding_md, False).strip()
        image_typst = self._render_mermaid(fence_match.group(1)).strip()
        # テキストは短めなことが多く、画像側により多くの幅を渡した方が図が読みやすいため 35:65 とする
        return (
            "#grid(\n"
            "  columns: (35fr, 65fr),\n"
            "  column-gutter: 1.5em,\n"
            "  align: (left + top, center + horizon),\n"
            f"  [{text_typst}],\n"
            f"  [{image_typst}],\n"
            ")\n\n"
        )

    def _render_compare_block(self, inner_text):
        """::: layout-compare ... ::: ブロックを、2つのmermaid図を左右に並べた2カラムgridへ変換する。
        各図の直前にあるテキスト（キャプション）は、その図と同じ列にまとめて配置する。"""
        fences = list(self.MERMAID_FENCE_RE.finditer(inner_text))
        if len(fences) != 2:
            print(f"[Error] 'layout-compare' block in {self.current_file} must contain exactly two ```mermaid fences (found {len(fences)}).")
            sys.exit(1)
        cells = []
        prev_end = 0
        for i, fence in enumerate(fences):
            caption_md = inner_text[prev_end:fence.start()].strip()
            # 2番目以降の図の後ろに残ったテキストは、最後の列にまとめて含める
            trailing_md = inner_text[fences[-1].end():].strip() if i == len(fences) - 1 else ""
            caption_typst = self._render_markdown_segment(caption_md, False).strip() if caption_md else ""
            image_typst = self._render_mermaid(fence.group(1)).strip()
            trailing_typst = self._render_markdown_segment(trailing_md, False).strip() if trailing_md else ""
            cell = "\n\n".join(t for t in [caption_typst, image_typst, trailing_typst] if t)
            cells.append(cell)
            prev_end = fence.end()
        columns_typst = ",\n".join(f"  [{cell}]" for cell in cells)
        return (
            "#grid(\n"
            "  columns: (1fr, 1fr),\n"
            "  column-gutter: 1.5em,\n"
            "  align: (left + top, left + top),\n"
            f"{columns_typst},\n"
            ")\n\n"
        )

    def _skip_leading_title(self, tokens):
        """cover: replace/none 用に、先頭のタイトルブロック（H1/H2と直後の区切り線）を読み飛ばす"""
        i = 0
        dropped = []
        # 先頭のHTMLコメント（Marpのディレクティブ等）は読み飛ばす。ただし警告は従来どおり出す
        while i < len(tokens) and tokens[i].type in ['html_block', 'html_inline']:
            self._warn_html(tokens[i])
            i += 1
        while i < len(tokens) and tokens[i].type == 'heading_open' and int(tokens[i].tag[1:]) <= 2:
            j = i
            while j < len(tokens) and tokens[j].type != 'heading_close':
                if tokens[j].type == 'inline':
                    dropped.append(tokens[j].content)
                j += 1
            i = j + 1
        if not dropped:
            return 0
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
                                                              'paper_size', 'landscape', 'font_size'):
                print(f"[Warning] Unknown front-matter key '{key}' in {self.current_file}")
        if 'font_size' in meta and not re.match(r'^\d+(\.\d+)?pt$', str(meta['font_size'])):
            print(f"[Warning] front-matter 'font_size' in {self.current_file} should look like '16pt'; got {meta['font_size']!r}. Ignoring.")
            del meta['font_size']
        # 除去した行数ぶん改行を残し、以降の警告メッセージの行番号がずれないようにする
        return '\n' * m.group(0).count('\n') + text[m.end():], meta
        
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
                result.append(f'#table(\n  columns: {cols},\n  ')
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
                elif lang == 'mermaid':
                    result.append(self._render_mermaid(t.content))
                else:
                    result.append(f"```{lang}\n{t.content}```\n\n")
            elif t.type in ['html_inline', 'html_block']:
                self._warn_html(t)
            elif t.type in ['th_open', 'td_open']:
                result.append('[')
            elif t.type in ['th_close', 'td_close']:
                result.append('], ')
            elif t.type == 'tr_close':
                result.append('\n  ')
            i += 1
        return "".join(result)
        
    def _warn_html(self, t):
        line_no = t.map[0] + 1 if t.map else '?'
        print(f"[Warning] HTML tag detected at {self.current_file}:{line_no} : {t.content.strip()}. HTML is not supported and will be ignored in Typst output.")

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

    def _render_mermaid(self, code):
        """mermaidブロックをmmdc(@mermaid-js/mermaid-cli)でSVG化し、Typstのimage呼び出しに変換する。
        外部APIへの通信は行わず、ローカルのmmdc/Puppeteerで完結させる（仕様書10章）。
        既存のChrome/Edgeが見つかればPUPPETEER_EXECUTABLE_PATHで明示指定し、Puppeteerによる
        ブラウザの自動ダウンロードを回避する。見つからない場合のみ、フルChrome(約428MB)ではなく
        軽量なchrome-headless-shell(約272MB)だけを取得するフォールバックへ切り替える（仕様書11章、#34）。"""
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
            npx = shutil.which("npx")
            if not npx:
                print(f"[Error] 'npx' (Node.js) not found in PATH; required to render a mermaid diagram in {self.current_file}.")
                sys.exit(1)
            mmd_path = os.path.join(cache_dir, f"mermaid_{digest}.mmd")
            with open(mmd_path, "w", encoding="utf-8") as f:
                f.write(code)
            # Typstのraw SVGレンダラーは<foreignObject>内のHTMLを描画できないため、
            # mermaid既定のHTMLラベルを無効化し、通常のSVG<text>要素で出力させる
            mmdc_config_path = os.path.join(cache_dir, "mmdc_config.json")
            if not os.path.exists(mmdc_config_path):
                with open(mmdc_config_path, "w", encoding="utf-8") as f:
                    json.dump({"flowchart": {"htmlLabels": False}, "htmlLabels": False}, f)

            env = os.environ.copy()
            puppeteer_args = []
            browser_path = find_system_browser()
            if browser_path:
                # 本命: 既存ブラウザを再利用し、ダウンロードを完全にゼロにする
                env["PUPPETEER_EXECUTABLE_PATH"] = browser_path
                env["PUPPETEER_SKIP_DOWNLOAD"] = "true"
                print(f"[Info] Reusing system browser for mermaid rendering: {browser_path}")
            else:
                # フォールバック: フルChromeは取得せず、軽量なchrome-headless-shellだけを使う
                env["PUPPETEER_SKIP_CHROME_DOWNLOAD"] = "true"
                puppeteer_config_path = os.path.join(cache_dir, "mmdc_puppeteer_config.json")
                with open(puppeteer_config_path, "w", encoding="utf-8") as f:
                    json.dump({"headless": "shell"}, f)
                puppeteer_args = ["-p", puppeteer_config_path]
                print("[Info] No system browser found; downloading chrome-headless-shell only (not full Chrome).")

            print(f"[Info] Rendering mermaid diagram via mmdc -> {os.path.basename(svg_path)}")
            result = subprocess.run(
                [npx, "-y", "-p", "@mermaid-js/mermaid-cli", "mmdc",
                 "-i", mmd_path, "-o", svg_path, "-b", "transparent",
                 "-c", mmdc_config_path] + puppeteer_args,
                capture_output=True, text=True, env=env)
            # 仕様9章のFail-fast方針: 描画失敗時はテキストへフォールバックせず即エラー
            if result.returncode != 0 or not os.path.exists(svg_path):
                print(f"[Error] mermaid rendering failed for {self.current_file}:\n{result.stderr}")
                sys.exit(1)

        # fit-image() は templates/slide.typ 側で定義されているため、image() の相対パス解決基準は
        # base_dir ではなく templates/ になってしまう。ファイルの置き場所に依存しない
        # ルート絶対パス（--root 起点の "/..." 形式）にして、どこから呼んでも解決できるようにする。
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

    def render_inline(self, tokens):
        res = []
        at_line_start = True
        for t in tokens:
            if t.type == 'text':
                res.append(self.escape_typst(t.content, at_line_start=at_line_start))
            elif t.type == 'strong_open':
                res.append('#strong[')
            elif t.type == 'strong_close':
                res.append(']')
            elif t.type == 'em_open':
                res.append('#emph[')
            elif t.type == 'em_close':
                res.append(']')
            elif t.type == 'code_inline':
                res.append(f'`{t.content}`')
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
            else:
                line_no = t.map[0] + 1 if t.map else '?'
                print(f"[Warning] Unhandled inline token '{t.type}' at {self.current_file}:{line_no}")
            # 改行直後のテキストのみ行頭エスケープの対象にする
            at_line_start = t.type in ['softbreak', 'hardbreak']
        return "".join(res)
        
    def _count_table_cols(self, tokens, start_idx):
        cols = 0
        for i in range(start_idx, len(tokens)):
            if tokens[i].type in ['th_open', 'td_open']:
                cols += 1
            if tokens[i].type == 'tr_close':
                break
        return max(1, cols)

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
            "path": "templates/template.typ"
        },
        "inputs": {
            "dir": "inputs",
            "files": None
        }
    }

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
    return parser.parse_args()

def build():
    tool_dir = os.path.dirname(os.path.abspath(__file__))
    args = parse_args()

    font_dir = ensure_fonts(tool_dir)

    # 汎用ツールとして、呼び出し元プロジェクトが持つ設定ファイルを指定できるようにする。
    # inputs.dir/output.dir などプロジェクト固有の相対パスは、このconfigファイルの
    # 置き場所(project_dir)を基準に解決する。templates/等ツール自身のリソースはtool_dir基準のまま。
    if args.config:
        config_path = os.path.abspath(args.config)
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

    # plugins: Graphviz/PlantUML/Mermaidの有効・無効切り替え（6章、#21）。未指定時は既存動作を
    # 維持する既定値（graphviz/mermaidは常時有効、plantumlは未実装のため既定で無効）。
    plugins_config = config.get("plugins") or {}
    graphviz_enabled = bool(plugins_config.get("graphviz", True))
    mermaid_enabled = bool(plugins_config.get("mermaid", True))
    if plugins_config.get("plantuml", False):
        print("[Warning] plugins.plantuml is enabled, but PlantUML rendering is not implemented yet; ```plantuml fences will be left as plain code.")

    outputs_dir = os.path.normpath(os.path.join(project_dir, config["output"]["dir"]))
    os.makedirs(outputs_dir, exist_ok=True)
    # 【修正】ハードコードをやめ config の inputs.dir を実際に使用する
    inputs_dir = os.path.normpath(os.path.join(project_dir, config.get("inputs", {}).get("dir") or "inputs"))

    work_dir = os.path.join(project_dir, ".context-compositor")
    os.makedirs(work_dir, exist_ok=True)

    # 【修正】8章のセキュリティ要件（ツール本体のディレクトリを--rootにしない）を満たすため、
    # tool_dirは--rootに含めない。テンプレートはtool_dir配下にあり#importでの参照が必要なため、
    # work_dir（project_dir配下、--rootの内側）へコピーしてから、コピーの方を参照する。
    template_abs_path = os.path.join(tool_dir, config["template"]["path"])
    if not os.path.exists(template_abs_path):
        print(f"[Error] Template not found: {template_abs_path}")
        sys.exit(1)
    template_copy_path = os.path.join(work_dir, "_template" + os.path.splitext(template_abs_path)[1])
    shutil.copyfile(template_abs_path, template_copy_path)

    # project_dir・inputs_dir・outputs_dir・work_dirすべてを跨いでtypstから参照できるよう、
    # それら全ての共通の親ディレクトリを --root にする（tool_dirは含めない）
    typst_root = os.path.commonpath([project_dir, inputs_dir, outputs_dir, work_dir])

    doc_config = config.get("document", {})
    # 生成コード(temp_build.typ)の実際の置き場所に依存させないよう、typst_root起点の
    # ルート絶対パスに変換する（.context-compositor/等サブディレクトリに置いても解決できる）。
    template_path = "/" + os.path.relpath(template_copy_path, typst_root).replace(os.sep, '/')
    
    global_landscape = str(doc_config.get('landscape', False)).lower() == 'true'
    global_paper = doc_config.get('paper_size', 'a4')

    # 表紙の扱い: template=テンプレートの表紙のみ / replace=テンプレートの表紙でMarkdown先頭の
    # タイトルスライドを置き換える / markdown=Markdown側のみ / none=表紙なし
    cover_mode = doc_config.get('cover', 'template')
    if isinstance(cover_mode, bool):
        cover_mode = 'template' if cover_mode else 'none'
    cover_mode = str(cover_mode).lower()
    if cover_mode not in ('template', 'replace', 'markdown', 'none'):
        print(f"[Error] Invalid document.cover: {cover_mode!r} (expected template / replace / markdown / none)")
        sys.exit(1)
    # 既定(template)のときは引数を渡さず、cover 引数を持たない既存テンプレートとの互換を保つ
    cover_arg = '' if cover_mode in ('template', 'replace') else '  cover: false,\n'

    # 表紙のページ番号表示。未指定ならテンプレート自身の既定値に任せ、引数自体を渡さない
    cover_page_number = doc_config.get('cover_page_number')
    cover_page_number_arg = (
        f'  cover_page_number: {str(bool(cover_page_number)).lower()},\n'
        if cover_page_number is not None else ''
    )

    date_str = doc_config.get("date", "")
    if date_str == "auto":
        date_str = datetime.now().strftime("%Y-%m-%d")

    safe_title = escape_string_literal(doc_config.get('title', 'Untitled'))
    safe_subtitle = escape_string_literal(doc_config.get('subtitle', ''))
    safe_author = escape_string_literal(doc_config.get('author', ''))
    safe_date = escape_string_literal(date_str)

    typst_code = f"""
#import "{template_path.replace(os.sep, '/')}": conf, fit-image
#show: doc => conf(
  title: "{safe_title}",
  subtitle: "{safe_subtitle}",
  author: "{safe_author}",
  date: "{safe_date}",
  paper_size: "{global_paper}",
  landscape: {str(global_landscape).lower()},
{cover_arg}{cover_page_number_arg}  graphviz: {str(graphviz_enabled).lower()},
  doc,
)

"""

    renderer = TypstRenderer(project_dir, typst_root=typst_root, mermaid_enabled=mermaid_enabled)

    current_landscape = global_landscape
    current_paper = global_paper
    is_first_chapter = True

    for ch in chapters:
        if isinstance(ch, str):
            ch_file = ch
            ch_landscape = global_landscape
            ch_paper = global_paper
            ch_type = "file"
        elif not isinstance(ch, dict):
            print(f"[Error] Invalid chapter entry (must be a string or a mapping): {ch!r}")
            sys.exit(1)
        elif "aggregate" in ch:
            ch_file = ch["aggregate"]
            ch_landscape = str(ch.get("landscape", global_landscape)).lower() == 'true'
            ch_paper = ch.get("paper_size", global_paper)
            ch_type = "aggregate"
        else:
            ch_file = ch.get("file")
            ch_landscape = str(ch.get("landscape", global_landscape)).lower() == 'true'
            ch_paper = ch.get("paper_size", global_paper)
            ch_type = "file"

        if not ch_file:
            print(f"[Error] Invalid chapter entry (no 'file' or 'aggregate' key): {ch!r}")
            sys.exit(1)

        if ch_landscape != current_landscape or ch_paper != current_paper:
            typst_code += f'#set page(paper: "{ch_paper}", flipped: {str(ch_landscape).lower()})\n'
            current_landscape = ch_landscape
            current_paper = ch_paper
            
        if ch_type == "aggregate":
            agg_path = os.path.join(inputs_dir, ch_file)
            typst_code += f'= {renderer.escape_typst(ch.get("title", "Test Cases"))}\n\n'
            
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

        else:
            md_path = os.path.join(inputs_dir, ch_file)
            if os.path.exists(md_path):
                with open(md_path, "r", encoding="utf-8") as f:
                    md_text = f.read()
                chapter_typst = renderer.render(
                    md_text, filepath=md_path,
                    drop_leading_title=is_first_chapter and cover_mode in ('replace', 'none'))
                font_size = renderer.front_matter.get('font_size')
                if font_size:
                    # スコープを#[...]で閉じ、このチャプターだけにフォントサイズ指定を適用する
                    typst_code += f"#[\n#set text(size: {font_size})\n{chapter_typst}\n]\n"
                else:
                    typst_code += chapter_typst
                typst_code += "\n#pagebreak(weak: true)\n"
            else:
                print(f"[Error] Chapter file not found: {md_path}")
                sys.exit(1)

        is_first_chapter = False
            
    if current_landscape != global_landscape or current_paper != global_paper:
         typst_code += f'#set page(paper: "{global_paper}", flipped: {str(global_landscape).lower()})\n'

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

if __name__ == "__main__":
    build()
