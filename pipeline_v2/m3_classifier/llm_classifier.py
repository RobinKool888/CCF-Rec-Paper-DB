import json
import logging
import re
import textwrap

from core.pipeline_db import PipelineDB

logger = logging.getLogger(__name__)

_CLASSIFY_PROMPT = textwrap.dedent("""
You are a computer science research classifier specializing in networking and systems.

For each paper title below, assign:
1. research_type: one of [PURE_ALGORITHM, SYSTEM_DESIGN, MEASUREMENT_STUDY, SURVEY_OVERVIEW, APPLIED_ML]
2. application_domain: list of applicable domains from [Datacenter, Satellite_LEO, IoT_Sensor,
   Wireless_Cellular_5G6G, SDN_NFV, Security, General_Networking, Medical, Autonomous_Driving]

Return ONLY a JSON array. Each element must have:
  - "title": the paper title (verbatim)
  - "research_type": string (one of the above)
  - "application_domain": list of strings
  - "method": brief description (1 sentence)

Paper titles:
{titles}
""").strip()


def _build_prompt(batch: list) -> str:
    titles_str = "\n".join(f"- {r.title}" for r in batch)
    return _CLASSIFY_PROMPT.format(titles=titles_str)


def _parse_response(response: str, batch: list) -> list:
    text = response.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    valid_types = {
        "PURE_ALGORITHM", "SYSTEM_DESIGN", "MEASUREMENT_STUDY",
        "SURVEY_OVERVIEW", "APPLIED_ML",
    }
    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rt = item.get("research_type", "SYSTEM_DESIGN")
        if rt not in valid_types:
            rt = "SYSTEM_DESIGN"
        domains = item.get("application_domain", [])
        if not isinstance(domains, list) or not domains:
            domains = ["General_Networking"]
        results.append({
            "title": item.get("title", ""),
            "research_type": rt,
            "application_domain": domains,
            "method": item.get("method", ""),
        })
    return results


class LLMClassifier:
    def classify_batch(
        self,
        records: list,
        llm_client,
        config: dict,
        db: PipelineDB,
    ) -> list:
        """
        Resume logic:
        - Load already-done title_norms from db.m3_done_norms()
        - Build prompts only for records NOT already in DB
        - After parsing each batch: call db.save_m3_tags_batch(results)
        - Return full results by merging DB data with newly computed data
        """
        batch_size = config.get("llm", {}).get("batch_size", 20)

        done_norms = db.m3_done_norms()
        existing_tags = db.load_m3_tags()

        pending = [r for r in records if r.title_normalized not in done_norms]
        n_done = len(done_norms)
        n_pending = len(pending)
        logger.info(
            f"[M3] LLM classification: {n_done} titles already done, {n_pending} pending"
        )

        # Build results from already-persisted data
        results = []
        for title_norm, tag_data in existing_tags.items():
            # Find original title
            title = title_norm
            for rec in records:
                if rec.title_normalized == title_norm:
                    title = rec.title
                    break
            results.append({
                "title": title,
                "title_norm": title_norm,
                "research_type": tag_data["research_type"],
                "application_domain": tag_data["application_domain"],
            })

        if not pending:
            return results

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
                    f"[M3] classification: empty response for batch of {len(batch)} titles"
                )
                continue

            parsed = _parse_response(response, batch)
            if not parsed:
                logger.warning(
                    f"[M3] classification: JSON parse failed for batch of {len(batch)} titles"
                )
                continue

            results.extend(parsed)

            # Build DB save batch using title_norm
            title_to_norm = {r.title: r.title_normalized for r in batch}
            db_batch = []
            for item in parsed:
                title_norm = title_to_norm.get(item["title"])
                if title_norm:
                    db_batch.append({
                        "title_norm": title_norm,
                        "research_type": item["research_type"],
                        "application_domain": item["application_domain"],
                    })

            if db_batch:
                db.save_m3_tags_batch(db_batch)
                logger.debug(
                    f"[M3] classification savepoint: +{len(db_batch)} titles persisted"
                )

        return results
