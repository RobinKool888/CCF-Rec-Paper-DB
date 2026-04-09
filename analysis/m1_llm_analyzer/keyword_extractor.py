import json
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
    records: list, llm_client, config: dict
) -> dict:
    """
    Returns dict mapping title_normalized -> list[str] of technical terms.
    Records are batched by config['llm']['batch_size'].
    """
    batch_size = config.get("llm", {}).get("batch_size", 50)
    result: dict = {}

    prompts = []
    batches = []
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        batches.append(batch)
        prompts.append(_build_prompt(batch))

    responses = llm_client.complete_batch(prompts)

    for batch, response in zip(batches, responses):
        if response:
            parsed = _parse_response(response, batch)
            result.update(parsed)

    return result
