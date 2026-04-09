import json
import re
import textwrap


_SYNONYM_PROMPT = textwrap.dedent("""
You are a computer science taxonomy expert specializing in networking and systems research.

Given the following list of technical terms with their occurrence counts, identify synonym groups.
For each group, produce a canonical name, optional abbreviation, list of aliases, and related narrower terms.

Return ONLY a JSON array. Each element must have:
  - "canonical": string (full descriptive name)
  - "abbreviation": string or null
  - "aliases": list of strings (other names/spellings)
  - "related_narrower": list of strings (specific sub-topics)

Terms (term: count):
{term_list}
""").strip()


def _build_prompt(term_counts: dict) -> str:
    lines = [f"  {term}: {count}" for term, count in
             sorted(term_counts.items(), key=lambda x: -x[1])]
    return _SYNONYM_PROMPT.format(term_list="\n".join(lines))


def _parse_response(response: str) -> list:
    text = response.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if "canonical" not in item:
            continue
        result.append({
            "canonical": str(item.get("canonical", "")),
            "abbreviation": item.get("abbreviation") or "",
            "aliases": [str(a) for a in item.get("aliases", [])],
            "related_narrower": [
                str(r) for r in item.get("related_narrower", [])
            ],
        })
    return result


def merge_synonyms(
    term_counts: dict, llm_client, config: dict
) -> list:
    """
    term_counts: dict mapping term -> count
    Returns term_map: list of dicts with canonical, abbreviation, aliases,
    related_narrower.
    """
    top_k = (
        config.get("term_stats", {})
        .get("top_k_for_synonym_merge", 2000)
    )
    batch_size = (
        config.get("term_stats", {})
        .get("synonym_batch_size", 500)
    )
    # Limit to top-k by count
    top_terms = dict(
        sorted(term_counts.items(), key=lambda x: -x[1])[:top_k]
    )
    if not top_terms:
        return []

    # Split into batches to avoid content-filter issues with large prompts
    items = list(top_terms.items())
    prompts = []
    for i in range(0, len(items), batch_size):
        chunk = dict(items[i : i + batch_size])
        prompts.append(_build_prompt(chunk))

    responses = llm_client.complete_batch(prompts)

    result = []
    for response in responses:
        if response:
            result.extend(_parse_response(response))
    return result
