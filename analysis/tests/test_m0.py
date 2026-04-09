"""Tests for M0 data loader."""
import pytest
from sandbox_helpers import load_sandbox, load_sandbox_report


def test_total_records_nonzero():
    records = load_sandbox()
    assert len(records) > 0


def test_catalog_verified_files_loaded():
    report = load_sandbox_report()
    verified_venues = report["catalog_verified_venues"]
    for expected in ["SIGCOMM", "INFOCOM", "TMC", "CC"]:
        assert expected in verified_venues, (
            f"Expected venue '{expected}' in verified_venues, got: {verified_venues}"
        )


def test_unverified_venues_detected():
    report = load_sandbox_report()
    unverified = report["catalog_unverified_venues"]
    assert "Computational Complexity" in unverified
    assert "International Conference on Compiler Construction" in unverified


def test_workshops_excluded_by_default():
    records = load_sandbox()
    workshop_records = [r for r in records if not r.is_main_track]
    assert len(workshop_records) == 0, (
        f"Expected no workshop records by default, got {len(workshop_records)}"
    )


def test_workshops_included_when_flag_set():
    records = load_sandbox(include_workshops=True)
    workshop_records = [r for r in records if not r.is_main_track]
    assert len(workshop_records) > 0, (
        "Expected workshop records when include_workshops=True"
    )


def test_unverified_excluded_when_filtered():
    all_records = load_sandbox(include_unverified=True)
    verified_only = load_sandbox(include_unverified=False)
    unverified_venues = {"Computational Complexity",
                         "International Conference on Compiler Construction"}
    verified_unverified = [r for r in all_records if r.venue in unverified_venues]
    assert len(verified_only) < len(all_records)
    assert len(verified_only) == len(all_records) - len(verified_unverified)


def test_rank_assigned_from_catalog():
    records = load_sandbox()
    sigcomm_papers = [r for r in records if r.venue == "SIGCOMM"]
    assert all(r.rank == "A" for r in sigcomm_papers), (
        "SIGCOMM papers should all have rank A"
    )
    cc_papers = [r for r in records if r.venue == "CC"]
    assert all(r.rank == "C" for r in cc_papers), (
        "Computer Communications papers should all have rank C"
    )


def test_unverified_rank_is_unknown():
    records = load_sandbox(include_unverified=True)
    unverified = [r for r in records if not r.catalog_verified]
    assert all(r.rank == "unknown" for r in unverified), (
        "Unverified papers should have rank 'unknown'"
    )


def test_title_normalized_lowercase():
    records = load_sandbox()
    for rec in records:
        assert rec.title_normalized == rec.title_normalized.lower(), (
            f"Normalized title not lowercase: {rec.title_normalized!r}"
        )


def test_no_duplicate_titles():
    records = load_sandbox()
    seen = set()
    duplicates = []
    for rec in records:
        key = (rec.title_normalized, rec.venue, rec.year)
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    assert len(duplicates) == 0, f"Duplicate records found: {duplicates}"


def test_year_range_in_report():
    report = load_sandbox_report()
    yr = report["year_range_actual"]
    assert yr[0] >= 2022
    assert yr[1] <= 2024


def test_venue_field_uses_catalog_abbr():
    records = load_sandbox()
    # Computer Communications file matches catalog abbr "CC"
    cc_papers = [r for r in records
                 if r.venue_full == "Computer Communications" or r.venue == "CC"]
    assert len(cc_papers) > 0, "Expected Computer Communications papers"
    assert all(r.venue == "CC" for r in cc_papers)
