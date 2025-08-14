# WATER MANAGEMENT ENGINE - PROTOTYPE

# CODE ARCHITECTURE AND FLOW

## TOOLS AND LIBRARIES USED
- **Python** 3.11
- **Streamlit** (web UI)
- **Pandas**, **NumPy** (data processing)
- **Plotly Express** (charts)
- **statsmodels** (used by Plotly for OLS trendlines)
- **requests** (HTTP calls)
- **python-dateutil** (time handling)
- **Ollama** (local LLM runtime), model: `llama3.1` (or compatible)

### Environment variables
- `OLLAMA_MODEL` (e.g., `llama3.1`)
- `OLLAMA_URL` (e.g., `http://127.0.0.1:11435/api/chat` for me)

### Assumptions
- Timezone: `Asia/Kolkata`
- Flow readings at 5-minute intervals
- Shifts: A = 06:00–14:00, B = 14:00–22:00, C = 22:00–06:00
- “Weather impact” is proxied by **HUMIDITY** from the quality CSV (no external weather API taken into consideration as of now)

------

## MODULE RESPONSIBILITIES

### `src/parsers.py`
- **`load_flow_csv(path)`**
  - Reads repeating header blocks (`Date | Time | Totalizer`).
  - Builds timezone-aware `timestamp`.
  - Converts `totalizer` to numeric and computes `consumption = totalizer.diff()`.
  - Negative diffs (counter resets) are set to 0.
  - Output: `timestamp`, `totalizer`, `consumption`.

- **`load_quality_csv(path)`**
  - Parses parameter sections like `1. NAME (CODE), Safe Range: (a to b)` followed by a `Date | Time | Value` table.
  - Extracts `safe_min`, `safe_max`.
  - Output: `timestamp`, `parameter`, `value`, `safe_min`, `safe_max`.

### `src/analytics.py`
- **Flow**
  - `flow_daily(df)`: daily totals and basic stats.
  - `flow_shift_aggregates(df)`: aggregates by shifts (A/B/C).
  - `flow_heatmap_hour_dow(df)`: mean consumption by hour × day-of-week (pivot).

- **Quality**
  - `quality_daily_compliance(df)`: percent of readings within safe range per parameter/day; includes value stats.
  - `quality_breach_events(df)`: consecutive out-of-range segments with start, end, duration, min/max; returns an empty table with headers if none.

- **Seasonal / Humidity**
  - `seasonal_rollups(flow, quality)`: monthly flow totals and monthly % in range per parameter.
  - `humidity_vs_flow_daily(flow, quality, humidity_name)`: daily consumption vs daily mean humidity, plus Pearson correlation.

### `src/alerts.py`
- `flow_anomalies(flow, window=24)`: rolling median + MAD to flag spikes in `consumption`.
- `quality_latest_breaches(quality)`: last 24 hours of out-of-range readings by parameter.
- `simple_recommendations(breaches_df)`: rule-of-thumb actions based on which parameters breached.

### `src/ask.py`
- `ensure_ollama_available()`: checks `/api/version` and fails fast if unreachable.
- `ask_ollama(prompt, system=None)`: plain Q&A call with `stream: false`.
- `plan_query(query)`: prompts the model to return **only** a compact JSON plan:
  ```json
  {
    "action": "flow_shift|flow_daily|quality_compliance|breach_events|humidity_vs_flow|none",
    "params": {
      "parameter": "string (optional)",
      "range_days": 7,
      "min_duration_min": 30
    }
  }


  -------------------------
## CONTROL FLOW (END TO END)

1. **Startup**
   - `streamlit_app.py` checks that `data/water_flow_data.csv` and `data/water_quality_data.csv` exist.
   - Calls `ensure_ollama_available()`; if the Ollama API is not reachable, the app exits early with a clear message.

2. **Data Load (cached)**
   - `load_flow_csv()` and `load_quality_csv()` parse the CSVs into tidy, timezone-aware DataFrames.
   - Results are memoized with `@st.cache_data` so re-renders don’t re-parse.

3. **Analytics Computation**
   - Flow: `flow_daily`, `flow_shift_aggregates`, `flow_heatmap_hour_dow`.
   - Quality: `quality_daily_compliance`, `quality_breach_events`.
   - Seasonal & humidity: `seasonal_rollups`, `humidity_vs_flow_daily` (including correlation).

4. **Alerts**
   - `flow_anomalies` computes spike flags using rolling median + MAD.
   - `quality_latest_breaches` extracts the most recent 24 hours of out-of-range readings.
   - `simple_recommendations` translates breached parameters into quick action tips.

5. **UI Rendering (Tabs)**
   - **Overview**: KPIs, daily totals chart, CSV export.
   - **Flow Analytics**: daily/shift/heatmap visuals, CSV exports.
   - **Quality & Compliance**: parameter trends, % in range, breach table, CSV exports.
   - **Seasonal & Weather Impact**: monthly rollups, humidity vs consumption (OLS trendline), CSV export.
   - **Alerts & Recommendations**: anomalies, last-24h breaches, recommendations, CSV exports.
   - **Ask the Assistant**: natural-language query → `plan_query()` returns a JSON plan → the app routes to the requested analytic and displays the matching chart/table with a CSV export. Falls back to `ask_ollama` text if no structured action applies.

---
## BASIC WORKFLOW (RUNTIME)

```mermaid
flowchart TD
  A[Start app] --> B[Check CSV files in data]
  B --> C[Ollama health check]
  C --> D[Parse data with parsers]
  D --> E[Run analytics]
  E --> F[Derive alerts]
  F --> G[Render Streamlit tabs]
  G --> H[Provide CSV downloads]
  G --> I[Ask tab routes to analytics via planner]
  I --> J[Finish]

