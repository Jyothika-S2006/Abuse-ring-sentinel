"""
Feature Extraction Pipeline for Abuse Ring Sentinel.
Computes the 9 core cluster-level graph and transactional features per detected cluster,
plus auxiliary context metrics for downstream ML and LLM agents.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import networkx as nx
import numpy as np
import pandas as pd


class ClusterFeatureExtractor:
    def __init__(
        self,
        df_accounts: pd.DataFrame,
        df_instruments: Optional[pd.DataFrame] = None,
        df_payout_destinations: Optional[pd.DataFrame] = None,
        df_transactions: Optional[pd.DataFrame] = None,
    ):
        self.df_accounts = df_accounts.set_index("account_id", drop=False)
        self.df_instruments = df_instruments if df_instruments is not None else pd.DataFrame()
        self.df_payouts = df_payout_destinations if df_payout_destinations is not None else pd.DataFrame()
        self.df_transactions = df_transactions if df_transactions is not None else pd.DataFrame()

    def compute_cluster_features(
        self,
        cluster_id: str,
        member_ids: List[str],
        subgraph: Optional[nx.Graph] = None
    ) -> Dict[str, Any]:
        """
        Computes the 9 core features for a single candidate cluster.
        """
        n_members = len(member_ids)
        if n_members == 0:
            return {}

        # 1. Account Metadata Slice
        acc_slice = self.df_accounts.loc[self.df_accounts.index.intersection(member_ids)]

        # 2. Transaction Slice
        if not self.df_transactions.empty:
            tx_slice = self.df_transactions[self.df_transactions["account_id"].isin(member_ids)]
        else:
            tx_slice = pd.DataFrame()

        # 3. Payout Destination Slice
        if not self.df_payouts.empty:
            payout_slice = self.df_payouts[self.df_payouts["account_id"].isin(member_ids)]
        else:
            payout_slice = pd.DataFrame()

        # 4. Instruments Slice
        if not self.df_instruments.empty:
            inst_slice = self.df_instruments[self.df_instruments["account_id"].isin(member_ids)]
        else:
            inst_slice = pd.DataFrame()

        # -------------------------------------------------------------------
        # Compute the 9 Core Features
        # -------------------------------------------------------------------

        # Feature 1: Cluster Size
        f1_cluster_size = int(n_members)

        # Feature 2: Graph Density
        if subgraph is not None and n_members > 1:
            f2_graph_density = float(nx.density(subgraph))
        else:
            f2_graph_density = 0.0

        # Feature 3: Shared Device Ratio
        unique_devices = acc_slice["device_id"].dropna().nunique()
        f3_shared_device_ratio = float(max(0.0, 1.0 - (unique_devices / n_members))) if n_members > 0 else 0.0

        # Feature 4: Shared IP Ratio
        unique_ips = acc_slice["ip_address"].dropna().nunique()
        f4_shared_ip_ratio = float(max(0.0, 1.0 - (unique_ips / n_members))) if n_members > 0 else 0.0

        # Feature 5: Shared Payout Destination Ratio
        if not payout_slice.empty and "destination_hash" in payout_slice.columns:
            dest_counts = payout_slice["destination_hash"].value_counts()
            shared_hashes = set(dest_counts[dest_counts > 1].index)
            accounts_sharing_payout = payout_slice[payout_slice["destination_hash"].isin(shared_hashes)]["account_id"].nunique()
            f5_shared_payout_ratio = float(accounts_sharing_payout / n_members)
        else:
            f5_shared_payout_ratio = 0.0

        # Feature 6: Average Risk Score
        f6_avg_risk_score = float(acc_slice["risk_score"].mean()) if not acc_slice.empty else 0.0

        # Feature 7: Transaction Velocity (Average Txns per Account)
        n_txns = len(tx_slice)
        f7_tx_velocity = float(n_txns / n_members) if n_members > 0 else 0.0

        # Feature 8: Decline Rate (Ratio of failed/declined transactions)
        if n_txns > 0:
            declined_mask = (
                tx_slice["status"].str.startswith("declined") |
                (tx_slice["status"] == "failed")
            )
            f8_decline_rate = float(declined_mask.sum() / n_txns)
        else:
            f8_decline_rate = 0.0

        # Feature 9: Rapid Drain / Cash-Out Ratio
        # Measures ratio of quick deposits-to-withdrawals (< 60 mins) or P2P/withdrawal flow
        f9_rapid_drain_ratio = self._compute_rapid_drain_ratio(tx_slice)

        # -------------------------------------------------------------------
        # Additional Contextual Features
        # -------------------------------------------------------------------
        total_volume = float(tx_slice["amount"].sum()) if n_txns > 0 else 0.0
        unverified_count = (acc_slice["kyc_status"] != "verified").sum()
        unverified_kyc_ratio = float(unverified_count / n_members) if n_members > 0 else 0.0

        primary_signal = self._determine_primary_signal(
            f3_shared_device_ratio, f4_shared_ip_ratio, f5_shared_payout_ratio, subgraph
        )
        detected_ring_type = self._heuristic_ring_type(
            f8_decline_rate, f9_rapid_drain_ratio, f5_shared_payout_ratio, f6_avg_risk_score, primary_signal
        )

        return {
            "cluster_id": cluster_id,
            "cluster_size": f1_cluster_size,
            "graph_density": round(f2_graph_density, 4),
            "shared_device_ratio": round(f3_shared_device_ratio, 4),
            "shared_ip_ratio": round(f4_shared_ip_ratio, 4),
            "shared_payout_ratio": round(f5_shared_payout_ratio, 4),
            "avg_risk_score": round(f6_avg_risk_score, 4),
            "tx_velocity": round(f7_tx_velocity, 2),
            "decline_rate": round(f8_decline_rate, 4),
            "rapid_drain_ratio": round(f9_rapid_drain_ratio, 4),
            "total_volume": round(total_volume, 2),
            "unverified_kyc_ratio": round(unverified_kyc_ratio, 4),
            "primary_shared_signal": primary_signal,
            "detected_ring_type": detected_ring_type,
        }

    def _compute_rapid_drain_ratio(self, tx_slice: pd.DataFrame) -> float:
        """
        Calculates the proportion of accounts in cluster that execute rapid deposit -> withdrawal sequences (<1 hour)
        or have high cash-out/P2P transfer volume relative to normal spend.
        """
        if tx_slice.empty or len(tx_slice) < 2:
            return 0.0

        # Check for rapid turnaround between deposit and withdrawal within same account
        rapid_drain_accounts = 0
        grouped = tx_slice.groupby("account_id")

        for acc_id, acc_tx in grouped:
            has_deposit = (acc_tx["transaction_type"] == "deposit").any()
            has_withdrawal = (acc_tx["transaction_type"].isin(["withdrawal", "p2p_transfer"])).any()

            if has_deposit and has_withdrawal:
                # Sort by timestamp
                sorted_tx = acc_tx.sort_values("timestamp")
                prev_time = None
                prev_type = None
                is_rapid = False

                for _, tx in sorted_tx.iterrows():
                    try:
                        curr_time = datetime.fromisoformat(str(tx["timestamp"]))
                    except Exception:
                        continue

                    if prev_time and prev_type == "deposit" and tx["transaction_type"] in ["withdrawal", "p2p_transfer"]:
                        delta_minutes = (curr_time - prev_time).total_seconds() / 60.0
                        if 0 <= delta_minutes <= 60:
                            is_rapid = True
                            break

                    prev_time = curr_time
                    prev_type = tx["transaction_type"]

                if is_rapid:
                    rapid_drain_accounts += 1

        total_active_accounts = len(grouped)
        if total_active_accounts == 0:
            return 0.0
        return float(rapid_drain_accounts / total_active_accounts)

    def _determine_primary_signal(
        self,
        shared_dev_ratio: float,
        shared_ip_ratio: float,
        shared_payout_ratio: float,
        subgraph: Optional[nx.Graph]
    ) -> str:
        signals = {
            "shared_device": shared_dev_ratio * 1.2,
            "shared_payout_destination": shared_payout_ratio * 1.2,
            "shared_ip": shared_ip_ratio * 0.8,
        }
        if subgraph is not None and subgraph.number_of_edges() > 0:
            edge_signals = []
            for _, _, data in subgraph.edges(data=True):
                s = data.get("signals", [])
                edge_signals.extend(s if isinstance(s, list) else [s])
            if "shared_card_fingerprint" in edge_signals:
                signals["shared_card_fingerprint"] = 0.95
            if "p2p_transfer" in edge_signals:
                signals["p2p_transfer"] = 0.85

        best_signal = max(signals.items(), key=lambda x: x[1])
        return best_signal[0] if best_signal[1] > 0.05 else "isolated_or_mixed"

    def _heuristic_ring_type(
        self,
        decline_rate: float,
        rapid_drain_ratio: float,
        shared_payout_ratio: float,
        avg_risk_score: float,
        primary_signal: str
    ) -> str:
        if decline_rate >= 0.50:
            return "card_testing"
        if rapid_drain_ratio >= 0.30 or (shared_payout_ratio >= 0.40 and avg_risk_score >= 0.60):
            return "cash_out"
        if primary_signal in ["shared_device", "shared_ip"] and avg_risk_score >= 0.70:
            return "promo_abuse"
        if avg_risk_score <= 0.15:
            return "legit_lookalike"
        return "suspicious_multi_signal"


def extract_features_for_all_clusters(
    clusters: List[Dict[str, Any]],
    df_accounts: pd.DataFrame,
    df_instruments: Optional[pd.DataFrame] = None,
    df_payout_destinations: Optional[pd.DataFrame] = None,
    df_transactions: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Computes 9 features for all candidate clusters and returns a DataFrame.
    """
    print(f"[+] Computing 9 Cluster Features across {len(clusters)} candidate clusters...")
    extractor = ClusterFeatureExtractor(
        df_accounts=df_accounts,
        df_instruments=df_instruments,
        df_payout_destinations=df_payout_destinations,
        df_transactions=df_transactions,
    )

    feature_rows = []
    for c in clusters:
        feat = extractor.compute_cluster_features(
            cluster_id=c["cluster_id"],
            member_ids=c["member_ids"],
            subgraph=c.get("subgraph")
        )
        feature_rows.append(feat)

    df_features = pd.DataFrame(feature_rows)
    print(f"[OK] Computed features for {len(df_features)} clusters.")
    return df_features

