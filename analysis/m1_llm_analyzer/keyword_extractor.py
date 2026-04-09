import json
import os
import re
import textwrap


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
    # Strip markdown code fences if present
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


def batch_extract_keywords(
    records: list, llm_client, config: dict,
    category: int = 0,
    cache_db=None,
) -> dict:
    """
    Returns dict mapping title_normalized -> list[str] of technical terms.
    Records are batched by config['llm']['batch_size'].

    When *cache_db* (a SubStageCache) is provided the function:
      - Pre-loads any already-persisted keyword results so those titles are
        skipped entirely (no prompt, no LLM call, no re-parse).
      - Writes each batch's parsed results to kw_results immediately after
        parsing, so a crash loses at most one in-flight batch (~batch_size
        titles) rather than the entire extraction run.
    """
    batch_size = config.get("llm", {}).get("batch_size", 50)

    cache_dir = config.get("paths", {}).get("cache_dir", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    skipped_log = os.path.join(cache_dir, "skipped_batches.jsonl")

    # Seed result with any already-persisted keyword rows.
    result: dict = {}
    if cache_db is not None:
        result.update(cache_db.load_kw_results(category))

    # Build prompts only for titles that have not yet been processed.
    batches_to_send = []
    prompts = []
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        pending = [r for r in batch if r.title_normalized not in result]
        if not pending:
            continue
        batches_to_send.append(pending)
        prompts.append(_build_prompt(pending))

    if not prompts:
        return result  # everything already in per-title cache

    responses = llm_client.complete_batch(prompts)

    for pending, response in zip(batches_to_send, responses):
        if not response:
            # Empty response — content filtered or other API error
            with open(skipped_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "reason": "empty_response",
                    "titles": [r.title for r in pending]
                }, ensure_ascii=False) + "\n")
            continue

        parsed = _parse_response(response, pending)

        if not parsed:
            # Response received but JSON parsing failed
            with open(skipped_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "reason": "json_parse_error",
                    "titles": [r.title for r in pending]
                }, ensure_ascii=False) + "\n")
            continue

        result.update(parsed)
        # Persist immediately — crash loses at most this one batch.
        if cache_db is not None:
            cache_db.save_kw_batch(category, parsed)

    return result
