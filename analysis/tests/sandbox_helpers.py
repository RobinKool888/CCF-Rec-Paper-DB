"""
sandbox_helpers.py — shared fixtures and helpers for sandbox tests.

All helpers use MockLLMClient: zero real HTTP calls.
"""
import json
import os
import re
import sys
from collections import Counter

import pytest

# ---------------------------------------------------------------------------
# Path setup — add analysis/ to sys.path so imports work
# ---------------------------------------------------------------------------
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ANALYSIS_DIR = os.path.dirname(_TESTS_DIR)
if _ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, _ANALYSIS_DIR)

_SANDBOX_DIR = os.path.join(_TESTS_DIR, "sandbox")

# ---------------------------------------------------------------------------
# Minimal config used in all sandbox tests
# ---------------------------------------------------------------------------
SANDBOX_CONFIG = {
    "paths": {
        "paper_db": "../paper_db",
        "ccf_catalog": "../paper_db/ccf_catalog.csv",
        "cache_dir": os.path.join(_ANALYSIS_DIR, "cache"),
        "viz_dir": os.path.join(_ANALYSIS_DIR, "viz"),
        "log_dir": os.path.join(_ANALYSIS_DIR, "logs"),
    },
    "loader": {
        "include_workshops": False,
        "include_unverified": True,
        "min_year": 2000,
        "max_year": 2025,
    },
    "llm": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "batch_size": 100,
        "max_concurrent": 1,
        "rpm_limit": 60,
        "max_retries": 1,
        "retry_statuses": [429, 500],
        "cache_dir": os.path.join(_ANALYSIS_DIR, "cache"),
    },
    "term_stats": {
        "top_k_for_synonym_merge": 2000,
        "min_display_freq": 1,
        "ngram_range": [1, 3],
        "trend_window_years": 5,
    },
    "classifier": {
        "heuristics_file": os.path.join(
            _ANALYSIS_DIR, "config", "heuristics", "cat2_networks.yaml"
        ),
        "heuristic_confidence_threshold": 0.85,
    },
    "graph": {
        "similarity_threshold": 0.2,
        "edge_weights": {
            "semantic": 0.6,
            "term_overlap": 0.3,
            "venue_year": 0.1,
        },
        "max_nodes_before_faiss": 20000,
        "top_k_neighbors_ann": 20,
        "embedding_model": "all-MiniLM-L6-v2",
        "umap_n_neighbors": 5,
        "umap_min_dist": 0.1,
    },
}


# ---------------------------------------------------------------------------
# MockLLMClient
# ---------------------------------------------------------------------------
from core.llm_client import SandboxFixtureMissError


