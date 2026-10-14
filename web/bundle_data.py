"""
bundle_data.py — Packs Project 2 reconciliation outputs into web/data.js for instant browser reactivity.
"""

import json
import os
import sys
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
import config


def export_bundle():
    out_dir = config.DATA_OUTPUT_DIR
    in_dir = config.DATA_INPUT_DIR
    web_dir = os.path.join(PROJECT_ROOT, "web")
    os.makedirs(web_dir, exist_ok=True)

    summary = pd.read_csv(os.path.join(out_dir, "reconciliation_summary.csv")).to_dict(orient="records")[0]
    matched_sample = pd.read_csv(os.path.join(out_dir, "matched_pairs.csv")).head(300).to_dict(orient="records")
    exceptions = pd.read_csv(os.path.join(out_dir, "break_exception_report.csv")).to_dict(orient="records")
    ageing = pd.read_csv(os.path.join(out_dir, "ageing_matrix.csv")).to_dict(orient="records")
    journal = pd.read_csv(os.path.join(out_dir, "adjusting_journal_entry.csv")).to_dict(orient="records")
    
    # Also load sample of raw internal & external for the drag-and-drop / ledger explorer
    int_sample = pd.read_csv(os.path.join(in_dir, "internal_ledger.csv")).head(200).to_dict(orient="records")
    ext_sample = pd.read_csv(os.path.join(in_dir, "external_statement.csv")).head(200).to_dict(orient="records")

    bundle = {
        "summary": summary,
        "matched_sample": matched_sample,
        "exceptions": exceptions,
        "ageing": ageing,
        "journal": journal,
        "accounts": config.ACCOUNTS,
        "internal_sample": int_sample,
        "external_sample": ext_sample,
    }

    js_content = f"window.RECON_DATA = {json.dumps(bundle, indent=2)};"
    js_path = os.path.join(web_dir, "data.js")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"Web dataset bundle written to {js_path} ({len(exceptions)} exceptions, {len(journal)} journal lines)")


if __name__ == "__main__":
    export_bundle()
