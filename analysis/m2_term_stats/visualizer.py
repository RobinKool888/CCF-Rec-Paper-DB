import os
from collections import defaultdict


def generate_all_visualizations(
    term_stats: dict, records: list, output_dir: str, config: dict
):
    """Generate wordclouds, top-50 bar chart, heatmap, and trend chart.

    Saves to output_dir. Falls back gracefully if optional deps missing.
    """
    os.makedirs(output_dir, exist_ok=True)

    try:
        _generate_wordcloud(term_stats, output_dir)
    except Exception:
        pass

    try:
        _generate_top50_chart(term_stats, output_dir)
    except Exception:
        pass

    try:
        _generate_heatmap(term_stats, records, output_dir)
    except Exception:
        pass

    try:
        _generate_trend_chart(term_stats, output_dir)
    except Exception:
        pass


def _generate_wordcloud(term_stats: dict, output_dir: str):
    from wordcloud import WordCloud
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Group by rank if available
    rank_words: dict = defaultdict(dict)
    for canonical, data in term_stats.items():
        by_rank = data.get("by_rank", {})
        for rank, cnt in by_rank.items():
            rank_words[rank][canonical] = cnt

    for rank, word_freq in rank_words.items():
        if not word_freq:
            continue
        wc = WordCloud(
            width=800,
            height=400,
            background_color="white",
            max_words=200,
        ).generate_from_frequencies(word_freq)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        ax.set_title(f"Word Cloud — Rank {rank}")
        fig.tight_layout()
        fig.savefig(os.path.join(output_dir, f"wordcloud_{rank}.png"), dpi=150)
        plt.close(fig)

    # Overall wordcloud
    overall = {c: d["total_count"] for c, d in term_stats.items()}
    if overall:
        wc = WordCloud(
            width=1200,
            height=600,
            background_color="white",
            max_words=300,
        ).generate_from_frequencies(overall)
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        ax.set_title("Word Cloud — All Papers")
        fig.tight_layout()
        fig.savefig(
            os.path.join(output_dir, "wordcloud_all.png"), dpi=150
        )
        plt.close(fig)


def _generate_top50_chart(term_stats: dict, output_dir: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sorted_terms = sorted(
        term_stats.items(), key=lambda x: -x[1]["total_count"]
    )[:50]
    if not sorted_terms:
        return
    labels = [t[0][:40] for t in sorted_terms]
    counts = [t[1]["total_count"] for t in sorted_terms]

    fig, ax = plt.subplots(figsize=(14, 10))
    ax.barh(labels[::-1], counts[::-1])
    ax.set_xlabel("Total Occurrences")
    ax.set_title("Top 50 Terms")
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "top50_terms.png"), dpi=150)
    plt.close(fig)


def _generate_heatmap(term_stats: dict, records: list, output_dir: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    top_terms = sorted(
        term_stats.items(), key=lambda x: -x[1]["total_count"]
    )[:20]
    if not top_terms or not records:
        return

    all_years = sorted({r.year for r in records})
    term_names = [t[0][:30] for t in top_terms]
    matrix = np.zeros((len(term_names), len(all_years)))
    for i, (term, data) in enumerate(top_terms):
        for j, year in enumerate(all_years):
            matrix[i, j] = data["by_year"].get(year, 0)

    fig, ax = plt.subplots(figsize=(max(10, len(all_years) * 0.6), 8))
    im = ax.imshow(matrix, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(all_years)))
    ax.set_xticklabels(all_years, rotation=45, ha="right")
    ax.set_yticks(range(len(term_names)))
    ax.set_yticklabels(term_names)
    ax.set_title("Term Frequency Heatmap (Top 20)")
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "heatmap.png"), dpi=150)
    plt.close(fig)


def generate_classification_figures(paper_tags: list, output_dir: str):
    """Generate classification summary charts from a list of paper-tag dicts.

    Produces:
      - classification_research_type_pie.png
      - classification_domain_bar.png
      - classification_research_type_by_year.png
      - classification_domain_by_rank.png
    """
    os.makedirs(output_dir, exist_ok=True)

    try:
        _clf_research_type_pie(paper_tags, output_dir)
    except Exception:
        pass

    try:
        _clf_domain_bar(paper_tags, output_dir)
    except Exception:
        pass

    try:
        _clf_research_type_by_year(paper_tags, output_dir)
    except Exception:
        pass

    try:
        _clf_domain_by_rank(paper_tags, output_dir)
    except Exception:
        pass


