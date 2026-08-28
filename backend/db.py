"""
Database models and connection utilities for Abuse Ring Sentinel.
Uses SQLAlchemy with SQLite (sentinel.db).
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

# Base declarative class
Base = declarative_base()


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class Account(Base):
    __tablename__ = "accounts"

    account_id = Column(String(64), primary_key=True, index=True)
    created_at = Column(String(64), nullable=False)
    user_name = Column(String(128), nullable=False)
    email = Column(String(128), nullable=False, index=True)
    phone_number = Column(String(64), nullable=False, index=True)
    ip_address = Column(String(64), nullable=False, index=True)
    device_id = Column(String(128), nullable=False, index=True)
    account_status = Column(String(32), nullable=False, default="active")
    risk_score = Column(Float, nullable=False, default=0.0)
    kyc_status = Column(String(32), nullable=False, default="unverified")

    # Relationships
    instruments = relationship("Instrument", back_populates="account", cascade="all, delete-orphan")
    payout_destinations = relationship("PayoutDestination", back_populates="account", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")
    ground_truth = relationship("GroundTruth", back_populates="account", uselist=False, cascade="all, delete-orphan")
    cluster_memberships = relationship("ClusterMember", back_populates="account", cascade="all, delete-orphan")


class Instrument(Base):
    __tablename__ = "instruments"

    instrument_id = Column(String(64), primary_key=True, index=True)
    account_id = Column(String(64), ForeignKey("accounts.account_id"), nullable=False, index=True)
    instrument_type = Column(String(32), nullable=False)
    card_fingerprint = Column(String(128), nullable=False, index=True)
    card_bin = Column(String(16), nullable=False, index=True)
    card_last4 = Column(String(8), nullable=False)
    card_network = Column(String(32), nullable=False)
    issuer_bank = Column(String(128), nullable=False)
    country = Column(String(8), nullable=False, default="US")
    is_prepaid = Column(Boolean, nullable=False, default=False)
    added_at = Column(String(64), nullable=False)

    account = relationship("Account", back_populates="instruments")


class PayoutDestination(Base):
    __tablename__ = "payout_destinations"

    payout_destination_id = Column(String(64), primary_key=True, index=True)
    account_id = Column(String(64), ForeignKey("accounts.account_id"), nullable=False, index=True)
    destination_type = Column(String(32), nullable=False)
    destination_hash = Column(String(128), nullable=False, index=True)
    routing_or_bank_code = Column(String(64), nullable=False)
    holder_name = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False, default="active")
    created_at = Column(String(64), nullable=False)

    account = relationship("Account", back_populates="payout_destinations")


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(String(64), primary_key=True, index=True)
    account_id = Column(String(64), ForeignKey("accounts.account_id"), nullable=False, index=True)
    instrument_id = Column(String(64), nullable=True, index=True)
    payout_destination_id = Column(String(64), nullable=True, index=True)
    timestamp = Column(String(64), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default="USD")
    transaction_type = Column(String(32), nullable=False, index=True)
    status = Column(String(64), nullable=False, index=True)
    merchant_id = Column(String(128), nullable=False)
    merchant_category = Column(String(64), nullable=False)
    ip_address = Column(String(64), nullable=True, index=True)
    device_id = Column(String(128), nullable=True, index=True)

    account = relationship("Account", back_populates="transactions")


class GroundTruth(Base):
    __tablename__ = "ground_truth"

    account_id = Column(String(64), ForeignKey("accounts.account_id"), primary_key=True)
    is_abuse = Column(Boolean, nullable=False, index=True)
    ring_id = Column(String(64), nullable=False, index=True)
    ring_type = Column(String(64), nullable=False)
    shared_signals = Column(Text, nullable=False, default="[]")
    notes = Column(Text, nullable=True)

    account = relationship("Account", back_populates="ground_truth")


class Cluster(Base):
    """
    Cluster detected by community detection and enriched with the 9 core features.
    """
    __tablename__ = "clusters"

    cluster_id = Column(String(64), primary_key=True, index=True)
    created_at = Column(String(64), nullable=False, default=lambda: datetime.now(timezone.utc).isoformat())

    # The 9 core cluster features
    cluster_size = Column(Integer, nullable=False, default=0)
    graph_density = Column(Float, nullable=False, default=0.0)
    shared_device_ratio = Column(Float, nullable=False, default=0.0)
    shared_ip_ratio = Column(Float, nullable=False, default=0.0)
    shared_payout_ratio = Column(Float, nullable=False, default=0.0)
    avg_risk_score = Column(Float, nullable=False, default=0.0)
    tx_velocity = Column(Float, nullable=False, default=0.0)
    decline_rate = Column(Float, nullable=False, default=0.0)
    rapid_drain_ratio = Column(Float, nullable=False, default=0.0)

    # Extended contextual features
    total_volume = Column(Float, nullable=False, default=0.0)
    unverified_kyc_ratio = Column(Float, nullable=False, default=0.0)
    primary_shared_signal = Column(String(64), nullable=True)
    detected_ring_type = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="UNDER_INVESTIGATION")
    ai_summary = Column(Text, nullable=True)

    members = relationship("ClusterMember", back_populates="cluster", cascade="all, delete-orphan")


class ClusterMember(Base):
    """
    Mapping between detected clusters and account nodes.
    """
    __tablename__ = "cluster_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(String(64), ForeignKey("clusters.cluster_id"), nullable=False, index=True)
    account_id = Column(String(64), ForeignKey("accounts.account_id"), nullable=False, index=True)
    degree = Column(Integer, nullable=False, default=0)
    is_core = Column(Boolean, nullable=False, default=False)
    account_role = Column(String(32), nullable=True, default="member")

    cluster = relationship("Cluster", back_populates="members")
    account = relationship("Account", back_populates="cluster_memberships")


class GraphEdge(Base):
    """
    Graph edges representing shared signal connections between accounts.
    """
    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_account_id = Column(String(64), nullable=False, index=True)
    target_account_id = Column(String(64), nullable=False, index=True)
    signal_type = Column(String(64), nullable=False, index=True)
    weight = Column(Float, nullable=False, default=1.0)
    signal_detail = Column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Database Utilities
# ---------------------------------------------------------------------------

def get_database_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url or "sentinel.bd" in db_url:
        db_url = "sqlite:///./sentinel.db"
    return db_url


def get_engine(db_url: Optional[str] = None):
    url = db_url or get_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, echo=False)


def get_session_factory(db_url: Optional[str] = None):
    engine = get_engine(db_url)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(db_url: Optional[str] = None):
    """Initializes the database by creating all declared tables."""
    engine = get_engine(db_url)
    Base.metadata.create_all(bind=engine)
    print(f"[OK] Database initialized at: {engine.url}")
    return engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI/Context dependency for database session."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()

