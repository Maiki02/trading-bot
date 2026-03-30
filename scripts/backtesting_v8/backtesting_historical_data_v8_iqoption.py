"""
Backtesting Historical Data V8 (IQ Option)
==========================================
Generate a typed JSONL dataset for backtesting candlestick reversal signals.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from iqoptionapi.stable_api import IQ_Option

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


OUTPUT_FILE = "data/trading_signals_dataset_v8_iqoption.jsonl"
CHUNK_SIZE = 1000
CHUNK_DELAY_SECONDS = 0.0
WARMUP_CANDLES = 100


def setup_logging() -> logging.Logger:
    """Configure console and file logging."""
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler("logs/backtesting_v8_iqoption.log", mode="w", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    logging.getLogger("iqoptionapi").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("websocket").setLevel(logging.WARNING)
    return logging.getLogger("BacktestingV8IQ")


logger = setup_logging()


def inject_custom_actives() -> None:
    """Inject custom active mapping to iqoptionapi constants."""
    import iqoptionapi.constants

    if not Config.CUSTOM_ACTIVES:
        return

    injected_count = 0
    for item in Config.CUSTOM_ACTIVES:
        key = item.get("key")
        active_id = item.get("id")
        if key and active_id:
            iqoptionapi.constants.ACTIVES[key] = active_id
            injected_count += 1
    logger.info("Injected custom IQ assets: %s", injected_count)


def connect_iq_option() -> IQ_Option:
    """Connect to IQ Option with credentials from Config."""
    if not Config.IQOPTION.email or not Config.IQOPTION.password:
        raise ValueError("IQ Option credentials are missing in environment variables")

    client = IQ_Option(Config.IQOPTION.email, Config.IQOPTION.password)
    connected, reason = client.connect()
    if not connected:
        raise ConnectionError(f"IQ Option connection failed: {reason}")

    logger.info("Connected to IQ Option")
    return client


def fetch_historical_data(iq: IQ_Option, asset: str, start_ts: int, end_ts: int) -> List[Dict[str, float]]:
    """Fetch historical candles using reverse pagination."""
    all_candles: List[Dict[str, float]] = []
    current_to_ts = end_ts

    while current_to_ts > start_ts:
        candles = iq.get_candles(asset, 60, CHUNK_SIZE, current_to_ts)
        if not candles:
            logger.warning("No candles returned for %s at %s", asset, current_to_ts)
            break

        chunk = [
            candle
            for candle in candles
            if start_ts <= int(candle.get("from", 0)) <= end_ts
        ]

        if chunk:
            all_candles.extend(chunk)

        oldest_ts = min(int(candle["from"]) for candle in candles)
        if oldest_ts >= current_to_ts:
            break

        current_to_ts = oldest_ts - 1
        if CHUNK_DELAY_SECONDS > 0:
            time.sleep(CHUNK_DELAY_SECONDS)

    deduped = {int(candle["from"]): candle for candle in all_candles}
    ordered = sorted(deduped.values(), key=lambda candle: int(candle["from"]))
    logger.info("Fetched %s unique candles for %s", len(ordered), asset)
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
                "source": "IQOPTION",
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
                    metadata.get("source", "IQOPTION"),
                    metadata.get("symbol"),
                    metadata.get("timestamp"),
                )
            )

    return keys


def process_asset(
    iq: IQ_Option,
    asset: str,
    start_ts: int,
    end_ts: int,
    existing_keys: Set[Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]],
    out_file,
) -> int:
    """Fetch, compute signals, and append valid rows for one asset."""
    candles = fetch_historical_data(iq, asset, start_ts, end_ts)
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
            "IQOPTION",
            str(row["symbol"]),
            int(row["from"]),
        )
        if dedupe_key in existing_keys:
            continue

        out_file.write(json.dumps(signal, cls=NumpyEncoder) + "\n")
        existing_keys.add(dedupe_key)
        generated += 1

    return generated


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Generate V8 historical dataset from IQ Option")
    parser.add_argument("--days", type=int, default=30, help="History depth in days")
    return parser.parse_args()


def main() -> None:
    """Entrypoint for IQ Option historical dataset generation."""
    args = parse_args()

    inject_custom_actives()
    iq = connect_iq_option()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)

    start_ts = int(start_date.timestamp())
    end_ts = int(end_date.timestamp())

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    existing_keys = load_existing_keys(OUTPUT_FILE)

    total_generated = 0
    with open(OUTPUT_FILE, "a", encoding="utf-8") as out_file:
        for asset in Config.TARGET_ASSETS:
            symbol = asset.strip()
            if not symbol:
                continue
            logger.info("Processing IQ asset %s", symbol)
            generated = process_asset(iq, symbol, start_ts, end_ts, existing_keys, out_file)
            logger.info("Generated %s signals for %s", generated, symbol)
            total_generated += generated

    logger.info("Finished IQ dataset generation. New rows: %s", total_generated)
    logger.info("Output file: %s", os.path.abspath(OUTPUT_FILE))


if __name__ == "__main__":
    main()
