import re
import yaml
from typing import Optional


class HeuristicClassifier:
    def __init__(self, heuristics_path: str, confidence_threshold: float = 0.85):
        with open(heuristics_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        self.confidence_threshold = confidence_threshold

        # Compile research_type patterns
        self._research_patterns = []
        for rtype, spec in raw.get("research_type_heuristics", {}).items():
            compiled = [re.compile(p, re.IGNORECASE) for p in spec.get("patterns", [])]
            self._research_patterns.append(
                (rtype, compiled, spec.get("confidence", 0.8))
            )

        # Compile application_domain patterns
        self._domain_patterns = []
        for domain, spec in raw.get("application_domain_heuristics", {}).items():
            compiled = [re.compile(p, re.IGNORECASE) for p in spec.get("patterns", [])]
            self._domain_patterns.append(
                (domain, compiled, spec.get("confidence", 0.8))
            )

    def classify(self, record) -> tuple:
        """
        Returns (research_type, app_domains, confidence) or (None, [], 0.0)
        if no heuristic fires above threshold.
        """
        title = record.title_normalized

        research_type = None
        rt_confidence = 0.0
        for rtype, patterns, conf in self._research_patterns:
            if any(p.search(title) for p in patterns):
                if conf >= self.confidence_threshold and conf > rt_confidence:
                    research_type = rtype
                    rt_confidence = conf

        app_domains = []
        for domain, patterns, conf in self._domain_patterns:
            if conf >= self.confidence_threshold:
                if any(p.search(title) for p in patterns):
                    app_domains.append(domain)

        if research_type is None and not app_domains:
            return None, [], 0.0

        return research_type, app_domains, max(rt_confidence, 0.0)
