# 独自テンプレートを使う

`template.path` に `.typ` で終わるパスを指定すると、自分で書いたTypstテンプレートを使えます（「template: テンプレートの指定」の章）。テンプレートは以下の関数をエクスポートする必要があります。

- `conf(title:, subtitle:, author:, date:, paper_size:, landscape:, cover:, cover_page_number:, graphviz:, doc)`: 文書全体の骨格（表紙・目次・本文ページの設定）。
- `fit-image(path)`: 画像を1枚受け取り、はみ出さないよう自動縮小して配置する。
- `chapter-meta(title:, subtitle:, author:, date:, doc)`: front-matterのtitle/subtitle/author/dateを受け取る（表示するかどうかはテンプレート次第。何もしないなら `doc` をそのまま返せばよい）。
- `cc-marp-header` / `cc-marp-footer` / `cc-marp-paginate`: Marpディレクティブの値を保持する状態変数。ヘッダー/フッターで反応的に読み出す。

同梱の `templates/template.typ`（最も単純な例）と `templates/template_with_chapter_meta.typ`（front-matter・Marpディレクティブを実際に表示する例）をコピーして書き換えるのが早道です。
