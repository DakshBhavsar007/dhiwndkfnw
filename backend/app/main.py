"""FastAPI main application for the wind-power forecast monitoring dashboard."""

from contextlib import asynccontextmanager
import logging
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.app.data_loader import data_loader
from backend.app.middleware import RequestLoggingMiddleware
from backend.app.schemas import (
    AccuracyResponse,
    ErrorBandResponse,
    ForecastResponse,
    HealthResponse,
    MetaResponse,
)
from backend.app.services import (
    DEFAULT_CUTOFF,
    MAX_DELIVERY_DATE,
    MIN_DELIVERY_DATE,
    get_accuracy_service,
    get_error_band_service,
    get_forecast_service,
    get_meta_service,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager: loads snapshot parquet files once at startup."""
    logger.info("Initializing application and loading parquet datasets...")
    try:
        data_loader.load_data()
        logger.info(
            "Successfully loaded %d actuals rows, %d hourly actuals, %d forecast rows.",
            len(data_loader.actuals_df),
            len(data_loader.hourly_actuals_df),
            len(data_loader.forecasts_df),
        )
    except Exception as exc:
        logger.error("Failed to load snapshot parquet datasets: %s", exc, exc_info=True)
        raise exc
    yield
    logger.info("Application shutting down...")


app = FastAPI(
    title="Wind-Power Forecast Monitoring API",
    version="1.0.0",
    description="""
API backend for UK Day-Ahead Electricity Market Wind Power Forecast Monitoring.

### Key Domain Rules & Conventions:
- **Decision Window**: Decisions are made during January 2026 for delivery days **2026-01-02 to 2026-02-01**.
- **Cutoff Rule**: Forecast selection strictly requires `publishTime <= cutoff` (default 09:00 Europe/London on D-1). Forecasts published after cutoff are never used.
- **Resolution Alignment (Option A)**:
  - Forecasts (`WINDFOR`): Hourly resolution (24 slots per normal delivery day).
  - Actuals (`FUELHH`): Half-hourly resolution (48 settlement periods per day).
  - For evaluation and tabular joins, actuals are aggregated to hourly by arithmetic mean: `(Actual(HH:00) + Actual(HH:30)) / 2`.
  - For charts, raw 30-min actuals are preserved alongside step-line forecasts.
- **Bias Sign Convention**:
  - `error = forecast - actual`
  - `bias = mean(forecast - actual)`
  - **Positive bias** indicates **over-forecasting** (forecast > actual).
  - **Negative bias** indicates **under-forecasting** (forecast < actual).
- **Leakage-Free Error Bands**: Historical error quantiles for day D are computed strictly from completed delivery days **<= D-2**.
""",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging & request-ID tracking
app.add_middleware(RequestLoggingMiddleware)


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["System"],
)
def get_health() -> HealthResponse:
    """Check service health and parquet snapshot memory state."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        data_loaded=data_loader.is_loaded,
    )


@app.get(
    "/api/meta",
    response_model=MetaResponse,
    summary="API metadata and domain parameters",
    tags=["Metadata"],
)
def get_meta() -> MetaResponse:
    """Return valid delivery date bounds, default cutoffs, and alignment assumptions."""
    return get_meta_service()


@app.get(
    "/api/forecast",
    response_model=ForecastResponse,
    summary="Per-hour cutoff-aware forecast, actuals, and daily metrics",
    tags=["Forecasts"],
)
def get_forecast(
    date: str = Query(
        ...,
        description="Delivery date (YYYY-MM-DD), valid between 2026-01-02 and 2026-02-01",
        examples=["2026-01-02"],
    ),
    cutoff: str = Query(
        DEFAULT_CUTOFF,
        description="Decision cutoff time on D-1 (HH:MM in Europe/London)",
        examples=["09:00"],
    ),
) -> ForecastResponse:
    """Retrieve the cutoff-aware forecast for a single delivery day along with hourly & 30-min actuals."""
    return get_forecast_service(date_str=date, cutoff_time=cutoff, loader=data_loader)


@app.get(
    "/api/accuracy",
    response_model=AccuracyResponse,
    summary="Accuracy metrics, by-hour, and by-horizon breakdown",
    tags=["Accuracy"],
)
def get_accuracy(
    start: str = Query(
        MIN_DELIVERY_DATE,
        description="Start delivery date (YYYY-MM-DD)",
        examples=["2026-01-02"],
    ),
    end: str = Query(
        MAX_DELIVERY_DATE,
        description="End delivery date (YYYY-MM-DD)",
        examples=["2026-02-01"],
    ),
    cutoff: str = Query(
        DEFAULT_CUTOFF,
        description="Decision cutoff time on D-1 (HH:MM in Europe/London)",
        examples=["09:00"],
    ),
) -> AccuracyResponse:
    """Compute overall accuracy metrics, hourly diurnal breakdown, and lead-time horizon breakdown."""
    return get_accuracy_service(
        start_str=start, end_str=end, cutoff_time=cutoff, loader=data_loader
    )


@app.get(
    "/api/error-band",
    response_model=ErrorBandResponse,
    summary="Forecast with leakage-free historical error bounds",
    tags=["Forecasts"],
)
def get_error_band(
    date: str = Query(
        ...,
        description="Delivery date (YYYY-MM-DD), valid between 2026-01-02 and 2026-02-01",
        examples=["2026-01-06"],
    ),
    cutoff: str = Query(
        DEFAULT_CUTOFF,
        description="Decision cutoff time on D-1 (HH:MM in Europe/London)",
        examples=["09:00"],
    ),
) -> ErrorBandResponse:
    """Compute hourly forecast with P10/P90 error confidence bands strictly using historical days <= D-2."""
    return get_error_band_service(
        date_str=date, cutoff_time=cutoff, loader=data_loader
    )