class MockLLMClient:
    """Deterministic in-process LLM mock. No HTTP calls."""

    def __init__(self):
        self.model = "mock-model"

    def complete(self, prompt: str, temperature: float = 0.1) -> str:
        if "BAD_PROMPT_MARKER" in prompt:
            raise SandboxFixtureMissError(
                "Prompt hash not found in fixture. "
                "Run analysis/tests/tools/record_fixtures.py to record responses."
            )
        return self._respond(prompt)

    def complete_batch(self, prompts: list, **kwargs) -> list:
        return [self.complete(p) for p in prompts]

    def _respond(self, prompt: str) -> str:
        p = prompt.lower()
        if ("extract" in p or "key technical" in p) and "paper titles" in p:
            return self._keyword_response(prompt)
        if "synonym" in p or ("canonical" in p and "aliases" in p):
            return self._synonym_response(prompt)
        if "anomaly" in p or "confirmed_anomaly" in p or "off-topic" in p:
            return self._anomaly_response(prompt)
        if "research_type" in p and "application_domain" in p:
            return self._classify_response(prompt)
        return "{}"

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------
    def _keyword_response(self, prompt: str) -> str:
        titles = self._extract_titles(prompt)
        result = {}
        for title in titles:
            tl = title.lower()
            terms = []
            if "rdma" in tl:
                terms += ["rdma", "remote direct memory access", "datacenter networking"]
            if "5g" in tl or "6g" in tl or "cellular" in tl or "mmwave" in tl:
                terms += ["5g", "wireless", "cellular network", "mobile network"]
            if "congestion" in tl:
                terms += ["congestion control", "transport protocol", "network performance"]
            if "sdn" in tl or "software-defined" in tl or "software defined" in tl:
                terms += ["software-defined networking", "sdn", "programmable network"]
            if "iot" in tl or "sensor" in tl:
                terms += ["iot", "sensor network", "wireless sensor"]
            if "satellite" in tl or "leo" in tl:
                terms += ["satellite network", "leo constellation", "low-earth orbit"]
            if "datacenter" in tl or "data center" in tl or "cloud" in tl:
                terms += ["datacenter", "cloud computing", "network infrastructure"]
            if "machine learning" in tl or "deep learning" in tl or "reinforcement" in tl:
                terms += ["machine learning", "deep learning", "neural network"]
            if "survey" in tl:
                terms += ["survey", "overview", "literature review"]
            if "graph isomorphism" in tl or "combinatorial" in tl:
                terms += ["graph theory", "combinatorial optimization", "algorithms"]
            if "compiler" in tl or "llvm" in tl or "jit" in tl:
                terms += ["compiler", "program optimization", "static analysis"]
            if "circuit" in tl or "boolean" in tl or "pseudorandom" in tl:
                terms += ["computational complexity", "boolean circuit", "derandomization"]
            if not terms:
                terms = ["networking", "protocol", "system design"]
            result[title] = terms
        return json.dumps(result)

    def _extract_titles(self, prompt: str) -> list:
        titles = []
        for line in prompt.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                titles.append(line[2:].strip())
        return titles

    # ------------------------------------------------------------------
    # Synonym merging
    # ------------------------------------------------------------------
    def _synonym_response(self, prompt: str) -> str:
        term_map = [
            {
                "canonical": "Software-Defined Networking",
                "abbreviation": "SDN",
                "aliases": ["software defined networking", "sdn", "openflow networking"],
                "related_narrower": ["P4 programmable planes", "OpenFlow", "NFV"],
            },
            {
                "canonical": "Remote Direct Memory Access",
                "abbreviation": "RDMA",
                "aliases": ["rdma", "remote direct memory access", "roce"],
                "related_narrower": ["InfiniBand", "RoCEv2", "iWARP"],
            },
            {
                "canonical": "Congestion Control",
                "abbreviation": "",
                "aliases": [
                    "congestion control",
                    "congestion avoidance",
                    "congestion management",
                ],
                "related_narrower": ["BBR", "CUBIC", "ECN"],
            },
            {
                "canonical": "5G Cellular Networks",
                "abbreviation": "5G",
                "aliases": ["5g", "fifth generation", "5g networks", "5g nr"],
                "related_narrower": ["mmWave", "massive MIMO", "network slicing"],
            },
            {
                "canonical": "Internet of Things",
                "abbreviation": "IoT",
                "aliases": ["iot", "internet of things", "iot devices"],
                "related_narrower": ["LoRa", "Zigbee", "NB-IoT"],
            },
            {
                "canonical": "Datacenter Networking",
                "abbreviation": "",
                "aliases": ["datacenter", "data center networking", "cloud networking"],
                "related_narrower": ["ECMP", "fat-tree topology", "RDMA"],
            },
            {
                "canonical": "Machine Learning",
                "abbreviation": "ML",
                "aliases": [
                    "machine learning",
                    "deep learning",
                    "neural network",
                    "reinforcement learning",
                ],
                "related_narrower": ["CNN", "RNN", "transformer"],
            },
        ]
        return json.dumps(term_map)

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------
    def _anomaly_response(self, prompt: str) -> str:
        titles = self._extract_titles(prompt)
        results = []
        for title in titles:
            tl = title.lower()
            is_anomaly = False
            reason = ""
            # Off-topic papers
            if "graph isomorphism" in tl and "combinatorial optimization" in tl:
                is_anomaly = True
                reason = (
                    "Graph isomorphism and combinatorial optimization are "
                    "theoretical CS, not computer networking."
                )
            elif "compiler" in tl or "llvm" in tl or "jit" in tl:
                is_anomaly = True
                reason = "Compiler research is outside computer networking domain."
            elif "boolean circuit" in tl or "pseudorandom generator" in tl:
                is_anomaly = True
                reason = "Complexity theory paper unrelated to networking."
            elif "lower bounds" in tl and "circuit" in tl:
                is_anomaly = True
                reason = "Complexity theory paper unrelated to networking."
            results.append(
                {
                    "title": title,
                    "confirmed_anomaly": is_anomaly,
                    "reason": reason,
                }
            )
        return json.dumps(results)

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    def _classify_response(self, prompt: str) -> str:
        titles = self._extract_titles(prompt)
        results = []
        for title in titles:
            tl = title.lower()
            rt = "SYSTEM_DESIGN"
            domains = ["General_Networking"]

            if "survey" in tl or "overview" in tl:
                rt = "SURVEY_OVERVIEW"
                domains = ["General_Networking"]
            elif "measurement" in tl or "characteriz" in tl or "vivisect" in tl or "wild" in tl:
                rt = "MEASUREMENT_STUDY"
                domains = []
                if "5g" in tl or "cellular" in tl or "wireless" in tl or "mobility" in tl:
                    domains.append("Wireless_Cellular_5G6G")
                if not domains:
                    domains = ["General_Networking"]
            elif "crux" in tl or (
                "gpu" in tl and "scheduling" in tl
            ) or "datacenter" in tl or "rdma" in tl or "data center" in tl:
                rt = "SYSTEM_DESIGN"
                domains = ["Datacenter"]
            elif "netllm" in tl or "llm" in tl or "large language" in tl or (
                "learning" in tl and ("deep" in tl or "machine" in tl or "reinforcement" in tl)
            ):
                rt = "APPLIED_ML"
                domains = ["General_Networking"]
                if "5g" in tl or "cellular" in tl or "edge" in tl:
                    domains.append("Wireless_Cellular_5G6G")
            elif "iot" in tl or "sensor" in tl or "backscatter" in tl or "lora" in tl:
                rt = "SYSTEM_DESIGN"
                domains = ["IoT_Sensor"]
            elif "satellite" in tl or "leo" in tl:
                rt = "SYSTEM_DESIGN"
                domains = ["Satellite_LEO"]
            elif "5g" in tl or "6g" in tl or "cellular" in tl or "wireless" in tl or "mmwave" in tl:
                rt = "SYSTEM_DESIGN"
                domains = ["Wireless_Cellular_5G6G"]
            elif "sdn" in tl or "software-defined" in tl or "nfv" in tl:
                rt = "SYSTEM_DESIGN"
                domains = ["General_Networking"]
            elif "congestion" in tl or "transport" in tl:
                rt = "SYSTEM_DESIGN"
                domains = ["General_Networking"]

            if not domains:
                domains = ["General_Networking"]

            results.append(
                {
                    "title": title,
                    "research_type": rt,
                    "application_domain": domains,
                    "method": "Mock classification result.",
                }
            )
        return json.dumps(results)


