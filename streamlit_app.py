import os
from pathlib import Path
import streamlit as st
import pandas as pd
import plotly.express as px

from src.parsers import load_flow_csv, load_quality_csv
from src.analytics import (
    flow_daily, flow_shift_aggregates, flow_heatmap_hour_dow,
    quality_daily_compliance, quality_breach_events,
    seasonal_rollups, humidity_vs_flow_daily
)
from src.ask import ensure_ollama_available, ask_ollama, plan_query
from src.alerts import flow_anomalies, quality_latest_breaches, simple_recommendations  # alerts import

DATA_DIR = Path("data")
TZ = "Asia/Kolkata"

st.set_page_config(page_title="Water Analytics (Prototype)", layout="wide")
st.title("Water Management Analytics — Prototype")

# ollama check
with st.status("Checking Ollama…", expanded=False):
    try:
        info = ensure_ollama_available()
        st.success(f"Ollama OK — {info}")
    except Exception as e:
        st.error(
            "Ollama server not reachable. "
            "Make sure `ollama serve` is running and OLLAMA_URL/OLLAMA_MODEL are set.\n\n"
            f"Details: {e}"
        )
        st.stop()

# load data
flow_path = DATA_DIR / "water_flow_data.csv"
qual_path = DATA_DIR / "water_quality_data.csv"

if not flow_path.exists() or not qual_path.exists():
    st.error("CSV files missing in ./data. Expected water_flow_data.csv and water_quality_data.csv.")
    st.stop()

@st.cache_data(show_spinner=False)
def load_all(flow_p: Path, qual_p: Path):
    flow = load_flow_csv(flow_p)
    qual = load_quality_csv(qual_p)
    return flow, qual

flow_df, quality_df = load_all(flow_path, qual_path)

# tabs
tabs = st.tabs([
    "Overview",
    "Flow Analytics",
    "Quality & Compliance",
    "Seasonal & Weather Impact",
    "Alerts & Recommendations",
    "Ask the Assistant"
])

# overview
with tabs[0]:
    st.subheader("Overview")
    c1, c2, c3, c4 = st.columns(4)

    if not flow_df.empty:
        today = pd.Timestamp.now(tz=TZ).date()
        last7 = pd.Timestamp.now(tz=TZ) - pd.Timedelta(days=7)
        total_today = flow_df[flow_df["timestamp"].dt.date == today]["consumption"].sum()
        total_7 = flow_df[flow_df["timestamp"] >= last7]["consumption"].sum()
        c1.metric("Total Consumption (Today)", f"{total_today:,.2f}")
        c2.metric("Total Consumption (Last 7d)", f"{total_7:,.2f}")

        daily = flow_daily(flow_df)
        fig = px.line(daily, x="date", y="total_consumption", title="Daily Total Consumption")
        st.plotly_chart(fig, use_container_width=True)
        st.download_button(
            "Download daily totals (CSV)",
            data=daily.to_csv(index=False).encode("utf-8"),
            file_name="flow_daily.csv",
            mime="text/csv"
        )

    if not quality_df.empty:
        comp = quality_daily_compliance(quality_df)
        if not comp.empty:
            latest_day = comp["date"].max()
            latest = comp[comp["date"] == latest_day]
            avg_comp = latest["pct_in_range"].mean()
            c3.metric("Avg % In Range (Latest Day)", f"{avg_comp:,.1f}%")
            st.download_button(
                "Download daily compliance (CSV)",
                data=comp.to_csv(index=False).encode("utf-8"),
                file_name="quality_daily_compliance.csv",
                mime="text/csv"
            )

    c4.metric("Timezone", TZ)

# flow analytics
with tabs[1]:
    st.subheader("Flow Analytics")
    if flow_df.empty:
        st.info("No flow data parsed.")
    else:
        daily = flow_daily(flow_df)
        st.plotly_chart(
            px.line(daily, x="date", y="total_consumption", title="Daily Total Consumption"),
            use_container_width=True
        )

        shift = flow_shift_aggregates(flow_df)
        st.plotly_chart(
            px.bar(shift, x="date", y="total_consumption", color="shift", barmode="group",
                   title="Shift-wise Consumption"),
            use_container_width=True
        )

        heat = flow_heatmap_hour_dow(flow_df)  # pivot
        st.write("**Hour × Day-of-Week (mean consumption)**")
        st.dataframe(heat.style.format("{:.2f}"), use_container_width=True)

        # exports
        c1, c2, c3 = st.columns(3)
        c1.download_button(
            "flow_daily.csv",
            data=daily.to_csv(index=False).encode("utf-8"),
            file_name="flow_daily.csv",
            mime="text/csv"
        )
        c2.download_button(
            "flow_shift.csv",
            data=shift.to_csv(index=False).encode("utf-8"),
            file_name="flow_shift.csv",
            mime="text/csv"
        )
        c3.download_button(
            "flow_heatmap_hour_dow.csv",
            data=heat.to_csv().encode("utf-8"),
            file_name="flow_heatmap_hour_dow.csv",
            mime="text/csv"
        )

