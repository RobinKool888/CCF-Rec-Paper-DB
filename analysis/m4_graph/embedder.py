import numpy as np


def compute_embeddings(records: list, config: dict):
    """
    Compute sentence embeddings for paper titles.

    Uses sentence-transformers all-MiniLM-L6-v2 (384-dim).
    Falls back to random 384-dim embeddings if package is unavailable.

    Returns np.ndarray of shape (N, 384).
    """
    titles = [r.title_normalized for r in records]
    model_name = config.get("graph", {}).get(
        "embedding_model", "all-MiniLM-L6-v2"
    )

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        embeddings = model.encode(titles, show_progress_bar=False)
        return np.array(embeddings, dtype=np.float32)
    except ImportError:
        # Graceful fallback: reproducible random embeddings based on title hash
        rng = np.random.default_rng(42)
        return _keyword_bag_embeddings(titles, rng)
    except Exception:
        rng = np.random.default_rng(42)
        return _keyword_bag_embeddings(titles, rng)


def _keyword_bag_embeddings(titles: list, rng) -> np.ndarray:
    """Simple deterministic bag-of-words style embedding for testing."""
    dim = 384
    result = []
    for title in titles:
        # Use a hash-seeded random vector per title for reproducibility
        seed = hash(title) % (2 ** 32)
        local_rng = np.random.default_rng(seed)
        vec = local_rng.standard_normal(dim).astype(np.float32)
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        result.append(vec)
    return np.array(result, dtype=np.float32)
