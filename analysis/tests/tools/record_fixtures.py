"""
record_fixtures.py — Tool for recording real LLM responses into fixture files.

Usage:
    python analysis/tests/tools/record_fixtures.py \\
        --category 2 \\
        --output analysis/tests/sandbox/llm_fixtures/responses.json

This script runs the M1 pipeline with real API credentials and saves all LLM
responses keyed by sha256(model:prompt) into the fixture file. The fixture can
then be used by tests to replay responses without real API calls.
"""
import argparse
import hashlib
import json
import os
import sys

# Ensure analysis/ is importable
_tools_dir = os.path.dirname(os.path.abspath(__file__))
_tests_dir = os.path.dirname(_tools_dir)
_analysis_dir = os.path.dirname(_tests_dir)
if _analysis_dir not in sys.path:
    sys.path.insert(0, _analysis_dir)


def record_fixtures(category: int, output_path: str, config_path: str):
    from core.config_loader import load_config
    from core.llm_client import LLMClient
    from m0_loader.loader import load_papers
    from m1_llm_analyzer.keyword_extractor import batch_extract_keywords
    from m1_llm_analyzer.synonym_merger import merge_synonyms
    from m1_llm_analyzer.anomaly_detector import detect_anomalies
    from collections import Counter
    import pandas as pd

    config = load_config(config_path)

    # Intercept LLM calls
    recorded = {}

    class RecordingLLMClient(LLMClient):
        def _dispatch(self, prompt: str, temperature: float) -> str:
            result = super()._dispatch(prompt, temperature)
            key = self._cache_key(prompt)
            recorded[key] = result
            return result

    catalog_df = pd.read_csv(config["paths"]["ccf_catalog"], dtype=str)
    records, _ = load_papers(category, config, catalog_df)

    llm = RecordingLLMClient(config["llm"])
    kw_map = batch_extract_keywords(records, llm, config)
    for rec in records:
        rec.keywords = kw_map.get(rec.title_normalized, [])

    term_counts = Counter()
    for rec in records:
        for kw in rec.keywords:
            term_counts[kw] += 1
    term_map = merge_synonyms(dict(term_counts), llm, config)
    detect_anomalies(records, term_map, llm, config)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(recorded, fh, indent=2, ensure_ascii=False)
    print(f"Recorded {len(recorded)} LLM responses → {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", type=int, default=2)
    parser.add_argument(
        "--output",
        default=os.path.join(
            _tests_dir, "sandbox", "llm_fixtures", "responses.json"
        ),
    )
    parser.add_argument(
        "--config",
        default=os.path.join(_analysis_dir, "config.yaml"),
    )
    args = parser.parse_args()
    record_fixtures(args.category, args.output, args.config)
