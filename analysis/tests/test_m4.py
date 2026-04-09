"""Tests for M4 graph pipeline."""
import pytest
from sandbox_helpers import run_m4_sandbox


def test_rdma_papers_are_neighbors():
    graph = run_m4_sandbox()
    rdma_nodes = [n for n in graph["nodes"] if "rdma" in n["title"].lower()]
    assert len(rdma_nodes) >= 2, (
        f"Need at least 2 RDMA papers in sandbox, got {len(rdma_nodes)}"
    )
    neighbors_of_first = {
        e["target"] for e in graph["edges"]
        if e["source"] == rdma_nodes[0]["id"]
    } | {
        e["source"] for e in graph["edges"]
        if e["target"] == rdma_nodes[0]["id"]
    }
    assert rdma_nodes[1]["id"] in neighbors_of_first, (
        f"RDMA papers are not neighbors. "
        f"First RDMA node {rdma_nodes[0]['id']} neighbors: {neighbors_of_first}"
    )


def test_louvain_produces_multiple_clusters():
    graph = run_m4_sandbox()
    cluster_ids = {n["cluster_id"] for n in graph["nodes"]}
    assert len(cluster_ids) >= 2, (
        f"Expected >= 2 clusters, got: {cluster_ids}"
    )


def test_no_self_loops():
    graph = run_m4_sandbox()
    for e in graph["edges"]:
        assert e["source"] != e["target"], (
            f"Self-loop found: edge {e}"
        )


def test_all_nodes_have_required_fields():
    graph = run_m4_sandbox()
    required = {
        "id", "title", "venue", "year", "rank",
        "cluster_id", "research_type", "application_domain",
    }
    for node in graph["nodes"]:
        missing = required - node.keys()
        assert not missing, (
            f"Node missing fields {missing}: {node.get('title', '?')}"
        )
