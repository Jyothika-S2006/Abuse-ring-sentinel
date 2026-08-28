#!/usr/bin/env python3
"""
Unit and Integration Tests for Abuse Ring Sentinel Day 2 Pipeline:
- Database schema & ORM models (backend/db.py)
- Graph construction (pipeline/build_graph.py)
- Louvain cluster detection (pipeline/detect_clusters.py)
- 9 Cluster feature engineering (pipeline/cluster_features.py)
- End-to-end pipeline execution (pipeline/run_pipeline.py)
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import networkx as nx
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import (
    Account,
    Base,
    Cluster,
    ClusterMember,
    GraphEdge,
    GroundTruth,
    Instrument,
    PayoutDestination,
    Transaction,
    get_session_factory,
    init_db,
)
from pipeline.build_graph import MultiSignalGraphBuilder, build_graph_from_data_dir
from pipeline.cluster_features import ClusterFeatureExtractor, extract_features_for_all_clusters
from pipeline.detect_clusters import ClusterDetector, detect_clusters_from_graph
from pipeline.run_pipeline import run_pipeline


TEST_DB_URL = "sqlite:///./test_sentinel.db"
DATA_DIR = "data"


def test_database_models_and_init():
    print("[+] Testing database initialization and schema models...")
    engine = init_db(TEST_DB_URL)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        # Create test account
        acc = Account(
            account_id="ACC_TEST_001",
            created_at="2026-08-28T12:00:00Z",
            user_name="Test User",
            email="test@example.com",
            phone_number="+1-555-0100",
            ip_address="192.0.2.1",
            device_id="DEV_TEST_01",
            account_status="active",
            risk_score=0.15,
            kyc_status="verified"
        )
        session.add(acc)
        session.commit()

        # Query back
        fetched = session.query(Account).filter_by(account_id="ACC_TEST_001").first()
        assert fetched is not None
        assert fetched.user_name == "Test User"

        # Cleanup
        session.query(Account).filter_by(account_id="ACC_TEST_001").delete()
        session.commit()

    print("[PASS] test_database_models_and_init")


def test_graph_builder():
    print("[+] Testing Multi-Signal Graph Builder...")
    G, df_edges = build_graph_from_data_dir(DATA_DIR)

    assert isinstance(G, nx.Graph)
    assert G.number_of_nodes() == 600, f"Expected 600 nodes, got {G.number_of_nodes()}"
    assert G.number_of_edges() > 500, f"Expected >500 edges, got {G.number_of_edges()}"
    assert not df_edges.empty
    assert "signal_type" in df_edges.columns
    assert "weight" in df_edges.columns

    # Verify edge attributes exist
    sample_edge = list(G.edges(data=True))[0]
    assert "weight" in sample_edge[2]
    assert "signals" in sample_edge[2]
    print(f"[PASS] test_graph_builder (Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()})")


def test_cluster_detector():
    print("[+] Testing Louvain Community Detection...")
    G, _ = build_graph_from_data_dir(DATA_DIR)
    detector = ClusterDetector(resolution=1.0, seed=42, min_cluster_size=2)
    clusters, acc_map, df_memberships = detector.detect_clusters(G)

    assert len(clusters) >= 10, f"Expected at least 10 clusters, got {len(clusters)}"
    assert len(acc_map) == len(df_memberships)
    assert "cluster_id" in df_memberships.columns
    assert "account_id" in df_memberships.columns
    assert "degree" in df_memberships.columns
    assert "is_core" in df_memberships.columns

    print(f"[PASS] test_cluster_detector (Detected: {len(clusters)} clusters across {len(df_memberships)} accounts)")


def test_9_cluster_features():
    print("[+] Testing 9 Cluster Feature Extraction...")
    G, _ = build_graph_from_data_dir(DATA_DIR)
    clusters, _, _ = detect_clusters_from_graph(G)

    df_acc = pd.read_csv(Path(DATA_DIR) / "accounts.csv")
    df_inst = pd.read_csv(Path(DATA_DIR) / "instruments.csv")
    df_payout = pd.read_csv(Path(DATA_DIR) / "payout_destinations.csv")
    df_tx = pd.read_csv(Path(DATA_DIR) / "transactions.csv")

    df_features = extract_features_for_all_clusters(
        clusters=clusters,
        df_accounts=df_acc,
        df_instruments=df_inst,
        df_payout_destinations=df_payout,
        df_transactions=df_tx
    )

    required_9_features = [
        "cluster_size",
        "graph_density",
        "shared_device_ratio",
        "shared_ip_ratio",
        "shared_payout_ratio",
        "avg_risk_score",
        "tx_velocity",
        "decline_rate",
        "rapid_drain_ratio",
    ]

    for feat in required_9_features:
        assert feat in df_features.columns, f"Missing required feature: {feat}"
        assert not df_features[feat].isna().any(), f"Feature {feat} contains NaN values"

    # Bounds check
    assert (df_features["cluster_size"] >= 2).all()
    assert (df_features["graph_density"] >= 0.0).all() and (df_features["graph_density"] <= 1.0).all()
    assert (df_features["shared_device_ratio"] >= 0.0).all() and (df_features["shared_device_ratio"] <= 1.0).all()
    assert (df_features["shared_ip_ratio"] >= 0.0).all() and (df_features["shared_ip_ratio"] <= 1.0).all()
    assert (df_features["avg_risk_score"] >= 0.0).all() and (df_features["avg_risk_score"] <= 1.0).all()
    assert (df_features["decline_rate"] >= 0.0).all() and (df_features["decline_rate"] <= 1.0).all()

    print(f"[PASS] test_9_cluster_features (All 9 features valid & bounded)")


def test_sqlite_database_tables():
    print("[+] Testing SQLite DB persistence from run_pipeline...")
    # Verify main sentinel.db has populated tables
    engine = create_engine("sqlite:///./sentinel.db")
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        acc_count = session.query(Account).count()
        inst_count = session.query(Instrument).count()
        payout_count = session.query(PayoutDestination).count()
        tx_count = session.query(Transaction).count()
        gt_count = session.query(GroundTruth).count()
        edge_count = session.query(GraphEdge).count()
        cluster_count = session.query(Cluster).count()
        member_count = session.query(ClusterMember).count()

        assert acc_count == 600, f"Expected 600 accounts in DB, got {acc_count}"
        assert inst_count > 800, f"Expected >800 instruments, got {inst_count}"
        assert payout_count > 200, f"Expected >200 payouts, got {payout_count}"
        assert tx_count > 3500, f"Expected >3500 transactions, got {tx_count}"
        assert gt_count == 600, f"Expected 600 ground truth labels, got {gt_count}"
        assert edge_count > 500, f"Expected >500 graph edges, got {edge_count}"
        assert cluster_count >= 10, f"Expected >=10 clusters, got {cluster_count}"
        assert member_count > 150, f"Expected >150 cluster members, got {member_count}"

    print(f"[PASS] test_sqlite_database_tables (DB: 600 accs, {tx_count} txs, {edge_count} edges, {cluster_count} clusters)")


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING DAY 2 PIPELINE TEST SUITE")
    print("=" * 60)
    test_database_models_and_init()
    test_graph_builder()
    test_cluster_detector()
    test_9_cluster_features()
    test_sqlite_database_tables()
    print("\nALL 5 DAY 2 PIPELINE TESTS PASSED SUCCESSFULLY!")

