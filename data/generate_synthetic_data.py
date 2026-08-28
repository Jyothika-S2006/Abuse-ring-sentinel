#!/usr/bin/env python3
"""
Synthetic Data Generator for Abuse Ring Sentinel
=================================================
Generates realistic financial fraud graphs and transaction records for abuse ring detection:
- ~600 accounts
- ~4,000 transactions
- ~1,000 payment instruments
- ~500 payout destinations
- Ground truth labels covering 10 planted abuse rings (Card-Testing, Promo-Abuse, Cash-Out),
  3 legit look-alike clusters (Shared Campus IP, Shared Family Device, Shared Landlord Destination),
  and organic platform users.

Output Files:
- data/accounts.csv
- data/instruments.csv
- data/payout_destinations.csv
- data/transactions.csv
- data/ground_truth.csv
"""

import argparse
import hashlib
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from faker import Faker
import pandas as pd


# ---------------------------------------------------------------------------
# Constants & Reference Data
# ---------------------------------------------------------------------------

CARD_BINS = {
    "VISA": ["411111", "402400", "426684", "453201", "491622", "471600"],
    "MASTERCARD": ["510510", "525500", "542418", "550000", "535310"],
    "AMEX": ["378282", "371449", "340000", "375987"],
    "DISCOVER": ["601100", "650000", "644000"],
}

ISSUER_BANKS = [
    "JPMorgan Chase", "Bank of America", "Wells Fargo", "Citibank", 
    "Capital One", "U.S. Bank", "PNC Bank", "Truist", "TD Bank", "Chime Neobank"
]

PREPAID_ISSUERS = [
    "Green Dot Bank", "The Bancorp Bank", "MetaBank", "Vanilla Prepaid", "Prepaid Financial Services"
]

MERCHANTS = [
    {"name": "Amazon Marketplace", "category": "retail"},
    {"name": "Walmart Online", "category": "retail"},
    {"name": "Target Digital", "category": "retail"},
    {"name": "Apple App Store", "category": "digital_goods"},
    {"name": "Google Play Store", "category": "digital_goods"},
    {"name": "Steam Games", "category": "gaming"},
    {"name": "PlayStation Network", "category": "gaming"},
    {"name": "Razer Gold", "category": "gaming_cards"},
    {"name": "Coinbase Exchange", "category": "crypto_exchange"},
    {"name": "Kraken Pay", "category": "crypto_exchange"},
    {"name": "Uber Eats", "category": "food_delivery"},
    {"name": "DoorDash", "category": "food_delivery"},
    {"name": "Airbnb Reservations", "category": "travel"},
    {"name": "Delta Airlines", "category": "travel"},
    {"name": "Starbucks Rewards", "category": "dining"},
    {"name": "Apex Property Management", "category": "real_estate"},
    {"name": "Direct P2P Transfer", "category": "p2p_transfer"},
    {"name": "Platform Promo Bonus", "category": "promo_reward"},
]


# ---------------------------------------------------------------------------
# Generator Class
# ---------------------------------------------------------------------------

