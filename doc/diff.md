# 汎用ツールとの違い

「Markdown → Typst → PDF」という技術スタック自体は、context-compositor独自のものではない。[Quarto](https://quarto.org/docs/output-formats/typst.html)はTypstをバックエンドに選べる汎用出版システムで、v1.9以降はbookプロジェクトで複数の`.qmd`ファイルを1つのPDFへ合成する機能も持つ。[md2pdf](https://github.com/cipherchabon/md2pdf)のような単一ファイル向けの軽量CLIも複数存在する。

したがって、context-compositorの存在意義は「技術的に他にない機能」ではなく、**特定のワークフロー(AIが生成した断片的なテキストを、人間がレビューして安全に本番化する)専用に、運用ルールごとツールへ埋め込んでいること**にある。以下、具体的な違いを挙げる。

## 比較表

| 観点 | 汎用ツール（Quarto等） | context-compositor |
| --- | --- | --- |
| AI生成コードの実行制御 | 特になし。Markdown内のコードは基本そのまま実行系（code cell等）に渡る前提 | `typst-exec`はホワイトリスト方式。`reviewed/`配下のファイルでのみ生Typstコードを許可し、それ以外は即エラー（仕様書7章・8章）。AIが生成した「未レビューの表現力」を本番に混ぜない、という運用ルールをツール自体に埋め込んでいる |
| 意図しないHTML混入の検知 | 通常はそのまま無視してレンダリング | AST解析でHTMLタグを検出したら行番号付き警告（仕様書9章）。AIがMarkdown生成時にたまに混ぜるHTMLタグを「サイレントに握りつぶさない」設計 |
| ファイルアクセスの境界 | プロジェクト全体が信頼された前提 | `--root`をプロジェクトディレクトリに厳密に閉じる。`typst-exec`で`read()`が使われても、意図しないファイルを読めないサンドボックス（仕様書5章・8章） |
| ツールとドキュメントの分離 | プロジェクトディレクトリの中にツールの設定・拡張を書き込む前提が多い | `--config`一つで完全分離。ツール本体を一切変更せず、任意の場所にあるドキュメントをビルドできる（仕様書3章） |
| 再現性への態度 | バージョン固定は利用者側の裁量 | Typst本体・プラグイン・フォントをすべてSHA256/バージョンピン留め（仕様書9章）。「同じ入力なら同じ出力」を強く担保 |
| ファイル分割の単位 | 章・セクション単位の分割が一般的 | 「1ファイル＝1コンテキスト」という粒度。AIとの対話1回分がそのままファイル境界になる設計（仕様書1章） |
| コードベースの規模 | 大規模・汎用（多数の出力形式、拡張機構、実行可能セル等） | `build.py` 1ファイル約700行。全体を読んで理解・改造できる規模に留めている |

## GitHub Actions上でのダウンロード量（弱点の正直な記録）

「軽量」を謳う前提で実測・調査したところ、**Mermaidを使う場合はcontext-compositorの方がQuartoよりダウンロード量が多い**という、意図と逆の結果になった。

| | ダウンロード量 | 内訳 |
| --- | --- | --- |
| Quarto（`ubuntu-latest`、Typstバックエンドでbook合成） | 約140MB | [Quarto CLI tarball](https://github.com/quarto-dev/quarto-cli/releases/) 1本。Pandoc・Deno・[Typstまで同梱済み](https://quarto.org/docs/output-formats/typst.html)で追加ダウンロード不要 |
| context-compositor（Mermaidなし） | 約60.5MB | pip: `typst`(32.6MB) + `markdown-it-py`(0.08MB) + `mdit-py-plugins`(0.05MB) + `PyYAML`(0.73MB) ≈ 33.5MB／Noto Sans JP: ZIP全体27MBをダウンロードし2ファイルだけ使用 |
| context-compositor（Mermaidあり） | **約456MB** | 上記60.5MB + `npx -p @mermaid-js/mermaid-cli mmdc` の実測ダウンロード量 約396MB（mermaid本体83MB、FontAwesome41MB、react-aria系UIライブラリ29MB等、mermaidの依存ツリーが非常に大きい） |
| Marp CLI（`npx @marp-team/marp-cli`） | 約123MB | HTML/CSSをヘッドレスブラウザ（Puppeteer-core）で描画してPDF化する方式。今回の実測ではChromium自体の追加ダウンロードは発生しなかった（後述） |
| Vivliostyle CLI（`npx @vivliostyle/cli`） | 約242MB | Marpと同じくPuppeteer-core方式。CSS組版のフル機能を持つ分、依存ツリーがさらに大きい |

Puppeteerが自前でダウンロードする巨大なChromiumバンドル（[150〜200MB](https://deepwiki.com/mermaid-js/mermaid-cli/4.2-puppeteer-configuration-in-docker)）は、GitHub Actions上のシステムChromeを`PUPPETEER_EXECUTABLE_PATH`で指定することで回避できている（11章）。これはMarp CLI・Vivliostyle CLIも同じPuppeteer-core方式なので、同様にシステムChrome指定で回避可能と考えられる（今回の実測ではブラウザを起動していないため、Chromium自体の追加ダウンロードは発生していない。CI側の設定次第ではここにさらに150〜200MBが乗る）。

それでも、mermaid・Marp・Vivliostyleいずれも「HTML/CSSをブラウザで描画してPDF化する」という共通のアプローチが、JS依存ツリーの重さの根本原因になっている。context-compositorはこの方式そのものを避け、Typstのネイティブなテーブル・グラフ描画（`diagraph`）を使っているため、Mermaidを使わない限りはこの重さと無縁である。Mermaid本体とその周辺ライブラリだけで数百MB規模になる点は見過ごせない弱点であり、「最小限のダウンロード」（2章）という設計原則との間に実際のギャップがある。

Mermaidを使わない用途に限れば、context-compositorはQuartoよりダウンロード量が少ない。この差はNoto SansフォントZIPの無駄（27MBダウンロードして9.2MBしか使わない）を解消すればさらに縮められる（今後の課題）。

実測値は展開後のディスク使用量ベース。実際のネットワーク転送量はgzip圧縮により幾分小さくなる。両ツールとも、GitHub Actionsのキャッシュ機構（`actions/cache`等）を使えば2回目以降の実行コストは大きく下げられる。

## 図表描画（Mermaid / Graphviz / PlantUML）の対応状況

これも実際に調べると、context-compositorの優位性は薄い。

| ツール | Mermaid | Graphviz(dot) | PlantUML |
| --- | --- | --- | --- |
| context-compositor | 実装済み（`mmdc`/npx） | 実装済み（`diagraph`） | 未実装（設計のみ） |
| [Quarto](https://quarto.org/docs/authoring/diagrams.html) | **ネイティブ組み込み**、追加設定不要 | **ネイティブ組み込み**、`{dot}`セルで即使える（[参照](https://medium.com/codex/quarto-1-4-adds-mermaid-and-graphviz-604de76fca21)） | 標準非対応。サードパーティのpandocフィルタか、Java+PlantUML jarの手動セットアップが必要（[参照](https://github.com/orgs/quarto-dev/discussions/6549)） |
| Marp CLI | 組み込みなし。`markdown-it-mermaid`等を自分で`engine.js`に組み込む必要（[参照](https://github.com/orgs/marp-team/discussions/207)） | 組み込みなし（[要望issueあり](https://github.com/orgs/marp-team/discussions/219)、未実装） | 組み込みなし |
| Vivliostyle CLI | 組み込みなし。`rehype-mermaid`等をprocessor置き換え拡張点経由で手動導入（[参照](https://zenn.dev/mura_mi/articles/4f08cc99f19887)） | 情報なし、おそらく同様に手動 | 情報なし、おそらく同様に手動 |

Mermaid・GraphvizはQuartoが最初からネイティブに持っており、context-compositorが独自に実装した`mmdc`連携・`diagraph`連携と機能的にはほぼ同等である。PlantUMLだけはQuartoも標準非対応なので、そこは互角（どちらも今後の課題）。

## 結論

実測・調査を重ねるほど、「ダウンロード量」でも「図表描画機能」でもQuartoに対する明確な優位性は見出せなかった。Mermaid・Graphvizはむしろ Quarto がネイティブに勝っている。

それでも比較表（冒頭）に挙げた項目——`typst-exec`のホワイトリスト、HTMLタグのフェイルファスト、`--root`のサンドボックス化、ツール/ドキュメントの完全分離——は、Quartoを含む汎用ツールが標準では持たない、**AIが生成したテキストを人間がレビューして安全に本番化するための運用ルール**である。これがcontext-compositorの存在意義の核であり、「軽さ」や「機能の独自性」はそもそも副次的な主張に過ぎなかった。今後この路線を続けるなら、強みとして語るべきは一貫してこのガバナンス面であるべきで、「軽量」「独自機能」を売りにするのは実態と合わない。
