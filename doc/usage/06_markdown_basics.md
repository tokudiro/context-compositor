# Markdownファイルの書き方

## 対応する拡張子

`chapters` に列挙するファイルは拡張子で扱いが変わります。

| 拡張子 | 扱い |
| --- | --- |
| `.md` / `.markdown` | Markdownとして変換（このガイドで説明する記法がすべて使える） |
| `.yaml` / `.yml` / `.json` | シンタックスハイライト付きの等幅表示（そのまま） |
| それ以外（`.txt`、コードファイル等） | 素の等幅表示（そのまま。インデント・改行を保持） |

`.md`/`.markdown` 以外はMarkdownとして解釈されないため、YAML内の `-` やコード内の `#` が見出しやリストに化けることはありません。

## front-matter

Markdownファイルの冒頭に `---` で囲んで書きます。

```markdown
---
font_size: 12pt
paper_size: a3
landscape: true
title: "この章だけのタイトル"
---

# 本文
```

| キー | 適用範囲 | 優先順位 |
| --- | --- | --- |
| `font_size` | そのファイル全体 | front-matterのみ |
| `paper_size` / `landscape` | そのファイル全体 | `chapters` の `file:` 指定 ＞ front-matter ＞ `document:` のグローバル設定 |
| `title` | そのファイルのページのヘッダーのみ（文書全体の表紙には影響しない） | front-matter ＞ `document.title`（フォールバック） |
| `subtitle` / `author` / `date` | そのファイルのページのみ（表示するかはテンプレート次第。同梱テンプレートは何も表示しない） | front-matterに無ければ何も表示しない |

`subtitle`/`author`/`date` を実際に画面に表示したい場合は、`template.path: "template_with_chapter_meta"` を使うか、独自テンプレートでそれらを表示する `chapter-meta()` を実装してください（「独自テンプレートを使う」の章）。
