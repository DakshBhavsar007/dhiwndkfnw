"""Elexon BMRS data ingestion script for FUELHH (WIND) and WINDFOR streams.

Fetches data for January 2026 (plus buffer on both sides), cleans it,
and saves deterministic Parquet snapshots to backend/data/.
"""

import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fetch_data")

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"


def get_http_session(
    retries: int = 5,
    backoff_factor: float = 1.0,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
) -> requests.Session:
    """Create a requests session with automatic retries and exponential backoff."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_fuelhh_actuals(
    session: requests.Session,
    start_date: str,
    end_date: str,
    chunk_days: int = 7,
) -> pd.DataFrame:
    """Fetch FUELHH wind actual generation stream with date chunking.

    Parameters:
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
    """
    url = f"{BASE_URL}/datasets/FUELHH/stream"
    dt_current = datetime.strptime(start_date, "%Y-%m-%d").date()
    dt_end = datetime.strptime(end_date, "%Y-%m-%d").date()

    all_records: List[Dict[str, Any]] = []

    while dt_current <= dt_end:
        chunk_end = min(dt_current + timedelta(days=chunk_days - 1), dt_end)
        logger.info(
            "Fetching FUELHH (WIND) from %s to %s...",
            dt_current.isoformat(),
            chunk_end.isoformat(),
        )
        params = {
            "settlementDateFrom": dt_current.isoformat(),
            "settlementDateTo": chunk_end.isoformat(),
            "fuelType": "WIND",
        }
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            all_records.extend(data)
        elif isinstance(data, dict) and "data" in data:
            all_records.extend(data["data"])
        else:
            raise ValueError(f"Unexpected response format from FUELHH: {type(data)}")

        dt_current = chunk_end + timedelta(days=1)

    logger.info("Raw FUELHH records fetched: %d", len(all_records))
    if not all_records:
        return pd.DataFrame(columns=["startTime", "generation"])

    df = pd.DataFrame(all_records)

    # Clean & standardize
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce").astype("int64")

    # Keep only needed columns, dedupe and sort
    df = df[["startTime", "generation"]].drop_duplicates(subset=["startTime"])
    df = df.sort_values(by="startTime").reset_index(drop=True)

    return df


def fetch_windfor_forecasts(
    session: requests.Session,
    start_dt: str,
    end_dt: str,
    chunk_days: int = 7,
) -> pd.DataFrame:
    """Fetch WINDFOR wind generation forecast stream with date chunking.

    Parameters:
        start_dt: ISO8601 string (e.g. 2025-12-28T00:00:00Z)
        end_dt: ISO8601 string (e.g. 2026-02-03T23:59:59Z)
    """
    url = f"{BASE_URL}/datasets/WINDFOR/stream"
    dt_current = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
    dt_end = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))

    all_records: List[Dict[str, Any]] = []

    while dt_current <= dt_end:
        chunk_end = min(
            dt_current + timedelta(days=chunk_days) - timedelta(seconds=1), dt_end
        )
        from_str = dt_current.strftime("%Y-%m-%dT%H:%M:%SZ")
        to_str = chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.info("Fetching WINDFOR from %s to %s...", from_str, to_str)

        params = {
            "publishDateTimeFrom": from_str,
            "publishDateTimeTo": to_str,
        }
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            all_records.extend(data)
        elif isinstance(data, dict) and "data" in data:
            all_records.extend(data["data"])
        else:
            raise ValueError(f"Unexpected response format from WINDFOR: {type(data)}")

        dt_current = chunk_end + timedelta(seconds=1)

    logger.info("Raw WINDFOR records fetched: %d", len(all_records))
    if not all_records:
        return pd.DataFrame(columns=["startTime", "publishTime", "generation"])

    df = pd.DataFrame(all_records)

    # Clean & standardize
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce").astype("int64")

    # Keep only needed columns, dedupe and sort
    df = df[["startTime", "publishTime", "generation"]].drop_duplicates(
        subset=["publishTime", "startTime"]
    )
    df = df.sort_values(by=["publishTime", "startTime"]).reset_index(drop=True)

    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and clean Elexon FUELHH actuals and WINDFOR forecasts."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "data"),
        help="Target directory for parquet files.",
    )
    parser.add_argument(
        "--fuelhh-start",
        type=str,
        default="2025-12-28",
        help="Start settlement date for FUELHH (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--fuelhh-end",
        type=str,
        default="2026-02-03",
        help="End settlement date for FUELHH (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--windfor-start",
        type=str,
        default="2025-12-28T00:00:00Z",
        help="Start publish date for WINDFOR (ISO8601)",
    )
    parser.add_argument(
        "--windfor-end",
        type=str,
        default="2026-02-03T23:59:59Z",
        help="End publish date for WINDFOR (ISO8601)",
    )
    parser.add_argument(
        "--convert-existing",
        action="store_true",
        help="Convert existing parquet snapshots to CSV.gz without fetching from Elexon.",
    )
    args = parser.parse_args()

    out_path = Path(args.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    session = get_http_session()

    # 1. Fetch FUELHH Actuals
    if args.convert_existing:
        actuals_file = out_path / "actuals.parquet"
        if not actuals_file.exists():
            raise FileNotFoundError(f"Cannot convert: {actuals_file} not found.")
        actuals_df = pd.read_parquet(actuals_file)
        logger.info("Loaded %d existing actuals from %s", len(actuals_df), actuals_file)
    else:
        actuals_df = fetch_fuelhh_actuals(
            session=session,
            start_date=args.fuelhh_start,
            end_date=args.fuelhh_end,
        )
        actuals_file = out_path / "actuals.parquet"
        actuals_df.to_parquet(actuals_file, index=False)

    # Save compact CSV.gz snapshot
    actuals_csv = out_path / "actuals.csv.gz"
    actuals_df.to_csv(actuals_csv, index=False, compression="gzip")
    logger.info(
        "Saved %d actuals rows to %s (parquet: %.2f KB, csv.gz: %.2f KB)",
        len(actuals_df),
        out_path,
        actuals_file.stat().st_size / 1024,
        actuals_csv.stat().st_size / 1024,
    )

    # 2. Fetch WINDFOR Forecasts
    if args.convert_existing:
        forecasts_file = out_path / "forecasts.parquet"
        if not forecasts_file.exists():
            raise FileNotFoundError(f"Cannot convert: {forecasts_file} not found.")
        forecasts_df = pd.read_parquet(forecasts_file)
        logger.info("Loaded %d existing forecasts from %s", len(forecasts_df), forecasts_file)
    else:
        forecasts_df = fetch_windfor_forecasts(
            session=session,
            start_dt=args.windfor_start,
            end_dt=args.windfor_end,
        )
        forecasts_file = out_path / "forecasts.parquet"
        forecasts_df.to_parquet(forecasts_file, index=False)

    # Save compact CSV.gz snapshot
    forecasts_csv = out_path / "forecasts.csv.gz"
    forecasts_df.to_csv(forecasts_csv, index=False, compression="gzip")
    logger.info(
        "Saved %d forecasts rows to %s (parquet: %.2f KB, csv.gz: %.2f KB)",
        len(forecasts_df),
        out_path,
        forecasts_file.stat().st_size / 1024,
        forecasts_csv.stat().st_size / 1024,
    )


if __name__ == "__main__":
    main()
