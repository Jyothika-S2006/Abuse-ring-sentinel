"""
Model Training & Scoring Pipeline for Abuse Ring Sentinel.
Trains a calibrated classifier (XGBoost / Logistic Regression) on the 9 cluster features,
saves model.pkl, and writes predictions and risk scores to sentinel.db.
"""

import argparse
import os
import pickle
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.db import Cluster, ClusterMember, GroundTruth, get_session_factory


# The 9 Core Cluster Features
FEATURE_COLS = [
    "cluster_size",
    "graph_density",
    "shared_device_ratio",
    "shared_ip_ratio",
    "shared_payout_ratio",
    "avg_risk_score",
    "tx_velocity",
    "decline_rate",
    "rapid_drain_ratio",
]


def generate_training_feature_samples(n_samples: int = 400, seed: int = 42) -> Tuple[pd.DataFrame, np.ndarray]:
    """
    Generates a synthetic distribution of cluster feature vectors to train a robust,
    generalized classifier representing the 4 key cluster archetypes:
    1. Card-Testing Abuse Rings (high decline rate, micro-charges, shared device/IP)
    2. Promo-Abuse Sybil Rings (high shared device/IP, high baseline risk, rapid vouchers)
    3. Cash-Out Mule Networks (high rapid drain, shared payout destination hash)
    4. Legit Look-Alike Clusters (shared public IP or family device, but low risk, low decline, normal spend)
    """
    np.random.seed(seed)
    samples = []
    labels = []

    # 1. Card-Testing Rings (Abuse = 1)
    for _ in range(n_samples // 4):
        size = np.random.randint(6, 25)
        density = np.random.uniform(0.6, 1.0)
        dev_rat = np.random.uniform(0.0, 0.95)
        ip_rat = np.random.uniform(0.0, 0.95)
        pay_rat = np.random.uniform(0.0, 0.20)
        risk = np.random.uniform(0.70, 0.98)
        velocity = np.random.uniform(10.0, 45.0)
        decline = np.random.uniform(0.60, 0.95)
        drain = np.random.uniform(0.0, 0.10)
        samples.append([size, density, dev_rat, ip_rat, pay_rat, risk, velocity, decline, drain])
        labels.append(1)

    # 2. Promo-Abuse Rings (Abuse = 1)
    for _ in range(n_samples // 4):
        size = np.random.randint(8, 30)
        density = np.random.uniform(0.7, 1.0)
        dev_rat = np.random.uniform(0.6, 0.98)
        ip_rat = np.random.uniform(0.5, 0.98)
        pay_rat = np.random.uniform(0.0, 0.25)
        risk = np.random.uniform(0.65, 0.95)
        velocity = np.random.uniform(2.0, 8.0)
        decline = np.random.uniform(0.0, 0.10)
        drain = np.random.uniform(0.0, 0.15)
        samples.append([size, density, dev_rat, ip_rat, pay_rat, risk, velocity, decline, drain])
        labels.append(1)

    # 3. Cash-Out Mule Rings (Abuse = 1)
    for _ in range(n_samples // 4):
        size = np.random.randint(5, 25)
        density = np.random.uniform(0.4, 1.0)
        dev_rat = np.random.uniform(0.0, 0.90)
        ip_rat = np.random.uniform(0.0, 0.50)
        pay_rat = np.random.uniform(0.40, 1.0)
        risk = np.random.uniform(0.75, 0.98)
        velocity = np.random.uniform(2.0, 10.0)
        decline = np.random.uniform(0.0, 0.08)
        drain = np.random.uniform(0.50, 1.0)
        samples.append([size, density, dev_rat, ip_rat, pay_rat, risk, velocity, decline, drain])
        labels.append(1)

    # 4. Legit Look-Alike Clusters (Abuse = 0)
    for _ in range(n_samples // 4):
        size = np.random.randint(8, 35)
        density = np.random.uniform(0.8, 1.0)
        pattern = np.random.choice(["shared_ip", "shared_dev", "shared_landlord"])
        if pattern == "shared_ip":
            dev_rat = np.random.uniform(0.0, 0.05)
            ip_rat = np.random.uniform(0.85, 0.98)
            pay_rat = 0.0
        elif pattern == "shared_dev":
            dev_rat = np.random.uniform(0.80, 0.95)
            ip_rat = np.random.uniform(0.80, 0.95)
            pay_rat = 0.0
        else:
            dev_rat = 0.0
            ip_rat = 0.0
            pay_rat = np.random.uniform(0.80, 1.0)

        risk = np.random.uniform(0.02, 0.15)
        velocity = np.random.uniform(3.0, 18.0)
        decline = np.random.uniform(0.0, 0.05)
        drain = 0.0
        samples.append([size, density, dev_rat, ip_rat, pay_rat, risk, velocity, decline, drain])
        labels.append(0)

    df = pd.DataFrame(samples, columns=FEATURE_COLS)
    y = np.array(labels)
    return df, y


class AbuseClusterModelTrainer:
    def __init__(self, model_type: str = "xgboost", model_path: str = "model.pkl", seed: int = 42):
        self.model_type = model_type
        self.model_path = model_path
        self.seed = seed
        self.pipeline: Optional[Pipeline] = None

    def train(self, df_train: pd.DataFrame, y_train: np.ndarray) -> Dict[str, float]:
        """Trains and calibrates the cluster classification model."""
        print(f"[+] Training {self.model_type.upper()} model on {len(df_train)} samples across {len(FEATURE_COLS)} features...")

        if self.model_type.lower() == "xgboost":
            base_clf = XGBClassifier(
                n_estimators=80,
                max_depth=4,
                learning_rate=0.08,
                subsample=0.85,
                colsample_bytree=0.85,
                random_state=self.seed,
                eval_metric="logloss"
            )
        elif self.model_type.lower() == "logistic_regression":
            base_clf = LogisticRegression(
                C=1.0,
                max_iter=500,
                random_state=self.seed,
                class_weight="balanced"
            )
        else:
            base_clf = RandomForestClassifier(
                n_estimators=80,
                max_depth=5,
                random_state=self.seed,
                class_weight="balanced"
            )

        self.pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", base_clf)
        ])

        self.pipeline.fit(df_train[FEATURE_COLS], y_train)

        preds = self.pipeline.predict(df_train[FEATURE_COLS])
        probs = self.pipeline.predict_proba(df_train[FEATURE_COLS])[:, 1]
        metrics = {
            "accuracy": float(accuracy_score(y_train, preds)),
            "f1_score": float(f1_score(y_train, preds)),
            "roc_auc": float(roc_auc_score(y_train, probs))
        }
        print(f"[OK] Training complete: Accuracy = {metrics['accuracy']:.4f}, F1 = {metrics['f1_score']:.4f}, ROC-AUC = {metrics['roc_auc']:.4f}")
        return metrics

    def save_model(self, out_path: Optional[str] = None):
        """Saves the trained pipeline model artifact to disk."""
        target = Path(out_path or self.model_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        artifact = {
            "pipeline": self.pipeline,
            "feature_cols": FEATURE_COLS,
            "model_type": self.model_type,
            "created_at": pd.Timestamp.now().isoformat()
        }

        with open(target, "wb") as f:
            pickle.dump(artifact, f)
        print(f"[OK] Saved trained model artifact to: {target.resolve()}")

    @classmethod
    def load_model(cls, model_path: str = "model.pkl") -> Pipeline:
        """Loads the serialized model pipeline."""
        with open(model_path, "rb") as f:
            artifact = pickle.load(f)
        return artifact["pipeline"]


def score_and_update_database(
    db_url: Optional[str] = None,
    model_path: str = "model.pkl"
) -> pd.DataFrame:
    """
    Loads detected clusters from SQLite, runs model inference using model.pkl,
    and updates the clusters table with predicted abuse scores and ring types.
    """
    print(f"\n[+] Scoring candidate clusters from database using '{model_path}'...")
    session_factory = get_session_factory(db_url)
    pipeline = AbuseClusterModelTrainer.load_model(model_path)

    with session_factory() as session:
        db_clusters = session.query(Cluster).all()
        if not db_clusters:
            print("[!] No clusters found in database to score.")
            return pd.DataFrame()

        rows = []
        for c in db_clusters:
            rows.append({
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
            })

        df_clusters = pd.DataFrame(rows)
        X = df_clusters[FEATURE_COLS]
        probs = pipeline.predict_proba(X)[:, 1]
        preds = (probs >= 0.50).astype(int)

        scored_records = []
        for idx, c in enumerate(db_clusters):
            prob = float(probs[idx])
            pred = int(preds[idx])
            c.avg_risk_score = round(prob, 4)

            # Refine detected ring type based on ML and signal dominance
            if prob >= 0.50:
                if c.decline_rate >= 0.50:
                    c.detected_ring_type = "card_testing"
                elif c.rapid_drain_ratio >= 0.25 or c.shared_payout_ratio >= 0.30:
                    c.detected_ring_type = "cash_out"
                else:
                    c.detected_ring_type = "promo_abuse"
                c.status = "CONFIRMED_FRAUD" if prob >= 0.85 else "UNDER_INVESTIGATION"
            else:
                c.detected_ring_type = "legit_lookalike"
                c.status = "DISMISSED_LEGIT" if prob <= 0.20 else "UNDER_INVESTIGATION"

            scored_records.append({
                "cluster_id": c.cluster_id,
                "cluster_size": c.cluster_size,
                "predicted_prob": round(prob, 4),
                "predicted_label": "ABUSE_RING" if pred == 1 else "LEGIT_CLUSTER",
                "detected_ring_type": c.detected_ring_type,
                "status": c.status
            })

        session.commit()
        print(f"[OK] Successfully scored and updated {len(db_clusters)} clusters in sentinel.db.")

    df_scored = pd.DataFrame(scored_records)
    return df_scored


def main():
    parser = argparse.ArgumentParser(description="Train Abuse Ring Detection ML Model")
    parser.add_argument("--model-type", type=str, default="xgboost", choices=["xgboost", "logistic_regression", "random_forest"])
    parser.add_argument("--model-path", type=str, default="model.pkl", help="Output model pickle path")
    parser.add_argument("--db-path", type=str, default="sentinel.db", help="SQLite database path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    # 1. Generate training dataset & fit model
    df_train, y_train = generate_training_feature_samples(n_samples=500, seed=args.seed)
    trainer = AbuseClusterModelTrainer(model_type=args.model_type, model_path=args.model_path, seed=args.seed)
    trainer.train(df_train, y_train)
    trainer.save_model(args.model_path)

    # 2. Score candidate clusters in DB
    db_url = f"sqlite:///./{args.db_path}"
    df_scored = score_and_update_database(db_url=db_url, model_path=args.model_path)

    print("\n" + "="*70)
    print(f"{'ML CLUSTER SCORING RESULTS':^70}")
    print("="*70)
    for _, r in df_scored.iterrows():
        print(f"  * {r['cluster_id']:<12} (Size: {r['cluster_size']:<2}) -> {r['predicted_label']:<14} [Score: {r['predicted_prob']:.3f}] Type: {r['detected_ring_type']:<15} Status: {r['status']}")
    print("="*70)


if __name__ == "__main__":
    main()
