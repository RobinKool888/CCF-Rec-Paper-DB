"""Streamlit dashboard for CCF-Rec-Paper-DB analysis results."""
import json
import os
import sys

# Ensure analysis/ is importable
_analysis_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _analysis_dir not in sys.path:
    sys.path.insert(0, _analysis_dir)

import streamlit as st
import pandas as pd

from core.config_loader import load_config


def _load_json(path: str):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return None


def run_dashboard(config: dict):
    st.set_page_config(
        page_title="CCF Paper Analysis",
        page_icon="📊",
        layout="wide",
    )
    st.title("📊 CCF-Rec-Paper-DB Analysis Dashboard")

    cache_dir = config["paths"]["cache_dir"]

    # Sidebar controls
    st.sidebar.header("Filters")
    rank_filter = st.sidebar.multiselect(
        "Rank",
        options=["A", "B", "C", "unknown"],
        default=["A", "B", "C"],
    )
    year_range = st.sidebar.slider(
        "Year Range",
        min_value=2000,
        max_value=2025,
        value=(2010, 2025),
    )
    main_track_only = st.sidebar.checkbox("Main Track Only", value=True)

    # Load data
    load_report = _load_json(os.path.join(cache_dir, "load_report.json"))
    term_stats = _load_json(os.path.join(cache_dir, "term_freq.json"))
    term_map = _load_json(os.path.join(cache_dir, "term_map.json"))
    paper_tags = _load_json(os.path.join(cache_dir, "paper_tags.json"))
    anomaly_report = _load_json(os.path.join(cache_dir, "anomaly_report.json"))
    graph_html = os.path.join(config["paths"]["viz_dir"], "paper_graph.html")

    tabs = st.tabs([
        "📥 Load Report",
        "📈 Term Statistics",
        "🔠 Term Map",
        "🏷️ Paper Tags",
        "⚠️ Anomalies",
        "🕸️ Graph",
    ])

    # Tab 0 — Load Report
    with tabs[0]:
        st.header("Data Load Report")
        if load_report:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Records", load_report.get("total_records", 0))
            col2.metric("Main Track", load_report.get("main_track_records", 0))
            col3.metric("Workshop", load_report.get("workshop_records", 0))
            st.json(load_report)
        else:
            st.info("No load report found. Run M0 first.")

    # Tab 1 — Term Statistics
    with tabs[1]:
        st.header("Term Frequency Statistics")
        if term_stats:
            rows = []
            for canonical, data in term_stats.items():
                rows.append({
                    "Term": canonical,
                    "Count": data.get("total_count", 0),
                    "Paper Fraction": data.get("paper_fraction", 0),
                    "Trend": data.get("trend_direction", ""),
                    "Peak Year": data.get("peak_year", ""),
                })
            df = pd.DataFrame(rows).sort_values("Count", ascending=False)
            st.dataframe(df, use_container_width=True)

            # Wordcloud image
            viz_dir = config["paths"]["viz_dir"]
            wc_path = os.path.join(viz_dir, "wordcloud_all.png")
            if os.path.exists(wc_path):
                st.image(wc_path, caption="Word Cloud — All Papers")
        else:
            st.info("No term statistics found. Run M2 first.")

    # Tab 2 — Term Map
    with tabs[2]:
        st.header("Synonym / Term Map")
        if term_map:
            df = pd.DataFrame(term_map)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No term map found. Run M1 first.")

    # Tab 3 — Paper Tags
    with tabs[3]:
        st.header("Paper Classifications")
        if paper_tags:
            df = pd.DataFrame(paper_tags)
            rank_col = "rank" if "rank" in df.columns else None
            if rank_col and rank_filter:
                df = df[df[rank_col].isin(rank_filter)]
            if "year" in df.columns:
                df = df[
                    (df["year"] >= year_range[0]) & (df["year"] <= year_range[1])
                ]
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No paper tags found. Run M3 first.")

    # Tab 4 — Anomalies
    with tabs[4]:
        st.header("Anomaly Report")
        if anomaly_report:
            col1, col2 = st.columns(2)
            col1.metric("Checked", anomaly_report.get("total_checked", 0))
            col2.metric("Flagged", anomaly_report.get("llm_confirmed", 0))
            flags = anomaly_report.get("flags", [])
            if flags:
                st.dataframe(pd.DataFrame(flags), use_container_width=True)
        else:
            st.info("No anomaly report found. Run M1 first.")

    # Tab 5 — Graph
    with tabs[5]:
        st.header("Paper Similarity Graph")
        if os.path.exists(graph_html):
            with open(graph_html, "r", encoding="utf-8") as fh:
                html_content = fh.read()
            st.components.v1.html(html_content, height=850, scrolling=True)
        else:
            st.info("No graph found. Run M4 first.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args, _ = parser.parse_known_args()

    config_path = os.path.join(_analysis_dir, args.config)
    cfg = load_config(config_path)
    run_dashboard(cfg)
