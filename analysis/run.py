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
from core.cache_manager import PaperCache


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


def run_m0(category: int, config: dict, args) -> tuple:
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
    cache_dir = config["paths"]["cache_dir"]
    _save_json(load_report, os.path.join(cache_dir, f"load_report_cat{category}.json"))
    logging.getLogger("M0").info(
        "Loaded %d records for category %d", len(records), category
    )
    return records, load_report


def run_m1(records: list, config: dict) -> tuple:
    from m1_llm_analyzer.keyword_extractor import batch_extract_keywords
    from m1_llm_analyzer.synonym_merger import merge_synonyms
    from m1_llm_analyzer.anomaly_detector import detect_anomalies
    from collections import Counter

    llm = LLMClient(config["llm"])
    cache_dir = config["paths"]["cache_dir"]

    # Keyword extraction
    kw_map = batch_extract_keywords(records, llm, config)
    for rec in records:
        rec.keywords = kw_map.get(rec.title_normalized, [])

    # Count terms
    term_counts: Counter = Counter()
    for rec in records:
        for kw in rec.keywords:
            term_counts[kw] += 1

    # Synonym merge
    term_map = merge_synonyms(dict(term_counts), llm, config)
    _save_json(term_map, os.path.join(cache_dir, "term_map.json"))

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
    _save_json(anomaly_report, os.path.join(cache_dir, "anomaly_report.json"))

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


def run_m3(records: list, config: dict) -> list:
    from m3_classifier.heuristic_classifier import HeuristicClassifier
    from m3_classifier.llm_classifier import LLMClassifier

    heuristics_file = config["classifier"]["heuristics_file"]
    threshold = config["classifier"].get("heuristic_confidence_threshold", 0.85)
    heuristic = HeuristicClassifier(heuristics_file, threshold)
    llm = LLMClient(config["llm"])
    llm_clf = LLMClassifier()

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
        llm_results = llm_clf.classify_batch(needs_llm, llm, config)
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
    cache_dir = config["paths"]["cache_dir"]
    _save_json(paper_tags, os.path.join(cache_dir, "paper_tags.json"))
    return paper_tags


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
        choices=["M0", "M1", "M2", "M3", "M4", "M1+M3", "ALL"],
        default="ALL",
        help="Which module to run",
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

    # Rank filter
    allowed_ranks = set(r.strip().upper() for r in args.rank.split("/"))

    records = []
    term_map = []

    if args.module in ("M0", "ALL"):
        records, _ = run_m0(args.category, config, args)

    if args.module in ("M1", "M1+M3", "ALL"):
        if not records:
            records, _ = run_m0(args.category, config, args)
        term_map, _ = run_m1(records, config)

    if args.module in ("M2", "ALL"):
        if not records:
            records, _ = run_m0(args.category, config, args)
        if not term_map:
            import json as _json
            tm_path = os.path.join(config["paths"]["cache_dir"], "term_map.json")
            if os.path.exists(tm_path):
                with open(tm_path) as fh:
                    term_map = _json.load(fh)
        run_m2(records, term_map, config)

    if args.module in ("M3", "M1+M3", "ALL"):
        if not records:
            records, _ = run_m0(args.category, config, args)
        run_m3(records, config)

    if args.module in ("M4", "ALL"):
        if not records:
            records, _ = run_m0(args.category, config, args)
        if not term_map:
            import json as _json
            tm_path = os.path.join(config["paths"]["cache_dir"], "term_map.json")
            if os.path.exists(tm_path):
                with open(tm_path) as fh:
                    term_map = _json.load(fh)
        run_m4(records, term_map, config)

    log.info("Done.")


if __name__ == "__main__":
    main()
