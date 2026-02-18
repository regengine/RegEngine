import sys
from pathlib import Path
import os

print(f"CWD: {os.getcwd()}")
print(f"__file__: {__file__}")
print(f"Resolved __file__: {Path(__file__).resolve()}")
print(f"Parent Parent: {Path(__file__).resolve().parent.parent}")

_parent_dir = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _parent_dir)
print(f"sys.path[0]: {sys.path[0]}")

try:
    import shared.paths
    print("SUCCESS: imported shared.paths")
except ImportError as e:
    print(f"FAILURE: {e}")

print("Directory listing of _parent_dir:")
print(os.listdir(_parent_dir))
