"""Streamlit dashboard for pipeline_v2 — venue-scoped analysis results.

Usage:
    streamlit run pipeline_v2/m5_dashboard/dashboard.py -- --venue CoNEXT
"""
import json
import os
import sys

# Ensure pipeline_v2/ is importable
_pipeline_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pipeline_dir not in sys.path:
    sys.path.insert(0, _pipeline_dir)

import streamlit as st
import pandas as pd


def _load_json(path: str):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return None


def run_dashboard(venue: str, output_dir: str):
    st.set_page_config(
        page_title=f"CCF Paper Analysis — {venue}",
        page_icon="📊",
        layout="wide",
    )
    st.title(f"📊 CCF-Rec-Paper-DB Analysis Dashboard")

    # Sidebar
    st.sidebar.header(f"Venue: {venue}")
    st.sidebar.markdown(f"**Output dir:** `{output_dir}`")
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
    load_report = _load_json(os.path.join(output_dir, "load_report.json"))
    term_stats = _load_json(os.path.join(output_dir, "term_freq.json"))
    term_map = _load_json(os.path.join(output_dir, "term_map.json"))
    paper_tags = _load_json(os.path.join(output_dir, "paper_tags.json"))
    anomaly_report = _load_json(os.path.join(output_dir, "anomaly_report.json"))
    graph_html = os.path.join(output_dir, "viz", "paper_graph.html")
    viz_dir = os.path.join(output_dir, "viz")

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
            if main_track_only and "is_main_track" in df.columns:
                df = df[df["is_main_track"]]
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
    parser.add_argument("--venue", required=True, help="Venue name, e.g. CoNEXT")
    parser.add_argument("--output-dir", default=None,
                        help="Override output directory (default: pipeline_v2/output/{venue})")
    args, _ = parser.parse_known_args()

    if args.output_dir:
        out_dir = args.output_dir
    else:
        out_dir = os.path.join(_pipeline_dir, "output", args.venue)

    run_dashboard(args.venue, out_dir)
