# step3_run_analytics.py
from pathlib import Path
from src.parsers import load_flow_csv, load_quality_csv
from src.analytics import (
    flow_daily, flow_shift_aggregates, flow_heatmap_hour_dow,
    quality_daily_compliance, quality_breach_events,
    seasonal_rollups, humidity_vs_flow_daily
)

DATA_DIR = Path("data")
ART = Path("artifacts"); ART.mkdir(exist_ok=True)

flow = load_flow_csv(DATA_DIR / "water_flow_data.csv")
qual = load_quality_csv(DATA_DIR / "water_quality_data.csv")

# flow
daily = flow_daily(flow)
shift = flow_shift_aggregates(flow)
heat  = flow_heatmap_hour_dow(flow)

daily.to_csv(ART / "flow_daily.csv", index=False)
shift.to_csv(ART / "flow_shift.csv", index=False)
heat.to_csv(ART / "flow_heatmap_hour_dow.csv")

# quality
comp  = quality_daily_compliance(qual)
breach= quality_breach_events(qual)

comp.to_csv(ART / "quality_daily_compliance.csv", index=False)
breach.to_csv(ART / "quality_breach_events.csv", index=False)

# seasonal
roll = seasonal_rollups(flow, qual)
roll["flow_month"].to_csv(ART / "seasonal_flow_month.csv", index=False)
roll["quality_month"].to_csv(ART / "seasonal_quality_month.csv", index=False)

# weather impact via humidity
hum_df, corr = humidity_vs_flow_daily(flow, qual, humidity_name="HUMIDITY (HUMIDITY)")
hum_df.to_csv(ART / "humidity_vs_flow_daily.csv", index=False)

print("Saved artifacts to:", ART.resolve())
print("Files:")
for p in ART.iterdir():
    print(" -", p.name)

print("\nCorrelation (daily total consumption vs daily mean humidity):", corr)
