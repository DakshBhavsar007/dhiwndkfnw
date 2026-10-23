# Wind-Power Forecast Monitoring Web App

Take-home "Full Stack SWE challenge": a wind-power forecast monitoring web app for a UK energy utility's day-ahead electricity buying team.

## Domain
The team buys power on the UK day-ahead market and must decide on day D-1 (before the auction gate closure) how much non-wind power to procure for delivery day D. They need:
1. The latest wind forecast available AT DECISION TIME.
2. Quantified forecast accuracy.

## Data (Elexon BMRS only, national WIND only)
- **Actuals**: `FUELHH` stream, `fuelType=WIND`. Fields: `startTime` (30-min), `generation` (MW).
- **Forecasts**: `WINDFOR` stream. Fields: `startTime`, `publishTime`, `generation` (MW).
- **Scope**: Decisions made in January 2026 only (delivery days 1 Jan to 31 Jan 2026; fetch a few days of buffer on both sides if needed).
- Verify exact endpoint params and response shapes from the Elexon API docs by actually calling the API; do not guess.

## Core Logic Rule
- For a given delivery day D and decision cutoff (default 09:00 Europe/London on D-1, configurable), for each 30-min `startTime` use the forecast row with the **LATEST `publishTime` <= cutoff**.
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
