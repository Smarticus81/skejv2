"""
Shared utilities for PSUR schedule processing
"""
import os
import re
from datetime import datetime, date
from typing import Dict, Any, Tuple
import pandas as pd
from pathlib import Path

# >>> Set this to your actual .xlsx path or via env
PSUR_SCHEDULE_PATH = os.getenv(
    "PSUR_SCHEDULE_PATH",
    r"C:\Users\tmuso\OneDrive\Printer Friendly Receipt Detail_files\Desktop\FUN PROJECTS\skej\2025 Periodic Safety Update Report Master Schedule (2).xlsx"
)

# ---------------- Exact headers from your sheet ----------------
EXACT_HEADERS = {
    "row_id": "TD Number",                     # used as the unique key (renamed to td_number in canon)
    "psur_number": "PSURNumber",
    "class": "Class",
    "type": "Type",
    "product_name": "Product Name",
    "catalog_number": "Catalog Number",
    "writer": "Writer",
    "email": "Email",
    "start_period": "Start Period",
    "end_period": "End Period",
    "frequency": "Frequency",
    "due_date": "Due Date",
    "status": "Status",
    "canada_needed": "Canada Summary Report Needed",
    "canada_status": "Canada Summary Report Status",
    "comments": "Comments",
}

def norm(s: Any) -> str:
    """Normalize string for comparison"""
    s = "" if s is None else str(s)
    return re.sub(r"[^a-z0-9]+", "", s.strip().lower())

def read_excel_auto(path: str) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Auto-detect and read Excel with exact header mapping"""
    xl = pd.ExcelFile(path)
    best_df, best_score = None, -1
    best_map = {}

    # Try every sheet, pick the one that contains all the exact headers
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        if df.empty:
            continue
        have_all = all(h in df.columns for h in EXACT_HEADERS.values())
        score = sum(h in df.columns for h in EXACT_HEADERS.values())
        if have_all and score > best_score:
            best_df = df.copy()
            best_score = score
    if best_df is None:
        # fallback: pick the sheet with max overlap
        for sheet in xl.sheet_names:
            df = pd.read_excel(path, sheet_name=sheet)
            score = sum(h in df.columns for h in EXACT_HEADERS.values())
            if score > best_score:
                best_df = df.copy(); best_score = score
        if best_df is None:
            raise RuntimeError("Workbook has no readable sheets")

    # Use exact header map where present
    best_map = {k: v for k, v in EXACT_HEADERS.items() if v in best_df.columns}

    # Ensure a key column exists
    if "row_id" not in best_map:
        # synthesize from index
        best_df["TD Number"] = best_df.index.astype(str)
        best_map["row_id"] = "TD Number"

    # Parse key dates
    for key in ["start_period", "end_period", "due_date"]:
        col = best_map.get(key)
        if col and col in best_df.columns:
            best_df[col] = pd.to_datetime(best_df[col], errors="coerce").dt.date

    return best_df, best_map

def canon_record(row, colmap: Dict[str, str]) -> Dict[str, Any]:
    """Convert a DataFrame row to canonical dict format"""
    out = {}
    for ckey, actual_col in colmap.items():
        val = row.get(actual_col)
        if pd.isna(val):
            out[ckey] = ""
        elif isinstance(val, (date, datetime)):
            out[ckey] = val.isoformat()
        else:
            out[ckey] = str(val)
    
    # Rename row_id to td_number for consistency
    if "row_id" in out:
        out["td_number"] = out.pop("row_id")
    return out

def save_with_backup(df: pd.DataFrame, path: str):
    """Save DataFrame to Excel with timestamped backup"""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    bak = path.replace(".xlsx", f".bak-{ts}.xlsx")
    df.to_excel(bak, index=False)
    df.to_excel(path, index=False)
    print(f"Saved to {path} (backup: {bak})")
