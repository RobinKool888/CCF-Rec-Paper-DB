import json
import os
from pathlib import Path
from typing import Optional

import pandas as pd

from core.data_model import PaperRecord
from m0_loader.normalizer import normalize_title, is_main_track


def _build_catalog_lookup(catalog_df: pd.DataFrame):
    """Return two dicts: abbr->row, name->row (both case-sensitive + lower)."""
    abbr_map = {}
    name_map = {}
    name_lower_map = {}
    for _, row in catalog_df.iterrows():
        abbr = str(row.get("abbr", "")).strip()
        name = str(row.get("name", "")).strip()
        if abbr:
            abbr_map[abbr] = row
        if name:
            name_map[name] = row
            name_lower_map[name.lower()] = row
    return abbr_map, name_map, name_lower_map


def _match_catalog(stem: str, abbr_map, name_map, name_lower_map):
    """Try to find catalog row for a JSON file stem. Returns row or None."""
    if stem in abbr_map:
        return abbr_map[stem]
    if stem in name_map:
        return name_map[stem]
    if stem.lower() in name_lower_map:
        return name_lower_map[stem.lower()]
    return None


def _rank_from_row(row) -> str:
    r = str(row.get("rank", "")).strip().upper()
    if r in ("A", "B", "C"):
        return r
    return "unknown"


def _venue_from_row(row, stem: str) -> str:
    abbr = str(row.get("abbr", "")).strip()
    if abbr:
        return abbr
    name = str(row.get("name", "")).strip()
    return name if name else stem


def load_papers(
    category: int,
    config: dict,
    catalog_df: Optional[pd.DataFrame] = None,
    **kwargs,
) -> tuple:
    """
    Load all PaperRecord objects for a given CCF category.

    Keyword args:
        include_workshops (bool): include non-main-track papers (default False)
        include_unverified (bool): include papers from unverified venues (default True)
        year_range (tuple): (min_year, max_year) inclusive (default (2000, 2025))
        sandbox_dir (str): if set, use this as the root (contains paper_db/ + ccf_catalog.csv)
    """
    include_workshops = kwargs.get("include_workshops", False)
    include_unverified = kwargs.get("include_unverified", True)
    year_range = kwargs.get("year_range", (2000, 2025))
    sandbox_dir = kwargs.get("sandbox_dir", None)

    # Resolve paths
    if sandbox_dir:
        db_root = os.path.join(sandbox_dir, "paper_db")
        catalog_path = os.path.join(sandbox_dir, "ccf_catalog.csv")
    else:
        analysis_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_root = os.path.join(analysis_dir, config["paths"]["paper_db"])
        catalog_path = os.path.join(analysis_dir, config["paths"]["ccf_catalog"])

    # Load catalog
    if catalog_df is None:
        catalog_df = pd.read_csv(catalog_path, dtype=str)

    # Filter catalog to this category
    cat_df = catalog_df[
        catalog_df["category"].astype(str) == str(category)
    ]
    abbr_map, name_map, name_lower_map = _build_catalog_lookup(cat_df)

    category_dir = os.path.join(db_root, str(category))
    if not os.path.isdir(category_dir):
        raise FileNotFoundError(f"Category directory not found: {category_dir}")

    records: list[PaperRecord] = []
    total_records = 0
    main_track_records = 0
    workshop_records = 0
    catalog_verified_venues = set()
    catalog_unverified_venues = set()
    dedup_seen = set()
    dedup_collisions = 0
    years_seen = set()

    json_files = sorted(Path(category_dir).glob("*.json"))

    for json_file in json_files:
        stem = json_file.stem  # filename without .json

        # Catalog matching
        cat_row = _match_catalog(stem, abbr_map, name_map, name_lower_map)
        if cat_row is not None:
            verified = True
            rank = _rank_from_row(cat_row)
            venue = _venue_from_row(cat_row, stem)
            venue_full = str(cat_row.get("name", stem)).strip()
        else:
            verified = False
            rank = "unknown"
            venue = stem
            venue_full = stem

        if not include_unverified and not verified:
            catalog_unverified_venues.add(stem)
            continue

        try:
            with open(json_file, "r", encoding="utf-8") as fh:
                annual_list = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        for annual in annual_list:
            try:
                year = int(annual.get("year", 0))
            except (ValueError, TypeError):
                year = 0
            if not (year_range[0] <= year <= year_range[1]):
                continue
            years_seen.add(year)

            for venue_entry in annual.get("venues", []):
                sub_name_abbr = venue_entry.get("sub_name_abbr", "")
                sub_name = venue_entry.get("sub_name", "")
                is_main = is_main_track(sub_name_abbr)

                if not is_main:
                    workshop_records += len(venue_entry.get("papers", []))
                    if not include_workshops:
                        continue

                for title in venue_entry.get("papers", []):
                    total_records += 1
                    title_norm = normalize_title(title)

                    # Deduplication
                    dedup_key = f"{title_norm}::{venue}::{year}"
                    if dedup_key in dedup_seen:
                        dedup_collisions += 1
                        continue
                    dedup_seen.add(dedup_key)

                    if is_main:
                        main_track_records += 1

                    records.append(
                        PaperRecord(
                            title=title,
                            title_normalized=title_norm,
                            venue=venue,
                            venue_full=venue_full,
                            year=year,
                            rank=rank,
                            category=category,
                            sub_venue=sub_name_abbr,
                            is_main_track=is_main,
                            catalog_verified=verified,
                        )
                    )

        if verified:
            catalog_verified_venues.add(venue)
        else:
            catalog_unverified_venues.add(stem)

    unverified_names = sorted(catalog_unverified_venues)
    year_range_actual = (min(years_seen), max(years_seen)) if years_seen else (0, 0)

    load_report = {
        "category": category,
        "total_records": total_records,
        "main_track_records": main_track_records,
        "workshop_records": workshop_records,
        "catalog_verified_venues": sorted(catalog_verified_venues),
        "catalog_unverified_venues": sorted(catalog_unverified_venues),
        "unverified_venue_names": unverified_names,
        "dedup_collisions": dedup_collisions,
        "year_range_actual": list(year_range_actual),
    }

    return records, load_report
