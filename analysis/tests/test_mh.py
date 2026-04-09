"""Tests for MH heuristic-only pipeline (no LLM)."""
import pytest
from sandbox_helpers import run_mh_sandbox


_VALID_TYPES = {
    "PURE_ALGORITHM",
    "SYSTEM_DESIGN",
    "MEASUREMENT_STUDY",
    "SURVEY_OVERVIEW",
    "APPLIED_ML",
}


def test_mh_no_llm_calls(monkeypatch):
    """Verify zero real HTTP calls in MH mode."""
    try:
        import httpx
        monkeypatch.setattr(
            httpx,
            "post",
            lambda *a, **kw: (_ for _ in ()).throw(
                AssertionError("Real HTTP call attempted in MH mode")
            ),
        )
    except ImportError:
        pass

    try:
        import requests
        monkeypatch.setattr(
            requests,
            "post",
            lambda *a, **kw: (_ for _ in ()).throw(
                AssertionError("Real HTTP call attempted in MH mode")
            ),
        )
    except ImportError:
        pass

    result = run_mh_sandbox()
    assert result is not None


def test_mh_all_records_have_valid_research_type():
    result = run_mh_sandbox()
    for tag in result["paper_tags"]:
        assert tag["research_type"] in _VALID_TYPES, (
            f"Invalid research_type '{tag['research_type']}' for '{tag['title']}'"
        )


def test_mh_all_records_have_application_domain():
    result = run_mh_sandbox()
    for tag in result["paper_tags"]:
        assert isinstance(tag["application_domain"], list), (
            f"application_domain not a list for '{tag['title']}'"
        )
        assert len(tag["application_domain"]) >= 1, (
            f"Empty application_domain for '{tag['title']}'"
        )


def test_mh_measurement_papers_classified():
    """Papers whose normalized title contains 'measurement' or 'vivisect'
    should fire the MEASUREMENT_STUDY heuristic (pattern uses \\bmeasurement\\b
    so plural-only titles are not expected to match)."""
    result = run_mh_sandbox()
    # Papers with exact singular 'measurement' or the 'vivisect' keyword
    meas_papers = [
        t for t in result["paper_tags"]
        if "vivisect" in t["title"].lower()
        or (
            " measurement " in f" {t['title'].lower()} "
            or t["title"].lower().startswith("measurement")
        )
    ]
    # Not all sandbox files necessarily contain such papers; skip if none found
    for t in meas_papers:
        assert t["research_type"] == "MEASUREMENT_STUDY", (
            f"Expected MEASUREMENT_STUDY for '{t['title']}', "
            f"got '{t['research_type']}'"
        )


def test_mh_survey_papers_classified():
    """Papers with 'survey' in title → SURVEY_OVERVIEW."""
    result = run_mh_sandbox()
    survey_papers = [
        t for t in result["paper_tags"]
        if "survey" in t["title"].lower()
    ]
    for t in survey_papers:
        assert t["research_type"] == "SURVEY_OVERVIEW", (
            f"Expected SURVEY_OVERVIEW for '{t['title']}', "
            f"got '{t['research_type']}'"
        )


def test_mh_term_stats_nonzero():
    result = run_mh_sandbox()
    assert len(result["term_stats"]) > 0, "term_stats should not be empty"


def test_mh_term_map_nonzero():
    result = run_mh_sandbox()
    assert len(result["term_map"]) > 0, "term_map should not be empty"


def test_mh_networking_keywords_present():
    """Core networking terms should appear in the n-gram term map."""
    result = run_mh_sandbox()
    all_terms = {e["canonical"].lower() for e in result["term_map"]}
    # At least some basic networking terms should appear in titles
    assert any("network" in t or "rdma" in t or "congestion" in t
               for t in all_terms), (
        f"No expected networking terms found in term_map: {sorted(all_terms)[:20]}"
    )


def test_mh_paper_tags_have_required_fields():
    result = run_mh_sandbox()
    required_fields = {"title", "research_type", "application_domain", "venue", "year", "rank"}
    for tag in result["paper_tags"]:
        missing = required_fields - set(tag.keys())
        assert not missing, f"Missing fields {missing} in tag: {tag}"
