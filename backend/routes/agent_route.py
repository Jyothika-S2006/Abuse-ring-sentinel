from fastapi import APIRouter, HTTPException
import sqlite3
import os

from agent.agent import run_full_investigation

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/explain/{cluster_id}")
def get_cluster_explanation(cluster_id: str):
    clean_id = cluster_id.strip("'\" ")

    db_path = os.path.join(os.getcwd(), "sentinel.db")
    if not os.path.exists(db_path):
        raise HTTPException(status_code=500, detail=f"Database file not found at {db_path}")

    # Quick existence check before we spend an LLM call on a bad ID
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT cluster_id FROM clusters WHERE cluster_id = ?", (clean_id,))
        row = cursor.fetchone()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Cluster '{clean_id}' not found in clusters table.")

    try:
        result = run_full_investigation(clean_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent investigation failed: {str(e)}")

    return result