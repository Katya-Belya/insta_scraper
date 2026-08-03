"""
Puts the repository root on sys.path so tests can `import src.*`.

This exists instead of a packaging file (pyproject.toml / setup.py) or an
editable install: the project is a prototype, and this is the smallest thing
that makes the package importable from both pytest and the notebooks.
"""

import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
