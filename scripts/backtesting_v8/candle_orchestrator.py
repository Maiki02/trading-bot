"""Build deep historical dataframe from Quotex paginated candle chunks."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import math
from pathlib import Path
from typing import Any

import pandas as pd
from src.utils.quotex_bootstrap import Quotex

logger = logging.getLogger(__name__)

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
    start_timestamp: int,
    end_timestamp: int,
    delay_seconds: float,
) -> pd.DataFrame:
    """Build deep historical candles dataframe using reverse pagination."""
    if start_timestamp >= end_timestamp:
        raise ValueError("start_timestamp must be lower than end_timestamp")

    delay_seconds = max(delay_seconds, 0.0)
    offset_seconds = max(period * 196, period)
    expected_total_candles = max(int((end_timestamp - start_timestamp) / period), 1)
    total_chunks_estimados = max(math.ceil(expected_total_candles / 196), 1)
    max_chunks_hard_limit = max(total_chunks_estimados + 5, total_chunks_estimados * 2)

    master_list: list[dict[str, float]] = []
    original_end_timestamp = int(end_timestamp)
    current_end_time = int(end_timestamp)
    current_chunk = 0
    consecutive_no_progress = 0

    # Date-driven cutoff: stop as soon as we cross the requested start bound.
    while current_end_time > start_timestamp and current_chunk < max_chunks_hard_limit:
        logger.info(
            "Solicitando chunk %s/%s para %s (cursor_end=%s)",
            current_chunk + 1,
            total_chunks_estimados,
            asset,
            current_end_time,
        )

        chunk = await _FETCH_CANDLES_CHUNK(
            client=client,
            asset=asset,
            end_time=current_end_time,
            period=period,
            offset_seconds=offset_seconds,
        )

        if not chunk:
            consecutive_no_progress += 1
            logger.warning(
                "Chunk vacio para %s (no_progress=%s). Retrocediendo cursor %s segundos.",
                asset,
                consecutive_no_progress,
                offset_seconds,
            )
            current_end_time -= offset_seconds
            await asyncio.sleep(delay_seconds)
            continue

        normalized_chunk = [
            normalized
            for normalized in (_normalize_candle(item) for item in chunk if isinstance(item, dict))
            if normalized is not None
        ]

        if not normalized_chunk:
            consecutive_no_progress += 1
            logger.warning(
                "Chunk sin velas normalizables para %s (no_progress=%s). Retrocediendo cursor %s segundos.",
                asset,
                consecutive_no_progress,
                offset_seconds,
            )
            current_end_time -= offset_seconds
            await asyncio.sleep(delay_seconds)
            continue

        # Keep only candles at or before current cursor to ensure backward pagination.
        normalized_chunk = [
            candle for candle in normalized_chunk if int(candle["time"]) <= current_end_time
        ]
        if not normalized_chunk:
            consecutive_no_progress += 1
            logger.warning(
                "Chunk sin velas <= cursor para %s (no_progress=%s). Retrocediendo cursor %s segundos.",
                asset,
                consecutive_no_progress,
                offset_seconds,
            )
            current_end_time -= offset_seconds
            await asyncio.sleep(delay_seconds)
            continue

        normalized_chunk.sort(key=lambda candle: int(candle["time"]))
        oldest_ts = int(normalized_chunk[0]["time"])

        # Hard stop if broker payload keeps the same/newer boundary repeatedly.
        if oldest_ts >= current_end_time:
            consecutive_no_progress += 1
            logger.warning(
                "Sin progreso temporal en %s: oldest_ts=%s current_end_time=%s (no_progress=%s).",
                asset,
                oldest_ts,
                current_end_time,
                consecutive_no_progress,
            )
            current_end_time -= offset_seconds
            await asyncio.sleep(delay_seconds)
            if consecutive_no_progress >= 3:
                logger.warning(
                    "Corte por falta de progreso temporal sostenida en %s tras %s intentos.",
                    asset,
                    consecutive_no_progress,
                )
                break
            continue

        master_list.extend(normalized_chunk)
        consecutive_no_progress = 0
        current_chunk += 1
        logger.info(
            f"Descargando chunk {current_chunk} de ~{total_chunks_estimados} para {asset}..."
        )
        logger.info(
            "Chunk %s recibido para %s: velas_validas=%s acumuladas=%s rango=[%s..%s]",
            current_chunk,
            asset,
            len(normalized_chunk),
            len(master_list),
            oldest_ts,
            int(normalized_chunk[-1]["time"]),
        )
        current_end_time = oldest_ts - period

        await asyncio.sleep(delay_seconds)

    if current_chunk >= max_chunks_hard_limit:
        logger.warning(
            "Corte por limite de chunks en %s: ejecutados=%s estimados=%s",
            asset,
            current_chunk,
            total_chunks_estimados,
        )

    if not master_list:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

    dataframe = pd.DataFrame(master_list)

    # Strict date range filter requested by caller.
    dataframe = dataframe[
        (dataframe["time"] >= int(start_timestamp)) &
        (dataframe["time"] <= int(original_end_timestamp))
    ]

    # Remove overlap across chunk borders and normalize chronological order.
    dataframe = dataframe.drop_duplicates(subset=["time"]).sort_values(
        "time", ascending=True
    ).reset_index(drop=True)

    # Vectorized temporal integrity validation.
    time_diffs = dataframe["time"].diff()
    gaps = time_diffs[time_diffs > period]
    if not gaps.empty:
        logger.warning(
            "Se detectaron %s saltos temporales mayores a %s segundos en %s.",
            len(gaps),
            period,
            asset,
        )

    if dataframe.empty:
        logger.warning("Sin velas finales en rango solicitado para %s.", asset)
    else:
        logger.info(
            "Historial final %s: velas=%s rango_final=[%s..%s]",
            asset,
            len(dataframe),
            int(dataframe.iloc[0]["time"]),
            int(dataframe.iloc[-1]["time"]),
        )

    return dataframe
