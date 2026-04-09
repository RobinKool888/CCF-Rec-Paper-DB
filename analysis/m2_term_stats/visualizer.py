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
