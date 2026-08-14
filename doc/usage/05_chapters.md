# chapters: 章の並び

`chapters` はリストで、上から順にPDFへ結合されます。各要素は3つの書き方があります。

## 1. 文字列（Markdownファイルをそのまま追加）

```yaml
chapters:
  - "01_intro.md"
```

## 2. file: （章ごとの用紙設定の上書き）

```yaml
chapters:
  - file: "03_architecture.md"
    paper_size: "a3"
    landscape: true
```

`paper_size`/`landscape` を省略すると、そのMarkdownファイルのfront-matter（次章）の値、それも無ければ `document:` のグローバル設定が使われます。

## 3. aggregate: （YAML/JSONファイル群をテーブルとして集約）

「1テストケース＝1ファイル」のようにディレクトリ内の大量のYAML/JSONファイルを、1枚のテーブルとして出力します。

```yaml
chapters:
  - aggregate: "testcases"       # inputs.dir 基準のディレクトリ名
    title: "テストケース一覧"     # 章の見出し（省略時 "Test Cases"）
    landscape: true
```

対象ディレクトリ配下の `.yaml`/`.yml`/`.json` ファイルをファイル名順に読み込み、各ファイルの `id`/`title`/`priority`/`steps`/`expected` キーをテーブルの列にします。
