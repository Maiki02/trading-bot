"""Build deep historical dataframe from Quotex paginated candle chunks."""

from __future__ import annotations

import asyncio
import importlib.util
import time
from pathlib import Path
from typing import Any

import pandas as pd
from src.utils.quotex_bootstrap import Quotex

REPO_ROOT = Path(__file__).resolve().parents[2]
FETCHER_PATH = REPO_ROOT / "scripts" / "quotex-symbols" / "get_historical_candles.py"


def _load_fetcher_func():
    """Load fetch_candles_chunk from scripts/quotex-symbols/get_historical_candles.py."""
    spec = importlib.util.spec_from_file_location("quotex_chunk_fetcher", FETCHER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load fetcher module from {FETCHER_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fetcher = getattr(module, "fetch_candles_chunk", None)
    if fetcher is None:
        raise ImportError("fetch_candles_chunk not found in get_historical_candles.py")

    return fetcher


_FETCH_CANDLES_CHUNK = _load_fetcher_func()


def _to_int_timestamp(raw_item: dict[str, Any]) -> int | None:
    """Resolve a candle timestamp from known payload keys."""
    for key in ("time", "timestamp", "from", "at"):
        if key in raw_item:
            try:
                return int(raw_item[key])
            except (TypeError, ValueError):
                return None
    return None


def _normalize_candle(raw_item: dict[str, Any]) -> dict[str, float] | None:
    """Normalize raw Quotex candle payload to a stable dataframe schema."""
    ts = _to_int_timestamp(raw_item)
    if ts is None:
        return None

    try:
        return {
            "time": ts,
            "open": float(raw_item.get("open")),
            "high": float(raw_item.get("high", raw_item.get("max"))),
            "low": float(raw_item.get("low", raw_item.get("min"))),
            "close": float(raw_item.get("close")),
            "volume": float(raw_item.get("ticks", raw_item.get("volume", 0.0))),
        }
    except (TypeError, ValueError):
        return None


async def build_historical_dataframe(
    client: Quotex,
    asset: str,
    period: int,
    target_candles: int,
    delay_seconds: float,
) -> pd.DataFrame:
    """Build deep historical candles dataframe using reverse pagination."""
    if target_candles <= 0:
        raise ValueError("target_candles must be > 0")

    delay_seconds = max(delay_seconds, 0.0)
    offset_seconds = max(period * 196, period)

    master_list: list[dict[str, float]] = []
    end_time = int(time.time())

    while len(master_list) < target_candles:
        chunk = await _FETCH_CANDLES_CHUNK(
            client=client,
            asset=asset,
            end_time=end_time,
            period=period,
            offset_seconds=offset_seconds,
        )

        if not chunk:
            await asyncio.sleep(delay_seconds)
            break

        normalized_chunk = [
            normalized
            for normalized in (_normalize_candle(item) for item in chunk if isinstance(item, dict))
            if normalized is not None
        ]

        if not normalized_chunk:
            await asyncio.sleep(delay_seconds)
            break

        normalized_chunk.sort(key=lambda candle: int(candle["time"]))
        oldest_ts = int(normalized_chunk[0]["time"])

        master_list.extend(normalized_chunk)
        end_time = oldest_ts - period

        await asyncio.sleep(delay_seconds)

    if not master_list:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

    dataframe = pd.DataFrame(master_list)
    dataframe = dataframe.drop_duplicates(subset=["time"])
    dataframe = dataframe.sort_values("time", ascending=True).reset_index(drop=True)
    dataframe = dataframe.tail(target_candles).reset_index(drop=True)
    return dataframe
