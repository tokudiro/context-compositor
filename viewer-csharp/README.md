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

## 検証結果（Windows実機・Microsoft Store版Python）

開発機（Windows 11、Microsoft Store版Python 3.10）で実際に`dotnet run`した結果、次の2段階の失敗を確認した。

1. `VIEWER_PYTHON_DLL`/`VIEWER_PYTHON_HOME`を未指定のまま実行すると、pythonnetのデフォルト探索が
   正しい`python310.dll`を特定できず、`Python.Runtime.BadPythonDllException`
   （内部的には`Py_IncRef`のシンボル解決に失敗、Win32エラー127＝プロシージャが見つからない）で
   起動できなかった。
2. READMEの手順通り`VIEWER_PYTHON_DLL`/`VIEWER_PYTHON_HOME`にMicrosoft Store版Pythonの実体パス
   （`sys.executable`から辿った`C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.10_...`
   配下の`python310.dll`）を明示しても、`System.ComponentModel.Win32Exception (5):
   アクセスが拒否されました`で`LoadLibrary`自体が失敗した。
   - `icacls`で確認した限り、対象DLLのNTFS ACL上は`BUILTIN\Users`にRead/Execute相当の権限が
     付与されている。それでもロードに失敗したことから、NTFSのアクセス権とは別に、
     `WindowsApps`配下のパッケージに対するWindowsの実行時保護（Store版アプリ以外の外部プロセス
     からのアクセス制限）が働いていると考えられる（原因はACLエントリの状況からの推測であり、
     本スパイクの範囲では未確定）。

**結論**: 開発機のMicrosoft Store版Pythonでは、C#(pythonnet)からの埋め込み呼び出しはそのままでは
動作しない。回避するにはpython.org配布版やpyenv-win等、Store経由ではない通常インストールの
Pythonが別途必要と考えられるが、本スパイクでは未検証。これはIssue #99の完了条件
「動作しない場合はどのような制約があるか」に対応する検証結果。

## 検証結果（Windows実機・組込版Python）

上記のMicrosoft Store版Pythonでのアクセス拒否問題の回避策として、python.orgが配布する
「embeddable package」（組込版Python、`python-3.10.11-embed-amd64.zip`）を
`viewer-csharp/python-embed/`（`.gitignore`対象、リポジトリにはコミットしない）に展開し、
開発機の既存Python環境（Microsoft Store版）には一切手を加えずに検証した。

- 依存パッケージ（`markdown-it-py`等、`requirements.txt`記載のもの）は、Microsoft Store版
  Pythonの`pip`を`pip install --target=<展開先>\site-packages ...`で実行し、グローバル環境を
  変更せずファイルとしてのみ`python-embed/site-packages/`へコピーした。
- 組込版Pythonはデフォルトで`site-packages`の読み込みが無効化されているため、
  `python310._pth`に`site-packages`の行を追記して有効化した。
- `VIEWER_PYTHON_DLL`/`VIEWER_PYTHON_HOME`/`VIEWER_PYTHON_EXTRA_PATH`を、この組込版Pythonの
  パス（`python-embed\python310.dll`、`python-embed`、`python-embed\site-packages`）に向けて
  `dotnet run`した結果、**`TypstRenderer.render()`の呼び出し・戻り値の受け取り・表示が
  問題なく成功した**（Microsoft Store版Pythonで発生していたアクセス拒否は解消した）。
- **ただし、Linux環境で確認していた「プロセスの終了処理でハングする」事象が、Windows実機・
  組込版Pythonでも再現した。** `dotnet run`は60秒経ってもプロセスが終了せず、外部から
  強制終了する必要があった。render()の呼び出し結果自体は正しく標準出力に表示されている。

**結論**: 組込版Pythonへの切り替えでMicrosoft Store版特有のアクセス拒否は回避できる。
一方で、終了時ハングはLinux固有の事象ではなく、Windows + 組込版Pythonでも再現する
（少なくともStore版由来の問題ではない）ことが今回新たに分かった。原因切り分け
（GIL解放・`PythonEngine.Shutdown()`・`Environment.Exit()`のどの段階で固まるか）は
未実施。

## Rust版（viewer-rust）との比較メモ

同じ検証環境（Linux）で、Rust + PyO3版（`../viewer-rust/`）は `render()` 呼び出し・表示に加えて
プロセスの正常終了（exit code 0）まで問題なく確認できた。C#/pythonnet版は終了処理の安定性に
課題が残ったという差分が、このスパイクで得られた比較材料の一つ。ただし本比較は本来Windows
（開発機）上で行う想定であり、Linux上の結果をそのままC#とRustの優劣と見なすべきではない点に
注意（次のステップで改めて確認する）。

## 次のステップ（本issueの範囲外）

Issue #99本文の「次のステップ」に加えて、次の点。

- 終了時ハングの原因切り分け。Linux・Windows（組込版Python）の両方で再現しており、
  Microsoft Store版特有の問題ではないことは分かった。GIL解放・
  `PythonEngine.Shutdown()`・`Environment.Exit()`のどの段階で固まるかの特定、および
  回避策（例: 別プロセスに切り出す、タイムアウト付きの強制終了を前提にする等）の検討が
  必要。組込版Pythonへの切り替え自体では解決しない問題だと分かったため、本実装で採用する
  場合はこのハング対策が前提条件になる。