class SyntheticDataGenerator:
    def __init__(self, seed: int = 42, base_date: Optional[datetime] = None):
        self.seed = seed
        self.fake = Faker()
        Faker.seed(seed)
        random.seed(seed)

        # Reference anchor timeline (simulate 90-day activity window ending recently)
        if base_date is None:
            self.end_date = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
        else:
            self.end_date = base_date
        self.start_date = self.end_date - timedelta(days=90)

        # ID sequences
        self.account_seq = 1
        self.instrument_seq = 1
        self.payout_dest_seq = 1
        self.transaction_seq = 1

        # Global storage
        self.accounts: List[Dict[str, Any]] = []
        self.instruments: List[Dict[str, Any]] = []
        self.payout_destinations: List[Dict[str, Any]] = []
        self.transactions: List[Dict[str, Any]] = []
        self.ground_truth: List[Dict[str, Any]] = []

        # Internal lookups
        self.account_instruments: Dict[str, List[Dict[str, Any]]] = {}
        self.account_payouts: Dict[str, List[Dict[str, Any]]] = {}

    def _next_account_id(self) -> str:
        aid = f"ACC_{self.account_seq:06d}"
        self.account_seq += 1
        return aid

    def _next_instrument_id(self) -> str:
        iid = f"INST_{self.instrument_seq:06d}"
        self.instrument_seq += 1
        return iid

    def _next_payout_dest_id(self) -> str:
        pid = f"DEST_{self.payout_dest_seq:06d}"
        self.payout_dest_seq += 1
        return pid

    def _next_transaction_id(self) -> str:
        tid = f"TXN_{self.transaction_seq:06d}"
        self.transaction_seq += 1
        return tid

    def _random_date(self, start: datetime, end: datetime) -> datetime:
        delta = end - start
        random_seconds = random.randint(0, max(1, int(delta.total_seconds())))
        return start + timedelta(seconds=random_seconds)

    def _generate_card_fingerprint(self, bin_num: str, last4: str, salt: str = "") -> str:
        raw = f"{bin_num}_{last4}_{salt}"
        return f"fp_card_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def _generate_payout_hash(self, routing: str, acct: str, salt: str = "") -> str:
        raw = f"{routing}_{acct}_{salt}"
        return f"dest_hash_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def _create_instrument(
        self,
        account_id: str,
        inst_type: str = "credit_card",
        card_network: Optional[str] = None,
        card_bin: Optional[str] = None,
        card_last4: Optional[str] = None,
        card_fingerprint: Optional[str] = None,
        issuer_bank: Optional[str] = None,
        is_prepaid: bool = False,
        added_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        inst_id = self._next_instrument_id()
        if card_network is None:
            card_network = random.choice(list(CARD_BINS.keys()))
        if card_bin is None:
            card_bin = random.choice(CARD_BINS[card_network])
        if card_last4 is None:
            card_last4 = f"{random.randint(1000, 9999)}"
        if card_fingerprint is None:
            card_fingerprint = self._generate_card_fingerprint(card_bin, card_last4, str(random.random()))
        if issuer_bank is None:
            issuer_bank = random.choice(PREPAID_ISSUERS) if is_prepaid else random.choice(ISSUER_BANKS)
        if added_at is None:
            added_at = self.start_date

        inst = {
            "instrument_id": inst_id,
            "account_id": account_id,
            "instrument_type": inst_type,
            "card_fingerprint": card_fingerprint,
            "card_bin": card_bin,
            "card_last4": card_last4,
            "card_network": card_network,
            "issuer_bank": issuer_bank,
            "country": "US",
            "is_prepaid": is_prepaid,
            "added_at": added_at.isoformat()
        }
        self.instruments.append(inst)
        self.account_instruments.setdefault(account_id, []).append(inst)
        return inst

    def _create_payout_destination(
        self,
        account_id: str,
        dest_type: str = "bank_account",
        destination_hash: Optional[str] = None,
        routing_or_bank_code: Optional[str] = None,
        holder_name: Optional[str] = None,
        status: str = "active",
        created_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        pid = self._next_payout_dest_id()
        if routing_or_bank_code is None:
            routing_or_bank_code = f"0{random.randint(10000000, 99999999)}"
        if destination_hash is None:
            destination_hash = self._generate_payout_hash(routing_or_bank_code, str(random.randint(1000000, 9999999)))
        if holder_name is None:
            holder_name = self.fake.name()
        if created_at is None:
            created_at = self.start_date

        pdest = {
            "payout_destination_id": pid,
            "account_id": account_id,
            "destination_type": dest_type,
            "destination_hash": destination_hash,
            "routing_or_bank_code": routing_or_bank_code,
            "holder_name": holder_name,
            "status": status,
            "created_at": created_at.isoformat()
        }
        self.payout_destinations.append(pdest)
        self.account_payouts.setdefault(account_id, []).append(pdest)
        return pdest

    def _create_transaction(
        self,
        account_id: str,
        timestamp: datetime,
        amount: float,
        transaction_type: str = "purchase",
        status: str = "settled",
        merchant_name: str = "Amazon Marketplace",
        merchant_category: str = "retail",
        instrument_id: Optional[str] = None,
        payout_destination_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        tid = self._next_transaction_id()
        txn = {
            "transaction_id": tid,
            "account_id": account_id,
            "instrument_id": instrument_id or "",
            "payout_destination_id": payout_destination_id or "",
            "timestamp": timestamp.isoformat(),
            "amount": round(amount, 2),
            "currency": "USD",
            "transaction_type": transaction_type,
            "status": status,
            "merchant_id": merchant_name,
            "merchant_category": merchant_category,
            "ip_address": ip_address or "",
            "device_id": device_id or ""
        }
        self.transactions.append(txn)
        return txn

    # -----------------------------------------------------------------------
    # Planted Abuse Rings (10 Rings, 135 Accounts)
    # -----------------------------------------------------------------------

    def _generate_ring_1_card_testing_botnet(self):
        """
        Ring 1: Automated Card Testing Botnet.
        12 accounts, high-velocity micro-charges ($0.50 - $2.50), ~85% decline rate.
        Shared /24 IP subnet (e.g., 185.220.101.xx) and shared bot device fingerprint signature.
        """
        ring_id = "RING_01_CARD_TESTING"
        ring_type = "card_testing"
        base_subnet = "185.220.101"
        bot_device_prefix = "dev_bot_selenium_"
        shared_signals = ["ip_subnet_24", "device_fingerprint_pattern", "high_velocity_micro_declines"]

        attack_start = self.start_date + timedelta(days=random.randint(10, 30))

        for i in range(12):
            acc_id = self._next_account_id()
            acc_created = attack_start + timedelta(minutes=i * 5)
            ip = f"{base_subnet}.{random.randint(10, 240)}"
            device = f"{bot_device_prefix}v4_{hashlib.md5(f'ring1_{i % 3}'.encode()).hexdigest()[:8]}"
            name = self.fake.name()
            email = f"user_{hashlib.md5(name.encode()).hexdigest()[:6]}@proton.me"

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": email,
                "phone_number": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
                "ip_address": ip,
                "device_id": device,
                "account_status": "flagged",
                "risk_score": 0.89,
                "kyc_status": "unverified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": True,
                "ring_id": ring_id,
                "ring_type": ring_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Card-testing botnet running micro-charge validations across shared /24 subnet and bot device fingerprints."
            })

            # Each account attaches 4 stolen cards and tests them in rapid succession
            for _ in range(4):
                inst = self._create_instrument(
                    account_id=acc_id,
                    inst_type="credit_card",
                    is_prepaid=False,
                    added_at=acc_created + timedelta(minutes=random.randint(1, 10))
                )
                for tx_idx in range(6):
                    tx_time = acc_created + timedelta(minutes=10 + tx_idx * 3)
                    amount = round(random.uniform(0.50, 3.00), 2)
                    is_declined = random.random() < 0.85
                    decline_reason = random.choice([
                        "declined_do_not_honor", "declined_insufficient_funds", "declined_fraud_suspected"
                    ])
                    status = decline_reason if is_declined else "settled"

                    self._create_transaction(
                        account_id=acc_id,
                        timestamp=tx_time,
                        amount=amount,
                        transaction_type="card_verification" if amount < 1.5 else "purchase",
                        status=status,
                        merchant_name=random.choice(["Steam Games", "Apple App Store", "Razer Gold"]),
                        merchant_category="digital_goods",
                        instrument_id=inst["instrument_id"],
                        ip_address=ip,
                        device_id=device
                    )

    def _generate_ring_2_card_testing_single_device(self):
        """
        Ring 2: Multi-Account Single Device Card Sprayer.
        10 accounts created on the exact same Android device emulator ID, testing stolen cards.
        """
        ring_id = "RING_02_CARD_TESTING"
        ring_type = "card_testing"
        shared_device = "dev_nox_emu_994a7b1c"
        shared_signals = ["device_id", "rapid_account_creation", "card_testing_declines"]

        attack_start = self.start_date + timedelta(days=random.randint(35, 55))

        for i in range(10):
            acc_id = self._next_account_id()
            acc_created = attack_start + timedelta(minutes=i * 8)
            ip = f"194.26.{random.randint(1, 250)}.{random.randint(1, 250)}"  # proxy pool
            name = f"TestUser {i+1}"
            email = f"autogen.tester.{i+100}@mailhost.xyz"

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": email,
                "phone_number": f"+1-555-01{i:02d}",
                "ip_address": ip,
                "device_id": shared_device,
                "account_status": "suspended",
                "risk_score": 0.94,
                "kyc_status": "unverified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": True,
                "ring_id": ring_id,
                "ring_type": ring_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Single device emulator spinning up multiple accounts to spray stolen card attempts."
            })

            # Create 4 cards per account
            for _ in range(4):
                inst = self._create_instrument(
                    account_id=acc_id,
                    inst_type="credit_card",
                    is_prepaid=False,
                    added_at=acc_created + timedelta(minutes=2)
                )
                for tx_step in range(5):
                    tx_time = acc_created + timedelta(minutes=5 + tx_step * 2)
                    amount = round(random.uniform(0.99, 4.99), 2)
                    status = "declined_fraud_suspected" if random.random() < 0.80 else "settled"
                    self._create_transaction(
                        account_id=acc_id,
                        timestamp=tx_time,
                        amount=amount,
                        transaction_type="purchase",
                        status=status,
                        merchant_name="Google Play Store",
                        merchant_category="digital_goods",
                        instrument_id=inst["instrument_id"],
                        ip_address=ip,
                        device_id=shared_device
                    )

    def _generate_ring_3_card_testing_shared_fingerprints(self):
        """
        Ring 3: Distributed Card Testing Ring with Shared Card Fingerprints.
        14 accounts across different IPs, but circulating and re-trying a pool of 18 stolen card fingerprints.
        """
        ring_id = "RING_03_CARD_TESTING"
        ring_type = "card_testing"
        shared_signals = ["card_fingerprint_overlap", "distributed_card_cycling"]

        # Pool of shared stolen cards
        card_pool = []
        for c_idx in range(18):
            net = random.choice(["VISA", "MASTERCARD"])
            bin_num = random.choice(CARD_BINS[net])
            last4 = f"{random.randint(1000, 9999)}"
            fp = f"fp_stolen_pool_{hashlib.sha256(f'pool_{c_idx}'.encode()).hexdigest()[:12]}"
            card_pool.append({
                "network": net,
                "bin": bin_num,
                "last4": last4,
                "fingerprint": fp,
                "bank": random.choice(ISSUER_BANKS)
            })

        attack_start = self.start_date + timedelta(days=random.randint(20, 45))

        for i in range(14):
            acc_id = self._next_account_id()
            acc_created = attack_start + timedelta(hours=i * 3)
            ip = f"45.142.{random.randint(10, 200)}.{random.randint(10, 240)}"
            device = f"dev_fingerprint_spoof_{i % 5}"
            name = self.fake.name()
            email = f"alpha.card.{i}@tutanota.com"

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": email,
                "phone_number": f"+1-555-88{i:02d}",
                "ip_address": ip,
                "device_id": device,
                "account_status": "flagged",
                "risk_score": 0.88,
                "kyc_status": "unverified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": True,
                "ring_id": ring_id,
                "ring_type": ring_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Distributed ring sharing a common pool of stolen card fingerprints across distinct accounts."
            })

            # Pick 4 cards from the shared pool
            assigned_cards = random.sample(card_pool, 4)
            for card in assigned_cards:
                inst = self._create_instrument(
                    account_id=acc_id,
                    inst_type="credit_card",
                    card_network=card["network"],
                    card_bin=card["bin"],
                    card_last4=card["last4"],
                    card_fingerprint=card["fingerprint"],
                    issuer_bank=card["bank"],
                    added_at=acc_created + timedelta(minutes=15)
                )
                for _ in range(3):
                    tx_time = acc_created + timedelta(minutes=random.randint(20, 300))
                    status = "declined_do_not_honor" if random.random() < 0.75 else "settled"
                    self._create_transaction(
                        account_id=acc_id,
                        timestamp=tx_time,
                        amount=round(random.uniform(1.00, 10.00), 2),
                        transaction_type="purchase",
                        status=status,
                        merchant_name="Target Digital",
                        merchant_category="retail",
                        instrument_id=inst["instrument_id"],
                        ip_address=ip,
                        device_id=device
                    )

    def _generate_ring_4_card_testing_gaming_micro(self):
        """
        Ring 4: Digital Goods / Gaming Micro-charge Testing.
        10 accounts, testing virtual & prepaid cards on gaming platforms at high speed.
        """
        ring_id = "RING_04_CARD_TESTING"
        ring_type = "card_testing"
        shared_ip = "193.106.191.55"
        shared_signals = ["ip_address", "merchant_category_gaming", "high_velocity_burst"]

        attack_start = self.start_date + timedelta(days=random.randint(60, 75))

        for i in range(10):
            acc_id = self._next_account_id()
            acc_created = attack_start + timedelta(minutes=i * 3)
            device = f"dev_game_bot_{i}"
            name = self.fake.name()

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": f"gamer_pro_{i}_{random.randint(100, 999)}@gmail.com",
                "phone_number": f"+1-555-77{i:02d}",
                "ip_address": shared_ip,
                "device_id": device,
                "account_status": "flagged",
                "risk_score": 0.85,
                "kyc_status": "unverified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": True,
                "ring_id": ring_id,
                "ring_type": ring_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Burst card testing targeting gaming merchants from a single proxy IP."
            })

            for _ in range(3):
                inst = self._create_instrument(
                    account_id=acc_id,
                    inst_type="prepaid_card",
                    is_prepaid=True,
                    added_at=acc_created + timedelta(minutes=1)
                )
                for tx_step in range(4):
                    tx_time = acc_created + timedelta(minutes=2 + tx_step)
                    status = "declined_insufficient_funds" if random.random() < 0.70 else "settled"
                    self._create_transaction(
                        account_id=acc_id,
                        timestamp=tx_time,
                        amount=round(random.uniform(0.99, 1.99), 2),
                        transaction_type="purchase",
                        status=status,
                        merchant_name="Razer Gold",
                        merchant_category="gaming_cards",
                        instrument_id=inst["instrument_id"],
                        ip_address=shared_ip,
                        device_id=device
                    )

    def _generate_ring_5_promo_abuse_email_plus(self):
        """
        Ring 5: Promo Abuse via Email Plus-Addressing & Device Farm.
        15 accounts using aliased emails (e.g. master.user+promoXX@gmail.com), shared device IDs,
        claiming welcome bonuses and promo codes with zero real card funding.
        """
        ring_id = "RING_05_PROMO_ABUSE"
        ring_type = "promo_abuse"
        shared_devices = ["dev_farm_bluestacks_01", "dev_farm_bluestacks_02"]
        shared_ip = "185.191.171.12"
        shared_signals = ["email_base_pattern", "device_farm_ids", "shared_ip", "instant_promo_redemption"]

        attack_start = self.start_date + timedelta(days=random.randint(15, 30))

        for i in range(15):
            acc_id = self._next_account_id()
            acc_created = attack_start + timedelta(minutes=i * 12)
            device = shared_devices[i % 2]
            email = f"sybil.collector+promo{i+1:02d}@gmail.com"
            name = f"Sybil User {i+1}"

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": email,
                "phone_number": f"+1-555-90{i:02d}",
                "ip_address": shared_ip,
                "device_id": device,
                "account_status": "flagged",
                "risk_score": 0.87,
                "kyc_status": "unverified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": True,
                "ring_id": ring_id,
                "ring_type": ring_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Sybil farm exploiting sign-up promotions via email plus-addressing on shared emulator devices."
            })

            # Attach virtual card
            inst = self._create_instrument(
                account_id=acc_id,
                inst_type="prepaid_card",
                is_prepaid=True,
                added_at=acc_created + timedelta(minutes=5)
            )

            # Promo bonus credit transaction
            tx_time_1 = acc_created + timedelta(minutes=6)
            self._create_transaction(
                account_id=acc_id,
                timestamp=tx_time_1,
                amount=50.00,
                transaction_type="promo_redemption",
                status="settled",
                merchant_name="Platform Promo Bonus",
                merchant_category="promo_reward",
                instrument_id=inst["instrument_id"],
                ip_address=shared_ip,
                device_id=device
            )

            # Immediate spend on gift cards/digital goods
            tx_time_2 = acc_created + timedelta(minutes=15)
            self._create_transaction(
                account_id=acc_id,
                timestamp=tx_time_2,
                amount=49.99,
                transaction_type="purchase",
                status="settled",
                merchant_name="Amazon Marketplace",
                merchant_category="retail",
                instrument_id=inst["instrument_id"],
                ip_address=shared_ip,
                device_id=device
            )

    def _generate_ring_6_promo_abuse_referral_star(self):
        """
        Ring 6: Star Topology Referral Ring.
        18 accounts: 1 root recruiter account and 17 referee accounts.
        All sharing a common virtual card BIN (510510) and similar phone prefixes.
        """
        ring_id = "RING_06_PROMO_ABUSE"
        ring_type = "promo_abuse"
        shared_bin = "510510"
        shared_signals = ["referral_star_topology", "card_bin_concentration", "phone_number_cluster"]

        attack_start = self.start_date + timedelta(days=random.randint(40, 50))
        parent_acc_id = self._next_account_id()
        parent_created = attack_start
        parent_ip = "104.28.19.45"
        parent_dev = "dev_recruiter_star_001"

        parent_acc = {
            "account_id": parent_acc_id,
            "created_at": parent_created.isoformat(),
            "user_name": "Marcus Root Recruiter",
            "email": "marcus.recruiter@yahoo.com",
            "phone_number": "+1-555-400-0001",
            "ip_address": parent_ip,
            "device_id": parent_dev,
            "account_status": "suspended",
            "risk_score": 0.91,
            "kyc_status": "pending"
        }
        self.accounts.append(parent_acc)
        self.ground_truth.append({
            "account_id": parent_acc_id,
            "is_abuse": True,
            "ring_id": ring_id,
            "ring_type": ring_type,
            "shared_signals": json.dumps(shared_signals),
            "notes": "Root recruiter in star-topology referral abuse network collecting referral bonus payouts."
        })

        parent_inst = self._create_instrument(
            account_id=parent_acc_id,
            inst_type="debit_card",
            card_bin=shared_bin,
            added_at=parent_created
        )
        parent_payout = self._create_payout_destination(
            account_id=parent_acc_id,
            dest_type="bank_account",
            holder_name="Marcus Recruiter",
            created_at=parent_created
        )

        for i in range(17):
            acc_id = self._next_account_id()
            acc_created = parent_created + timedelta(hours=i * 2 + 1)
            ip = f"104.28.19.{random.randint(50, 200)}"
            device = f"dev_star_ref_{i:02d}"
            name = self.fake.name()
            email = f"ref.user.{i+1}_{random.randint(10,99)}@outlook.com"

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": email,
                "phone_number": f"+1-555-400-00{i+2:02d}",
                "ip_address": ip,
                "device_id": device,
                "account_status": "flagged",
                "risk_score": 0.83,
                "kyc_status": "unverified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": True,
                "ring_id": ring_id,
                "ring_type": ring_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Child referee account in star-topology referral ring claiming sign-up rewards."
            })

            inst = self._create_instrument(
                account_id=acc_id,
                inst_type="prepaid_card",
                card_bin=shared_bin,
                added_at=acc_created
            )

            # Referral signup credit
            self._create_transaction(
                account_id=acc_id,
                timestamp=acc_created + timedelta(minutes=5),
                amount=25.00,
                transaction_type="promo_redemption",
                status="settled",
                merchant_name="Platform Promo Bonus",
                merchant_category="promo_reward",
                instrument_id=inst["instrument_id"],
                ip_address=ip,
                device_id=device
            )

            # Referral reward to parent
            self._create_transaction(
                account_id=parent_acc_id,
                timestamp=acc_created + timedelta(minutes=10),
                amount=20.00,
                transaction_type="promo_redemption",
                status="settled",
                merchant_name="Platform Promo Bonus",
                merchant_category="promo_reward",
                instrument_id=parent_inst["instrument_id"],
                ip_address=parent_ip,
                device_id=parent_dev
            )

        # Parent cashes out all accumulated referral bonuses
        self._create_transaction(
            account_id=parent_acc_id,
            timestamp=parent_created + timedelta(days=2),
            amount=340.00,
            transaction_type="withdrawal",
            status="settled",
            merchant_name="Direct P2P Transfer",
            merchant_category="p2p_transfer",
            payout_destination_id=parent_payout["payout_destination_id"],
            ip_address=parent_ip,
            device_id=parent_dev
        )

    def _generate_ring_7_promo_abuse_disposable_domain(self):
        """
        Ring 7: Disposable Domain Coupon Churners.
        12 accounts created with disposable email domains (mailinator.com, tempmail.org),
        sharing same /24 IP gateway, performing $0 coupon redemptions.
        """
        ring_id = "RING_07_PROMO_ABUSE"
        ring_type = "promo_abuse"
        shared_gateway = "195.181.168.10"
        shared_signals = ["disposable_email_domain", "shared_gateway_ip", "zero_dollar_voucher_churn"]

        attack_start = self.start_date + timedelta(days=random.randint(65, 78))

        for i in range(12):
            acc_id = self._next_account_id()
            acc_created = attack_start + timedelta(minutes=i * 20)
            domain = random.choice(["mailinator.com", "tempmail.org", "guerrillamail.com", "trashmail.net"])
            email = f"coupon_hunter_{i}_{hashlib.md5(f'{i}'.encode()).hexdigest()[:4]}@{domain}"

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": self.fake.name(),
                "email": email,
                "phone_number": f"+1-555-66{i:02d}",
                "ip_address": shared_gateway,
                "device_id": f"dev_coupon_bot_{i % 3}",
                "account_status": "flagged",
                "risk_score": 0.82,
                "kyc_status": "unverified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": True,
                "ring_id": ring_id,
                "ring_type": ring_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Disposable domain accounts churning coupon discount codes on shared gateway."
            })

            inst = self._create_instrument(
                account_id=acc_id,
                inst_type="prepaid_card",
                is_prepaid=True,
                added_at=acc_created
            )

            # Promo discount application
            self._create_transaction(
                account_id=acc_id,
                timestamp=acc_created + timedelta(minutes=8),
                amount=30.00,
                transaction_type="promo_redemption",
                status="settled",
                merchant_name="Platform Promo Bonus",
                merchant_category="promo_reward",
                instrument_id=inst["instrument_id"],
                ip_address=shared_gateway,
                device_id=acc["device_id"]
            )
            # Full redemption purchase
            self._create_transaction(
                account_id=acc_id,
                timestamp=acc_created + timedelta(minutes=12),
                amount=30.00,
                transaction_type="purchase",
                status="settled",
                merchant_name="Uber Eats",
                merchant_category="food_delivery",
                instrument_id=inst["instrument_id"],
                ip_address=shared_gateway,
                device_id=acc["device_id"]
            )

    def _generate_ring_8_cashout_funnel_mules(self):
        """
        Ring 8: Mule Account Funnel to Single Consolidation Payout Destination.
        15 mule accounts receive funds and all 15 withdraw/funnel to the EXACT SAME destination hash
        (shared crypto wallet / bank account hash).
        """
        ring_id = "RING_08_CASHOUT"
        ring_type = "cash_out"
        shared_signals = ["shared_payout_destination_hash", "funnel_consolidation", "rapid_payout_drain"]

        # Shared consolidation destination
        shared_dest_hash = f"dest_hash_crypto_consolidator_{hashlib.sha256(b'ring8').hexdigest()[:12]}"
        shared_routing = "021000021"  # Bank / Wire code
        shared_holder = "Nexus Holdings LLC"

        attack_start = self.start_date + timedelta(days=random.randint(15, 35))

        for i in range(15):
            acc_id = self._next_account_id()
            acc_created = attack_start + timedelta(hours=i * 4)
            ip = f"198.54.{random.randint(100, 150)}.{random.randint(1, 250)}"
            device = f"dev_mule_phone_{i:02d}"
            name = self.fake.name()

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": f"mule_holder_{i+1}@safeinbox.cc",
                "phone_number": f"+1-555-33{i:02d}",
                "ip_address": ip,
                "device_id": device,
                "account_status": "flagged",
                "risk_score": 0.93,
                "kyc_status": "unverified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": True,
                "ring_id": ring_id,
                "ring_type": ring_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Mule account funnelling stolen card deposits into a single shared crypto/bank consolidation endpoint."
            })

            # Deposit instrument (stolen credit card)
            inst = self._create_instrument(
                account_id=acc_id,
                inst_type="credit_card",
                added_at=acc_created + timedelta(hours=1)
            )

            # Payout destination (all sharing same destination_hash!)
            pdest = self._create_payout_destination(
                account_id=acc_id,
                dest_type="crypto_wallet",
                destination_hash=shared_dest_hash,
                routing_or_bank_code=shared_routing,
                holder_name=shared_holder,
                created_at=acc_created + timedelta(hours=1, minutes=30)
            )

            # 2 cycles of high value deposit + immediate cash-out
            for cyc in range(2):
                deposit_amt = round(random.uniform(750.00, 2400.00), 2)
                dep_time = acc_created + timedelta(hours=2 + cyc * 12)
                self._create_transaction(
                    account_id=acc_id,
                    timestamp=dep_time,
                    amount=deposit_amt,
                    transaction_type="deposit",
                    status="settled",
                    merchant_name="Coinbase Exchange",
                    merchant_category="crypto_exchange",
                    instrument_id=inst["instrument_id"],
                    ip_address=ip,
                    device_id=device
                )

                wdr_time = dep_time + timedelta(minutes=random.randint(5, 18))
                self._create_transaction(
                    account_id=acc_id,
                    timestamp=wdr_time,
                    amount=round(deposit_amt * 0.97, 2),
                    transaction_type="withdrawal",
                    status="settled",
                    merchant_name="Coinbase Exchange",
                    merchant_category="crypto_exchange",
                    payout_destination_id=pdest["payout_destination_id"],
                    ip_address=ip,
                    device_id=device
                )

    def _generate_ring_9_cashout_rapid_drain(self):
        """
        Ring 9: Rapid Drain Cashout Ring with Shared Device ID & Structured Amounts.
        14 accounts sharing 2 master cash-out control devices, executing structured withdrawals ($950 - $990).
        """
        ring_id = "RING_09_CASHOUT"
        ring_type = "cash_out"
        controller_devices = ["dev_controller_macbook_pro_01", "dev_controller_macbook_pro_02"]
        shared_signals = ["shared_controller_device", "structured_amounts", "short_holding_time"]

        shared_dest_hash = f"dest_hash_wire_mule_{hashlib.sha256(b'ring9').hexdigest()[:12]}"
        attack_start = self.start_date + timedelta(days=random.randint(45, 65))

        for i in range(14):
            acc_id = self._next_account_id()
            acc_created = attack_start + timedelta(hours=i * 3)
            device = controller_devices[i % 2]
            ip = f"185.244.25.{random.randint(10, 240)}"
            name = self.fake.name()

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": f"cash_ops_{i+1}@secure-mail.biz",
                "phone_number": f"+1-555-22{i:02d}",
                "ip_address": ip,
                "device_id": device,
                "account_status": "suspended",
                "risk_score": 0.95,
                "kyc_status": "unverified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": True,
                "ring_id": ring_id,
                "ring_type": ring_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Coordinated cash-out operation using shared control hardware with structured $900+ withdrawals."
            })

            inst = self._create_instrument(
                account_id=acc_id,
                inst_type="bank_account",
                added_at=acc_created
            )
            pdest = self._create_payout_destination(
                account_id=acc_id,
                dest_type="bank_account",
                destination_hash=shared_dest_hash,
                routing_or_bank_code="071000288",
                holder_name="Apex Liquidity Services",
                created_at=acc_created + timedelta(minutes=10)
            )

            # 2 structured deposits and withdrawals
            for step in range(2):
                dep_time = acc_created + timedelta(minutes=30 + step * 180)
                struct_amt = round(random.uniform(940.00, 995.00), 2)
                self._create_transaction(
                    account_id=acc_id,
                    timestamp=dep_time,
                    amount=struct_amt,
                    transaction_type="deposit",
                    status="settled",
                    merchant_name="Kraken Pay",
                    merchant_category="crypto_exchange",
                    instrument_id=inst["instrument_id"],
                    ip_address=ip,
                    device_id=device
                )

                self._create_transaction(
                    account_id=acc_id,
                    timestamp=dep_time + timedelta(minutes=8),
                    amount=struct_amt,
                    transaction_type="withdrawal",
                    status="settled",
                    merchant_name="Direct P2P Transfer",
                    merchant_category="p2p_transfer",
                    payout_destination_id=pdest["payout_destination_id"],
                    ip_address=ip,
                    device_id=device
                )

    def _generate_ring_10_cashout_layered_mule_mesh(self):
        """
        Ring 10: Layered P2P Mule Mesh to Shared Exit Destinations.
        15 accounts: Layer 1 (5 deposit accounts) -> P2P transfers -> Layer 2 (5 intermediate mules) ->
        Layer 3 (5 cashout accounts) sharing 2 destination hashes and shared recovery phones.
        """
        ring_id = "RING_10_CASHOUT"
        ring_type = "cash_out"
        shared_signals = ["p2p_layering_topology", "shared_recovery_phone", "exit_destination_overlap"]

        exit_dest_hashes = [
            f"dest_hash_exit_alpha_{hashlib.sha256(b'exit1').hexdigest()[:10]}",
            f"dest_hash_exit_beta_{hashlib.sha256(b'exit2').hexdigest()[:10]}"
        ]
        shared_phone_base = "+1-555-500-99"

        attack_start = self.start_date + timedelta(days=random.randint(30, 60))
        layer_accounts: List[List[Dict[str, Any]]] = [[], [], []]

        for layer_idx in range(3):
            for i in range(5):
                acc_id = self._next_account_id()
                acc_created = attack_start + timedelta(days=layer_idx, hours=i * 2)
                ip = f"194.135.{random.randint(10, 200)}.{random.randint(1, 250)}"
                dev = f"dev_layered_mesh_l{layer_idx}_{i}"
                phone = f"{shared_phone_base}{layer_idx}"

                acc = {
                    "account_id": acc_id,
                    "created_at": acc_created.isoformat(),
                    "user_name": self.fake.name(),
                    "email": f"mesh_node_l{layer_idx}_{i+1}@ghostmail.net",
                    "phone_number": phone,
                    "ip_address": ip,
                    "device_id": dev,
                    "account_status": "flagged",
                    "risk_score": 0.90,
                    "kyc_status": "unverified"
                }
                self.accounts.append(acc)
                layer_accounts[layer_idx].append(acc)
                self.ground_truth.append({
                    "account_id": acc_id,
                    "is_abuse": True,
                    "ring_id": ring_id,
                    "ring_type": ring_type,
                    "shared_signals": json.dumps(shared_signals),
                    "notes": f"Layer {layer_idx+1} node in 3-tier layering mule network terminating in shared exit endpoints."
                })

        # Generate transactions along the chain: Layer 0 (Deposit) -> Layer 1 (P2P) -> Layer 2 (Withdrawal)
        for i in range(5):
            acc_l0 = layer_accounts[0][i]
            acc_l1 = layer_accounts[1][i]
            acc_l2 = layer_accounts[2][i]

            inst_l0 = self._create_instrument(account_id=acc_l0["account_id"], inst_type="credit_card")
            pdest_l2 = self._create_payout_destination(
                account_id=acc_l2["account_id"],
                dest_type="crypto_wallet",
                destination_hash=exit_dest_hashes[i % 2],
                holder_name="Global Trade Clearing"
            )

            chain_time = attack_start + timedelta(days=3, hours=i * 3)
            amt = round(random.uniform(1200.00, 3500.00), 2)

            # 1. Deposit on L0
            self._create_transaction(
                account_id=acc_l0["account_id"],
                timestamp=chain_time,
                amount=amt,
                transaction_type="deposit",
                status="settled",
                merchant_name="Coinbase Exchange",
                merchant_category="crypto_exchange",
                instrument_id=inst_l0["instrument_id"],
                ip_address=acc_l0["ip_address"],
                device_id=acc_l0["device_id"]
            )

            # 2. P2P transfer L0 -> L1
            p2p_time_1 = chain_time + timedelta(minutes=20)
            self._create_transaction(
                account_id=acc_l0["account_id"],
                timestamp=p2p_time_1,
                amount=amt,
                transaction_type="p2p_transfer",
                status="settled",
                merchant_name=f"Transfer to {acc_l1['account_id']}",
                merchant_category="p2p_transfer",
                ip_address=acc_l0["ip_address"],
                device_id=acc_l0["device_id"]
            )

            # 3. P2P transfer L1 -> L2
            p2p_time_2 = p2p_time_1 + timedelta(minutes=30)
            self._create_transaction(
                account_id=acc_l1["account_id"],
                timestamp=p2p_time_2,
                amount=amt,
                transaction_type="p2p_transfer",
                status="settled",
                merchant_name=f"Transfer to {acc_l2['account_id']}",
                merchant_category="p2p_transfer",
                ip_address=acc_l1["ip_address"],
                device_id=acc_l1["device_id"]
            )

            # 4. Final Cash-Out on L2 to exit destination
            wdr_time = p2p_time_2 + timedelta(minutes=15)
            self._create_transaction(
                account_id=acc_l2["account_id"],
                timestamp=wdr_time,
                amount=amt,
                transaction_type="withdrawal",
                status="settled",
                merchant_name="Coinbase Exchange",
                merchant_category="crypto_exchange",
                payout_destination_id=pdest_l2["payout_destination_id"],
                ip_address=acc_l2["ip_address"],
                device_id=acc_l2["device_id"]
            )

    # -----------------------------------------------------------------------
    # Legit Look-Alike Clusters (3 Clusters, 56 Accounts)
    # -----------------------------------------------------------------------

    def _generate_legit_cluster_1_campus_ip(self):
        """
        Legit Cluster 1: University Campus / Corporate NAT IP.
        20 legitimate independent users sharing single public NAT IP (198.51.100.45).
        Different devices, distinct payment cards, healthy retail/food spending, 98% success rate.
        """
        cluster_id = "LEGIT_CLUSTER_01_CAMPUS_IP"
        cluster_type = "legit_shared_ip"
        shared_campus_ip = "198.51.100.45"
        shared_signals = ["shared_public_ip"]

        for i in range(20):
            acc_id = self._next_account_id()
            acc_created = self._random_date(self.start_date, self.start_date + timedelta(days=40))
            name = self.fake.name()
            email = f"{name.lower().replace(' ', '.')}.{random.randint(10, 99)}@university.edu"
            device = f"dev_student_laptop_{hashlib.md5(f'campus_{i}'.encode()).hexdigest()[:8]}"

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": email,
                "phone_number": f"+1-555-11{i:02d}",
                "ip_address": shared_campus_ip,
                "device_id": device,
                "account_status": "active",
                "risk_score": 0.08,
                "kyc_status": "verified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": False,
                "ring_id": cluster_id,
                "ring_type": cluster_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Legitimate university students/staff sharing campus gateway public NAT IP address."
            })

            inst = self._create_instrument(
                account_id=acc_id,
                inst_type="debit_card",
                is_prepaid=False,
                added_at=acc_created
            )

            # Normal retail, dining, food delivery spending over 60 days
            for _ in range(random.randint(12, 18)):
                tx_time = self._random_date(acc_created + timedelta(days=1), self.end_date)
                m = random.choice([
                    {"name": "Starbucks Rewards", "cat": "dining"},
                    {"name": "DoorDash", "cat": "food_delivery"},
                    {"name": "Amazon Marketplace", "cat": "retail"},
                    {"name": "Target Digital", "cat": "retail"}
                ])
                amt = round(random.uniform(5.50, 75.00), 2)
                status = "declined_insufficient_funds" if random.random() < 0.02 else "settled"

                self._create_transaction(
                    account_id=acc_id,
                    timestamp=tx_time,
                    amount=amt,
                    transaction_type="purchase",
                    status=status,
                    merchant_name=m["name"],
                    merchant_category=m["cat"],
                    instrument_id=inst["instrument_id"],
                    ip_address=shared_campus_ip,
                    device_id=device
                )

    def _generate_legit_cluster_2_family_device(self):
        """
        Legit Cluster 2: Household / Family Shared Device & Home WiFi.
        16 legitimate family members sharing 2 shared household iPad / tablet devices and home IP.
        Normal household purchases: groceries, streaming, utilities.
        """
        cluster_id = "LEGIT_CLUSTER_02_HOUSEHOLD"
        cluster_type = "legit_shared_device"
        home_ip = "73.189.44.120"
        family_devices = ["dev_family_ipad_living_room", "dev_family_ipad_kitchen"]
        shared_signals = ["shared_device_id", "shared_home_ip"]

        family_surnames = ["Miller", "Davis", "Wilson", "Taylor"]

        for i in range(16):
            acc_id = self._next_account_id()
            acc_created = self._random_date(self.start_date, self.start_date + timedelta(days=50))
            surname = family_surnames[i % len(family_surnames)]
            first_name = self.fake.first_name()
            name = f"{first_name} {surname}"
            email = f"{first_name.lower()}.{surname.lower()}{random.randint(1,99)}@gmail.com"
            device = family_devices[i % 2]

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": email,
                "phone_number": f"+1-555-70{i:02d}",
                "ip_address": home_ip,
                "device_id": device,
                "account_status": "active",
                "risk_score": 0.05,
                "kyc_status": "verified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": False,
                "ring_id": cluster_id,
                "ring_type": cluster_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Legitimate household family members sharing a shared home iPad and residential WiFi."
            })

            inst = self._create_instrument(
                account_id=acc_id,
                inst_type="credit_card",
                issuer_bank=random.choice(["JPMorgan Chase", "Bank of America", "Wells Fargo"]),
                added_at=acc_created
            )

            for _ in range(random.randint(10, 16)):
                tx_time = self._random_date(acc_created + timedelta(days=1), self.end_date)
                m = random.choice([
                    {"name": "Walmart Online", "cat": "retail"},
                    {"name": "Apple App Store", "cat": "digital_goods"},
                    {"name": "Uber Eats", "cat": "food_delivery"}
                ])
                amt = round(random.uniform(12.00, 150.00), 2)
                self._create_transaction(
                    account_id=acc_id,
                    timestamp=tx_time,
                    amount=amt,
                    transaction_type="purchase",
                    status="settled",
                    merchant_name=m["name"],
                    merchant_category=m["cat"],
                    instrument_id=inst["instrument_id"],
                    ip_address=home_ip,
                    device_id=device
                )

    def _generate_legit_cluster_3_landlord_payout(self):
        """
        Legit Cluster 3: Property Management / Shared Landlord Payout Destination.
        20 legitimate tenant accounts sending monthly rent to a single property management payout hash.
        Normal monthly cadence, high amounts ($1200 - $2200), high KYC verification, distinct IPs/devices.
        """
        cluster_id = "LEGIT_CLUSTER_03_LANDLORD"
        cluster_type = "legit_shared_payout_dest"
        shared_signals = ["shared_payout_destination_hash"]

        landlord_dest_hash = f"dest_hash_apex_property_mgmt_{hashlib.sha256(b'landlord').hexdigest()[:10]}"
        landlord_routing = "021000021"

        for i in range(20):
            acc_id = self._next_account_id()
            acc_created = self._random_date(self.start_date, self.start_date + timedelta(days=30))
            name = self.fake.name()
            ip = f"67.180.{random.randint(10, 240)}.{random.randint(1, 240)}"
            device = f"dev_tenant_mobile_{i:02d}"

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": f"{name.lower().replace(' ', '.')}.tenant@gmail.com",
                "phone_number": f"+1-555-80{i:02d}",
                "ip_address": ip,
                "device_id": device,
                "account_status": "active",
                "risk_score": 0.04,
                "kyc_status": "verified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": False,
                "ring_id": cluster_id,
                "ring_type": cluster_type,
                "shared_signals": json.dumps(shared_signals),
                "notes": "Legitimate residential tenants transferring monthly rent to verified property manager destination."
            })

            inst = self._create_instrument(
                account_id=acc_id,
                inst_type="bank_account",
                issuer_bank="JPMorgan Chase",
                added_at=acc_created
            )
            pdest = self._create_payout_destination(
                account_id=acc_id,
                dest_type="bank_account",
                destination_hash=landlord_dest_hash,
                routing_or_bank_code=landlord_routing,
                holder_name="Apex Property Management Escrow",
                created_at=acc_created + timedelta(days=1)
            )

            # Monthly rent payments + utility bills
            for month_offset in [5, 35, 65]:
                tx_time = self.start_date + timedelta(days=month_offset, hours=random.randint(8, 18))
                if tx_time > self.end_date:
                    continue
                rent_amt = round(random.uniform(1200.00, 2200.00), 2)
                self._create_transaction(
                    account_id=acc_id,
                    timestamp=tx_time,
                    amount=rent_amt,
                    transaction_type="withdrawal",
                    status="settled",
                    merchant_name="Apex Property Management",
                    merchant_category="real_estate",
                    payout_destination_id=pdest["payout_destination_id"],
                    ip_address=ip,
                    device_id=device
                )

    # -----------------------------------------------------------------------
    # Organic Platform Traffic (409 Accounts -> Total 600 Accounts)
    # -----------------------------------------------------------------------

    def _generate_organic_accounts(self, target_count: int = 409):
        """
        Generates standard legitimate platform users with realistic distributions of:
        - Diverse geo IP addresses
        - Unique personal devices
        - Normal cards and bank accounts
        - Typical e-commerce and P2P transactions
        - Low baseline risk scores and typical ~3% benign decline rate
        """
        for i in range(target_count):
            acc_id = self._next_account_id()
            acc_created = self._random_date(self.start_date, self.end_date - timedelta(days=3))
            name = self.fake.name()
            email = f"{name.lower().replace(' ', '.')}_{random.randint(100, 999)}@{self.fake.free_email_domain()}"
            ip = self.fake.ipv4_public()
            device = f"dev_user_{hashlib.md5(f'{acc_id}_{name}'.encode()).hexdigest()[:12]}"

            acc = {
                "account_id": acc_id,
                "created_at": acc_created.isoformat(),
                "user_name": name,
                "email": email,
                "phone_number": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
                "ip_address": ip,
                "device_id": device,
                "account_status": "active" if random.random() < 0.96 else "suspended",
                "risk_score": round(random.betavariate(1.5, 12.0), 3),
                "kyc_status": "verified" if random.random() < 0.85 else "unverified"
            }
            self.accounts.append(acc)
            self.ground_truth.append({
                "account_id": acc_id,
                "is_abuse": False,
                "ring_id": "ORGANIC_LEGIT",
                "ring_type": "organic_legit",
                "shared_signals": "[]",
                "notes": "Standard organic platform user with regular benign activity."
            })

            # Create 1-3 payment instruments
            num_insts = random.choices([1, 2, 3], weights=[0.65, 0.25, 0.10])[0]
            insts = []
            for _ in range(num_insts):
                itype = random.choices(["credit_card", "debit_card", "bank_account", "prepaid_card"], weights=[0.45, 0.40, 0.12, 0.03])[0]
                inst = self._create_instrument(
                    account_id=acc_id,
                    inst_type=itype,
                    is_prepaid=(itype == "prepaid_card"),
                    added_at=acc_created + timedelta(days=random.randint(0, 5))
                )
                insts.append(inst)

            # Optional payout destination (for ~40% of accounts)
            pdest = None
            if random.random() < 0.40:
                pdest = self._create_payout_destination(
                    account_id=acc_id,
                    dest_type=random.choice(["bank_account", "crypto_wallet", "debit_push"]),
                    holder_name=name,
                    created_at=acc_created + timedelta(days=random.randint(1, 10))
                )

            # Generate realistic organic transactions
            num_txns = random.choices(
                [3, 4, 5, 6, 7, 8, 10, 12],
                weights=[0.10, 0.20, 0.25, 0.20, 0.10, 0.08, 0.05, 0.02]
            )[0]

            for _ in range(num_txns):
                tx_time = self._random_date(acc_created + timedelta(hours=1), self.end_date)
                m = random.choice(MERCHANTS)
                inst = random.choice(insts)

                if m["category"] in ["retail", "dining", "food_delivery"]:
                    tx_type = "purchase"
                    amount = round(random.expovariate(1/45.0) + 3.0, 2)
                elif m["category"] in ["gaming", "digital_goods"]:
                    tx_type = "purchase"
                    amount = round(random.uniform(4.99, 69.99), 2)
                elif m["category"] == "crypto_exchange":
                    tx_type = "deposit" if random.random() < 0.7 else "withdrawal"
                    amount = round(random.uniform(50.0, 800.0), 2)
                elif m["category"] == "p2p_transfer":
                    tx_type = "p2p_transfer"
                    amount = round(random.uniform(15.0, 250.0), 2)
                else:
                    tx_type = "purchase"
                    amount = round(random.uniform(20.0, 300.0), 2)

                if random.random() < 0.04:
                    status = random.choice(["declined_insufficient_funds", "failed"])
                else:
                    status = "settled"

                txn_ip = acc["ip_address"] if random.random() < 0.90 else self.fake.ipv4_public()
                txn_pdest_id = pdest["payout_destination_id"] if (tx_type == "withdrawal" and pdest) else ""

                self._create_transaction(
                    account_id=acc_id,
                    timestamp=tx_time,
                    amount=amount,
                    transaction_type=tx_type,
                    status=status,
                    merchant_name=m["name"],
                    merchant_category=m["category"],
                    instrument_id=inst["instrument_id"] if tx_type != "withdrawal" else "",
                    payout_destination_id=txn_pdest_id,
                    ip_address=txn_ip,
                    device_id=acc["device_id"]
                )

    # -----------------------------------------------------------------------
    # Main Execution Pipeline
    # -----------------------------------------------------------------------

    def generate_all(self) -> Dict[str, pd.DataFrame]:
        print(f"[+] Initializing Synthetic Data Generator (Seed: {self.seed})...")

        # 1. Generate 10 Planted Abuse Rings (135 accounts)
        print("[+] Generating 10 Planted Abuse Rings...")
        self._generate_ring_1_card_testing_botnet()
        self._generate_ring_2_card_testing_single_device()
        self._generate_ring_3_card_testing_shared_fingerprints()
        self._generate_ring_4_card_testing_gaming_micro()
        self._generate_ring_5_promo_abuse_email_plus()
        self._generate_ring_6_promo_abuse_referral_star()
        self._generate_ring_7_promo_abuse_disposable_domain()
        self._generate_ring_8_cashout_funnel_mules()
        self._generate_ring_9_cashout_rapid_drain()
        self._generate_ring_10_cashout_layered_mule_mesh()

        # 2. Generate 3 Legit Look-Alike Clusters (56 accounts)
        print("[+] Generating 3 Legit Look-Alike Clusters...")
        self._generate_legit_cluster_1_campus_ip()
        self._generate_legit_cluster_2_family_device()
        self._generate_legit_cluster_3_landlord_payout()

        # 3. Generate Organic Platform Traffic (409 accounts -> total 600)
        print("[+] Generating Organic Platform Traffic...")
        self._generate_organic_accounts(target_count=409)

        # Convert to DataFrames and sort logically
        df_accounts = pd.DataFrame(self.accounts).sort_values("account_id").reset_index(drop=True)
        df_instruments = pd.DataFrame(self.instruments).sort_values("instrument_id").reset_index(drop=True)
        df_payouts = pd.DataFrame(self.payout_destinations).sort_values("payout_destination_id").reset_index(drop=True)
        df_transactions = pd.DataFrame(self.transactions).sort_values("timestamp").reset_index(drop=True)
        df_ground_truth = pd.DataFrame(self.ground_truth).sort_values("account_id").reset_index(drop=True)

        print("\n" + "="*50)
        print("Dataset Summary Statistics:")
        print("="*50)
        print(f"Total Accounts:            {len(df_accounts):,}")
        print(f"Total Instruments:         {len(df_instruments):,}")
        print(f"Total Payout Destinations: {len(df_payouts):,}")
        print(f"Total Transactions:        {len(df_transactions):,}")
        print(f"Total Ground Truth Labels: {len(df_ground_truth):,}")
        print("-" * 50)
        print("Ground Truth Ring Breakdown:")
        ring_counts = df_ground_truth["ring_id"].value_counts()
        for rid, cnt in ring_counts.items():
            is_ab = df_ground_truth[df_ground_truth["ring_id"] == rid]["is_abuse"].iloc[0]
            status_tag = "[ABUSE]" if is_ab else "[LEGIT]"
            print(f"  - {rid:<32} {status_tag}: {cnt} accounts")
        print("="*50)

        return {
            "accounts": df_accounts,
            "instruments": df_instruments,
            "payout_destinations": df_payouts,
            "transactions": df_transactions,
            "ground_truth": df_ground_truth
        }

    def save_csvs(self, output_dir: str = "data"):
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        dfs = self.generate_all()

        for name, df in dfs.items():
            file_path = out_path / f"{name}.csv"
            df.to_csv(file_path, index=False)
            print(f"[OK] Saved {file_path} ({len(df):,} rows)")


def main():
    parser = argparse.ArgumentParser(description="Synthetic Financial Abuse Ring Data Generator")
    parser.add_argument("--output-dir", type=str, default="data", help="Directory to save generated CSV files")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    generator = SyntheticDataGenerator(seed=args.seed)
    generator.save_csvs(output_dir=args.output_dir)


if __name__ == "__main__":
    main()

