#!/usr/bin/env python3
"""
Abuse Ring Sentinel - Pipeline Runner
=====================================
Orchestrates the complete Day 2 data pipeline:
1. Initializes SQLite Database (sentinel.db) and loads CSV records.
2. Builds Multi-Signal Entity Graph (NetworkX) from shared signals.
3. Detects Candidate Abuse Rings via Louvain Community Detection.
4. Computes 9 Graph & Transaction Features per Candidate Cluster.
5. Populates SQLite Tables (clusters, cluster_members, graph_edges).
6. Compares Detected Clusters against Ground Truth.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from sqlalchemy.orm import Session

# Import project modules
from backend.db import (
    Account,
    Cluster,
    ClusterMember,
    GraphEdge,
    GroundTruth,
    Instrument,
    PayoutDestination,
    Transaction,
    get_engine,
    get_session_factory,
    init_db,
)
from pipeline.build_graph import MultiSignalGraphBuilder
from pipeline.cluster_features import extract_features_for_all_clusters
from pipeline.detect_clusters import ClusterDetector


def run_pipeline(
    data_dir: str = "data",
    db_url: Optional[str] = None,
    resolution: float = 1.0,
    min_cluster_size: int = 2,
    seed: int = 42
):
    print("=" * 65)
    print("      ABUSE RING SENTINEL - GRAPH & CLUSTER PIPELINE")
    print("=" * 65)

    data_path = Path(data_dir)
    if not (data_path / "accounts.csv").exists():
        raise FileNotFoundError(f"accounts.csv not found in {data_dir}. Run generate_synthetic_data.py first.")

    # 1. Initialize Database
    print(f"\n[Step 1/5] Initializing SQLite database...")
    engine = init_db(db_url)
    session_factory = get_session_factory(db_url)

    # 2. Ingest CSVs into DataFrames & DB
    print(f"\n[Step 2/5] Ingesting CSV datasets from '{data_dir}'...")
    df_acc = pd.read_csv(data_path / "accounts.csv")
    df_inst = pd.read_csv(data_path / "instruments.csv") if (data_path / "instruments.csv").exists() else pd.DataFrame()
    df_payout = pd.read_csv(data_path / "payout_destinations.csv") if (data_path / "payout_destinations.csv").exists() else pd.DataFrame()
    df_tx = pd.read_csv(data_path / "transactions.csv") if (data_path / "transactions.csv").exists() else pd.DataFrame()
    df_gt = pd.read_csv(data_path / "ground_truth.csv") if (data_path / "ground_truth.csv").exists() else pd.DataFrame()

    with session_factory() as session:
        # Clear existing raw data
        session.query(ClusterMember).delete()
        session.query(Cluster).delete()
        session.query(GraphEdge).delete()
        session.query(Transaction).delete()
        session.query(PayoutDestination).delete()
        session.query(Instrument).delete()
        session.query(GroundTruth).delete()
        session.query(Account).delete()
        session.commit()

        # Insert accounts
        accounts_to_insert = [
            Account(
                account_id=str(r["account_id"]),
                created_at=str(r["created_at"]),
                user_name=str(r["user_name"]),
                email=str(r["email"]),
                phone_number=str(r["phone_number"]),
                ip_address=str(r["ip_address"]),
                device_id=str(r["device_id"]),
                account_status=str(r.get("account_status", "active")),
                risk_score=float(r.get("risk_score", 0.0)),
                kyc_status=str(r.get("kyc_status", "unverified")),
            )
            for _, r in df_acc.iterrows()
        ]
        session.bulk_save_objects(accounts_to_insert)

        # Insert instruments
        if not df_inst.empty:
            insts_to_insert = [
                Instrument(
                    instrument_id=str(r["instrument_id"]),
                    account_id=str(r["account_id"]),
                    instrument_type=str(r["instrument_type"]),
                    card_fingerprint=str(r["card_fingerprint"]),
                    card_bin=str(r["card_bin"]),
                    card_last4=str(r["card_last4"]),
                    card_network=str(r["card_network"]),
                    issuer_bank=str(r["issuer_bank"]),
                    country=str(r.get("country", "US")),
                    is_prepaid=bool(r.get("is_prepaid", False)),
                    added_at=str(r["added_at"]),
                )
                for _, r in df_inst.iterrows()
            ]
            session.bulk_save_objects(insts_to_insert)

        # Insert payout destinations
        if not df_payout.empty:
            payouts_to_insert = [
                PayoutDestination(
                    payout_destination_id=str(r["payout_destination_id"]),
                    account_id=str(r["account_id"]),
                    destination_type=str(r["destination_type"]),
                    destination_hash=str(r["destination_hash"]),
                    routing_or_bank_code=str(r["routing_or_bank_code"]),
                    holder_name=str(r["holder_name"]),
                    status=str(r.get("status", "active")),
                    created_at=str(r["created_at"]),
                )
                for _, r in df_payout.iterrows()
            ]
            session.bulk_save_objects(payouts_to_insert)

        # Insert transactions
        if not df_tx.empty:
            tx_to_insert = [
                Transaction(
                    transaction_id=str(r["transaction_id"]),
                    account_id=str(r["account_id"]),
                    instrument_id=str(r["instrument_id"]) if pd.notna(r.get("instrument_id")) else "",
                    payout_destination_id=str(r["payout_destination_id"]) if pd.notna(r.get("payout_destination_id")) else "",
                    timestamp=str(r["timestamp"]),
                    amount=float(r["amount"]),
                    currency=str(r.get("currency", "USD")),
                    transaction_type=str(r["transaction_type"]),
                    status=str(r["status"]),
                    merchant_id=str(r["merchant_id"]),
                    merchant_category=str(r["merchant_category"]),
                    ip_address=str(r.get("ip_address", "")) if pd.notna(r.get("ip_address")) else "",
                    device_id=str(r.get("device_id", "")) if pd.notna(r.get("device_id")) else "",
                )
                for _, r in df_tx.iterrows()
            ]
            session.bulk_save_objects(tx_to_insert)

        # Insert ground truth
        if not df_gt.empty:
            gt_to_insert = [
                GroundTruth(
                    account_id=str(r["account_id"]),
                    is_abuse=bool(r["is_abuse"]),
                    ring_id=str(r["ring_id"]),
                    ring_type=str(r["ring_type"]),
                    shared_signals=str(r.get("shared_signals", "[]")),
                    notes=str(r.get("notes", "")) if pd.notna(r.get("notes")) else "",
                )
                for _, r in df_gt.iterrows()
            ]
            session.bulk_save_objects(gt_to_insert)

        session.commit()
        print(f"[OK] Ingested: {len(df_acc)} accounts, {len(df_inst)} instruments, {len(df_payout)} payouts, {len(df_tx)} txns, {len(df_gt)} ground truth.")

    # 3. Build Graph
    print(f"\n[Step 3/5] Building Multi-Signal Entity Graph...")
    builder = MultiSignalGraphBuilder()
    G, df_edges = builder.build_graph(df_acc, df_inst, df_payout, df_tx)

    # 4. Detect Communities & Extract 9 Features
    print(f"\n[Step 4/5] Detecting Candidate Clusters & Computing Features...")
    detector = ClusterDetector(resolution=resolution, seed=seed, min_cluster_size=min_cluster_size)
    clusters, acc_cluster_map, df_memberships = detector.detect_clusters(G)

    df_features = extract_features_for_all_clusters(
        clusters=clusters,
        df_accounts=df_acc,
        df_instruments=df_inst,
        df_payout_destinations=df_payout,
        df_transactions=df_tx,
    )

    # 5. Persist Results to SQLite
    print(f"\n[Step 5/5] Saving Graph Edges, Clusters, and Memberships to SQLite...")
    with session_factory() as session:
        # Save Graph Edges
        edge_records = [
            GraphEdge(
                source_account_id=str(r["source_account_id"]),
                target_account_id=str(r["target_account_id"]),
                signal_type=str(r["signal_type"]),
                weight=float(r["weight"]),
                signal_detail=str(r.get("signal_detail", "")),
            )
            for _, r in df_edges.iterrows()
        ]
        session.bulk_save_objects(edge_records)

        # Save Clusters
        cluster_records = [
            Cluster(
                cluster_id=str(r["cluster_id"]),
                cluster_size=int(r["cluster_size"]),
                graph_density=float(r["graph_density"]),
                shared_device_ratio=float(r["shared_device_ratio"]),
                shared_ip_ratio=float(r["shared_ip_ratio"]),
                shared_payout_ratio=float(r["shared_payout_ratio"]),
                avg_risk_score=float(r["avg_risk_score"]),
                tx_velocity=float(r["tx_velocity"]),
                decline_rate=float(r["decline_rate"]),
                rapid_drain_ratio=float(r["rapid_drain_ratio"]),
                total_volume=float(r.get("total_volume", 0.0)),
                unverified_kyc_ratio=float(r.get("unverified_kyc_ratio", 0.0)),
                primary_shared_signal=str(r.get("primary_shared_signal", "")),
                detected_ring_type=str(r.get("detected_ring_type", "")),
                status="UNDER_INVESTIGATION",
            )
            for _, r in df_features.iterrows()
        ]
        session.bulk_save_objects(cluster_records)

        # Save Cluster Memberships
        member_records = [
            ClusterMember(
                cluster_id=str(r["cluster_id"]),
                account_id=str(r["account_id"]),
                degree=int(r["degree"]),
                is_core=bool(r["is_core"]),
                account_role=str(r.get("account_role", "member")),
            )
            for _, r in df_memberships.iterrows()
        ]
        session.bulk_save_objects(member_records)

        session.commit()
        print(f"[OK] Saved {len(edge_records)} edges, {len(cluster_records)} clusters, {len(member_records)} memberships.")

    # -----------------------------------------------------------------------
    # Summary Report & Alignment
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"{'DETECTED CLUSTER SUMMARY TABLE':^80}")
    print("=" * 80)
    fmt_hdr = f"{'Cluster ID':<12} | {'Size':<5} | {'Density':<7} | {'DevRat':<6} | {'IPRat':<6} | {'PayRat':<6} | {'Risk':<5} | {'Decline%':<8} | {'Drain%':<6} | {'Heuristic Type':<15}"
    print(fmt_hdr)
    print("-" * 80)
    for _, row in df_features.iterrows():
        print(
            f"{row['cluster_id']:<12} | "
            f"{row['cluster_size']:<5} | "
            f"{row['graph_density']:<7.3f} | "
            f"{row['shared_device_ratio']:<6.2f} | "
            f"{row['shared_ip_ratio']:<6.2f} | "
            f"{row['shared_payout_ratio']:<6.2f} | "
            f"{row['avg_risk_score']:<5.2f} | "
            f"{row['decline_rate']*100:<7.1f}% | "
            f"{row['rapid_drain_ratio']*100:<5.1f}% | "
            f"{row['detected_ring_type']:<15}"
        )
    print("=" * 80)

    # Cross-reference with Ground Truth
    if not df_gt.empty:
        merged = df_memberships.merge(df_gt, on="account_id")
        print("\nGround Truth Alignment Matrix (Cluster ID -> Top Planted Ring):")
        for cid, group in merged.groupby("cluster_id"):
            top_ring = group["ring_id"].value_counts().index[0]
            ring_cnt = group["ring_id"].value_counts().iloc[0]
            is_ab = group["is_abuse"].iloc[0]
            tag = "[ABUSE]" if is_ab else "[LEGIT]"
            print(f"  * {cid:<12} ({len(group)} accts) -> {tag} {top_ring} ({ring_cnt}/{len(group)} members)")

    print("\n[OK] Pipeline completed successfully!")


def main():
    parser = argparse.ArgumentParser(description="Abuse Ring Sentinel Graph & Cluster Pipeline")
    parser.add_argument("--data-dir", type=str, default="data", help="Directory with CSV files")
    parser.add_argument("--db-path", type=str, default="sentinel.db", help="SQLite database path")
    parser.add_argument("--resolution", type=float, default=1.0, help="Louvain community detection resolution")
    parser.add_argument("--min-size", type=int, default=2, help="Minimum cluster size to keep")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    db_url = f"sqlite:///./{args.db_path}"
    run_pipeline(
        data_dir=args.data_dir,
        db_url=db_url,
        resolution=args.resolution,
        min_cluster_size=args.min_size,
        seed=args.seed
    )


if __name__ == "__main__":
    main()
