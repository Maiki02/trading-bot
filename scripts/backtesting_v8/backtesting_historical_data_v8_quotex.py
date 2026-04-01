"""
Backtesting Historical Data V8 (Quotex)
=======================================
Generate a typed JSONL dataset for backtesting candlestick reversal signals
using Quotex historical candles.
"""

import argparse
import asyncio
from dataclasses import dataclass
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from src.utils.quotex_bootstrap import Quotex

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from config import Config
from src.logic.analysis_service import analyze_trend, detect_exhaustion
from src.logic.candle import (
    detect_candle_exhaustion,
    is_hammer,
    is_hanging_man,
    is_inverted_hammer,
    is_shooting_star,
)
from src.logic.signal_classifier import classify_signal
from src.utils.indicators import calculate_bollinger_bands, calculate_ema, calculate_rsi


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder with numpy support."""

    def default(self, obj):  # type: ignore[override]
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


OUTPUT_FILE = "data/trading_signals_dataset_v8_quotex.jsonl"
CANDLE_PERIOD_SECONDS = 60
QUOTEX_CHUNK_LIMIT = 196
OFFSET_SECONDS = QUOTEX_CHUNK_LIMIT * CANDLE_PERIOD_SECONDS
WARMUP_CANDLES = 100
CHUNK_MAX_RETRIES = 3
CHUNK_RETRY_DELAY_SECONDS = 0.5
CHUNK_MAX_CONSECUTIVE_FAILURES = 5
CHUNK_MAX_CONSECUTIVE_EMPTY_WINDOWS = 5
CONNECT_PHASE_RETRIES = 3
CONNECT_BACKOFF_BASE_SECONDS = 0.6
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SESSION_FILE = os.path.join(PROJECT_ROOT, "session.json")


def setup_logging() -> logging.Logger:
    """Configure console and file logging."""
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler("logs/backtesting_v8_quotex.log", mode="w", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    logging.getLogger("websocket").setLevel(logging.WARNING)
    return logging.getLogger("BacktestingV8Quotex")


logger = setup_logging()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Generate V8 historical dataset from Quotex")
    parser.add_argument(
        "--start-date",
        required=True,
        type=str,
        help="Start date in format YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="Optional end date in format YYYY-MM-DD (defaults to now)",
    )
    return parser.parse_args()


def parse_date(date_text: str, end_of_day: bool = False) -> datetime:
    """Parse date string in YYYY-MM-DD format."""
    base_date = datetime.strptime(date_text, "%Y-%m-%d")
    if end_of_day:
        return base_date + timedelta(days=1) - timedelta(seconds=1)
    return base_date


@dataclass(frozen=True)
class ConnectionPhaseResult:
    """Connection result details for one strategy phase."""

    client: Optional[Quotex]
    reason: Optional[str]
    attempts: int


def load_persisted_session(email: str) -> Optional[Dict[str, Optional[str]]]:
    """Load persisted Quotex session data from session.json for the given email."""
    if not email or not os.path.exists(SESSION_FILE):
        return None

    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as session_file:
            payload = json.load(session_file)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    account_entry = payload.get(email)
    if not isinstance(account_entry, dict):
        return None

    user_agent = str(account_entry.get("user_agent") or "").strip()
    token = str(account_entry.get("token") or "").strip()
    cookies_raw = account_entry.get("cookies")
    cookies = str(cookies_raw).strip() if cookies_raw is not None else ""

    if not user_agent or not token:
        return None

    return {
        "user_agent": user_agent,
        "token": token,
        "cookies": cookies or None,
    }


def build_client_for_phase(
    phase: str,
    session_data: Optional[Dict[str, Optional[str]]],
) -> Quotex:
    """Build a Quotex client for the requested connection phase."""
    client = Quotex(email=Config.QUOTEX.email, password=Config.QUOTEX.password, lang="en")
    client.debug_ws_enable = Config.QUOTEX.ws_debug

    if phase == "persisted":
        if not session_data:
            raise ValueError("Persisted session phase requested without valid session data")
        client.session_data = {
            "user_agent": str(session_data["user_agent"]),
            "cookies": session_data["cookies"],
            "token": str(session_data["token"]),
        }
    elif phase != "fresh":
        raise ValueError(f"Unsupported connection phase: {phase}")

    return client


async def try_connect_phase(
    phase: str,
    session_data: Optional[Dict[str, Optional[str]]],
    retries: int = CONNECT_PHASE_RETRIES,
) -> ConnectionPhaseResult:
    """Try one connection phase with retries and exponential backoff."""
    last_reason: Optional[str] = None

    for attempt in range(1, retries + 1):
        client: Optional[Quotex] = None
        try:
            client = build_client_for_phase(phase, session_data)
            connected, reason = await asyncio.wait_for(
                client.connect(),
                timeout=Config.QUOTEX.connect_timeout_seconds,
            )
            reason_text = str(reason)
            token_rejected = "token rejected" in reason_text.lower()

            if connected and not token_rejected:
                await asyncio.wait_for(
                    client.change_account("PRACTICE"),
                    timeout=Config.QUOTEX.request_timeout_seconds,
                )
                logger.info(
                    "Quotex connected using phase=%s (attempt %s/%s), account=PRACTICE",
                    phase,
                    attempt,
                    retries,
                )
                return ConnectionPhaseResult(client=client, reason=None, attempts=attempt)

            last_reason = reason_text or "Unknown connection failure"
        except asyncio.TimeoutError:
            last_reason = "Connection timeout"
        except Exception as error:
            last_reason = str(error)

        if client is not None:
            try:
                await client.close()
            except Exception:
                pass

        logger.warning(
            "Quotex connect failed in phase=%s (attempt %s/%s): %s",
            phase,
            attempt,
            retries,
            last_reason,
        )

        if attempt < retries:
            backoff = CONNECT_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            await asyncio.sleep(backoff)

    return ConnectionPhaseResult(client=None, reason=last_reason, attempts=retries)


async def connect_with_session_strategy() -> Quotex:
    """Connect to Quotex using a phased persisted-then-fresh strategy."""
    if not Config.QUOTEX.email or not Config.QUOTEX.password:
        raise ValueError("Quotex credentials are missing in environment variables")

    persisted_session = load_persisted_session(Config.QUOTEX.email)
    phases = ["persisted", "fresh"] if persisted_session else ["fresh"]
    logger.info("Starting Quotex connection strategy with phases=%s", ",".join(phases))

    failures: List[str] = []

    for phase in phases:
        phase_session = persisted_session if phase == "persisted" else None
        result = await try_connect_phase(phase=phase, session_data=phase_session)
        if result.client is not None:
            return result.client

        failure_reason = result.reason or "Unknown connection failure"
        failures.append(f"{phase}:{failure_reason}")
        logger.warning("Connection phase failed: %s", phase)

    raise ConnectionError(
        "Quotex connection failed after all phases. Details: " + " | ".join(failures)
    )


async def connect_quotex() -> Quotex:
    """Connect to Quotex using persisted/fresh session strategy."""
    return await connect_with_session_strategy()


def resolve_assets() -> List[str]:
    """Resolve target assets for Quotex dataset generation."""
    assets = [asset.strip() for asset in Config.QUOTEX.assets if asset.strip()]
    if assets:
        return assets
    return [asset.strip() for asset in Config.TARGET_ASSETS if asset.strip()]


def normalize_quotex_candle(raw: Dict[str, object]) -> Optional[Dict[str, float]]:
    """Normalize Quotex candle payload into the IQ-compatible candle schema."""
    timestamp_value = (
        raw.get("time")
        or raw.get("timestamp")
        or raw.get("from")
        or raw.get("at")
    )
    if timestamp_value is None:
        return None

    try:
        candle = {
            "from": int(timestamp_value),
            "open": float(raw.get("open")),
            "max": float(raw.get("high", raw.get("max"))),
            "min": float(raw.get("low", raw.get("min"))),
            "close": float(raw.get("close")),
            "volume": float(raw.get("ticks", raw.get("volume", 0.0))),
        }
    except (TypeError, ValueError):
        return None

    return candle


async def subscribe_asset_stream(client: Quotex, asset: str) -> None:
    """Subscribe to candle stream before requesting historical data."""
    client.start_candles_stream(asset, CANDLE_PERIOD_SECONDS)
    await asyncio.sleep(0.2)
    logger.info("Subscribed to Quotex candle stream for %s", asset)


async def resolve_quotex_asset_name(client: Quotex, symbol: str) -> str:
    """Resolve broker asset name for a requested symbol."""
    try:
        asset_name, _asset_data = await asyncio.wait_for(
            client.get_available_asset(symbol, force_open=True),
            timeout=Config.QUOTEX.request_timeout_seconds,
        )
        resolved = str(asset_name or symbol)
        if resolved != symbol:
            logger.info("Resolved Quotex asset %s -> %s", symbol, resolved)
        return resolved
    except Exception as error:
        logger.warning(
            "Could not resolve asset name for %s (%s). Using raw symbol.",
            symbol,
            error,
        )
        return symbol


async def fetch_historical_data(
    client: Quotex,
    asset: str,
    start_ts: int,
    end_ts: int,
) -> List[Dict[str, float]]:
    """Fetch historical candles in reverse chunks of 196 candles with retries.

    Flow requested by user:
    - Start from end_ts and move backwards.
    - If one chunk cannot return usable data, stop this symbol and continue with next.
    """
    all_candles: List[Dict[str, float]] = []
    seen_timestamps: Set[int] = set()
    cursor_end = int(end_ts)
    consecutive_chunk_failures = 0
    consecutive_empty_windows = 0
    chunk_timeout_seconds = max(Config.QUOTEX.request_timeout_seconds, 60)
    chunk_index = 0

    while cursor_end >= start_ts:
        chunk_index += 1
        window_end = cursor_end
        window_start = max(start_ts, window_end - OFFSET_SECONDS)
        logger.info(
            "Chunk %s | %s | requested reverse range %s -> %s",
            chunk_index,
            asset,
            datetime.fromtimestamp(window_start).isoformat(),
            datetime.fromtimestamp(window_end).isoformat(),
        )

        chunk_payload: Optional[List[Dict[str, object]]] = None

        for attempt in range(1, CHUNK_MAX_RETRIES + 1):
            try:
                raw_chunk = await asyncio.wait_for(
                    client.get_candles(asset, float(window_end), OFFSET_SECONDS, CANDLE_PERIOD_SECONDS),
                    timeout=chunk_timeout_seconds,
                )
                if isinstance(raw_chunk, list):
                    chunk_payload = raw_chunk
                else:
                    chunk_payload = []
                break
            except asyncio.TimeoutError:
                logger.warning(
                    "Timeout on chunk for %s at window_end=%s (attempt %s/%s)",
                    asset,
                    window_end,
                    attempt,
                    CHUNK_MAX_RETRIES,
                )
            except Exception as error:
                logger.warning(
                    "Chunk error for %s at window_end=%s (attempt %s/%s): %s",
                    asset,
                    window_end,
                    attempt,
                    CHUNK_MAX_RETRIES,
                    error,
                )

            await asyncio.sleep(CHUNK_RETRY_DELAY_SECONDS * attempt)

        if chunk_payload is None:
            consecutive_chunk_failures += 1
            logger.warning(
                "Failed chunk for %s at range %s -> %s after %s attempts (consecutive failures=%s/%s)",
                asset,
                datetime.fromtimestamp(window_start).isoformat(),
                datetime.fromtimestamp(window_end).isoformat(),
                CHUNK_MAX_RETRIES,
                consecutive_chunk_failures,
                CHUNK_MAX_CONSECUTIVE_FAILURES,
            )
            if consecutive_chunk_failures >= CHUNK_MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "Stopping symbol %s after %s consecutive chunk failures.",
                    asset,
                    consecutive_chunk_failures,
                )
                break

            # Move to previous window to avoid getting stuck on same failing range.
            cursor_end = window_start - CANDLE_PERIOD_SECONDS
            continue

        consecutive_chunk_failures = 0

        normalized_chunk = []
        for raw_candle in chunk_payload:
            if not isinstance(raw_candle, dict):
                continue
            normalized = normalize_quotex_candle(raw_candle)
            if normalized is None:
                continue
            candle_ts = int(normalized["from"])
            if window_start <= candle_ts <= window_end:
                normalized_chunk.append(normalized)

        if normalized_chunk:
            added_count = 0
            oldest_ts = window_end
            for candle in normalized_chunk:
                candle_ts = int(candle["from"])
                if candle_ts in seen_timestamps:
                    continue
                seen_timestamps.add(candle_ts)
                all_candles.append(candle)
                added_count += 1
                if candle_ts < oldest_ts:
                    oldest_ts = candle_ts

            consecutive_empty_windows = 0

            cursor_end = oldest_ts - CANDLE_PERIOD_SECONDS
            logger.info(
                "Chunk %s | %s | valid=%s added=%s next_end=%s",
                chunk_index,
                asset,
                len(normalized_chunk),
                added_count,
                datetime.fromtimestamp(max(cursor_end, start_ts)).isoformat(),
            )
            continue

        logger.warning(
            "Chunk %s | %s | no valid candles in requested range %s -> %s",
            chunk_index,
            asset,
            datetime.fromtimestamp(window_start).isoformat(),
            datetime.fromtimestamp(window_end).isoformat(),
        )
        consecutive_empty_windows += 1
        if consecutive_empty_windows >= CHUNK_MAX_CONSECUTIVE_EMPTY_WINDOWS:
            logger.warning(
                "Stopping symbol %s after %s consecutive empty windows.",
                asset,
                consecutive_empty_windows,
            )
            break

        cursor_end = window_start - CANDLE_PERIOD_SECONDS
        continue

    ordered = sorted(all_candles, key=lambda candle: int(candle["from"]))
    logger.info("Fetched %s unique Quotex candles for %s", len(ordered), asset)
    return ordered


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all indicators required by V8 signal generation."""
    for period in [3, 5, 7, 10, 15, 20, 30, 50]:
        df[f"ema_{period}"] = calculate_ema(df["close"], period)

    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(
        df["close"], Config.CANDLE.BB_PERIOD, Config.CANDLE.BB_STD_DEV
    )
    df["bb_upper"] = bb_upper
    df["bb_middle"] = bb_middle
    df["bb_lower"] = bb_lower
    df["rsi"] = calculate_rsi(df["close"], Config.RSI_PERIOD)
    return df


