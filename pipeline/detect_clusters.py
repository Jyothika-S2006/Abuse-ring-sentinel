"""
Community Detection Pipeline for Abuse Ring Sentinel.
Applies Louvain modularity optimization on the entity graph to discover
dense candidate abuse rings and look-alike clusters.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
import pandas as pd


class ClusterDetector:
    def __init__(self, resolution: float = 1.0, seed: int = 42, min_cluster_size: int = 2):
        self.resolution = resolution
        self.seed = seed
        self.min_cluster_size = min_cluster_size

    def detect_clusters(self, G: nx.Graph) -> Tuple[List[Dict[str, Any]], Dict[str, str], pd.DataFrame]:
        """
        Executes Louvain community detection on weighted graph G.
        
        Returns:
            - clusters: List of cluster metadata dicts containing cluster_id, member_ids, size, subgraph.
            - account_cluster_map: Dict mapping account_id -> cluster_id.
            - df_memberships: DataFrame of cluster membership records.
        """
        print(f"[+] Running Louvain Community Detection (Resolution={self.resolution}, Seed={self.seed})...")

        # 1. Run Louvain Community Detection
        raw_communities = nx.community.louvain_communities(
            G,
            weight="weight",
            resolution=self.resolution,
            seed=self.seed
        )

        # 2. Filter communities by minimum size
        candidate_communities = [
            list(comm) for comm in raw_communities
            if len(comm) >= self.min_cluster_size
        ]

        # Sort candidate clusters by size descending
        candidate_communities.sort(key=lambda c: len(c), reverse=True)

        clusters: List[Dict[str, Any]] = []
        account_cluster_map: Dict[str, str] = {}
        membership_rows: List[Dict[str, Any]] = []

        for idx, members in enumerate(candidate_communities, start=1):
            cluster_id = f"CLUSTER_{idx:03d}"
            subgraph = G.subgraph(members).copy()

            # Compute internal node degrees within the cluster
            degrees = dict(subgraph.degree(weight="weight"))
            max_degree = max(degrees.values()) if degrees else 0.0

            for acc_id in members:
                account_cluster_map[acc_id] = cluster_id
                node_deg = degrees.get(acc_id, 0)
                is_core = (node_deg >= max_degree * 0.75) and (node_deg > 0)
                role = "core_hub" if is_core else "member"

                membership_rows.append({
                    "cluster_id": cluster_id,
                    "account_id": acc_id,
                    "degree": int(subgraph.degree(acc_id)),
                    "is_core": bool(is_core),
                    "account_role": role
                })

            clusters.append({
                "cluster_id": cluster_id,
                "member_ids": members,
                "size": len(members),
                "subgraph": subgraph
            })

        df_memberships = pd.DataFrame(membership_rows)
        print(f"[OK] Detected {len(clusters)} candidate clusters (sizes: {[c['size'] for c in clusters]}) across {len(df_memberships)} accounts.")
        return clusters, account_cluster_map, df_memberships


def detect_clusters_from_graph(
    G: nx.Graph,
    resolution: float = 1.0,
    seed: int = 42,
    min_cluster_size: int = 2
) -> Tuple[List[Dict[str, Any]], Dict[str, str], pd.DataFrame]:
    """Helper function to run Louvain detection on a graph."""
    detector = ClusterDetector(resolution=resolution, seed=seed, min_cluster_size=min_cluster_size)
    return detector.detect_clusters(G)


if __name__ == "__main__":
    from pipeline.build_graph import build_graph_from_data_dir

    G, _ = build_graph_from_data_dir("data")
    clusters, _, df_members = detect_clusters_from_graph(G)
    print(f"Top 5 clusters detected:\n{df_members.groupby('cluster_id').size().head(5)}")

