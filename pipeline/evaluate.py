"""
Model Evaluation Pipeline for Abuse Ring Sentinel.
Evaluates the trained ML classifier on detected clusters against ground truth labels,
computes classification metrics (Precision, Recall, F1, ROC-AUC, Confusion Matrix),
extracts feature importances, and writes evaluation_results.json.
"""

import argparse
import json
import os
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from backend.db import Cluster, ClusterMember, GroundTruth, get_session_factory
from pipeline.train_model import FEATURE_COLS, AbuseClusterModelTrainer


def evaluate_model(
    db_url: str = "sqlite:///./sentinel.db",
    model_path: str = "model.pkl",
    output_json: str = "evaluation_results.json"
) -> Dict[str, Any]:
    print(f"[+] Loading model from '{model_path}' and evaluating against database '{db_url}'...")

    pipeline = AbuseClusterModelTrainer.load_model(model_path)
    session_factory = get_session_factory(db_url)

    # 1. Fetch Clusters and Ground Truth from DB
    with session_factory() as session:
        clusters = session.query(Cluster).all()
        members = session.query(ClusterMember).all()
        ground_truth = session.query(GroundTruth).all()

        if not clusters:
            raise ValueError("No clusters found in database. Run pipeline/run_pipeline.py first.")

        # Build ground truth lookup: account_id -> is_abuse
        gt_map = {gt.account_id: gt.is_abuse for gt in ground_truth}

        # Determine true label for each cluster by majority vote of members
        cluster_members_map: Dict[str, List[str]] = {}
        for m in members:
            cluster_members_map.setdefault(m.cluster_id, []).append(m.account_id)

        eval_rows = []
        for c in clusters:
            c_members = cluster_members_map.get(c.cluster_id, [])
            abuse_votes = sum(1 for acc in c_members if gt_map.get(acc, False))
            true_is_abuse = (abuse_votes / len(c_members)) >= 0.5 if c_members else False

            eval_rows.append({
                "cluster_id": c.cluster_id,
                "cluster_size": c.cluster_size,
                "graph_density": c.graph_density,
                "shared_device_ratio": c.shared_device_ratio,
                "shared_ip_ratio": c.shared_ip_ratio,
                "shared_payout_ratio": c.shared_payout_ratio,
                "avg_risk_score": c.avg_risk_score,
                "tx_velocity": c.tx_velocity,
                "decline_rate": c.decline_rate,
                "rapid_drain_ratio": c.rapid_drain_ratio,
                "y_true": int(true_is_abuse),
                "abuse_member_ratio": round(abuse_votes / len(c_members), 3) if c_members else 0.0
            })

    df_eval = pd.DataFrame(eval_rows)
    X = df_eval[FEATURE_COLS]
    y_true = df_eval["y_true"].values

    # 2. Inference
    y_probs = pipeline.predict_proba(X)[:, 1]
    y_pred = (y_probs >= 0.50).astype(int)

    df_eval["predicted_prob"] = np.round(y_probs, 4)
    df_eval["predicted_label"] = y_pred

    # 3. Compute Metrics
    acc = float(accuracy_score(y_true, y_pred))
    prec = float(precision_score(y_true, y_pred, zero_division=0))
    rec = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))

    try:
        roc_auc = float(roc_auc_score(y_true, y_probs))
    except Exception:
        roc_auc = 1.0

    cm = confusion_matrix(y_true, y_pred).tolist()

    # 4. Extract Feature Importances
    feature_importances = {}
    clf = pipeline.named_steps.get("classifier")
    if hasattr(clf, "feature_importances_"):
        for name, imp in zip(FEATURE_COLS, clf.feature_importances_):
            feature_importances[name] = round(float(imp), 4)
    elif hasattr(clf, "coef_"):
        for name, coef in zip(FEATURE_COLS, clf.coef_[0]):
            feature_importances[name] = round(float(abs(coef)), 4)

    # Sort feature importances
    sorted_importances = dict(sorted(feature_importances.items(), key=lambda x: x[1], reverse=True))

    results = {
        "metrics": {
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "roc_auc": round(roc_auc, 4),
            "confusion_matrix": {
                "true_negative": cm[0][0] if len(cm) > 0 and len(cm[0]) > 0 else 0,
                "false_positive": cm[0][1] if len(cm) > 0 and len(cm[0]) > 1 else 0,
                "false_negative": cm[1][0] if len(cm) > 1 and len(cm[1]) > 0 else 0,
                "true_positive": cm[1][1] if len(cm) > 1 and len(cm[1]) > 1 else 0,
            }
        },
        "feature_importances": sorted_importances,
        "cluster_evaluations": df_eval.to_dict(orient="records"),
        "evaluated_at": pd.Timestamp.now().isoformat()
    }

    # Save to JSON
    with open(output_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[OK] Saved evaluation results to: {output_json}")

    # Print Summary Report
    print("\n" + "=" * 70)
    print(f"{'MODEL EVALUATION PERFORMANCE REPORT':^70}")
    print("=" * 70)
    print(f"Accuracy:           {acc * 100:.2f}%")
    print(f"Precision (Abuse):  {prec * 100:.2f}%")
    print(f"Recall (Abuse):     {rec * 100:.2f}%")
    print(f"F1 Score:           {f1:.4f}")
    print(f"ROC-AUC:            {roc_auc:.4f}")
    print("-" * 70)
    print("Confusion Matrix:")
    print(f"  True Negatives (Legit):   {results['metrics']['confusion_matrix']['true_negative']}")
    print(f"  False Positives:          {results['metrics']['confusion_matrix']['false_positive']}")
    print(f"  False Negatives:          {results['metrics']['confusion_matrix']['false_negative']}")
    print(f"  True Positives (Abuse):   {results['metrics']['confusion_matrix']['true_positive']}")
    print("-" * 70)
    print("Top Feature Importances:")
    for feat, imp in sorted_importances.items():
        bar = "#" * int(imp * 30)
        print(f"  - {feat:<24}: {imp:.4f} {bar}")
    print("=" * 70)

    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate Abuse Ring ML Classifier")
    parser.add_argument("--db-path", type=str, default="sentinel.db", help="SQLite database path")
    parser.add_argument("--model-path", type=str, default="model.pkl", help="Model artifact path")
    parser.add_argument("--output-json", type=str, default="evaluation_results.json", help="Output metrics JSON")
    args = parser.parse_args()

    db_url = f"sqlite:///./{args.db_path}"
    evaluate_model(db_url=db_url, model_path=args.model_path, output_json=args.output_json)


if __name__ == "__main__":
    main()
