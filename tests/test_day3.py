#!/usr/bin/env python3
"""
Unit and Integration Test Suite for Day 3:
- ML Model Artifact & Inference (pipeline/train_model.py)
- Evaluation Metrics (pipeline/evaluate.py)
- FastAPI REST Endpoints (backend/main.py, backend/routes/clusters.py)
- Frontend Static Assets (frontend/index.html, frontend/style.css, frontend/app.js)
"""

import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.main import app
from pipeline.train_model import FEATURE_COLS, AbuseClusterModelTrainer


def test_model_artifact_and_inference():
    print("[+] Testing ML Model Artifact (model.pkl)...")
    model_path = PROJECT_ROOT / "model.pkl"
    assert model_path.exists(), "model.pkl was not found"

    pipeline = AbuseClusterModelTrainer.load_model(str(model_path))
    assert pipeline is not None

    # Test scoring a dummy 9-feature vector
    dummy_features = pd.DataFrame([{
        "cluster_size": 15,
        "graph_density": 0.85,
        "shared_device_ratio": 0.80,
        "shared_ip_ratio": 0.90,
        "shared_payout_ratio": 0.10,
        "avg_risk_score": 0.90,
        "tx_velocity": 5.0,
        "decline_rate": 0.0,
        "rapid_drain_ratio": 0.0,
    }])
    prob = pipeline.predict_proba(dummy_features[FEATURE_COLS])[:, 1][0]
    assert 0.0 <= prob <= 1.0
    print(f"[PASS] test_model_artifact_and_inference (Inference score: {prob:.4f})")


def test_evaluation_results_file():
    print("[+] Testing Evaluation Results JSON (evaluation_results.json)...")
    eval_file = PROJECT_ROOT / "evaluation_results.json"
    assert eval_file.exists(), "evaluation_results.json not found"

    with open(eval_file, "r") as f:
        data = json.load(f)

    assert "metrics" in data
    assert "accuracy" in data["metrics"]
    assert "f1_score" in data["metrics"]
    assert "confusion_matrix" in data["metrics"]
    assert "feature_importances" in data
    assert len(data["feature_importances"]) == 9

    print(f"[PASS] test_evaluation_results_file (F1: {data['metrics']['f1_score']}, Acc: {data['metrics']['accuracy']})")


def test_fastapi_endpoints():
    print("[+] Testing FastAPI REST API Endpoints...")
    client = TestClient(app)

    # 1. Health check
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"

    # 2. GET /api/clusters
    res = client.get("/api/clusters")
    assert res.status_code == 200
    data = res.json()
    assert "total_clusters" in data
    assert "clusters" in data
    assert len(data["clusters"]) >= 10

    sample_cluster = data["clusters"][0]
    cid = sample_cluster["cluster_id"]
    assert "cluster_size" in sample_cluster
    assert "avg_risk_score" in sample_cluster
    assert "status" in sample_cluster

    # 3. GET /api/clusters/{id}
    res_detail = client.get(f"/api/clusters/{cid}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert "cluster" in detail
    assert "nodes" in detail
    assert "edges" in detail
    assert "transactions" in detail
    assert "instruments" in detail
    assert "payout_destinations" in detail
    assert len(detail["nodes"]) == sample_cluster["cluster_size"]

    # 4. PATCH /api/clusters/{id}
    res_patch = client.patch(
        f"/api/clusters/{cid}",
        json={"status": "CONFIRMED_FRAUD", "ai_summary": "Verified automated card-testing botnet."}
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["status"] == "CONFIRMED_FRAUD"

    print(f"[PASS] test_fastapi_endpoints (Validated /api/health, /api/clusters, /api/clusters/{cid}, PATCH)")


def test_frontend_assets_and_mount():
    print("[+] Testing Frontend Static Assets & Web Serving...")
    index_file = PROJECT_ROOT / "frontend" / "index.html"
    css_file = PROJECT_ROOT / "frontend" / "style.css"
    js_file = PROJECT_ROOT / "frontend" / "app.js"

    assert index_file.exists(), "frontend/index.html missing"
    assert css_file.exists(), "frontend/style.css missing"
    assert js_file.exists(), "frontend/app.js missing"

    # Verify style.css contains color tokens specified in spec
    with open(css_file, "r") as f:
        css_text = f.read()
    assert "#0F172A" in css_text or "#1E293B" in css_text
    assert "#A7F3D0" in css_text or "mint" in css_text.lower()
    assert "#FDE68A" in css_text or "amber" in css_text.lower()
    assert "#FCA5A5" in css_text or "coral" in css_text.lower()

    # Test client serving root /
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "Abuse Ring Sentinel" in res.text

    print("[PASS] test_frontend_assets_and_mount (HTML, CSS palette, JS, and root endpoint validated)")


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING DAY 3 TEST SUITE")
    print("=" * 60)
    test_model_artifact_and_inference()
    test_evaluation_results_file()
    test_fastapi_endpoints()
    test_frontend_assets_and_mount()
    print("\nALL 4 DAY 3 TESTS PASSED SUCCESSFULLY!")
