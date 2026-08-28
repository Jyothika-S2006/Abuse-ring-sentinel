"""
FastAPI Routes for Cluster Exploration & Entity Graph Investigation.
Exposes:
- GET /api/clusters
- GET /api/clusters/{id}
- PATCH /api/clusters/{id}
"""

import pandas as pd
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db import (
    Account,
    Cluster,
    ClusterMember,
    GraphEdge,
    GroundTruth,
    Instrument,
    PayoutDestination,
    Transaction,
    get_db,
)

router = APIRouter(prefix="/api/clusters", tags=["Clusters"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class ClusterSummary(BaseModel):
    cluster_id: str
    cluster_size: int
    graph_density: float
    shared_device_ratio: float
    shared_ip_ratio: float
    shared_payout_ratio: float
    avg_risk_score: float
    tx_velocity: float
    decline_rate: float
    rapid_drain_ratio: float
    total_volume: float
    unverified_kyc_ratio: float
    primary_shared_signal: Optional[str] = None
    detected_ring_type: Optional[str] = None
    status: str
    created_at: str

    class Config:
        from_attributes = True


class ClusterListResponse(BaseModel):
    total_clusters: int
    high_risk_count: int
    under_investigation_count: int
    dismissed_count: int
    clusters: List[ClusterSummary]


class NodeDetail(BaseModel):
    account_id: str
    user_name: str
    email: str
    phone_number: str
    ip_address: str
    device_id: str
    account_status: str
    risk_score: float
    kyc_status: str
    degree: int
    is_core: bool
    account_role: str
    ground_truth_ring: Optional[str] = None
    ground_truth_is_abuse: Optional[bool] = None


class EdgeDetail(BaseModel):
    source: str
    target: str
    signal_type: str
    weight: float
    signal_detail: Optional[str] = None


class ClusterDetailResponse(BaseModel):
    cluster: ClusterSummary
    nodes: List[NodeDetail]
    edges: List[EdgeDetail]
    transactions: List[Dict[str, Any]]
    instruments: List[Dict[str, Any]]
    payout_destinations: List[Dict[str, Any]]
    ground_truth_summary: Dict[str, Any]


class UpdateClusterStatusRequest(BaseModel):
    status: str = Field(..., description="Status: CONFIRMED_FRAUD, DISMISSED_LEGIT, or UNDER_INVESTIGATION")
    ai_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=ClusterListResponse)
def list_clusters(
    status_filter: Optional[str] = Query(None, alias="status"),
    min_risk: Optional[float] = Query(None, ge=0.0, le=1.0),
    ring_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Retrieves all detected candidate clusters with summary metrics and the 9 core features.
    """
    query = db.query(Cluster)

    if status_filter:
        query = query.filter(Cluster.status == status_filter.upper())
    if min_risk is not None:
        query = query.filter(Cluster.avg_risk_score >= min_risk)
    if ring_type:
        query = query.filter(Cluster.detected_ring_type == ring_type.lower())

    all_clusters = query.order_by(Cluster.avg_risk_score.desc(), Cluster.cluster_size.desc()).all()

    high_risk = sum(1 for c in all_clusters if c.avg_risk_score >= 0.70)
    under_inv = sum(1 for c in all_clusters if c.status == "UNDER_INVESTIGATION")
    dismissed = sum(1 for c in all_clusters if c.status == "DISMISSED_LEGIT")

    return ClusterListResponse(
        total_clusters=len(all_clusters),
        high_risk_count=high_risk,
        under_investigation_count=under_inv,
        dismissed_count=dismissed,
        clusters=all_clusters
    )


@router.get("/{cluster_id}", response_model=ClusterDetailResponse)
def get_cluster_detail(cluster_id: str, db: Session = Depends(get_db)):
    """
    Retrieves the complete graph subgraph, member roster, transaction trail,
    and payment links for a specific cluster.
    """
    cluster = db.query(Cluster).filter(Cluster.cluster_id == cluster_id).first()
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cluster with ID '{cluster_id}' not found."
        )

    # 1. Fetch member mappings
    members = db.query(ClusterMember).filter(ClusterMember.cluster_id == cluster_id).all()
    member_acc_ids = [m.account_id for m in members]

    # 2. Fetch account records & Ground Truth (use SQLAlchemy .in_() not pandas .isin())
    accounts = db.query(Account).filter(Account.account_id.in_(member_acc_ids)).all()
    gt_records = db.query(GroundTruth).filter(GroundTruth.account_id.in_(member_acc_ids)).all()
    gt_map = {gt.account_id: gt for gt in gt_records}
    member_meta_map = {m.account_id: m for m in members}

    nodes: List[NodeDetail] = []
    for acc in accounts:
        mm = member_meta_map.get(acc.account_id)
        gt = gt_map.get(acc.account_id)
        nodes.append(NodeDetail(
            account_id=acc.account_id,
            user_name=acc.user_name,
            email=acc.email,
            phone_number=acc.phone_number,
            ip_address=acc.ip_address,
            device_id=acc.device_id,
            account_status=acc.account_status,
            risk_score=acc.risk_score,
            kyc_status=acc.kyc_status,
            degree=mm.degree if mm else 0,
            is_core=mm.is_core if mm else False,
            account_role=mm.account_role if mm else "member",
            ground_truth_ring=gt.ring_id if gt else None,
            ground_truth_is_abuse=gt.is_abuse if gt else None,
        ))

    # 3. Fetch connecting graph edges within the cluster
    raw_edges = db.query(GraphEdge).filter(
        GraphEdge.source_account_id.in_(member_acc_ids),
        GraphEdge.target_account_id.in_(member_acc_ids)
    ).all()

    edges: List[EdgeDetail] = [
        EdgeDetail(
            source=e.source_account_id,
            target=e.target_account_id,
            signal_type=e.signal_type,
            weight=e.weight,
            signal_detail=e.signal_detail
        )
        for e in raw_edges
    ]

    # 4. Fetch transactions
    tx_records = db.query(Transaction).filter(
        Transaction.account_id.in_(member_acc_ids)
    ).order_by(Transaction.timestamp.desc()).limit(150).all()

    tx_list = [
        {
            "transaction_id": t.transaction_id,
            "account_id": t.account_id,
            "timestamp": t.timestamp,
            "amount": t.amount,
            "currency": t.currency,
            "transaction_type": t.transaction_type,
            "status": t.status,
            "merchant_id": t.merchant_id,
            "merchant_category": t.merchant_category,
            "ip_address": t.ip_address,
            "device_id": t.device_id,
        }
        for t in tx_records
    ]

    # 5. Fetch instruments
    inst_records = db.query(Instrument).filter(
        Instrument.account_id.in_(member_acc_ids)
    ).all()

    inst_list = [
        {
            "instrument_id": i.instrument_id,
            "account_id": i.account_id,
            "instrument_type": i.instrument_type,
            "card_fingerprint": i.card_fingerprint,
            "card_bin": i.card_bin,
            "card_last4": i.card_last4,
            "card_network": i.card_network,
            "issuer_bank": i.issuer_bank,
            "is_prepaid": i.is_prepaid,
        }
        for i in inst_records
    ]

    # 6. Fetch payout destinations
    payout_records = db.query(PayoutDestination).filter(
        PayoutDestination.account_id.in_(member_acc_ids)
    ).all()

    payout_list = [
        {
            "payout_destination_id": p.payout_destination_id,
            "account_id": p.account_id,
            "destination_type": p.destination_type,
            "destination_hash": p.destination_hash,
            "holder_name": p.holder_name,
            "status": p.status,
        }
        for p in payout_records
    ]

    # Ground truth summary
    top_gt_ring = "UNKNOWN"
    is_abuse_gt = False
    if gt_records:
        ring_counts = pd.Series([gt.ring_id for gt in gt_records]).value_counts()
        top_gt_ring = ring_counts.index[0]
        abuse_count = sum(1 for gt in gt_records if gt.is_abuse)
        is_abuse_gt = (abuse_count / len(gt_records)) >= 0.5

    gt_summary = {
        "dominant_ring_id": top_gt_ring,
        "is_abuse": is_abuse_gt,
        "member_abuse_ratio": round(
            sum(1 for gt in gt_records if gt.is_abuse) / len(gt_records), 3
        ) if gt_records else 0.0
    }

    return ClusterDetailResponse(
        cluster=cluster,
        nodes=nodes,
        edges=edges,
        transactions=tx_list,
        instruments=inst_list,
        payout_destinations=payout_list,
        ground_truth_summary=gt_summary
    )


@router.patch("/{cluster_id}", response_model=ClusterSummary)
def update_cluster_status(
    cluster_id: str,
    req: UpdateClusterStatusRequest,
    db: Session = Depends(get_db)
):
    """
    Updates the investigation status of a cluster.
    """
    cluster = db.query(Cluster).filter(Cluster.cluster_id == cluster_id).first()
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cluster '{cluster_id}' not found."
        )

    valid_statuses = ["CONFIRMED_FRAUD", "DISMISSED_LEGIT", "UNDER_INVESTIGATION", "RESOLVED"]
    status_upper = req.status.upper()
    if status_upper not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{req.status}'. Must be one of {valid_statuses}"
        )

    cluster.status = status_upper
    if req.ai_summary:
        cluster.ai_summary = req.ai_summary

    db.commit()
    db.refresh(cluster)
    return cluster
