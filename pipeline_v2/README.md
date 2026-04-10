# pipeline_v2 — Venue-Scoped CCF Analysis Pipeline

A clean-slate reimplementation of the M0–M5 analysis pipeline, designed around two principles:

1. **Venue-scoped execution** — the minimum unit of work is one venue (e.g. `CoNEXT`). The pipeline loads, analyzes, and saves all results for one venue at a time.
2. **Per-title savepoints** — every LLM result is written to SQLite immediately after each batch is parsed. A crash loses at most one in-flight batch (~20 titles). On restart, already-processed titles are skipped with zero API calls and zero re-parsing.

---

## Quick Start

```bash
cd pipeline_v2
pip install -r requirements.txt
python run.py --venue CoNEXT
```

## Running Without an API Key (M0 + M2 + M4 only)

```bash
python run.py --venue CoNEXT --skip-llm
```

This runs M0 (data loading), M2 (term statistics), and M4 (graph building) without any LLM calls. No API key required.

## Dashboard

```bash
streamlit run m5_dashboard/dashboard.py -- --venue CoNEXT
```

The dashboard works even if only M0 has been run — it shows the load report and empty tabs with "run pipeline first" messages for stages not yet complete.

## Resume After Crash

Just re-run the same command:

```bash
python run.py --venue CoNEXT
```

Savepoints are automatic. Already-processed titles are loaded from `pipeline.sqlite` with zero API calls. The pipeline picks up exactly where it left off.

## Force Restart

To clear all savepoints for a venue and start from scratch:

```bash
python run.py --venue CoNEXT --force-restart
```

This deletes all rows from all tables in `pipeline.sqlite` but does **not** delete the file itself.

---

## Pipeline Stages

| Stage | Module | Description |
|-------|--------|-------------|
| M0 | `m0_loader/` | Load papers for a single venue from `paper_db/{category}/{venue}.json` |
| M1 | `m1_analyzer/` | LLM keyword extraction, synonym merge, anomaly detection |
| M2 | `m2_stats/` | Term frequency statistics + visualizations |
| M3 | `m3_classifier/` | Heuristic + LLM paper classification |
| M4 | `m4_graph/` | Sentence embeddings + similarity graph |
| M5 | `m5_dashboard/` | Streamlit dashboard |

---

## Savepoint Architecture

Each venue has its own SQLite file at `output/{venue}/pipeline.sqlite`. Tables:

| Table | Key | Content |
|-------|-----|---------|
| `m0_records` | `title_norm` | Full `PaperRecord` as JSON (all fields) |
| `m1_keywords` | `title_norm` | LLM-extracted keyword list per title |
| `m1_canonical` | `title_norm` | Canonical term list per title (after synonym merge) |
| `m1_anomaly` | `title_norm` | Anomaly flag + reason per title |
| `m1_term_map` | `venue` | Full synonym/term-map from LLM |
| `m3_tags` | `title_norm` | `research_type` + `application_domain` per title |
| `m4_embeddings` | `title_norm` | Sentence embedding vector per title |
| `stage_done` | `key` | Stage completion timestamps (M0–M4) |

The `llm_cache.sqlite` (LLM prompt-level cache, keyed by `sha256(model:prompt)`) is a **separate file** in the same directory. The two files serve different purposes and must coexist.

---

## Output Files

After a full pipeline run, `output/{venue}/` contains:

```
output/CoNEXT/
├── pipeline.sqlite          # All savepoint state
├── llm_cache.sqlite         # LLM prompt-level cache
├── run.log                  # Pipeline execution log
├── load_report.json         # M0 data load summary
├── term_map.json            # M1 synonym/term groups
├── anomaly_report.json      # M1 anomaly detection results
├── term_freq.json           # M2 term frequency statistics
├── paper_tags.json          # M3 paper classifications
├── graph_data.json          # M4 graph summary
└── viz/
    ├── paper_graph.html     # M4 interactive paper similarity graph
    ├── wordcloud_all.png    # M2 overall word cloud
    ├── wordcloud_A.png      # M2 rank-A word cloud
    ├── top50_terms.png      # M2 top-50 terms bar chart
    ├── heatmap.png          # M2 term frequency heatmap
    ├── trend_rising.png     # M2 rising terms chart
    ├── classification_research_type_pie.png
    ├── classification_domain_bar.png
    ├── classification_research_type_by_year.png
    └── classification_domain_by_rank.png
```

---

## Configuration

Edit `config.yaml` to customize:

- `paths.paper_db`: path to the `paper_db/` directory (relative to `pipeline_v2/`)
- `llm.model`: LLM model to use (default: `gpt-4o-mini`)
- `llm.batch_size`: titles per LLM batch (default: 20 for finer savepoints)
- `llm.api_key_env`: environment variable holding the API key
- `domain.category`: CCF category number (default: 2 = Computer Networks)

Set your API key before running:

```bash
export OPENAI_API_KEY="your-key-here"
```

Or create a `.env` file in the `pipeline_v2/` directory.

---

## Directory Structure

```
pipeline_v2/
├── README.md
├── config.yaml
├── run.py                           # CLI entry point
├── requirements.txt
├── core/
│   ├── data_model.py                # PaperRecord dataclass
│   ├── pipeline_db.py               # SQLite savepoint store
│   ├── llm_client.py                # LLM client with prompt-level cache
│   └── cache_manager.py             # SQLite key-value cache (used by llm_client)
├── m0_loader/
│   ├── loader.py                    # Venue-scoped loader
│   └── normalizer.py                # Title normalization utilities
├── m1_analyzer/
│   ├── keyword_extractor.py         # Per-title savepoint keyword extraction
│   ├── synonym_merger.py            # Per-venue savepoint synonym merge
│   └── anomaly_detector.py          # Per-title savepoint anomaly detection
├── m2_stats/
│   ├── statistician.py              # Term frequency computation
│   └── visualizer.py                # Chart generation
├── m3_classifier/
│   ├── heuristic_classifier.py      # Rule-based classifier
│   └── llm_classifier.py            # Per-title savepoint LLM classifier
├── m4_graph/
│   ├── embedder.py                  # Per-title savepoint sentence embeddings
│   ├── edge_builder.py              # Similarity edge construction
│   ├── clusterer.py                 # Graph clustering + layout
│   └── renderer.py                  # PyVis HTML graph renderer
├── m5_dashboard/
│   └── dashboard.py                 # Streamlit dashboard
└── config/
    └── heuristics/
        └── cat2_networks.yaml       # Classification heuristics
```
