# src/parsers.py
from __future__ import annotations
import re
from pathlib import Path
from typing import Tuple, Optional
import pandas as pd
import numpy as np

TZ = "Asia/Kolkata"

# flow parser
def load_flow_csv(path: Path | str) -> pd.DataFrame:
    """
    Flow CSV has repeating header blocks ("Date | Time | Totalizer").
    Returns tidy DataFrame: [timestamp (tz-aware), totalizer (float), consumption (float)]
    """
    raw = pd.read_csv(path, dtype=str).fillna("")
    # identify header rows
    is_header = (
        (raw.iloc[:, 0].str.strip().str.lower() == "date")
        & (raw.iloc[:, 1].str.strip().str.lower() == "time")
        & (raw.iloc[:, 2].str.strip().str.lower().str.contains("totalizer"))
    )
    header_idxs = list(raw[is_header].index) + [len(raw)]

    blocks = []
    for i in range(len(header_idxs) - 1):
        start = header_idxs[i] + 1
        end = header_idxs[i + 1]
        if start >= end:
            continue
        block = raw.iloc[start:end, :3].copy()
        block.columns = ["date", "time", "totalizer"]
        # keep rows with all three fields
        block = block[
            (block["date"].str.strip() != "")
            & (block["time"].str.strip() != "")
            & (block["totalizer"].str.strip() != "")
        ]
        # parse types
        ts = pd.to_datetime(
            block["date"].str.strip() + " " + block["time"].str.strip(),
            dayfirst=True, errors="coerce"
        )
        block["timestamp"] = ts.dt.tz_localize(TZ, nonexistent="shift_forward", ambiguous="NaT")
        block["totalizer"] = pd.to_numeric(block["totalizer"].str.replace(",", ""), errors="coerce")
        block = block.dropna(subset=["timestamp", "totalizer"]).sort_values("timestamp")
        blocks.append(block[["timestamp", "totalizer"]])

    if not blocks:
        return pd.DataFrame(columns=["timestamp", "totalizer", "consumption"])

    df = (
        pd.concat(blocks, ignore_index=True)
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    # per-interval consumption = diff(totalizer)
    df["consumption"] = df["totalizer"].diff()
    # treat resets/negatives as 0 for that interval
    df.loc[df["consumption"] < 0, "consumption"] = 0.0
    # fill first interval nan with 0
    df["consumption"] = df["consumption"].fillna(0.0)

    return df

# quality parser
# header format example: '1. humidity (humidity), safe range: (30 to 70)'
PARAM_RE = re.compile(r"^\s*\d+\.\s*(.+?)\s*,\s*Safe Range:\s*\(([^)]+)\)\s*$", re.I)

def _parse_safe_range(text: str) -> Tuple[Optional[float], Optional[float]]:
    # expects 'a to b'
    if not isinstance(text, str):
        return (None, None)
    parts = text.split("to")
    if len(parts) != 2:
        return (None, None)
    try:
        return (float(parts[0].strip()), float(parts[1].strip()))
    except Exception:
        return (None, None)

def load_quality_csv(path: Path | str) -> pd.DataFrame:
    """
    Quality CSV is grouped by parameter blocks:
      "<n>. NAME (CODE), Safe Range: (a to b)"
      "Date | Time | Value"
      rows...
    Returns tidy: [timestamp, parameter, value, safe_min, safe_max]
    """
    raw = pd.read_csv(path, dtype=str).fillna("")
    rows = raw.values.tolist()

    out = []
    current_param = None
    safe_min = safe_max = None
    in_table = False

    for r in rows:
        cells = [str(x).strip() for x in r if str(x).strip() != ""]
        if not cells:
            continue

        # param header?
        m = PARAM_RE.match(cells[0])
        if m:
            current_param = m.group(1).strip()
            safe_min, safe_max = _parse_safe_range(m.group(2).strip())
            in_table = False
            continue

        # table header?
        if current_param and len(cells) >= 3 and cells[0].lower() == "date" and cells[1].lower() == "time":
            in_table = True
            continue

        # table row
        if in_table and current_param:
            # expect [date, time, value]
            if len(cells) < 3:
                continue
            date_str, time_str, val_str = cells[0], cells[1], cells[2]
            ts = pd.to_datetime(f"{date_str} {time_str}", dayfirst=True, errors="coerce")
            if pd.isna(ts):
                continue
            val = pd.to_numeric(val_str.replace(",", ""), errors="coerce")
            out.append({
                "timestamp": ts.tz_localize(TZ, nonexistent="shift_forward", ambiguous="NaT"),
                "parameter": current_param,
                "value": val,
                "safe_min": safe_min,
                "safe_max": safe_max
            })

    if not out:
        return pd.DataFrame(columns=["timestamp", "parameter", "value", "safe_min", "safe_max"])

    df = pd.DataFrame(out).dropna(subset=["timestamp"]).sort_values(["parameter", "timestamp"]).reset_index(drop=True)
    return df
