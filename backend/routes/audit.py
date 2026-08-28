from fastapi import APIRouter
from pydantic import BaseModel
import sqlite3
import os

router = APIRouter(prefix="/api/audit", tags=["audit"])

class AuditAction(BaseModel):
    cluster_id: str
    action: str
    analyst_notes: str = ""

@router.post("/log")
def log_analyst_action(data: AuditAction):
    db_path = os.path.join(os.getcwd(), "sentinel.db")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id TEXT,
            action TEXT,
            notes TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute(
        "INSERT INTO audit_logs (cluster_id, action, notes) VALUES (?, ?, ?)",
        (data.cluster_id, data.action, data.analyst_notes)
    )
    
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "cluster_id": data.cluster_id,
        "recorded_action": data.action
    }