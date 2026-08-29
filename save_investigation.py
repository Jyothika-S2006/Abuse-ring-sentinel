"""
save_investigation.py
One-off script: runs the agent on a cluster and persists the result into
clusters.ai_summary. Run this once per cluster you want to demo, so the
frontend (and you, while testing) can read the stored result instead of
re-calling Gemini every time -- keeps you well under the free-tier quota.

Usage:
    python save_investigation.py CLUSTER_010
"""
import sqlite3
import json
import sys

from agent.agent import run_full_investigation


def save(cluster_id: str):
    result = run_full_investigation(cluster_id)

    conn = sqlite3.connect("sentinel.db")
    conn.execute(
        "UPDATE clusters SET ai_summary = ? WHERE cluster_id = ?",
        (json.dumps(result), cluster_id),
    )
    conn.commit()
    conn.close()

    print(f"Saved investigation for {cluster_id}\n")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else "CLUSTER_010"
    save(cid)