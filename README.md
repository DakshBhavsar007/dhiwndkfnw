# UK Day-Ahead Wind-Power Forecast Monitoring

[![CI](https://github.com/DakshBhavsar007/dhiwndkfnw/actions/workflows/ci.yml/badge.svg)](https://github.com/DakshBhavsar007/dhiwndkfnw/actions/workflows/ci.yml)

## 1. Overview
This web application supports a UK energy utility's day-ahead electricity trading desk. When deciding on day D-1 how much non-wind power to procure for delivery day D, traders need to know the latest wind forecast available at decision time and have quantified forecast accuracy to manage shortfall risk. Scope covers national GB wind generation only, using public Elexon BMRS streams (`FUELHH` actuals and `WINDFOR` forecasts) for trading decisions made in January 2026 (delivery days 2026-01-02 to 2026-02-01 inclusive).

## 2. Live Demo
- Frontend Application: https://dhiwndkfnw-q7lf.vercel.app/
- Backend API: https://dhiwndkfnw.vercel.app/
- Service Health: https://dhiwndkfnw.vercel.app/health
- Interactive API Documentation: https://dhiwndkfnw.vercel.app/docs

## 3. AI Tools
Built with AI assistance (Antigravity agents, Claude models). Project rules and prompts are in `.agent/rules/project.md`. I reviewed the design, assumptions and tests myself.

## 4. Key Results
Numbers below apply to the 31-day operational delivery window (2026-01-02 to 2026-02-01, 744 hourly evaluation slots) evaluated at the default 09:00 Europe/London cutoff on D-1:
- Headline metrics (full window): MAE = 2,038.9 MW, RMSE = 2,504.8 MW, Mean Bias = +1,747.9 MW (forecasts consistently exceeded actuals), MAPE = 22.0%.
- Rolling leakage-free backtest (days <= D-2): Mean daily MAE of raw forecast was 2,038.9 MW vs. 1,504.4 MW for the bias-adjusted forecast (-534.5 MW / -26.2% error reduction).
- Bias adjustment performance: Bias-adjusted forecast beat raw forecast on 22 of 31 days (71.0%).
- Shortfall buffer reliability: Out of 744 hourly slots, the buffer was breached in 98 slots (13.17% breach rate vs. the 10.0% P90 tail risk target).

## 5. How It Works
- Cutoff rule: For delivery day D and decision cutoff (default 09:00 Europe/London on D-1), for each of the 24 hourly slots, the system selects the forecast row with the latest publishTime <= cutoff. Cutoff times are converted between Europe/London and UTC to guarantee zero future leakage.
- Resolution alignment (Option A): `WINDFOR` forecasts have 24 hourly slots per delivery day (00:00 to 23:00 UTC). `FUELHH` 30-minute actuals are aggregated to hourly by arithmetic mean for tabular joins and metric evaluations, while raw 30-minute actuals are preserved as line points on the visualization.
- Error and shortfall buffer definitions: Signed error is defined as `error = forecast - actual` (positive indicates over-forecasting, negative indicates under-forecasting). Shortfall buffer is defined as the 90th percentile (P90) of historical errors, floored at 0 MW.
- Leakage rule for history: Historical error statistics and buffers for day D are computed strictly from completed delivery days <= D-2 (prior-day outturn is not yet known at morning gate closure). Buffer days from 2025-12-28 are used solely to establish baseline history.

## 6. Project Structure
- `backend/app/`: FastAPI application, endpoints, Pydantic schemas, and middleware.
- `backend/app/core/`: Pure calculation logic (hourly actuals aggregation, cutoff forecast selection, metrics, decision summary).
- `backend/scripts/`: Snapshot fetch and compression utility (`fetch_data.py`).
- `backend/data/`: Committed snapshot datasets (`actuals.parquet`, `forecasts.parquet`, and `.csv.gz` compressed fallbacks).
- `backend/tests/`: Pytest suite covering aggregation, cutoff selection, leakage protection, metrics, and API endpoints.
- `backend/vercel.json`: Vercel serverless Python runtime build and routing configuration.
- `frontend/src/`: Vite React TypeScript application (components, API client, charts, KPI cards).
- `frontend/vercel.json`: Vercel SPA routing rewrite configuration.
- `docs/`: Comprehensive data notes and technical analysis (`docs/DATA_NOTES.md`).
- `.github/workflows/`: CI automation workflow running linting, unit tests, and Docker container builds.
- `.agent/`: Agentic workflow instructions and evaluation criteria (`.agent/rules/project.md`).
- `docker-compose.yml`: Multi-container orchestration for backend and frontend services.

## 7. How to Run

### a. With Docker
```bash
docker compose up --build
```
- Frontend: http://localhost:8080
- Backend: http://localhost:8000
- Stop containers: `docker compose down`

### b. Without Docker
1. Backend:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate | Unix: source .venv/bin/activate
pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8000
```
2. Frontend:
```bash
cd frontend
npm ci
npm run dev
```
Access frontend at http://localhost:5173 (points to http://localhost:8000 via proxy or `VITE_API_BASE_URL`).

### c. Tests & Data Refresh
- Run backend tests: `python -m pytest -q`
- Run frontend tests: `cd frontend && npm test`
- Refresh snapshot data: `python backend/scripts/fetch_data.py` (not needed for normal execution; snapshots are committed).

## 8. Assumptions
- Default cutoff 09:00 Europe/London on D-1: Chosen to sit safely before the earliest GB day-ahead gate closures (EPEX 60-minute auction at ~09:20, N2EX at ~09:50; sources: Modo Energy explainer on GB wholesale markets; Nord Pool support page on GB day-ahead auction). Timings may vary by exchange and should be verified directly. Cutoff is configurable in the UI.
- Forecast and actual resolution: `WINDFOR` is hourly (73 rows per publish run, 72-hour window); `FUELHH` is half-hourly. Actuals are averaged to hourly for metrics; raw 30-minute actuals are displayed on charts.
- Generation metric definition: Forecast `generation` is treated as hourly average MW. Elexon documentation does not explicitly state whether it is hourly average or instantaneous MW, nor does it define the exact boundary match between `FUELHH` and `WINDFOR` wind farm metering.
- Observed +1.7 GW offset: A persistent forecast-above-actual offset of approximately +1.7 GW is observed across hours and horizons; its underlying operational cause is not verified.
- Offline snapshot reliance: The deployed application never calls Elexon at runtime, relying strictly on committed snapshot files (Parquet with gzip CSV fallback).

## 9. Limitations and Future Work
- Limited window: Only one calendar month of operational decisions was evaluated (January 2026); seasonal summer/winter variations remain unassessed.
- Pooled vs. per-hour error bands: Historical error quantiles are currently pooled across all 24 hours rather than segmented by hour of day or horizon bucket.
- Buffer breach rate: The observed 13.17% breach rate exceeded the 10.0% theoretical target, reflecting fat-tailed negative ramp events.
- Bias adjustment limits: Rolling median bias adjustment beat raw forecasts on 71% of days but underperformed on 29% of days during positive ramp events. Reasons for raw outperformance were not individually analysed, and persistence is not guaranteed.
- Absence of demand data: Without national demand and market price streams, net procurement volume and financial imbalance exposure cannot be calculated.
- Next steps: Incorporate intraday forecast runs post-gate closure, per-hour quantile regression error bands, and plant-level availability signals.

## 10. CI / CD Pipeline
The GitHub Actions CI pipeline runs on every push and pull request to `main` across three automated jobs:
1. Backend Matrix: Runs linting (`ruff check backend`), type checks (`mypy`), and the full `pytest` suite across Python 3.12 and 3.13 (`fail-fast: false`).
2. Frontend: Runs code quality checks (`oxlint`), component tests (`vitest`), and static production build verification (`tsc` + `vite build`).
3. Docker Container Build: Verifies that both container images build cleanly via `docker compose build`.
