"""後方互換用ラッパー（#111）。

「クローンして直接叩く」既存の使い方（`python build.py --config ...`）をそのまま維持するための
薄いエントリーポイント。実際のロジックは text_compositor/build.py にある
（pipインストール後は `text-compositor` コマンドから `text_compositor.build:build` が
直接呼ばれる）。
"""
from text_compositor.build import build

if __name__ == "__main__":
    build()
