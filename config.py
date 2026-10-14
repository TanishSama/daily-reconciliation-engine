"""
config.py — Central configuration for the Automated Reconciliation & Break Engine.

All matching tolerances, ageing thresholds, account definitions, and break seed
parameters are centralized here for full reproducibility and auditability.
"""

import os
from datetime import date

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_INPUT_DIR = os.path.join(PROJECT_ROOT, "data", "input")
DATA_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "output")
WEB_DIR = os.path.join(PROJECT_ROOT, "web")

# ---------------------------------------------------------------------------
# Reconciliation Valuation Date & Seed
# ---------------------------------------------------------------------------
RECON_DATE = date(2024, 9, 30)         # Month-end reconciliation snapshot
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Scale Targets
# ---------------------------------------------------------------------------
TARGET_TOTAL_RECORDS = 10_000          # ~5,000 internal + ~5,000 external
INTERNAL_RECORDS = 5_000
EXTERNAL_RECORDS = 5_000

# ---------------------------------------------------------------------------
# Nostro Accounts & Currencies
# ---------------------------------------------------------------------------
ACCOUNTS = {
    "ACC_JPM_USD_01": {"bank": "J.P. Morgan NY", "currency": "USD", "type": "Cash Settlement"},
    "ACC_CITI_USD_02": {"bank": "Citibank NY", "currency": "USD", "type": "Collateral & Margin"},
    "ACC_BNY_EUR_01": {"bank": "BNY Mellon Frankfurt", "currency": "EUR", "type": "Euroclear Settle"},
    "ACC_BARC_GBP_01": {"bank": "Barclays London", "currency": "GBP", "type": "CREST Settlement"},
    "ACC_HDFC_INR_01": {"bank": "HDFC Bank Mumbai", "currency": "INR", "type": "NSE/BSE Custody"},
    "ACC_MUFG_JPY_01": {"bank": "MUFG Bank Tokyo", "currency": "JPY", "type": "BOJ Net Settle"},
}

# ---------------------------------------------------------------------------
# Matching Tolerances & Rules
# ---------------------------------------------------------------------------
DEFAULT_AMOUNT_TOLERANCE = 0.05        # $0.05 penny rounding tolerance
DEFAULT_DATE_TOLERANCE_DAYS = 2        # ±2 business days settlement lag
MAX_TIMING_WINDOW_DAYS = 5             # Up to 5 days for aged timing checks

# ---------------------------------------------------------------------------
# Seeded Breaks Calibration (Ground Truth)
# ---------------------------------------------------------------------------
BREAK_TARGETS = {
    "TIMING_DIFFERENCE": 140,          # Settled with 1-4 days timing lag
    "MISSING_INTERNAL": 60,            # On bank statement, missing from GL (e.g. custody fees)
    "MISSING_EXTERNAL": 75,            # In GL, pending custodian confirmation
    "DUPLICATE_BOOKING": 30,           # Two internal entries against single external
    "FX_MISMATCH": 45,                 # Currency converted at different rate
    "ROUNDING_VARIANCE": 50,           # Mismatch within/near penny tolerance
}

# ---------------------------------------------------------------------------
# Ageing Thresholds (Days)
# ---------------------------------------------------------------------------
AGEING_BUCKETS = [
    ("0-30 days", 0, 30, "LOW"),
    ("31-60 days", 31, 60, "MEDIUM"),
    ("61-90 days", 61, 90, "HIGH"),
    (">90 days", 91, 9999, "CRITICAL"),
]
