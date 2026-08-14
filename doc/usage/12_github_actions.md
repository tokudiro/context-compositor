# GitHub Actionsでの利用

GitHub-hosted runner（`ubuntu-latest`等）には標準でGoogle Chromeが導入されている。`plugins.mermaid: true`を使うプロジェクトでも、ビルド時に既存のChromeを自動検出して再利用するため、追加のブラウザダウンロード（設定を誤ると発生しうる約699MB）は発生しない。

## 最小構成のワークフロー例

```yaml
name: Build Docs

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Build PDF
        run: python build.py --config path/to/context-compositor.config.yaml

      - uses: actions/upload-artifact@v4
        with:
          name: pdf
          path: path/to/output.pdf
```

`plugins.graphviz`のみを使うプロジェクトは、これだけで完結する（Node.js/JRE等の追加インストール不要）。

## Mermaidを使う場合の注意

`plugins.mermaid: true`のプロジェクトでは、`pip install playwright==1.62.0`を追加で実行する（`requirements.txt`には含まれない。任意依存のため）。ブラウザは前述のとおりランナー標準搭載のChromeを再利用するため、Node.jsのインストールは不要。

```yaml
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install playwright==1.62.0
```

Mermaid公式配布の単一バンドルJS（`mermaid.min.js`、約3.4MB）は初回ビルド時に`tool_dir/.mermaid-cache/`へダウンロードされる。`actions/checkout`は毎回新規チェックアウトのためこのキャッシュは引き継がれないが、サイズが小さいため実用上は都度取得でも問題にならない。

## リリース時にPDFをアセットとして添付する

このツール自身の使い方ガイド（本書）は、`v*`タグのpushをトリガーにビルドし、GitHub Releaseへアセットとして添付している。設定例は `.github/workflows/release.yml` を参照。
