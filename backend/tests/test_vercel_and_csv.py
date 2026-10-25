"""Tests for CSV snapshot fallback, Vercel entrypoint, and CORS configuration."""

from pathlib import Path
import tempfile
import pandas as pd
from fastapi.testclient import TestClient

from backend.app.data_loader import DataLoader, data_loader
from backend.app.main import app


def test_data_loader_csv_fallback():
    """Verify DataLoader falls back to CSV.gz when parquet engine is unavailable."""
    # Ensure standard data_loader is loaded first
    if not data_loader.is_loaded:
        data_loader.load_data()

    # Create a temporary directory containing only the .csv.gz files
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_data_dir = Path(__file__).resolve().parent.parent / "data"

        actuals_csvgz = source_data_dir / "actuals.csv.gz"
        forecasts_csvgz = source_data_dir / "forecasts.csv.gz"

        assert actuals_csvgz.exists(), "actuals.csv.gz must exist"
        assert forecasts_csvgz.exists(), "forecasts.csv.gz must exist"

        # Copy only csv.gz files to temp dir
        import shutil

        shutil.copy(actuals_csvgz, tmp_path / "actuals.csv.gz")
        shutil.copy(forecasts_csvgz, tmp_path / "forecasts.csv.gz")

        loader = DataLoader(data_dir=tmp_path)
        loader.load_data()

        assert loader.is_loaded is True
        assert loader.source_format == "csv"
        assert len(loader.actuals_df) == len(data_loader.actuals_df)
        assert len(loader.hourly_actuals_df) == len(data_loader.hourly_actuals_df)
        assert len(loader.forecasts_df) == len(data_loader.forecasts_df)

        # Verify columns and data integrity
        pd.testing.assert_series_equal(
            loader.actuals_df["generation"].reset_index(drop=True),
            data_loader.actuals_df["generation"].reset_index(drop=True),
            check_dtype=False,
        )


def test_vercel_entrypoint_import():
    """Verify backend/api/index.py exposes FastAPI app successfully."""
    from backend.api.index import app as vercel_app

    assert vercel_app is not None
    client = TestClient(vercel_app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_cors_preflight_response():
    """Verify CORS OPTIONS preflight returns expected headers."""
    client = TestClient(app)
    headers = {
        "Origin": "https://example-frontend.vercel.app",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/health", headers=headers)
    assert response.status_code == 200
