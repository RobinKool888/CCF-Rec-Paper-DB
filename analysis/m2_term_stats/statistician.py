from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TermStats:
    canonical: str
    total_count: int = 0
    paper_fraction: float = 0.0
    by_year: dict = field(default_factory=dict)
    by_rank: dict = field(default_factory=dict)
    by_venue: dict = field(default_factory=dict)
    trend_slope: float = 0.0
    trend_direction: str = "stable"
    peak_year: int = 0
    first_seen: int = 0
    last_seen: int = 0


def _build_alias_to_canonical(term_map: list) -> dict:
    """Build a lookup: any alias/abbr -> canonical."""
    mapping = {}
    for entry in term_map:
        canonical = entry.get("canonical", "")
        mapping[canonical.lower()] = canonical
        abbr = entry.get("abbreviation", "")
        if abbr:
            mapping[abbr.lower()] = canonical
        for alias in entry.get("aliases", []):
            mapping[alias.lower()] = canonical
    return mapping


def _linear_trend(by_year: dict):
    """Return (slope, direction) from year->count dict."""
    if len(by_year) < 2:
        return 0.0, "stable"
    years = sorted(by_year.keys())
    n = len(years)
    xs = list(range(n))
    ys = [by_year[y] for y in years]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0, "stable"
    slope = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n)) / denom
    if slope > 0.05:
        direction = "rising"
    elif slope < -0.05:
        direction = "falling"
    else:
        direction = "stable"
    return slope, direction


def compute_term_stats(records: list, term_map: list, config: dict) -> dict:
    """
    Returns dict[canonical_name -> TermStats-like dict].
    Each record's canonical_terms list is used to find term occurrences.
    """
    alias_to_canonical = _build_alias_to_canonical(term_map)
    total_papers = max(len(records), 1)

    stats: dict = defaultdict(
        lambda: {
            "canonical": "",
            "total_count": 0,
            "paper_fraction": 0.0,
            "by_year": defaultdict(int),
            "by_rank": defaultdict(int),
            "by_venue": defaultdict(int),
            "trend_slope": 0.0,
            "trend_direction": "stable",
            "peak_year": 0,
            "first_seen": 9999,
            "last_seen": 0,
        }
    )

    for record in records:
        # Gather canonical terms from record
        seen_canonicals = set()
        for term in record.canonical_terms:
            canonical = alias_to_canonical.get(term.lower())
            if canonical is None:
                canonical = term  # use as-is if not in map
            seen_canonicals.add(canonical)

        # Also check keywords directly if canonical_terms is empty
        if not seen_canonicals:
            for kw in record.keywords:
                canonical = alias_to_canonical.get(kw.lower(), kw)
                seen_canonicals.add(canonical)

        for canonical in seen_canonicals:
            s = stats[canonical]
            s["canonical"] = canonical
            s["total_count"] += 1
            s["by_year"][record.year] += 1
            s["by_rank"][record.rank] += 1
            s["by_venue"][record.venue] += 1
            if record.year < s["first_seen"]:
                s["first_seen"] = record.year
            if record.year > s["last_seen"]:
                s["last_seen"] = record.year

    # Post-process
    min_freq = config.get("term_stats", {}).get("min_display_freq", 3)
    result = {}
    for canonical, s in stats.items():
        if s["total_count"] < min_freq:
            continue
        slope, direction = _linear_trend(s["by_year"])
        by_year_plain = dict(s["by_year"])
        peak_year = max(by_year_plain, key=by_year_plain.get) if by_year_plain else 0
        result[canonical] = {
            "canonical": s["canonical"],
            "total_count": s["total_count"],
            "paper_fraction": round(s["total_count"] / total_papers, 4),
            "by_year": by_year_plain,
            "by_rank": dict(s["by_rank"]),
            "by_venue": dict(s["by_venue"]),
            "trend_slope": round(slope, 4),
            "trend_direction": direction,
            "peak_year": peak_year,
            "first_seen": s["first_seen"] if s["first_seen"] != 9999 else 0,
            "last_seen": s["last_seen"],
        }

    return result
