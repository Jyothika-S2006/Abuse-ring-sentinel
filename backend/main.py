"""
Abuse Ring Sentinel - FastAPI Backend Application
Serves REST APIs for graph intelligence & the investigative web dashboard.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.db import init_db
from backend.routes import clusters
from backend.routes.agent_route import router as agent_router  # Added agent route import
from backend.routes.audit import router as audit_router  # Added audit route import

app = FastAPI(
    title="Abuse Ring Sentinel API",
    description="Multi-Entity Graph Intelligence & Abuse Ring Detection Platform",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(clusters.router)
app.include_router(agent_router)  # Registered agent router here
app.include_router(audit_router)  # Registered audit router here

@app.get("/api/health", tags=["Health"])
def health_check():
    """Service health check."""
    return {
        "status": "healthy",
        "service": "Abuse Ring Sentinel",
        "version": "1.0.0"
    }


# Mount static frontend files if directory exists
frontend_path = PROJECT_ROOT / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")


@app.on_event("startup")
def on_startup():
    """Initializes database schema on startup."""
    init_db()
    print("[✓] Sentinel Backend initialized and ready for requests.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)