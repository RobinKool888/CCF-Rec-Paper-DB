import json
import re
import textwrap


_ANOMALY_PROMPT = textwrap.dedent("""
You are a domain expert for computer networking research (CCF Category 2).

For each paper title below, determine if it is an anomaly (clearly off-topic for computer networks).
Computer networks research includes: datacenter networks, wireless/mobile, IoT, 5G/6G, SDN, NFV,
network measurement, congestion control, transport protocols, CDN, and network security.

Return ONLY a JSON array. Each element must have:
  - "title": the paper title (verbatim)
  - "confirmed_anomaly": true or false
  - "reason": brief explanation if anomaly, else ""

Paper titles to check:
{titles}
""").strip()


def heuristic_anomaly_check(record, domain_keywords):
    """Quick heuristic check before LLM confirmation."""
    t = record.title_normalized
    if not any(kw in t for kw in domain_keywords):
        return True, "no_domain_keyword"
    try:
        from langdetect import detect
        if detect(t) != 'en':
            return True, "non_english"
    except Exception:
        pass
    if len(t.split()) <= 3:
        return True, "too_short"
    return False, None


def _build_prompt(candidates: list) -> str:
    titles_str = "\n".join(f"- {r.title}" for r in candidates)
    return _ANOMALY_PROMPT.format(titles=titles_str)


def _parse_response(response: str) -> list:
    text = response.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def detect_anomalies(
    records: list, term_map: list, llm_client, config: dict
) -> dict:
    """
    Returns anomaly_report dict with:
      - total_checked, heuristic_candidates, llm_confirmed, flags
    """
    # Build domain keyword set from term_map
    domain_keywords: set = set()
    for entry in term_map:
        domain_keywords.add(entry.get("canonical", "").lower())
        domain_keywords.update(a.lower() for a in entry.get("aliases", []))
        abbr = entry.get("abbreviation", "")
        if abbr:
            domain_keywords.add(abbr.lower())

    # Fallback keywords if term_map is empty
    if not domain_keywords:
        domain_keywords = {
            "network", "wireless", "internet", "protocol", "routing",
            "congestion", "bandwidth", "latency", "mobile", "sensor",
            "datacenter", "cloud", "5g", "iot", "rdma", "sdn", "nfv",
        }

    heuristic_candidates = []
    for rec in records:
        flagged, reason = heuristic_anomaly_check(rec, domain_keywords)
        if flagged:
            heuristic_candidates.append((rec, reason))

    flags = []
    if heuristic_candidates:
        batch_size = config.get("llm", {}).get("batch_size", 50)
        cands = [r for r, _ in heuristic_candidates]
        for i in range(0, len(cands), batch_size):
            batch = cands[i : i + batch_size]
            prompt = _build_prompt(batch)
            response = llm_client.complete(prompt)
            parsed = _parse_response(response)
            for item in parsed:
                if isinstance(item, dict) and item.get("confirmed_anomaly"):
                    flags.append({
                        "title": item.get("title", ""),
                        "reason": item.get("reason", ""),
                    })

    return {
        "total_checked": len(records),
        "heuristic_candidates": len(heuristic_candidates),
        "llm_confirmed": len(flags),
        "flags": flags,
    }
