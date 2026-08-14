# context-compositor: 複数のコンテキストから文書を組み上げるツール 仕様書

## 1. 目的
AIが生成し、人間が加筆・修正するテキストファイルを、1つ1つ独立した「コンテキスト」として扱うツールである。複数のコンテキストを、人間の手作業によるレイアウト調整なしに、1つの人間可読なPDF文書へ決定論的に組み上げる（compose）。これにより「Document as Code」の概念と「AIからのデザイン権限の剥奪」を実証する。

コンテキストとなるテキストファイルはMarkdownに限らない。プレーンテキスト、コードコメント、YAML、JSON、CSVなど、あらゆるテキストファイルが対象になり得る。`chapters`のファイルは拡張子で扱いが分かれる： `.md`/`.markdown`はMarkdownとして変換し（7章）、`.yaml`/`.yml`/`.json`はシンタックスハイライト付きの等幅表示、それ以外（プレーンテキスト・コードファイル等）は素の等幅表示にする。いずれもMarkdown以外の拡張子ではmarkdown-itを一切通さないため、行頭の`#`や`-`等がMarkdown構文として誤解釈されることはない（[#15](https://github.com/tokudiro/context-compositor/issues/15)）。CSVを表として構造化する変換は未実装（[#36](https://github.com/tokudiro/context-compositor/issues/36)）。

もう1つの要件は「書いている場所で、そのままPDFにできること」。ドキュメントの置き場所をツールの都合に合わせさせない。

## 2. 実行環境の要件
実行環境に関する要件は本章に一本化する。他章で個別の依存関係（Typst、Mermaid等）に触れる際も、方針はここを参照する。

* **Python中心・最小限のダウンロード**: コアはPython（`build.py`）のみで完結する。追加が必要なものも、その場でのダウンロードで完結させ、常駐サーバーやコンテナは要求しない。
  * Typstコンパイラ: バイナリを同梱せず、PyPIのホイール経由で取得する（3章）。
  * オプトインの図表プラグイン: Mermaidは`pip install playwright`とシステムにインストール済みのChrome/Edge（新規ダウンロードはしない）、PlantUMLはJREをその場取得する（11章、[#35](https://github.com/tokudiro/context-compositor/issues/35)）。
  * 日本語CJKフォント: リポジトリに同梱せず取得（ダウンロード）する方式とする。Noto Sans JP（Regular/Bold）を初回ビルド時に `tool_dir/.fonts-cache/` へダウンロード・キャッシュし、以降はキャッシュを使う（9章）。
* **外部サーバー・SaaS非依存**: どこかの外部サーバーやSaaSに依存しない。図表描画を含め、外部APIへの通信によるコンテンツ生成は一切行わず、常に完全ローカルで完結させる。これは絶対要件であり、11章のプラグインにも適用される。
* **GitHub Actions上での完結**: 上記2点の帰結として、GitHub Actions（`ubuntu-latest` などのGitHub-hosted runner）上だけで、セルフホストサーバーなしに完結してビルドできる。
* **ローカル環境（Windows/Linux/macOS）**: 同じ理由で、Python（および必要に応じてJRE等の軽量ランタイム）さえ用意すれば、Windows/Linux/macOSいずれでも同一の手順でビルドできる。

## 3. ツールとドキュメントの分離
ツール本体とドキュメントは役割を分離する。原稿は通常、章ごとに分割された複数のテキストファイル（それぞれが1つのコンテキスト。1章）として、ツール外の任意の場所に存在する。原稿をツール側へコピーする運用は行わない。

* **ツール本体（このリポジトリ）**: 変換エンジン（`build.py`）とテンプレート。書き換えずに使えるものだけを置く（フォントは同梱せず取得する方式。2章・9章）。
* **ドキュメント（任意の場所）**: テキストファイル群（現状はMarkdownのみ。1章）、画像、設定ファイル。ツールのディレクトリ構成に従う必要はない。
  * 設定ファイルの推奨名は `context-compositor.config.yaml`。
  * `--config` で明示するか、省略時はカレントディレクトリ（ドキュメント側）直下のこのファイルを自動的に探す。ツール本体のディレクトリ（`tool_dir`）は探索しない。

```text
<ツール本体>                          <ドキュメント（任意の場所・複数可）>
context-compositor/                   my-project/
 ├── build.py                          ├── 01_intro.md
 ├── context-compositor.cmd # PATH に通す ├── 02_features.md
 ├── templates/      # 既定テンプレート  ├── 03_architecture.md          # 複数ファイルを1冊に結合
 └── doc/spec.md                        ├── context-compositor.config.yaml # --config で指定（既定推奨名）
                                         ├── images/
                                         └── manual.pdf                  # 既定の出力先
```

* **Typstコンパイラの入手方法**: バイナリを同梱しない（2章）。PyPIの `typst` パッケージ（[typst-py](https://github.com/messense/typst-py/)、`requirements.txt` で版固定）がOSごとのホイールにコンパイラ本体を含むため、`pip install -r requirements.txt` だけで済む。`build.py` は `typst.compile(input, output=, root=)` というPython APIを直接呼び出すだけで、バイナリの配置やOS判定コードを持たない。

## 4. 使い方（CLI 仕様）
現在実装されているCLIは次の1コマンドのみである。

```bash
python build.py --config <path/to/context-compositor.config.yaml>
```

* **`--config <path>`**: 設定ファイル（yaml/json）へのパス。省略した場合はカレントディレクトリ直下の `context-compositor.config.yaml`/`context-compositor.config.json` を探す（5章）。どちらも指定・発見できなければエラー終了する。
* 上記以外のオプション（出力先の上書き、テンプレート指定、用紙設定、ログレベル等）は存在しない。
* **終了コード**: 成功 `0` / 失敗 `1`。入力欠損・画像欠損・コンパイルエラーは即時失敗する（Fail-fast、10章）。

`context-compositor` コマンド化、複数ファイル/ディレクトリの直接指定、追加オプション等の拡張は構想段階であり、実装するかどうかも含めて未定（[#25](https://github.com/tokudiro/context-compositor/issues/25)）。

## 5. パス解決規則
パスの基準点は次のとおり一意に定める。

| 対象 | 基準ディレクトリ |
| --- | --- |
| `config.yaml` 内のすべての相対パス（`chapters`, `inputs.dir`, `output.*`, `aggregate`） | その `config.yaml` が置かれたディレクトリ（`project_dir`） |
| Markdown 内の画像・リンク先ファイル | その Markdown ファイルのディレクトリ |
| `template.path` | 値が`.typ`で終わらない「名前」（例: `template`, `slide`）はツール同梱`tool_dir/templates/<名前>.typ`基準。`.typ`で終わる「パス」（例: `my_template.typ`, `custom/my_template.typ`）は他の相対パスと同じ`project_dir`基準（プロジェクト独自テンプレート、[#23](https://github.com/tokudiro/context-compositor/issues/23)）。 |

* **ドキュメントルート（`--root`）**: `project_dir`・実際の `inputs_dir`/`outputs_dir`・`work_dir`（`project_dir/.context-compositor`）の共通の親ディレクトリを動的に計算する。`tool_dir`（ツール本体のディレクトリ）は含めない。テンプレートは`tool_dir`配下・`project_dir`配下いずれの場合も、`build.py`がビルドのたびに`work_dir`へコピーしてからそのコピーを参照するため、`--root`を元のテンプレートの置き場所まで広げる必要がない（8章のサンドボックス要件）。この結果、Markdown内の画像等が`project_dir`の外を参照している場合はビルドエラーになる（テンプレート自体はPythonのファイルコピーで読むため、`project_dir`の外に置いても構わない）。
* **設定ファイルの指定**: `--config` で明示するか、省略時はカレントディレクトリ直下の `context-compositor.config.yaml`/`context-compositor.config.json` を探す（`tool_dir` は探索しない）。どちらもなければエラーで終了する。
* **出力先**: `config.yaml` の `output.dir`/`output.filename` に従い `project_dir` 基準で決まる。入力パスからの出力先自動判定やCLIオプションでの上書きは未実装で、構想段階（[#25](https://github.com/tokudiro/context-compositor/issues/25)）。

## 6. 設定ファイル (Configuration as Code)
* `config.yaml` / `config.json` のどちらでも書けるが、内部では単一のスキーマ（正規化された辞書構造やPydantic等）に統合して扱い、パース処理の破綻を防ぐ。パスの基準は5章に従う。
* ファイル順序、ページ設定、出力メタデータ、データ集約ディレクトリ（aggregate）を一元管理する。
  * `plugins:`（Graphviz/PlantUML/Mermaidの有効・無効切り替え）。`graphviz`/`mermaid`/`plantuml`はいずれも既定`true`（未指定時は常時有効）。`false`にすると該当フェンス（```` ```dot ````/```` ```graphviz ````/```` ```mermaid ````/```` ```plantuml ````）は描画せず、未対応言語と同じ素のコード表示にフォールバックする（[#21](https://github.com/tokudiro/context-compositor/issues/21)、[#22](https://github.com/tokudiro/context-compositor/issues/22)）。
  * `plugins.mermaid_auto_download`（既定`false`）/`plugins.plantuml_auto_download`（既定`true`）: 描画に必要なツール（ブラウザ/Java）がシステムに見つからない場合の振る舞いを別軸で制御する。`true`なら自動取得、`false`ならFail-fast。既定値が非対称なのは、Playwright自身のChromium（約700MB）とEclipse Temurin JRE（約49.7MB）でダウンロード量が一桁違うため（11章、#22の設計議論）。
* **設定の優先順位**: `config.yaml` の章別設定 ＞ グローバル設定 ＞ 内蔵デフォルト。CLIオプションによる上書きは、`--config` 以外のオプションが未実装のため現状存在しない（4章）。実装された場合はCLIオプションが最優先になる想定。
* **設定ファイル自体は必須**: `--config`、またはカレントディレクトリからの自動検出（5章）で、いずれかの設定ファイルが必要。中身は最小限でよいが、`chapters` は現状ここで指定する以外の方法がない（入力パスからの自動導出は未実装。[#25](https://github.com/tokudiro/context-compositor/issues/25)）。
* YAML パーサ（PyYAML）が未導入のまま `config.yaml` を無視して既定値でビルドを続行してはならない。サイレントに誤った成果物が出るため即エラーとする。

## 7. Markdown 方言と Marp 互換
本章は、ディレクティブ・front-matter・改ページ規則等の専用の変換規則を持つ唯一のフォーマットであるMarkdownの扱いを規定する（1章）。他フォーマット（YAML/JSON/プレーンテキスト等）は専用の変換規則を持たず、拡張子に応じて等幅表示にフォールバックするのみ（1章、[#15](https://github.com/tokudiro/context-compositor/issues/15)）。フォーマットごとに専用の変換規則を追加していく場合も、本章のMarkdown固有の扱いは維持する設計とする。

**対応するMarkdown記法のスコープ**（[#48](https://github.com/tokudiro/context-compositor/issues/48)）: CommonMark（`markdown-it-py`の`commonmark`プリセット）を土台に、GFM (GitHub Flavored Markdown) の一部とGitHub Wikiの記法を対応範囲とする。**（実装済み）**
* GFM拡張: テーブル・取り消し線（`~~text~~`、`.enable("strikethrough")`）・タスクリスト（`- [ ]`/`- [x]`、`mdit-py-plugins`の`tasklists_plugin`）に対応。山括弧付き自動リンク（`<https://example.com>`）はCommonMark標準機能で、`link_open`/`link_close`という通常のリンクと同じトークンとして出力されるため追加実装なしで動く。山括弧なしの裸URL自動リンク化（GFMの拡張自動リンク）は`linkify-it-py`という追加依存が要るため非対応とする（対応する場合は別途検討）。
* タスクリストのチェックボックスは、`tasklists_plugin`が生HTML（`<input class="task-list-item-checkbox" ...>`）として出力するため、他のHTMLタグと同じ「未対応HTML」警告で消えてしまう問題があった。このパターンだけを`render_inline`内で特別に認識し、Unicodeのチェックボックス記号（☐/☑）に変換する。それ以外のHTMLは従来どおり警告のみ（HTMLは「対応した」のではなく、狭い許可リストへの1パターン追加として扱う方針。[#46](https://github.com/tokudiro/context-compositor/issues/46)で議論・記録）。
* GitHub Wiki拡張: `[[用語]]`によるMarkdown内リンク記法。用語索引機能（[#47](https://github.com/tokudiro/context-compositor/issues/47)、設計確定・未実装）で利用予定。
* このスコープに含まれないもの: Obsidian固有の拡張（コールアウト・埋め込み・`==ハイライト==`等）、Pandoc記法等の第三の由来の記法（文字色指定など。[#46](https://github.com/tokudiro/context-compositor/issues/46)で個別に検討し、例外として扱う）、生HTML全般。

原稿は Marp 形式（`<!-- header: ... -->` ディレクティブ、`---` によるスライド区切り）で書かれている実績があるため、同一の Markdown が Marp でもこのツールでも通ることを要件とする。

**方針の限界（意図的なスコープ）**: 「Marpでも通る」とは、Marp原稿を`chapters`にそのまま流し込んでもビルドが失敗したり不要な警告が出たりしない、という意味に限る。ディレクティブ・front-matterの一部キーの**値を実際に反映する**ことは要件にしていない（[#41](https://github.com/tokudiro/context-compositor/issues/41)）。Marpの`theme:`/`class:`/`backgroundColor:`やカスタムCSS等の見た目に関わる指定も`MARP_ONLY_KEYS`として同様に無視する。

反映機能は`header`/`footer`/`paginate`ディレクティブ（[#16](https://github.com/tokudiro/context-compositor/issues/16)）とfront-matterの`title`/`subtitle`/`author`/`date`（[#38](https://github.com/tokudiro/context-compositor/issues/38)）について一度実装したが、撤回した（[#41](https://github.com/tokudiro/context-compositor/issues/41)）。理由は2つある。1つは、Marpの見た目はCSS前提でありTypstの組版モデルとは根本的に異なるため、変換の労力に対して得られる価値が薄いこと。もう1つ、こちらがより本質的だが、Marpが「1ファイル=1デッキ」を前提に「ディレクティブは以降のページに適用され、次の同種ディレクティブまで持続する」というスコープ規則を持つのに対し、このツールは「複数ファイル=1文書」を核の設計にしており（1章）、**章の並べ替えを安全に行えることが価値の核**である。ディレクティブがチャプター（ファイル）をまたいで持続する実装は、この並べ替えの安全性と正面から衝突する（あるチャプターを並べ替えると、意図しないヘッダーが別のチャプターに混入しうる）。今後Marpの新しい記法への対応や、上記2点を踏まえた別の反映方式を検討する際も、この経緯を踏まえること。

* **ディレクティブコメントの解釈**: `<!-- header: X -->` `<!-- footer: X -->` `<!-- paginate: true -->` は認識するが、値は反映しない（読み捨てる）。認識しているため、他の生のHTMLタグ（`<br>`等）と違って警告は出さない。未知のディレクティブ・その他の生のHTMLタグは、従来どおり行番号付きの警告にとどめ、ビルドは継続する。
* **front-matter**: 冒頭の `---` ブロックは水平線ではなく設定として扱う。認識済みキーは `title`/`subtitle`/`author`/`date`/`paper_size`/`landscape`/`font_size`（Marp固有キーの`marp:`/`theme:`等は無視、それ以外の未知キーは警告）。
  * `paper_size`/`landscape`は、`config.yaml`のチャプター個別設定（10章）より弱い優先順位で適用する。`chapters`の該当エントリに`paper_size`/`landscape`の明示指定が無い場合のみ、front-matterの値を使う（[#17](https://github.com/tokudiro/context-compositor/issues/17)）。
  * `title`/`subtitle`/`author`/`date`は認識するが、値は反映しない（読み捨てる）。文書全体の表紙（`document.title`等、6章）は常に`config.yaml`側のみが正であり、front-matterはここには一切影響しない。
* **`---` はページ区切り**（`#pagebreak()`）として扱う。ただしテンプレート側の「見出し直前で改ページ」と二重に効いて空ページが発生する既知の不具合があるため、連続する改ページは1つに畳み、原則 `#pagebreak(weak: true)` を用いる。
* **表紙の二重化を避ける**: Marp のタイトルスライド（先頭の H1 と直後の H2）とテンプレートの表紙は同じ役割のため、両方出すと 1 枚目が重複する。`document.cover` で扱いを選べる。
  * `template`（既定）: テンプレートの表紙のみを出す。Markdown 側には手を入れない。
  * `replace`: テンプレートの表紙を出し、Markdown 先頭のタイトルスライドを取り除く。Marp と共用の Markdown を書き換えずに重複を解消できる（著者・日付を持つテンプレート表紙を活かす場合の推奨）。
  * `markdown`: テンプレートの表紙を出さず、Markdown 先頭のスライドをそのまま表紙にする。
  * `none`: どちらも出さない。
  * `replace` / `none` で取り除いた見出しは、サイレントな脱落を避けるため必ずログに出力する。テンプレートには `cover` 引数を追加するが、既定値のときは引数自体を渡さず、`cover` を持たない既存テンプレートとの互換を保つ。
* **表紙のページ番号表示**: `document.cover_page_number`（真偽値）で、表紙（1ページ目）にページ番号を出すかどうかを切り替えられる。未指定時はテンプレート自身の既定値に従う（`templates/slide.typ` は表示・`templates/template.typ` は非表示）。本文側のページ番号表示には影響しない。`cover` 引数と同様、未指定時は引数自体を渡さず既存テンプレートとの互換を保つ。
* **ディレクティブ以外の HTML タグ**（`<br>` 等）は行番号付きで警告する（8章のフェイルファスト方針）。ディレクティブ構文に合致するもののみを解釈し、それ以外は無害化しない。

## 8. 人間とAIの協調執筆
本システムは「AIが草案を作り、人間が直接Markdownをレビュー・加筆修正してGitにコミットする」という協調ワークフローを前提とする。人間の介入に伴う例外処理として「Raw Typstパススルー」を許容するが、AIへのデザイン権限剥奪とセキュリティを担保するため、以下のガバナンス設計を設ける。

* **Raw Typstの専用タグとガバナンス**: 人間が高度な数式やTypst固有のレイアウト機能を使いたい場合のみ、Markdown内で ```` ```typst-exec ```` ブロックとして記述することで生のTypstコードとしてPDFに注入する（単なるコード表示用の ```` ```typst ```` とは区別する）。
  * **ホワイトリスト方式のガードレール**: 既定を禁止とし、`reviewed/` 配下に置かれたファイルでのみ許可する。ドラフトから本番への昇格は必ず人間のPR承認を必須とする。
  * **ディレクトリ非依存の運用への対応**: ドキュメントがツール外の任意の場所に置かれるため、`reviewed/` 規約に加えて `config.yaml` での明示的な許可（例 `security.allow_typst_exec: [ "appendix/*.md" ]`）を将来的な代替手段として想定する。許可の意思表示は必ずコミット対象のファイルに残ること（CLI オプション一発で許可できてはならない）を原則とする。
  * **残存リスクの明記**: 「人間がAI出力を無検証でコピペしてcommitする」ケースは、技術的な仕組みだけでは防げない残存リスクであり、チームのレビュー文化に依存することを前提とする。
* **ファイルアクセス制限 (セキュリティ)**: `typst-exec` ブロック経由で意図せぬローカルファイルがPDFに埋め込まれる事故を防ぐため、`typst compile` 実行時は常に `--root` にドキュメントルート（5章）を指定し、アクセス範囲をサンドボックス化する。ツール本体のディレクトリを `--root` にしてはならない。
* **HTMLタグのフェイルファスト**: 無意識に混入したHTMLタグ（`<br>`等）をサイレントに無視すると事故につながるため、AST解析時にHTMLタグを検出した場合は行番号付きの警告（またはエラー）を出す（7章のディレクティブを除く）。

## 9. 変換パイプラインの基本方針
* **Unixフィルタとしての設計は意図的に採用していない**: `build.py`は標準入力/標準出力で連鎖する小さなフィルタ群ではなく、`config.yaml`というマニフェストを読んで複数ファイルをオーケストレーションする単一プロセスである。これは複数コンテキストを1つの文書へ集約するという1章の核である目的そのものが、全入力を同時に見る必要がある（目次・章番号等）ためで、Pandocの複数ファイル結合や`make`と同様、集約系ツールでは一般的な形である。図表レンダリング（Mermaid/Graphviz、11章）やTypstコンパイル自体は専門ツールへの委譲（Playwright経由のCDP直接操作・`diagraph`・`typst`パッケージ）という形でフィルタ的な境界を保っている。
  * かつてMarpディレクティブ（7章、`<!-- header: X -->`等）がチャプター（ファイル）をまたいで持続する機能を実装したことがあったが（[#16](https://github.com/tokudiro/context-compositor/issues/16)）、これは「1つのファイルだけを見て1つのTypst断片を返す」という純粋な変換から外れるだけでなく、このツールの核である**章の並べ替えの安全性**（並べ替えると意図しないヘッダーが混入しうる）とも衝突したため撤回した（[#41](https://github.com/tokudiro/context-compositor/issues/41)）。今後同種の「チャプターをまたいで持続する状態」を持つ機能を検討する際は、この失敗を踏まえること。
* **ASTベースの変換**: Markdownを単なる文字列置換（正規表現等）で処理するとテーブル等で破綻しやすいため、`markdown-it-py` でAST（抽象構文木）を生成し、そこからTypst構文へ決定論的にマッピングする。
* **特殊文字のエスケープ**: AI出力テキスト内のTypstマークアップと衝突する文字（`#`, `$`, `@`, `_`, `*`, `<`, `>`, `[`, `]` 等）は専用のエスケープ処理で必ず無害化する。
  * **行頭ブロック記法のエスケープ**: 行頭の `=` `-` `+` `/` `1.` は Typst の見出し・リスト等として解釈され、地の文が勝手に見出し化して目次にまで混入する。改行直後のテキストは行頭記号をエスケープする（実測で確認済みの実害）。
* **リスト構造の忠実な再現**: markdown-it はタイトなリストの段落トークンに `hidden` を立てる。これを無視すると Typst 側が loose list と解釈し、箇条書きが間延びする。リストの入れ子はスタックの深さに応じたインデントで出力し、階層を保持する。
* **決定論的出力とバージョン固定**: `requirements.txt` のパーサーライブラリに加え、Typstコンパイラ本体および利用する全プラグイン（例: `diagraph:0.3.7`）のバージョンを厳密固定する。Typstコンパイラ自体はPyPIパッケージ（3章）で版固定されているため、同梱バイナリとの食い違いは構造的に起きない。
* **日本語フォントの指定**: OSのデフォルトフォントに依存せず、CJK対応のオープンソースフォントを`font_paths`（Typst Python APIの`typst.compile(..., font_paths=[...])`、CLIの`--font-path`に相当）で明示的に指定する。テンプレート側で`Yu Gothic`等のOSフォントを直接指定してはならない。**（実装済み）** 採用フォントは Noto Sans JP（[SIL Open Font License](https://github.com/notofonts/noto-cjk/blob/main/Sans/OFL.txt)、再配布可）。取得方法は2章、実装は`build.py`の`ensure_fonts()`を参照。`templates/template.typ`・`templates/slide.typ`とも`set text(font: "Noto Sans JP", ...)`のみを指定し、OSフォント名は書かない。Noto Sans JPに無いグリフ（絵文字等）はTypstが自動でシステムフォントにフォールバックする。

## 10. 動的ページレイアウトとデータ駆動型アグリゲーション
* **章ごとのページ設定 (Dynamic Layout)**: ドキュメント全体または特定の章（Markdownファイル単位）に、独立して用紙サイズ（例: A4, A3）と用紙の向き（Landscape/Portrait）を指定できる。設定は `config.yaml` のグローバル設定および章ごとのローカル設定（上書き）として定義する。
  * テンプレートは受け取った `paper_size` / `landscape` を必ず `set page` に反映すること。現状 `templates/slide.typ` は `landscape` を引数に取りながら使っておらず、グローバル指定が無視されている。
* **データ駆動型アグリゲーション (Data-driven Aggregation)**: 「1テストケース＝1ファイル」の原則（Gitでのコンフリクト回避・並行作業の容易化）を守るため、指定ディレクトリ内の大量のYAML/JSONファイルを読み込み、AST変換を経由してTypstのネイティブなテーブル（マトリクス）として出力する。集約ディレクトリのパス基準は5章に従う。
* **テーブルヘッダのスタイル**（[#45](https://github.com/tokudiro/context-compositor/issues/45)）: 通常のMarkdownテーブル（```` | a | b | ````構文）のヘッダ行の太字・背景色・文字色を、`document.table_header`（グローバル）と`chapters[].table_header`（章ごとの上書き。landscape/paper_sizeと同じ優先順位パターン）で指定できる。**（実装済み）** 未指定のキーは装飾なし（後方互換）。front-matterでの上書きは非対応（`_render_markdown_chapter`がfront-matter解決前に`table_header`を確定させる必要があるため）。aggregate（YAML/JSONテストケース集約）テーブルは別コードパスであり対象外（既存の固定スタイルのまま）。実装は`TypstRenderer.table_header_style`（章ごとに`_render_markdown_chapter`が設定）を`render_tokens`の`table_open`/`th_open`/`th_close`が参照し、`#table(..., fill: ...)`と`#strong[]`/`#text(fill: ...)`のTypstコードを生成する。

## 11. プラグイン（図表描画アドイン）の設計方針
2章の実行環境の要件は本章のプラグインにもそのまま適用される。重い依存関係を持つ図表描画ツールは、コアパイプライン（テキスト→PDF化）とは別に「オプトイン形式のプラグイン」として分離する。外部APIへの通信による図表生成を行わない（完全ローカル完結）という2章の絶対要件は、プラグインであっても緩めない。

1. **Graphviz (dot)**: コミュニティ製Wasmプラグイン（`diagraph`）で、追加環境なしにローカル描画する。**（実装済み）** テンプレート側の `show raw.where(lang: "dot"/"graphviz")` が ```` ```dot ```` フェンスを自動的にレンダリングする。
2. **PlantUML**: ローカルJava環境を要求し、純Javaレイアウトエンジン「Smetana」（`-Playout=smetana`）を採用してGraphviz(dot)等の外部バイナリへの依存を避ける。**（実装済み）**
   * **ライセンス**: 本体は`plantuml-mit-*.jar`（MIT）を採用する。`mit-light`版（DITAA等ごく一部を除き機能同等、約7.4MB）も検討したが、jarの中身を比較した結果、差分は`stdlib/`配下のクラウドアイコン素材と絵文字データのみだった。原稿（Markdown、GitHub管理・AI生成）には絵文字が含まれ得るため、フル機能の`mit`版（約17.6MB）を採用する（[#22](https://github.com/tokudiro/context-compositor/issues/22)）。
   * **実行環境の前提**: `find_system_java()`（`build.py`）でシステムのJava（11以上。PlantUML最新版のクラスファイル要件）を検出して再利用する（2章）。GitHub-hosted runner（`ubuntu-latest`）にはJavaが標準搭載されているため、そのまま動く。見つからない場合の挙動は`plugins.plantuml_auto_download`（既定`true`）で制御する。`true`ならEclipse Temurin JRE（Adoptium配布、GPLv2+Classpath Exception。OpenJDK本体と同じライセンス系統）をバージョン・プラットフォーム別にURL・SHA256を固定して自動取得し（9章の決定論的出力）、`false`なら本章3のMermaid/Chrome（[#35](https://github.com/tokudiro/context-compositor/issues/35)）と同じFail-fastになる。既定を自動取得側にしたのは、Chromeと違いJavaは手元環境への標準搭載率が低く、「Java 11以上を入れて」という指示だけでは行き止まりになりやすい（配布元の選択肢が多く迷いやすい）ため、ローカル開発時の利便性を優先する設計判断による。ダウンロードされる実体が約49.7MB（Chromiumの約700MBの1桁下）に収まることも判断材料にした。
   * **実装**: `plantuml.jar`をコンテンツのSHA256込みで`tool_dir/.plantuml-cache/`へ取得・キャッシュし、`java -jar plantuml.jar -tsvg -pipe -Playout=smetana`へ図のソースを標準入力で渡し、標準出力のSVGをそのまま使う。常駐プロセスを持つMermaidのヘッドレスブラウザとは異なり、図ごとにsubprocessを都度起動する（描画コストがMermaidほど大きくないため）。コンテンツのSHA256ハッシュをキー名として`project_dir/.context-compositor/cache/`にSVG結果をキャッシュする点、描画失敗（構文エラー等、終了コード非0）でテキストへフォールバックせず即エラー終了する点はMermaidと同じ方針。`@startuml`/`@enduml`の自動補完は行わない（明示性を優先）。
3. **Mermaid**: ヘッドレスブラウザでの描画を要するため、別途環境構築を伴うオプトイン機能として扱う。**（実装済み）**
   * **実行環境の前提**: `find_system_browser()`（`build.py`）でシステムにインストール済みのChrome/Edgeを検出して再利用する（2章）。GitHub-hosted runner（`ubuntu-latest`）には標準搭載のChromeがあるため、そのまま動く。見つからない場合の挙動は`plugins.mermaid_auto_download`（既定`false`）で制御する。既定ではFail-fastでエラー終了する（[#35](https://github.com/tokudiro/context-compositor/issues/35)。npm/npxに依存しなくなったため、npm経由の代替ダウンロードという選択肢が無い）。`true`にした場合のみ、`playwright install chromium`相当の呼び出しでPlaywright自身のChromium（実測約700MB）を取得し、`connect_over_cdp()`ではなく`chromium.launch()`で起動する。この約700MBはまさに#34/#35で避けた規模であるため既定はfalseのままとし、PlantUML側の`plugins.plantuml_auto_download`（既定`true`、JREは約49.7MB）とは意図的に非対称にしている（#22の設計議論）。
   * **実装**: Mermaid公式配布の単一バンドルJS（`mermaid.min.js`、UMD形式、全図種込み。実測約3.4MB）を`tool_dir/.mermaid-cache/`へバージョン・SHA256を固定してダウンロード・キャッシュし（9章）、Playwright（Python版）の`connect_over_cdp()`でシステムブラウザにCDP接続してブラウザ内で`mermaid.render()`を直接呼び出す（`mermaid-cli`丸ごとの導入は不要、Node.js自体が不要になった）。1回のビルドでヘッドレスブラウザ・ページは1つだけ起動し、複数のMermaid図で使い回す。コンテンツのSHA256ハッシュをキー名として `project_dir/.context-compositor/cache/` にSVG結果をキャッシュする。mermaid既定のHTMLラベル（`<foreignObject>`）はTypstのraw SVGレンダラーが描画できないため、`flowchart.htmlLabels`とトップレベルの`htmlLabels`両方を`false`に指定し通常のSVG `<text>` 要素で出力する（トップレベルのみでは効かないことを実測で確認済み）。
   * **図とテキストのレイアウト**: `::: layout-right ... :::`（テキスト左・mermaid図右の2カラム）、`::: layout-compare ... :::`（2つのmermaid図を左右に並べる）という独自のMarkdown拡張記法を用意した。ASTの通常フローに入る前の生テキスト段階で正規表現により切り出し、個別にTypstの`grid`へ変換している。横長の図をlayout-compareで並べると縮小されすぎて読めなくなることを実測で確認済み。正方形に近い図でのみ使うこと。
   * **画像サイズの自動調整**: `templates/slide.typ` の `fit-image()` が幅・高さそれぞれの縮小率を計算し、小さい方を採用する。高さの上限は固定値`MAX_IMG_HEIGHT`（現在12cm）。Typstの`layout()`が返す`size`は「ページの残りスペース」ではなく「コンテナ全体のサイズ」で、見出しや本文が使った分を考慮できないため、動的計算ではなく安全側の固定値にしている。

## 12. ビルド成果物と一時ファイル
* 中間 Typst ファイルは `project_dir` 直下の `.context-compositor/temp_build.typ` に生成する（Mermaidのキャッシュも同じ `.context-compositor/cache/` 配下）。テンプレートは同じ `.context-compositor/_template.typ` へコピーしてから参照する（5章・8章のサンドボックス要件）。画像はコピーせず、`--root` 起点のルート絶対パス（`/...`）で参照して解決する。
* ビルド成功後、`temp_build.typ` と `_template.typ` は使い捨ての中間ファイルとして削除する。`cache/`（Mermaid等の描画結果）は次回以降のビルドで再利用するため削除しない。ビルド失敗時はデバッグに使えるよう `temp_build.typ` 等を残したまま終了する（[#20](https://github.com/tokudiro/context-compositor/issues/20)）。`.gitignore` への追加を推奨する。
* 出力 PDF が既に開かれている等で書き込めない場合は、部分的な破損ファイルを残さず明確なエラーで終了する。
