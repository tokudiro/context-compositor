# document: 文書全体の設定

| キー | 説明 | 既定値 |
| --- | --- | --- |
| `title` | 文書タイトル。表紙と本文ページのヘッダーに使われる | `"Untitled"` |
| `subtitle` | サブタイトル。表紙のみ | `""` |
| `author` | 著者名。表紙のみ | `""` |
| `date` | 日付。`"auto"` を指定すると実行日（`YYYY-MM-DD`）が自動で入る | `""` |
| `paper_size` | 用紙サイズ（`a4`, `a3`, `presentation-16-9` 等、Typstが認識する値） | `"a4"` |
| `landscape` | 横向きにするか | `false` |
| `cover` | 表紙の扱い（下記） | `"template"` |
| `cover_page_number` | 表紙にページ番号を出すか | テンプレートの既定値 |
| `table_header` | 通常のMarkdownテーブルのヘッダ行スタイル（下記） | 無装飾 |

## table_header: テーブルヘッダのスタイル

通常のMarkdownテーブル（` | a | b | `構文）のヘッダ行に、太字・背景色・文字色を指定できます（`chapters`側で章ごとに上書きも可能。「chapters: 章の並び」の章を参照）。未指定のキーは装飾なし（従来どおり）です。

```yaml
document:
  table_header:
    bold: true            # 既定 false
    background: "#eeeeee" # 既定 none（Typstのrgb()に渡せる形式。#rrggbb等）
    color: "#333333"      # 既定 none
```

なお、aggregate（YAML/JSONテストケース集約）テーブルのヘッダは対象外です（別途固定スタイルが適用されます）。

## cover の4つのモード

Marp形式（先頭に `# タイトル` `## サブタイトル` のスライド）で書かれた原稿と共用する場合に関係します。

- `template`（既定）: テンプレートの表紙だけを出す。Markdown側はそのまま。
- `replace`: テンプレートの表紙を出し、Markdown先頭のタイトルスライド（H1+H2）を取り除く。Marpと共用の原稿で二重表紙を避けたいときに推奨。
- `markdown`: テンプレートの表紙を出さず、Markdown先頭のスライドをそのまま表紙にする。
- `none`: どちらの表紙も出さない。
