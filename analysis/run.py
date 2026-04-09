"""Main entry point for the CCF-Rec-Paper-DB analysis pipeline."""
import argparse
import json
import logging
import os
import sys

# Ensure analysis/ directory is importable
_ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, _ANALYSIS_DIR)

from core.config_loader import load_config
from core.llm_client import LLMClient
from core.cache_manager import CacheDB, PaperCache, SubStageCache


def _setup_logging(log_dir: str):
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(log_dir, "run.log")),
        ],
    )


def _save_json(obj, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)


def _get_checkpoint_db(config: dict) -> "CacheDB":
    """Returns a CacheDB instance pointing at the same llm_cache.sqlite used by LLMClient."""
    cache_dir = config["paths"]["cache_dir"]
    os.makedirs(cache_dir, exist_ok=True)
    return CacheDB(os.path.join(cache_dir, "llm_cache.sqlite"))


def _ckpt_key(stage: str, category: int) -> str:
    return f"pipeline_checkpoint:cat{category}:{stage}"


def run_m0(category: int, config: dict, args) -> tuple:
    cache_dir = config["paths"]["cache_dir"]
    paper_cache = PaperCache(os.path.join(cache_dir, "llm_cache.sqlite"))
    ckpt_db = _get_checkpoint_db(config)
    ckpt = _ckpt_key("M0", category)
    force = getattr(args, "force_recompute", False)

    if not force and ckpt_db.get(ckpt):
        cached_records = paper_cache.load_papers(category)
        if cached_records:
            logging.getLogger("M0").info(
                "Resuming: loaded %d records for category %d from cache (skipping CSV parse)",
                len(cached_records), category,
            )
            report_path = os.path.join(cache_dir, f"load_report_cat{category}.json")
            load_report = {}
            if os.path.exists(report_path):
                with open(report_path) as fh:
                    load_report = json.load(fh)
            return cached_records, load_report

    from m0_loader.loader import load_papers
    import pandas as pd

    catalog_df = pd.read_csv(config["paths"]["ccf_catalog"], dtype=str)
    records, load_report = load_papers(
        category=category,
        config=config,
        catalog_df=catalog_df,
        include_workshops=config["loader"]["include_workshops"],
        include_unverified=config["loader"]["include_unverified"],
        year_range=(config["loader"]["min_year"], config["loader"]["max_year"]),
    )
    _save_json(load_report, os.path.join(cache_dir, f"load_report_cat{category}.json"))
    paper_cache.save_papers(records, category)
    ckpt_db.set(ckpt, "done")
    logging.getLogger("M0").info(
        "Loaded %d records for category %d", len(records), category
    )
    return records, load_report


