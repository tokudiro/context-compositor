import os
import sys

# build.pyはリポジトリ直下の単一スクリプトであり、パッケージ化されていないため、
# tests/配下からimportできるようリポジトリ直下をsys.pathへ追加する。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
