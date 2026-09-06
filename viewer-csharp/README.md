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

## 終了時ハングの原因調査（Windows実機・dotnet-dump）

上記のハングを、Microsoft公式の.NET診断ツール`dotnet-dump`（開発機のグローバル環境ではなく
一時フォルダへ`dotnet tool install --tool-path`でローカルインストールして使用）でダンプを取得し、
`clrthreads`/`pstacks`コマンドでスレッドのマネージドスタックトレースを確認した。

- メインスレッド: `Program.Main` → `System.Environment.Exit(Int32)` を呼び出した状態で停止。
- ファイナライザースレッド: `PythonEngine.OnProcessExit` → `PythonEngine.Shutdown()` →
  `Py.GIL()` → `PythonEngine.AcquireLock()` → `Runtime.PyGILState_Ensure()` で停止。

**原因（この調査結果からの推測）**: pythonnetは`AppDomain.ProcessExit`イベントに
`PythonEngine.OnProcessExit`を自動登録しており、プロセス終了時に自動で`PythonEngine.Shutdown()`
を呼び出す。`Program.cs`は`Py.GIL()`を呼んだ後、GILを一度も解放せず（`using`で囲んでいない）
そのまま`Environment.Exit(0)`を呼んでいる。そのため次の相互待ちが発生していると考えられる。

1. メインスレッドが`Environment.Exit()`のランタイム終了処理として、`ProcessExit`イベント
   ハンドラ（ファイナライザースレッド側）の完了を待つ。
2. そのハンドラ内の`PythonEngine.Shutdown()`がGIL取得（`PyGILState_Ensure`）を試みる。
3. GILはメインスレッドが保持したまま解放されないため、ファイナライザースレッドは永久に
   GILを取得できず、メインスレッドも`ProcessExit`完了待ちから抜けられない。

これまで「GIL解放・Shutdown()・Exit()のどれを試してもダメだった」（Linux環境での記録、
上記参照）としていたが、これらは独立した失敗ではなく、GIL未解放のまま`Environment.Exit()`を
呼ぶことによる一つのデッドロックパターンの現れだった可能性が高い、という仮説を立てた。

**この仮説は不十分だった。** `using (Py.GIL())`でGIL State API（`PyGILState_Ensure`/
`PyGILState_Release`）を使ってGILを解放するよう修正し再検証したが、再度dotnet-dumpで
確認したところ、まったく同じ箇所（ファイナライザースレッドの`PyGILState_Ensure()`）で
依然としてハングした。真の原因と解決策は次節を参照。

## 終了時ハングの解決（Windows実機）

pythonnet公式リポジトリの
[Issue #1701「`PythonEngine.Shutdown()` hangs if called from `AppDomain.ProcessExit`」](https://github.com/pythonnet/pythonnet/issues/1701)
に、本スパイクと同じ症状の既知の挙動が報告されていた。

**真の原因**: `PythonEngine.Initialize()`を呼んだ直後、メインスレッドはPythonの実行
コンテキスト（スレッドステート）を暗黙的に保持したままになる。この暗黙の保持は
`using (Py.GIL())`のGIL State API（`PyGILState_Ensure`/`Release`、内部的にGILの
獲得・解放を一時的に行うだけ）では解放されない。そのため、プロセス終了時にpythonnetの
`OnProcessExit`（別スレッドで実行される）が`PyGILState_Ensure()`でGILを取得しようとしても、
メインスレッドが暗黙に保持したままのコンテキストにブロックされ続ける。

**解決策**: `PythonEngine.Initialize()`の直後に`PythonEngine.BeginAllowThreads()`
（CPythonの`PyEval_SaveThread`に相当）を呼び、このスレッドステートを明示的に手放す。
`Program.cs`にこの1行を追加したところ、組込版Pythonを使ったWindows実機での実行で
**2回連続して`Environment.Exit(0)`後にexit code 0で正常終了し、プロセスの残留も
発生しなかった**。

```csharp
PythonEngine.Initialize();
PythonEngine.BeginAllowThreads(); // これを追加
```

これにより、組込版Python同梱と組み合わせることで、Windows実機でC#(pythonnet)版が
アクセス拒否も終了時ハングもなく動作する構成が確立できた。#99の完了条件
「動作しない場合はどのような制約があるか」に対応する調査は完了し、実際に動作させる
ための具体的な手順（組込版Python同梱 + `BeginAllowThreads()`）も得られた。

## Rust版（viewer-rust）との比較メモ

同じ検証環境（Linux）で、Rust + PyO3版（`../viewer-rust/`）は `render()` 呼び出し・表示に加えて
プロセスの正常終了（exit code 0）まで問題なく確認できた。C#/pythonnet版は終了処理の安定性に
課題が残ったという差分が、このスパイクで得られた比較材料の一つ。ただし本比較は本来Windows
（開発機）上で行う想定であり、Linux上の結果をそのままC#とRustの優劣と見なすべきではない点に
注意（次のステップで改めて確認する）。

## 次のステップ（本issueの範囲外）

Issue #99本文の「次のステップ」を参照。終了時ハングは「終了時ハングの解決（Windows実機）」
節の対策で解消済み。組込版Python同梱の本実装への組み込み（`._pth`編集やsite-packages
vendoringの自動化、ライセンス同梱等）は [Issue #102](https://github.com/tokudiro/context-compositor/issues/102)
で別途検討する。
