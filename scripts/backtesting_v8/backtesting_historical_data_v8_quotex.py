"""Backtesting Historical Data V8 (Quotex).

Entrypoint orchestrator:
- Reads environment configuration.
- Connects to Quotex once.
- Builds historical dataframes per instrument.
- Runs V8 signal logic.
- Appends JSONL output.
- Optionally generates charts from processed dataframes.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPTS_ROOT = os.path.join(PROJECT_ROOT, "scripts")
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
if SCRIPTS_ROOT not in sys.path:
    sys.path.append(SCRIPTS_ROOT)

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
from src.utils.charting import generate_chart_base64
from src.utils.indicators import calculate_bollinger_bands, calculate_ema, calculate_rsi
from backtesting_v8.candle_orchestrator import build_historical_dataframe
from utils.quotex_auth import get_connected_client


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
    logging.getLogger("pyquotex.ws.client").setLevel(logging.WARNING)
    return logging.getLogger("BacktestingV8Quotex")


logger = setup_logging()


def parse_bool(value: str, default: bool = False) -> bool:
    """Parse environment booleans."""
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_assets() -> List[str]:
    """Resolve target assets from env/config."""
    env_assets = os.getenv("QUOTEX_BACKTEST_ASSETS", "").strip()
    if env_assets:
        return [asset.strip() for asset in env_assets.split(",") if asset.strip()]

    assets = [asset.strip() for asset in Config.QUOTEX.assets if asset.strip()]
    if assets:
        return assets

    return [asset.strip() for asset in Config.TARGET_ASSETS if asset.strip()]


def load_runtime_config() -> dict:
    """Load backtesting runtime config from environment."""
    load_dotenv()

    return {
        "output_file": os.getenv(
            "QUOTEX_BACKTEST_OUTPUT_FILE",
            "data/trading_signals_dataset_v8_quotex.jsonl",
        ).strip()
        or "data/trading_signals_dataset_v8_quotex.jsonl",
        "period": max(int(os.getenv("QUOTEX_BACKTEST_PERIOD", "60")), 1),
        "start_timestamp": Config.QUOTEX_BACKTEST_START_TIMESTAMP,
        "end_timestamp": Config.QUOTEX_BACKTEST_END_TIMESTAMP,
        "delay_seconds": max(float(os.getenv("QUOTEX_BACKTEST_DELAY_SECONDS", "0.35")), 0.0),
        "generate_charts": Config.QUOTEX_GENERATE_CHARTS,
        "chart_lookback": max(int(os.getenv("CHART_LOOKBACK", "40")), 10),
        "account_mode": (os.getenv("QUOTEX_HISTORY_ACCOUNT_MODE", "PRACTICE").strip().upper() or "PRACTICE"),
        "email": os.getenv("QUOTEX_EMAIL", "").strip(),
        "password": os.getenv("QUOTEX_PASSWORD", "").strip(),
        "ssid": os.getenv("QUOTEX_SSID", "").strip(),
    }


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


def prepare_dataframe_for_strategy(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Map orchestrator dataframe schema to V8 strategy schema."""
    if df.empty:
        return pd.DataFrame(columns=["from", "open", "max", "min", "close", "volume", "symbol"])

    mapped = df.rename(
        columns={
            "time": "from",
            "high": "max",
            "low": "min",
        }
    ).copy()
    mapped["symbol"] = symbol
    return mapped[["from", "open", "max", "min", "close", "volume", "symbol"]]


def process_asset_dataframe(
    strategy_df: pd.DataFrame,
    existing_keys: Set[Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]],
    out_file,
) -> int:
    """Run V8 signal generation for one symbol dataframe and append JSONL."""
    warmup_candles = 100
    if len(strategy_df) < warmup_candles + 2:
        logger.warning("Skipping %s: not enough candles (%s)", strategy_df["symbol"].iloc[0], len(strategy_df))
        return 0

    df = calculate_indicators(strategy_df.copy())
    generated = 0

    for index in range(warmup_candles, len(df) - 1):
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


