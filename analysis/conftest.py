"""
Root conftest.py for the analysis/ directory.

Adds analysis/ and analysis/tests/ to sys.path so that:
- `from core.xxx import` works from test files
- `from sandbox_helpers import` works from test files
"""
import os
import sys

_ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TESTS_DIR = os.path.join(_ANALYSIS_DIR, "tests")

# Insert tests/ first so 'from sandbox_helpers import' resolves correctly
for path in (_TESTS_DIR, _ANALYSIS_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)
