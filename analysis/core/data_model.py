from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PaperRecord:
    title: str
    title_normalized: str
    venue: str
    venue_full: str
    year: int
    rank: str           # "A" | "B" | "C" | "unknown"
    category: int
    sub_venue: str
    is_main_track: bool
    catalog_verified: bool
    keywords: list = field(default_factory=list)
    canonical_terms: list = field(default_factory=list)
    research_type: str = ""
    application_domain: list = field(default_factory=list)
    anomaly_flag: bool = False
    anomaly_reason: str = ""
    embedding: list = field(default_factory=list)
