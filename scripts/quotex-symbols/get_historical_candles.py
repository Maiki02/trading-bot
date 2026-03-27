"""Fetch historical Quotex candles for one symbol configured in .env.

This utility is intentionally minimal and split into two clear steps:
1. login_to_quotex()
2. fetch_historical_candles(symbol, candles_count)

It writes the raw response to a JSON file for inspection.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import pandas as pd
from pyquotex.stable_api import Quotex

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.connection_service import CandleData
from src.utils.charting import generate_chart_base64


@dataclass(frozen=True)
class ScriptConfig:
    """Configuration loaded from environment variables."""

    email: str
    password: str
    auth_method: str
    ssid: str
    ws_debug: bool
    account_mode: str
    symbol: str
    candles_count: int
    output_dir: str
    request_timeout_seconds: int
    chart_lookback: int
    session_file: Path


def _parse_bool(value: str, default: bool = False) -> bool:
    """Convert common string booleans to a Python bool."""

    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> ScriptConfig:
    """Load script configuration from .env."""

    load_dotenv()

    candles_count_raw = os.getenv("QUOTEX_HISTORY_CANDLES", "150").strip()
    candles_count = int(candles_count_raw) if candles_count_raw else 150

    return ScriptConfig(
        email=os.getenv("QUOTEX_EMAIL", "").strip(),
        password=os.getenv("QUOTEX_PASSWORD", "").strip(),
        auth_method=os.getenv("QUOTEX_AUTH_METHOD", "CREDENTIALS").strip().upper(),
        ssid=os.getenv("QUOTEX_SSID", "").strip(),
        ws_debug=_parse_bool(os.getenv("QUOTEX_WS_DEBUG", "false"), default=False),
        account_mode=os.getenv("QUOTEX_HISTORY_ACCOUNT_MODE", "PRACTICE").strip().upper() or "PRACTICE",
        symbol=os.getenv("QUOTEX_HISTORY_SYMBOL", "").strip(),
        candles_count=max(candles_count, 1),
        output_dir=os.getenv("QUOTEX_HISTORY_OUTPUT_DIR", "data/quotex-history").strip() or "data/quotex-history",
        request_timeout_seconds=int(os.getenv("QUOTEX_REQUEST_TIMEOUT", "20")),
        chart_lookback=max(int(os.getenv("CHART_LOOKBACK", "40")), 10),
        session_file=PROJECT_ROOT / "session.json",
    )


def load_persisted_session(config: ScriptConfig) -> dict[str, str] | None:
    """Load a previously saved pyquotex session for the current account."""

    if not config.session_file.exists() or not config.email:
        return None

    try:
        session_payload = json.loads(config.session_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    entry = session_payload.get(config.email)
    if not isinstance(entry, dict):
        return None

    user_agent = str(entry.get("user_agent") or "").strip()
    cookies = str(entry.get("cookies") or "").strip()
    token = str(entry.get("token") or "").strip()
    if not user_agent or not token:
        return None

    return {
        "user_agent": user_agent,
        "cookies": cookies,
        "token": token,
    }


def map_raw_candle_to_candle_data(raw_candle: dict[str, Any], symbol: str) -> CandleData:
    """Normalize a pyquotex OHLC candle to the project's CandleData model."""

    return CandleData(
        timestamp=int(raw_candle["time"]),
        open=float(raw_candle["open"]),
        high=float(raw_candle["high"]),
        low=float(raw_candle["low"]),
        close=float(raw_candle["close"]),
        volume=float(raw_candle.get("ticks", 0)),
        source="QX",
        symbol=symbol,
    )


