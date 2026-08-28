#!/usr/bin/env python3
"""
Unit and Integration Tests for Synthetic Data Generator
"""

import os
import json
import pandas as pd
from pathlib import Path


DATA_DIR = Path("data")


def test_csv_files_exist():
    expected_files = [
        "accounts.csv",
        "instruments.csv",
        "payout_destinations.csv",
        "transactions.csv",
        "ground_truth.csv",
    ]
    for fname in expected_files:
        path = DATA_DIR / fname
        assert path.exists(), f"Missing expected CSV file: {fname}"
        assert path.stat().st_size > 0, f"File is empty: {fname}"
    print("[PASS] test_csv_files_exist")


def test_dataset_counts():
    df_acc = pd.read_csv(DATA_DIR / "accounts.csv")
    df_inst = pd.read_csv(DATA_DIR / "instruments.csv")
    df_payout = pd.read_csv(DATA_DIR / "payout_destinations.csv")
    df_tx = pd.read_csv(DATA_DIR / "transactions.csv")
    df_gt = pd.read_csv(DATA_DIR / "ground_truth.csv")

    assert 550 <= len(df_acc) <= 650, f"Expected ~600 accounts, got {len(df_acc)}"
    assert 3500 <= len(df_tx) <= 4500, f"Expected ~4000 transactions, got {len(df_tx)}"
    assert len(df_gt) == len(df_acc), f"Ground truth count ({len(df_gt)}) does not match accounts ({len(df_acc)})"
    assert len(df_inst) >= 800, f"Expected >=800 instruments, got {len(df_inst)}"
    assert len(df_payout) >= 200, f"Expected >=200 payout destinations, got {len(df_payout)}"
    print(f"[PASS] test_dataset_counts (Accounts: {len(df_acc)}, Txns: {len(df_tx)}, Insts: {len(df_inst)}, Payouts: {len(df_payout)})")


def test_referential_integrity():
    df_acc = pd.read_csv(DATA_DIR / "accounts.csv")
    df_inst = pd.read_csv(DATA_DIR / "instruments.csv")
    df_payout = pd.read_csv(DATA_DIR / "payout_destinations.csv")
    df_tx = pd.read_csv(DATA_DIR / "transactions.csv")
    df_gt = pd.read_csv(DATA_DIR / "ground_truth.csv")

    valid_account_ids = set(df_acc["account_id"])
    valid_inst_ids = set(df_inst["instrument_id"])
    valid_payout_ids = set(df_payout["payout_destination_id"])

    # Instruments link to valid accounts
    assert set(df_inst["account_id"]).issubset(valid_account_ids)

    # Payouts link to valid accounts
    assert set(df_payout["account_id"]).issubset(valid_account_ids)

    # Ground truth links to valid accounts
    assert set(df_gt["account_id"]) == valid_account_ids

    # Transactions link to valid accounts
    assert set(df_tx["account_id"]).issubset(valid_account_ids)

    # Transaction instruments link to valid instruments
    tx_insts = set(df_tx["instrument_id"].dropna().loc[lambda x: x != ""])
    assert tx_insts.issubset(valid_inst_ids)

    # Transaction payouts link to valid payouts
    tx_payouts = set(df_tx["payout_destination_id"].dropna().loc[lambda x: x != ""])
    assert tx_payouts.issubset(valid_payout_ids)
    print("[PASS] test_referential_integrity")


def test_ground_truth_rings_and_clusters():
    df_gt = pd.read_csv(DATA_DIR / "ground_truth.csv")

    # Check 10 abuse rings
    abuse_rings = [
        "RING_01_CARD_TESTING",
        "RING_02_CARD_TESTING",
        "RING_03_CARD_TESTING",
        "RING_04_CARD_TESTING",
        "RING_05_PROMO_ABUSE",
        "RING_06_PROMO_ABUSE",
        "RING_07_PROMO_ABUSE",
        "RING_08_CASHOUT",
        "RING_09_CASHOUT",
        "RING_10_CASHOUT",
    ]
    for ring in abuse_rings:
        ring_df = df_gt[df_gt["ring_id"] == ring]
        assert len(ring_df) >= 8, f"Abuse ring {ring} has too few members ({len(ring_df)})"
        assert (ring_df["is_abuse"] == True).all(), f"Abuse ring {ring} has non-abuse labels"

    # Check 3 legit clusters
    legit_clusters = [
        "LEGIT_CLUSTER_01_CAMPUS_IP",
        "LEGIT_CLUSTER_02_HOUSEHOLD",
        "LEGIT_CLUSTER_03_LANDLORD",
    ]
    for cluster in legit_clusters:
        cluster_df = df_gt[df_gt["ring_id"] == cluster]
        assert len(cluster_df) >= 10, f"Legit cluster {cluster} has too few members ({len(cluster_df)})"
        assert (cluster_df["is_abuse"] == False).all(), f"Legit cluster {cluster} has abuse labels"

    # Check organic legit accounts
    organic_df = df_gt[df_gt["ring_id"] == "ORGANIC_LEGIT"]
    assert len(organic_df) >= 300, f"Expected >=300 organic legit accounts, got {len(organic_df)}"
    assert (organic_df["is_abuse"] == False).all()
    print("[PASS] test_ground_truth_rings_and_clusters (10 Abuse Rings + 3 Legit Clusters + Organic Verified)")


def test_abuse_pattern_characteristics():
    df_tx = pd.read_csv(DATA_DIR / "transactions.csv")
    df_gt = pd.read_csv(DATA_DIR / "ground_truth.csv")
    merged = df_tx.merge(df_gt, on="account_id")

    # Card testing rings should have high decline rates
    card_testing_tx = merged[merged["ring_id"].isin([
        "RING_01_CARD_TESTING", "RING_02_CARD_TESTING", "RING_03_CARD_TESTING", "RING_04_CARD_TESTING"
    ])]
    decline_count = card_testing_tx["status"].str.startswith("declined").sum()
    decline_rate = decline_count / len(card_testing_tx)
    assert decline_rate >= 0.65, f"Card testing rings should have >=65% decline rate, got {decline_rate:.2%}"

    # Legit campus cluster should have high success rate (>95%)
    campus_tx = merged[merged["ring_id"] == "LEGIT_CLUSTER_01_CAMPUS_IP"]
    campus_success_rate = (campus_tx["status"] == "settled").sum() / len(campus_tx)
    assert campus_success_rate >= 0.95, f"Campus cluster should have high success rate, got {campus_success_rate:.2%}"
    print(f"[PASS] test_abuse_pattern_characteristics (Card testing decline rate: {decline_rate:.1%}, Campus success rate: {campus_success_rate:.1%})")


if __name__ == "__main__":
    print("Running synthetic data integrity tests...")
    test_csv_files_exist()
    test_dataset_counts()
    test_referential_integrity()
    test_ground_truth_rings_and_clusters()
    test_abuse_pattern_characteristics()
    print("\nALL 5 TEST SUITES PASSED SUCCESSFULLY!")

