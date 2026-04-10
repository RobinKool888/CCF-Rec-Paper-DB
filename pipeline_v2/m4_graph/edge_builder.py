import numpy as np
from typing import List


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def _term_set(record, term_maps: list) -> set:
    terms = set()
    for t in record.canonical_terms:
        terms.add(t.lower())
    for t in record.keywords:
        terms.add(t.lower())
    return terms


def build_edges(
    records: list,
    embeddings: np.ndarray,
    term_maps: list,
    config: dict,
) -> List[dict]:
    """
    Build edges between papers. Uses FAISS for large corpora.

    Returns list of {source, target, weight} dicts.
    """
    graph_cfg = config.get("graph", {})
    threshold = graph_cfg.get("similarity_threshold", 0.45)
    w_sem = graph_cfg.get("edge_weights", {}).get("semantic", 0.6)
    w_term = graph_cfg.get("edge_weights", {}).get("term_overlap", 0.3)
    w_meta = graph_cfg.get("edge_weights", {}).get("venue_year", 0.1)
    max_faiss = graph_cfg.get("max_nodes_before_faiss", 20000)
    top_k_ann = graph_cfg.get("top_k_neighbors_ann", 20)

    n = len(records)
    if n == 0:
        return []

    term_sets = [_term_set(r, term_maps) for r in records]
    emb = embeddings.astype(np.float32)

    edges = []

    if n > max_faiss:
        edges = _build_edges_faiss(
            records, emb, term_sets, threshold,
            w_sem, w_term, w_meta, top_k_ann
        )
    else:
        edges = _build_edges_brute(
            records, emb, term_sets, threshold,
            w_sem, w_term, w_meta
        )

    return edges


def _meta_bonus(r1, r2) -> float:
    bonus = 0.0
    if r1.venue == r2.venue:
        bonus += 0.5
    if abs(r1.year - r2.year) <= 2:
        bonus += 0.5
    return bonus


def _build_edges_brute(records, emb, term_sets, threshold,
                        w_sem, w_term, w_meta):
    n = len(records)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            sem = _cosine_similarity(emb[i], emb[j])
            term = _jaccard(term_sets[i], term_sets[j])
            meta = _meta_bonus(records[i], records[j])
            score = w_sem * sem + w_term * term + w_meta * meta
            if score >= threshold:
                edges.append({"source": i, "target": j, "weight": round(score, 4)})
    return edges


def _build_edges_faiss(records, emb, term_sets, threshold,
                        w_sem, w_term, w_meta, top_k):
    try:
        import faiss
    except ImportError:
        # Fallback to brute force for small enough datasets
        return _build_edges_brute(
            records, emb, term_sets, threshold, w_sem, w_term, w_meta
        )

    n = len(records)
    dim = emb.shape[1]
    index = faiss.IndexFlatIP(dim)
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    emb_norm = (emb / norms).astype(np.float32)
    index.add(emb_norm)

    k = min(top_k + 1, n)
    distances, indices = index.search(emb_norm, k)

    seen = set()
    edges = []
    for i in range(n):
        for rank in range(1, k):
            j = int(indices[i][rank])
            if j <= i:
                continue
            key = (min(i, j), max(i, j))
            if key in seen:
                continue
            seen.add(key)
            sem = float(distances[i][rank])
            term = _jaccard(term_sets[i], term_sets[j])
            meta = _meta_bonus(records[i], records[j])
            score = w_sem * sem + w_term * term + w_meta * meta
            if score >= threshold:
                edges.append(
                    {"source": i, "target": j, "weight": round(score, 4)}
                )
    return edges