def analyze_candle_row(
    row: pd.Series,
    prev_row: pd.Series,
    prev_emas: Dict[str, float],
) -> Optional[Dict[str, object]]:
    """Analyze one candle row and return a signal payload if a valid pattern exists."""
    open_price = float(row["open"])
    high = float(row["max"])
    low = float(row["min"])
    close = float(row["close"])
    timestamp = int(row["from"])

    emas = {
        "ema_3": float(row["ema_3"]),
        "ema_5": float(row["ema_5"]),
        "ema_7": float(row["ema_7"]),
        "ema_10": float(row["ema_10"]),
        "ema_15": float(row["ema_15"]),
        "ema_20": float(row["ema_20"]),
        "ema_30": float(row["ema_30"]),
        "ema_50": float(row["ema_50"]),
    }

    trend_analysis = analyze_trend(close, emas, prev_emas)

    patterns: List[Tuple[str, float, str]] = []

    is_ss, conf_ss, _ = is_shooting_star(open_price, high, low, close)
    if is_ss:
        patterns.append(("SHOOTING_STAR", conf_ss, "PUT"))

    is_hm, conf_hm, _ = is_hanging_man(open_price, high, low, close)
    if is_hm:
        patterns.append(("HANGING_MAN", conf_hm, "CALL"))

    is_ih, conf_ih, _ = is_inverted_hammer(open_price, high, low, close)
    if is_ih:
        patterns.append(("INVERTED_HAMMER", conf_ih, "PUT"))

    is_h, conf_h, _ = is_hammer(open_price, high, low, close)
    if is_h:
        patterns.append(("HAMMER", conf_h, "CALL"))

    if not patterns:
        return None

    for pattern_name, confidence, direction in patterns:
        is_bullish_trend = "BULLISH" in trend_analysis.status
        is_bearish_trend = "BEARISH" in trend_analysis.status

        valid_trend = False
        if direction == "PUT" and is_bullish_trend:
            valid_trend = True
        if direction == "CALL" and is_bearish_trend:
            valid_trend = True

        if not valid_trend and trend_analysis.status != "NEUTRAL":
            continue

        exhaustion_bb = detect_exhaustion(high, low, close, row["bb_upper"], row["bb_lower"])
        candle_exhaustion = detect_candle_exhaustion(
            pattern_name,
            high,
            low,
            float(prev_row["max"]),
            float(prev_row["min"]),
        )
        rsi_value = float(row["rsi"]) if pd.notna(row["rsi"]) else None

        signal_strength = classify_signal(
            pattern=pattern_name,
            trend_status=trend_analysis.status,
            exhaustion_bb=exhaustion_bb,
            candle_exhaustion=candle_exhaustion,
            rsi_val=rsi_value,
        )

        return {
            "metadata": {
                "algo_version": Config.ALGO_VERSION,
                "source": "QUOTEX",
                "symbol": row["symbol"],
                "timestamp": timestamp,
                "datetime": datetime.fromtimestamp(timestamp).isoformat(),
            },
            "signal": {
                "pattern_name": pattern_name,
                "direction": direction,
                "confidence": confidence,
                "signal_strength": signal_strength,
                "rsi_filter_passed": True,
            },
            "pattern_candle": {
                "timestamp": timestamp,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": float(row["volume"]),
                "pattern": pattern_name,
                "confidence": float(confidence),
            },
            "technical": {
                "ema_values": emas,
                "rsi_value": rsi_value,
                "trend_status": trend_analysis.status,
                "exhaustion_bb": exhaustion_bb,
                "exhaustion_candle": candle_exhaustion,
            },
        }

    return None


