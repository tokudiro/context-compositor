# 独自テンプレートを使う

`template.path` に `.typ` で終わるパスを指定すると、自分で書いたTypstテンプレートを使えます（「template: テンプレートの指定」の章）。テンプレートは以下の関数をエクスポートする必要があります。

- `conf(title:, subtitle:, author:, date:, paper_size:, landscape:, cover:, cover_page_number:, graphviz:, doc)`: 文書全体の骨格（表紙・目次・本文ページの設定）。
- `fit-image(path)`: 画像を1枚受け取り、はみ出さないよう自動縮小して配置する。

同梱の `templates/template.typ` をコピーして書き換えるのが早道です。
