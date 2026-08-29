"""
agent/tools.py
Tool functions the investigation agent can call. Reads directly from sentinel.db
using the real schema from backend/db.py.
"""

import sqlite3
import os
import math

def _db_path() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///./sentinel.db")
    if "sentinel.bd" in url:  # matches the typo fallback in db.py
        url = "sqlite:///./sentinel.db"
    path = url.replace("sqlite:///", "")
    return path.lstrip("./") or "sentinel.db"

DB_PATH = _db_path()

FEATURE_COLUMNS = [
    "cluster_size", "graph_density", "shared_device_ratio", "shared_ip_ratio",
    "shared_payout_ratio", "avg_risk_score", "tx_velocity", "decline_rate", "rapid_drain_ratio",
]


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_cluster_features(cluster_id: str) -> dict:
    """Return the 9 ML features, risk score, and heuristic ring type for a cluster."""
    conn = _connect()
    row = conn.execute(
        f"SELECT cluster_id, {', '.join(FEATURE_COLUMNS)}, "
        f"total_volume, unverified_kyc_ratio, primary_shared_signal, "
        f"detected_ring_type, status "
        f"FROM clusters WHERE cluster_id = ?",
        (cluster_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return {"error": f"cluster {cluster_id} not found"}
    return dict(row)


def get_shared_signal_evidence(cluster_id: str) -> dict:
    """Return exactly which member accounts share which signals, with counts."""
    conn = _connect()
    members = conn.execute(
        "SELECT account_id, degree, is_core, account_role "
        "FROM cluster_members WHERE cluster_id = ?",
        (cluster_id,),
    ).fetchall()
    member_ids = [m["account_id"] for m in members]
    if not member_ids:
        conn.close()
        return {"error": f"no members found for cluster {cluster_id}"}

    placeholders = ",".join("?" * len(member_ids))
    edges = conn.execute(
        f"SELECT source_account_id, target_account_id, signal_type, weight, signal_detail "
        f"FROM graph_edges WHERE source_account_id IN ({placeholders}) "
        f"AND target_account_id IN ({placeholders})",
        member_ids + member_ids,
    ).fetchall()
    conn.close()

    signal_counts = {}
    edge_list = []
    for e in edges:
        edge_list.append(dict(e))
        signal_counts[e["signal_type"]] = signal_counts.get(e["signal_type"], 0) + 1

    return {
        "cluster_id": cluster_id,
        "member_count": len(member_ids),
        "members": [dict(m) for m in members],
        "shared_signal_edges": edge_list,
        "signal_type_counts": signal_counts,
    }


def get_account_details(account_id: str) -> dict:
    """Return KYC status, account age, and a transaction summary for one account."""
    conn = _connect()
    account = conn.execute(
        "SELECT account_id, created_at, account_status, risk_score, kyc_status, "
        "ip_address, device_id, phone_number FROM accounts WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    if account is None:
        conn.close()
        return {"error": f"account {account_id} not found"}

    # NOTE: assumes transactions.status uses a literal like 'failed' for declines --
    # adjust this string if your generator uses a different value (e.g. 'DECLINED').
    tx_summary = conn.execute(
        "SELECT COUNT(*) as tx_count, "
        "SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count, "
        "AVG(amount) as avg_amount, MIN(timestamp) as first_tx, MAX(timestamp) as last_tx "
        "FROM transactions WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    conn.close()

    result = dict(account)
    result["transaction_summary"] = dict(tx_summary) if tx_summary else {}
    return result


def get_similar_historical_cases(cluster_id: str, top_k: int = 3) -> dict:
    """Return the top_k other clusters most similar to this one on the 9 features,
    limited to clusters an analyst has already reviewed (status != UNDER_INVESTIGATION)."""
    conn = _connect()
    target = conn.execute(
        f"SELECT {', '.join(FEATURE_COLUMNS)} FROM clusters WHERE cluster_id = ?", (cluster_id,)
    ).fetchone()
    if target is None:
        conn.close()
        return {"error": f"cluster {cluster_id} not found"}

    others = conn.execute(
        f"SELECT cluster_id, {', '.join(FEATURE_COLUMNS)}, status, detected_ring_type "
        f"FROM clusters WHERE cluster_id != ? AND status != 'UNDER_INVESTIGATION'",
        (cluster_id,),
    ).fetchall()
    conn.close()

    def vec(row):
        return [float(row[c] or 0.0) for c in FEATURE_COLUMNS]

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    t_vec = vec(target)
    scored = [
        {
            "cluster_id": row["cluster_id"],
            "similarity": round(cosine(t_vec, vec(row)), 3),
            "status": row["status"],
            "ring_type": row["detected_ring_type"],
        }
        for row in others
    ]
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return {"similar_cases": scored[:top_k]}


TOOL_REGISTRY = {
    "get_cluster_features": get_cluster_features,
    "get_shared_signal_evidence": get_shared_signal_evidence,
    "get_account_details": get_account_details,
    "get_similar_historical_cases": get_similar_historical_cases,
}