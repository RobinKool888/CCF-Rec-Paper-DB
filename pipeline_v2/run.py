"""
pipeline_v2/run.py — venue-scoped M0→M5 pipeline

Usage:
    python run.py --venue CoNEXT
    python run.py --venue CoNEXT --category 2
    python run.py --venue CoNEXT --force-restart     # clears all savepoints for this venue
    python run.py --venue CoNEXT --skip-llm          # runs M0, M2, M4 only (no API key needed)
    python run.py --venue CoNEXT --dashboard-only    # launches M5 without running pipeline
"""
import argparse
import json
import logging
import os
import sys
from collections import Counter

# Ensure pipeline_v2/ directory is on sys.path so imports resolve
_PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
if _PIPELINE_DIR not in sys.path:
    sys.path.insert(0, _PIPELINE_DIR)

import yaml


def _load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _setup_logging(log_path: str) -> None:
    """Write to both stdout and a log file."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def _build_term_counts(records: list) -> dict:
    """Build {term: count} from all record keywords."""
    counts: Counter = Counter()
    for rec in records:
        for kw in rec.keywords:
            counts[kw.lower().strip()] += 1
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(
        description="pipeline_v2 — venue-scoped CCF analysis pipeline"
    )
    parser.add_argument("--venue", required=True, help="Venue name (e.g. CoNEXT)")
    parser.add_argument(
        "--category", type=int, default=None,
        help="CCF category number (default: from config.yaml domain.category)"
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to config.yaml (default: pipeline_v2/config.yaml)"
    )
    parser.add_argument(
        "--force-restart", action="store_true",
        help="Clear all savepoints for this venue before running"
    )
    parser.add_argument(
        "--skip-llm", action="store_true",
        help="Skip M1 and M3 (no API key required). Runs M0, M2, M4, M5."
    )
    parser.add_argument(
        "--dashboard-only", action="store_true",
        help="Launch M5 dashboard without running the pipeline"
    )
    args = parser.parse_args()

    venue = args.venue

    # Load config
    config_path = args.config or os.path.join(_PIPELINE_DIR, "config.yaml")
    config = _load_config(config_path)

    category = args.category or config.get("domain", {}).get("category", 2)

    # Resolve output dir relative to pipeline_v2/
    output_base = config.get("paths", {}).get("output_dir", "output")
    if not os.path.isabs(output_base):
        output_base = os.path.join(_PIPELINE_DIR, output_base)
    venue_output_dir = os.path.join(output_base, venue)
    os.makedirs(venue_output_dir, exist_ok=True)

    viz_dir = os.path.join(venue_output_dir, "viz")
    os.makedirs(viz_dir, exist_ok=True)

    # Setup logging
    log_path = os.path.join(venue_output_dir, "run.log")
    _setup_logging(log_path)
    logger = logging.getLogger("run")
    logger.info(f"pipeline_v2 starting — venue={venue}, category={category}")

    # Dashboard-only mode
    if args.dashboard_only:
        logger.info("Dashboard-only mode — launching M5")
        _launch_dashboard(venue, venue_output_dir)
        return

    # Initialize pipeline DB
    from core.pipeline_db import PipelineDB
    db_path = os.path.join(venue_output_dir, "pipeline.sqlite")
    db = PipelineDB(db_path)

    if args.force_restart:
        logger.info("--force-restart: clearing all savepoints")
        db.clear_all()

    # ──────────────────────────────────────────────────────────────────
    # M0: Load
    # ──────────────────────────────────────────────────────────────────
    from m0_loader.loader import load_venue
    logger.info("── M0: Loading venue data ──")
    records, load_report = load_venue(venue, category, config, db)
    logger.info(f"M0 complete: {len(records)} records for venue '{venue}'")

    # Write load_report.json
    load_report_path = os.path.join(venue_output_dir, "load_report.json")
    with open(load_report_path, "w", encoding="utf-8") as fh:
        json.dump(load_report, fh, ensure_ascii=False, indent=2)

    if not records:
        logger.warning("No records loaded. Stopping pipeline.")
        return

    # ──────────────────────────────────────────────────────────────────
    # LLM client setup (only if LLM stages will run)
    # ──────────────────────────────────────────────────────────────────
    llm_client = None
    if not args.skip_llm:
        from core.llm_client import LLMClient
        llm_config = dict(config.get("llm", {}))
        llm_config["cache_dir"] = venue_output_dir  # llm_cache.sqlite sits next to pipeline.sqlite
        llm_client = LLMClient(llm_config)

    term_map = []
    anomaly_report = {}

    # ──────────────────────────────────────────────────────────────────
    # M1: LLM Keyword Extraction, Synonym Merge, Anomaly Detection
    # ──────────────────────────────────────────────────────────────────
    if not args.skip_llm:
        if db.is_stage_done("M1"):
            logger.info("M1: resumed from savepoint (stage already complete)")
            # Reload keyword and anomaly data from DB
            kw_map = db.load_m1_keywords()
            for rec in records:
                rec.keywords = kw_map.get(rec.title_normalized, [])
            term_map = db.load_m1_term_map(venue) or []
            canonical_map = db.load_m1_canonical()
            for rec in records:
                rec.canonical_terms = canonical_map.get(rec.title_normalized, [])
            anomaly_data = db.load_m1_anomaly()
            for rec in records:
                data = anomaly_data.get(rec.title_normalized, {})
                rec.anomaly_flag = data.get("flag", False)
                rec.anomaly_reason = data.get("reason", "")
            anomaly_report = _build_anomaly_report(records)
        else:
            logger.info("── M1: Keyword extraction ──")
            from m1_analyzer.keyword_extractor import extract_keywords
            kw_map = extract_keywords(records, llm_client, config, db)
            for rec in records:
                rec.keywords = kw_map.get(rec.title_normalized, [])

            logger.info("── M1: Synonym merge ──")
            from m1_analyzer.synonym_merger import merge_synonyms
            term_counts = _build_term_counts(records)
            term_map = merge_synonyms(term_counts, venue, llm_client, config, db)

            logger.info("── M1: Anomaly detection ──")
            from m1_analyzer.anomaly_detector import detect_anomalies
            anomaly_report = detect_anomalies(records, term_map, llm_client, config, db)

            db.mark_stage_done("M1")
            logger.info("M1 complete")

        # Write M1 outputs
        term_map_path = os.path.join(venue_output_dir, "term_map.json")
        with open(term_map_path, "w", encoding="utf-8") as fh:
            json.dump(term_map, fh, ensure_ascii=False, indent=2)

        anomaly_report_path = os.path.join(venue_output_dir, "anomaly_report.json")
        with open(anomaly_report_path, "w", encoding="utf-8") as fh:
            json.dump(anomaly_report, fh, ensure_ascii=False, indent=2)

    # ──────────────────────────────────────────────────────────────────
    # M2: Term Statistics & Visualizations
    # ──────────────────────────────────────────────────────────────────
    if db.is_stage_done("M2"):
        logger.info("M2: resumed from savepoint (stage already complete)")
        term_stats = _load_json_file(os.path.join(venue_output_dir, "term_freq.json")) or {}
    else:
        logger.info("── M2: Term statistics ──")
        from m2_stats.statistician import compute_term_stats
        from m2_stats.visualizer import generate_all_visualizations
        term_stats = compute_term_stats(records, term_map, config)
        generate_all_visualizations(term_stats, records, viz_dir, config)

        term_freq_path = os.path.join(venue_output_dir, "term_freq.json")
        with open(term_freq_path, "w", encoding="utf-8") as fh:
            json.dump(term_stats, fh, ensure_ascii=False, indent=2)

        db.mark_stage_done("M2")
        logger.info(f"M2 complete: {len(term_stats)} terms")

    # ──────────────────────────────────────────────────────────────────
    # M3: Classification
    # ──────────────────────────────────────────────────────────────────
    paper_tags = []
    if not args.skip_llm:
        if db.is_stage_done("M3"):
            logger.info("M3: resumed from savepoint (stage already complete)")
            paper_tags = _load_json_file(os.path.join(venue_output_dir, "paper_tags.json")) or []
            # Restore record fields from tags
            tag_by_title = {t.get("title", ""): t for t in paper_tags}
            for rec in records:
                tag = tag_by_title.get(rec.title)
                if tag:
                    rec.research_type = tag.get("research_type", "")
                    rec.application_domain = tag.get("application_domain", [])
        else:
            logger.info("── M3: Classification ──")
            _run_m3(records, config, llm_client, db, venue_output_dir, viz_dir)
            paper_tags = _load_json_file(os.path.join(venue_output_dir, "paper_tags.json")) or []
            db.mark_stage_done("M3")
            logger.info(f"M3 complete: {len(paper_tags)} papers tagged")

    # ──────────────────────────────────────────────────────────────────
    # M4: Embeddings & Graph
    # ──────────────────────────────────────────────────────────────────
    if db.is_stage_done("M4"):
        logger.info("M4: resumed from savepoint (stage already complete)")
    else:
        logger.info("── M4: Embeddings & Graph ──")
        _run_m4(records, config, db, term_map, viz_dir)
        db.mark_stage_done("M4")
        logger.info("M4 complete")

    # ──────────────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────────────
    n_anomalies = len(anomaly_report.get("flags", [])) if anomaly_report else 0
    n_terms = len(term_map)
    logger.info(
        f"\n{'='*60}\n"
        f"  Venue:       {venue}\n"
        f"  Papers:      {len(records)}\n"
        f"  Terms:       {n_terms}\n"
        f"  Anomalies:   {n_anomalies}\n"
        f"  Output dir:  {venue_output_dir}\n"
        f"{'='*60}"
    )
    print(
        f"\nTo view the dashboard:\n"
        f"  streamlit run pipeline_v2/m5_dashboard/dashboard.py -- --venue {venue}\n"
    )


def _run_m3(records, config, llm_client, db, venue_output_dir, viz_dir):
    import os
    from m3_classifier.heuristic_classifier import HeuristicClassifier
    from m3_classifier.llm_classifier import LLMClassifier
    from m2_stats.visualizer import generate_classification_figures

    pipeline_dir = os.path.dirname(os.path.abspath(__file__))
    heuristics_file = config.get("classifier", {}).get(
        "heuristics_file", "config/heuristics/cat2_networks.yaml"
    )
    if not os.path.isabs(heuristics_file):
        heuristics_file = os.path.join(pipeline_dir, heuristics_file)

    confidence_threshold = config.get("classifier", {}).get(
        "heuristic_confidence_threshold", 0.85
    )

    heuristic = HeuristicClassifier(heuristics_file, confidence_threshold)
    needs_llm = []
    for rec in records:
        rt, domains, conf = heuristic.classify(rec)
        if rt is not None or domains:
            rec.research_type = rt or "SYSTEM_DESIGN"
            rec.application_domain = domains or ["General_Networking"]
        else:
            needs_llm.append(rec)

    logger = logging.getLogger("run")
    logger.info(
        f"[M3] heuristic classified {len(records) - len(needs_llm)}, "
        f"{len(needs_llm)} pending LLM"
    )

    if needs_llm:
        llm_cls = LLMClassifier()
        llm_results = llm_cls.classify_batch(needs_llm, llm_client, config, db)

        # Apply LLM results back to records
        title_to_result = {item.get("title", ""): item for item in llm_results}
        for rec in needs_llm:
            result = title_to_result.get(rec.title)
            if result:
                rec.research_type = result.get("research_type", "SYSTEM_DESIGN")
                rec.application_domain = result.get("application_domain", ["General_Networking"])
            else:
                rec.research_type = "SYSTEM_DESIGN"
                rec.application_domain = ["General_Networking"]

    # Build paper_tags list
    paper_tags = []
    for rec in records:
        paper_tags.append({
            "title": rec.title,
            "title_norm": rec.title_normalized,
            "venue": rec.venue,
            "year": rec.year,
            "rank": rec.rank,
            "is_main_track": rec.is_main_track,
            "research_type": rec.research_type,
            "application_domain": rec.application_domain,
        })

    tags_path = os.path.join(venue_output_dir, "paper_tags.json")
    with open(tags_path, "w", encoding="utf-8") as fh:
        import json
        json.dump(paper_tags, fh, ensure_ascii=False, indent=2)

    # Generate classification figures
    try:
        generate_classification_figures(paper_tags, viz_dir)
    except Exception:
        pass


def _run_m4(records, config, db, term_map, viz_dir):
    from m4_graph.embedder import compute_embeddings
    from m4_graph.edge_builder import build_edges
    from m4_graph.clusterer import build_graph
    from m4_graph.renderer import render_paper_graph

    import os
    graph_data_path = os.path.join(os.path.dirname(viz_dir), "graph_data.json")
    graph_html_path = os.path.join(viz_dir, "paper_graph.html")

    embeddings = compute_embeddings(records, config, db)

    # Store embeddings back on records
    for i, rec in enumerate(records):
        rec.embedding = embeddings[i].tolist()

    edges = build_edges(records, embeddings, term_map, config)
    graph = build_graph(records, edges, embeddings, config)
    render_paper_graph(graph, records, graph_html_path)

    # Write graph_data.json
    graph_data = {
        "nodes": len(records),
        "edges": len(edges),
        "venue": records[0].venue if records else "",
    }
    with open(graph_data_path, "w", encoding="utf-8") as fh:
        import json
        json.dump(graph_data, fh, ensure_ascii=False, indent=2)


def _build_anomaly_report(records: list) -> dict:
    flags = []
    for rec in records:
        if rec.anomaly_flag:
            flags.append({"title": rec.title, "reason": rec.anomaly_reason})
    return {
        "total_checked": len(records),
        "heuristic_candidates": len(flags),
        "llm_confirmed": len(flags),
        "flags": flags,
    }


def _load_json_file(path: str):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            import json
            return json.load(fh)
    return None


def _launch_dashboard(venue: str, output_dir: str):
    """Launch the Streamlit dashboard."""
    dashboard_path = os.path.join(_PIPELINE_DIR, "m5_dashboard", "dashboard.py")
    cmd = f"streamlit run {dashboard_path} -- --venue {venue} --output-dir {output_dir}"
    logger = logging.getLogger("run")
    logger.info(f"Launching dashboard: {cmd}")
    os.system(cmd)


if __name__ == "__main__":
    main()
