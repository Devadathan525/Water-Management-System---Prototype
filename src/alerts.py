# src/alerts.py
from __future__ import annotations
import pandas as pd
import numpy as np

def flow_anomalies(flow: pd.DataFrame, window: int = 24) -> pd.DataFrame:
    """
    flag spikes using rolling median + mad; window is number of readings (5-min each; 24 ≈ 2 hours)
    """
    z = flow.sort_values("timestamp").copy()
    z["roll_med"] = z["consumption"].rolling(window, min_periods=max(6, window//4)).median()
    mad = (z["consumption"] - z["roll_med"]).abs().rolling(window, min_periods=max(6, window//4)).median()
    z["threshold"] = z["roll_med"] + 3.0 * mad.replace(0, np.nan)
    z["anomaly"] = z["consumption"] > z["threshold"]
    return z[["timestamp","consumption","roll_med","threshold","anomaly"]]

def quality_latest_breaches(quality: pd.DataFrame) -> pd.DataFrame:
    """
    latest out-of-range readings per parameter (last 24h)
    """
    if quality.empty:
        return quality.copy()
    end = quality["timestamp"].max()
    start = end - pd.Timedelta(hours=24)
    q = quality[(quality["timestamp"] >= start) & (quality["timestamp"] <= end)].copy()
    q["in_range"] = (q["value"] >= q["safe_min"]) & (q["value"] <= q["safe_max"])
    breaches = q[~q["in_range"]].sort_values(["parameter","timestamp"])
    return breaches[["timestamp","parameter","value","safe_min","safe_max"]]

def simple_recommendations(quality_breaches: pd.DataFrame) -> list[str]:
    """
    rule-of-thumb text recommendations by parameter
    """
    tips = []
    if quality_breaches.empty:
        return ["All parameters within safe ranges in the last 24h."]
    params = set(quality_breaches["parameter"].unique())
    if any("TDS" in p for p in params):
        tips.append("High TDS detected → check RO/softener status, resin condition, and source blend.")
    if any("(pH" in p or "pH)" in p or p.endswith("(pH)") for p in params):
        tips.append("pH out of range → verify dosing pumps (alkali/acid), probe calibration, and tank mixing.")
    if any("TSS" in p or "Turb" in p for p in params):
        tips.append("Suspended solids/turbidity ↑ → inspect filters/backwash cycles and upstream settling.")
    if any("BOD" in p or "COD" in p for p in params):
        tips.append("BOD/COD breaches → check biological treatment load, aeration, and recycle ratios.")
    if any("HUMIDITY" in p for p in params):
        tips.append("Humidity spikes → consider ventilation/conditioning; correlate with usage peaks.")
    return tips
