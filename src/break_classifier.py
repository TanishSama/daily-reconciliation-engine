"""
break_classifier.py — Root-Cause Taxonomy & Regulatory Ageing Engine for Project 2.

Classifies every break into one of 6 root causes:
  1. TIMING_LAG_EXCEEDED (Settled with lag > allowed tolerance window)
  2. FX_REVALUATION_MISMATCH (Currency conversion variance)
  3. ROUNDING_VARIANCE_EXCEEDED (Penny rounding variance > tolerance)
  4. DUPLICATE_POSTING (Internal entry booked multiple times)
  5. MISSING_INTERNAL_BOOKING (Bank debits/credits missing from GL, e.g. custody fees)
  6. MISSING_EXTERNAL_BOOKING (GL entries pending bank settlement)

Computes days aged relative to valuation date and assigns regulatory risk bucket:
  - 0-30 days: Low Risk
  - 31-60 days: Medium Risk
  - 61-90 days: High Risk
  - >90 days: Critical Risk (Potential P&L Write-off)
"""

import os
import sys
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def get_age_bucket(days: int) -> tuple[str, str]:
    """Returns (bucket_label, risk_level)."""
    for label, min_d, max_d, risk in config.AGEING_BUCKETS:
        if min_d <= days <= max_d:
            return label, risk
    return ">90 days", "CRITICAL"


def parse_date(d):
    if isinstance(d, str):
        return datetime.strptime(d, "%Y-%m-%d").date()
    return d


def classify_breaks(recon_results: dict) -> dict:
    """
    Classifies all breaks and computes ageing matrix.
    """
    recon_date = config.RECON_DATE
    
    partial_df = recon_results["partial"]
    unmatched_int = recon_results["unmatched_internal"]
    unmatched_ext = recon_results["unmatched_external"]

    exception_rows = []

    # 1. Classify Partial Breaks (Both sides present, amount variance > tolerance)
    for _, row in partial_df.iterrows():
        val_date = parse_date(row["value_date"])
        age_days = max(0, (recon_date - val_date).days)
        bucket, risk = get_age_bucket(age_days)
        variance = row["variance"]

        if variance <= 0.15:
            cause = "ROUNDING_VARIANCE_EXCEEDED"
            action = f"Post penny variance adjustment of {row['currency']} {variance:.2f} to rounding expense"
        else:
            cause = "FX_REVALUATION_MISMATCH"
            action = f"Verify FX spot rate used in GL vs Custodian confirmation; post FX revaluation delta"

        exception_rows.append({
            "break_id": f"BRK_PARTIAL_{len(exception_rows)+1:05d}",
            "root_cause": cause,
            "origin": "PARTIAL_MATCH",
            "account_id": row["account_id"],
            "reference_key": row["reference_key"],
            "currency": row["currency"],
            "break_amount": variance,
            "internal_id": row["internal_id"],
            "external_id": row["external_id"],
            "value_date": str(val_date),
            "age_days": age_days,
            "age_bucket": bucket,
            "risk_level": risk,
            "remediation_action": action,
        })

    # 2. Check for Duplicate Bookings inside Unmatched Internal
    # Group unmatched internal by (account_id, reference_key, amount)
    dup_counts = unmatched_int.groupby(["account_id", "reference_key", "amount"]).size()
    duplicate_keys = set(dup_counts[dup_counts > 1].index)
    handled_int_ids = set()

    for _, row in unmatched_int.iterrows():
        key = (row["account_id"], row["reference_key"], row["amount"])
        val_date = parse_date(row["value_date"])
        age_days = max(0, (recon_date - val_date).days)
        bucket, risk = get_age_bucket(age_days)

        if key in duplicate_keys:
            cause = "DUPLICATE_POSTING"
            action = f"Reverse redundant internal journal entry {row['internal_id']} (duplicate booking)"
        else:
            cause = "MISSING_EXTERNAL_BOOKING"
            action = f"Escalate unconfirmed trade to Settlement Ops; query custodian {row['counterparty']}"

        exception_rows.append({
            "break_id": f"BRK_INT_{len(exception_rows)+1:05d}",
            "root_cause": cause,
            "origin": "UNMATCHED_INTERNAL",
            "account_id": row["account_id"],
            "reference_key": row["reference_key"],
            "currency": row["currency"],
            "break_amount": abs(row["amount"]),
            "internal_id": row["internal_id"],
            "external_id": None,
            "value_date": str(val_date),
            "age_days": age_days,
            "age_bucket": bucket,
            "risk_level": risk,
            "remediation_action": action,
        })
        handled_int_ids.add(row["internal_id"])

    # 3. Classify Unmatched External (Bank statement entries missing internally)
    for _, row in unmatched_ext.iterrows():
        val_date = parse_date(row["value_date"])
        age_days = max(0, (recon_date - val_date).days)
        bucket, risk = get_age_bucket(age_days)

        cause = "MISSING_INTERNAL_BOOKING"
        narrative = str(row.get("narrative", "")).upper()
        if "FEE" in narrative or "SAFEKEEPING" in narrative:
            action = f"Post adjusting entry: Debit Custody Fee Expense / Credit Cash at Bank"
        else:
            action = f"Investigate unbooked external credit/debit; obtain MT940 swift confirmation"

        exception_rows.append({
            "break_id": f"BRK_EXT_{len(exception_rows)+1:05d}",
            "root_cause": cause,
            "origin": "UNMATCHED_EXTERNAL",
            "account_id": row["account_id"],
            "reference_key": row["bank_ref"],
            "currency": row["currency"],
            "break_amount": abs(row["amount"]),
            "internal_id": None,
            "external_id": row["external_id"],
            "value_date": str(val_date),
            "age_days": age_days,
            "age_bucket": bucket,
            "risk_level": risk,
            "remediation_action": action,
        })

    df_exceptions = pd.DataFrame(exception_rows)

    # Compute Ageing Matrix
    ageing_summary = df_exceptions.groupby(["age_bucket", "risk_level"]).agg(
        break_count=("break_id", "count"),
        total_break_value=("break_amount", "sum")
    ).reset_index()

    # Sort ageing by order in config
    bucket_order = {b[0]: i for i, b in enumerate(config.AGEING_BUCKETS)}
    ageing_summary["sort_key"] = ageing_summary["age_bucket"].map(bucket_order)
    ageing_summary = ageing_summary.sort_values("sort_key").drop(columns=["sort_key"])

    # Compute Root Cause breakdown
    cause_summary = df_exceptions.groupby("root_cause").agg(
        break_count=("break_id", "count"),
        total_break_value=("break_amount", "sum")
    ).reset_index()

    print("\n--- Break Classification & Ageing Matrix ---")
    print(f"  Total Exceptions Classified: {len(df_exceptions):,}")
    print(f"  Gross Break Value:          ${df_exceptions['break_amount'].sum():,.2f}")
    print("\n  Ageing Distribution:")
    for _, r in ageing_summary.iterrows():
        print(f"    • {r['age_bucket']:<12} ({r['risk_level']:<8}): {r['break_count']:>4} breaks | ${r['total_break_value']:>14,.2f}")

    return {
        "exceptions": df_exceptions,
        "ageing_matrix": ageing_summary,
        "cause_summary": cause_summary,
        "total_exceptions": len(df_exceptions),
        "total_break_value": round(df_exceptions["break_amount"].sum(), 2),
    }
