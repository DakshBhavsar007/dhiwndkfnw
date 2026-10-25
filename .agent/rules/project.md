---
trigger: always_on
---

# Wind-Power Forecast Monitoring Web App

Take-home "Full Stack SWE challenge": a wind-power forecast monitoring web app for a UK energy utility's day-ahead electricity buying team.

## Domain
The team buys power on the UK day-ahead market and must decide on day D-1 (before the auction gate closure) how much non-wind power to procure for delivery day D. They need:
1. The latest wind forecast available AT DECISION TIME.
2. Quantified forecast accuracy.

## Data (Elexon BMRS only, national WIND only)
- **Actuals**: `FUELHH` stream, `fuelType=WIND`. Half-hourly resolution (30-min settlement periods starting at `:00` and `:30`, 48 periods/day). Fields: `startTime` (UTC), `generation` (MW).
- **Forecasts**: `WINDFOR` stream. Hourly resolution (minute distribution: 100% of rows have `startTime` minute `:00`, 0 rows at `:30`). Exactly 73 hourly rows per publish run, i.e. a 72-hour window per run. The window position relative to `publishTime` varies by run: the first slot is 5.5 to 25.5 hours before `publishTime`, and the last slot is 46.5 to 66.5 hours after it. Fields: `startTime` (UTC), `publishTime` (UTC), `generation` (MW).
- **Ingestion Window**: 2025-12-28 to 2026-02-03 inclusive = **38 days** (4 days in Dec 2025 + 31 days in Jan 2026 + 3 days in Feb 2026).
- **Scope**: Decisions made in January 2026 (2026-01-01 to 2026-01-31 inclusive). Since decisions made on D-1 are for delivery on D, the delivery days are **2026-01-02 to 2026-02-01** (31 delivery days).
- **Generation Metric**: National wind power in MW. Elexon's API docs do not state the exact scope of FUELHH WIND vs WINDFOR (e.g. whether both cover the same set of wind farms) nor whether forecast `generation` is an hourly average or instantaneous MW. Treated as hourly average MW (assumption). A persistent forecast-above-actual offset (~+1.7 GW) is observed; its cause is not verified.

## Resolution Alignment: Option A
- **Forecast / Evaluation Alignment**: `WINDFOR` forecasts have 24 hourly slots per delivery day (00:00 to 23:00 UTC), not 48 periods. For metric calculations and tabular joins, aggregate `FUELHH` actuals to hourly by taking the arithmetic mean of the two 30-minute settlement periods in each hour (`HH:00` and `HH:30`). Join with forecast on the hourly `startTime`.
- **Chart / Visualization**: Keep raw 30-min actuals from `FUELHH` and render the hourly forecast as a step line spanning each hourly slot $[HH:00, (HH+1):00)$.

## Core Logic Rule
- For a given delivery day D and decision cutoff (default 09:00 Europe/London on D-1, configurable), for each of the 24 hourly `startTime` slots use the forecast row with the **LATEST `publishTime` <= cutoff**.
- **Never use forecasts published after the cutoff** (strictly no future leakage).
- Handle UTC vs Europe/London and DST correctly.

## Stack & Architecture
- **Backend**: Python 3.12 + FastAPI + pandas/numpy.
- **Frontend**: React + TypeScript + Vite (Recharts or Plotly).
- **Containerization**: Docker + docker-compose.
- **CI/CD & Deployment**: GitHub Actions CI; deploy on Vercel.

## Development Rules & Guidelines
- Typed code, small modular architecture.
- Unit tests: `pytest` for all core backend logic, `vitest` for key frontend logic.
- Structured logging.
- `/health` endpoint.
- No secrets in repo.
- Deployed app must **NOT** depend on live Elexon calls (use committed data snapshot).
- Document every assumption in `README.md`.
- Keep it simple, avoid over-engineering, total scope ~16 hours.
- Before big changes, show a plan.
- After each task, run tests and report results.