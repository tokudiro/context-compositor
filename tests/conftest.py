import os
import sys

# text_compositor/ パッケージはリポジトリ直下にあるため、pipインストールしていない
# 開発環境でも tests/配下からimportできるよう、リポジトリ直下をsys.pathへ追加する（#111）。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
