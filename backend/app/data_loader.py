"""Data loader module for cached snapshot Parquet / CSV datasets."""

import importlib.util
import logging
import os
from pathlib import Path
from typing import Optional
import pandas as pd

from backend.app.core.actuals import aggregate_actuals_hourly

logger = logging.getLogger("data_loader")


def _is_parquet_supported() -> bool:
    """Return True if a parquet engine (pyarrow or fastparquet) is installed."""
    return (
        importlib.util.find_spec("pyarrow") is not None
        or importlib.util.find_spec("fastparquet") is not None
    )


class DataLoader:
    """Singleton-style data holder for in-memory snapshot datasets."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            # Default to backend/data relative to project root or module
            env_path = os.getenv("DATA_DIR")
            if env_path:
                self.data_dir = Path(env_path)
            else:
                self.data_dir = Path(__file__).resolve().parent.parent / "data"
        else:
            self.data_dir = Path(data_dir)

        self.actuals_df: pd.DataFrame = pd.DataFrame()
        self.hourly_actuals_df: pd.DataFrame = pd.DataFrame()
        self.forecasts_df: pd.DataFrame = pd.DataFrame()
        self.is_loaded: bool = False
        self.source_format: str = "unknown"

    def load_data(self) -> None:
        """Load parquet or compact CSV.gz snapshots and precompute hourly actuals once."""
        actuals_parquet = self.data_dir / "actuals.parquet"
        forecasts_parquet = self.data_dir / "forecasts.parquet"
        actuals_csvgz = self.data_dir / "actuals.csv.gz"
        forecasts_csvgz = self.data_dir / "forecasts.csv.gz"
        actuals_csv = self.data_dir / "actuals.csv"
        forecasts_csv = self.data_dir / "forecasts.csv"

        can_use_parquet = (
            _is_parquet_supported()
            and actuals_parquet.exists()
            and forecasts_parquet.exists()
        )

        if can_use_parquet:
            logger.info("Loading snapshots from Parquet at %s", self.data_dir)
            self.actuals_df = pd.read_parquet(actuals_parquet)
            self.forecasts_df = pd.read_parquet(forecasts_parquet)
            self.source_format = "parquet"
        else:
            actuals_target = (
                actuals_csvgz
                if actuals_csvgz.exists()
                else (actuals_csv if actuals_csv.exists() else None)
            )
            forecasts_target = (
                forecasts_csvgz
                if forecasts_csvgz.exists()
                else (forecasts_csv if forecasts_csv.exists() else None)
            )

            if not actuals_target or not forecasts_target:
                raise FileNotFoundError(
                    f"Missing snapshots in {self.data_dir}. Required either "
                    f"(actuals.parquet & forecasts.parquet) or (actuals.csv.gz & forecasts.csv.gz)."
                )

            logger.info(
                "Loading snapshots from CSV (%s, %s)",
                actuals_target.name,
                forecasts_target.name,
            )
            self.actuals_df = pd.read_csv(
                actuals_target,
                compression="gzip" if str(actuals_target).endswith(".gz") else None,
            )
            self.actuals_df["startTime"] = pd.to_datetime(self.actuals_df["startTime"], utc=True)
            self.actuals_df["generation"] = pd.to_numeric(self.actuals_df["generation"], errors="coerce")

            self.forecasts_df = pd.read_csv(
                forecasts_target,
                compression="gzip" if str(forecasts_target).endswith(".gz") else None,
            )
            self.forecasts_df["startTime"] = pd.to_datetime(self.forecasts_df["startTime"], utc=True)
            self.forecasts_df["publishTime"] = pd.to_datetime(self.forecasts_df["publishTime"], utc=True)
            self.forecasts_df["generation"] = pd.to_numeric(self.forecasts_df["generation"], errors="coerce")
            self.source_format = "csv"

        # Pre-aggregate actuals to hourly resolution for fast query execution
        self.hourly_actuals_df = aggregate_actuals_hourly(self.actuals_df, drop_incomplete=True)
        self.is_loaded = True


# Global default instance
data_loader = DataLoader()