def load_existing_keys(output_file: str) -> Set[Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]]:
    """Load existing keys to avoid duplicate lines when appending."""
    keys: Set[Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]] = set()
    if not os.path.exists(output_file):
        return keys

    with open(output_file, "r", encoding="utf-8") as existing_file:
        for line in existing_file:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            metadata = record.get("metadata", {})
            keys.add(
                (
                    metadata.get("algo_version"),
                    metadata.get("source", "QUOTEX"),
                    metadata.get("symbol"),
                    metadata.get("timestamp"),
                )
            )

    return keys


def process_asset(
    candles: List[Dict[str, float]],
    asset: str,
    existing_keys: Set[Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]],
    out_file,
) -> int:
    """Compute signals and append rows for one asset candle collection."""
    if len(candles) < WARMUP_CANDLES + 2:
        logger.warning("Skipping %s: not enough candles (%s)", asset, len(candles))
        return 0

    df = pd.DataFrame(candles)
    df["symbol"] = asset
    df = calculate_indicators(df)

    generated = 0

    for index in range(WARMUP_CANDLES, len(df) - 1):
        row = df.iloc[index]
        prev_row = df.iloc[index - 1]

        prev_emas = {
            "ema_3": float(prev_row["ema_3"]),
            "ema_5": float(prev_row["ema_5"]),
            "ema_20": float(prev_row["ema_20"]),
        }

        signal = analyze_candle_row(row, prev_row, prev_emas)
        if not signal:
            continue

        outcome_row = df.iloc[index + 1]
        signal["outcome_candle"] = {
            "timestamp": int(outcome_row["from"]),
            "open": float(outcome_row["open"]),
            "high": float(outcome_row["max"]),
            "low": float(outcome_row["min"]),
            "close": float(outcome_row["close"]),
            "volume": float(outcome_row["volume"]),
        }

        dedupe_key = (
            Config.ALGO_VERSION,
            "QUOTEX",
            str(row["symbol"]),
            int(row["from"]),
        )
        if dedupe_key in existing_keys:
            continue

        out_file.write(json.dumps(signal, cls=NumpyEncoder) + "\n")
        existing_keys.add(dedupe_key)
        generated += 1

    return generated


