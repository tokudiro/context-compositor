# plugins: 図表プラグインの有効・無効

```yaml
plugins:
  graphviz: true    # 既定 true
  mermaid: false    # 既定 true
  plantuml: false   # 未実装（trueにしても警告のみ）
```

`false` にすると、該当する図表フェンス（`dot`/`graphviz`/`mermaid`言語のコードブロック）は描画せず、素のコード表示にフォールバックします。`mermaid: true` の場合のみ、ビルド時にNode.js（`npx`）が必要になります（詳細はREADME）。

# inputs: 原稿ファイルの基準ディレクトリ

```yaml
inputs:
  dir: "."
```

`chapters` に列挙するファイル名は、この `dir`（`config.yaml` からの相対パス）を基準に解決されます。
