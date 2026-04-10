import json
import logging
import re
import textwrap

from core.pipeline_db import PipelineDB

logger = logging.getLogger(__name__)

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


def _heuristic_anomaly_check(record, domain_keywords: set):
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
    records: list,
    term_map: list,
    llm_client,
    config: dict,
    db: PipelineDB,
) -> dict:
    """
    Resume logic:
    - Load already-done title_norms from db.m1_anomaly_done_norms()
    - Only run heuristic + LLM checks on records NOT already in the DB
    - After parsing each batch: call db.save_m1_anomaly_batch(results)
    - At the end: load ALL anomaly results from db.load_m1_anomaly() to build full report

    Also updates each PaperRecord's anomaly_flag/anomaly_reason fields and
    writes canonical_terms back via db.save_m1_canonical_batch.
    """
    # Build domain keyword set from term_map
    domain_keywords: set = set()
    for entry in term_map:
        domain_keywords.add(entry.get("canonical", "").lower())
        domain_keywords.update(a.lower() for a in entry.get("aliases", []))
        abbr = entry.get("abbreviation", "")
        if abbr:
            domain_keywords.add(abbr.lower())

    if not domain_keywords:
        domain_keywords = {
            "network", "wireless", "internet", "protocol", "routing",
            "congestion", "bandwidth", "latency", "mobile", "sensor",
            "datacenter", "cloud", "5g", "iot", "rdma", "sdn", "nfv",
        }

    # Build alias-to-canonical mapping for canonical_terms
    alias_to_canonical: dict = {}
    for entry in term_map:
        canonical = entry.get("canonical", "")
        alias_to_canonical[canonical.lower()] = canonical
        abbr = entry.get("abbreviation", "")
        if abbr:
            alias_to_canonical[abbr.lower()] = canonical
        for alias in entry.get("aliases", []):
            alias_to_canonical[alias.lower()] = canonical

    done_norms = db.m1_anomaly_done_norms()
    pending = [r for r in records if r.title_normalized not in done_norms]

    n_done = len(done_norms)
    n_pending = len(pending)
    logger.info(
        f"[M1] anomaly detection: {n_done} titles already done, {n_pending} pending"
    )

    if pending:
        batch_size = config.get("llm", {}).get("batch_size", 20)

        # Run heuristic check on pending records
        heuristic_candidates = []
        non_candidates = []
        for rec in pending:
            flagged, reason = _heuristic_anomaly_check(rec, domain_keywords)
            if flagged:
                heuristic_candidates.append((rec, reason))
            else:
                non_candidates.append(rec)

        # Save non-candidates immediately (no anomaly)
        non_candidate_batch = [
            {"title_norm": r.title_normalized, "flag": False, "reason": ""}
            for r in non_candidates
        ]
        if non_candidate_batch:
            db.save_m1_anomaly_batch(non_candidate_batch)

        # LLM check on heuristic candidates in batches
        if heuristic_candidates:
            cands = [r for r, _ in heuristic_candidates]
            for i in range(0, len(cands), batch_size):
                batch = cands[i: i + batch_size]
                prompt = _build_prompt(batch)
                response = llm_client.complete(prompt)
                parsed = _parse_response(response)

                # Build title->norm mapping
                title_to_norm = {r.title: r.title_normalized for r in batch}
                batch_results = []
                confirmed_titles = set()
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title", "")
                    norm = title_to_norm.get(title)
                    if norm is None:
                        continue
                    confirmed = bool(item.get("confirmed_anomaly", False))
                    reason = item.get("reason", "")
                    batch_results.append({
                        "title_norm": norm,
                        "flag": confirmed,
                        "reason": reason,
                    })
                    confirmed_titles.add(norm)

                # Any LLM-batch titles not in parsed response default to no anomaly
                for rec in batch:
                    if rec.title_normalized not in confirmed_titles:
                        batch_results.append({
                            "title_norm": rec.title_normalized,
                            "flag": False,
                            "reason": "",
                        })

                db.save_m1_anomaly_batch(batch_results)
                logger.debug(
                    f"[M1] anomaly savepoint: +{len(batch_results)} titles persisted"
                )

    # Load all anomaly results from DB
    anomaly_data = db.load_m1_anomaly()

    # Update records in memory and collect canonical_terms
    canonical_batch: dict = {}
    for rec in records:
        data = anomaly_data.get(rec.title_normalized)
        if data:
            rec.anomaly_flag = data["flag"]
            rec.anomaly_reason = data["reason"]

        # Build canonical_terms from keywords via alias_to_canonical
        canonical_terms = []
        seen_canonicals = set()
        for kw in rec.keywords:
            canonical = alias_to_canonical.get(kw.lower(), kw)
            if canonical not in seen_canonicals:
                seen_canonicals.add(canonical)
                canonical_terms.append(canonical)
        rec.canonical_terms = canonical_terms
        if canonical_terms:
            canonical_batch[rec.title_normalized] = canonical_terms

    if canonical_batch:
        db.save_m1_canonical_batch(canonical_batch)

    # Build report
    flags = []
    for title_norm, data in anomaly_data.items():
        if data["flag"]:
            # Find original title
            title = title_norm
            for rec in records:
                if rec.title_normalized == title_norm:
                    title = rec.title
                    break
            flags.append({"title": title, "reason": data["reason"]})

    return {
        "total_checked": len(records),
        "heuristic_candidates": sum(
            1 for d in anomaly_data.values() if d["flag"]
        ),
        "llm_confirmed": len(flags),
        "flags": flags,
    }
