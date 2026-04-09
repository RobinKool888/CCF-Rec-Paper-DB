"""
test_substage_cache.py — verifies per-title crash-resume for keyword
extraction (M1a) and classification (M3).

These tests do NOT make real LLM calls.  They use a CountingMockLLM that
tracks how many prompts it receives, so we can assert that already-persisted
titles are truly skipped on a simulated restart.
"""
import json
import os
import sys
import tempfile

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ANALYSIS_DIR = os.path.dirname(_TESTS_DIR)
if _ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, _ANALYSIS_DIR)

from core.cache_manager import SubStageCache
from core.data_model import PaperRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(title: str, category: int = 2) -> PaperRecord:
    return PaperRecord(
        title=title,
        title_normalized=title.lower(),
        venue="TEST",
        venue_full="Test Venue",
        year=2024,
        rank="A",
        category=category,
        sub_venue="",
        is_main_track=True,
        catalog_verified=True,
    )


class CountingMockLLM:
    """Records every prompt received and returns deterministic responses."""

    def __init__(self):
        self.call_count = 0
        self.received_titles: list = []

    def _extract_titles(self, prompt: str) -> list:
        """Extract paper titles from '- <title>' lines.
        Skip template description lines like '- "title": ...'."""
        titles = []
        for line in prompt.split("\n"):
            line = line.strip()
            if line.startswith("- ") and not line[2:].startswith('"'):
                titles.append(line[2:].strip())
        return titles

    def _respond(self, prompt: str) -> str:
        titles = self._extract_titles(prompt)
        self.received_titles.extend(titles)
        self.call_count += 1

        # Keyword response
        if "paper titles" in prompt.lower() and "extract" in prompt.lower():
            result = {t: ["networking", "protocol"] for t in titles}
            return json.dumps(result)

        # Classification response
        if "research_type" in prompt and "application_domain" in prompt:
            result = [
                {
                    "title": t,
                    "research_type": "SYSTEM_DESIGN",
                    "application_domain": ["General_Networking"],
                    "method": "mock",
                }
                for t in titles
            ]
            return json.dumps(result)

        return "{}"

    def complete(self, prompt: str, temperature: float = 0.1) -> str:
        return self._respond(prompt)

    def complete_batch(self, prompts: list, **kwargs) -> list:
        return [self.complete(p) for p in prompts]


# ---------------------------------------------------------------------------
# SubStageCache unit tests
# ---------------------------------------------------------------------------

