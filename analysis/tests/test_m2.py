"""Tests for M2 term statistics."""
from sandbox_helpers import run_m2_sandbox, count_term_in_sandbox_titles


def test_rdma_count_matches_fixture():
    expected = count_term_in_sandbox_titles("rdma")
    stats = run_m2_sandbox()
    # Look for RDMA under its canonical name
    rdma_entry = (
        stats.get("Remote Direct Memory Access")
        or stats.get("RDMA")
        or stats.get("rdma")
    )
    actual = rdma_entry["total_count"] if rdma_entry else 0
    assert actual == expected, (
        f"RDMA count mismatch: expected {expected}, got {actual}"
    )


def test_rank_breakdown_sums_to_total():
    stats = run_m2_sandbox()
    for term, data in stats.items():
        rank_sum = sum(data["by_rank"].values())
        assert rank_sum == data["total_count"], (
            f"Rank breakdown sum ({rank_sum}) != total_count ({data['total_count']}) "
            f"for term '{term}'"
        )


def test_year_breakdown_sums_to_total():
    stats = run_m2_sandbox()
    for term, data in stats.items():
        year_sum = sum(data["by_year"].values())
        assert year_sum == data["total_count"], (
            f"Year breakdown sum ({year_sum}) != total_count ({data['total_count']}) "
            f"for term '{term}'"
        )


def test_unverified_excluded_when_filtered():
    stats_verified = run_m2_sandbox(include_unverified=False)
    stats_all = run_m2_sandbox(include_unverified=True)
    total_verified = sum(s["total_count"] for s in stats_verified.values())
    total_all = sum(s["total_count"] for s in stats_all.values())
    assert total_all >= total_verified, (
        f"total_all ({total_all}) should be >= total_verified ({total_verified})"
    )
