import sys
from pathlib import Path

pkg_py_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(pkg_py_root))
