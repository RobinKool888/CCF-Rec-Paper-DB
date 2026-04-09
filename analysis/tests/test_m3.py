"""Tests for M3 paper classifier."""
from sandbox_helpers import run_m3_sandbox


def test_known_system_paper_classified_correctly():
    tags = run_m3_sandbox()
    crux = next(
        (
            t for t in tags
            if "crux" in t["title"].lower() and "gpu-efficient" in t["title"].lower()
        ),
        None,
    )
    assert crux is not None, "Crux paper not found in tags"
    assert crux["research_type"] == "SYSTEM_DESIGN", (
        f"Expected SYSTEM_DESIGN, got {crux['research_type']}"
    )
    assert "Datacenter" in crux["application_domain"], (
        f"Expected 'Datacenter' in {crux['application_domain']}"
    )


def test_measurement_study_classified_correctly():
    tags = run_m3_sandbox()
    meas = next(
        (t for t in tags if "vivisect" in t["title"].lower()),
        None,
    )
    assert meas is not None, "Measurement study paper ('vivisecting') not found"
    assert meas["research_type"] == "MEASUREMENT_STUDY", (
        f"Expected MEASUREMENT_STUDY, got {meas['research_type']}"
    )
    assert "Wireless_Cellular_5G6G" in meas["application_domain"], (
        f"Expected 'Wireless_Cellular_5G6G' in {meas['application_domain']}"
    )


def test_all_records_have_research_type():
    tags = run_m3_sandbox()
    valid_types = {
        "PURE_ALGORITHM",
        "SYSTEM_DESIGN",
        "MEASUREMENT_STUDY",
        "SURVEY_OVERVIEW",
        "APPLIED_ML",
    }
    for t in tags:
        assert t["research_type"] in valid_types, (
            f"Invalid research_type '{t['research_type']}' for '{t['title']}'"
        )


def test_all_records_have_application_domain():
    tags = run_m3_sandbox()
    for t in tags:
        assert isinstance(t["application_domain"], list), (
            f"application_domain not a list for '{t['title']}'"
        )
        assert len(t["application_domain"]) >= 1, (
            f"Empty application_domain for '{t['title']}'"
        )
