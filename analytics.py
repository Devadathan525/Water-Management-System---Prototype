# src/analytics.py
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, Tuple

SHIFT_DEF = [
    ("Shift A", 6, 14),   # 06:00–14:00
    ("Shift B", 14, 22),  # 14:00–22:00
    ("Shift C", 22, 6),   # 22:00–06:00 (overnight)
]

def _add_time_parts(df: pd.DataFrame) -> pd.DataFrame:
    z = df.copy()
    z["date"] = z["timestamp"].dt.date
    z["hour"] = z["timestamp"].dt.hour
    z["dow"]  = z["timestamp"].dt.dayofweek  # 0=mon
    z["month"]= z["timestamp"].dt.month
    return z

def _hour_to_shift(h: int) -> str:
    for name, start, end in SHIFT_DEF:
        if start < end:
            if start <= h < end:
                return name
        else:
            # overnight window
            if h >= start or h < end:
                return name
    return "Unknown"

# flow
def flow_daily(flow: pd.DataFrame) -> pd.DataFrame:
    """Daily totals and basic stats."""
    z = _add_time_parts(flow)
    g = z.groupby("date", as_index=False).agg(
        total_consumption=("consumption", "sum"),
        mean_interval=("consumption", "mean"),
        p95_interval=("consumption", lambda s: float(np.nanpercentile(s, 95)) if len(s) else np.nan),
        readings=("consumption", "size"),
    )
    return g.sort_values("date")

def flow_shift_aggregates(flow: pd.DataFrame) -> pd.DataFrame:
    z = _add_time_parts(flow)
    z["shift"] = z["hour"].apply(_hour_to_shift)
    g = z.groupby(["date", "shift"], as_index=False).agg(
        total_consumption=("consumption", "sum"),
        readings=("consumption", "size"),
    )
    return g.sort_values(["date", "shift"])

def flow_heatmap_hour_dow(flow: pd.DataFrame) -> pd.DataFrame:
    """Mean consumption by hour-of-day vs day-of-week (pivot)."""
    z = _add_time_parts(flow)
    heat = z.groupby(["dow","hour"], as_index=False)["consumption"].mean()
    return heat.pivot(index="dow", columns="hour", values="consumption").sort_index()

# quality
def quality_daily_compliance(quality: pd.DataFrame) -> pd.DataFrame:
    """% in safe range per parameter per day (+ basic stats)."""
    q = quality.copy()
    q["in_range"] = (q["value"] >= q["safe_min"]) & (q["value"] <= q["safe_max"])
    q["date"] = q["timestamp"].dt.date
    g = q.groupby(["parameter","date"], as_index=False).agg(
        pct_in_range=("in_range", lambda s: 100.0 * s.mean() if len(s) else np.nan),
        breaches=("in_range", lambda s: int((~s).sum())),
        readings=("in_range","size"),
        avg_value=("value","mean"),
        min_value=("value","min"),
        max_value=("value","max"),
    )
    return g.sort_values(["parameter","date"])

def quality_breach_events(quality: pd.DataFrame) -> pd.DataFrame:
    """Consecutive out-of-range segments per parameter with duration.
    Returns an empty DataFrame with proper columns if there are no breaches.
    """
    q = quality.sort_values(["parameter","timestamp"]).copy()
    q["in_range"] = (q["value"] >= q["safe_min"]) & (q["value"] <= q["safe_max"])

    rows = []
    for param, g in q.groupby("parameter"):
        g = g.reset_index(drop=True)
        run_id = (g["in_range"] != g["in_range"].shift(1)).cumsum()
        for _, seg in g.groupby(run_id):
            if not seg.empty and (seg["in_range"].iloc[0] is False):
                start = seg["timestamp"].iloc[0]
                end   = seg["timestamp"].iloc[-1]
                dur_min = (end - start).total_seconds() / 60.0
                rows.append({
                    "parameter": param,
                    "start": start,
                    "end": end,
                    "duration_min": round(dur_min, 2),
                    "min_value": float(seg["value"].min()),
                    "max_value": float(seg["value"].max()),
                    "readings": int(len(seg)),
                })

    cols = ["parameter","start","end","duration_min","min_value","max_value","readings"]
    if not rows:
        return pd.DataFrame(columns=cols)

    return pd.DataFrame(rows, columns=cols).sort_values(["parameter","start"])

# seasonal and humidity impact
def seasonal_rollups(flow: pd.DataFrame, quality: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Monthly flow totals and monthly %in-range by parameter."""
    f = flow.copy()
    q = quality.copy()

    f["month"] = f["timestamp"].dt.month
    flow_month = f.groupby("month", as_index=False)["consumption"].sum().rename(columns={"consumption":"total_consumption"})

    q["in_range"] = (q["value"] >= q["safe_min"]) & (q["value"] <= q["safe_max"])
    q["month"] = q["timestamp"].dt.month
    qual_month = (q.groupby(["parameter","month"], as_index=False)["in_range"].mean()
                    .rename(columns={"in_range":"mean_in_range"}))
    qual_month["pct_in_range"] = 100.0 * qual_month["mean_in_range"]
    qual_month = qual_month.drop(columns=["mean_in_range"])

    return {"flow_month": flow_month, "quality_month": qual_month}

def humidity_vs_flow_daily(flow: pd.DataFrame, quality: pd.DataFrame, humidity_name: str = "HUMIDITY (HUMIDITY)") -> Tuple[pd.DataFrame, float | None]:
    """Daily total consumption vs daily mean humidity; returns merged df and Pearson corr."""
    # daily flow
    fd = flow_daily(flow).rename(columns={"date":"date_flow"})
    fd["date"] = pd.to_datetime(fd["date_flow"]).dt.date

    # daily humidity
    h = quality[quality["parameter"] == humidity_name].copy()
    if h.empty:
        return pd.DataFrame(columns=["date","total_consumption","humidity"]), None
    h["date"] = h["timestamp"].dt.date
    hd = h.groupby("date", as_index=False)["value"].mean().rename(columns={"value":"humidity"})

    # join on date
    merged = pd.merge(fd[["date","total_consumption"]], hd, on="date", how="inner")
    corr = None
    if len(merged) >= 2 and merged["humidity"].notna().any():
        corr = float(merged["total_consumption"].corr(merged["humidity"]))
    return merged, corr
