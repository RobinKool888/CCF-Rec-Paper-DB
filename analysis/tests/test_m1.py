"""Tests for M1 LLM analyzer (keyword extraction, synonym merging, anomaly detection)."""
import pytest
from sandbox_helpers import run_m1_sandbox, run_m1_with_bad_prompt
from core.llm_client import SandboxFixtureMissError


def test_no_real_api_calls(monkeypatch):
    """Confirm no real HTTP calls are made in sandbox mode."""
    try:
        import httpx
        monkeypatch.setattr(
            httpx, "post",
            lambda *a, **kw: (_ for _ in ()).throw(
                AssertionError("Real HTTP call attempted in sandbox mode")
            ),
        )
    except ImportError:
        pass

    try:
        import requests
        monkeypatch.setattr(
            requests, "post",
            lambda *a, **kw: (_ for _ in ()).throw(
                AssertionError("Real HTTP call attempted in sandbox mode")
            ),
        )
    except ImportError:
        pass

    run_m1_sandbox()


def test_fixture_miss_raises_clear_error():
    with pytest.raises(SandboxFixtureMissError) as exc_info:
        run_m1_with_bad_prompt()
    assert "record_fixtures.py" in str(exc_info.value)


def test_key_networking_terms_present_in_term_map():
    result = run_m1_sandbox()
    term_map = result["term_map"]
    canonical_names = {t["canonical"].lower() for t in term_map}
    assert any("congestion control" in c for c in canonical_names), (
        f"'congestion control' not found in: {canonical_names}"
    )
    assert any("rdma" in c or "remote direct memory access" in c
               for c in canonical_names), (
        f"'rdma' / 'remote direct memory access' not found in: {canonical_names}"
    )
    assert any("software-defined" in c or "sdn" in c for c in canonical_names), (
        f"'sdn'/'software-defined' not found in: {canonical_names}"
    )


def test_sdn_synonyms_correctly_grouped():
    result = run_m1_sandbox()
    term_map = result["term_map"]
    sdn = next(
        (
            t for t in term_map
            if "sdn" in t.get("abbreviation", "").lower()
            or "software-defined networking" in t["canonical"].lower()
        ),
        None,
    )
    assert sdn is not None, "SDN canonical term not found in term_map"
    aliases_lower = [a.lower() for a in sdn.get("aliases", [])]
    assert "software defined networking" in aliases_lower or "sdn" in aliases_lower, (
        f"Expected 'sdn' or 'software defined networking' in aliases: {aliases_lower}"
    )


def test_injected_anomaly_is_flagged():
    result = run_m1_sandbox()
    report = result["anomaly_report"]
    flagged_titles = [f["title"].lower() for f in report["flags"]]
    assert any("graph isomorphism" in t for t in flagged_titles), (
        f"Anomaly 'Graph Isomorphism' not in flagged titles: {flagged_titles}"
    )


def test_legitimate_papers_not_flagged():
    result = run_m1_sandbox()
    report = result["anomaly_report"]
    flagged = {f["title"].lower() for f in report["flags"]}
    safe_titles = [
        "rdma over ethernet for distributed training at meta scale",
        "a variegated look at 5g in the wild: performance, power, and qoe implications",
    ]
    for t in safe_titles:
        assert t not in flagged, f"Legitimate paper incorrectly flagged: '{t}'"
