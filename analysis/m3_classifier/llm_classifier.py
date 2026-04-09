import json
import re
import textwrap


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
        self, records: list, llm_client, config: dict
    ) -> list:
        """Returns list of {title, research_type, application_domain, method}."""
        batch_size = config.get("llm", {}).get("batch_size", 50)
        results = []
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
                results.extend(parsed)
        return results
