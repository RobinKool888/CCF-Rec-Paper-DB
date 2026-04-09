"""
conftest.py — pytest conftest for sandbox tests.

Sandbox helper functions live in sandbox_helpers.py.
"""
import os
import sys

# ---------------------------------------------------------------------------
# Path setup — add analysis/ to sys.path so imports work
# ---------------------------------------------------------------------------
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ANALYSIS_DIR = os.path.dirname(_TESTS_DIR)
if _ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, _ANALYSIS_DIR)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# Re-export everything from sandbox_helpers so tests can import from either
from sandbox_helpers import (  # noqa: F401, E402
    SANDBOX_CONFIG,
    MockLLMClient,
    load_sandbox,
    load_sandbox_report,
    run_mh_sandbox,
    run_m1_sandbox,
    run_m2_sandbox,
    run_m3_sandbox,
    run_m4_sandbox,
    run_m3_sandbox_records,
    count_term_in_sandbox_titles,
    run_m1_with_bad_prompt,
)
