# viewer-rust（Issue #99 スパイク）

Rust + [PyO3](https://pyo3.rs/) で、`build.py` の `TypstRenderer.render()`（Markdown文字列→
Typstコード文字列の変換）を埋め込み呼び出しできるかを確認するだけの最小疎通確認（スパイク）。
ファイル監視・Typstコンパイル・PDF表示・GUI本体は範囲外。詳細は
[Issue #99](https://github.com/tokudiro/context-compositor/issues/99) を参照。

## 前提

- リポジトリ直下の `requirements.txt` の依存パッケージ（`markdown-it-py` 等）がインストール済みの
  Pythonが必要（`build.py` を `import` するため）。
- PyO3はビルド時に `PYO3_PYTHON` 環境変数（未指定時はPATH上の `python3`）が指す Python の
  ヘッダ・共有ライブラリ情報を使ってリンクする。実行時も同じPythonのインタプリタが埋め込まれる。

```bash
python3 -m venv /path/to/venv
/path/to/venv/bin/pip install -r ../requirements.txt
```

## ビルド・実行

```bash
cd viewer-rust
PYO3_PYTHON=/path/to/venv/bin/python3 cargo build

# 実行時、依存パッケージ（markdown-it-py等）のsite-packagesをPYTHONPATHへ通す。
# 埋め込まれるPythonの標準ライブラリ探索が環境依存（Microsoft Store版Python等）で崩れる場合は
# PYTHONHOME等の追加調整が必要になる可能性がある（下記「検証結果」参照）。
PYTHONPATH="$(/path/to/venv/bin/python3 -c 'import site; print(site.getsitepackages()[0])')" \
  ./target/debug/viewer-rust
```

固定のサンプルMarkdown文字列を `TypstRenderer.render()` に渡し、変換結果のTypstコードを
標準出力へ表示するだけのプログラム（`src/main.rs`）。

## 検証結果（Linux・開発機ではないサンドボックス環境）

- `TypstRenderer.render()` の呼び出し・戻り値の受け取り・表示は問題なく動作した。
- プロセスは正常終了する（exit code 0）。GIL解放やインタプリタの後始末で固まる事象は見られなかった。
- 開発機のMicrosoft Store版Pythonでの検証はしていない（本スパイクをLinux上で作成したため）。
  Windows + Microsoft Store版Pythonでビルド・実行して同様に動作するかは別途確認が必要
  （`PYO3_PYTHON` をStore版Pythonの `python.exe` に向けてビルドし直す想定）。

## 次のステップ（本issueの範囲外）

Issue #99本文の「次のステップ」を参照。