````

## DATA FLOW SUMMARY

- Raw CSVs → `src/parsers.py` → tidy DataFrames (`flow_df`, `quality_df`) with tz-aware timestamps  
- `flow_df`, `quality_df` → `src/analytics.py` → daily/shift/heatmap/compliance/breaches/rollups/humidity-correlation tables  
- `flow_df`, `quality_df` → `src/alerts.py` → anomalies and last-24h breaches (+ recommendations)  
- Streamlit UI → renders charts/tables and exposes CSV downloads  
- Ask tab → user question → `plan_query()` → routed analytic → chart/table + CSV (or plain text via `ask_ollama`)

---

## EDGE CASES HANDLED

- **Repeating headers in flow CSVs**  
  The parser detects each header block and concatenates sections safely.

- **Counter resets / negative diffs**  
  When `totalizer.diff()` is negative, that interval’s `consumption` is set to 0 to avoid false spikes.

- **Empty breach results**  
  `quality_breach_events()` returns an empty DataFrame with the correct columns when there are no breaches, preventing sort/index errors.

- **LLM streaming vs single JSON**  
  All Ollama calls set `"stream": false` to avoid partial NDJSON; responses are parsed as a single JSON.

- **Planner output sanitation**  
  `plan_query()` extracts and validates the first JSON object found, supplies defaults, and falls back to a safe `"none"` action if parsing fails.

- **Timezone consistency**  
  All timestamps are localized to `Asia/Kolkata` to keep charts and aggregates aligned.


### SETUP AND INSTALLATION

## PREREQUISITES
- Python 3.11+
- Git
- Ollama installed locally with a model (e.g., `llama3.1`); install with Microsoft Store or `winget install Ollama.Ollama`
- Two CSV files in `data/`:
  - `water_flow_data.csv`
  - `water_quality_data.csv`

## CLONE THE REPOSITORY
  ```powershell
    git clone https://github.com/<your-username>/<your-repo>.git
    cd <your-repo>
  ```
