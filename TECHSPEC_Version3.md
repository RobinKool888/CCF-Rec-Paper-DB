
# CCF Paper Domain Visualization & Analysis System
## Technical Specification Document

**Version:** 1.1.0  
**Date:** 2026-04-09  
**Pilot Domain:** Computer Networks (Category 2)  
**Repository:** RobinKool888/CCF-Rec-Paper-DB  
**Status:** Draft — Pre-Implementation

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Data Foundation & Existing Schema](#2-data-foundation--existing-schema)
3. [System Architecture](#3-system-architecture)
4. [Module Specifications](#4-module-specifications)
   - [M0: Data Loader & Normalizer](#m0-data-loader--normalizer)
   - [M1: LLM Semantic Analyzer](#m1-llm-semantic-analyzer)
   - [M2: Term Frequency Statistician](#m2-term-frequency-statistician)
   - [M3: Application Background Classifier](#m3-application-background-classifier)
   - [M4: Graph Builder](#m4-graph-builder)
   - [M5: Dashboard](#m5-dashboard)
5. [Cross-Cutting Concerns](#5-cross-cutting-concerns)
   - [LLM Client Abstraction & Execution Modes](#51-llm-client-abstraction--execution-modes)
   - [Caching & Persistence Layer](#52-caching--persistence-layer)
   - [Configuration Management](#53-configuration-management)
   - [Logging & Observability](#54-logging--observability)
6. [Module Validation Plans (Sandbox-Based)](#6-module-validation-plans-sandbox-based)
7. [Inter-Domain Portability Design](#7-inter-domain-portability-design)
8. [Directory Layout](#8-directory-layout)
9. [Dependency Manifest](#9-dependency-manifest)
10. [Development Roadmap](#10-development-roadmap)
11. [Open Questions & Future Extensions](#11-open-questions--future-extensions)

---

## 1. Project Overview

### 1.1 Motivation

Writing a high-quality survey paper requires a researcher to efficiently:

1. Identify dominant research sub-directions within a domain.
2. Track how terminology evolves over time.
3. Detect anomalous or off-topic works that may distort analysis.
4. Understand semantic connections between papers without reading every one.

This system automates all four tasks by combining the CCF-Rec-Paper-DB paper title database with LLM-based semantic analysis and interactive visualization. It is a **compass and radar** for the survey-writing process — not a replacement for careful reading.

### 1.2 Scope

**In scope (v1.0):**
- Operate on paper titles as the primary data source (no abstract or full-text required).
- Pilot on CCF Category 2 (Computer Networks), ranks A/B/C.
- Produce: canonical term vocabulary, frequency statistics, trend charts, semantic similarity graphs, application-background classification tags, and a Connected-Papers-style interactive graph.
- Export all artifacts as portable static files (HTML, JSON, PNG/SVG) that can be served without a backend.

**Out of scope (v1.0):**
- Real-time crawling (all data is pre-fetched via the existing `src/` pipeline).
- Full-text or abstract-level analysis.
- Author co-authorship networks.
- Cross-category comparative analysis.

### 1.3 Relationship to Existing Codebase

The existing `src/` directory (with `main.py`, `parse_html.py`, `utils.py`, `stat_info.py`) forms the **data acquisition layer** and is left entirely unchanged. This specification describes a new `analysis/` directory that consumes the already-crawled `paper_db/` data files as read-only inputs.

```
Existing layer (unchanged):     src/  →  paper_db/{category}/*.json
New layer (this spec):          analysis/  →  reads paper_db/, writes cache/ + viz/
```

### 1.4 Primary Users

| User | Use Case |
|------|----------|
| Survey paper authors | Identify sub-directions, representative works, and research gaps |
| New PhD students | Rapid field landscape overview |
| Research group leaders | Monitor field evolution year by year |

---

## 2. Data Foundation & Existing Schema

### 2.1 Source Files

All input data lives in `paper_db/{category_no}/{venue_name_or_abbr}.json`. The authoritative venue list for each category is `paper_db/ccf_catalog.csv`. For **Category 2 (Computer Networks)**, the complete venue inventory derived directly from the catalog is:

#### CCF-A

| Type | Venue | Full Name |
|------|-------|-----------|
| Journal | JSAC | IEEE Journal on Selected Areas in Communications |
| Journal | TMC | IEEE Transactions on Mobile Computing |
| Journal | TON | IEEE Transactions on Networking |
| Conference | SIGCOMM | ACM International Conference on Applications, Technologies, Architectures, and Protocols for Computer Communication |
| Conference | MobiCom | ACM International Conference on Mobile Computing and Networking |
| Conference | INFOCOM | IEEE International Conference on Computer Communications |
| Conference | NSDI | Symposium on Network System Design and Implementation |

#### CCF-B

| Type | Venue | Full Name |
|------|-------|-----------|
| Journal | TOIT | ACM Transactions on Internet Technology |
| Journal | TOMM | ACM Transactions on Multimedia Computing, Communications and Applications |
| Journal | TOSN | ACM Transactions on Sensor Networks |
| Journal | CN | Computer Networks |
| Journal | TCOM | IEEE Transactions on Communications |
| Journal | TWC | IEEE Transactions on Wireless Communications |
| Conference | SenSys | ACM Conference on Embedded Networked Sensor Systems |
| Conference | CoNEXT | ACM International Conference on Emerging Networking Experiments and Technologies |
| Conference | SECON | IEEE International Conference on Sensing, Communication, and Networking |
| Conference | IPSN | International Conference on Information Processing in Sensor Networks |
| Conference | MobiSys | ACM International Conference on Mobile Systems, Applications, and Services |
| Conference | ICNP | IEEE International Conference on Network Protocols |
| Conference | MobiHoc | International Symposium on Theory, Algorithmic Foundations, and Protocol Design for Mobile Networks |
| Conference | NOSSDAV | International Workshop on Network and Operating System Support for Digital Audio and Video |
| Conference | IWQoS | IEEE/ACM International Workshop on Quality of Service |
| Conference | IMC | ACM Internet Measurement Conference |

#### CCF-C

| Type | Venue | Full Name |
|------|-------|-----------|
| Journal | Ad Hoc Networks | Ad Hoc Networks |
| Journal | CC | Computer Communications |
| Journal | TNSM | IEEE Transactions on Network and Service Management |
| Journal | IET Communications | IET Communications |
| Journal | JNCA | Journal of Network and Computer Applications |
| Journal | MONET | Mobile Networks and Applications |
| Journal | Networks | Networks |
| Journal | PPNA | Peer-to-Peer Networking and Applications |
| Journal | WCMC | Wireless Communications and Mobile Computing |
| Journal | Wireless Networks | Wireless Networks |
| Journal | IOT | IEEE Internet of Things Journal |
| Journal | TIOT | ACM Transactions on Internet of Things |
| Conference | ANCS | ACM/IEEE Symposium on Architectures for Networking and Communication Systems |
| Conference | APNOMS | Asia-Pacific Network Operations and Management Symposium |
| Conference | FORTE | International Conference on Formal Techniques for Distributed Objects, Components, and Systems |
| Conference | LCN | IEEE Conference on Local Computer Networks |
| Conference | GLOBECOM | IEEE Global Communications Conference |
| Conference | ICC | IEEE International Conference on Communications |
| Conference | ICCCN | IEEE International Conference on Computer Communications and Networks |
| Conference | MASS | IEEE International Conference on Mobile Adhoc and Sensor Systems |
| Conference | P2P | IEEE International Conference on Peer-to-Peer Computing |
| Conference | IPCCC | IEEE International Performance Computing and Communications Conference |
| Conference | WoWMoM | IEEE International Symposium on a World of Wireless, Mobile and Multimedia Networks |
| Conference | ISCC | IEEE Symposium on Computers and Communications |
| Conference | WCNC | IEEE Wireless Communications and Networking Conference |
| Conference | Networking | IFIP International Conferences on Networking |
| Conference | IM | IFIP/IEEE International Symposium on Integrated Network Management |
| Conference | MSN | International Conference on Mobility, Sensing and Networking |
| Conference | MSWiM | International Conference on Modeling, Analysis and Simulation of Wireless and Mobile Systems |
| Conference | WASA | The International Conference on Wireless Artificial Intelligent Computing Systems and Applications |
| Conference | HotNets | ACM The Workshop on Hot Topics in Networks |
| Conference | APNet | Asia-Pacific Workshop on Networking |

> **Note on TOMM:** This venue appears in both Category 2 (CCF-B) and Category 7 (CCF-B) in `ccf_catalog.csv`. This is by design in the CCF catalog itself. When the loader operates on Category 2, TOMM is legitimately included. Its dual-category listing does not constitute an anomaly.

> **Note on additional files in `paper_db/2/`:** The directory may contain files corresponding to venues not listed in `ccf_catalog.csv` under `category=2` — for example, venues from a previous version of the CCF catalog in which the category boundaries differed. The M0 loader **does not reject such files**. Instead, it loads them as-is and attaches a `source: "catalog_unverified"` flag so the researcher can decide at the dashboard level whether to include them in analysis. This preserves the historical integrity of the crawled data.

### 2.2 Existing JSON Schema

Each venue JSON file is a list of annual records produced by the existing `src/parse_html.py`:

```json
[
  {
    "year": "2024",
    "name": "SIGCOMM 2024",
    "info": "Sydney, NSW, Australia",
    "venues": [
      {
        "sub_name_abbr": "conf/sigcomm/2024",
        "sub_name": "Proceedings of the ACM SIGCOMM 2024 Conference...",
        "count": 62,
        "papers": [
          "Crux: GPU-Efficient Communication Scheduling for Deep Learning Training.",
          "RDMA over Ethernet for Distributed Training at Meta Scale.",
          "..."
        ]
      },
      {
        "sub_name_abbr": "conf/sigcomm/2024pd",
        "sub_name": "Proceedings of the ACM SIGCOMM 2024 Conference: Posters and Demos...",
        "count": 45,
        "papers": ["..."]
      }
    ]
  }
]
```

### 2.3 Canonical Paper Record (Normalized Form)

M0 flattens every title from every JSON file into a `PaperRecord` — the universal data unit consumed by all downstream modules:

```python
@dataclass
class PaperRecord:
    # ── Identity ─────────────────────────────────────
    title: str                   # Raw title string, as crawled
    title_normalized: str        # Lowercase, trailing period stripped, whitespace collapsed

    # ── Provenance ───────────────────────────────────
    venue: str                   # Resolved venue identifier (e.g. "SIGCOMM")
    venue_full: str              # Full venue name from catalog
    year: int
    rank: str                    # "A" | "B" | "C" | "unknown"
    category: int                # CCF category number (e.g. 2)
    sub_venue: str               # sub_name_abbr (e.g. "conf/sigcomm/2024pd")
    is_main_track: bool          # True if main proceedings; False if workshop/poster/demo
    catalog_verified: bool       # True if venue found in ccf_catalog.csv for this category

    # ── Computed fields (populated by downstream modules) ──
    keywords: list[str]          # Extracted n-gram keywords          [M2]
    canonical_terms: list[str]   # LLM-normalized canonical terms     [M1]
    research_type: str           # See M3 taxonomy                    [M3]
    application_domain: list[str]# See M3 taxonomy                    [M3]
    anomaly_flag: bool           # True if suspected anomalous        [M1]
    anomaly_reason: str          # Explanation if flagged             [M1]
    embedding: list[float]       # Sentence embedding vector (384-d)  [M4]
```

### 2.4 Known Data Characteristics

The following characteristics are observed in `paper_db/2/` and are **handled gracefully** by M0 rather than treated as errors:

| Characteristic | Description | M0 Handling |
|---------------|-------------|-------------|
| Workshop / poster / demo sub-tracks | Conferences like SIGCOMM include workshops (e.g., `conf/sigcomm/2021foci`) and poster sessions (`conf/sigcomm/2024pd`) as separate `venues` entries within the same JSON file | Classified via `sub_name_abbr` suffix pattern; exposed as `is_main_track: bool` |
| Files from previous catalog versions | Some files in `paper_db/2/` may correspond to venues whose category assignment changed across CCF catalog versions | Loaded and flagged as `catalog_verified: false`; included in analysis by default, filterable in dashboard |
| Duplicate filenames differing only in case | e.g., `Ad Hoc Networks.json` and `Ad hoc Networks.json` | Normalized to lowercase for dedup; records merged |
| Trailing period in titles | DBLP includes sentence-ending periods in titles | Stripped in `title_normalized`; raw title preserved |
| `TOMM` appearing in both cat-2 and cat-7 JSON | Legitimate dual-category listing in the CCF catalog | Both files loaded when their respective categories are queried; no dedup across categories |

---

## 3. System Architecture

### 3.1 High-Level Data Flow

```
paper_db/2/*.json   +   paper_db/ccf_catalog.csv
          │
          ▼
┌─────────────────────────────────────────────┐
│  M0: Data Loader & Normalizer               │
│  Output: List[PaperRecord] + SQLite cache   │
└──────┬──────────────────────────────────────┘
       │ PaperRecord stream (shared by all modules)
       │
       ├──────────────────────────┬────────────────────────────┐
       ▼                          ▼                            ▼
┌──────────────┐        ┌──────────────────┐        ┌──────────────────────┐
│  M1: LLM     │        │  M2: Term Freq   │        │  M3: Background      │
│  Analyzer    │        │  Statistician    │        │  Classifier          │
│              │        │                  │        │                      │
│ term_map.json│        │ term_freq.json   │        │ paper_tags.json      │
│ anomaly_     │        │ viz/wordcloud    │        │ viz/sankey.html      │
│  report.json │        │ viz/heatmap.html │        │ viz/pie.html         │
└──────┬───────┘        └────────┬─────────┘        └──────────┬───────────┘
       │                         │                              │
       └─────────────────────────┴──────────────────────────────┘
                                 │ All module outputs
                                 ▼
                    ┌────────────────────────┐
                    │  M4: Graph Builder     │
                    │                        │
                    │  graph_data.json       │
                    │  viz/graph.html        │
                    └────────────┬───────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  M5: Dashboard         │
                    │  (Streamlit)           │
                    └────────────────────────┘
```

### 3.2 Execution Modes

| Mode | Command | Description |
|------|---------|-------------|
| Full pipeline | `python run.py --category 2 --rank A/B/C` | Run all modules end-to-end |
| Single module | `python run.py --module M2 --category 2` | Re-run one module using cached outputs from others |
| Interactive | `streamlit run m5_dashboard/dashboard.py` | Launch dashboard only; requires prior cached outputs |
| Sandbox test | `pytest analysis/tests/ -v` | Run all module tests against the fixed sandbox dataset |

### 3.3 Module Dependency Graph

```
M0
├─► M1   [needs: M0]
├─► M2   [needs: M0 ; optionally consumes M1.term_map for richer grouping]
├─► M3   [needs: M0 ; optionally consumes M1.term_map]
└─► M4   [needs: M0, M1, M2, M3]
         └─► M5  [reads outputs of M1–M4, writes nothing]
```

M1, M2, and M3 can run **in parallel** after M0 completes.  
M4 must wait for M1, M2, and M3.  
M5 is read-only and can launch at any time, showing partial results if some modules have not yet run.

---

## 4. Module Specifications

---

### M0: Data Loader & Normalizer

**Purpose:** Discover all JSON files for a given category, parse every paper title into a `PaperRecord`, handle known data characteristics gracefully, and persist the result to a SQLite cache for fast re-use by all downstream modules.

#### 4.0.1 Inputs

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `category` | `int` | — | CCF category number (e.g. `2`) |
| `rank_filter` | `str` | `"A/B/C"` | Pipe-separated rank selection |
| `year_range` | `tuple[int,int]` | `(2000, 2025)` | Inclusive year window |
| `include_workshops` | `bool` | `False` | Whether to include non-main-track sub-venues |
| `include_unverified` | `bool` | `True` | Whether to include files not in the current catalog |

#### 4.0.2 Processing Pipeline

```
Step 1 — File discovery
  Glob: paper_db/{category}/*.json
  For each file:
    Attempt to match filename to ccf_catalog.csv (category == given category)
    via: exact abbr match → exact name match → case-insensitive name match
    If matched: set catalog_verified=True, read rank from catalog
    If unmatched: set catalog_verified=False, rank="unknown"

Step 2 — Parse each file
  For each annual record → for each sub_venue entry → for each title string:
    Determine is_main_track:
      True  if sub_name_abbr matches pattern r'^conf/[a-z]+/\d{4}$'
                                           or r'^journals/[a-z]+/\d{4}'
      False if sub_name_abbr contains known workshop/poster suffixes:
              pd, p, w, nai, foci, netai, optsys, spin, fira,
              flexnets, taurin, visnext, net4us, ffspin, ...
    Build PaperRecord with all provenance fields

Step 3 — Title normalization
  title_normalized = title.lower()
                          .rstrip('.')
                          .strip()
                          re.sub(r'\s+', ' ', ...)

Step 4 — Within-file deduplication
  Group by (title_normalized, venue, year)
  On collision: keep first occurrence, log warning

Step 5 — File-level deduplication
  Normalize JSON filenames to lowercase before loading
  If two filenames normalize identically, load only one and log warning

Step 6 — Persist to SQLite
  Table: papers(id, title, title_normalized, venue, venue_full, year,
                rank, category, sub_venue, is_main_track, catalog_verified)
  Indexed on: (category, year, rank, venue, is_main_track)
  Cache is invalidated when any source JSON mtime changes
```

#### 4.0.3 Outputs

| Output | Format | Description |
|--------|--------|-------------|
| `List[PaperRecord]` | In-memory | Primary output consumed by M1–M4 |
| `cache/papers_cat{N}.sqlite` | SQLite | Persistent cache; skips re-parsing on subsequent runs |
| `cache/load_report_cat{N}.json` | JSON | Statistics: total records, per-venue counts, unverified files, dedup counts |

#### 4.0.4 Load Report Schema

```json
{
  "category": 2,
  "total_records": 98432,
  "main_track_records": 67201,
  "workshop_records": 31231,
  "catalog_verified_venues": 33,
  "catalog_unverified_venues": 2,
  "unverified_venue_names": ["Computational Complexity", "International Conference on Compiler Construction"],
  "dedup_collisions": 14,
  "year_range_actual": [1991, 2025]
}
```

---

### M1: LLM Semantic Analyzer

**Purpose:** Use an LLM to extract technical terms from paper titles, merge synonyms into a canonical vocabulary, and flag titles that appear semantically anomalous relative to the declared domain.

#### 4.1.1 Inputs

- `List[PaperRecord]` from M0
- `domain_context`: injected from config (e.g. `"Computer Networks (CCF Category 2): areas include datacenter networking, wireless & mobile, IoT, network measurement, congestion control, SDN/NFV, 5G/6G, satellite networks, and network security protocols."`)

#### 4.1.2 Sub-Task A — Keyword Extraction (Batched)

Titles are sent to the LLM in batches of 50.

```
PROMPT TEMPLATE — Keyword Extraction
═══════════════════════════════════════════════════════════════════
System: You are a computer science expert in {domain_context}.

User:
For each of the following {N} paper titles, extract 2–5 key technical
terms. A valid term is a method name, protocol name, system component,
architectural concept, or domain-specific noun phrase (1–3 words).
Exclude generic adjectives (e.g. "efficient", "novel", "scalable",
"improved") and generic nouns (e.g. "approach", "method", "framework",
"system") unless they form part of a proper technical name.

Return a JSON array with exactly {N} objects:
[
  {"idx": 0, "terms": ["congestion control", "RDMA", "datacenter network"]},
  {"idx": 1, "terms": ["LEO satellite", "traffic engineering"]},
  ...
]

Titles:
0. {title_0}
1. {title_1}
...
═══════════════════════════════════════════════════════════════════
```

#### 4.1.3 Sub-Task B — Synonym Merging

After collecting all raw terms, the top-N (configurable, default 2000) most frequent terms are sent in a single pass for synonym resolution.

```
PROMPT TEMPLATE — Synonym Merging
═══════════════════════════════════════════════════════════════════
System: You are a {domain_context} terminology expert.

User:
Below is a ranked list of technical terms extracted from CCF paper
titles. Group synonymous or near-synonymous terms under a single
canonical form. Apply the following rules:

1. The canonical form should be the most widely used standard name
   in academic literature.
2. Abbreviations and their expansions are synonyms
   (e.g., "SDN" ↔ "software-defined networking").
3. Do NOT merge terms that differ in specificity
   ("congestion control" and "TCP congestion control" are related
   but NOT synonyms).
4. Vendor-specific names are NOT synonyms of the general concept
   unless they are universally understood as such.

Return a JSON array:
[
  {
    "canonical": "Software-Defined Networking",
    "abbreviation": "SDN",
    "aliases": ["software defined networking", "software-defined network",
                "SDN-based networking"],
    "related_narrower": ["OpenFlow", "NFV", "network virtualization"]
  },
  ...
]

Terms:
{term_list}
═══════════════════════════════════════════════════════════════════
```

**Output:** `cache/term_map.json` — the canonical vocabulary file shared by M2 and M4.

#### 4.1.4 Sub-Task C — Anomaly Detection

Anomaly detection operates on a **two-stage pipeline**:

**Stage 1 — Heuristic pre-screen (no LLM cost):**

```python
def heuristic_anomaly_check(record: PaperRecord, domain_keywords: set[str]) -> tuple[bool, str]:
    t = record.title_normalized
    # Signal 1: title has no domain-relevant keyword whatsoever
    if not any(kw in t for kw in domain_keywords):
        return True, "no_domain_keyword"
    # Signal 2: non-English title
    if langdetect.detect(t) != 'en':
        return True, "non_english"
    # Signal 3: suspiciously short and generic
    if len(t.split()) <= 3:
        return True, "too_short"
    return False, None
```

**Stage 2 — LLM confirmation for heuristic-flagged titles:**

Only titles flagged in Stage 1 are sent to the LLM, minimizing cost.

```
PROMPT TEMPLATE — Anomaly Confirmation
═══════════════════════════════════════════════════════════════════
Domain: {domain_context}
Venue: {venue} ({rank}-rank, Category 2)

The following paper title was heuristically flagged as potentially
anomalous for this domain. Confirm or dismiss the flag.

Title: "{title}"
Heuristic signal: {signal}

Respond with JSON:
{
  "confirmed_anomaly": true | false,
  "issue_type": null | "domain_mismatch" | "non_technical" | "malformed",
  "confidence": 0.0–1.0,
  "reason": "one sentence explanation"
}
═══════════════════════════════════════════════════════════════════
```

**Output:** `cache/anomaly_report.json`

```json
{
  "total_screened": 98432,
  "heuristic_flagged": 312,
  "llm_confirmed_anomalies": 47,
  "flags": [
    {
      "title": "...",
      "venue": "GLOBECOM",
      "year": 2019,
      "rank": "C",
      "catalog_verified": true,
      "issue_type": "domain_mismatch",
      "confidence": 0.88,
      "reason": "Title describes a pure graph-theoretic algorithm with no networking context.",
      "user_override": null
    }
  ]
}
```

#### 4.1.5 LLM Call Budget Estimates

| Scope | Papers | Keyword Batches | Synonym Pass | Anomaly Confirmations | Total Calls (approx.) |
|-------|--------|----------------|--------------|----------------------|----------------------|
| A-rank only | ~10,000 | 200 | 1 | ~30 | ~231 |
| A+B rank | ~30,000 | 600 | 1 | ~80 | ~681 |
| A+B+C rank | ~100,000 | 2,000 | 2 | ~250 | ~2,252 |

All responses are cached in `cache/llm_cache.sqlite` keyed by `sha256(model + ":" + prompt)`. Re-runs with unchanged prompts incur **zero additional API cost**.

---

### M2: Term Frequency Statistician

**Purpose:** Compute multi-dimensional frequency statistics for all canonical terms and produce publication-ready visualizations.

#### 4.2.1 Inputs

- `List[PaperRecord]` (with `canonical_terms` populated by M1)
- `cache/term_map.json`
- Runtime filters: `rank_filter`, `year_range`, `venue_filter`, `main_track_only`

#### 4.2.2 Statistics Schema

```python
# For each canonical term t:
TermStats = {
    "canonical": str,
    "total_count": int,
    "paper_fraction": float,      # count / total_papers_in_scope
    "by_year": dict[int, int],    # {2015: 3, 2016: 7, ...}
    "by_rank": dict[str, int],    # {"A": 45, "B": 120, "C": 200}
    "by_venue": dict[str, int],   # {"SIGCOMM": 30, "INFOCOM": 50, ...}
    "trend_slope": float,         # OLS slope over the last 5 years
    "trend_direction": str,       # "rising" | "falling" | "stable"
    "peak_year": int,
    "first_seen": int,
    "last_seen": int,
}
```

#### 4.2.3 Visualization Outputs

| File | Type | Description |
|------|------|-------------|
| `viz/wordcloud_A.png` | PNG | Wordcloud for CCF-A papers; font size ∝ frequency |
| `viz/wordcloud_ABC.png` | PNG | Wordcloud for all ranks combined |
| `viz/top50_terms.html` | Plotly HTML | Horizontal bar chart, top 50 terms; filterable by rank |
| `viz/trend_heatmap.html` | Plotly HTML | Year (x-axis) × term (y-axis) heatmap; color = count |
| `viz/term_trends.html` | Plotly HTML | Multi-line trend chart; user selects terms to overlay |

#### 4.2.4 Output Files

| File | Format | Contents |
|------|--------|----------|
| `cache/term_freq.json` | JSON | Full `TermStats` dict keyed by canonical term |
| `viz/wordcloud_*.png` | PNG | Per-rank wordclouds |
| `viz/trend_heatmap.html` | HTML | Interactive trend heatmap |
| `viz/top50_terms.html` | HTML | Interactive bar chart |
| `viz/term_trends.html` | HTML | Interactive multi-term trend lines |

---

### M3: Application Background Classifier

**Purpose:** Assign each paper two structured labels — research type and application domain — enabling systematic filtering and cross-cutting analysis in the dashboard.

#### 4.3.1 Label Taxonomy

**Research Type** (mutually exclusive, single label per paper):

| Label | Description | Typical Title Signal |
|-------|-------------|---------------------|
| `PURE_ALGORITHM` | Theoretical or algorithmic contribution with no specific deployment domain | "Optimal scheduling under adversarial arrival" |
| `SYSTEM_DESIGN` | A concrete system, architecture, or protocol is proposed and evaluated | "Crux: GPU-Efficient Communication Scheduling for Deep Learning Training" |
| `MEASUREMENT_STUDY` | Primarily empirical observation of existing systems; no new design | "Vivisecting mobility management in 5G cellular networks" |
| `SURVEY_OVERVIEW` | Explicit survey, tutorial, or overview paper | "A Survey on..." / "An Overview of..." |
| `APPLIED_ML` | Machine learning applied as the primary technical contribution to a networking problem | "NetLLM: Adapting Large Language Models for Networking" |

**Application Domain** (multi-label, one or more per paper):

`Datacenter` / `Wireless_Cellular_5G6G` / `IoT_Sensor` / `WAN_Backbone` / `CDN_Streaming` / `Satellite_LEO` / `Industrial_TSN` / `Vehicular_V2X` / `Security_Privacy` / `General_Networking` / `Unknown`

#### 4.3.2 Two-Stage Classification

**Stage 1 — Heuristic pre-classification** (zero LLM cost; handles ~40% of papers):

Domain-specific heuristic rules are stored in `config/heuristics/cat2_networks.yaml` (see §7.2). A paper is classified by heuristic if any pattern fires with confidence above the configured threshold.

**Stage 2 — LLM classification** for papers not resolved by heuristics:

```
PROMPT TEMPLATE — Classification
═══════════════════════════════════════════════════════════════════
Domain: {domain_context}

Classify each of the following {N} paper titles on two axes:

1. research_type: exactly one of
   [PURE_ALGORITHM, SYSTEM_DESIGN, MEASUREMENT_STUDY,
    SURVEY_OVERVIEW, APPLIED_ML]

2. application_domain: one or more of
   [Datacenter, Wireless_Cellular_5G6G, IoT_Sensor, WAN_Backbone,
    CDN_Streaming, Satellite_LEO, Industrial_TSN, Vehicular_V2X,
    Security_Privacy, General_Networking]
   Use General_Networking if no specific application domain is apparent.

Return a JSON array with exactly {N} objects:
[
  {
    "idx": 0,
    "research_type": "SYSTEM_DESIGN",
    "application_domain": ["Datacenter"]
  },
  ...
]

Titles:
0. {title_0}
...
═══════════════════════════════════════════════════════════════════
```

#### 4.3.3 Outputs

| File | Format | Contents |
|------|--------|----------|
| `cache/paper_tags.json` | JSON | Per-paper classification results with confidence and method (heuristic vs. LLM) |
| `viz/research_type_pie.html` | HTML | Research type distribution pie chart |
| `viz/app_domain_bar.html` | HTML | Application domain distribution bar chart |
| `viz/sankey_type_domain.html` | HTML | Sankey diagram: research_type → application_domain flow |

---

### M4: Graph Builder

**Purpose:** Construct a semantic paper-to-paper or term-to-term similarity graph and render it as a navigable interactive visualization.

#### 4.4.1 Graph Modes

| Mode | Node = | Recommended for |
|------|--------|----------------|
| `PAPER_GRAPH` | Individual paper | Deep exploration of a focused sub-topic |
| `TERM_GRAPH` | Canonical term | Full-field landscape overview, survey skeleton generation |

#### 4.4.2 Embedding Strategy

Paper title embeddings are computed **entirely locally** using `sentence-transformers`:

```python
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")  # 22M params, 384-dim output
titles = [r.title_normalized for r in records]
embeddings = model.encode(titles, batch_size=256, show_progress_bar=True,
                           normalize_embeddings=True)
# Shape: (N_papers, 384), L2-normalized for cosine similarity via dot product
np.save("cache/embeddings_cat2.npy", embeddings)
```

No API calls are required for this step.

#### 4.4.3 Edge Construction

**PAPER_GRAPH edges:**

```
For each pair (i, j):
  score = w_sem  * dot(embed_i, embed_j)           # semantic similarity
        + w_term * jaccard(canonical_terms_i, canonical_terms_j)  # term overlap
        + w_meta * same_venue_year_bonus(i, j)      # venue/year proximity

  default weights: w_sem=0.6, w_term=0.3, w_meta=0.1

Add edge (i, j) if score > similarity_threshold (default: 0.45)
```

For corpora > 20,000 papers, switch to Approximate Nearest Neighbors (ANN) via `faiss` to avoid O(N²) computation:

```python
import faiss
index = faiss.IndexFlatIP(384)          # inner product on normalized vectors = cosine
index.add(embeddings)
distances, neighbors = index.search(embeddings, k=20)   # top-20 per paper
```

**TERM_GRAPH edges:**

Edge weight between terms `t_i` and `t_j` = Pointwise Mutual Information (PMI) of co-occurrence within the same paper title across the full corpus.

#### 4.4.4 Graph Construction & Layout

```
1. Build NetworkX graph from edges above threshold
2. Louvain community detection → assign cluster_id to each node
3. UMAP dimensionality reduction: embeddings → 2D coordinates
   (n_components=2, n_neighbors=15, min_dist=0.1)
4. PyVis rendering:
   - Node size    ∝ degree (number of neighbors above threshold)
   - Node color   = cluster_id (mapped to qualitative color palette)
   - Edge opacity ∝ edge score
   - Node tooltip = full title / canonical term + venue + year + rank
                    + research_type + application_domain
   - On click     = highlight 1-hop neighborhood + show detail panel
```

#### 4.4.5 Temporal Slider Feature

The graph HTML includes a year-range slider that dynamically shows/hides nodes based on publication year, allowing the user to observe how the field's topology evolves over time.

#### 4.4.6 Outputs

| File | Format | Contents |
|------|--------|----------|
| `cache/graph_data.json` | JSON | Raw node list + edge list with all attributes |
| `viz/graph_paper.html` | HTML | Self-contained interactive paper graph (~5–10 MB) |
| `viz/graph_term.html` | HTML | Self-contained interactive term graph |

---

### M5: Dashboard

**Purpose:** Integrate all module outputs into a single Streamlit web application for survey-writing support.

#### 4.5.1 Technology

**Streamlit** — chosen for rapid development, zero-JavaScript requirement, and straightforward deployment to Hugging Face Spaces or GitHub Pages (via `stlite`).

#### 4.5.2 Sidebar Controls

```
┌─────────────────────────────────────────┐
│  SIDEBAR                                │
│  Category:    [2 — Computer Networks]   │
│  Rank:        [A] [A+B] [A+B+C]        │
│  Year Range:  ════════════════          │
│               2000              2025    │
│  Venue:       [All ▼]                   │
│  Track:       [Main only] [All]         │
│  Unverified:  [Include] [Exclude]       │
│  Anomalies:   [Show all] [Hide flagged] │
└─────────────────────────────────────────┘
```

All sidebar controls propagate to **all tabs simultaneously**.

#### 4.5.3 Tab Descriptions

**Tab 1 — Overview**
- Total papers by year (bar chart)
- Papers per venue per year (heatmap)
- Rank distribution (pie)
- Main track vs. workshop split (stacked bar)
- Catalog-verified vs. unverified papers count

**Tab 2 — Terms**
- Wordcloud (filtered by current sidebar state)
- Top-50 terms sortable table (term, count, rank breakdown, trend direction)
- Trend chart: user selects multiple terms → co-evolution line chart
- Trend heatmap: year × term × count

**Tab 3 — Classification**
- Research type pie chart
- Application domain bar chart
- Sankey: research_type → application_domain
- Filterable paper table with all tags; CSV export button

**Tab 4 — Graph**
- `st.components.v1.html()` embedding of `viz/graph_paper.html` or `viz/graph_term.html`
- Toggle: Paper Graph / Term Graph
- Year range slider (duplicated here for graph-specific use)
- Community legend

**Tab 5 — Anomalies**
- Sortable table: flagged papers with venue, year, issue_type, confidence, reason
- Manual override per row: "Confirm anomaly" / "Mark as false positive"
- Overrides written to `cache/anomaly_overrides.json`
- Export flagged list as CSV

**Tab 6 — Survey Assist** *(v1.1 placeholder)*
- Input: free-text research focus description
- Output: ranked reading list + suggested survey outline skeleton

---

## 5. Cross-Cutting Concerns

### 5.1 LLM Client Abstraction & Execution Modes

The system supports **two orthogonal dimensions** of flexibility: provider choice and execution environment. Both are controlled entirely by `config.yaml`.

#### Dimension 1 — Provider

| Provider | Use Case | Key |
|----------|----------|-----|
| `openai` | General use; GPT-4o-mini is recommended for cost/quality | `OPENAI_API_KEY` |
| `anthropic` | Alternative; Claude Haiku for cost-sensitive runs | `ANTHROPIC_API_KEY` |
| `deepseek` | Cost-optimized alternative with strong technical performance | `DEEPSEEK_API_KEY` |
| `ollama` | Fully local, zero cost; requires Ollama server running locally | No key; `ollama_base_url` |

#### Dimension 2 — Execution Environment

##### Mode A: Local API

The researcher runs the pipeline directly on their own machine. API keys are read from local environment variables (`.env` file via `python-dotenv`).

```
Researcher laptop
  └── python analysis/run.py --module M1 --category 2 --rank A
        └── LLMClient
              ├── reads .env for API key
              ├── checks cache/llm_cache.sqlite
              └── HTTPS → LLM provider API (or local Ollama)
```

```yaml
# config.yaml — Mode A
llm:
  execution_mode: "local_api"
  provider: "openai"
  model: "gpt-4o-mini"
  api_key_env: "OPENAI_API_KEY"
  ollama_base_url: "http://localhost:11434"
  batch_size: 50
  max_concurrent: 5
  rpm_limit: 500
```

**When to prefer this mode:**
- Active prompt development and iteration
- Small-scale runs (A-rank only, ~230 total calls)
- Using a fully local Ollama model

##### Mode B: GitHub Actions Cloud Execution

The pipeline runs as a GitHub Actions workflow. API keys are stored as GitHub repository Secrets and never appear in any committed file.

```
GitHub Actions runner (ubuntu-latest)
  └── python analysis/run.py --module M1 --category 2 --rank A/B/C
        └── LLMClient
              ├── reads OPENAI_API_KEY from GitHub Secret (env var)
              ├── downloads llm_cache artifact from prior run (if exists)
              └── HTTPS → LLM provider API
                    └── uploads cache + results as workflow artifacts
```

```yaml
# config.yaml — Mode B (safe to commit; no secrets)
llm:
  execution_mode: "github_actions"
  provider: "openai"
  model: "gpt-4o-mini"
  api_key_env: "OPENAI_API_KEY"
  batch_size: 50
  max_concurrent: 3      # conservative for shared runner
  rpm_limit: 300
```

```yaml
# .github/workflows/llm_analysis.yml
name: LLM Analysis Pipeline

on:
  workflow_dispatch:
    inputs:
      category:
        description: 'CCF category number (1–10)'
        required: true
        default: '2'
      rank:
        description: "Rank filter — e.g. 'A' or 'A/B' or 'A/B/C'"
        required: true
        default: 'A'
      module:
        description: 'Module to run: M1 | M3 | M1+M3 | ALL'
        required: true
        default: 'M1'

jobs:
  run_analysis:
    runs-on: ubuntu-latest
    steps:

      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Cache pip packages
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ hashFiles('analysis/requirements_analysis.txt') }}

      - name: Install dependencies
        run: pip install -r analysis/requirements_analysis.txt

      - name: Download prior LLM cache (if exists)
        uses: actions/download-artifact@v4
        continue-on-error: true   # first run: no prior cache exists yet
        with:
          name: llm-cache-cat${{ github.event.inputs.category }}
          path: analysis/cache/

      - name: Run analysis module
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          python analysis/run.py \
            --module ${{ github.event.inputs.module }} \
            --category ${{ github.event.inputs.category }} \
            --rank "${{ github.event.inputs.rank }}"

      - name: Upload LLM cache artifact
        uses: actions/upload-artifact@v4
        with:
          name: llm-cache-cat${{ github.event.inputs.category }}
          path: analysis/cache/llm_cache.sqlite
          retention-days: 90

      - name: Upload analysis results
        uses: actions/upload-artifact@v4
        with:
          name: analysis-results-cat${{ github.event.inputs.category }}
          path: |
            analysis/cache/term_map.json
            analysis/cache/term_freq.json
            analysis/cache/paper_tags.json
            analysis/cache/anomaly_report.json
            analysis/cache/graph_data.json
            analysis/cache/load_report_cat${{ github.event.inputs.category }}.json
          retention-days: 30
```

**Key properties of Mode B:**
- API keys are stored only in GitHub Secrets; never in any file in the repository
- The `llm_cache.sqlite` is uploaded as a persistent artifact; subsequent workflow runs download it first, so cache hits remain free
- The `workflow_dispatch` trigger allows manual invocation with configurable parameters from the GitHub Actions UI — no local CLI required
- All result JSON files are available as downloadable artifacts, which can be placed into `analysis/cache/` locally to run the dashboard without re-computing anything

#### LLMClient Implementation

```python
# analysis/core/llm_client.py

import os, json, hashlib, sqlite3, time
from typing import Optional

class LLMClient:
    """
    Unified LLM interface.
    - Supports: openai, anthropic, deepseek, ollama
    - All calls are transparently cached in cache/llm_cache.sqlite
    - In sandbox/test mode, a pre-recorded fixture replaces all real calls
    """

    def __init__(self, config: dict, fixture_path: Optional[str] = None):
        self.mode = config["llm"]["execution_mode"]
        self.provider = config["llm"]["provider"]
        self.model = config["llm"]["model"]
        self.api_key = os.environ.get(config["llm"]["api_key_env"], "")
        self.ollama_url = config["llm"].get("ollama_base_url", "http://localhost:11434")
        self._db = CacheDB("analysis/cache/llm_cache.sqlite")
        self._fixture: Optional[dict] = None
        if fixture_path:
            with open(fixture_path) as f:
                self._fixture = json.load(f)

    def complete(self, prompt: str, temperature: float = 0.1) -> str:
        key = hashlib.sha256(f"{self.model}:{prompt}".encode()).hexdigest()

        # Sandbox mode: must be in fixture
        if self._fixture is not None:
            if key not in self._fixture:
                raise SandboxFixtureMissError(
                    f"Prompt hash {key[:12]}… not in fixture.\n"
                    f"Run: python tests/tools/record_fixtures.py to update.\n"
                    f"Prompt preview: {prompt[:120]}"
                )
            return self._fixture[key]

        # Production mode: check persistent cache first
        cached = self._db.get(key)
        if cached:
            return cached

        response = self._dispatch(prompt, temperature)
        self._db.set(key, response)
        return response

    def complete_batch(self, prompts: list[str], **kwargs) -> list[str]:
        """Rate-limit-aware parallel execution."""
        ...

    def _dispatch(self, prompt: str, temperature: float) -> str:
        if self.provider == "openai":
            return self._call_openai(prompt, temperature)
        elif self.provider == "anthropic":
            return self._call_anthropic(prompt, temperature)
        elif self.provider == "deepseek":
            return self._call_deepseek(prompt, temperature)
        elif self.provider == "ollama":
            return self._call_ollama(prompt, temperature)
        raise ValueError(f"Unknown LLM provider: {self.provider}")
```

---

### 5.2 Caching & Persistence Layer

```
analysis/cache/                         ← gitignored
├── papers_cat{N}.sqlite                M0 output: normalized PaperRecords
├── llm_cache.sqlite                    LLM prompt→response; content-addressed; never invalidated
├── embeddings_cat{N}.npy               Sentence embeddings; invalidated when papers DB changes
├── term_map.json                       M1 output: canonical vocabulary
├── term_freq.json                      M2 output: per-term statistics
├── paper_tags.json                     M3 output: per-paper classification labels
├── anomaly_report.json                 M1 output: flagged papers
├── anomaly_overrides.json              M5 output: user manual overrides
├── graph_data.json                     M4 output: graph nodes + edges
└── load_report_cat{N}.json             M0 output: loading statistics
```

**Cache invalidation policy:**

| Cache file | Invalidated when |
|-----------|-----------------|
| `papers_cat{N}.sqlite` | Any `paper_db/{N}/*.json` file mtime changes |
| `llm_cache.sqlite` | **Never** (content-addressed; prompt changes produce new keys automatically) |
| `embeddings_cat{N}.npy` | `papers_cat{N}.sqlite` is invalidated |
| `term_map.json`, `term_freq.json`, `paper_tags.json`, `anomaly_report.json`, `graph_data.json` | Corresponding upstream input changes; or `--force-recompute M{N}` flag passed |

---

### 5.3 Configuration Management

A single `analysis/config.yaml` governs all tunable parameters:

```yaml
# analysis/config.yaml

# ── Paths ──────────────────────────────────────────────────────────
paths:
  paper_db: "../paper_db"
  ccf_catalog: "../paper_db/ccf_catalog.csv"
  cache_dir: "cache"
  viz_dir: "viz"
  log_dir: "logs"

# ── Loader (M0) ────────────────────────────────────────────────────
loader:
  include_workshops: false
  include_unverified: true          # include catalog_verified=False files
  min_year: 2000
  max_year: 2025

# ── LLM (M1, M3) ──────────────────────────────────────────────────
llm:
  execution_mode: "local_api"       # "local_api" | "github_actions"
  provider: "openai"                # openai | anthropic | deepseek | ollama
  model: "gpt-4o-mini"
  api_key_env: "OPENAI_API_KEY"
  ollama_base_url: "http://localhost:11434"
  batch_size: 50
  max_concurrent: 5
  rpm_limit: 500
  max_retries: 3
  retry_statuses: [429, 500, 502, 503]

# ── Domain Context (injected into all LLM prompts) ─────────────────
domain:
  category: 2
  description: >
    Computer Networks (CCF Category 2): covers datacenter networking,
    wireless and mobile networks, IoT and sensor networks, network
    measurement and monitoring, congestion control and transport protocols,
    software-defined networking (SDN), network function virtualization (NFV),
    5G/6G cellular systems, satellite and LEO networks, content delivery,
    and network security protocols.

# ── Term Statistics (M2) ──────────────────────────────────────────
term_stats:
  top_k_for_synonym_merge: 2000
  min_display_freq: 3
  ngram_range: [1, 3]
  trend_window_years: 5

# ── Classifier (M3) ───────────────────────────────────────────────
classifier:
  heuristics_file: "config/heuristics/cat2_networks.yaml"
  heuristic_confidence_threshold: 0.85

# ── Graph (M4) ────────────────────────────────────────────────────
graph:
  default_mode: "PAPER_GRAPH"       # PAPER_GRAPH | TERM_GRAPH
  similarity_threshold: 0.45
  edge_weights:
    semantic: 0.6
    term_overlap: 0.3
    venue_year: 0.1
  max_nodes_before_faiss: 20000
  top_k_neighbors_ann: 20
  embedding_model: "all-MiniLM-L6-v2"
  umap_n_neighbors: 15
  umap_min_dist: 0.1

# ── Dashboard (M5) ────────────────────────────────────────────────
dashboard:
  host: "localhost"
  port: 8501
  default_rank: "A/B/C"
  default_year_range: [2010, 2025]
  default_main_track_only: true
```

---

### 5.4 Logging & Observability

All modules emit structured JSON logs:

```python
# Structured log record format
{
  "timestamp": "2026-04-09T14:32:11.421Z",
  "level": "INFO",
  "module": "M1",
  "event": "batch_complete",
  "batch_id": 42,
  "titles_processed": 50,
  "cache_hits": 48,
  "api_calls": 2,
  "llm_tokens_used": 1840,
  "elapsed_ms": 1230
}
```

Log files: `analysis/logs/run_{ISO_timestamp}.jsonl`  
Each pipeline run writes to a new file; old logs are retained for cost tracking and debugging.

---

## 6. Module Validation Plans (Sandbox-Based)

All module tests run against a **self-contained sandbox** — a minimal, hand-crafted dataset that exercises every known data characteristic and edge case. Tests make **zero real API calls**; all LLM interactions are served from a pre-recorded fixture file.

### 6.1 Sandbox Dataset Structure

```
analysis/tests/sandbox/
│
├── paper_db/
│   └── 2/
│       ├── SIGCOMM.json          # 3 years × 12 papers = 36 papers (main + workshop entries)
│       ├── INFOCOM.json          # 3 years × 10 papers = 30 papers
│       ├── TMC.json              # 2 years × 8 papers  = 16 papers (journal)
│       ├── Computer Communications.json   # CC — legit cat-2 C-rank journal
│       ├── Computational Complexity.json  # present by design; loader must handle gracefully
│       └── International Conference on Compiler Construction.json  # same
│
├── llm_fixtures/
│   └── responses.json            # pre-recorded dict: sha256(model+":"+prompt) → response_string
│
└── expected_outputs/
    ├── load_report.json          # expected record counts, unverified file list, etc.
    ├── term_map_fragment.json    # expected canonical terms for sandbox titles
    ├── anomaly_report.json       # expected flagged papers (1 injected anomaly in SIGCOMM fixture)
    ├── term_freq_fragment.json   # expected counts for 5 specific terms
    └── paper_tags_fragment.json  # expected labels for 10 specific papers
```

**Fixture recording workflow** (run once; output committed to repo):

```bash
# Requires real API access; run once per significant prompt change
python analysis/tests/tools/record_fixtures.py \
  --sandbox-dir analysis/tests/sandbox \
  --output analysis/tests/sandbox/llm_fixtures/responses.json
```

After recording, all subsequent test runs are fully offline and reproducible.

### 6.2 M0 Sandbox Tests

```python
# analysis/tests/test_m0.py

def test_catalog_verified_files_loaded():
    """SIGCOMM, INFOCOM, TMC, Computer Communications must be loaded and verified."""
    records = load_sandbox(category=2)
    verified_venues = {r.venue for r in records if r.catalog_verified}
    for expected in ["SIGCOMM", "INFOCOM", "TMC", "CC"]:
        assert expected in verified_venues

def test_unverified_files_loaded_with_flag():
    """
    Computational Complexity and CC (Compiler Construction) must be loaded
    (not rejected) but flagged as catalog_verified=False.
    Their presence in paper_db/2/ is intentional — they were included in a
    previous version of the crawl and must not be silently dropped.
    """
    records = load_sandbox(category=2)
    unverified = [r for r in records if not r.catalog_verified]
    unverified_venues = {r.venue for r in unverified}
    assert "Computational Complexity" in unverified_venues
    assert "International Conference on Compiler Construction" in unverified_venues
    # And they must appear in the load report
    report = load_sandbox_report(category=2)
    assert "Computational Complexity" in report["unverified_venue_names"]
    assert "International Conference on Compiler Construction" in report["unverified_venue_names"]

def test_workshop_papers_excluded_when_flag_false():
    records = load_sandbox(category=2, include_workshops=False)
    for r in records:
        assert r.is_main_track is True, \
            f"Workshop paper leaked into main-track-only result: {r.title}"

def test_workshop_papers_included_when_flag_true():
    main_only = load_sandbox(category=2, include_workshops=False)
    all_tracks = load_sandbox(category=2, include_workshops=True)
    assert len(all_tracks) > len(main_only), \
        "include_workshops=True should yield more records than False"

def test_no_duplicate_records():
    records = load_sandbox(category=2)
    keys = [(r.title_normalized, r.venue, r.year, r.sub_venue) for r in records]
    assert len(keys) == len(set(keys)), "Duplicate records found"

def test_trailing_period_stripped():
    records = load_sandbox(category=2)
    for r in records:
        assert not r.title_normalized.endswith('.'), \
            f"Trailing period not stripped: '{r.title_normalized}'"
```

### 6.3 M1 Sandbox Tests

```python
# analysis/tests/test_m1.py

def test_no_real_api_calls(monkeypatch):
    """M1 must not make any outbound HTTP requests in sandbox mode."""
    import httpx, requests
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("Real HTTP call attempted in sandbox mode")))
    monkeypatch.setattr(requests, "post", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("Real HTTP call attempted in sandbox mode")))
    run_m1_sandbox()   # must complete without triggering monkeypatched functions

def test_fixture_miss_raises_clear_error():
    """If a prompt is not in the fixture, a descriptive error must be raised."""
    with pytest.raises(SandboxFixtureMissError) as exc_info:
        run_m1_with_bad_prompt()
    assert "record_fixtures.py" in str(exc_info.value)

def test_key_networking_terms_present_in_term_map():
    term_map = run_m1_sandbox()
    canonical_names = {t["canonical"].lower() for t in term_map}
    assert any("congestion control" in c for c in canonical_names)
    assert any("rdma" in c or "remote direct memory access" in c for c in canonical_names)
    assert any("software-defined" in c or "sdn" in c for c in canonical_names)

def test_sdn_synonyms_correctly_grouped():
    term_map = run_m1_sandbox()
    sdn = next((t for t in term_map
                if "sdn" in t.get("abbreviation", "").lower()
                or "software-defined networking" in t["canonical"].lower()), None)
    assert sdn is not None, "SDN canonical term not found in term_map"
    aliases_lower = [a.lower() for a in sdn["aliases"]]
    assert "software defined networking" in aliases_lower or "sdn" in aliases_lower

def test_injected_anomaly_is_flagged():
    """
    The sandbox SIGCOMM fixture contains one deliberately injected off-topic title.
    It must appear in the anomaly report.
    """
    report = run_m1_sandbox()
    flagged_titles = [f["title"].lower() for f in report["flags"]]
    assert any("graph isomorphism" in t for t in flagged_titles), \
        "Injected off-topic title was not detected as anomalous"

def test_legitimate_papers_not_flagged():
    """Core networking papers must not be flagged as anomalous."""
    report = run_m1_sandbox()
    flagged = {f["title"].lower() for f in report["flags"]}
    safe_titles = [
        "rdma over ethernet for distributed training at meta scale",
        "a variegated look at 5g in the wild: performance, power, and qoe implications",
    ]
    for t in safe_titles:
        assert t not in flagged, f"Legitimate paper incorrectly flagged: '{t}'"
```

### 6.4 M2 Sandbox Tests

```python
# analysis/tests/test_m2.py

def test_rdma_count_matches_fixture():
    """'RDMA' appears exactly N times in sandbox data — verify exact count."""
    expected = count_term_in_sandbox_titles("rdma")
    stats = run_m2_sandbox()
    actual = (stats.get("RDMA") or stats.get("rdma") or {}).get("total_count", 0)
    assert actual == expected, f"RDMA count: expected {expected}, got {actual}"

def test_rank_breakdown_sums_to_total():
    stats = run_m2_sandbox()
    for term, data in stats.items():
        rank_sum = sum(data["by_rank"].values())
        assert rank_sum == data["total_count"], \
            f"Rank breakdown does not sum to total for term '{term}'"

def test_year_breakdown_sums_to_total():
    stats = run_m2_sandbox()
    for term, data in stats.items():
        year_sum = sum(data["by_year"].values())
        assert year_sum == data["total_count"], \
            f"Year breakdown does not sum to total for term '{term}'"

def test_unverified_excluded_when_filtered():
    stats_verified = run_m2_sandbox(include_unverified=False)
    stats_all      = run_m2_sandbox(include_unverified=True)
    # unverified venues add extra papers; all-count should be >= verified-only count
    total_verified = sum(s["total_count"] for s in stats_verified.values())
    total_all      = sum(s["total_count"] for s in stats_all.values())
    assert total_all >= total_verified
```

### 6.5 M3 Sandbox Tests

```python
# analysis/tests/test_m3.py

def test_known_system_paper_classified_correctly():
    tags = run_m3_sandbox()
    crux = next(t for t in tags
                if "crux" in t["title"].lower() and "gpu-efficient" in t["title"].lower())
    assert crux["research_type"] == "SYSTEM_DESIGN"
    assert "Datacenter" in crux["application_domain"]

def test_measurement_study_classified_correctly():
    tags = run_m3_sandbox()
    meas = next(t for t in tags
                if "vivisecting" in t["title"].lower())
    assert meas["research_type"] == "MEASUREMENT_STUDY"
    assert "Wireless_Cellular_5G6G" in meas["application_domain"]

def test_all_records_have_research_type():
    tags = run_m3_sandbox()
    valid_types = {"PURE_ALGORITHM", "SYSTEM_DESIGN", "MEASUREMENT_STUDY",
                   "SURVEY_OVERVIEW", "APPLIED_ML"}
    for t in tags:
        assert t["research_type"] in valid_types, \
            f"Invalid research_type '{t['research_type']}' for: {t['title']}"

def test_all_records_have_application_domain():
    tags = run_m3_sandbox()
    for t in tags:
        assert isinstance(t["application_domain"], list)
        assert len(t["application_domain"]) >= 1
```

### 6.6 M4 Sandbox Tests

```python
# analysis/tests/test_m4.py

def test_rdma_papers_are_neighbors():
    """Two papers about RDMA in the sandbox must be within each other's top-5 neighbors."""
    graph = run_m4_sandbox()
    rdma_nodes = [n for n in graph.nodes if "rdma" in n["title"].lower()]
    assert len(rdma_nodes) >= 2, "Need at least 2 RDMA papers in sandbox"
    neighbors_of_first = {e["target"] for e in graph.edges
                          if e["source"] == rdma_nodes[0]["id"]}
    assert rdma_nodes[1]["id"] in neighbors_of_first, \
        "RDMA papers are not neighbors in the graph"

def test_louvain_produces_multiple_clusters():
    graph = run_m4_sandbox()
    cluster_ids = {n["cluster_id"] for n in graph.nodes}
    assert len(cluster_ids) >= 2, \
        f"Expected ≥2 Louvain clusters; got {len(cluster_ids)}"

def test_no_self_loops():
    graph = run_m4_sandbox()
    for e in graph.edges:
        assert e["source"] != e["target"], f"Self-loop found on node {e['source']}"

def test_all_nodes_have_required_fields():
    graph = run_m4_sandbox()
    required = {"id", "title", "venue", "year", "rank", "cluster_id",
                "research_type", "application_domain"}
    for node in graph.nodes:
        missing = required - node.keys()
        assert not missing, f"Node missing fields {missing}: {node.get('title', '?')}"
```

### 6.7 CI Workflow for Sandbox Tests

```yaml
# .github/workflows/sandbox_tests.yml
name: Sandbox Module Tests

on:
  push:
    paths:
      - 'analysis/**'
      - '.github/workflows/sandbox_tests.yml'
  pull_request:
    paths:
      - 'analysis/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ hashFiles('analysis/requirements_analysis.txt') }}

      - name: Install dependencies
        run: pip install -r analysis/requirements_analysis.txt

      - name: Run sandbox tests
        run: pytest analysis/tests/ -v --tb=short --cov=analysis --cov-report=term-missing
        # No API keys needed — all LLM calls served from fixture
```

---

## 7. Inter-Domain Portability Design

A central design principle: **switching from Category 2 (Computer Networks) to any other CCF category requires zero Python code changes** — only configuration and heuristic YAML file additions.

### 7.1 Portability Mechanisms by Component

| Component | Portability Mechanism |
|-----------|----------------------|
| M0 Loader | Parameterized entirely by `category` integer; file discovery is data-driven from `ccf_catalog.csv` |
| M1 Analyzer | `domain_context` string is injected from `config.yaml`; all prompts use `{domain_context}` placeholder; no domain names hardcoded in Python |
| M2 Statistics | Purely numeric; operates on the `canonical_terms` field of `PaperRecord`; domain-agnostic |
| M3 Classifier | Heuristic rules loaded from `config/heuristics/cat{N}_{name}.yaml`; label taxonomy is shared across all domains |
| M4 Graph | Operates on embeddings; domain-agnostic |
| M5 Dashboard | Page title and domain description injected from `config.yaml` |

### 7.2 Domain-Specific Heuristic Files

```yaml
# config/heuristics/cat2_networks.yaml

research_type_heuristics:
  SURVEY_OVERVIEW:
    patterns: ['\bsurvey\b', '\boverview\b', '\btutorial\b', '\bsurvey on\b']
    confidence: 0.95
  MEASUREMENT_STUDY:
    patterns: ['\bmeasurement\b', '\bcharacteriz', '\banalysis of\b',
               '\bstudy of\b', '\bunderstanding\b.*\bwild\b']
    confidence: 0.88

application_domain_heuristics:
  Datacenter:
    patterns: ['datacenter', 'data center', '\bRDMA\b', 'SmartNIC',
               '\bcloud\b.*network', 'hyperscale']
    confidence: 0.90
  Satellite_LEO:
    patterns: ['\bsatellite\b', '\bLEO\b', 'low.earth orbit', '\bStarlink\b']
    confidence: 0.95
  IoT_Sensor:
    patterns: ['\bIoT\b', '\bsensor\b', '\bbackscatter\b', '\bLoRa\b',
               'embedded.*network']
    confidence: 0.88
  Wireless_Cellular_5G6G:
    patterns: ['\b5G\b', '\b6G\b', '\bLTE\b', '\bcellular\b', '\bmobile\b.*network',
               '\bmmWave\b', '\bwireless\b']
    confidence: 0.85
```

```yaml
# config/heuristics/cat8_ai.yaml  (example for future AI domain)

research_type_heuristics:
  PURE_ALGORITHM:
    patterns: ['\bconvergence\b', '\bproof\b', '\btheorem\b',
               '\bregret bound\b', '\bcomplexity\b']
    confidence: 0.88

application_domain_heuristics:
  Medical:
    patterns: ['medical', 'clinical', 'hospital', 'diagnosis', 'imaging',
               'pathology', 'radiology']
    confidence: 0.92
  Autonomous_Driving:
    patterns: ['autonomous driving', 'self-driving', '\bADAS\b',
               '\bLiDAR\b', 'autonomous vehicle']
    confidence: 0.95
```

### 7.3 Adding a New Domain: Step-by-Step

```bash
# Prerequisite: paper_db/{N}/ has been populated by the existing src/ crawler

# 1. Add domain heuristic file (5–10 minutes)
cp analysis/config/heuristics/cat2_networks.yaml \
   analysis/config/heuristics/cat8_ai.yaml
# Edit patterns to match AI domain

# 2. Update config.yaml
#    Set: domain.category: 8
#    Set: domain.description: "Artificial Intelligence (CCF Category 8): ..."

# 3. Run the full pipeline
python analysis/run.py --category 8 --rank A

# 4. Launch dashboard
streamlit run analysis/m5_dashboard/dashboard.py -- --category 8

# No Python code changes required.
```

---

## 8. Directory Layout

```
CCF-Rec-Paper-DB/
│
├── paper_db/                         # Existing (read-only input to analysis/)
│   ├── ccf_catalog.csv
│   ├── 2/                            # Category 2 JSON files
│   └── ... (categories 1–10)
│
├── src/                              # Existing crawler (unchanged)
│   ├── main.py
│   ├── parse_html.py
│   ├── utils.py
│   ├── stat_info.py
│   └── db_search.py
│
├── analysis/                         # NEW — this entire directory
│   ├── run.py                        # Pipeline entry point (CLI)
│   ├── config.yaml                   # Master configuration
│   │
│   ├── core/                         # Shared utilities
│   │   ├── data_model.py             # PaperRecord dataclass
│   │   ├── llm_client.py             # LLM abstraction + cache
│   │   ├── cache_manager.py          # SQLite + file cache helpers
│   │   └── config_loader.py          # config.yaml reader + validator
│   │
│   ├── m0_loader/
│   │   ├── loader.py                 # File discovery + JSON parsing
│   │   └── normalizer.py             # Title cleaning, dedup, sub_venue classification
│   │
│   ├── m1_llm_analyzer/
│   │   ├── keyword_extractor.py      # Batched keyword extraction
│   │   ├── synonym_merger.py         # Top-N terms → canonical vocabulary
│   │   └── anomaly_detector.py       # Heuristic + LLM anomaly pipeline
│   │
│   ├── m2_term_stats/
│   │   ├── statistician.py           # Frequency computation
│   │   └── visualizer.py             # Wordcloud, heatmap, trend charts
│   │
│   ├── m3_classifier/
│   │   ├── heuristic_classifier.py   # Rule-based first pass
│   │   └── llm_classifier.py         # LLM second pass for uncertain cases
│   │
│   ├── m4_graph/
│   │   ├── embedder.py               # sentence-transformers + FAISS fallback
│   │   ├── edge_builder.py           # Similarity score computation
│   │   ├── clusterer.py              # Louvain + UMAP layout
│   │   └── renderer.py               # PyVis HTML generation
│   │
│   ├── m5_dashboard/
│   │   └── dashboard.py              # Streamlit application
│   │
│   ├── config/
│   │   └── heuristics/
│   │       ├── cat2_networks.yaml
│   │       └── cat8_ai.yaml          # (future)
│   │
│   ├── tests/
│   │   ├── test_m0.py
│   │   ├── test_m1.py
│   │   ├── test_m2.py
│   │   ├── test_m3.py
│   │   ├── test_m4.py
│   │   ├── conftest.py               # Shared fixtures and sandbox loader helpers
│   │   ├── sandbox/
│   │   │   ├── paper_db/2/           # Miniature hand-crafted dataset
│   │   │   ├── llm_fixtures/
│   │   │   │   └── responses.json    # Pre-recorded LLM responses (committed)
│   │   │   └── expected_outputs/     # Expected test output files
│   │   └── tools/
│   │       └── record_fixtures.py    # One-time fixture recorder (needs real API key)
│   │
│   ├── cache/                        # Auto-generated; gitignored
│   │   └── .gitkeep
│   ├── viz/                          # Auto-generated; gitignored
│   │   └── .gitkeep
│   └── logs/                         # Auto-generated; gitignored
│       └── .gitkeep
│
├── .github/
│   └── workflows/
│       ├── sandbox_tests.yml         # NEW: runs on every push to analysis/
│       └── llm_analysis.yml          # NEW: manual trigger for large-scale runs
│
├── requirements.txt                  # Existing (crawler dependencies)
├── analysis/requirements_analysis.txt  # NEW (analysis dependencies)
└── README.md
```

---

## 9. Dependency Manifest

```txt
# analysis/requirements_analysis.txt

# ── Core data ──────────────────────────────────────────────────────
pandas>=2.0
numpy>=1.26

# ── NLP / embeddings ───────────────────────────────────────────────
sentence-transformers>=2.7        # Local title embeddings (no API cost)
keybert>=0.8                       # Unsupervised keyword extraction fallback
langdetect>=1.0.0                  # Language detection for anomaly heuristics

# ── LLM provider SDKs ──────────────────────────────────────────────
openai>=1.30
anthropic>=0.25
litellm>=1.40                      # Optional: unified multi-provider interface

# ── Approximate nearest neighbors ─────────────────────────────────
faiss-cpu>=1.8                     # ANN for corpora > 20K papers

# ── Graph ──────────────────────────────────────────────────────────
networkx>=3.3
python-louvain>=0.16               # Louvain community detection
umap-learn>=0.5                    # 2D layout from high-dim embeddings
pyvis>=0.3                         # Interactive HTML graph rendering

# ── Visualization ──────────────────────────────────────────────────
plotly>=5.22
wordcloud>=1.9
matplotlib>=3.8

# ── Dashboard ──────────────────────────────────────────────────────
streamlit>=1.35

# ── Utilities ──────────────────────────────────────────────────────
pyyaml>=6.0
tqdm>=4.66
python-dotenv>=1.0                 # Load .env for local API keys (Mode A only)
Levenshtein>=0.25                  # Fast string distance for dedup

# ── Testing ────────────────────────────────────────────────────────
pytest>=8.0
pytest-cov>=5.0
```

---

## 10. Development Roadmap

### Phase 1 — Foundation (Week 1)
**Goal:** Working M0 + M2 (no LLM required). First term statistics on Category 2 A-rank.

- [ ] Implement `PaperRecord`, `config_loader.py`, `cache_manager.py`
- [ ] Implement M0 with full normalization, dedup, and unverified-file handling
- [ ] Write and pass all M0 sandbox tests
- [ ] Implement M2 statistician using raw n-gram keywords (no LLM needed)
- [ ] Produce first wordcloud from SIGCOMM + INFOCOM + NSDI + MobiCom (A-rank conferences)
- [ ] **Milestone:** Screenshot of first wordcloud shared for feedback

### Phase 2 — LLM Layer (Week 2)
**Goal:** Working M1 + M3. Paper records enriched with semantic labels.

- [ ] Implement `LLMClient` (both Mode A and Mode B; with fixture-based sandbox)
- [ ] Implement M1 keyword extractor + synonym merger
- [ ] Record sandbox LLM fixtures (`record_fixtures.py`)
- [ ] Write and pass all M1 sandbox tests
- [ ] Run M1 on Category 2 A-rank (~230 LLM calls); review `term_map.json` and `anomaly_report.json`
- [ ] Implement M3 heuristic + LLM classifier
- [ ] Write and pass all M3 sandbox tests
- [ ] **Milestone:** `term_map.json` and `paper_tags.json` reviewed and approved for A-rank

### Phase 3 — Graph & Dashboard (Week 3)
**Goal:** Working M4 + M5. End-to-end interactive experience.

- [ ] Implement M4 embedder (local, no API cost) + FAISS fallback
- [ ] Implement M4 edge builder + Louvain clusterer + UMAP layout
- [ ] Implement M4 PyVis renderer with hover, click, and year slider
- [ ] Write and pass all M4 sandbox tests
- [ ] Implement M5 Streamlit dashboard (all 6 tabs)
- [ ] End-to-end test on Category 2 A+B rank, 2015–2025
- [ ] **Milestone:** Live demo of full dashboard on A+B rank data

### Phase 4 — Hardening & Portability (Week 4)
**Goal:** Production-quality pipeline; portable to any CCF category.

- [ ] Add `config/heuristics/cat8_ai.yaml`; verify portability by running on Category 8
- [ ] Set up `sandbox_tests.yml` and `llm_analysis.yml` GitHub Actions workflows
- [ ] Optimize for A+B+C rank: enable FAISS for large corpus
- [ ] Write user-facing `analysis/README.md` with setup, quickstart, and FAQ
- [ ] **Milestone:** All 4 GitHub Actions checks green; full A+B+C Category 2 pipeline complete

---

## 11. Open Questions & Future Extensions

### Open Questions (Resolve Before Implementation)

| # | Question | Decision Needed By |
|---|----------|--------------------|
| Q1 | Should workshop papers be **included** in term statistics by default, or only as an opt-in? Workshops may capture emerging topics earlier than main tracks. | Phase 1 |
| Q2 | For the **graph default view**: paper-level nodes (more detail) or term-level nodes (cleaner landscape)? Affects M4 UX first impression. | Phase 3 |
| Q3 | Should **anomaly-confirmed** papers be automatically excluded from all statistics, or remain visible with a visual flag in the dashboard? | Phase 2 |
| Q4 | Which LLM for the **v1.0 pilot**: GPT-4o-mini (fast, cheap, strong English) or DeepSeek-Chat (cheaper, competitive on technical content)? | Phase 2 |

### Planned Future Extensions (v1.1+)

| Feature | Primary Module | Description |
|---------|---------------|-------------|
| **Abstract enrichment** | M0+ | Pull abstracts from Semantic Scholar API; significantly improves M1 and M3 quality without changing any downstream interfaces |
| **Citation graph overlay** | M4+ | Overlay real citation edges (from Semantic Scholar) on top of semantic similarity edges; edge color distinguishes the two sources |
| **Research gap finder** | M2+ | Detect terms that are semantically adjacent to hot topics but show low or declining frequency; surface as "potential research opportunities" |
| **Personalized reading list** | M5+ | User inputs 3–5 seed paper titles or keywords; system returns a ranked reading list ordered by semantic similarity |
| **Survey outline generator** | M5+ | LLM generates a structured survey outline: section titles, key sub-topics per section, and 3–5 representative papers per sub-topic |
| **Cross-category comparison** | M4+ | Side-by-side term evolution comparison between two CCF categories (e.g., Networks vs. AI on the topic of "federated learning") |
| **Author network** | M4+ | Node = author, edge = co-authorship weight; requires enriching JSON files with author metadata from the existing DBLP source |
| **Temporal cluster tracking** | M4+ | Track how Louvain community membership shifts year by year; identify when a new sub-field crystallizes or when two communities merge |

---

*End of Technical Specification Document*  
*Repository: RobinKool888/CCF-Rec-Paper-DB | Maintained by: RobinKool888*  
*Next review: after Phase 1 Milestone (first wordcloud produced)*