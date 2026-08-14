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
| GitHub Wikiの用語索引記法（`[[用語]]`） | 対応（`document.glossary: true`のときのみ。下記） |
| 生HTML | 非対応（一部の狭い例外を除く。「Markdownの書き方」以降の各章を参照） |

対応するスコープの詳しい経緯は[doc/spec.md](../spec.md)を参照してください。

## [[用語]]: 巻末用語索引

`document.glossary: true` を設定すると、本文中の `[[用語]]` を検出し、巻末に索引ページ（用語と出現ページ番号の一覧）を自動生成します。

```markdown
本システムは [[認証機能]] と [[Markdown変換]] を中核に持つ。
```

- 表示は`[[`/`]]`を取り除いた素のテキストのみです。説明文（定義）は付きません（本の巻末索引と同じ、用語と参照ページの一覧のみ）。
- 同じ用語が複数ページに出現した場合、全ページ番号をカンマ区切りで列挙します（重複ページはまとめます）。
- 索引の並び順は文字コード順（Pythonの`sorted()`）です。厳密な五十音順ではありません。
- `document.glossary`が既定（`false`）のままの場合、`[[用語]]`は何の効果も持たず、ブラケット付きの素のテキストとしてそのまま表示されます。
- コードスパン（`` `[[example]]` ``）やコードブロック内の`[[example]]`は対象外です（検出されません）。
- `[[表示テキスト|用語]]`のような区切り記法（表示と索引登録名を分ける）は、使い方が分かりにくいため非対応です。表示テキストと索引登録名は常に同一です。

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
