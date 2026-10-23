"""Data loader module for cached snapshot Parquet datasets."""

import os
from pathlib import Path
from typing import Optional
import pandas as pd

from backend.app.core.actuals import aggregate_actuals_hourly


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

    def load_data(self) -> None:
        """Load parquet snapshots and precompute hourly actuals once."""
        actuals_file = self.data_dir / "actuals.parquet"
        forecasts_file = self.data_dir / "forecasts.parquet"

        if not actuals_file.exists():
            raise FileNotFoundError(f"Missing actuals snapshot at {actuals_file}")
        if not forecasts_file.exists():
            raise FileNotFoundError(f"Missing forecasts snapshot at {forecasts_file}")

        self.actuals_df = pd.read_parquet(actuals_file)
        self.forecasts_df = pd.read_parquet(forecasts_file)

        # Pre-aggregate actuals to hourly resolution for fast query execution
        self.hourly_actuals_df = aggregate_actuals_hourly(self.actuals_df, drop_incomplete=True)
        self.is_loaded = True


# Global default instance
data_loader = DataLoader()
