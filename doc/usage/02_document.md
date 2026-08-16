# document: 文書全体の設定

| キー | 説明 | 既定値 |
| --- | --- | --- |
| `title` | 文書タイトル。表紙と本文ページのヘッダーに使われる | `"Untitled"` |
| `subtitle` | サブタイトル。表紙のみ | `""` |
| `author` | 著者名。表紙のみ | `""` |
| `date` | 日付。`"auto"` を指定すると実行日（`YYYY-MM-DD`）が自動で入る | `""` |
| `paper_size` | 用紙サイズ（`a4`, `a3`, `presentation-16-9` 等、Typstが認識する値） | `"a4"` |
| `landscape` | 横向きにするか | `false` |
| `cover` | 表紙の扱い（下記） | `"none"` |
| `cover_page_number` | 表紙にページ番号を出すか | `false` |
| `toc` | 目次を出すか | `false` |
| `header` | 本文ページのヘッダーに表示する文字列（下記） | `title`と同じ |
| `footer` | 本文ページのフッターに表示する文字列（下記） | なし（ページ番号のみ） |
| `paginate` | 本文ページにページ番号を表示するか（下記） | `true` |
| `background` | 本文ページの背景画像（下記） | なし |
| `table_header` | 通常のMarkdownテーブルのヘッダ行スタイル（下記） | 無装飾 |
| `glossary` | `[[用語]]`による巻末用語索引を生成するか（「Markdownファイルの書き方」の章を参照） | `false` |

## 用途別の設定早見表

`templates/template.typ`は、ほぼ万能テンプレートです（[独自テンプレートを使う](10_custom_template.md)「いつ新しいテンプレートが要るか」を参照）。文書の種類ごとに、`document:`側の設定だけで大抵まかなえます。

| 用途 | 設定 |
| --- | --- |
| 仕様書（表紙・目次あり） | `cover: template` / `toc: true` |
| 軽量メモ（表紙・目次なし、要点だけ） | 何も指定しない（既定のまま） |
| テストケースの集約表 | `chapters`に`aggregate:`を指定（「chapters: 章の並び」の章を参照） |
| マニュアル（注意書きを目立たせたい） | 本文中で`> [!NOTE]`等のalert記法を使う（「Markdownファイルの書き方」の章を参照）。`document:`側の追加設定は不要 |

### 軽量メモの例

`cover`/`toc`とも既定が「出さない」なので、何も指定しなければ表紙・目次なしの軽量メモになります。

```yaml
document:
  title: "週次ミーティングメモ"
  date: "auto"
```

```yaml
chapters:
  - "memo.md"
```

これだけで、1ページ目から本文がそのまま始まる短い文書が生成されます。表紙・目次が要らない用途（メモ・議事録・簡単な報告書等）に向いています。

## header / footer / paginate: 本文ページのヘッダー・フッター

```yaml
document:
  header: "システム仕様書"   # 省略時はdocument.titleが使われる
  footer: "社外秘"           # 省略時はページ番号のみ
  paginate: true             # falseにするとページ番号を出さない
```

`chapters`側で章ごとに上書きできます（`landscape`/`paper_size`と同じ優先順位パターン。「chapters: 章の並び」の章を参照）。フッターにカスタム文字列とページ番号を両方指定した場合は、左にフッター文字列・右にページ番号が並びます。この設定はMarpの`header`/`footer`/`paginate`ディレクティブとは無関係です（[#42](https://github.com/tokudiro/context-compositor/issues/42)。ディレクティブは「Markdownの書き方」の章を参照）。

## background: 背景画像

本文ページ全体に、透かしや地紋のような背景画像を敷けます。

```yaml
document:
  background: "watermark.png"   # config.yamlからの相対パス
```

`chapters`側で章ごとに上書きできます（`header`/`footer`/`paginate`と同じ優先順位パターン。`background: null`を指定すると、その章だけ背景を外せます）。front-matter経由での上書きは非対応です（パス値のため、`table_header`と同じ理由）。

画像はページ全面に敷かれ、本文はその上に通常どおりレイアウトされます。透明度の自動調整は行わないため、本文が読みにくくならないよう、あらかじめ薄い・低コントラストな画像を用意してください。ファイルサイズが大きいとPDFの出力サイズにも影響します。

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

## toc: 目次の表示/非表示

既定では目次を出しません。出したい場合は明示的に指定します。

```yaml
document:
  toc: true   # 目次を出す
```

指定すると目次のページ（見出し・ローマ数字のページ番号）が追加されます。本文のページ番号は目次の有無に関わらず1から始まります。

## cover の4つのモード

Marp形式（先頭に `# タイトル` `## サブタイトル` のスライド）で書かれた原稿と共用する場合に関係します。既定では表紙を出しません。

- `template`: テンプレートの表紙だけを出す。Markdown側はそのまま。
- `replace`: テンプレートの表紙を出し、Markdown先頭のタイトルスライド（H1+H2）を取り除く。Marpと共用の原稿で二重表紙を避けたいときに推奨。
- `markdown`: テンプレートの表紙を出さず、Markdown先頭のスライドをそのまま表紙にする。
- `none`（既定）: どちらの表紙も出さない。
