import json
import logging
import re
import textwrap

from core.pipeline_db import PipelineDB

logger = logging.getLogger(__name__)

_KEYWORD_BATCH_PROMPT = textwrap.dedent("""
You are a computer science research expert. Extract key technical terms and concepts from each paper title below.

Return ONLY a JSON object (no explanation) mapping each title (verbatim, as given) to a list of concise technical terms.
Example: {{"Title A": ["term1", "term2"], "Title B": ["term3"]}}

Paper titles:
{titles}
""").strip()


def _build_prompt(batch: list) -> str:
    titles_str = "\n".join(f"- {t.title}" for t in batch)
    return _KEYWORD_BATCH_PROMPT.format(titles=titles_str)


def _parse_response(response: str, batch: list) -> dict:
    """Parse LLM JSON response into title_normalized -> [terms] mapping."""
    text = response.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return {}

    result = {}
    title_to_norm = {r.title: r.title_normalized for r in batch}
    for title, terms in raw.items():
        norm = title_to_norm.get(title)
        if norm is not None and isinstance(terms, list):
            result[norm] = [str(t).lower().strip() for t in terms if t]
    return result


def extract_keywords(
    records: list,
    llm_client,
    config: dict,
    db: PipelineDB,
) -> dict:
    """
    Returns {title_norm: [keywords]}.

    Resume logic:
    - Load already-done title_norms from db.m1_keyword_done_norms()
    - Build prompts only for pending records
    - After parsing each batch response: call db.save_m1_keywords_batch(parsed)
    - Never re-process a title_norm already in the DB
    """
    batch_size = config.get("llm", {}).get("batch_size", 20)

    # Seed result with already-persisted keyword rows
    done_norms = db.m1_keyword_done_norms()
    result: dict = db.load_m1_keywords()

    pending = [r for r in records if r.title_normalized not in done_norms]
    n_done = len(done_norms)
    n_pending = len(pending)
    logger.info(
        f"[M1] keyword extraction: {n_done} titles already done, {n_pending} pending"
    )

    if not pending:
        return result

    batches = []
    prompts = []
    for i in range(0, len(pending), batch_size):
        batch = pending[i: i + batch_size]
        batches.append(batch)
        prompts.append(_build_prompt(batch))

    responses = llm_client.complete_batch(prompts)

    for batch, response in zip(batches, responses):
        if not response:
            logger.warning(
                f"[M1] keyword extraction: empty response for batch of {len(batch)} titles"
            )
            continue

        parsed = _parse_response(response, batch)
        if not parsed:
            logger.warning(
                f"[M1] keyword extraction: JSON parse failed for batch of {len(batch)} titles"
            )
            continue

        result.update(parsed)
        # Persist immediately — crash loses at most this one batch
        db.save_m1_keywords_batch(parsed)
        logger.debug(f"[M1] keyword savepoint: +{len(parsed)} titles persisted")

    return result
