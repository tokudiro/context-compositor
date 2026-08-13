# context-compositor

AIが生成し、人間が加筆・修正する複数のテキストファイルを、それぞれ独立した「コンテキスト」として扱い、1つの人間可読なPDF文書へ決定論的に組み上げる（compose）ツールです。

詳細な設計方針・実装状況は [doc/specification.md](doc/specification.md) を参照してください。このREADMEは最短で使い始めるための要点のみを記載します。Quarto等の汎用ツールとの違いは [doc/diff.md](doc/diff.md) にまとめています。

## 特徴

- 複数のMarkdownファイル（コンテキスト）を1冊のPDFに結合
- Markdown → [markdown-it-py](https://github.com/executablebooks/markdown-it-py) でAST化 → [Typst](https://typst.app/) 構文へ決定論的に変換 → PDF出力
- ツール本体とドキュメント（原稿）を分離し、原稿はリポジトリ外の任意の場所に置ける
- Python中心・最小限のダウンロードで完結し、外部サーバーやSaaSに依存しない（GitHub Actions上でも、Windows/Linux/macOSのローカルでも同じ手順で動く）

現時点での対応フォーマットはMarkdownのみですが、将来的にプレーンテキストやYAML/JSON/CSV等のテキストファイル全般への対応を想定しています。

## 必要なもの

- Python 3
- 依存ライブラリ（[requirements.txt](requirements.txt)）

```bash
pip install -r requirements.txt
```

Typstコンパイラ本体はバイナリを同梱せず、上記の `pip install` で入る `typst` パッケージ（PyPIのホイール）から取得します。追加のダウンロードやインストールは不要です。

### Mermaid図を使う場合（任意）

原稿の中で ` ```mermaid ` フェンスを使う場合のみ、追加で **Node.js**（`npx` コマンド）が必要です。あらかじめのインストール作業は不要で、ビルド時に `npx -y -p @mermaid-js/mermaid-cli mmdc` が自動的に [@mermaid-js/mermaid-cli](https://www.npmjs.com/package/@mermaid-js/mermaid-cli) を取得してSVGに変換します（結果は `.context-compositor/cache/` にキャッシュされ、次回以降は再取得しません）。Mermaidを使わない原稿ではNode.jsは不要です。

## 使い方

```bash
python build.py --config <path/to/context-compositor.config.yaml>
```

`--config` を省略した場合は、カレントディレクトリ直下の `context-compositor.config.yaml`（または `.json`）を自動的に探します。

```bash
cd my-project/
python /path/to/context-compositor/build.py
```

設定ファイルの書き方は [sample/context-compositor.config.yaml](sample/context-compositor.config.yaml) を参照してください。`chapters` に列挙したMarkdownファイルを順に結合してPDFを生成します。

## サンプルを試す

```bash
cd sample/
python ../build.py
```

`sample/System_Specification.pdf` が生成されます。

## 実装状況

現在実装されているのは「`--config` で指定した（または自動検出した）設定ファイルに従い、複数のMarkdownファイルを1つのPDFへ結合する」というコア機能のみです。CLIオプションの拡張（出力先の上書き、テンプレート指定など）や、Markdown以外のフォーマット対応は構想段階です。既知の課題・今後の予定は [GitHub Issues](https://github.com/tokudiro/context-compositor/issues) を参照してください。

## ライセンス

[MIT License](LICENSE)
