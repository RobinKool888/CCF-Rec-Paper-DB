"""
full_classifier.py — Pure heuristic paper classifier (zero LLM calls).

Uses the existing HeuristicClassifier with the configured heuristics file.
Records that do not match any heuristic pattern receive deterministic defaults:
  research_type   → "SYSTEM_DESIGN"
  application_domain → ["General_Networking"]
"""

from typing import List


def classify_all(records: list, config: dict) -> List[dict]:
    """
    Classify every record using heuristics only.

    Side-effect: sets ``record.research_type`` and
    ``record.application_domain`` on each PaperRecord.

    Returns a list of paper-tag dicts compatible with M3 output:
        {"title", "research_type", "application_domain", "venue", "year", "rank"}
    """
    from m3_classifier.heuristic_classifier import HeuristicClassifier

    heuristics_file = config["classifier"]["heuristics_file"]
    threshold = config["classifier"].get("heuristic_confidence_threshold", 0.85)
    heuristic = HeuristicClassifier(heuristics_file, threshold)

    for rec in records:
        rt, domains, _conf = heuristic.classify(rec)
        rec.research_type = rt if rt else "SYSTEM_DESIGN"
        rec.application_domain = domains if domains else ["General_Networking"]

    return [
        {
            "title": r.title,
            "research_type": r.research_type,
            "application_domain": r.application_domain,
            "venue": r.venue,
            "year": r.year,
            "rank": r.rank,
        }
        for r in records
    ]
