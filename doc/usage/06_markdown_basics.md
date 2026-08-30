# Markdownファイルの書き方

## 対応する拡張子

`chapters` に列挙するファイルは拡張子で扱いが変わります。

| 拡張子 | 扱い |
| --- | --- |
| `.md` / `.markdown` | Markdownとして変換（このガイドで説明する記法がすべて使える） |
| `.yaml` / `.yml` / `.json` | シンタックスハイライト付きの等幅表示（そのまま） |
| `.dot` / `.gv` | Graphviz図として1章分描画（`plugins.graphviz`） |
| `.mmd` | Mermaid図として1章分描画（`plugins.mermaid`） |
| `.puml` / `.plantuml` / `.pu` | PlantUML図として1章分描画（`plugins.plantuml`） |
| それ以外（`.txt`、コードファイル等） | 素の等幅表示（そのまま。インデント・改行を保持） |

`.md`/`.markdown` 以外はMarkdownとして解釈されないため、YAML内の `-` やコード内の `#` が見出しやリストに化けることはありません。

図表ソースファイル（`.dot`/`.mmd`/`.puml`等）は、Markdown内の```` ```mermaid ````等のフェンスコードブロックと全く同じ描画機構を使います。1ファイル＝1章（見出しなし、図だけのページ）として扱われ、該当する`plugins.*`が無効な場合は素のコード表示にフォールバックします（[#53](https://github.com/tokudiro/context-compositor/issues/53)）。「図表（Mermaid / Graphviz / PlantUML）」の章も参照してください。

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
| alert（`> [!NOTE]`等） | 対応（下記） |
| 文字色指定 | 対応（GFM/GitHub Wikiのどちらにも属さない例外。下記） |
| 生HTML | 非対応（`<span style="color:...">`を除く狭い例外のみ。「Markdownの書き方」以降の各章を参照） |

対応するスコープの詳しい経緯は[doc/spec.md](../spec.md)を参照してください。

## 文字色指定

2つの記法をどちらも常にサポートしています。設定での切り替えはありません（同じ原稿がconfig次第で意味が変わることを避けるため）。

```markdown
[赤い文字]{color=red} や [青い文字]{color="#0000ff"} のように書けます。

<span style="color:green">緑の文字</span> とも書けます。
```

- `[text]{color=...}`はPandoc由来のブラケット+属性記法です。GitHubの生表示では特別扱いされず、`{color=red}`がそのまま文字として見えます。
- `<span style="color:...">`はGitHub上でもそのまま正しく色付き表示されます。ただし対応するのはこの1パターンのみで、他のHTMLタグ・他のCSSプロパティは今までどおり非対応（警告）です。
- 色の指定は、Typstが認識する色名（`red`、`blue`等の英単語）か `"#rrggbb"` 形式のいずれかです。
- `color`以外の属性（`[text]{class=foo}`等）は無視され、見た目には反映されません。
- `<span>`を閉じ忘れた場合はビルドを止めず、自動的に閉じたうえで警告を出します。

## alert: 注意書きの囲み

GitHub形式のalert記法（`> [!NOTE]`等）で、本文と区別した囲み枠（callout）を出せます。

```markdown
> [!NOTE]
> これは補足情報です。
> 複数行にもなります。

> [!TIP]
> これはヒントです。
```

- 対応する種別は`NOTE`/`TIP`/`IMPORTANT`/`WARNING`/`CAUTION`の5つです（大文字のみ）。
- マーカー（`[!NOTE]`等）は、引用ブロックの最初の行に単独で書く必要があります。それ以外の内容と同じ行に書いても認識されません。
- 実体は[note-me](https://github.com/FlandiaYingman/note-me)（MITライセンス、`@preview/note-me:0.6.0`）というTypst Universeのパッケージにそのまま委譲しています。色・アイコンはこのパッケージの既定のままです。
- マーカーに一致しない通常の引用（`>`）は、従来どおり装飾なしの引用として表示されます。

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

## 画像: サイズ・配置指定

`![alt](path)`のalt部分に`|`区切りで独自属性を書くと、サイズや配置を指定できます。

```markdown
![説明|width=50%](image.png)
![説明|width=50%|height=30%](image.png)
![説明|align=center](image.png)
![説明|align=center|height=30%](image.png)
```

| 属性 | 内容 |
| --- | --- |
| `width=...` | 画像の幅（TypstのサイズまたはCJK単位でも可、例: `50%`、`8cm`） |
| `height=...` | 画像の高さ（同上） |
| `align=left` / `align=center` / `align=right` | 画像の左寄せ・中央寄せ・右寄せ（[#75](https://github.com/tokudiro/context-compositor/issues/75)） |

- `align`を指定しない場合の見た目は変わらず、これまでどおり左寄せです。
- `width`/`height`と`align`は組み合わせて指定できます（順不同）。
- Mermaid/PlantUML/Graphvizのフェンス（「図表（Mermaid / Graphviz / PlantUML）」の章）には`align`は無く、常に中央寄せです。

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
