# Data Notes: Elexon BMRS Datasets (FUELHH & WINDFOR)

This document describes the datasets fetched, cleaned, and snapshotted for the January 2026 decision scope (with buffer) for the UK day-ahead wind power forecast monitoring web app.

---

## 1. Overview & Data Sources

The data is sourced directly from the **Elexon BMRS Insights Solution REST API** (`https://data.elexon.co.uk/bmrs/api/v1`). No API keys or authentication are required for public access.

| Dataset | Stream Endpoint | Primary Filter / Query Params | Resolution / Granularity | Target Role in App |
| :--- | :--- | :--- | :--- | :--- |
| **Actuals** | `/datasets/FUELHH/stream` | `fuelType=WIND`, `settlementDateFrom`, `settlementDateTo` | **Half-hourly** (30-min settlement periods starting at `:00` and `:30`) | Ground-truth outturn generation (MW) |
| **Forecasts** | `/datasets/WINDFOR/stream` | `publishDateTimeFrom`, `publishDateTimeTo` | **Hourly** (starts at `:00`, rolling publish runs ~every 2–4 hours) | Day-ahead forecasted generation (MW) |

### Ingestion Scope & Decision Context
- **Decision Window**: Decisions are made during **January 2026** (2026-01-01 to 2026-01-31 inclusive).
- **Delivery Days**: Because day-ahead market decisions on day $D-1$ determine procurement for delivery day $D$, the operational delivery scope spans **2026-01-02 to 2026-02-01** (31 delivery days).
- **Buffer Window**: Ingested from **2025-12-28** to **2026-02-03** across **38 settlement dates** (4 days in Dec 2025 + 31 days in Jan 2026 + 3 days in Feb 2026 = exactly 38 calendar days). The fetch window is 2025-12-28 to 2026-02-03 inclusive (38 days).

---

## 2. Row Counts & Storage

| Snapshot File | Format | Row Count | File Size (on disk) | Cleaned Columns |
| :--- | :--- | :--- | :--- | :--- |
| `backend/data/actuals.parquet` | Apache Parquet (Snappy) | **1,824** | ~26.6 KB | `startTime` (UTC), `generation` (MW) |
| `backend/data/forecasts.parquet` | Apache Parquet (Snappy) | **22,192** | ~100.2 KB | `startTime` (UTC), `publishTime` (UTC), `generation` (MW) |

Both datasets are stored with zero null values and deduplicated on their natural primary keys:
- Actuals key: `startTime`
- Forecasts key: `(publishTime, startTime)`

---

## 3. Data Schema & Generation Metric Definition