# ---------------------------------------------------------------------------
# Public helper functions called by tests
# ---------------------------------------------------------------------------

def load_sandbox(category: int = 2, **kwargs) -> list:
    """Load PaperRecords from sandbox data."""
    from m0_loader.loader import load_papers
    import pandas as pd

    catalog_path = os.path.join(_SANDBOX_DIR, "ccf_catalog.csv")
    catalog_df = pd.read_csv(catalog_path, dtype=str)

    records, _ = load_papers(
        category=category,
        config=SANDBOX_CONFIG,
        catalog_df=catalog_df,
        sandbox_dir=_SANDBOX_DIR,
        **kwargs,
    )
    return records


def load_sandbox_report(category: int = 2) -> dict:
    """Load sandbox data and return the load_report dict."""
    from m0_loader.loader import load_papers
    import pandas as pd

    catalog_path = os.path.join(_SANDBOX_DIR, "ccf_catalog.csv")
    catalog_df = pd.read_csv(catalog_path, dtype=str)

    _, report = load_papers(
        category=category,
        config=SANDBOX_CONFIG,
        catalog_df=catalog_df,
        sandbox_dir=_SANDBOX_DIR,
    )
    return report


def run_m1_sandbox() -> dict:
    """
    Run M1 pipeline on sandbox data using MockLLMClient.
    Returns {"term_map": [...], "anomaly_report": {...}}.
    """
    from m1_llm_analyzer.keyword_extractor import batch_extract_keywords
    from m1_llm_analyzer.synonym_merger import merge_synonyms
    from m1_llm_analyzer.anomaly_detector import detect_anomalies

    records = load_sandbox()
    llm = MockLLMClient()

    kw_map = batch_extract_keywords(records, llm, SANDBOX_CONFIG)
    for rec in records:
        rec.keywords = kw_map.get(rec.title_normalized, [])

    term_counts: Counter = Counter()
    for rec in records:
        for kw in rec.keywords:
            term_counts[kw] += 1

    term_map = merge_synonyms(dict(term_counts), llm, SANDBOX_CONFIG)

    # Build alias -> canonical mapping
    alias_to_canonical: dict = {}
    for entry in term_map:
        canonical = entry["canonical"]
        alias_to_canonical[canonical.lower()] = canonical
        if entry.get("abbreviation"):
            alias_to_canonical[entry["abbreviation"].lower()] = canonical
        for alias in entry.get("aliases", []):
            alias_to_canonical[alias.lower()] = canonical

    for rec in records:
        rec.canonical_terms = list(
            {alias_to_canonical.get(kw.lower(), kw) for kw in rec.keywords}
        )

    anomaly_report = detect_anomalies(records, term_map, llm, SANDBOX_CONFIG)

    return {"term_map": term_map, "anomaly_report": anomaly_report}


