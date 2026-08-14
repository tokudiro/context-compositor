# Markdownファイルの書き方

## 対応する拡張子

`chapters` に列挙するファイルは拡張子で扱いが変わります。

| 拡張子 | 扱い |
| --- | --- |
| `.md` / `.markdown` | Markdownとして変換（このガイドで説明する記法がすべて使える） |
| `.yaml` / `.yml` / `.json` | シンタックスハイライト付きの等幅表示（そのまま） |
| それ以外（`.txt`、コードファイル等） | 素の等幅表示（そのまま。インデント・改行を保持） |

`.md`/`.markdown` 以外はMarkdownとして解釈されないため、YAML内の `-` やコード内の `#` が見出しやリストに化けることはありません。

## 対応するMarkdown記法のスコープ

CommonMark準拠に加え、GFM (GitHub Flavored Markdown) の一部とGitHub Wikiの記法を対応範囲としています（#48）。

| 記法 | 対応状況 |
| --- | --- |
| テーブル（` \| a \| b \| `） | 対応 |
| 取り消し線（`~~text~~`） | 対応 |
| タスクリスト（`- [ ]` / `- [x]`） | 対応（☐/☑のUnicode記号で表示。実際に操作できるチェックボックスにはならない） |
| 自動リンク（`<https://example.com>`、山括弧付き） | 対応（CommonMark標準） |
| 裸URLの自動リンク化（`https://example.com`、山括弧なし） | **非対応**。リンクにしたい場合は山括弧で囲むか `[表示テキスト](URL)` を使う |
| 生HTML | 非対応（一部の狭い例外を除く。「Markdownの書き方」以降の各章を参照） |

対応するスコープの詳しい経緯は[doc/spec.md](../spec.md)を参照してください。

## front-matter

Markdownファイルの冒頭に `---` で囲んで書きます。

```markdown
---
font_size: 12pt
paper_size: a3
landscape: true
---

# 本文
```

| キー | 適用範囲 | 優先順位 |
| --- | --- | --- |
| `font_size` | そのファイル全体 | front-matterのみ |
| `paper_size` / `landscape` | そのファイル全体 | `chapters` の `file:` 指定 ＞ front-matter ＞ `document:` のグローバル設定 |
| `header` / `footer` / `paginate` | そのファイル全体（他の章には持続しない） | `chapters` の `file:` 指定 ＞ front-matter ＞ `document:` のグローバル設定（[#42](https://github.com/tokudiro/context-compositor/issues/42)） |
| `title` / `subtitle` / `author` / `date` | 認識はするが反映しない（読み捨てる） | — |

`title`/`subtitle`/`author`/`date`は、Marp原稿との共用時にエラーや警告が出ないよう認識だけしていますが、実際には何も反映されません。文書全体のタイトル等は `document:` の設定（「document: 文書全体の設定」の章）で指定してください。
