# よくあるエラー

| メッセージ | 原因と対処 |
| --- | --- |
| `Config file not found` | `--config` のパスが誤っているか、カレントディレクトリに `context-compositor.config.yaml`/`.json` が無い |
| `Template not found` | `template.path` の値が同梱テンプレート名（`.typ`なし）でも独自テンプレートのパス（`.typ`あり）でも見つからない。綴りミスを確認 |
| `Chapter file not found` | `chapters` に書いたファイル名が `inputs.dir` 配下に存在しない |
| `Image not found` | Markdown内で参照している画像がそのMarkdownファイルからの相対パスで見つからない |
| `'typst-exec' is allowed only under a 'reviewed/' directory` | `typst-exec`ブロックを `reviewed/` 配下以外のファイルで使った |
| `'npx' (Node.js) not found in PATH` | Mermaid図があるのにNode.jsが未インストール |
