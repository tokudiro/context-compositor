// Issue #99: pythonnet経由でbuild.pyのTypstRenderer.render()を呼び出せるかを確認するだけの
// 最小疎通確認（スパイク）。ファイル監視・PDF表示・GUI本体は範囲外。
using Python.Runtime;

// スパイクとして固定のMarkdown文字列を変換する（ファイル指定・CLI引数は範囲外）。
const string SampleMarkdown = """
# Hello from viewer-csharp

This is **bold** text and a list:

- one
- two
""";

// viewer-csharp/ はリポジトリ直下に置かれる想定なので、実行ファイルの場所に依存させず、
// ビルド元ソースの位置からリポジトリルートを求める。
string repoRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
Console.WriteLine($"[viewer-csharp] repo root: {repoRoot}");

// 埋め込み先のPython実行体（libpython）とPYTHONHOMEは環境依存（開発機ではMicrosoft Store版Python）
// なので、環境変数で上書きできるようにする（#99の検証項目そのもの）。
string? pythonDll = Environment.GetEnvironmentVariable("VIEWER_PYTHON_DLL");
if (!string.IsNullOrEmpty(pythonDll))
{
    Runtime.PythonDLL = pythonDll;
}

string? pythonHome = Environment.GetEnvironmentVariable("VIEWER_PYTHON_HOME");
if (!string.IsNullOrEmpty(pythonHome))
{
    PythonEngine.PythonHome = pythonHome;
}

PythonEngine.Initialize();

// 【注意】このスパイクの検証環境（Linux + .NET 8 + pythonnet 3.0.5）では、GILを取得する
// using (Py.GIL())ブロックを抜ける（Dispose、GIL解放）、PythonEngine.Shutdown()、
// Environment.Exit()のいずれを最後に実行してもプロセスがハングし、SIGKILLでしか終了できない
// ことを実機確認した。render()自体の呼び出し結果（末尾のTypstコード出力）は正しく得られており、
// ハングは終了処理側の問題。これも#99の完了条件「動作しない場合はどのような制約があるか」に
// 該当する結果のため、GIL解放・Shutdown()を行わずusing文も使わずに進める
// （原因の切り分け・Windows/MS Store版Pythonでの再現有無の確認は別途必要。次のステップを参照）。
Py.GIL();
Console.WriteLine($"[viewer-csharp] embedded Python: {PythonEngine.Version}");

// build.py を `import build` できるよう、リポジトリルートをsys.pathへ追加する。
// 依存パッケージ（markdown-it-py等）用のsite-packagesを別途追加したい場合は
// VIEWER_PYTHON_EXTRA_PATH（区切り文字はPath.PathSeparator）で指定する。
dynamic sys = Py.Import("sys");
sys.path.insert(0, repoRoot);
string? extraPath = Environment.GetEnvironmentVariable("VIEWER_PYTHON_EXTRA_PATH");
if (!string.IsNullOrEmpty(extraPath))
{
    foreach (string p in extraPath.Split(Path.PathSeparator))
    {
        sys.path.insert(0, p);
    }
}

dynamic buildModule = Py.Import("build");
dynamic renderer = buildModule.TypstRenderer();
string typstCode = renderer.render(SampleMarkdown, filepath: "", drop_leading_title: false);

Console.WriteLine("[viewer-csharp] --- TypstRenderer.render() output ---");
Console.WriteLine(typstCode);

Console.Out.Flush();
Environment.Exit(0);
