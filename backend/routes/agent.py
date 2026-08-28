from fastapi import APIRouter, HTTPException
import sqlite3
import os

from agent.agent import explain_cluster

router = APIRouter(prefix="/api/agent", tags=["agent"])

@router.get("/explain/{cluster_id}")
def get_cluster_explanation(cluster_id: str):
    clean_id = cluster_id.strip("'\" ")
    
    db_path = os.path.join(os.getcwd(), "sentinel.db")
    if not os.path.exists(db_path):
        raise HTTPException(status_code=500, detail=f"Database file not found at {db_path}")
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            SELECT cluster_id, cluster_size, graph_density, shared_device_ratio,
                   shared_ip_ratio, shared_payout_ratio, avg_risk_score,
                   tx_velocity, decline_rate, rapid_drain_ratio
            FROM clusters
            WHERE cluster_id = ?
            """,
            (clean_id,),
        )
        row = cursor.fetchone()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail=f"Cluster '{clean_id}' not found in clusters table.")

    _, *feature_values = row
    feature_names = (
        "cluster_size", "graph_density", "shared_device_ratio",
        "shared_ip_ratio", "shared_payout_ratio", "avg_risk_score",
        "tx_velocity", "decline_rate", "rapid_drain_ratio",
    )
    features = dict(zip(feature_names, feature_values))
    risk_score = features["avg_risk_score"]
    explanation = explain_cluster(clean_id, features, risk_score)
    
    return {
        "cluster_id": clean_id,
        "risk_score": risk_score,
        "explanation": explanation
    }