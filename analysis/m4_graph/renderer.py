import os


def render_paper_graph(graph, records: list, output_path: str):
    """Generate an interactive PyVis HTML graph of papers."""
    try:
        from pyvis.network import Network
    except ImportError:
        _render_fallback_html(output_path, "paper")
        return

    net = Network(height="800px", width="100%", bgcolor="#222222",
                  font_color="white")
    net.toggle_physics(True)

    color_map = {
        "A": "#e74c3c",
        "B": "#3498db",
        "C": "#2ecc71",
        "unknown": "#95a5a6",
    }

    for node_id, data in graph.nodes(data=True):
        color = color_map.get(data.get("rank", "unknown"), "#95a5a6")
        label = data.get("title", "")[:50]
        title_tooltip = (
            f"<b>{data.get('title', '')}</b><br>"
            f"Venue: {data.get('venue', '')}<br>"
            f"Year: {data.get('year', '')}<br>"
            f"Rank: {data.get('rank', '')}<br>"
            f"Type: {data.get('research_type', '')}<br>"
            f"Domain: {data.get('application_domain', '')}"
        )
        net.add_node(
            node_id,
            label=label,
            title=title_tooltip,
            color=color,
            x=data.get("x", 0) * 1000,
            y=data.get("y", 0) * 1000,
        )

    for src, dst, edge_data in graph.edges(data=True):
        net.add_edge(src, dst, value=edge_data.get("weight", 1.0))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    net.save_graph(output_path)


def render_term_graph(term_stats: dict, output_path: str):
    """Generate a PyVis term co-occurrence graph."""
    try:
        from pyvis.network import Network
    except ImportError:
        _render_fallback_html(output_path, "term")
        return

    net = Network(height="700px", width="100%", bgcolor="#1a1a2e",
                  font_color="white")

    top_terms = sorted(
        term_stats.items(), key=lambda x: -x[1]["total_count"]
    )[:80]

    for term, data in top_terms:
        size = max(5, min(50, data["total_count"] // 2))
        net.add_node(
            term,
            label=term[:30],
            title=f"{term}<br>count: {data['total_count']}",
            size=size,
        )

    # Connect terms that share venues or time windows
    term_list = [t[0] for t in top_terms]
    for i in range(len(term_list)):
        for j in range(i + 1, len(term_list)):
            t1_venues = set(term_stats[term_list[i]].get("by_venue", {}).keys())
            t2_venues = set(term_stats[term_list[j]].get("by_venue", {}).keys())
            overlap = len(t1_venues & t2_venues)
            if overlap >= 2:
                net.add_edge(term_list[i], term_list[j], value=overlap)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    net.save_graph(output_path)


def _render_fallback_html(output_path: str, graph_type: str):
    html = (
        f"<html><body><p>PyVis not installed — {graph_type} graph "
        f"unavailable.</p></body></html>"
    )
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as fh:
        fh.write(html)