## CREATE AND ACTIVATE A VIRTUAL ENVIRONMENT
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
```
## 3) INSTALL PYTHON DEPENDENCIES
```powershell
pip install -r requirements.txt
```
## 4) PREPARE DATA
Ensure the CSVs are present

## 5) START OLLAMA AND PULL A MODEL
Open a second PowerShell window (leave it running):
```powershell
ollama pull llama3.1
ollama serve
```
## 6) SET APP ENVIRONMENT VARIABLES
```powershell
$env:OLLAMA_MODEL = "llama3.1"
$env:OLLAMA_URL = "http://127.0.0.1:11435/api/chat"
```
## 7)  Check If API is Reachable
```powershell
Invoke-WebRequest http://127.0.0.1:11435/api/version | Select-Object -Expand Content
```
## 8) LLM Check
```powershell
python .\test_ollama.py
```
## 9) Run
```powershell
streamlit run .\streamlit_app.py
```

## FEATURES — IMPLEMENTED VS PLANNED

### Implemented
- **Data processing engine**  
  Robust CSV parsers for flow and quality; timezone-aware timestamps; consumption derived from totalizer diffs with reset handling.
- **Time/shift analytics**  
  Daily totals, shift-wise aggregates (06–14, 14–22, 22–06), hour × day-of-week heatmap.
- **Seasonal & weather impact (via humidity)**  
  Monthly rollups and humidity - flow correlation (humidity sourced from the quality CSV).
- **Regulatory compliance**  
  Daily percent-in-range by parameter; breach event detection with start/end/duration and extrema.
- **Alerts & recommendations**  
  Flow anomalies via rolling median + MAD; last-24h quality breaches; concise, rule-of-thumb actions.
- **AI-powered query (on-demand visuals)**  
  “Ask” tab uses a JSON plan from the LLM to render the requested chart/table and offer CSV downloads; fallback to text when needed.
- **Operational safeguards**  
  Mandatory Ollama health check on startup with clear error messages.
- **Exports**  
  CSV downloads for key tables across tabs.

### Planned / Not Implemented Yet
- **Retrieval-augmented grounding (RAG)**  
  Beneficial delivery with more time; can be considered as a second step and a clear scope for improvement.
- **External weather API integration**  
  No city context and added complexity; instead, humidity from our dataset was used as the weather proxy.
- **Multi-station support, authentication, and database persistence**  
  Complex; can be considered in the next or end steps.
- **Global date-range filter (with Reset)**  
  Implemented experimentally but didn’t pass my tests; can be integrated after polishing.
- **Packaged installer / executable**  
  Implemented experimentally but couldn’t complete within the timeframe.
- **Alert tuning controls (UI sliders for window/MAD/min-duration)**  
  Focused on landing the alerting first; can be added as an improvement later.
- **Alerting is rule-based**
  Anomalies use rolling median + MAD; no advanced ML or seasonality-aware detection - can perform better with SARIMA or other techniques; requires more time and understanding of the dataset for better functionality
- **Expanded Ask-tab toolset and better summaries**  
  Once RAG is introduced, we can make this part better (more grounded actions and concise bullet summaries).

## KNOWN LIMITATIONS

- **CSV-only ingestion**  
  Reads from two local CSVs - no database, API, or streaming input.

- **Single-station, single-timezone**  
  Assumes one site and `Asia/Kolkata`; no multi-station rollups or timezone switching.

- **Schema assumptions**  
  Flow CSV expects repeating headers and a `Totalizer`; quality CSV expects “Safe Range: (a to b)” format.

- **No persistent storage**  
  Derived tables/alerts aren’t saved; exports are manual CSV downloads.

- **Alerting is rule-based**  
  Anomalies use rolling median + MAD; no advanced ML or seasonality-aware detection.

- **LLM planner is minimal**  
  Limited set of actions; no retrieval grounding (answers rely on the prompt and current data only).

- **No notifications**  
  Alerts are in-app only.

- **No access control**  
  No user auth, roles, or audit logs.

- **Operational dependency on Ollama**  
  Requires a local Ollama server and model; no cloud fallback.

- **Testing and CI are basic**  
  Manual testing; no unit test suite or automated pipeline.

---

## FUTURE IMPROVEMENTS

- **Add RAG grounding**  
  Index glossary, SOPs, and compliance rules to make LLM answers consistently grounded.

- **Richer LLM toolset**  
  More actions (peak detection, parameter comparisons, export-all, top-N anomalies) and structured summaries.

- **External weather integration**  
  Pull temperature, rainfall, humidity from an API; correlate with demand and quality.

- **Configurable alert controls**  
  UI sliders for anomaly window/MAD factor and minimum breach duration; parameter-specific thresholds.

- **Global date filters**  
  Re-introduce a polished date-range filter with a safe reset and clear UX.

- **Multi-station and persistence**  
  Store data and results in a DB (SQLite/Postgres), add station dimension, and enable historical replays.

- **Notifications and schedules**  
  Alerts and scheduled daily/weekly reports.

- **Packaging & deployment**  
  Dockerfile, CI/CD, optional Windows installer; environment templates.

- **Data quality checks**  
  Validations for missing timestamps, outliers, unit mismatches; ingest logs.

- **Access control**  
  Authentication, roles (viewer/operator/admin), and audit trails.

- **Advanced analytics**  
  Seasonality decomposition, changepoint detection, forecast of consumption/quality with confidence bands.














