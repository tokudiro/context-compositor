# plugins: 図表プラグインの有効・無効

```yaml
plugins:
  graphviz: true               # 既定 true
  mermaid: true                # 既定 true
  mermaid_auto_download: false # 既定 false
  plantuml: true                # 既定 true
  plantuml_auto_download: true  # 既定 true
```

`graphviz`/`mermaid`/`plantuml`を`false`にすると、該当する図表フェンス（`dot`/`graphviz`/`mermaid`/`plantuml`言語のコードブロック）は描画せず、素のコード表示にフォールバックします。`mermaid: true`の場合は`playwright`パッケージが、`plantuml: true`の場合はローカルのJava（11以上）が必要です。

`*_auto_download`は、これらの実行に必要なツール（ブラウザ／Java）がシステムに見つからない場合の振る舞いを別軸で制御します。

| 設定 | trueの時 | falseの時 |
| --- | --- | --- |
| `mermaid_auto_download` | Playwright自身のChromiumをダウンロード（**約700MB**） | エラーで終了（システムのChrome/Edgeを自分でインストールする） |
| `plantuml_auto_download` | Eclipse Temurin JREをダウンロード（約50MB） | エラーで終了（Java 11以上を自分でインストールする） |

既定値が非対称（mermaidはfalse、plantumlはtrue）なのは、ダウンロードされる実体のサイズが一桁違うためです。Mermaidの描画に失敗して`mermaid_auto_download: true`にしたくなった場合は、約700MBのダウンロードが実行されることを理解した上で設定してください（詳細は「図表（Mermaid / Graphviz / PlantUML）」の章、README）。

# inputs: 原稿ファイルの基準ディレクトリ

```yaml
inputs:
  dir: "."
```

`chapters` に列挙するファイル名は、この `dir`（`config.yaml` からの相対パス）を基準に解決されます。
