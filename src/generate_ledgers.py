"""
generate_ledgers.py — Seeded synthetic ledger generator for Project 2.

Generates 10,000 realistic records:
  - internal_ledger.csv (~5,000 rows): Trading Desk Cash Book / General Ledger
  - external_statement.csv (~5,000 rows): Custodian / Bank Statement (SWIFT MT940 format)
  - _seeded_breaks_truth.json: Ground truth audit manifest of planted breaks

Sign convention:
  - Internal: +Debit (inflow/asset), -Credit (outflow/payable)
  - External: -Credit (bank obligation to us / inflow), +Debit (bank charge / outflow)
  - Matching condition: internal_amount + external_amount ≈ 0 (exact inverse)
"""

import json
import os
import sys
from datetime import date, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def generate_all_ledgers() -> dict:
    rng = np.random.default_rng(config.RANDOM_SEED)
    os.makedirs(config.DATA_INPUT_DIR, exist_ok=True)

    print("\n--- Generating Reconciling Ledgers ---")
    
    base_date = config.RECON_DATE
    accounts_list = list(config.ACCOUNTS.keys())
    
    internal_rows = []
    external_rows = []
    seeded_breaks = []
    
    txn_types = ["SECURITY_SETTLE", "DIVIDEND", "COLLATERAL", "FX_SPOT", "CUSTODY_FEE"]
    counterparties = ["STATE_STREET", "BNY_MELLON", "CITIBANK", "CLEARSTREAM", "EUROCLEAR", "JPMORGAN"]
    
    # Target baseline clean matches
    n_clean = 4_500
    
    for i in range(1, n_clean + 1):
        int_id = f"INT_TXN_{i:06d}"
        ext_id = f"EXT_STMT_{i:06d}"
        ref_key = f"REF_ST_{i:06d}"
        
        acc = accounts_list[i % len(accounts_list)]
        ccy = config.ACCOUNTS[acc]["currency"]
        ttype = txn_types[i % len(txn_types)]
        cp = counterparties[i % len(counterparties)]
        
        # Transaction date spread over past 90 days
        days_ago = rng.integers(1, 95)
        val_date = base_date - timedelta(days=int(days_ago))
        book_date = val_date - timedelta(days=int(rng.integers(0, 2)))
        
        # Amount: realistic size
        amount = float(rng.uniform(10_000.0, 5_000_000.0))
        direction = 1.0 if rng.random() > 0.45 else -1.0
        int_amount = round(amount * direction, 2)
        ext_amount = round(-int_amount, 2)     # Exact inverse
        
        internal_rows.append({
            "internal_id": int_id,
            "booking_date": str(book_date),
            "value_date": str(val_date),
            "account_id": acc,
            "transaction_type": ttype,
            "reference_key": ref_key,
            "currency": ccy,
            "amount": int_amount,
            "counterparty": cp,
        })
        
        external_rows.append({
            "external_id": ext_id,
            "statement_date": str(val_date),
            "value_date": str(val_date),
            "account_id": acc,
            "bank_ref": ref_key,
            "currency": ccy,
            "amount": ext_amount,
            "narrative": f"SWIFT MT940 {ttype} {ref_key}",
        })

    # ========================================================================
    # SEEDING KNOWN BREAKS (Ground Truth)
    # ========================================================================
    current_idx = n_clean + 1

    # 1. TIMING DIFFERENCES (T+1 to T+4 lag on bank side)
    n_timing = config.BREAK_TARGETS["TIMING_DIFFERENCE"]
    for _ in range(n_timing):
        current_idx += 1
        int_id = f"INT_TXN_{current_idx:06d}"
        ext_id = f"EXT_STMT_{current_idx:06d}"
        ref_key = f"REF_TIMING_{current_idx:06d}"
        acc = accounts_list[current_idx % len(accounts_list)]
        ccy = config.ACCOUNTS[acc]["currency"]
        
        days_ago = rng.integers(5, 75)
        int_val_date = base_date - timedelta(days=int(days_ago))
        lag_days = int(rng.integers(1, 4))
        ext_val_date = int_val_date + timedelta(days=lag_days)
        
        amount = round(float(rng.uniform(50_000, 2_000_000)), 2)
        direction = 1.0 if rng.random() > 0.5 else -1.0
        int_amount = amount * direction
        ext_amount = -int_amount
        
        internal_rows.append({
            "internal_id": int_id,
            "booking_date": str(int_val_date),
            "value_date": str(int_val_date),
            "account_id": acc,
            "transaction_type": "SECURITY_SETTLE",
            "reference_key": ref_key,
            "currency": ccy,
            "amount": int_amount,
            "counterparty": "STATE_STREET",
        })
        external_rows.append({
            "external_id": ext_id,
            "statement_date": str(ext_val_date),
            "value_date": str(ext_val_date),
            "account_id": acc,
            "bank_ref": ref_key,
            "currency": ccy,
            "amount": ext_amount,
            "narrative": f"DVP SETTLE TIMING LAG +{lag_days}D {ref_key}",
        })
        seeded_breaks.append({
            "break_type": "TIMING_DIFFERENCE",
            "internal_id": int_id,
            "external_id": ext_id,
            "reference_key": ref_key,
            "variance_amount": 0.0,
            "timing_lag_days": lag_days,
            "account_id": acc,
        })

    # 2. MISSING INTERNAL BOOKINGS (Bank fees / interest debited by bank, missing from GL)
    n_miss_int = config.BREAK_TARGETS["MISSING_INTERNAL"]
    for _ in range(n_miss_int):
        current_idx += 1
        ext_id = f"EXT_STMT_{current_idx:06d}"
        ref_key = f"REF_UNBOOKED_FEE_{current_idx:06d}"
        acc = accounts_list[current_idx % len(accounts_list)]
        ccy = config.ACCOUNTS[acc]["currency"]
        
        days_ago = rng.integers(2, 85)
        stmt_date = base_date - timedelta(days=int(days_ago))
        fee_amount = round(float(rng.uniform(500.0, 45_000.0)), 2)
        # Bank charge is debit in bank's books (positive under bank statement format or negative outflow)
        # We model bank fee debit as positive in external statement (drawing down balance)
        ext_amount = fee_amount
        
        external_rows.append({
            "external_id": ext_id,
            "statement_date": str(stmt_date),
            "value_date": str(stmt_date),
            "account_id": acc,
            "bank_ref": ref_key,
            "currency": ccy,
            "amount": ext_amount,
            "narrative": f"MONTHLY SAFEKEEPING FEE {ref_key}",
        })
        seeded_breaks.append({
            "break_type": "MISSING_INTERNAL",
            "internal_id": None,
            "external_id": ext_id,
            "reference_key": ref_key,
            "variance_amount": ext_amount,
            "account_id": acc,
            "age_days": days_ago,
        })

    # 3. MISSING EXTERNAL BOOKINGS (Internal trade booked, never settled by bank)
    n_miss_ext = config.BREAK_TARGETS["MISSING_EXTERNAL"]
    for _ in range(n_miss_ext):
        current_idx += 1
        int_id = f"INT_TXN_{current_idx:06d}"
        ref_key = f"REF_PENDING_SETTLE_{current_idx:06d}"
        acc = accounts_list[current_idx % len(accounts_list)]
        ccy = config.ACCOUNTS[acc]["currency"]
        
        days_ago = rng.integers(15, 110)    # Some are aged >90d
        val_date = base_date - timedelta(days=int(days_ago))
        amount = round(float(rng.uniform(100_000.0, 3_500_000.0)), 2)
        direction = 1.0 if rng.random() > 0.5 else -1.0
        int_amount = amount * direction
        
        internal_rows.append({
            "internal_id": int_id,
            "booking_date": str(val_date),
            "value_date": str(val_date),
            "account_id": acc,
            "transaction_type": "SECURITY_SETTLE",
            "reference_key": ref_key,
            "currency": ccy,
            "amount": int_amount,
            "counterparty": "BNY_MELLON",
        })
        seeded_breaks.append({
            "break_type": "MISSING_EXTERNAL",
            "internal_id": int_id,
            "external_id": None,
            "reference_key": ref_key,
            "variance_amount": int_amount,
            "account_id": acc,
            "age_days": days_ago,
        })

    # 4. DUPLICATE INTERNAL BOOKINGS (Accidental double upload against 1 bank line)
    n_dup = config.BREAK_TARGETS["DUPLICATE_BOOKING"]
    for _ in range(n_dup):
        current_idx += 1
        int_id_1 = f"INT_TXN_{current_idx:06d}"
        int_id_2 = f"INT_TXN_{current_idx + 10000:06d}"
        ext_id = f"EXT_STMT_{current_idx:06d}"
        ref_key = f"REF_DUP_{current_idx:06d}"
        acc = accounts_list[current_idx % len(accounts_list)]
        ccy = config.ACCOUNTS[acc]["currency"]
        
        days_ago = rng.integers(3, 40)
        val_date = base_date - timedelta(days=int(days_ago))
        amount = round(float(rng.uniform(25_000.0, 750_000.0)), 2)
        int_amount = amount
        ext_amount = -amount
        
        # Primary internal
        internal_rows.append({
            "internal_id": int_id_1,
            "booking_date": str(val_date),
            "value_date": str(val_date),
            "account_id": acc,
            "transaction_type": "COLLATERAL",
            "reference_key": ref_key,
            "currency": ccy,
            "amount": int_amount,
            "counterparty": "CITIBANK",
        })
        # Duplicate internal
        internal_rows.append({
            "internal_id": int_id_2,
            "booking_date": str(val_date),
            "value_date": str(val_date),
            "account_id": acc,
            "transaction_type": "COLLATERAL",
            "reference_key": ref_key,
            "currency": ccy,
            "amount": int_amount,
            "counterparty": "CITIBANK",
        })
        # Single external
        external_rows.append({
            "external_id": ext_id,
            "statement_date": str(val_date),
            "value_date": str(val_date),
            "account_id": acc,
            "bank_ref": ref_key,
            "currency": ccy,
            "amount": ext_amount,
            "narrative": f"COLLATERAL POSTING {ref_key}",
        })
        seeded_breaks.append({
            "break_type": "DUPLICATE_BOOKING",
            "internal_id_primary": int_id_1,
            "internal_id_duplicate": int_id_2,
            "external_id": ext_id,
            "reference_key": ref_key,
            "duplicate_amount": int_amount,
            "account_id": acc,
        })

    # 5. FX CONVERSION / REVALUATION DIFFERENCES
    n_fx = config.BREAK_TARGETS["FX_MISMATCH"]
    for _ in range(n_fx):
        current_idx += 1
        int_id = f"INT_TXN_{current_idx:06d}"
        ext_id = f"EXT_STMT_{current_idx:06d}"
        ref_key = f"REF_FX_DIFF_{current_idx:06d}"
        acc = accounts_list[current_idx % len(accounts_list)]
        ccy = config.ACCOUNTS[acc]["currency"]
        
        days_ago = rng.integers(10, 60)
        val_date = base_date - timedelta(days=int(days_ago))
        base_amt = round(float(rng.uniform(100_000.0, 1_000_000.0)), 2)
        # Seed rate difference of ~0.5%
        fx_diff = round(base_amt * float(rng.uniform(0.003, 0.008)), 2)
        int_amount = base_amt
        ext_amount = -(base_amt + fx_diff)
        
        internal_rows.append({
            "internal_id": int_id,
            "booking_date": str(val_date),
            "value_date": str(val_date),
            "account_id": acc,
            "transaction_type": "FX_SPOT",
            "reference_key": ref_key,
            "currency": ccy,
            "amount": int_amount,
            "counterparty": "JPMORGAN",
        })
        external_rows.append({
            "external_id": ext_id,
            "statement_date": str(val_date),
            "value_date": str(val_date),
            "account_id": acc,
            "bank_ref": ref_key,
            "currency": ccy,
            "amount": ext_amount,
            "narrative": f"FX SPOT SETTLE REVAL DIFF {ref_key}",
        })
        seeded_breaks.append({
            "break_type": "FX_MISMATCH",
            "internal_id": int_id,
            "external_id": ext_id,
            "reference_key": ref_key,
            "internal_amount": int_amount,
            "external_amount": ext_amount,
            "variance_amount": round(abs(int_amount + ext_amount), 2),
            "account_id": acc,
        })

    # 6. PENNY ROUNDING VARIANCE (Small diffs between $0.02 and $0.08)
    n_round = config.BREAK_TARGETS["ROUNDING_VARIANCE"]
    for _ in range(n_round):
        current_idx += 1
        int_id = f"INT_TXN_{current_idx:06d}"
        ext_id = f"EXT_STMT_{current_idx:06d}"
        ref_key = f"REF_ROUND_{current_idx:06d}"
        acc = accounts_list[current_idx % len(accounts_list)]
        ccy = config.ACCOUNTS[acc]["currency"]
        
        days_ago = rng.integers(1, 30)
        val_date = base_date - timedelta(days=int(days_ago))
        amount = round(float(rng.uniform(10_000.0, 500_000.0)), 2)
        penny_diff = float(rng.choice([0.02, 0.03, 0.04, 0.06, 0.07, 0.08]))
        int_amount = amount
        ext_amount = -(amount + penny_diff)
        
        internal_rows.append({
            "internal_id": int_id,
            "booking_date": str(val_date),
            "value_date": str(val_date),
            "account_id": acc,
            "transaction_type": "SECURITY_SETTLE",
            "reference_key": ref_key,
            "currency": ccy,
            "amount": int_amount,
            "counterparty": "STATE_STREET",
        })
        external_rows.append({
            "external_id": ext_id,
            "statement_date": str(val_date),
            "value_date": str(val_date),
            "account_id": acc,
            "bank_ref": ref_key,
            "currency": ccy,
            "amount": ext_amount,
            "narrative": f"DIVIDEND PENNY ROUNDING {ref_key}",
        })
        seeded_breaks.append({
            "break_type": "ROUNDING_VARIANCE",
            "internal_id": int_id,
            "external_id": ext_id,
            "reference_key": ref_key,
            "variance_amount": round(penny_diff, 2),
            "account_id": acc,
        })

    # Convert to DataFrames
    df_internal = pd.DataFrame(internal_rows)
    df_external = pd.DataFrame(external_rows)

    # Shuffle to simulate real-world ledger feeds
    df_internal = df_internal.sample(frac=1.0, random_state=config.RANDOM_SEED).reset_index(drop=True)
    df_external = df_external.sample(frac=1.0, random_state=config.RANDOM_SEED).reset_index(drop=True)

    # Save CSVs
    int_path = os.path.join(config.DATA_INPUT_DIR, "internal_ledger.csv")
    ext_path = os.path.join(config.DATA_INPUT_DIR, "external_statement.csv")
    truth_path = os.path.join(config.DATA_INPUT_DIR, "_seeded_breaks_truth.json")

    df_internal.to_csv(int_path, index=False)
    df_external.to_csv(ext_path, index=False)
    with open(truth_path, "w", encoding="utf-8") as f:
        json.dump(seeded_breaks, f, indent=2, default=str)

    print(f"  Internal Ledger saved: {len(df_internal)} records -> {int_path}")
    print(f"  External Statement saved: {len(df_external)} records -> {ext_path}")
    print(f"  Ground Truth Manifest: {len(seeded_breaks)} seeded breaks -> {truth_path}")

    return {
        "internal": df_internal,
        "external": df_external,
        "truth": seeded_breaks,
    }


if __name__ == "__main__":
    generate_all_ledgers()