def candles_to_dataframe(candles: list[CandleData]) -> pd.DataFrame:
    """Convert normalized candles to the dataframe shape expected by charting."""

    records = [
        {
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in candles
    ]
    return pd.DataFrame.from_records(records)


async def login_to_quotex(config: ScriptConfig) -> Quotex:
    """Authenticate and return a connected Quotex client."""

    persisted_session = load_persisted_session(config)

    if config.auth_method == "CREDENTIALS":
        if not config.email or not config.password:
            raise ValueError("Missing QUOTEX_EMAIL or QUOTEX_PASSWORD in .env")
        client = Quotex(email=config.email, password=config.password, lang="en")
        if persisted_session:
            client.session_data = {
                "user_agent": persisted_session["user_agent"],
                "cookies": persisted_session["cookies"] or None,
                "token": persisted_session["token"],
            }
            print("session_bootstrap: loaded persisted session from session.json")
    else:
        if not config.ssid:
            raise ValueError("Missing QUOTEX_SSID in .env for SESSION auth")
        client = Quotex(email="SESSION_AUTH", password="SESSION_AUTH", lang="en")
        client.session_data = {
            "user_agent": "Quotex/1.0",
            "cookies": None,
            "token": config.ssid,
        }

    client.debug_ws_enable = config.ws_debug
    client.set_account_mode(config.account_mode)

    check_connect, message = await client.connect()
    print(f"connect: success={check_connect} message={message}")
    if not check_connect:
        raise RuntimeError(f"Connection failed: {message}")

    if "Token Rejected" in str(message):
        print("connect_warning: token rejected reported, forcing reauthentication")
        await client.reconnect()
        check_connect, message = await client.connect()
        print(f"connect_retry: success={check_connect} message={message}")
        if not check_connect:
            raise RuntimeError(f"Connection retry failed: {message}")

    await client.change_account(config.account_mode)
    print(f"account_mode: {config.account_mode}")
    return client


async def resolve_symbol(client: Quotex, requested_symbol: str, timeout_seconds: int) -> str:
    """Resolve the exact asset name through pyquotex without auto-fallback to OTC."""

    asset_name, asset_data = await asyncio.wait_for(
        client.get_available_asset(requested_symbol, force_open=False),
        timeout=timeout_seconds,
    )
    is_open = bool(asset_data and len(asset_data) > 2 and asset_data[2])
    print(f"asset_resolution: requested={requested_symbol} resolved={asset_name} is_open={is_open}")
    return asset_name or requested_symbol


async def prepare_historical_context(
    client: Quotex,
    symbol: str,
    request_timeout_seconds: int,
) -> None:
    """Warm up asset metadata and chart settings before historical fetch."""

    await asyncio.wait_for(client.get_all_assets(), timeout=request_timeout_seconds)
    client.api.settings_apply(symbol, 60)
    await asyncio.sleep(1.0)
    print(f"historical_context_ready: symbol={symbol} period=60")


async def fetch_historical_candles_v2(
    client: Quotex,
    symbol: str,
    candles_count: int,
    request_timeout_seconds: int,
) -> list[dict[str, Any]]:
    """Fetch candles using the stream-backed history/list/v2 path."""

    period = 60
    print(f"historical_request_v2: symbol={symbol} candles={candles_count} period={period}")
    candles = await asyncio.wait_for(
        client.get_candle_v2(symbol, period),
        timeout=request_timeout_seconds,
    )
    return (candles or [])[-candles_count:]


async def fetch_historical_candles_legacy(
    client: Quotex,
    symbol: str,
    candles_count: int,
    request_timeout_seconds: int,
) -> list[dict[str, Any]]:
    """Fetch candles using the documented get_candles API."""

    period = 60
    end_from_time = datetime.now(timezone.utc).timestamp()
    offset = candles_count * period

    print(
        f"historical_request_legacy: symbol={symbol} candles={candles_count} "
        f"period={period} offset={offset}"
    )

    candles = await asyncio.wait_for(
        client.get_candles(
            asset=symbol,
            end_from_time=end_from_time,
            offset=offset,
            period=period,
        ),
        timeout=request_timeout_seconds,
    )
    return candles or []


async def fetch_historical_candles(
    client: Quotex,
    symbol: str,
    candles_count: int,
    request_timeout_seconds: int,
) -> tuple[list[dict[str, Any]], str, str]:
    """Fetch historical candles using the first working pyquotex method."""

    if not symbol:
        raise ValueError("Missing QUOTEX_HISTORY_SYMBOL in .env")

    resolved_symbol = await resolve_symbol(client, symbol, request_timeout_seconds)
    await prepare_historical_context(client, resolved_symbol, request_timeout_seconds)
    attempts = [
        ("get_candle_v2", fetch_historical_candles_v2),
        ("get_candles", fetch_historical_candles_legacy),
    ]
    errors: list[str] = []

    for method_name, method in attempts:
        try:
            candles = await method(
                client,
                resolved_symbol,
                candles_count,
                request_timeout_seconds,
            )
            if candles:
                print(f"historical_method_selected: {method_name}")
                return candles, method_name, resolved_symbol

            errors.append(f"{method_name}: empty response")
            print(f"historical_method_empty: {method_name}")
        except asyncio.TimeoutError:
            message = (
                f"{method_name}: timed out after {request_timeout_seconds}s "
                f"for symbol={resolved_symbol}"
            )
            errors.append(message)
            print(f"historical_method_timeout: {message}")
        except Exception as exc:
            message = f"{method_name}: {exc}"
            errors.append(message)
            print(f"historical_method_error: {message}")

    raise RuntimeError("Historical fetch failed. " + " | ".join(errors))


def write_output(
    output_dir: Path,
    symbol: str,
    method_name: str,
    raw_candles: list[dict[str, Any]],
    normalized_candles: list[CandleData],
    chart_lookback: int,
) -> tuple[Path, Path, Path]:
    """Persist raw candles, normalized candles, and a chart image to disk."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_symbol = symbol.replace("/", "_")
    raw_output_path = output_dir / f"historical_raw_{safe_symbol}_{timestamp}.json"
    normalized_output_path = output_dir / f"historical_candle_data_{safe_symbol}_{timestamp}.json"
    chart_output_path = output_dir / f"historical_chart_{safe_symbol}_{timestamp}.png"

    raw_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "method": method_name,
        "count": len(raw_candles),
        "candles": raw_candles,
    }
    raw_output_path.write_text(json.dumps(raw_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    normalized_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "method": method_name,
        "count": len(normalized_candles),
        "candles": [
            {
                "timestamp": candle.timestamp,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "source": candle.source,
                "symbol": candle.symbol,
            }
            for candle in normalized_candles
        ],
    }
    normalized_output_path.write_text(
        json.dumps(normalized_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    dataframe = candles_to_dataframe(normalized_candles)
    lookback = min(max(chart_lookback, 10), len(dataframe))
    if lookback < 10:
        raise ValueError("At least 10 candles are required to generate a chart image")

    chart_base64 = generate_chart_base64(
        dataframe,
        lookback,
        title=f"QX:{symbol} - Historical {method_name}",
        show_emas=False,
    )
    chart_output_path.write_bytes(base64.b64decode(chart_base64))

    return raw_output_path, normalized_output_path, chart_output_path


async def run() -> int:
    """Main async execution."""

    config = load_config()
    client: Quotex | None = None

    try:
        client = await login_to_quotex(config)
        raw_candles, method_name, resolved_symbol = await fetch_historical_candles(
            client,
            symbol=config.symbol,
            candles_count=config.candles_count,
            request_timeout_seconds=config.request_timeout_seconds,
        )

        normalized_candles = [
            map_raw_candle_to_candle_data(raw_candle, resolved_symbol)
            for raw_candle in raw_candles
        ]

        raw_output_path, normalized_output_path, chart_output_path = write_output(
            Path(config.output_dir),
            resolved_symbol,
            method_name,
            raw_candles,
            normalized_candles,
            config.chart_lookback,
        )
        print(f"candles_found: {len(raw_candles)}")
        print(f"resolved_symbol: {resolved_symbol}")
        print(f"historical_method_used: {method_name}")
        print(f"raw_output_file: {raw_output_path}")
        print(f"candle_data_output_file: {normalized_output_path}")
        print(f"chart_output_file: {chart_output_path}")
        if normalized_candles:
            print(f"first_candle: {normalized_candles[0]}")
            print(f"last_candle: {normalized_candles[-1]}")
        return 0
    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    except Exception as exc:
        print(f"error: {exc}")
        return 1
    finally:
        if client is not None:
            await client.close()


def main() -> None:
    """Entrypoint."""

    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()