# quality and compliance
with tabs[2]:
    st.subheader("Quality & Compliance")
    if quality_df.empty:
        st.info("No quality data parsed.")
    else:
        params = sorted(quality_df["parameter"].dropna().unique().tolist())
        param = st.selectbox("Parameter", params, index=0)
        qsel = quality_df[quality_df["parameter"] == param].copy()
        if not qsel.empty:
            st.caption(f"Safe range: {qsel['safe_min'].iloc[0]} to {qsel['safe_max'].iloc[0]}")
            st.plotly_chart(
                px.line(qsel, x="timestamp", y="value", title=f"{param} over time"),
                use_container_width=True
            )

        comp = quality_daily_compliance(quality_df)
        st.plotly_chart(
            px.bar(comp[comp["parameter"] == param], x="date", y="pct_in_range",
                   title=f"{param} — Daily % In Range"),
            use_container_width=True
        )

        breaches = quality_breach_events(quality_df)
        st.write("**Breach Events**")
        st.dataframe(breaches, use_container_width=True, height=260)

        # exports
        c1, c2 = st.columns(2)
        c1.download_button(
            "quality_daily_compliance.csv",
            data=comp.to_csv(index=False).encode("utf-8"),
            file_name="quality_daily_compliance.csv",
            mime="text/csv"
        )
        c2.download_button(
            "quality_breach_events.csv",
            data=breaches.to_csv(index=False).encode("utf-8"),
            file_name="quality_breach_events.csv",
            mime="text/csv"
        )

# seasonal and weather impact
with tabs[3]:
    st.subheader("Seasonal & Weather Impact (Humidity as weather)")
    roll = seasonal_rollups(flow_df, quality_df)
    c1, c2 = st.columns(2)
    if not roll["flow_month"].empty:
        c1.plotly_chart(
            px.bar(roll["flow_month"], x="month", y="total_consumption", title="Monthly Total Consumption"),
            use_container_width=True
        )
    if not roll["quality_month"].empty:
        c2.plotly_chart(
            px.box(quality_df.assign(month=quality_df["timestamp"].dt.month),
                   x="month", y="value", color="parameter", title="Monthly Distribution by Parameter"),
            use_container_width=True
        )

    hum_df, corr = humidity_vs_flow_daily(flow_df, quality_df, "HUMIDITY (HUMIDITY)")
    st.plotly_chart(
        px.scatter(hum_df, x="humidity", y="total_consumption",
                   trendline="ols", title=f"Daily Consumption vs Daily Mean Humidity (corr={corr})"),
        use_container_width=True
    )
    st.download_button(
        "humidity_vs_flow_daily.csv",
        data=hum_df.to_csv(index=False).encode("utf-8"),
        file_name="humidity_vs_flow_daily.csv",
        mime="text/csv"
    )

# alerts and recommendations
with tabs[4]:
    st.subheader("Alerts & Recommendations")

    col1, col2 = st.columns(2)

    # flow anomalies (last 24h)
    with col1:
        st.markdown("**Flow anomalies (last 24h)**")
        an = flow_anomalies(flow_df, window=24)
        if not an.empty:
            end = an["timestamp"].max()
            start = end - pd.Timedelta(hours=24)
            recent = an[(an["timestamp"] >= start) & (an["timestamp"] <= end)]
            flagged = recent[recent["anomaly"]][["timestamp", "consumption", "threshold"]]
            if not flagged.empty:
                st.dataframe(flagged, use_container_width=True, height=260)
            else:
                st.success("No anomalies flagged in the last 24 hours.")
            st.download_button(
                "flow_anomalies_24h.csv",
                data=recent.to_csv(index=False).encode("utf-8"),
                file_name="flow_anomalies_24h.csv",
                mime="text/csv"
            )
        else:
            st.info("No flow data or anomalies computed.")

    # quality breaches (last 24h) and tips
    with col2:
        st.markdown("**Quality breaches (last 24h)**")
        breaches_24h = quality_latest_breaches(quality_df)
        if not breaches_24h.empty:
            st.dataframe(breaches_24h, use_container_width=True, height=260)
            st.download_button(
                "quality_breaches_24h.csv",
                data=breaches_24h.to_csv(index=False).encode("utf-8"),
                file_name="quality_breaches_24h.csv",
                mime="text/csv"
            )
        else:
            st.success("No quality breaches in the last 24 hours.")

    st.markdown("**Recommended actions**")
    recs = simple_recommendations(breaches_24h if 'breaches_24h' in locals() else pd.DataFrame())
    for r in recs:
        st.write("- " + r)

