import numpy as np


def build_graph(records: list, edges: list, embeddings, config: dict):
    """
    Build a networkx.Graph with cluster_id and 2D coords (x, y) on each node.

    Uses Louvain clustering and UMAP for layout (falls back to random
    layout if libraries are unavailable).

    Returns networkx.Graph.
    """
    import networkx as nx

    G = nx.Graph()

    # Add nodes
    for i, record in enumerate(records):
        G.add_node(
            i,
            title=record.title,
            venue=record.venue,
            year=record.year,
            rank=record.rank,
            research_type=record.research_type,
            application_domain=record.application_domain,
            cluster_id=0,
            x=0.0,
            y=0.0,
        )

    # Add edges
    for edge in edges:
        G.add_edge(
            edge["source"],
            edge["target"],
            weight=edge.get("weight", 1.0),
        )

    # Louvain clustering
    try:
        import community as community_louvain
        partition = community_louvain.best_partition(G)
        for node, cluster_id in partition.items():
            G.nodes[node]["cluster_id"] = cluster_id
    except ImportError:
        # Fallback: connected-components as clusters
        for comp_id, component in enumerate(nx.connected_components(G)):
            for node in component:
                G.nodes[node]["cluster_id"] = comp_id

    # UMAP layout for 2D coords
    coords = _compute_layout(records, embeddings, G, config)
    for i, (x, y) in enumerate(coords):
        G.nodes[i]["x"] = float(x)
        G.nodes[i]["y"] = float(y)

    return G


def _compute_layout(records, embeddings, G, config):
    """Return list of (x, y) tuples for each node."""
    n = len(records)
    if n == 0:
        return []

    emb = np.array(embeddings, dtype=np.float32) if embeddings is not None else None

    try:
        import umap
        umap_cfg = config.get("graph", {})
        reducer = umap.UMAP(
            n_components=2,
            n_neighbors=min(umap_cfg.get("umap_n_neighbors", 15), n - 1),
            min_dist=umap_cfg.get("umap_min_dist", 0.1),
            random_state=42,
        )
        coords_2d = reducer.fit_transform(emb if emb is not None else
                                           np.eye(n, 64))
        return coords_2d.tolist()
    except (ImportError, Exception):
        pass

    # Fallback: networkx spring layout
    import networkx as nx
    pos = nx.spring_layout(G, seed=42)
    return [(pos[i][0], pos[i][1]) for i in range(n)]