def run_m2_sandbox(**kwargs) -> dict:
    """
    Run M2 term statistics on sandbox data.
    Returns term_stats dict.
    kwargs can override loader options (e.g., include_unverified=False).
    """
    from m1_llm_analyzer.keyword_extractor import batch_extract_keywords
    from m1_llm_analyzer.synonym_merger import merge_synonyms
    from m2_term_stats.statistician import compute_term_stats

    records = load_sandbox(**kwargs)
    llm = MockLLMClient()

    kw_map = batch_extract_keywords(records, llm, SANDBOX_CONFIG)
    for rec in records:
        rec.keywords = kw_map.get(rec.title_normalized, [])

    term_counts: Counter = Counter()
    for rec in records:
        for kw in rec.keywords:
            term_counts[kw] += 1

    term_map = merge_synonyms(dict(term_counts), llm, SANDBOX_CONFIG)

    alias_to_canonical: dict = {}
    for entry in term_map:
        canonical = entry["canonical"]
        alias_to_canonical[canonical.lower()] = canonical
        if entry.get("abbreviation"):
            alias_to_canonical[entry["abbreviation"].lower()] = canonical
        for alias in entry.get("aliases", []):
            alias_to_canonical[alias.lower()] = canonical

    for rec in records:
        rec.canonical_terms = list(
            {alias_to_canonical.get(kw.lower(), kw) for kw in rec.keywords}
        )

    # Use min_display_freq=1 so all terms appear
    cfg = dict(SANDBOX_CONFIG)
    cfg["term_stats"] = dict(cfg["term_stats"])
    cfg["term_stats"]["min_display_freq"] = 1

    return compute_term_stats(records, term_map, cfg)


def run_m3_sandbox() -> list:
    """
    Run M3 classifier on sandbox data using MockLLMClient.
    Returns list of paper tag dicts.
    """
    from m3_classifier.heuristic_classifier import HeuristicClassifier
    from m3_classifier.llm_classifier import LLMClassifier

    records = load_sandbox()
    llm = MockLLMClient()

    heuristics_file = os.path.join(
        _ANALYSIS_DIR, "config", "heuristics", "cat2_networks.yaml"
    )
    heuristic = HeuristicClassifier(heuristics_file, confidence_threshold=0.85)
    llm_clf = LLMClassifier()

    needs_llm = []
    for rec in records:
        rt, domains, conf = heuristic.classify(rec)
        if rt:
            rec.research_type = rt
        if domains:
            rec.application_domain = list(domains)
        if not rec.research_type or not rec.application_domain:
            needs_llm.append(rec)

    if needs_llm:
        llm_results = llm_clf.classify_batch(needs_llm, llm, SANDBOX_CONFIG)
        title_to_result = {r["title"]: r for r in llm_results}
        for rec in needs_llm:
            res = title_to_result.get(rec.title, {})
            if not rec.research_type:
                rec.research_type = res.get("research_type", "SYSTEM_DESIGN")
            if not rec.application_domain:
                rec.application_domain = res.get(
                    "application_domain", ["General_Networking"]
                )

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