def _clf_research_type_pie(paper_tags: list, output_dir: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from collections import Counter

    counts = Counter(t["research_type"] for t in paper_tags)
    if not counts:
        return

    labels = list(counts.keys())
    sizes = [counts[l] for l in labels]
    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3"]

    fig, ax = plt.subplots(figsize=(9, 7))
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        autopct="%1.1f%%",
        colors=colors[: len(labels)],
        startangle=140,
    )
    for at in autotexts:
        at.set_fontsize(9)
    ax.set_title("Research Type Distribution", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(
        os.path.join(output_dir, "classification_research_type_pie.png"), dpi=150
    )
    plt.close(fig)


def _clf_domain_bar(paper_tags: list, output_dir: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from collections import Counter

    domain_counts: Counter = Counter()
    for t in paper_tags:
        for d in t.get("application_domain", []):
            domain_counts[d] += 1

    if not domain_counts:
        return

    sorted_items = domain_counts.most_common()
    labels = [i[0] for i in sorted_items]
    counts = [i[1] for i in sorted_items]

    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.5)))
    bars = ax.barh(labels[::-1], counts[::-1], color="#4C72B0")
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.set_xlabel("Number of Papers")
    ax.set_title("Application Domain Distribution", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(
        os.path.join(output_dir, "classification_domain_bar.png"), dpi=150
    )
    plt.close(fig)


def _clf_research_type_by_year(paper_tags: list, output_dir: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from collections import defaultdict

    VALID_TYPES = [
        "SYSTEM_DESIGN",
        "MEASUREMENT_STUDY",
        "APPLIED_ML",
        "SURVEY_OVERVIEW",
        "PURE_ALGORITHM",
    ]

    # Build year -> type -> count
    by_year: dict = defaultdict(lambda: defaultdict(int))
    for t in paper_tags:
        year = t.get("year", 0)
        rt = t.get("research_type", "SYSTEM_DESIGN")
        if year and rt in VALID_TYPES:
            by_year[year][rt] += 1

    if not by_year:
        return

    years = sorted(by_year.keys())
    x = np.arange(len(years))
    width = 0.8 / max(len(VALID_TYPES), 1)
    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3"]

    fig, ax = plt.subplots(figsize=(max(10, len(years) * 0.5), 6))
    bottom = np.zeros(len(years))
    for i, rt in enumerate(VALID_TYPES):
        vals = np.array([by_year[y].get(rt, 0) for y in years], dtype=float)
        ax.bar(x, vals, bottom=bottom, label=rt, color=colors[i % len(colors)])
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Number of Papers")
    ax.set_title("Research Type by Year", fontsize=14, fontweight="bold")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(
        os.path.join(output_dir, "classification_research_type_by_year.png"), dpi=150
    )
    plt.close(fig)


def _clf_domain_by_rank(paper_tags: list, output_dir: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from collections import Counter, defaultdict

    # Collect all domains and ranks
    domain_counts: Counter = Counter()
    for t in paper_tags:
        for d in t.get("application_domain", []):
            domain_counts[d] += 1
    top_domains = [d for d, _ in domain_counts.most_common(8)]

    ranks = ["A", "B", "C"]
    by_rank: dict = defaultdict(lambda: defaultdict(int))
    for t in paper_tags:
        rank = t.get("rank", "unknown")
        if rank not in ranks:
            continue
        for d in t.get("application_domain", []):
            if d in top_domains:
                by_rank[rank][d] += 1

    if not top_domains or not any(by_rank.values()):
        return

    x = np.arange(len(top_domains))
    width = 0.25
    colors = ["#4C72B0", "#DD8452", "#55A868"]

    fig, ax = plt.subplots(figsize=(12, 6))
    for i, rank in enumerate(ranks):
        vals = [by_rank[rank].get(d, 0) for d in top_domains]
        ax.bar(x + i * width, vals, width, label=f"Rank {rank}", color=colors[i])

    ax.set_xticks(x + width)
    ax.set_xticklabels([d[:20] for d in top_domains], rotation=25, ha="right", fontsize=9)
    ax.set_ylabel("Number of Papers")
    ax.set_title("Application Domain by CCF Rank (Top 8 Domains)", fontsize=14, fontweight="bold")
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(
        os.path.join(output_dir, "classification_domain_by_rank.png"), dpi=150
    )
    plt.close(fig)


def _generate_trend_chart(term_stats: dict, output_dir: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rising = [
        (c, d) for c, d in term_stats.items()
        if d.get("trend_direction") == "rising"
    ]
    rising = sorted(rising, key=lambda x: -x[1]["trend_slope"])[:10]
    if not rising:
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    for term, data in rising:
        by_year = dict(sorted(data["by_year"].items()))
        ax.plot(list(by_year.keys()), list(by_year.values()), marker="o",
                label=term[:30])

    ax.set_xlabel("Year")
    ax.set_ylabel("Occurrences")
    ax.set_title("Rising Trends (Top 10)")
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "trend_rising.png"), dpi=150)
    plt.close(fig)