def maybe_generate_chart(df: pd.DataFrame, symbol: str, chart_lookback: int) -> None:
    """Generate optional chart from already processed dataframe."""
    if df.empty:
        return

    charts_dir = os.path.join("logs", "backtesting_v8_charts")
    os.makedirs(charts_dir, exist_ok=True)

    chart_df = df[["time", "open", "high", "low", "close", "volume"]].rename(
        columns={"time": "timestamp"}
    )
    lookback = min(max(chart_lookback, 10), len(chart_df))
    if lookback < 10:
        return

    chart_base64 = generate_chart_base64(
        chart_df,
        lookback,
        title=f"Backtesting QX:{symbol}",
        show_emas=False,
    )
    output_file = os.path.join(charts_dir, f"{symbol}_{int(datetime.now().timestamp())}.png")
    with open(output_file, "wb") as chart_file:
        chart_file.write(base64.b64decode(chart_base64))

    logger.info("Chart generated for %s: %s", symbol, output_file)


async def run() -> None:
    """Backtesting entrypoint using single connected client and injected dependencies."""
    cfg = load_runtime_config()

    assets = resolve_assets()
    if not assets:
        raise ValueError("No assets configured for Quotex backtesting")

    os.makedirs(os.path.dirname(cfg["output_file"]), exist_ok=True)
    existing_keys = load_existing_keys(cfg["output_file"])

    client = None
    try:
        client = await get_connected_client(
            email=cfg["email"],
            password=cfg["password"],
            ssid=cfg["ssid"],
            account_mode=cfg["account_mode"],
        )

        logger.info(
            "Inicio backtesting Quotex | assets=%s | rango=[%s..%s] | period=%s | charts=%s",
            len(assets),
            cfg["start_timestamp"],
            cfg["end_timestamp"],
            cfg["period"],
            cfg["generate_charts"],
        )

        total_generated = 0
        with open(cfg["output_file"], "a", encoding="utf-8") as out_file:
            for asset in assets:
                try:
                    try:
                        resolved_asset, _ = await client.get_available_asset(asset, force_open=True)
                    except Exception:
                        resolved_asset = asset

                    resolved_asset = str(resolved_asset or asset)
                    logger.info(
                        "Building history for asset=%s resolved=%s start=%s end=%s delay=%s",
                        asset,
                        resolved_asset,
                        cfg["start_timestamp"],
                        cfg["end_timestamp"],
                        cfg["delay_seconds"],
                    )

                    history_df = await build_historical_dataframe(
                        client=client,
                        asset=resolved_asset,
                        period=cfg["period"],
                        start_timestamp=cfg["start_timestamp"],
                        end_timestamp=cfg["end_timestamp"],
                        delay_seconds=cfg["delay_seconds"],
                    )

                    strategy_df = prepare_dataframe_for_strategy(history_df, asset)
                    if strategy_df.empty:
                        logger.warning("Skipping %s: empty historical dataframe", asset)
                        continue

                    generated = process_asset_dataframe(strategy_df, existing_keys, out_file)
                    total_generated += generated
                    logger.info(
                        "Resumen %s | velas=%s | señales_nuevas=%s",
                        asset,
                        len(strategy_df),
                        generated,
                    )

                    if cfg["generate_charts"]:
                        maybe_generate_chart(history_df, asset, cfg["chart_lookback"])
                    else:
                        logger.info("Chart deshabilitado para %s (QUOTEX_GENERATE_CHARTS=false)", asset)
                except Exception as e:
                    logger.error(f"Fallo crítico al procesar el activo {asset}: {e}")
                    continue

        logger.info("Finished Quotex dataset generation. New rows: %s", total_generated)
        logger.info("Output file: %s", os.path.abspath(cfg["output_file"]))
    finally:
        if client is not None:
            await client.close()


def main() -> None:
    """Entrypoint for Quotex historical dataset generation."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