def run_m4_sandbox() -> dict:
    """
    Run M4 graph pipeline on sandbox data.
    Returns {"nodes": [...], "edges": [...]}.
    Uses keyword-bag embeddings (no sentence-transformers needed).
    """
    from m4_graph.embedder import _keyword_bag_embeddings
    from m4_graph.edge_builder import build_edges
    from m4_graph.clusterer import build_graph
    import numpy as np

    records = run_m3_sandbox_records()

    # Use mock keyword embeddings
    rng = np.random.default_rng(42)
    embeddings = _keyword_bag_embeddings(
        [r.title_normalized for r in records], rng
    )

    # Make RDMA papers very similar to each other
    rdma_indices = [i for i, r in enumerate(records)
                    if "rdma" in r.title_normalized]
    if len(rdma_indices) >= 2:
        # Set RDMA papers to have nearly identical embeddings
        base = embeddings[rdma_indices[0]].copy()
        for idx in rdma_indices[1:]:
            # Slightly perturb but keep very high cosine similarity
            noise = np.random.default_rng(idx).standard_normal(384).astype(np.float32) * 0.01
            vec = base + noise
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            embeddings[idx] = vec

    # Low threshold to ensure edges form in small dataset
    cfg = dict(SANDBOX_CONFIG)
    cfg = {
        **SANDBOX_CONFIG,
        "graph": {
            **SANDBOX_CONFIG["graph"],
            "similarity_threshold": 0.1,
        },
    }

    edges = build_edges(records, embeddings, [], cfg)
    G = build_graph(records, edges, embeddings, cfg)

    nodes = [
        {
            "id": n,
            "title": d.get("title", ""),
            "venue": d.get("venue", ""),
            "year": d.get("year", 0),
            "rank": d.get("rank", ""),
            "cluster_id": d.get("cluster_id", 0),
            "research_type": d.get("research_type", ""),
            "application_domain": d.get("application_domain", []),
        }
        for n, d in G.nodes(data=True)
    ]
    edge_list = [
        {"source": u, "target": v, "weight": d.get("weight", 1.0)}
        for u, v, d in G.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edge_list}


def run_m3_sandbox_records():
    """Internal helper: returns classified PaperRecord list."""
    from m3_classifier.heuristic_classifier import HeuristicClassifier
    from m3_classifier.llm_classifier import LLMClassifier

    records = load_sandbox()
    llm = MockLLMClient()

    heuristics_file = os.path.join(
        _ANALYSIS_DIR, "config", "heuristics", "cat2_networks.yaml"
    )
    heuristic = HeuristicClassifier(heuristics_file, confidence_threshold=0.85)
    llm_clf = LLMClassifier()

    needs_llm = []
    for rec in records:
        rt, domains, conf = heuristic.classify(rec)
        if rt:
            rec.research_type = rt
        if domains:
            rec.application_domain = list(domains)
        if not rec.research_type or not rec.application_domain:
            needs_llm.append(rec)

    if needs_llm:
        llm_results = llm_clf.classify_batch(needs_llm, llm, SANDBOX_CONFIG)
        title_to_result = {r["title"]: r for r in llm_results}
        for rec in needs_llm:
            res = title_to_result.get(rec.title, {})
            if not rec.research_type:
                rec.research_type = res.get("research_type", "SYSTEM_DESIGN")
            if not rec.application_domain:
                rec.application_domain = res.get(
                    "application_domain", ["General_Networking"]
                )
    return records


def count_term_in_sandbox_titles(term: str) -> int:
    """Count how many sandbox (main-track, default) papers have term in normalized title."""
    records = load_sandbox()
    return sum(1 for r in records if term.lower() in r.title_normalized)


def run_m1_with_bad_prompt():
    """Trigger SandboxFixtureMissError by using an empty fixture + bad prompt."""
    fixture_path = os.path.join(
        _TESTS_DIR, "sandbox", "llm_fixtures", "responses.json"
    )
    from core.llm_client import LLMClient

    # Build config with the empty fixture
    llm_cfg = dict(SANDBOX_CONFIG["llm"])
    llm_cfg["cache_dir"] = os.path.join(_ANALYSIS_DIR, "cache")
    client = LLMClient(config=llm_cfg, fixture_path=fixture_path)
    client.complete("BAD_PROMPT_MARKER: this prompt is not in any fixture.")