def test_kw_save_and_load(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    cache = SubStageCache(db_path)

    cache.save_kw_batch(2, {"title_a": ["rdma", "networking"], "title_b": ["5g"]})
    loaded = cache.load_kw_results(2)

    assert loaded == {
        "title_a": ["rdma", "networking"],
        "title_b": ["5g"],
    }


def test_kw_results_isolated_by_category(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    cache = SubStageCache(db_path)

    cache.save_kw_batch(1, {"shared_title": ["compiler"]})
    cache.save_kw_batch(2, {"shared_title": ["networking"]})

    assert cache.load_kw_results(1)["shared_title"] == ["compiler"]
    assert cache.load_kw_results(2)["shared_title"] == ["networking"]


def test_kw_clear(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    cache = SubStageCache(db_path)

    cache.save_kw_batch(2, {"title_a": ["rdma"]})
    cache.clear_kw_results(2)
    assert cache.load_kw_results(2) == {}


def test_clf_save_and_load(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    cache = SubStageCache(db_path)

    cache.save_clf_batch(2, [
        {"title": "Paper A", "research_type": "SYSTEM_DESIGN",
         "application_domain": ["Datacenter"]},
        {"title": "Paper B", "research_type": "MEASUREMENT_STUDY",
         "application_domain": ["Wireless_Cellular_5G6G"]},
    ])
    loaded = cache.load_clf_results(2)

    assert loaded["Paper A"]["research_type"] == "SYSTEM_DESIGN"
    assert loaded["Paper A"]["application_domain"] == ["Datacenter"]
    assert loaded["Paper B"]["research_type"] == "MEASUREMENT_STUDY"


def test_clf_results_isolated_by_category(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    cache = SubStageCache(db_path)

    cache.save_clf_batch(1, [{"title": "T", "research_type": "PURE_ALGORITHM",
                               "application_domain": ["General_Networking"]}])
    cache.save_clf_batch(2, [{"title": "T", "research_type": "SYSTEM_DESIGN",
                               "application_domain": ["Datacenter"]}])

    assert cache.load_clf_results(1)["T"]["research_type"] == "PURE_ALGORITHM"
    assert cache.load_clf_results(2)["T"]["research_type"] == "SYSTEM_DESIGN"


# ---------------------------------------------------------------------------
# batch_extract_keywords — crash-resume tests
# ---------------------------------------------------------------------------

def _make_config(cache_dir: str) -> dict:
    return {
        "llm": {"batch_size": 2},
        "paths": {"cache_dir": cache_dir},
    }


def test_kw_extraction_full_run_persists_all_titles(tmp_path):
    """First run: all 5 titles are sent to the LLM and persisted to kw_results."""
    from m1_llm_analyzer.keyword_extractor import batch_extract_keywords

    records = [_make_record(f"Paper {i}") for i in range(5)]
    config = _make_config(str(tmp_path))
    db_path = str(tmp_path / "llm_cache.sqlite")
    cache = SubStageCache(db_path)
    llm = CountingMockLLM()

    kw_map = batch_extract_keywords(records, llm, config, category=2, cache_db=cache)

    # All 5 titles should have keywords
    assert len(kw_map) == 5
    for rec in records:
        assert rec.title_normalized in kw_map

    # All 5 titles should be in kw_results
    persisted = cache.load_kw_results(2)
    assert len(persisted) == 5

    # 3 batches of 2 (ceil(5/2) = 3) prompts sent
    assert llm.call_count == 3


def test_kw_extraction_skips_persisted_on_restart(tmp_path):
    """Simulate crash after first 2 titles processed: only remaining 3 sent to LLM."""
    from m1_llm_analyzer.keyword_extractor import batch_extract_keywords

    records = [_make_record(f"Paper {i}") for i in range(5)]
    config = _make_config(str(tmp_path))
    db_path = str(tmp_path / "llm_cache.sqlite")
    cache = SubStageCache(db_path)

    # Simulate partial progress: first two titles already in kw_results
    cache.save_kw_batch(2, {
        records[0].title_normalized: ["pre_cached_term_0"],
        records[1].title_normalized: ["pre_cached_term_1"],
    })

    llm = CountingMockLLM()
    kw_map = batch_extract_keywords(records, llm, config, category=2, cache_db=cache)

    # Result must include ALL 5 titles (2 from cache + 3 from LLM)
    assert len(kw_map) == 5
    # Pre-cached values are preserved
    assert kw_map[records[0].title_normalized] == ["pre_cached_term_0"]
    assert kw_map[records[1].title_normalized] == ["pre_cached_term_1"]

    # Only the 3 remaining titles were sent to the LLM
    sent_titles = set(llm.received_titles)
    assert records[0].title not in sent_titles
    assert records[1].title not in sent_titles
    for rec in records[2:]:
        assert rec.title in sent_titles


def test_kw_extraction_no_llm_calls_when_fully_cached(tmp_path):
    """If all titles are in kw_results, zero LLM calls are made."""
    from m1_llm_analyzer.keyword_extractor import batch_extract_keywords

    records = [_make_record(f"Paper {i}") for i in range(3)]
    config = _make_config(str(tmp_path))
    db_path = str(tmp_path / "llm_cache.sqlite")
    cache = SubStageCache(db_path)

    # Pre-populate all titles
    for rec in records:
        cache.save_kw_batch(2, {rec.title_normalized: ["cached_term"]})

    llm = CountingMockLLM()
    kw_map = batch_extract_keywords(records, llm, config, category=2, cache_db=cache)

    assert llm.call_count == 0
    assert len(kw_map) == 3


def test_kw_extraction_no_cache_db_unchanged_behaviour(tmp_path):
    """When cache_db=None, function behaves exactly as before (no persistence)."""
    from m1_llm_analyzer.keyword_extractor import batch_extract_keywords

    records = [_make_record(f"Paper {i}") for i in range(4)]
    config = _make_config(str(tmp_path))
    llm = CountingMockLLM()

    kw_map = batch_extract_keywords(records, llm, config)  # no cache_db

    assert len(kw_map) == 4
    assert llm.call_count == 2  # ceil(4/2) = 2 batches


# ---------------------------------------------------------------------------
# LLMClassifier.classify_batch — crash-resume tests
# ---------------------------------------------------------------------------

def test_clf_full_run_persists_all_titles(tmp_path):
    """First run: all 4 titles classified and persisted to clf_results."""
    from m3_classifier.llm_classifier import LLMClassifier

    records = [_make_record(f"Paper {i}") for i in range(4)]
    config = _make_config(str(tmp_path))
    db_path = str(tmp_path / "llm_cache.sqlite")
    cache = SubStageCache(db_path)
    llm = CountingMockLLM()
    clf = LLMClassifier()

    results = clf.classify_batch(records, llm, config, category=2, cache_db=cache)

    assert len(results) == 4
    persisted = cache.load_clf_results(2)
    assert len(persisted) == 4
    assert llm.call_count == 2  # 2 batches of 2


def test_clf_skips_persisted_on_restart(tmp_path):
    """Simulate crash after classifying 2 titles: only remaining 2 sent to LLM."""
    from m3_classifier.llm_classifier import LLMClassifier

    records = [_make_record(f"Paper {i}") for i in range(4)]
    config = _make_config(str(tmp_path))
    db_path = str(tmp_path / "llm_cache.sqlite")
    cache = SubStageCache(db_path)

    # Simulate partial progress: first two titles already classified
    cache.save_clf_batch(2, [
        {"title": records[0].title, "research_type": "SURVEY_OVERVIEW",
         "application_domain": ["General_Networking"]},
        {"title": records[1].title, "research_type": "MEASUREMENT_STUDY",
         "application_domain": ["Datacenter"]},
    ])

    llm = CountingMockLLM()
    clf = LLMClassifier()
    results = clf.classify_batch(records, llm, config, category=2, cache_db=cache)

    # All 4 titles present in output
    titles_in_results = {r["title"] for r in results}
    assert len(titles_in_results) == 4

    # Pre-cached values are preserved
    r0 = next(r for r in results if r["title"] == records[0].title)
    assert r0["research_type"] == "SURVEY_OVERVIEW"

    # Only the 2 remaining titles were sent to the LLM (1 batch)
    sent = set(llm.received_titles)
    assert records[0].title not in sent
    assert records[1].title not in sent
    assert records[2].title in sent
    assert records[3].title in sent


def test_clf_no_llm_calls_when_fully_cached(tmp_path):
    """If all titles are in clf_results, zero LLM calls are made."""
    from m3_classifier.llm_classifier import LLMClassifier

    records = [_make_record(f"Paper {i}") for i in range(3)]
    config = _make_config(str(tmp_path))
    db_path = str(tmp_path / "llm_cache.sqlite")
    cache = SubStageCache(db_path)

    for rec in records:
        cache.save_clf_batch(2, [
            {"title": rec.title, "research_type": "SYSTEM_DESIGN",
             "application_domain": ["General_Networking"]},
        ])

    llm = CountingMockLLM()
    clf = LLMClassifier()
    results = clf.classify_batch(records, llm, config, category=2, cache_db=cache)

    assert llm.call_count == 0
    assert len(results) == 3


def test_clf_no_cache_db_unchanged_behaviour(tmp_path):
    """When cache_db=None, function behaves exactly as before (no persistence)."""
    from m3_classifier.llm_classifier import LLMClassifier

    records = [_make_record(f"Paper {i}") for i in range(4)]
    config = _make_config(str(tmp_path))
    llm = CountingMockLLM()
    clf = LLMClassifier()

    results = clf.classify_batch(records, llm, config)  # no cache_db

    assert len(results) == 4
    assert llm.call_count == 2  # 2 batches of 2
