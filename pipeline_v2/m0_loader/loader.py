import json
import logging
import os

import pandas as pd

from core.data_model import PaperRecord
from core.pipeline_db import PipelineDB
from m0_loader.normalizer import normalize_title, is_main_track

logger = logging.getLogger(__name__)


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


def load_venue(
    venue: str,
    category: int,
    config: dict,
    db: PipelineDB,
) -> tuple:
    """
    Load PaperRecord objects for a single venue from paper_db/{category}/{venue}.json.

    Resume logic: if M0 is already done in the DB, load records from the DB
    and return immediately (zero file I/O, zero API calls).

    Returns:
        (records: list[PaperRecord], load_report: dict)

    Raises:
        FileNotFoundError: if paper_db/{category}/{venue}.json does not exist.
    """
    if db.is_stage_done("M0"):
        raw_records = db.load_m0_records()
        records = [PaperRecord(**r) for r in raw_records]
        n = len(records)
        logger.info(f"M0: resumed from savepoint ({n} records)")
        # Reconstruct a minimal load_report from the stored records
        load_report = {
            "venue": venue,
            "category": category,
            "total_records": n,
            "main_track_records": sum(1 for r in records if r.is_main_track),
            "workshop_records": sum(1 for r in records if not r.is_main_track),
            "catalog_verified_venues": list({r.venue for r in records if r.catalog_verified}),
            "catalog_unverified_venues": list({r.venue for r in records if not r.catalog_verified}),
            "unverified_venue_names": [],
            "dedup_collisions": 0,
            "year_range_actual": (
                [min(r.year for r in records), max(r.year for r in records)]
                if records else [0, 0]
            ),
        }
        return records, load_report

    # Resolve paths
    pipeline_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paper_db_path = config["paths"]["paper_db"]
    if not os.path.isabs(paper_db_path):
        paper_db_path = os.path.normpath(os.path.join(pipeline_dir, paper_db_path))

    catalog_path = config["paths"]["ccf_catalog"]
    if not os.path.isabs(catalog_path):
        catalog_path = os.path.normpath(os.path.join(pipeline_dir, catalog_path))

    # The venue JSON file
    json_file = os.path.join(paper_db_path, str(category), f"{venue}.json")
    if not os.path.exists(json_file):
        raise FileNotFoundError(
            f"Venue file not found: {json_file}\n"
            f"Check that '{venue}' exists in paper_db/{category}/ "
            f"(use the filename without .json extension)."
        )

    # Load catalog
    catalog_df = pd.read_csv(catalog_path, dtype=str)
    cat_df = catalog_df[catalog_df["category"].astype(str) == str(category)]
    abbr_map, name_map, name_lower_map = _build_catalog_lookup(cat_df)

    # Load loader config
    loader_cfg = config.get("loader", {})
    include_workshops = loader_cfg.get("include_workshops", False)
    include_unverified = loader_cfg.get("include_unverified", True)
    min_year = loader_cfg.get("min_year", 2000)
    max_year = loader_cfg.get("max_year", 2025)
    year_range = (min_year, max_year)

    stem = venue

    # Catalog matching
    cat_row = _match_catalog(stem, abbr_map, name_map, name_lower_map)
    if cat_row is not None:
        verified = True
        rank = _rank_from_row(cat_row)
        venue_key = _venue_from_row(cat_row, stem)
        venue_full = str(cat_row.get("name", stem)).strip()
    else:
        verified = False
        rank = "unknown"
        venue_key = stem
        venue_full = stem

    if not include_unverified and not verified:
        logger.warning(f"M0: venue '{venue}' is not catalog-verified and include_unverified=false — no records loaded.")
        return [], {
            "venue": venue,
            "category": category,
            "total_records": 0,
            "main_track_records": 0,
            "workshop_records": 0,
            "catalog_verified_venues": [],
            "catalog_unverified_venues": [stem],
            "unverified_venue_names": [stem],
            "dedup_collisions": 0,
            "year_range_actual": [0, 0],
        }

    try:
        with open(json_file, "r", encoding="utf-8") as fh:
            annual_list = json.load(fh)
    except (json.JSONDecodeError, OSError) as e:
        raise FileNotFoundError(f"Could not read venue file {json_file}: {e}") from e

    records: list[PaperRecord] = []
    total_records = 0
    main_track_records = 0
    workshop_records = 0
    dedup_seen = set()
    dedup_collisions = 0
    years_seen = set()

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
                dedup_key = f"{title_norm}::{venue_key}::{year}"
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
                        venue=venue_key,
                        venue_full=venue_full,
                        year=year,
                        rank=rank,
                        category=category,
                        sub_venue=sub_name_abbr,
                        is_main_track=is_main,
                        catalog_verified=verified,
                    )
                )

    year_range_actual = (
        [min(years_seen), max(years_seen)] if years_seen else [0, 0]
    )

    load_report = {
        "venue": venue,
        "category": category,
        "total_records": total_records,
        "main_track_records": main_track_records,
        "workshop_records": workshop_records,
        "catalog_verified_venues": [venue_key] if verified else [],
        "catalog_unverified_venues": [] if verified else [stem],
        "unverified_venue_names": [] if verified else [stem],
        "dedup_collisions": dedup_collisions,
        "year_range_actual": list(year_range_actual),
    }

    logger.info(f"M0: loaded {len(records)} records for venue '{venue}'")

    # Save to DB
    db.save_m0_records_bulk(records)
    db.mark_stage_done("M0")
    logger.info(f"M0: savepoint written ({len(records)} records)")

    return records, load_report