# ask the assistant (ollama required)
with tabs[5]:  # note: adjust index if the tab list changes
    st.subheader("Ask the Assistant")
    st.caption("Ask for charts or tables directly, for example: 'shift-wise consumption yesterday', "
               "'TDS compliance last 7 days', 'humidity impact this month'.")
    q = st.text_input("Your question", "")

    def _apply_lookback(df, days: int):
        if df.empty or not isinstance(days, int) or days <= 0:
            return df
        end = df["timestamp"].max()
        start = end - pd.Timedelta(days=days)
        return df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].copy()

    if st.button("Ask") and q.strip():
        try:
            with st.spinner("Planning…"):
                plan = plan_query(q.strip())
            st.caption("Plan:")
            st.code(plan, language="json")

            action = plan.get("action", "none")
            params = plan.get("params", {}) or {}
            lookback = params.get("range_days")
            param_name = params.get("parameter")
            min_dur = params.get("min_duration_min")

            # filtered views if lookback requested
            fdf = _apply_lookback(flow_df, lookback) if lookback else flow_df
            qdf = _apply_lookback(quality_df, lookback) if lookback else quality_df

            if action == "flow_shift":
                data = flow_shift_aggregates(fdf)
                st.plotly_chart(
                    px.bar(data, x="date", y="total_consumption", color="shift", barmode="group",
                           title="Shift-wise Consumption"),
                    use_container_width=True
                )
                st.dataframe(data.tail(60), use_container_width=True, height=280)
                st.download_button(
                    "ask_flow_shift.csv",
                    data=data.to_csv(index=False).encode("utf-8"),
                    file_name="ask_flow_shift.csv",
                    mime="text/csv"
                )

            elif action == "flow_daily":
                data = flow_daily(fdf)
                st.plotly_chart(
                    px.line(data, x="date", y="total_consumption", title="Daily Total Consumption"),
                    use_container_width=True
                )
                st.dataframe(data.tail(60), use_container_width=True, height=280)
                st.download_button(
                    "ask_flow_daily.csv",
                    data=data.to_csv(index=False).encode("utf-8"),
                    file_name="ask_flow_daily.csv",
                    mime="text/csv"
                )

            elif action == "quality_compliance":
                # default parameter if missing
                if not param_name:
                    params_list = sorted(qdf["parameter"].dropna().unique().tolist())
                    param_name = params_list[0] if params_list else None
                if not param_name:
                    st.warning("No parameters found in data.")
                else:
                    comp = quality_daily_compliance(qdf)
                    data = comp[comp["parameter"] == param_name]
                    st.plotly_chart(
                        px.bar(data, x="date", y="pct_in_range", title=f"{param_name} — Daily % In Range"),
                        use_container_width=True
                    )
                    st.dataframe(data.tail(60), use_container_width=True, height=280)
                    st.download_button(
                        f"ask_compliance_{param_name}.csv",
                        data=data.to_csv(index=False).encode("utf-8"),
                        file_name=f"ask_compliance_{param_name}.csv",
                        mime="text/csv"
                    )

            elif action == "breach_events":
                data = quality_breach_events(qdf)
                if param_name:
                    data = data[data["parameter"] == param_name]
                if isinstance(min_dur, (int, float)) and not data.empty:
                    data = data[data["duration_min"] >= float(min_dur)]
                st.dataframe(data, use_container_width=True, height=360)
                st.download_button(
                    f"ask_breaches_{param_name or 'all'}.csv",
                    data=data.to_csv(index=False).encode("utf-8"),
                    file_name=f"ask_breaches_{param_name or 'all'}.csv",
                    mime="text/csv"
                )

            elif action == "humidity_vs_flow":
                hvf, corr = humidity_vs_flow_daily(fdf, qdf, "HUMIDITY (HUMIDITY)")
                corr_txt = "None" if corr is None else f"{corr:.3f}"
                st.plotly_chart(
                    px.scatter(hvf, x="humidity", y="total_consumption",
                               trendline="ols", title=f"Daily Consumption vs Daily Mean Humidity (corr={corr_txt})"),
                    use_container_width=True
                )
                st.dataframe(hvf, use_container_width=True, height=280)
                st.download_button(
                    "ask_humidity_vs_flow.csv",
                    data=hvf.to_csv(index=False).encode("utf-8"),
                    file_name="ask_humidity_vs_flow.csv",
                    mime="text/csv"
                )

            else:
                # fallback to text answer
                answer = ask_ollama(q.strip())
                st.write(answer)

        except Exception as e:
            st.error(f"Failed to run LLM-driven analytics. Details: {e}")
