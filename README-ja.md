# context-compositor

*[English version (英語版)](README.md)*

AIが生成し、人間が加筆・修正する複数のテキストファイルを、それぞれ独立した「コンテキスト」として扱い、1つの人間可読なPDF文書へ決定論的に組み上げる（compose）ツールです。

このREADMEは最短で使い始めるための要点のみを記載します。`config.yaml`や原稿の書き方を一通り知りたい場合は[使い方ガイド](doc/usage/)（`cd doc/usage && python ../../build.py` でPDF化もできます）を、詳細な設計方針・実装状況は [doc/spec.md](doc/spec.md) を参照してください。Quarto等の汎用ツールとの違いは [doc/diff.md](doc/diff.md) にまとめています。

## 特徴

- 複数のテキストファイル（コンテキスト）を1冊のPDFに結合
- Markdown → [markdown-it-py](https://github.com/executablebooks/markdown-it-py) でAST化 → [Typst](https://typst.app/) 構文へ決定論的に変換 → PDF出力
- その他のテキストファイル → そのままPDF出力
- ツール本体とドキュメント（原稿）を分離し、原稿はリポジトリ外の任意の場所に置ける
- Python中心・最小限のダウンロードで完結し、外部サーバーやSaaSに依存しない（GitHub Actions上でも、Windows/Linux/macOSのローカルでも同じ手順で動く）

`chapters`に列挙するファイルは拡張子で扱いが分かれます。`.md`/`.markdown`はMarkdownとして変換し、`.yaml`/`.yml`/`.json`はシンタックスハイライト付きの等幅表示、`.dot`/`.gv`・`.mmd`・`.puml`/`.plantuml`/`.pu`はそれぞれGraphviz/Mermaid/PlantUMLの図として1章分描画し、それ以外（プレーンテキスト・コードファイル等）は素の等幅表示にします（CSVを表として構造化する変換は未実装）。詳細は[使い方ガイド](doc/usage/)を参照してください。

## 必要なもの

- Python 3
- 依存ライブラリ（[requirements.txt](requirements.txt)）

```bash
pip install -r requirements.txt
```

Typstコンパイラ本体はバイナリを同梱せず、上記の `pip install` で入る `typst` パッケージ（PyPIのホイール）から取得します。追加のダウンロードやインストールは不要です。

### Mermaid図を使う場合（任意）

原稿の中で ` ```mermaid ` フェンスを使う場合（または`.mmd`ファイルを`chapters`に直接指定する場合）のみ、追加で以下が必要です。

```bash
pip install playwright==1.62.0
```

- **システムにインストール済みのGoogle ChromeまたはMicrosoft Edge**（既定では新規ダウンロードしない。ビルド時に自動検出して再利用する）
- 上記の `playwright` パッケージ（既存ブラウザへCDP接続するために使うだけで、既定ではPlaywright自身のブラウザダウンロード機能は使わない）

Node.js/npmは不要です。ビルド時にMermaid公式配布の単一バンドルJS（`mermaid.min.js`、約3.4MB）を取得してヘッドレスブラウザに読み込ませ、SVGに変換します（バンドルJS自体は `tool_dir/.mermaid-cache/` に、変換結果は `.context-compositor/cache/` にキャッシュされ、次回以降は再取得しません）。Mermaidを使わない原稿ではこれらは一切不要です。

システムにChrome/Edgeが無い場合は既定でエラー終了します。`plugins: { mermaid_auto_download: true }` にすると代わりにPlaywright自身のChromiumを自動取得しますが、**このダウンロードは約700MBあります**（プレインストールされたブラウザを使わない場合の最後の手段として用意した設定で、既定でこの量をダウンロードしてしまうことは意図的に避けています）。

### PlantUML図を使う場合（任意）

原稿の中で ` ```plantuml ` フェンスを使う場合（または`.puml`ファイルを`chapters`に直接指定する場合）、`config.yaml`側の追加設定は不要です（`plugins.plantuml`は既定`true`。追加の`pip install`も不要）。

- ローカルにJava（11以上）があればそのまま再利用します
- 無ければ既定でEclipse Temurin JRE（Adoptium配布、約49.7MB）を自動取得・キャッシュします（`tool_dir/.jre-cache/`）。`plugins: { plantuml_auto_download: false }` にすると、自動取得せずエラー終了に変えられます
- GitHub Actionsの`ubuntu-latest`にはJavaが標準搭載されているため、CI上では追加ダウンロードは発生しません

レイアウトエンジンには純Java実装の Smetana を使うため、Graphviz（`dot`）等の外部バイナリは不要です。PlantUML本体（MIT版、約17.6MB）は `tool_dir/.plantuml-cache/` に、変換結果はMermaidと同じく `.context-compositor/cache/` にキャッシュされます。

## 使い方

```bash
python build.py --config <path/to/context-compositor.config.yaml>
```

`--config` を省略した場合は、カレントディレクトリ直下の `context-compositor.config.yaml`（または `.json`）を自動的に探します。

```bash
cd my-project/
python /path/to/context-compositor/build.py
```

設定ファイルの書き方は [sample/context-compositor.config.yaml](sample/context-compositor.config.yaml) を、`document:`/`plugins:`/front-matter/Marpディレクティブ等の詳しい説明は[使い方ガイド](doc/usage/)を参照してください。`chapters` に列挙したMarkdownファイルを順に結合してPDFを生成します。

## サンプルを試す

```bash
cd sample/
python ../build.py
```

`sample/System_Specification.pdf` が生成されます。

## 実装状況

現在実装されているのは「`--config` で指定した（または自動検出した）設定ファイルに従い、複数のファイルを1つのPDFへ結合する」というコア機能です。CLIオプションの拡張（出力先の上書きなど）は構想段階です。既知の課題・今後の予定は [GitHub Issues](https://github.com/tokudiro/context-compositor/issues) を参照してください。

## ライセンス

[MIT License](LICENSE)
