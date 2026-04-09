# CCF Paper Domain Visualization & Analysis System

> **Pilot domain:** Computer Networks (CCF Category 2) — reads `paper_db/2/*.json` as **read-only** input; never re-downloads data.

---

## Test Results (latest)

| Module | Tests | Status |
|--------|-------|--------|
| M0 — Data Loader | 12 | ✅ Pass |
| M1 — LLM Analyzer | 6 | ✅ Pass |
| M2 — Term Stats | 4 | ✅ Pass |
| M3 — Classifier | 4 | ✅ Pass |
| M4 — Graph Builder | 4 | ✅ Pass |
| **Total** | **30** | **✅ 30 / 30** |

> Tests run zero real API calls — all LLM interactions use a `MockLLMClient` in sandbox mode.

CI badge (auto-updated on every push to `analysis/`):

![Sandbox Tests](https://github.com/RobinKool888/CCF-Rec-Paper-DB/actions/workflows/sandbox_tests.yml/badge.svg)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Quick Start](#3-quick-start)
4. [Configuration](#4-configuration)
5. [Module Reference](#5-module-reference)
6. [Running on GitHub Actions](#6-running-on-github-actions)
7. [Adding a New CCF Category](#7-adding-a-new-ccf-category)
8. [Directory Layout](#8-directory-layout)
9. [Development & Testing](#9-development--testing)
10. [FAQ](#10-faq)

---

## 1. Overview

Writing a high-quality survey paper requires efficiently identifying dominant research sub-directions, tracking terminology evolution, and detecting anomalous works. This pipeline automates all of this by combining the pre-crawled `paper_db/` title database with LLM-based semantic analysis and interactive visualizations.

**What it produces:**

| Output | File | Description |
|--------|------|-------------|
| Canonical vocabulary | `cache/term_map.json` | LLM-normalized technical terms with synonyms |
| Term frequency stats | `cache/term_freq.json` | Counts, trends, rank/venue breakdowns |
| Paper classifications | `cache/paper_tags.json` | Research type + application domain per paper |
| Anomaly report | `cache/anomaly_report.json` | Off-topic or malformed titles |
| Semantic graph | `viz/paper_graph.html` | Connected-Papers-style interactive HTML |
| Dashboard | Streamlit app | 6-tab interactive analysis interface |

---

## 2. Architecture

```
paper_db/2/*.json  +  paper_db/ccf_catalog.csv
         │
         ▼
 M0: Data Loader & Normalizer
   - Discovers all JSON files for category
   - Matches filenames to ccf_catalog.csv
   - Normalizes titles, deduplicates, flags workshops
   - Output: List[PaperRecord] + SQLite cache
         │
    ┌────┴──────────────┬─────────────────────┐
    ▼                   ▼                     ▼
 M1: LLM Analyzer   M2: Term Stats       M3: Classifier
   Keyword extract    Frequency counts     Heuristic rules
   Synonym merging    Trend slopes         + LLM fallback
   Anomaly detect     Wordcloud/charts     research_type
   → term_map.json    → term_freq.json     → paper_tags.json
    └────────────────────┴─────────────────────┘
                         │
                         ▼
                  M4: Graph Builder
                    Sentence embeddings (local)
                    FAISS ANN (large corpora)
                    Louvain communities
                    UMAP 2D layout → PyVis HTML
                         │
                         ▼
                  M5: Dashboard (Streamlit)
                    6 interactive tabs
```

**Execution order:** M1 / M2 / M3 can run in parallel after M0. M4 waits for all three. M5 is read-only.

---

## 3. Quick Start

### Prerequisites

```bash
# Python 3.12 recommended (3.10+ required)
pip install -r analysis/requirements_analysis.txt
```

### Step 1 — Load & normalize papers (no API key needed)

```bash
# From the repo root
python analysis/run.py --category 2 --rank A --module M0
```

This reads `paper_db/2/*.json`, normalizes all titles, and writes a SQLite cache.

### Step 2 — Compute term statistics (no API key needed)

```bash
python analysis/run.py --category 2 --rank A --module M2
```

Produces `analysis/cache/term_freq.json` and charts in `analysis/viz/`.

### Step 3 — Run full pipeline (requires LLM API key)

```bash
# Copy .env.example and fill in your key
cp .env.example .env
# e.g. OPENAI_API_KEY=sk-...

python analysis/run.py --category 2 --rank A --module ALL
```

### Step 4 — Launch the dashboard

```bash
streamlit run analysis/m5_dashboard/dashboard.py
# Opens at http://localhost:8501
```

---

## 4. Configuration

All tunable parameters live in `analysis/config.yaml`. The key sections:

```yaml
# Which category and domain description to inject into LLM prompts
domain:
  category: 2
  description: >
    Computer Networks (CCF Category 2): covers datacenter networking,
    wireless and mobile networks, IoT and sensor networks ...

# LLM provider — change provider/model without touching any Python code
llm:
  execution_mode: "local_api"   # "local_api" | "github_actions"
  provider: "openai"            # openai | anthropic | deepseek | ollama
  model: "gpt-4o-mini"
  api_key_env: "OPENAI_API_KEY"
  ollama_base_url: "http://localhost:11434"
  batch_size: 50
  rpm_limit: 500
```

### LLM Provider Options

| Provider | Model example | Cost | Notes |
|----------|--------------|------|-------|
| `openai` | `gpt-4o-mini` | Low | Recommended default |
| `anthropic` | `claude-haiku-3-5` | Low | Alternative |
| `deepseek` | `deepseek-chat` | Very low | Strong technical performance |
| `ollama` | `llama3.2` | Free | Fully local; requires Ollama running |

### Environment Variables

Create a `.env` file in the repo root (never committed):

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
```

---

## 5. Module Reference

### M0 — Data Loader & Normalizer

```bash
python analysis/run.py --category 2 --rank A/B/C --module M0
```

- Discovers all `paper_db/2/*.json` files
- Matches each file to `ccf_catalog.csv` (by abbreviation → full name → case-insensitive)
- Files not found in the catalog are loaded with `catalog_verified=False`
- Workshop/poster/demo sub-tracks detected via `sub_name_abbr` suffix patterns
- Outputs: `cache/papers_cat2.sqlite`, `cache/load_report_cat2.json`

### M1 — LLM Semantic Analyzer

```bash
python analysis/run.py --category 2 --rank A --module M1
```

- **Keyword extraction:** sends batches of 50 titles to LLM; extracts 2–5 technical terms each
- **Synonym merging:** top-2000 terms sent in a single pass for canonical vocabulary
- **Anomaly detection:** heuristic pre-screen (no LLM cost) → LLM confirmation for flagged titles only
- All LLM calls cached in `cache/llm_cache.sqlite`; re-runs with same prompts are free
- Outputs: `cache/term_map.json`, `cache/anomaly_report.json`

### M2 — Term Frequency Statistician

```bash
python analysis/run.py --category 2 --rank A/B/C --module M2
```

- Computes per-term: total count, paper fraction, breakdown by year/rank/venue, OLS trend slope
- Outputs: `cache/term_freq.json`, `viz/wordcloud_*.png`, `viz/top50_terms.html`, `viz/trend_heatmap.html`, `viz/term_trends.html`

### M3 — Application Background Classifier

```bash
python analysis/run.py --category 2 --rank A/B/C --module M3
```

- **Heuristic pass:** YAML rules in `config/heuristics/cat2_networks.yaml` handle ~40% of papers at zero cost
- **LLM pass:** remaining papers sent in batches for research_type + application_domain labels
- Labels: `PURE_ALGORITHM` / `SYSTEM_DESIGN` / `MEASUREMENT_STUDY` / `SURVEY_OVERVIEW` / `APPLIED_ML`
- Domains: `Datacenter` / `Wireless_Cellular_5G6G` / `IoT_Sensor` / `WAN_Backbone` / `CDN_Streaming` / `Satellite_LEO` / `Industrial_TSN` / `Vehicular_V2X` / `Security_Privacy` / `General_Networking`
- Output: `cache/paper_tags.json`

### M4 — Graph Builder

```bash
python analysis/run.py --category 2 --rank A/B/C --module M4
```

- Computes local sentence embeddings via `all-MiniLM-L6-v2` (no API cost)
- Edge score: `0.6 × cosine + 0.3 × Jaccard(terms) + 0.1 × venue-year bonus`
- Switches to FAISS ANN automatically for corpora > 20,000 papers
- Louvain community detection → cluster colors; UMAP → 2D layout
- Output: `cache/graph_data.json`, `viz/paper_graph.html`

### M5 — Dashboard

```bash
streamlit run analysis/m5_dashboard/dashboard.py
```

Six tabs — all controlled by shared sidebar (rank, year range, venue, track, anomalies):

| Tab | Contents |
|-----|---------|
| **Overview** | Papers by year, per-venue heatmap, rank/track distribution |
| **Terms** | Wordcloud, top-50 sortable table, trend lines, trend heatmap |
| **Classification** | Research type pie, app domain bar, Sankey flow chart, CSV export |
| **Graph** | Embedded interactive paper graph with year slider |
| **Anomalies** | Flagged papers with manual override (confirm / false positive) |
| **Survey Assist** | *(v1.1 placeholder)* Reading list + outline generator |

---

## 6. Running on GitHub Actions

### Sandbox tests (automatic)

The `sandbox_tests.yml` workflow runs on every push to `analysis/` — zero API keys needed.

```
GitHub → push to analysis/** → sandbox_tests.yml
  └── pytest analysis/tests/ -v
        └── 30 tests, ~35s, MockLLMClient (no real API calls)
```

### Full LLM pipeline (manual trigger)

1. Go to **Actions → LLM Analysis Pipeline → Run workflow**
2. Fill in parameters:
   - `category`: `2`
   - `rank`: `A` (or `A/B` or `A/B/C`)
   - `module`: `M1` / `M3` / `M1+M3` / `ALL`
3. Store your LLM API key as a GitHub Secret named `OPENAI_API_KEY`

The workflow:
- Downloads the prior LLM cache artifact (if any) to avoid re-paying for already-cached prompts
- Runs `analysis/run.py` with the chosen parameters
- Uploads the LLM cache + all result JSON files as downloadable artifacts (retained 30–90 days)

---

## 7. Adding a New CCF Category

Switching to any other CCF category requires **zero Python code changes**:

```bash
# 1. Create a heuristic file for the new domain (5–10 min)
cp analysis/config/heuristics/cat2_networks.yaml \
   analysis/config/heuristics/cat8_ai.yaml
# Edit patterns to match the AI domain

# 2. Update config.yaml
#    domain.category: 8
#    domain.description: "Artificial Intelligence (CCF Category 8): ..."
#    classifier.heuristics_file: "config/heuristics/cat8_ai.yaml"

# 3. Run the pipeline
python analysis/run.py --category 8 --rank A

# 4. Launch the dashboard
streamlit run analysis/m5_dashboard/dashboard.py -- --category 8
```

The `paper_db/8/` directory must already be populated by the existing `src/` crawler before running the analysis.

---

## 8. Directory Layout

```
analysis/
├── run.py                        # CLI entry point
├── config.yaml                   # Master configuration
├── requirements_analysis.txt     # Python dependencies
│
├── core/                         # Shared utilities
│   ├── data_model.py             # PaperRecord dataclass
│   ├── llm_client.py             # Multi-provider LLM + SQLite prompt cache
│   ├── cache_manager.py          # SQLite helpers + mtime-based invalidation
│   └── config_loader.py          # config.yaml reader
│
├── m0_loader/                    # Stage 0: load & normalize
├── m1_llm_analyzer/              # Stage 1: LLM keyword / synonym / anomaly
├── m2_term_stats/                # Stage 2: frequency stats + charts
├── m3_classifier/                # Stage 3: heuristic + LLM classification
├── m4_graph/                     # Stage 4: embedding graph
├── m5_dashboard/                 # Stage 5: Streamlit dashboard
│
├── config/
│   └── heuristics/
│       ├── cat2_networks.yaml    # Category 2 domain heuristics
│       └── cat8_ai.yaml          # Category 8 example
│
├── tests/
│   ├── conftest.py               # MockLLMClient + sandbox loader helpers
│   ├── test_m0.py  … test_m4.py  # 30 offline sandbox tests
│   ├── sandbox/                  # Miniature hand-crafted dataset
│   │   ├── paper_db/2/           # SIGCOMM, INFOCOM, TMC, CC + unverified files
│   │   ├── llm_fixtures/         # Pre-recorded LLM responses
│   │   └── expected_outputs/     # Reference outputs for assertions
│   └── tools/
│       └── record_fixtures.py    # One-time fixture recorder (needs real API key)
│
├── cache/          # Auto-generated; gitignored
├── viz/            # Auto-generated; gitignored
└── logs/           # Auto-generated; gitignored
```

---

## 9. Development & Testing

### Run all tests

```bash
# From repo root
pytest analysis/tests/ -v
```

Expected output:
```
analysis/tests/test_m0.py::test_total_records_nonzero          PASSED
analysis/tests/test_m0.py::test_catalog_verified_files_loaded  PASSED
... (30 total)
30 passed in ~35s
```

### Run a single module's tests

```bash
pytest analysis/tests/test_m0.py -v
pytest analysis/tests/test_m4.py -v
```

### Run with coverage

```bash
pytest analysis/tests/ -v --cov=analysis --cov-report=term-missing
```

### Recording LLM fixtures (one-time, needs real API key)

If you change M1 or M3 prompts significantly, regenerate the sandbox fixtures:

```bash
python analysis/tests/tools/record_fixtures.py \
  --sandbox-dir analysis/tests/sandbox \
  --output analysis/tests/sandbox/llm_fixtures/responses.json
```

Then commit the updated `responses.json`.

---

## 10. FAQ

**Q: Do I need an LLM API key to use this?**  
A: No, for M0 (data loading) and M2 (term statistics). M1, M3, and ALL require an API key. Use `--module M2` for a no-cost first pass. All tests also run without any API key.

**Q: Will this re-download paper data?**  
A: Never. The `analysis/` layer is strictly read-only with respect to `paper_db/`. All paper data was already crawled by `src/`.

**Q: How much does the full A+B+C pipeline cost with GPT-4o-mini?**  
A: Approximately 2,250 LLM calls for Category 2 (A+B+C). At GPT-4o-mini pricing, this is typically under $1. Subsequent runs with unchanged prompts are free (SQLite cache).

**Q: The dashboard says "no data — run the pipeline first". What do I do?**  
A: Run at minimum `python analysis/run.py --category 2 --rank A --module M0`. Some tabs (Terms, Graph) need M1/M2/M4 to have been run first.

**Q: How do I use a fully local LLM?**  
A: Install [Ollama](https://ollama.com), pull a model (`ollama pull llama3.2`), then set `config.yaml`:
```yaml
llm:
  provider: "ollama"
  model: "llama3.2"
  ollama_base_url: "http://localhost:11434"
```
No API key required.
