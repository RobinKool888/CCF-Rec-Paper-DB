import logging

import numpy as np

from core.pipeline_db import PipelineDB

logger = logging.getLogger(__name__)


def compute_embeddings(records: list, config: dict, db: PipelineDB):
    """
    Compute sentence embeddings for paper titles with per-title savepoints.

    Resume logic:
    - Load already-done title_norms from db.m4_done_norms()
    - Only compute embeddings for records NOT already in DB
    - After computing each batch of embeddings: call db.save_m4_embeddings_batch(batch_dict)
    - Return full np.ndarray by merging DB embeddings with newly computed ones,
      in the same order as `records`

    Batch size for embedding: 256 titles at a time (no LLM, just sentence-transformers).

    Returns np.ndarray of shape (N, dim).
    """
    batch_size = 256
    model_name = config.get("graph", {}).get("embedding_model", "all-MiniLM-L6-v2")

    done_norms = db.m4_done_norms()
    stored_embeddings = db.load_m4_embeddings()

    pending = [r for r in records if r.title_normalized not in done_norms]
    n_done = len(done_norms)
    n_pending = len(pending)
    logger.info(
        f"[M4] embeddings: {n_done} titles already done, {n_pending} pending"
    )

    if pending:
        # Load embedding model once
        encode_fn = _make_encoder(model_name)

        for i in range(0, len(pending), batch_size):
            batch = pending[i: i + batch_size]
            titles = [r.title_normalized for r in batch]
            vecs = encode_fn(titles)  # np.ndarray shape (batch, dim)

            batch_dict = {}
            for rec, vec in zip(batch, vecs):
                stored_embeddings[rec.title_normalized] = vec.tolist()
                batch_dict[rec.title_normalized] = vec.tolist()

            db.save_m4_embeddings_batch(batch_dict)
            logger.debug(
                f"[M4] embedding savepoint: +{len(batch_dict)} titles persisted"
            )

    # Assemble result array in the same order as records
    if not records:
        return np.zeros((0, 384), dtype=np.float32)

    dim = None
    result_vecs = []
    for rec in records:
        vec = stored_embeddings.get(rec.title_normalized)
        if vec is not None:
            result_vecs.append(vec)
            if dim is None:
                dim = len(vec)
        else:
            # Should not happen — fallback to zeros
            logger.warning(
                f"[M4] missing embedding for '{rec.title_normalized}', using zeros"
            )
            result_vecs.append(None)

    if dim is None:
        dim = 384

    arr = np.zeros((len(result_vecs), dim), dtype=np.float32)
    for i, vec in enumerate(result_vecs):
        if vec is not None:
            arr[i] = np.array(vec, dtype=np.float32)

    return arr


def _make_encoder(model_name: str):
    """Return a callable that encodes a list of strings to np.ndarray."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)

        def encode_st(titles: list) -> np.ndarray:
            return np.array(
                model.encode(titles, show_progress_bar=False), dtype=np.float32
            )

        return encode_st
    except (ImportError, Exception):
        logger.warning(
            "[M4] sentence-transformers not available, using deterministic fallback embeddings"
        )
        return _keyword_bag_encoder


def _keyword_bag_encoder(titles: list) -> np.ndarray:
    """Simple deterministic bag-of-words style embedding for testing."""
    dim = 384
    result = []
    for title in titles:
        seed = hash(title) % (2 ** 32)
        local_rng = np.random.default_rng(seed)
        vec = local_rng.standard_normal(dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        result.append(vec)
    return np.array(result, dtype=np.float32)
