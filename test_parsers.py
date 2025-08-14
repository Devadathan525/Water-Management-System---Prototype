from pathlib import Path
from src.parsers import load_flow_csv, load_quality_csv

flow_path = Path("data/water_flow_data.csv")
qual_path = Path("data/water_quality_data.csv")

flow = load_flow_csv(flow_path)
qual = load_quality_csv(qual_path)

print("FLOW ===")
print(flow.head(8))
print("rows:", len(flow), "time_range:", flow["timestamp"].min(), "→", flow["timestamp"].max())
print("consumption_sum:", float(flow["consumption"].sum()))

print("\nQUALITY ===")
print(qual.head(8))
print("rows:", len(qual), "params:", sorted(qual["parameter"].unique().tolist()))
print("time_range:", qual["timestamp"].min(), "→", qual["timestamp"].max())
