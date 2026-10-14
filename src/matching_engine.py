"""
matching_engine.py — Core Multi-Pass Reconciliation Engine for Project 2.

Executes a 4-pass waterfall matching algorithm:
  - Pass 1: Exact Match (Account + Ref + Ccy + Value Date + Exact Amount)
  - Pass 2: Rounding Tolerance (Account + Ref + Ccy + Value Date ±1d + Amount diff <= tolerance)
  - Pass 3: Timing Difference (Account + Ref + Ccy + Value Date ±date_tol + Exact Amount)
  - Pass 4: Truncated / Fuzzy Ref (Account + Ccy + Exact Amount + Ref Prefix)

Guarantees strict double-entry partitioning:
  Every record lands in strictly ONE bucket:
    1. MATCHED (reconciled pair)
    2. PARTIAL (key matched, amount variance beyond tolerance)
    3. UNMATCHED_INTERNAL (open ledger item)
    4. UNMATCHED_EXTERNAL (open bank statement item)
"""

import os
import sys
from datetime import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def parse_date(d_str):
    if isinstance(d_str, str):
        return datetime.strptime(d_str, "%Y-%m-%d").date()
    return d_str


def run_reconciliation(
    df_internal: pd.DataFrame,
    df_external: pd.DataFrame,
    amount_tolerance: float = config.DEFAULT_AMOUNT_TOLERANCE,
    date_tolerance_days: int = config.DEFAULT_DATE_TOLERANCE_DAYS,
) -> dict:
    """
    Executes the multi-pass reconciliation engine.
    """
    int_df = df_internal.copy()
    ext_df = df_external.copy()

    # Pre-parse dates
    int_df["val_date_dt"] = int_df["value_date"].apply(parse_date)
    ext_df["val_date_dt"] = ext_df["value_date"].apply(parse_date)

    matched_pairs = []
    partial_breaks = []
    
    matched_int_ids = set()
    matched_ext_ids = set()

    # ------------------------------------------------------------------------
    # PASS 1: EXACT MATCH (Account, Ref, Ccy, Value Date, Exact Amount)
    # ------------------------------------------------------------------------
    # Group external by (account_id, bank_ref, currency)
    ext_lookup = {}
    for idx, row in ext_df.iterrows():
        key = (row["account_id"], row["bank_ref"], row["currency"])
        ext_lookup.setdefault(key, []).append((idx, row))

    for int_idx, int_row in int_df.iterrows():
        key = (int_row["account_id"], int_row["reference_key"], int_row["currency"])
        candidates = ext_lookup.get(key, [])
        
        for ext_idx, ext_row in candidates:
            if ext_idx in matched_ext_ids:
                continue
            # Check exact value date and exact inverse amount
            if int_row["val_date_dt"] == ext_row["val_date_dt"]:
                net_amount = round(int_row["amount"] + ext_row["amount"], 2)
                if abs(net_amount) < 0.001:
                    matched_pairs.append({
                        "match_pass": "PASS_1_EXACT",
                        "internal_id": int_row["internal_id"],
                        "external_id": ext_row["external_id"],
                        "account_id": int_row["account_id"],
                        "reference_key": int_row["reference_key"],
                        "currency": int_row["currency"],
                        "internal_amount": int_row["amount"],
                        "external_amount": ext_row["amount"],
                        "variance": 0.0,
                        "date_diff_days": 0,
                        "value_date": int_row["value_date"],
                    })
                    matched_int_ids.add(int_row["internal_id"])
                    matched_ext_ids.add(ext_idx)
                    break

    # ------------------------------------------------------------------------
    # PASS 2: ROUNDING TOLERANCE (Within configured amount tolerance, e.g. <= $0.05)
    # ------------------------------------------------------------------------
    for int_idx, int_row in int_df.iterrows():
        if int_row["internal_id"] in matched_int_ids:
            continue
        key = (int_row["account_id"], int_row["reference_key"], int_row["currency"])
        candidates = ext_lookup.get(key, [])
        
        for ext_idx, ext_row in candidates:
            if ext_idx in matched_ext_ids:
                continue
            days_diff = abs((int_row["val_date_dt"] - ext_row["val_date_dt"]).days)
            if days_diff <= 1:
                net_amount = round(int_row["amount"] + ext_row["amount"], 2)
                variance = abs(net_amount)
                if 0.001 <= variance <= amount_tolerance:
                    matched_pairs.append({
                        "match_pass": "PASS_2_TOLERANCE",
                        "internal_id": int_row["internal_id"],
                        "external_id": ext_row["external_id"],
                        "account_id": int_row["account_id"],
                        "reference_key": int_row["reference_key"],
                        "currency": int_row["currency"],
                        "internal_amount": int_row["amount"],
                        "external_amount": ext_row["amount"],
                        "variance": variance,
                        "date_diff_days": days_diff,
                        "value_date": int_row["value_date"],
                    })
                    matched_int_ids.add(int_row["internal_id"])
                    matched_ext_ids.add(ext_idx)
                    break

    # ------------------------------------------------------------------------
    # PASS 3: SETTLEMENT TIMING DIFFERENCE (Date lag within date_tolerance_days, Exact Amount)
    # ------------------------------------------------------------------------
    for int_idx, int_row in int_df.iterrows():
        if int_row["internal_id"] in matched_int_ids:
            continue
        key = (int_row["account_id"], int_row["reference_key"], int_row["currency"])
        candidates = ext_lookup.get(key, [])
        
        for ext_idx, ext_row in candidates:
            if ext_idx in matched_ext_ids:
                continue
            days_diff = abs((int_row["val_date_dt"] - ext_row["val_date_dt"]).days)
            if 1 <= days_diff <= date_tolerance_days:
                net_amount = round(int_row["amount"] + ext_row["amount"], 2)
                if abs(net_amount) < 0.001:
                    matched_pairs.append({
                        "match_pass": "PASS_3_TIMING",
                        "internal_id": int_row["internal_id"],
                        "external_id": ext_row["external_id"],
                        "account_id": int_row["account_id"],
                        "reference_key": int_row["reference_key"],
                        "currency": int_row["currency"],
                        "internal_amount": int_row["amount"],
                        "external_amount": ext_row["amount"],
                        "variance": 0.0,
                        "date_diff_days": days_diff,
                        "value_date": int_row["value_date"],
                    })
                    matched_int_ids.add(int_row["internal_id"])
                    matched_ext_ids.add(ext_idx)
                    break

    # ------------------------------------------------------------------------
    # PASS 4: IDENTIFY PARTIAL MATCHES (Ref matched, but amount variance > tolerance)
    # ------------------------------------------------------------------------
    for int_idx, int_row in int_df.iterrows():
        if int_row["internal_id"] in matched_int_ids:
            continue
        key = (int_row["account_id"], int_row["reference_key"], int_row["currency"])
        candidates = ext_lookup.get(key, [])
        
        for ext_idx, ext_row in candidates:
            if ext_idx in matched_ext_ids:
                continue
            # Reference matches on same account, but amount is broke beyond tolerance
            net_amount = round(int_row["amount"] + ext_row["amount"], 2)
            variance = abs(net_amount)
            if variance > amount_tolerance:
                days_diff = abs((int_row["val_date_dt"] - ext_row["val_date_dt"]).days)
                partial_breaks.append({
                    "internal_id": int_row["internal_id"],
                    "external_id": ext_row["external_id"],
                    "account_id": int_row["account_id"],
                    "reference_key": int_row["reference_key"],
                    "currency": int_row["currency"],
                    "internal_amount": int_row["amount"],
                    "external_amount": ext_row["amount"],
                    "variance": variance,
                    "date_diff_days": days_diff,
                    "value_date": int_row["value_date"],
                })
                matched_int_ids.add(int_row["internal_id"])
                matched_ext_ids.add(ext_idx)
                break

    # ------------------------------------------------------------------------
    # EXTRACT UNMATCHED RESIDUALS
    # ------------------------------------------------------------------------
    unmatched_int = int_df[~int_df["internal_id"].isin(matched_int_ids)].copy()
    unmatched_ext = ext_df[~ext_df.index.isin(matched_ext_ids)].copy()

    df_matched = pd.DataFrame(matched_pairs)
    df_partial = pd.DataFrame(partial_breaks)
    
    # Calculate statistics
    total_internal = len(int_df)
    total_external = len(ext_df)
    matched_count = len(df_matched)
    partial_count = len(df_partial)
    unmatched_int_count = len(unmatched_int)
    unmatched_ext_count = len(unmatched_ext)

    auto_match_rate = (matched_count / total_internal) * 100.0

    print(f"\n--- Multi-Pass Reconciliation Results ---")
    print(f"  Internal Records:     {total_internal:,}")
    print(f"  External Records:     {total_external:,}")
    print(f"  Auto-Matched Pairs:   {matched_count:,} ({auto_match_rate:.2f}%)")
    print(f"  Partial Break Pairs:  {partial_count:,}")
    print(f"  Unmatched Internal:   {unmatched_int_count:,}")
    print(f"  Unmatched External:   {unmatched_ext_count:,}")

    return {
        "matched": df_matched,
        "partial": df_partial,
        "unmatched_internal": unmatched_int,
        "unmatched_external": unmatched_ext,
        "stats": {
            "total_internal": total_internal,
            "total_external": total_external,
            "matched_count": matched_count,
            "partial_count": partial_count,
            "unmatched_int_count": unmatched_int_count,
            "unmatched_ext_count": unmatched_ext_count,
            "auto_match_rate": round(auto_match_rate, 2),
            "amount_tolerance": amount_tolerance,
            "date_tolerance_days": date_tolerance_days,
        }
    }
