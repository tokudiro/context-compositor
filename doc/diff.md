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

「軽量」を謳う前提で実測・調査したところ、**Mermaidを使う場合はcontext-compositorの方がQuartoより大幅にダウンロード量が多い**という、意図と逆の結果になった（後述のとおり、当初の想定よりもさらに悪い実態が判明した）。

| | ダウンロード量 | 内訳 |
| --- | --- | --- |
| Quarto（Mermaidなし、Typstバックエンドでbook合成） | 約140MB | [Quarto CLI tarball](https://github.com/quarto-dev/quarto-cli/releases/) 1本。Pandoc・Deno・[Typstまで同梱済み](https://quarto.org/docs/output-formats/typst.html)で追加ダウンロード不要 |
| Quarto（Mermaidあり） | **約254MB** | 上記140MB + Mermaid図をPDF化するために必要な[Chrome Headless Shell](https://quarto.org/docs/blog/posts/2026-04-14-chrome-headless-shell.html) linux64版。[Google公式配布元](https://storage.googleapis.com/chrome-for-testing-public/152.0.7977.42/linux64/chrome-headless-shell-linux64.zip)で実測 **119,483,791バイト（約114MB、圧縮zip）** |
| context-compositor（Mermaidなし） | 約60.5MB | pip: `typst`(32.6MB) + `markdown-it-py`(0.08MB) + `mdit-py-plugins`(0.05MB) + `PyYAML`(0.73MB) ≈ 33.5MB／Noto Sans JP: ZIP全体27MBをダウンロードし2ファイルだけ使用 |
| context-compositor（Mermaidあり） | **約1,155MB（約1.1GB）** | 上記60.5MB + `npx -p @mermaid-js/mermaid-cli mmdc` の依存ツリー約396MB + ブラウザ自動ダウンロード約699MB（詳細は次項） |
| Marp CLI（`npx @marp-team/marp-cli`） | 約123MB＋ブラウザ | HTML/CSSをヘッドレスブラウザ（Puppeteer-core）で描画してPDF化する方式。パッケージ自体は約123MBだが、Chromiumが別途必要 |
| Vivliostyle CLI（`npx @vivliostyle/cli`） | 約242MB＋ブラウザ | Marpと同じくPuppeteer-core方式。CSS組版のフル機能を持つ分、依存ツリーがさらに大きい |

### ブラウザの扱い（重要な訂正）

当初「`build.py`はシステムChromeを再利用する設計（11章）なのでブラウザ分のダウンロードはゼロ」と記載していたが、**これは誤りだった**。`build.py`は実際には`PUPPETEER_EXECUTABLE_PATH`を一度も設定しておらず、11章の記述は設計意図に留まり実装されていない。実際に`npx -p @mermaid-js/mermaid-cli mmdc`を実行したところ、`puppeteer-core`が自前でブラウザを探しに行き、見つからなかったため`~/.cache/puppeteer/`配下に次の2つを自動ダウンロードしていたことを確認した。

- フルChrome: 約428MB
- Chrome Headless Shell: 約272MB
- 合計: **約699MB**

npm依存ツリー（約396MB）とは完全に別枠で発生しており、当初の「約456MB」という数字は実態を大きく下回っていた。仕様と実装の乖離として[#34](https://github.com/tokudiro/context-compositor/issues/34)に記録した。

一方Quartoは、自前で管理するChrome Headless Shellを明示的に取得する方式で、実測114MBのみ（フルChromeは取得しない）。**同じ「ブラウザを自前で持つ」場合の比較でも、Quarto（114MB）はcontext-compositor（699MB、しかも不要なフルChromeまで含む）よりはるかに軽い**。

### 現実的な改善余地

- [#34](https://github.com/tokudiro/context-compositor/issues/34): `PUPPETEER_EXECUTABLE_PATH`をシステムChromeへ明示的に設定すれば、ブラウザの追加ダウンロードをゼロ、または少なくとも軽量な Chrome Headless Shell 一本（272MB）に抑えられる
- [#35](https://github.com/tokudiro/context-compositor/issues/35): `mermaid-cli`丸ごとではなく、Mermaid公式が配布する単一バンドルJSファイル（`mermaid.min.js`、**実測3.4MB**）を直接取得し、CDP（Chrome DevTools Protocol）を自前で叩く最小限スクリプトに置き換える案。実現すればnpm依存ツリー396MBの大部分（使っていないUML図・ELKレイアウト機能等）を削減できる

Mermaidを使わない用途に限れば、context-compositorはQuartoよりダウンロード量が少ない（60.5MB対140MB）。この差はNoto SansフォントZIPの無駄（27MBダウンロードして9.2MBしか使わない）を解消すればさらに縮められる（今後の課題）。

実測値は展開後のディスク使用量、またはHTTPヘッダーから直接取得した圧縮ファイルサイズのいずれか（各行に記載の取得方法を参照）。両ツールとも、GitHub Actionsのキャッシュ機構（`actions/cache`等）を使えば2回目以降の実行コストは大きく下げられる。

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
