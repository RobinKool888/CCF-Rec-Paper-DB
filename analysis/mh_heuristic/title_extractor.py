"""
title_extractor.py — N-gram keyword extraction from paper titles.

No LLM calls.  Produces a term_map (list of canonical-entry dicts) and
populates ``record.canonical_terms`` for every PaperRecord.
"""

import re
from collections import Counter
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Stop-word set — common English words + academic filler
# ---------------------------------------------------------------------------
_STOP = frozenset("""
a about above after again against all also although am an and any are as at
be because been before being below between both but by
can could did do does doing down during
each few for from further
get got had has have having he her here him his how
i if in into is it its itself
just let me more most my
new no nor not of off on once only or other our out over own
paper per same she since so some such
than that the their them then there these they this those through to too
under until up very was we were what when where which while who whom why will with
would you your
""".split())

# Tokens: at least 2 characters, letters/digits/hyphens
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-/]*[a-z0-9]|[a-z]{2,}")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def _keep(token: str) -> bool:
    if token in _STOP:
        return False
    if re.fullmatch(r"\d+", token):
        return False
    return True


def _make_ngrams(tokens: List[str], min_n: int, max_n: int) -> List[str]:
    """Return all valid n-grams (stop words may not appear at edges of bigrams+)."""
    result = []
    for n in range(min_n, max_n + 1):
        for i in range(len(tokens) - n + 1):
            gram_tokens = tokens[i : i + n]
            if n >= 2:
                # Skip if first or last token is a stop word
                if gram_tokens[0] in _STOP or gram_tokens[-1] in _STOP:
                    continue
            result.append(" ".join(gram_tokens))
    return result


def extract_keywords_from_titles(
    records: list, config: dict
) -> Tuple[list, dict]:
    """
    Extract n-gram keywords from paper titles without any LLM.

    Side-effect: populates ``record.canonical_terms`` on every record.

    Returns
    -------
    term_map : list of ``{"canonical": str, "abbreviation": "", "aliases": []}``
    alias_to_canonical : dict mapping lower-cased term -> canonical term
    """
    ngram_cfg = config.get("term_stats", {}).get("ngram_range", [1, 3])
    min_n, max_n = int(ngram_cfg[0]), int(ngram_cfg[1])

    global_counter: Counter = Counter()
    per_record_terms: List[List[str]] = []

    for rec in records:
        tokens = _tokenize(rec.title_normalized)
        kept_tokens = [t for t in tokens if _keep(t)]
        grams = _make_ngrams(kept_tokens, min_n, max_n)
        # Deduplicate per paper (count each term once per paper for IDF-style
        # counting later, but record the raw list for canonical_terms)
        seen: dict = {}
        for g in grams:
            if g not in seen:
                seen[g] = True
                global_counter[g] += 1
        per_record_terms.append(list(seen.keys()))

    # Build a simple identity term_map (no synonym merging without LLM)
    term_map = [
        {"canonical": term, "abbreviation": "", "aliases": []}
        for term in global_counter
    ]
    alias_to_canonical = {term: term for term in global_counter}

    # Assign canonical_terms to records
    for rec, terms in zip(records, per_record_terms):
        rec.canonical_terms = terms

    return term_map, alias_to_canonical