def run_m1(records: list, config: dict, category: int, args) -> tuple:
    from m1_llm_analyzer.keyword_extractor import batch_extract_keywords
    from m1_llm_analyzer.synonym_merger import merge_synonyms
    from m1_llm_analyzer.anomaly_detector import detect_anomalies
    from collections import Counter

    log = logging.getLogger("M1")
    cache_dir = config["paths"]["cache_dir"]
    ckpt_db = _get_checkpoint_db(config)
    ckpt = _ckpt_key("M1", category)
    force = getattr(args, "force_recompute", False)

    term_map_path = os.path.join(cache_dir, "term_map.json")
    anomaly_path = os.path.join(cache_dir, "anomaly_report.json")

    if not force and ckpt_db.get(ckpt) and os.path.exists(term_map_path) and os.path.exists(anomaly_path):
        log.info("Resuming: M1 already complete, loading term_map and anomaly_report from disk")
        with open(term_map_path) as fh:
            term_map = json.load(fh)
        with open(anomaly_path) as fh:
            anomaly_report = json.load(fh)
        alias_to_canonical: dict = {}
        for entry in term_map:
            canonical = entry["canonical"]
            alias_to_canonical[canonical.lower()] = canonical
            if entry.get("abbreviation"):
                alias_to_canonical[entry["abbreviation"].lower()] = canonical
            for alias in entry.get("aliases", []):
                alias_to_canonical[alias.lower()] = canonical
        for rec in records:
            if not getattr(rec, "canonical_terms", None):
                rec.canonical_terms = list({
                    alias_to_canonical.get(kw.lower(), kw)
                    for kw in (getattr(rec, "keywords", None) or [])
                })
        return term_map, anomaly_report

    llm = LLMClient(config["llm"])
    sub_cache = SubStageCache(os.path.join(cache_dir, "llm_cache.sqlite"))
    m1a_ckpt = _ckpt_key("M1a", category)

    # Sub-stage M1a: keyword extraction
    # If M1a checkpoint is set, keyword extraction already completed on a
    # previous run — load the persisted per-title results directly and skip
    # the entire batch_extract_keywords call.
    if not force and ckpt_db.get(m1a_ckpt):
        log.info(
            "Resuming: M1a (keyword extraction) complete, loading kw_results from cache"
        )
        kw_map = sub_cache.load_kw_results(category)
    else:
        kw_map = batch_extract_keywords(
            records, llm, config, category=category, cache_db=sub_cache
        )
        ckpt_db.set(m1a_ckpt, "done")
        log.info("M1a complete: extracted keywords for %d titles", len(kw_map))

    for rec in records:
        rec.keywords = kw_map.get(rec.title_normalized, [])

    # Count terms
    term_counts: Counter = Counter()
    for rec in records:
        for kw in rec.keywords:
            term_counts[kw] += 1

    # Synonym merge
    term_map = merge_synonyms(dict(term_counts), llm, config)
    _save_json(term_map, term_map_path)

    # Assign canonical_terms to records
    alias_to_canonical: dict = {}
    for entry in term_map:
        canonical = entry["canonical"]
        alias_to_canonical[canonical.lower()] = canonical
        if entry.get("abbreviation"):
            alias_to_canonical[entry["abbreviation"].lower()] = canonical
        for alias in entry.get("aliases", []):
            alias_to_canonical[alias.lower()] = canonical

    for rec in records:
        rec.canonical_terms = list({
            alias_to_canonical.get(kw.lower(), kw) for kw in rec.keywords
        })

    # Anomaly detection
    anomaly_report = detect_anomalies(records, term_map, llm, config)
    _save_json(anomaly_report, anomaly_path)

    # Persist enriched records (keywords + canonical_terms now populated) so
    # that re-runs loading from PaperCache have the full data for M2 and M4.
    paper_cache = PaperCache(os.path.join(cache_dir, "llm_cache.sqlite"))
    paper_cache.save_papers(records, category)
    ckpt_db.set(ckpt, "done")
    return term_map, anomaly_report


def run_m2(records: list, term_map: list, config: dict) -> dict:
    from m2_term_stats.statistician import compute_term_stats
    from m2_term_stats.visualizer import generate_all_visualizations

    term_stats = compute_term_stats(records, term_map, config)
    cache_dir = config["paths"]["cache_dir"]
    _save_json(term_stats, os.path.join(cache_dir, "term_freq.json"))
    generate_all_visualizations(
        term_stats, records, config["paths"]["viz_dir"], config
    )
    return term_stats


