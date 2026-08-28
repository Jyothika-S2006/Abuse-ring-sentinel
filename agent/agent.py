import sqlite3
import json

def explain_cluster(cluster_id, features, risk_score):
    reasons = []
    if features.get("shared_device_ratio", 0) > 0.5:
        reasons.append(f"High device sharing ratio of {features['shared_device_ratio']:.2f}.")
    if features.get("tx_velocity", 0) > 5:
        reasons.append(f"High transaction velocity of {features['tx_velocity']:.2f} per account.")
    if features.get("shared_payout_ratio", 0) > 0:
        reasons.append("Shared withdrawal endpoint across multiple accounts.")
    if features.get("decline_rate", 0) > 0.3:
        reasons.append(f"Elevated transaction decline rate of {features['decline_rate']:.2f}.")

    return {
        "cluster_id": cluster_id,
        "risk_score": risk_score,
        "summary": "High probability fraud ring detected." if risk_score > 0.7 else "Moderate risk activity.",
        "evidence_bullets": reasons if reasons else ["Standard structural activity pattern detected."],
    }

def generate_risk_explanation(cluster_id, db_path="sentinel.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT risk_score, features_json FROM candidate_clusters WHERE cluster_id = ?", (cluster_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {"error": "Cluster not found"}
        
    score, feats = row[0], json.loads(row[1])
    
    reasons = []
    if feats.get("shared_device_count", 0) > 2:
        reasons.append(f"High device sharing: {feats['shared_device_count']} accounts linked to identical hardware.")
    if feats.get("velocity_score", 0) > 0.7:
        reasons.append(f"Suspicious transfer velocity score of {feats['velocity_score']:.2f}.")
    if feats.get("shared_payout_dest", 0) > 0:
        reasons.append(f"Shared withdrawal endpoint across multiple non-linked accounts.")
        
    summary = " High probability fraud ring detected." if score > 0.7 else " Moderate risk activity."
    return {
        "cluster_id": cluster_id,
        "risk_score": score,
        "summary": summary,
        "evidence_bullets": reasons if reasons else ["Standard structural activity pattern detected."]
    }