According to Elexon BMRS documentation (see [Elexon Insights Solution API /datasets/WINDFOR](https://developer.data.elexon.co.uk/api-details#api=prod-insol-insights-api&operation=get-datasets-windfor)):

### Meaning of `generation` in WINDFOR and FUELHH
- **`WINDFOR`**:
  - **API Documentation Finding**: In the official Elexon Insights Solution REST API documentation and response schema model (`WindGenerationForecast`), `generation` is typed as an `integer (int64)` representing power in **Megawatts (MW)** for visible Power Park Modules (wind farms connected to the GB transmission network with operational metering).
  - **Hourly Average MW vs. Instantaneous**: The official Elexon API documentation **does not explicitly state** whether `generation` represents an hourly average MW or an instantaneous MW at `startTime`. While standard GB electricity market day-ahead scheduling and settlement convention treats 1-hour interval wind forecasts as the expected average generation (MW) over $[startTime, startTime + 1h)$, this distinction cannot be verified from the official API documentation alone.
  - **Source URL**: `https://developer.data.elexon.co.uk/api-details#api=prod-insol-insights-api&operation=get-datasets-windfor`
- **`FUELHH`**: `generation` is an integer representing the average electricity outturn power in **Megawatts (MW)** during the **30-minute settlement period** starting at `startTime` for the `WIND` fuel type.

### Actuals Schema (`actuals.parquet`)
- **`startTime`** (`datetime64[ns, UTC]`): Half-hour settlement period start in UTC (`:00` or `:30`).
- **`generation`** (`int64`): Outturn average generation in Megawatts (MW).
  - Min: 1,695 MW
  - Max: 17,805 MW
  - Mean: 11,068.65 MW

### Forecasts Schema (`forecasts.parquet`)
- **`startTime`** (`datetime64[ns, UTC]`): Forecasted hourly period start in UTC (always `:00`).
- **`publishTime`** (`datetime64[ns, UTC]`): Timestamp when NESO published the forecast run.
- **`generation`** (`int64`): Forecasted wind power in Megawatts (MW).
  - Min: 2,051 MW
  - Max: 21,353 MW
  - Mean: 12,832.00 MW

---

## 4. Hourly Resolution Finding & Alignment (Option A)

Analysis of the raw `WINDFOR` forecast stream reveals:
1. **Minute Distribution**: 100% of forecast rows have `startTime.dt.minute == 0` (all 22,192 rows). There are zero half-hourly forecast rows (0 rows at minute `:30`).
2. **Fixed Publication Shape**: Every single publication run (`publishTime`) contains **exactly 73 hourly rows** ($\text{min} = 73, \text{max} = 73, \text{mean} = 73.0, \text{std} = 0.0$). These 73 hours represent:
   - A 24-hour retrospective nowcast/backcast window ($-24\text{h}$ to $-1\text{h}$).
   - The current hour ($0\text{h}$).
   - A 48-hour forward forecast ($+1\text{h}$ to $+48\text{h}$).
3. **Forecast Slots per Delivery Day**: Each delivery day has **24 hourly slots** (00:00 to 23:00 UTC), not 48 periods.

### Approved Resolution Alignment Strategy: Option A
To compare the half-hourly actuals (`FUELHH`, 48 periods/day) against the hourly forecasts (`WINDFOR`, 24 hourly slots/day):
- **Accuracy Metrics & Tabular Joins**: Aggregate `FUELHH` actuals to hourly resolution by taking the arithmetic mean of the two 30-minute settlement periods starting at `HH:00` and `HH:30`:
  $$\text{Actual}_{\text{hourly}}(H) = \frac{\text{Actual}(H:00) + \text{Actual}(H:30)}{2}$$
  Both actuals and forecasts are then in Megawatts (MW) on the hourly `startTime` ($00:00, 01:00, \dots, 23:00$).
- **Visual Chart**: Keep the raw 30-minute actuals from `FUELHH` and render the hourly `WINDFOR` forecast as a step line spanning each hourly slot $[HH:00, (HH+1):00)$.

---

## 5. Forecast Horizons Observed

$$\text{Horizon (hours)} = \frac{\text{startTime} - \text{publishTime}}{3600}$$

| Metric | Horizon (Hours) | Interpretation |
| :--- | :--- | :--- |
| **Minimum** | **-25.5 h** | Retroactive nowcast/backcast window published with each run |
| **5th Percentile** | -13.5 h | Past settlement periods included in publication payload |
| **25th Percentile** | +3.5 h | Short-term intraday horizon |
| **Median (50th)** | **+21.5 h** | Day-ahead horizon |
| **75th Percentile** | +39.5 h | Day-ahead evening and next-day boundary |
| **95th Percentile** | +56.5 h | Two-day ahead horizon |
| **Maximum** | **+66.5 h** | Forward reach |

### Implications for Day-Ahead Decision Making
For delivery day $D$ (24 hourly slots: 00:00 to 23:00 UTC) with decision cutoff at `09:00 Europe/London` on $D-1$:
- The required forecast lead time ranges from **+16.5 hours** (for slot 00:00, since the latest publish time prior to 09:00 is consistently 07:30 on $D-1$) to **+39.5 hours** (for slot 23:00).
- Because the forward reach extends to $+48\text{h}$ (and up to $+66.5\text{h}$), the latest forecast published on or before 09:00 $D-1$ **consistently covers all 24 hourly slots** of day $D$.

### Day-Ahead Forecast Coverage Table (2026-01-02 to 2026-02-01)
Cutoff: `09:00 Europe/London` on $D-1$. Evaluated against actuals snapshot (`actuals.parquet`) and forecasts snapshot (`forecasts.parquet`).

| Delivery Day ($D$) | Decision Date ($D-1$) | Cutoff Time (Europe/London) | Covered Slots (of 24) | Latest `publishTime` Used (UTC) | Min Horizon (h) | Max Horizon (h) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 2026-01-02 | 2026-01-01 | 2026-01-01 09:00 | 24 / 24 (100%) | 2026-01-01 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-03 | 2026-01-02 | 2026-01-02 09:00 | 24 / 24 (100%) | 2026-01-02 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-04 | 2026-01-03 | 2026-01-03 09:00 | 24 / 24 (100%) | 2026-01-03 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-05 | 2026-01-04 | 2026-01-04 09:00 | 24 / 24 (100%) | 2026-01-04 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-06 | 2026-01-05 | 2026-01-05 09:00 | 24 / 24 (100%) | 2026-01-05 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-07 | 2026-01-06 | 2026-01-06 09:00 | 24 / 24 (100%) | 2026-01-06 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-08 | 2026-01-07 | 2026-01-07 09:00 | 24 / 24 (100%) | 2026-01-07 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-09 | 2026-01-08 | 2026-01-08 09:00 | 24 / 24 (100%) | 2026-01-08 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-10 | 2026-01-09 | 2026-01-09 09:00 | 24 / 24 (100%) | 2026-01-09 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-11 | 2026-01-10 | 2026-01-10 09:00 | 24 / 24 (100%) | 2026-01-10 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-12 | 2026-01-11 | 2026-01-11 09:00 | 24 / 24 (100%) | 2026-01-11 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-13 | 2026-01-12 | 2026-01-12 09:00 | 24 / 24 (100%) | 2026-01-12 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-14 | 2026-01-13 | 2026-01-13 09:00 | 24 / 24 (100%) | 2026-01-13 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-15 | 2026-01-14 | 2026-01-14 09:00 | 24 / 24 (100%) | 2026-01-14 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-16 | 2026-01-15 | 2026-01-15 09:00 | 24 / 24 (100%) | 2026-01-15 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-17 | 2026-01-16 | 2026-01-16 09:00 | 24 / 24 (100%) | 2026-01-16 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-18 | 2026-01-17 | 2026-01-17 09:00 | 24 / 24 (100%) | 2026-01-17 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-19 | 2026-01-18 | 2026-01-18 09:00 | 24 / 24 (100%) | 2026-01-18 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-20 | 2026-01-19 | 2026-01-19 09:00 | 24 / 24 (100%) | 2026-01-19 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-21 | 2026-01-20 | 2026-01-20 09:00 | 24 / 24 (100%) | 2026-01-20 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-22 | 2026-01-21 | 2026-01-21 09:00 | 24 / 24 (100%) | 2026-01-21 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-23 | 2026-01-22 | 2026-01-22 09:00 | 24 / 24 (100%) | 2026-01-22 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-24 | 2026-01-23 | 2026-01-23 09:00 | 24 / 24 (100%) | 2026-01-23 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-25 | 2026-01-24 | 2026-01-24 09:00 | 24 / 24 (100%) | 2026-01-24 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-26 | 2026-01-25 | 2026-01-25 09:00 | 24 / 24 (100%) | 2026-01-25 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-27 | 2026-01-26 | 2026-01-26 09:00 | 24 / 24 (100%) | 2026-01-26 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-28 | 2026-01-27 | 2026-01-27 09:00 | 24 / 24 (100%) | 2026-01-27 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-29 | 2026-01-28 | 2026-01-28 09:00 | 24 / 24 (100%) | 2026-01-28 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-30 | 2026-01-29 | 2026-01-29 09:00 | 24 / 24 (100%) | 2026-01-29 07:30:00 | 16.5 h | 39.5 h |
| 2026-01-31 | 2026-01-30 | 2026-01-30 09:00 | 24 / 24 (100%) | 2026-01-30 07:30:00 | 16.5 h | 39.5 h |
| 2026-02-01 | 2026-01-31 | 2026-01-31 09:00 | 24 / 24 (100%) | 2026-01-31 07:30:00 | 16.5 h | 39.5 h |

---

## 6. Publication Frequency

Over the 304 unique publish runs between `2025-12-28 02:30:00Z` and `2026-02-03 22:30:00Z`:
- Standard cadence:
  - **Every 2 hours**: 113 runs (37.2%)
  - **Every 4 hours**: 112 runs (36.8%)
  - **Every 3 hours**: 76 runs (25.0%)
- Minor timing jitter:
  - **2h 55m**: 1 run
  - **3h 05m**: 1 run
- No publication gap exceeded 4 hours.

---

## 7. Timestamp Continuity & Missing Data

### Actuals (`FUELHH`)
- **100% continuous and complete**: Exactly 48 settlement periods per day for all 38 settlement dates ($38 \times 48 = 1,824$ records).
- All successive `startTime` records have a delta of exactly **30 minutes** (`0 days 00:30:00`). Zero missing periods, zero nulls.

### Forecasts (`WINDFOR`)
- All 304 publication runs have **exactly 73 hourly rows** ($304 \times 73 = 22,192$ records).
- Zero null values across `publishTime`, `startTime`, and `generation`.

---

## 8. Anomalies & Domain Observations

1. **Negative Forecast Horizons**:
   - 4,561 records (20.55% of all forecast records) have negative horizons down to -25.5 hours. NESO publishes rolling batches containing retrospective updates for the past ~24 hours alongside forward forecasts.
   - For day-ahead delivery matching on day $D$, all target slots are strictly $\ge 15\text{ hours}$ ahead of the cutoff, naturally filtering out negative horizon rows.

2. **Daily 07:30 Publish Run Consistency**:
   - For every single decision day in January 2026 with a 09:00 cutoff, the latest available publish run is consistently at **07:30 UTC** (published 1.5 hours before the 09:00 cutoff).
   - This results in an identical horizon profile for all 31 delivery days: minimum horizon of 16.5 hours (slot 00:00) and maximum horizon of 39.5 hours (slot 23:00).