def run_m3(records: list, config: dict, category: int, args) -> list:
    from m3_classifier.heuristic_classifier import HeuristicClassifier
    from m3_classifier.llm_classifier import LLMClassifier

    cache_dir = config["paths"]["cache_dir"]
    ckpt_db = _get_checkpoint_db(config)
    ckpt = _ckpt_key("M3", category)
    force = getattr(args, "force_recompute", False)

    paper_tags_path = os.path.join(cache_dir, "paper_tags.json")

    if not force and ckpt_db.get(ckpt) and os.path.exists(paper_tags_path):
        logging.getLogger("M3").info("Resuming: M3 already complete, loading paper_tags from disk")
        with open(paper_tags_path) as fh:
            return json.load(fh)

    heuristics_file = config["classifier"]["heuristics_file"]
    threshold = config["classifier"].get("heuristic_confidence_threshold", 0.85)
    heuristic = HeuristicClassifier(heuristics_file, threshold)
    llm = LLMClient(config["llm"])
    llm_clf = LLMClassifier()
    sub_cache = SubStageCache(os.path.join(cache_dir, "llm_cache.sqlite"))

    needs_llm = []
    for rec in records:
        rt, domains, conf = heuristic.classify(rec)
        if rt:
            rec.research_type = rt
        if domains:
            rec.application_domain = domains
        if not rt or not domains:
            needs_llm.append(rec)

    if needs_llm:
        llm_results = llm_clf.classify_batch(
            needs_llm, llm, config, category=category, cache_db=sub_cache
        )
        title_to_result = {r["title"]: r for r in llm_results}
        for rec in needs_llm:
            res = title_to_result.get(rec.title, {})
            if not rec.research_type:
                rec.research_type = res.get("research_type", "SYSTEM_DESIGN")
            if not rec.application_domain:
                rec.application_domain = res.get(
                    "application_domain", ["General_Networking"]
                )

    paper_tags = [
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
    _save_json(paper_tags, paper_tags_path)
    # Persist enriched records (research_type + application_domain now set) so
    # that re-runs loading from PaperCache have the full data for M4.
    paper_cache = PaperCache(os.path.join(cache_dir, "llm_cache.sqlite"))
    paper_cache.save_papers(records, category)
    ckpt_db.set(ckpt, "done")
    return paper_tags


def run_mh(category: int, config: dict, args) -> dict:
    """MH — heuristic-only pipeline (no LLM).

    Steps:
      1. Load papers (M0).
      2. Extract n-gram keywords from titles.
      3. Compute term statistics.
      4. Classify using heuristics only.
      5. Generate term visualizations + classification figures.

    Returns a summary dict with counts and output paths.
    """
    from mh_heuristic.title_extractor import extract_keywords_from_titles
    from mh_heuristic.full_classifier import classify_all
    from m2_term_stats.statistician import compute_term_stats
    from m2_term_stats.visualizer import (
        generate_all_visualizations,
        generate_classification_figures,
    )

    log = logging.getLogger("MH")

    # --- Step 1: load ---
    records, load_report = run_m0(category, config, args)
    log.info("Loaded %d records for category %d", len(records), category)

    # --- Step 2: n-gram keyword extraction ---
    term_map, _alias_map = extract_keywords_from_titles(records, config)
    log.info("Extracted %d distinct n-gram terms", len(term_map))

    # --- Step 3: term stats ---
    term_stats = compute_term_stats(records, term_map, config)
    cache_dir = config["paths"]["cache_dir"]
    _save_json(
        {k: v for k, v in list(term_stats.items())[:500]},
        os.path.join(cache_dir, f"mh_term_freq_cat{category}.json"),
    )
    log.info("Term stats computed: %d terms above min_display_freq", len(term_stats))

    # --- Step 4: heuristic classification ---
    paper_tags = classify_all(records, config)
    _save_json(paper_tags, os.path.join(cache_dir, f"mh_paper_tags_cat{category}.json"))
    log.info("Classified %d papers (heuristics only)", len(paper_tags))

    # --- Step 5: visualizations ---
    viz_dir = config["paths"]["viz_dir"]
    generate_all_visualizations(term_stats, records, viz_dir, config)
    generate_classification_figures(paper_tags, viz_dir)
    log.info("Figures saved to %s", viz_dir)

    from collections import Counter
    rt_counts = dict(Counter(t["research_type"] for t in paper_tags))
    domain_counts: Counter = Counter()
    for t in paper_tags:
        for d in t.get("application_domain", []):
            domain_counts[d] += 1

    summary = {
        "category": category,
        "total_papers": len(paper_tags),
        "research_type_counts": rt_counts,
        "domain_counts": dict(domain_counts.most_common()),
        "term_stats_count": len(term_stats),
        "viz_dir": os.path.abspath(viz_dir),
    }
    _save_json(summary, os.path.join(cache_dir, f"mh_summary_cat{category}.json"))
    return summary


def run_m4(records: list, term_map: list, config: dict):
    from m4_graph.embedder import compute_embeddings
    from m4_graph.edge_builder import build_edges
    from m4_graph.clusterer import build_graph
    from m4_graph.renderer import render_paper_graph

    emb = compute_embeddings(records, config)
    for i, rec in enumerate(records):
        rec.embedding = emb[i].tolist()

    edges = build_edges(records, emb, term_map, config)
    G = build_graph(records, edges, emb, config)

    viz_dir = config["paths"]["viz_dir"]
    os.makedirs(viz_dir, exist_ok=True)
    render_paper_graph(G, records, os.path.join(viz_dir, "paper_graph.html"))

    # Save graph data as JSON
    nodes = [dict(id=n, **d) for n, d in G.nodes(data=True)]
    edge_list = [{"source": u, "target": v, **d}
                 for u, v, d in G.edges(data=True)]
    graph_data = {"nodes": nodes, "edges": edge_list}
    cache_dir = config["paths"]["cache_dir"]
    _save_json(graph_data, os.path.join(cache_dir, "graph_data.json"))
    return G


def main():
    parser = argparse.ArgumentParser(
        description="CCF-Rec-Paper-DB Analysis Pipeline"
    )
    parser.add_argument("--category", type=int, required=True,
                        help="CCF category number")
    parser.add_argument("--rank", default="A/B/C",
                        help="Rank filter: A | B | C | A/B | A/B/C")
    parser.add_argument(
        "--module",
        choices=["MH", "M0", "M1", "M2", "M3", "M4", "M1+M3", "ALL"],
        default="ALL",
        help=(
            "Which module to run. "
            "MH = heuristic-only pipeline (no LLM, fastest); "
            "M0 = data loader only; "
            "M1 = LLM keyword extractor; "
            "M2 = term stats + charts; "
            "M3 = LLM classifier; "
            "M4 = graph builder; "
            "M1+M3 = LLM analysis; "
            "ALL = full pipeline including LLM steps."
        ),
    )
    parser.add_argument("--force-recompute", action="store_true",
                        help="Ignore cached results and recompute")
    parser.add_argument("--config", default="config.yaml",
                        help="Path to config.yaml")
    parser.add_argument("--base-url", default=None,
                        help="Override LLM base URL (for OpenAI-compatible endpoints)")
    args = parser.parse_args()

    config = load_config(os.path.join(_ANALYSIS_DIR, args.config))
    if args.base_url:
        config["llm"]["openai_base_url"] = args.base_url
    _setup_logging(config["paths"]["log_dir"])
    log = logging.getLogger("run")
    log.info(
        "Starting analysis: category=%d, rank=%s, module=%s",
        args.category, args.rank, args.module,
    )

    if args.force_recompute:
        ckpt_db = _get_checkpoint_db(config)
        for stage in ("M0", "M1", "M1a", "M2", "M3", "M4"):
            ckpt_db.invalidate(_ckpt_key(stage, args.category))
        cache_dir = config["paths"]["cache_dir"]
        sub_cache = SubStageCache(os.path.join(cache_dir, "llm_cache.sqlite"))
        sub_cache.clear_kw_results(args.category)
        sub_cache.clear_clf_results(args.category)
        log.info("force-recompute: cleared all pipeline checkpoints and sub-stage caches for category %d", args.category)

    # Rank filter
    allowed_ranks = set(r.strip().upper() for r in args.rank.split("/"))

    records = []
    term_map = []

    if args.module == "MH":
        summary = run_mh(args.category, config, args)
        log.info("MH summary: %s", json.dumps(summary, indent=2))
        return

    if args.module in ("M0", "ALL"):
        records, _ = run_m0(args.category, config, args)

    if args.module in ("M1", "M1+M3", "ALL"):
        if not records:
            records, _ = run_m0(args.category, config, args)
        term_map, _ = run_m1(records, config, args.category, args)

    if args.module in ("M2", "ALL"):
        if not records:
            records, _ = run_m0(args.category, config, args)
        if not term_map:
            tm_path = os.path.join(config["paths"]["cache_dir"], "term_map.json")
            if os.path.exists(tm_path):
                with open(tm_path) as fh:
                    term_map = json.load(fh)
        ckpt_db_m2 = _get_checkpoint_db(config)
        m2_ckpt = _ckpt_key("M2", args.category)
        force = getattr(args, "force_recompute", False)
        if not force and ckpt_db_m2.get(m2_ckpt) and os.path.exists(os.path.join(config["paths"]["cache_dir"], "term_freq.json")):
            log.info("Resuming: M2 already complete, skipping")
        else:
            run_m2(records, term_map, config)
            ckpt_db_m2.set(m2_ckpt, "done")

    if args.module in ("M3", "M1+M3", "ALL"):
        if not records:
            records, _ = run_m0(args.category, config, args)
        run_m3(records, config, args.category, args)

    if args.module in ("M4", "ALL"):
        if not records:
            records, _ = run_m0(args.category, config, args)
        if not term_map:
            tm_path = os.path.join(config["paths"]["cache_dir"], "term_map.json")
            if os.path.exists(tm_path):
                with open(tm_path) as fh:
                    term_map = json.load(fh)
        ckpt_db_m4 = _get_checkpoint_db(config)
        m4_ckpt = _ckpt_key("M4", args.category)
        force = getattr(args, "force_recompute", False)
        if not force and ckpt_db_m4.get(m4_ckpt) and os.path.exists(os.path.join(config["paths"]["cache_dir"], "graph_data.json")):
            log.info("Resuming: M4 already complete, skipping")
        else:
            run_m4(records, term_map, config)
            ckpt_db_m4.set(m4_ckpt, "done")

    log.info("Done.")


if __name__ == "__main__":
    main()