async def run() -> None:
    """Async dataset generation flow for Quotex."""
    args = parse_args()

    start_dt = parse_date(args.start_date)
    end_dt = parse_date(args.end_date, end_of_day=True) if args.end_date else datetime.now()

    if start_dt >= end_dt:
        raise ValueError("start-date must be earlier than end-date")

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    existing_keys = load_existing_keys(OUTPUT_FILE)

    client = await connect_quotex()
    assets = resolve_assets()
    if not assets:
        raise ValueError("No assets configured for Quotex")

    total_generated = 0
    subscribed_assets: List[str] = []
    try:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as out_file:
            for asset in assets:
                resolved_asset = await resolve_quotex_asset_name(client, asset)
                logger.info("Processing Quotex asset %s (resolved=%s)", asset, resolved_asset)
                await subscribe_asset_stream(client, resolved_asset)
                subscribed_assets.append(resolved_asset)
                candles = await fetch_historical_data(client, resolved_asset, start_ts, end_ts)
                generated = process_asset(candles, asset, existing_keys, out_file)
                logger.info("Generated %s signals for %s", generated, asset)
                total_generated += generated
    finally:
        for asset in subscribed_assets:
            try:
                client.stop_candles_stream(asset)
            except Exception:
                continue
        await client.close()

    logger.info("Finished Quotex dataset generation. New rows: %s", total_generated)
    logger.info("Output file: %s", os.path.abspath(OUTPUT_FILE))


def main() -> None:
    """Entrypoint for Quotex historical dataset generation."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
