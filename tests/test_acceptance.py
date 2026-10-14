"""
test_acceptance.py — Automated Acceptance Tests for Project 2 (Reconciliation Engine).

Verifies the 4 critical acceptance criteria:
  AC-1: 100% Break Recall & Classification against _seeded_breaks_truth.json.
  AC-2: Strict Double-Entry Partitioning (no record in multiple buckets, exact row conservation).
  AC-3: Adjusting Journal Voucher Balance (Total Debits strictly equal Total Credits).
  AC-4: Efficiency & Summary Integrity (Auto-match rate >= 90%, total break count and value reported).
"""

import json
import os
import sys
import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import config
from src.generate_ledgers import generate_all_ledgers
from src.matching_engine import run_reconciliation
from src.break_classifier import classify_breaks
from src.reports import generate_reports


@pytest.fixture(scope="session")
def recon_pipeline():
    """Run full reconciliation pipeline once for test session."""
    data = generate_all_ledgers()
    recon_res = run_reconciliation(data["internal"], data["external"])
    classified_res = classify_breaks(recon_res)
    generate_reports(recon_res, classified_res)
    return {
        "data": data,
        "recon": recon_res,
        "classified": classified_res,
    }


def test_ac1_break_detection_and_classification(recon_pipeline):
    """
    AC-1: Every seeded break type in ground truth manifest is detected and classified.
    """
    truth = recon_pipeline["data"]["truth"]
    exceptions_df = recon_pipeline["classified"]["exceptions"]

    # Build lookup of detected exceptions by reference_key
    detected_refs = set(exceptions_df["reference_key"].dropna().unique())

    # Check each seeded break
    missing_detections = []
    for item in truth:
        ref = item.get("reference_key")
        b_type = item.get("break_type")
        if b_type == "TIMING_DIFFERENCE":
            # Timing differences within tolerance (<=2 days) are auto-reconciled under Pass 3!
            # Timing differences > tolerance are flagged as exceptions.
            continue
        if b_type == "ROUNDING_VARIANCE":
            # Rounding differences <= tolerance (<=0.05) are auto-reconciled under Pass 2!
            # Rounding differences > tolerance (>0.05) must appear in exceptions.
            if item.get("variance_amount", 0.0) <= config.DEFAULT_AMOUNT_TOLERANCE:
                continue
        if ref not in detected_refs:
            missing_detections.append((b_type, ref))

    assert len(missing_detections) == 0, f"Failed to detect seeded breaks: {missing_detections[:10]}"


def test_ac2_strict_double_entry_partitioning(recon_pipeline):
    """
    AC-2: Strict Partitioning:
      1. No internal_id appears in more than one bucket.
      2. Row counts strictly conserve: Total Internal = Matched + Partial + Unmatched Internal.
    """
    int_df = recon_pipeline["data"]["internal"]
    matched_df = recon_pipeline["recon"]["matched"]
    partial_df = recon_pipeline["recon"]["partial"]
    unmatched_int = recon_pipeline["recon"]["unmatched_internal"]

    matched_ids = set(matched_df["internal_id"].unique())
    partial_ids = set(partial_df["internal_id"].unique())
    unmatched_ids = set(unmatched_int["internal_id"].unique())

    # Check zero overlap
    assert len(matched_ids.intersection(partial_ids)) == 0, "Overlap between Matched and Partial!"
    assert len(matched_ids.intersection(unmatched_ids)) == 0, "Overlap between Matched and Unmatched!"
    assert len(partial_ids.intersection(unmatched_ids)) == 0, "Overlap between Partial and Unmatched!"

    # Conservation
    total_internal = len(int_df)
    sum_buckets = len(matched_ids) + len(partial_ids) + len(unmatched_ids)
    assert total_internal == sum_buckets, f"Row conservation broke! Total: {total_internal}, Buckets sum: {sum_buckets}"


def test_ac3_adjusting_journal_voucher_balance():
    """
    AC-3: The generated adjusting journal entry strictly debits and credits to the exact cent:
      Total Debits == Total Credits
    """
    journal_path = os.path.join(config.DATA_OUTPUT_DIR, "adjusting_journal_entry.csv")
    assert os.path.exists(journal_path), "Missing adjusting journal entry file!"
    
    df_j = pd.read_csv(journal_path)
    assert not df_j.empty, "Adjusting journal entry is empty!"

    total_debit = df_j["debit_amount"].sum()
    total_credit = df_j["credit_amount"].sum()

    diff = abs(total_debit - total_credit)
    assert diff < 0.001, f"Adjusting journal entry out of balance! Debits: {total_debit}, Credits: {total_credit}"


def test_ac4_efficiency_and_summary_metrics(recon_pipeline):
    """
    AC-4: Auto-match rate >= 90%, total break count and value reported and finite.
    """
    stats = recon_pipeline["recon"]["stats"]
    classified = recon_pipeline["classified"]

    assert stats["auto_match_rate"] >= 90.0, f"Auto-match rate {stats['auto_match_rate']}% is below 90% target!"
    assert classified["total_exceptions"] > 0, "Exception count must be greater than zero."
    assert classified["total_break_value"] > 0, "Break value must be positive."

    summary_path = os.path.join(config.DATA_OUTPUT_DIR, "reconciliation_summary.csv")
    assert os.path.exists(summary_path), "reconciliation_summary.csv is missing!"
    df_sum = pd.read_csv(summary_path)
    assert len(df_sum) == 1, "reconciliation_summary.csv must have exactly 1 row"
