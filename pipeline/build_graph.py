"""
Multi-Signal Graph Construction Pipeline for Abuse Ring Sentinel.
Builds a NetworkX graph connecting accounts based on shared devices, IPs,
card fingerprints/BINs, payout destination hashes, phone clusters, and transaction flows.
"""

import itertools
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
import pandas as pd


# Signal Weights Configuration
DEFAULT_SIGNAL_WEIGHTS = {
    "shared_device": 1.0,
    "shared_card_fingerprint": 1.0,
    "shared_payout_destination": 1.0,
    "shared_phone": 0.8,
    "shared_phone_prefix": 0.5,
    "p2p_transfer": 0.8,
    "shared_ip": 0.4,
    "shared_ip_subnet": 0.35,
    "shared_prepaid_bin": 0.5,
}


class MultiSignalGraphBuilder:
    def __init__(self, signal_weights: Optional[Dict[str, float]] = None):
        self.weights = signal_weights or DEFAULT_SIGNAL_WEIGHTS

    def build_graph(
        self,
        df_accounts: pd.DataFrame,
        df_instruments: Optional[pd.DataFrame] = None,
        df_payout_destinations: Optional[pd.DataFrame] = None,
        df_transactions: Optional[pd.DataFrame] = None,
    ) -> Tuple[nx.Graph, pd.DataFrame]:
        """
        Builds an undirected NetworkX graph where nodes are accounts and edges
        represent shared identity, payment, or transactional signals.
        """
        print(f"[+] Building Multi-Signal Entity Graph for {len(df_accounts)} accounts...")
        G = nx.Graph()

        # 1. Add Account Nodes
        for _, row in df_accounts.iterrows():
            acc_id = str(row["account_id"])
            G.add_node(
                acc_id,
                account_id=acc_id,
                user_name=row.get("user_name", ""),
                email=row.get("email", ""),
                phone_number=row.get("phone_number", ""),
                ip_address=row.get("ip_address", ""),
                device_id=row.get("device_id", ""),
                account_status=row.get("account_status", "active"),
                risk_score=float(row.get("risk_score", 0.0)),
                kyc_status=row.get("kyc_status", "unverified"),
                created_at=str(row.get("created_at", "")),
            )

        raw_edges: List[Dict[str, any]] = []

        # 2. Shared Device IDs (Exact Fingerprint Match)
        if "device_id" in df_accounts.columns:
            device_groups = df_accounts.groupby("device_id")["account_id"].apply(list)
            for dev_id, acc_list in device_groups.items():
                if dev_id and len(acc_list) > 1:
                    for a1, a2 in itertools.combinations(acc_list, 2):
                        raw_edges.append({
                            "source_account_id": a1,
                            "target_account_id": a2,
                            "signal_type": "shared_device",
                            "weight": self.weights.get("shared_device", 1.0),
                            "signal_detail": f"Shared registration device: {dev_id}"
                        })

        # 3. Shared Exact IP Addresses
        if "ip_address" in df_accounts.columns:
            ip_groups = df_accounts.groupby("ip_address")["account_id"].apply(list)
            for ip_addr, acc_list in ip_groups.items():
                if ip_addr and len(acc_list) > 1:
                    for a1, a2 in itertools.combinations(acc_list, 2):
                        raw_edges.append({
                            "source_account_id": a1,
                            "target_account_id": a2,
                            "signal_type": "shared_ip",
                            "weight": self.weights.get("shared_ip", 0.4),
                            "signal_detail": f"Shared registration IP: {ip_addr}"
                        })

            # Subnet /24 clustering (for botnets spanning dedicated subnets like 185.220.101.xx)
            df_accounts_copy = df_accounts.copy()
            df_accounts_copy["ip_subnet_24"] = df_accounts_copy["ip_address"].apply(
                lambda x: x.rsplit(".", 1)[0] if isinstance(x, str) and "." in x else ""
            )
            subnet_groups = df_accounts_copy.groupby("ip_subnet_24")["account_id"].apply(list)
            for subnet, acc_list in subnet_groups.items():
                # Only link subnets if there is a concentration of accounts (e.g. >= 6 accounts in same /24)
                if subnet and len(acc_list) >= 6:
                    for a1, a2 in itertools.combinations(acc_list, 2):
                        raw_edges.append({
                            "source_account_id": a1,
                            "target_account_id": a2,
                            "signal_type": "shared_ip_subnet",
                            "weight": self.weights.get("shared_ip_subnet", 0.35),
                            "signal_detail": f"Shared /24 subnet: {subnet}.0/24"
                        })

        # 4. Shared Phone Numbers & Phone Prefixes
        if "phone_number" in df_accounts.columns:
            phone_groups = df_accounts.groupby("phone_number")["account_id"].apply(list)
            for phone, acc_list in phone_groups.items():
                if phone and len(acc_list) > 1:
                    for a1, a2 in itertools.combinations(acc_list, 2):
                        raw_edges.append({
                            "source_account_id": a1,
                            "target_account_id": a2,
                            "signal_type": "shared_phone",
                            "weight": self.weights.get("shared_phone", 0.8),
                            "signal_detail": f"Shared phone number: {phone}"
                        })

            # Concentrated sequential phone blocks (e.g. +1-555-400-00xx)
            df_accounts_copy["phone_prefix"] = df_accounts_copy["phone_number"].apply(
                lambda x: x[:-2] if isinstance(x, str) and len(x) > 4 else ""
            )
            prefix_groups = df_accounts_copy.groupby("phone_prefix")["account_id"].apply(list)
            for pfx, acc_list in prefix_groups.items():
                if pfx and len(acc_list) >= 6:
                    for a1, a2 in itertools.combinations(acc_list, 2):
                        raw_edges.append({
                            "source_account_id": a1,
                            "target_account_id": a2,
                            "signal_type": "shared_phone_prefix",
                            "weight": self.weights.get("shared_phone_prefix", 0.5),
                            "signal_detail": f"Shared phone prefix cluster: {pfx}xx"
                        })

        # 5. Shared Payment Instruments (Card Fingerprints & Prepaid BINs)
        if df_instruments is not None and not df_instruments.empty:
            # Exact Card Fingerprint Overlap (reused card tokens)
            if "card_fingerprint" in df_instruments.columns:
                fp_groups = df_instruments.groupby("card_fingerprint")["account_id"].unique()
                for fp, acc_list in fp_groups.items():
                    if fp and len(acc_list) > 1:
                        for a1, a2 in itertools.combinations(acc_list, 2):
                            raw_edges.append({
                                "source_account_id": a1,
                                "target_account_id": a2,
                                "signal_type": "shared_card_fingerprint",
                                "weight": self.weights.get("shared_card_fingerprint", 1.0),
                                "signal_detail": f"Shared card fingerprint token: {fp}"
                            })

            # Concentrated Virtual / Prepaid BINs (e.g. 510510)
            if "card_bin" in df_instruments.columns and "is_prepaid" in df_instruments.columns:
                prepaid_insts = df_instruments[df_instruments["is_prepaid"] == True]
                bin_groups = prepaid_insts.groupby("card_bin")["account_id"].unique()
                for bin_val, acc_list in bin_groups.items():
                    if bin_val and len(acc_list) >= 6:
                        for a1, a2 in itertools.combinations(acc_list, 2):
                            raw_edges.append({
                                "source_account_id": a1,
                                "target_account_id": a2,
                                "signal_type": "shared_prepaid_bin",
                                "weight": self.weights.get("shared_prepaid_bin", 0.5),
                                "signal_detail": f"Concentrated prepaid/virtual BIN: {bin_val}"
                            })

        # 6. Shared Payout Destinations (Destination Hashes / Crypto Wallets)
        if df_payout_destinations is not None and not df_payout_destinations.empty:
            if "destination_hash" in df_payout_destinations.columns:
                dest_groups = df_payout_destinations.groupby("destination_hash")["account_id"].unique()
                for d_hash, acc_list in dest_groups.items():
                    if d_hash and len(acc_list) > 1:
                        for a1, a2 in itertools.combinations(acc_list, 2):
                            raw_edges.append({
                                "source_account_id": a1,
                                "target_account_id": a2,
                                "signal_type": "shared_payout_destination",
                                "weight": self.weights.get("shared_payout_destination", 1.0),
                                "signal_detail": f"Shared payout destination hash: {d_hash}"
                            })

        # 7. Direct Transaction Relationships (e.g. P2P transfers)
        if df_transactions is not None and not df_transactions.empty:
            p2p_txns = df_transactions[
                (df_transactions["transaction_type"] == "p2p_transfer") |
                (df_transactions["merchant_id"].str.contains("Transfer to ACC_", na=False))
            ]
            for _, tx in p2p_txns.iterrows():
                sender = str(tx["account_id"])
                merchant = str(tx["merchant_id"])
                match = re.search(r"ACC_\d+", merchant)
                if match:
                    recipient = match.group(0)
                    if G.has_node(recipient) and sender != recipient:
                        raw_edges.append({
                            "source_account_id": sender,
                            "target_account_id": recipient,
                            "signal_type": "p2p_transfer",
                            "weight": self.weights.get("p2p_transfer", 0.8),
                            "signal_detail": f"P2P Transfer of ${tx['amount']:.2f} (Txn: {tx['transaction_id']})"
                        })

        # 8. Aggregate & Merge Multi-Signal Edges
        edge_map: Dict[Tuple[str, str], Dict[str, any]] = {}
        for edge in raw_edges:
            u, v = sorted([edge["source_account_id"], edge["target_account_id"]])
            key = (u, v)
            if key not in edge_map:
                edge_map[key] = {
                    "source_account_id": u,
                    "target_account_id": v,
                    "weight": 0.0,
                    "signals": [],
                    "details": []
                }
            edge_map[key]["weight"] += edge["weight"]
            if edge["signal_type"] not in edge_map[key]["signals"]:
                edge_map[key]["signals"].append(edge["signal_type"])
            edge_map[key]["details"].append(edge["signal_detail"])

        # Add consolidated edges to NetworkX
        consolidated_edges = []
        for (u, v), data in edge_map.items():
            G.add_edge(
                u,
                v,
                weight=round(data["weight"], 3),
                signals=data["signals"],
                signals_str=",".join(data["signals"]),
                details=data["details"],
                detail_str="; ".join(data["details"])
            )
            consolidated_edges.append({
                "source_account_id": u,
                "target_account_id": v,
                "signal_type": ",".join(data["signals"]),
                "weight": round(data["weight"], 3),
                "signal_detail": "; ".join(data["details"])
            })

        df_edges = pd.DataFrame(consolidated_edges)
        print(f"[OK] Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges across {len(raw_edges)} raw signals.")
        return G, df_edges


def build_graph_from_data_dir(
    data_dir: str = "data"
) -> Tuple[nx.Graph, pd.DataFrame]:
    """Loads CSVs from data_dir and builds the multi-signal graph."""
    path = Path(data_dir)
    df_acc = pd.read_csv(path / "accounts.csv")
    df_inst = pd.read_csv(path / "instruments.csv") if (path / "instruments.csv").exists() else None
    df_payout = pd.read_csv(path / "payout_destinations.csv") if (path / "payout_destinations.csv").exists() else None
    df_tx = pd.read_csv(path / "transactions.csv") if (path / "transactions.csv").exists() else None

    builder = MultiSignalGraphBuilder()
    return builder.build_graph(df_acc, df_inst, df_payout, df_tx)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Multi-Signal Entity Graph Builder")
    parser.add_argument("--data-dir", type=str, default="data", help="Directory containing CSV files")
    args = parser.parse_args()

    G, df_edges = build_graph_from_data_dir(args.data_dir)
    print(f"Top 5 connected edge pairs:\n{df_edges.head(5)}")
