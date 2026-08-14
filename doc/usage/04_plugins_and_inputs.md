# plugins: 図表プラグインの有効・無効

```yaml
plugins:
  graphviz: true    # 既定 true
  mermaid: false    # 既定 true
  plantuml: true    # 既定 false
```

`false` にすると、該当する図表フェンス（`dot`/`graphviz`/`mermaid`/`plantuml`言語のコードブロック）は描画せず、素のコード表示にフォールバックします。`mermaid: true` の場合は `playwright`パッケージとシステムのChrome/Edgeが必要です。`plantuml: true` の場合はローカルのJava（11以上）が必要ですが、見つからなければEclipse Temurin JREを自動取得するため追加のインストール作業は不要です（詳細は「図表（Mermaid / Graphviz / PlantUML）」の章、README）。

# inputs: 原稿ファイルの基準ディレクトリ

```yaml
inputs:
  dir: "."
```

`chapters` に列挙するファイル名は、この `dir`（`config.yaml` からの相対パス）を基準に解決されます。
