# viewer-csharp（Issue #99 スパイク）

C#（.NET） + [pythonnet](https://github.com/pythonnet/pythonnet) で、`build.py` の
`TypstRenderer.render()`（Markdown文字列→Typstコード文字列の変換）を埋め込み呼び出しできるかを
確認するだけの最小疎通確認（スパイク）。ファイル監視・Typstコンパイル・PDF表示・GUI本体は範囲外。
詳細は [Issue #99](https://github.com/tokudiro/context-compositor/issues/99) を参照。

## 前提

- リポジトリ直下の `requirements.txt` の依存パッケージ（`markdown-it-py` 等）がインストール済みの
  Pythonが必要（`build.py` を `import` するため）。
- .NET 8 SDK。

```bash
python3 -m venv /path/to/venv
/path/to/venv/bin/pip install -r ../requirements.txt
```

## ビルド・実行

```bash
cd viewer-csharp
dotnet build

# 埋め込み先のPython（libpython/python.dll）とPYTHONHOMEは環境依存
# （開発機ではMicrosoft Store版Python）なので環境変数で明示する。
VIEWER_PYTHON_DLL="libpython3.11.so.1.0" \
VIEWER_PYTHON_EXTRA_PATH="$(/path/to/venv/bin/python3 -c 'import site; print(site.getsitepackages()[0])')" \
  dotnet bin/Debug/net8.0/ViewerCSharp.dll
```

- `VIEWER_PYTHON_DLL`: pythonnetが読み込むlibpython（Windowsなら `python311.dll` のような
  ファイル名、またはフルパス）。未指定ならpythonnetの既定の探索に任せる。
- `VIEWER_PYTHON_HOME`: `PythonEngine.PythonHome` を明示したい場合に指定（Microsoft Store版
  Pythonのようなサンドボックス配置での探索確認用）。
- `VIEWER_PYTHON_EXTRA_PATH`: `sys.path` へ追加のディレクトリ（venvのsite-packages等）を
  区切り文字（Linux/macOSは`:`、Windowsは`;`）で複数指定できる。

固定のサンプルMarkdown文字列を `TypstRenderer.render()` に渡し、変換結果のTypstコードを
標準出力へ表示するだけのプログラム（`Program.cs`）。

## 検証結果（Linux・開発機ではないサンドボックス環境）

- `TypstRenderer.render()` の呼び出し・戻り値の受け取り・表示は問題なく動作した
  （完了条件の「呼び出し結果が正しく表示できる」は満たしている）。
- **ただし、プロセスの終了処理でハングする事象を確認した。** `using (Py.GIL())` を抜ける
  （GIL解放）、`PythonEngine.Shutdown()`、`Environment.Exit()`、
  `Process.GetCurrentProcess().Kill()` のいずれを試しても標準出力への表示後にプロセスが
  終了せず、SIGKILL（`timeout` コマンド等での強制終了）でしか止められなかった。
  - `PythonEngine.Shutdown()` は.NET 8がBinaryFormatterを既定無効化した影響で単体でも
    例外を投げる（`RuntimeData.Stash` がBinaryFormatterを使うため）。これは
    `<EnableUnsafeBinaryFormatterSerialization>` を有効化すれば回避できる可能性があるが、
    非推奨機能の再有効化になるため本スパイクでは行っていない。
  - 上記のハングとは別に、そもそも通常のプロセス終了処理自体が固まる事象が残った
    （原因未特定。pythonnet起因のネイティブスレッド絡みの可能性が高いが本スパイクの
    範囲では切り分けきれていない）。
- 開発機のMicrosoft Store版Pythonでの検証はしていない（本スパイクをLinux上で作成したため）。
  上記ハングがLinux固有（pythonnetはWindowsでの利用が主で、Linux上の枯れ具合が相対的に低い
  可能性がある）か、Windows + Microsoft Store版Pythonでも再現するかは別途確認が必要。
  自動化スクリプトから呼び出す場合は、当面 `timeout` 等でタイムアウト付き実行にする必要がある。

## Rust版（viewer-rust）との比較メモ

同じ検証環境（Linux）で、Rust + PyO3版（`../viewer-rust/`）は `render()` 呼び出し・表示に加えて
プロセスの正常終了（exit code 0）まで問題なく確認できた。C#/pythonnet版は終了処理の安定性に
課題が残ったという差分が、このスパイクで得られた比較材料の一つ。ただし本比較は本来Windows
（開発機）上で行う想定であり、Linux上の結果をそのままC#とRustの優劣と見なすべきではない点に
注意（次のステップで改めて確認する）。

## 次のステップ（本issueの範囲外）

Issue #99本文の「次のステップ」に加えて、上記の終了時ハングの原因切り分け（Windows +
Microsoft Store版Pythonでの再現確認を含む）。
