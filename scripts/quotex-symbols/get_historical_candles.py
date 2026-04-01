"""Fetch historical Quotex candles for one symbol configured in .env.

This utility authenticates with the installed pyquotex library and retrieves
historical candles through the official ``get_candles`` API.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import pandas as pd

DEFAULT_HISTORY_SYMBOL = "USDJPY"

# Repository root (trading-bot). Used only for local imports and session.json path.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.utils.quotex_bootstrap import Quotex

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
    session_strategy: str
    connect_retries: int
    connect_retry_delay_seconds: float


@dataclass(frozen=True)
class ConnectionResult:
    """Connected client and diagnostics about connection strategy/phase."""

    client: Quotex
    auth_method: str
    strategy_requested: str
    effective_phase: str
    attempts: list[dict[str, Any]]


@dataclass(frozen=True)
class FetchResult:
    """Raw response details from historical data request."""

    method_used: str
    resolved_symbol: str
    end_from_time: int
    offset: int
    period: int
    request_metadata: dict[str, Any]
    payload: Any
    diagnostics: dict[str, Any]
    timed_out: bool
    error_message: str | None
    error_category: str | None


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
    session_strategy = os.getenv("QUOTEX_SESSION_STRATEGY", "AUTO").strip().upper() or "AUTO"
    if session_strategy not in {"AUTO", "PERSISTED_ONLY", "FRESH_ONLY"}:
        raise ValueError(
            "Invalid QUOTEX_SESSION_STRATEGY. Use AUTO, PERSISTED_ONLY, or FRESH_ONLY"
        )
    return ScriptConfig(
        email=os.getenv("QUOTEX_EMAIL", "").strip(),
        password=os.getenv("QUOTEX_PASSWORD", "").strip(),
        auth_method=os.getenv("QUOTEX_AUTH_METHOD", "CREDENTIALS").strip().upper(),
        ssid=os.getenv("QUOTEX_SSID", "").strip(),
        ws_debug=_parse_bool(os.getenv("QUOTEX_WS_DEBUG", "false"), default=False),
        account_mode=os.getenv("QUOTEX_HISTORY_ACCOUNT_MODE", "PRACTICE").strip().upper() or "PRACTICE",
        symbol=os.getenv("QUOTEX_HISTORY_SYMBOL", DEFAULT_HISTORY_SYMBOL).strip() or DEFAULT_HISTORY_SYMBOL,
        candles_count=max(candles_count, 1),
        output_dir=os.getenv("QUOTEX_HISTORY_OUTPUT_DIR", "data/quotex-history").strip() or "data/quotex-history",
        request_timeout_seconds=max(int(os.getenv("QUOTEX_REQUEST_TIMEOUT", "20")), 1),
        chart_lookback=max(int(os.getenv("CHART_LOOKBACK", "40")), 10),
        session_file=REPO_ROOT / "session.json",
        session_strategy=session_strategy,
        connect_retries=max(int(os.getenv("QUOTEX_CONNECT_RETRIES", "3")), 1),
        connect_retry_delay_seconds=max(
            float(os.getenv("QUOTEX_CONNECT_RETRY_DELAY_SECONDS", "2")),
            0.1,
        ),
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
    """Backward-compatible login wrapper that returns a connected client."""

    connection_result = await connect_with_session_strategy(config)
    return connection_result.client


def classify_connection_failure(message: str) -> str:
    """Classify connection failures into actionable categories."""

    lowered = message.lower()
    auth_markers = (
        "token rejected",
        "token",
        "auth",
        "unauthorized",
        "forbidden",
        "ssid",
        "session",
        "cookie",
    )
    if any(marker in lowered for marker in auth_markers):
        return "AUTH_SESSION_ERROR"
    if "timeout" in lowered or "timed out" in lowered:
        return "CONNECTION_TIMEOUT"
    return "CONNECTION_ERROR"


def build_credentials_client(
    config: ScriptConfig,
    phase: str,
    persisted_session: dict[str, str] | None,
) -> Quotex:
    """Build a Quotex client for credentials auth in persisted/fresh phases."""

    if not config.email or not config.password:
        raise ValueError("Missing QUOTEX_EMAIL or QUOTEX_PASSWORD in .env")

    client = Quotex(email=config.email, password=config.password, lang="en")

    if phase == "persisted":
        if not persisted_session:
            raise ValueError(
                "No persisted session available in session.json for PERSISTED_ONLY strategy"
            )
        client.session_data = {
            "user_agent": persisted_session["user_agent"],
            "cookies": persisted_session["cookies"] or None,
            "token": persisted_session["token"],
        }

    client.debug_ws_enable = config.ws_debug
    client.set_account_mode(config.account_mode)
    return client


def build_session_token_client(config: ScriptConfig) -> Quotex:
    """Build a Quotex client for SESSION auth with explicit SSID token."""

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
    return client


async def try_connect_phase(
    config: ScriptConfig,
    phase: str,
    persisted_session: dict[str, str] | None,
) -> tuple[Quotex | None, list[dict[str, Any]], str | None]:
    """Try to connect using one phase with retries and short backoff."""

    attempts: list[dict[str, Any]] = []

    for attempt in range(1, config.connect_retries + 1):
        client: Quotex | None = None
        try:
            if config.auth_method == "CREDENTIALS":
                client = build_credentials_client(config, phase, persisted_session)
            else:
                client = build_session_token_client(config)

            success, message = await client.connect()
            message_text = str(message)
            category = classify_connection_failure(message_text)
            token_rejected = "token rejected" in message_text.lower()

            attempts.append(
                {
                    "phase": phase,
                    "attempt": attempt,
                    "success": bool(success and not token_rejected),
                    "message": message_text,
                    "category": category if (not success or token_rejected) else None,
                }
            )

            if success and not token_rejected:
                await client.change_account(config.account_mode)
                assets_map = await client.get_all_assets()
                print(
                    f"connect_phase_ok: phase={phase} attempts={attempt} "
                    f"account_mode={config.account_mode} assets={len(assets_map)}"
                )
                return client, attempts, None

            if client is not None:
                await client.close()

            if attempt < config.connect_retries:
                delay = config.connect_retry_delay_seconds * (2 ** (attempt - 1))
                await asyncio.sleep(delay)
        except Exception as exc:
            error_message = str(exc)
            attempts.append(
                {
                    "phase": phase,
                    "attempt": attempt,
                    "success": False,
                    "message": error_message,
                    "category": classify_connection_failure(error_message),
                }
            )
            if client is not None:
                await client.close()

            if attempt < config.connect_retries:
                delay = config.connect_retry_delay_seconds * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

    last_message = attempts[-1]["message"] if attempts else "unknown connection failure"
    return None, attempts, str(last_message)


def build_connection_phases(config: ScriptConfig, has_persisted_session: bool) -> list[str]:
    """Resolve connection phases according to env strategy and auth mode."""

    if config.auth_method != "CREDENTIALS":
        return ["session_token"]

    if config.session_strategy == "FRESH_ONLY":
        return ["fresh"]
    if config.session_strategy == "PERSISTED_ONLY":
        return ["persisted"]

    phases: list[str] = []
    if has_persisted_session:
        phases.append("persisted")
    phases.append("fresh")
    return phases


async def connect_with_session_strategy(config: ScriptConfig) -> ConnectionResult:
    """Connect to Quotex using layered session strategy with retries."""

    persisted_session = load_persisted_session(config)
    phases = build_connection_phases(config, has_persisted_session=persisted_session is not None)

    print(
        "connect_strategy: "
        f"auth_method={config.auth_method} strategy={config.session_strategy} "
        f"phases={phases} retries={config.connect_retries} "
        f"retry_delay_seconds={config.connect_retry_delay_seconds}"
    )

    all_attempts: list[dict[str, Any]] = []

    for phase in phases:
        client, attempts, phase_error = await try_connect_phase(
            config,
            phase=phase,
            persisted_session=persisted_session,
        )
        all_attempts.extend(attempts)

        if client is not None:
            return ConnectionResult(
                client=client,
                auth_method=config.auth_method,
                strategy_requested=config.session_strategy,
                effective_phase=phase,
                attempts=all_attempts,
            )

        print(f"connect_phase_failed: phase={phase} error={phase_error}")

    if not all_attempts:
        raise RuntimeError("AUTH_SESSION_ERROR: no connection phase could be executed")

    last_attempt = all_attempts[-1]
    last_message = str(last_attempt.get("message", "unknown connection failure"))
    last_category = str(last_attempt.get("category") or "CONNECTION_ERROR")
    raise RuntimeError(f"{last_category}: {last_message}")


def summarize_payload(payload: Any) -> dict[str, Any]:
    """Create a compact, printable summary for raw API payloads."""

    if isinstance(payload, list):
        first_item = payload[0] if payload else None
        last_item = payload[-1] if payload else None
        return {
            "type": "list",
            "count": len(payload),
            "first": first_item,
            "last": last_item,
        }

    if isinstance(payload, dict):
        keys = list(payload.keys())
        candles_data = payload.get("candles")
        data_data = payload.get("data")
        history_data = payload.get("history")
        result_data = payload.get("result")

        selected_list: list[Any] | None = None
        inferred_count = None
        for candidate in (candles_data, data_data, history_data, result_data):
            if isinstance(candidate, list):
                inferred_count = len(candidate)
                selected_list = candidate
                break

        return {
            "type": "dict",
            "keys": keys,
            "inferred_count": inferred_count,
            "first": selected_list[0] if selected_list else None,
            "last": selected_list[-1] if selected_list else None,
        }

    return {
        "type": type(payload).__name__,
        "value": payload,
    }


def build_payload_summary(payload: Any) -> dict[str, Any]:
    """Build compact diagnostics summary for API payloads."""

    return summarize_payload(payload)


def normalize_history_payload(payload: Any) -> list[dict[str, Any]]:
    """Normalize history payload and keep only robust OHLC entries."""

    candidates: list[Any] = []

    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        for key in (
            "aggregated_ohlc",
            "candles",
            "data",
            "history",
            "result",
            "list",
            "items",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
        if not candidates and all(
            field in payload for field in ("time", "open", "high", "low", "close")
        ):
            candidates = [payload]

    if not candidates:
        return []

    normalized: list[dict[str, Any]] = []
    required_fields = ("time", "open", "high", "low", "close")
    timestamp_aliases = ("time", "timestamp", "at", "t")

    for item in candidates:
        if not isinstance(item, dict):
            continue

        resolved_time: Any = None
        for key in timestamp_aliases:
            if key in item:
                resolved_time = item[key]
                break

        candle_source = dict(item)
        if resolved_time is not None:
            candle_source["time"] = resolved_time

        if not all(field in candle_source for field in required_fields):
            continue

        try:
            candle: dict[str, Any] = {
                "time": int(candle_source["time"]),
                "open": float(candle_source["open"]),
                "high": float(candle_source["high"]),
                "low": float(candle_source["low"]),
                "close": float(candle_source["close"]),
                "ticks": float(candle_source.get("ticks", candle_source.get("volume", 0))),
            }
        except (TypeError, ValueError):
            continue

        normalized.append(candle)

    return normalized


async def fetch_candles_via_get_candles(
    client: Quotex,
    config: ScriptConfig,
) -> FetchResult:
    """Fetch historical candles using client.get_candles() official API."""

    period = 60
    end_from_time = int(time.time())
    offset = config.candles_count * period
    resolved_symbol = config.symbol or "UNKNOWN"
    method_used = "GET_CANDLES_API"

    diagnostics: dict[str, Any] = {}
    request_metadata: dict[str, Any] = {
        "period": period,
        "end_from_time": end_from_time,
        "offset": offset,
        "timeout_seconds": config.request_timeout_seconds,
    }

    try:
        asset_name, asset_data = await asyncio.wait_for(
            client.get_available_asset(config.symbol, force_open=True),
            timeout=config.request_timeout_seconds,
        )
        resolved_symbol = asset_name or config.symbol or "UNKNOWN"
        is_open = bool(asset_data and len(asset_data) > 2 and asset_data[2])
        diagnostics["asset_name"] = resolved_symbol
        diagnostics["asset_is_open"] = is_open

        print(
            f"asset_resolved: requested={config.symbol} resolved={resolved_symbol} is_open={is_open}"
        )

        if not is_open:
            print(f"asset_warning: {resolved_symbol} is currently closed, continuing anyway")

        print(
            f"historical_request: symbol={resolved_symbol} candles={config.candles_count} "
            f"period={period} offset={offset} method={method_used}"
        )

        candles = await asyncio.wait_for(
            client.get_candles(resolved_symbol, end_from_time, offset, period),
            timeout=config.request_timeout_seconds,
        )

        if not candles:
            return FetchResult(
                method_used=method_used,
                resolved_symbol=resolved_symbol,
                end_from_time=end_from_time,
                offset=offset,
                period=period,
                request_metadata=request_metadata,
                payload=candles,
                diagnostics=diagnostics,
                timed_out=False,
                error_message="get_candles returned empty or None response",
                error_category="GET_CANDLES_EMPTY",
            )

        return FetchResult(
            method_used=method_used,
            resolved_symbol=resolved_symbol,
            end_from_time=end_from_time,
            offset=offset,
            period=period,
            request_metadata=request_metadata,
            payload=candles,
            diagnostics=diagnostics,
            timed_out=False,
            error_message=None,
            error_category=None,
        )
    except asyncio.TimeoutError:
        return FetchResult(
            method_used=method_used,
            resolved_symbol=resolved_symbol,
            end_from_time=end_from_time,
            offset=offset,
            period=period,
            request_metadata=request_metadata,
            payload=None,
            diagnostics=diagnostics,
            timed_out=True,
            error_message=f"get_candles timed out after {config.request_timeout_seconds} seconds",
            error_category="GET_CANDLES_TIMEOUT",
        )
    except Exception as exc:
        return FetchResult(
            method_used=method_used,
            resolved_symbol=resolved_symbol,
            end_from_time=end_from_time,
            offset=offset,
            period=period,
            request_metadata=request_metadata,
            payload=None,
            diagnostics=diagnostics,
            timed_out=False,
            error_message=f"get_candles failed: {str(exc)}",
            error_category="GET_CANDLES_ERROR",
        )


def build_attempt_diagnostics(fetch_result: FetchResult, normalized_count: int) -> dict[str, Any]:
    """Build compact diagnostics for one historical method attempt."""

    return {
        "method": fetch_result.method_used,
        "timed_out": fetch_result.timed_out,
        "error": fetch_result.error_message,
        "error_category": fetch_result.error_category,
        "normalized_ohlc_count": normalized_count,
        "request_metadata": fetch_result.request_metadata,
        "diagnostics_summary": summarize_payload(fetch_result.diagnostics),
        "payload_summary": summarize_payload(fetch_result.payload),
    }


def write_api_raw_output(
    output_dir: Path,
    fetch_result: FetchResult,
    requested_symbol: str,
    connection_result: ConnectionResult,
    method_requested: str,
    method_attempts: list[dict[str, Any]],
) -> Path:
    """Persist raw diagnostics payload for analysis."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_symbol = fetch_result.resolved_symbol.replace("/", "_")
    output_path = output_dir / f"historical_api_raw_{safe_symbol}_{timestamp}.json"

    payload_summary = build_payload_summary(fetch_result.payload)
    api_raw_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_symbol": requested_symbol,
        "resolved_symbol": fetch_result.resolved_symbol,
        "method_requested": method_requested,
        "method_used": fetch_result.method_used,
        "method_attempts": method_attempts,
        "connection": {
            "auth_method": connection_result.auth_method,
            "strategy_requested": connection_result.strategy_requested,
            "effective_phase": connection_result.effective_phase,
            "attempts": connection_result.attempts,
        },
        "request": {
            "period": fetch_result.period,
            "end_from_time": fetch_result.end_from_time,
            "offset": fetch_result.offset,
        },
        "request_metadata": fetch_result.request_metadata,
        "timed_out": fetch_result.timed_out,
        "error": fetch_result.error_message,
        "error_category": fetch_result.error_category,
        "diagnostics": fetch_result.diagnostics,
        "payload_summary": payload_summary,
        "payload": fetch_result.payload,
    }
    output_path.write_text(
        json.dumps(api_raw_payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return output_path


def write_ohlc_outputs(
    output_dir: Path,
    symbol: str,
    requested_symbol: str,
    raw_candles: list[dict[str, Any]],
    normalized_candles: list[CandleData],
    chart_lookback: int,
    method_used: str,
) -> tuple[Path, Path, Path]:
    """Persist normalized OHLC outputs and chart image to disk."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_symbol = symbol.replace("/", "_")
    raw_output_path = output_dir / f"historical_raw_{safe_symbol}_{timestamp}.json"
    normalized_output_path = output_dir / f"historical_candle_data_{safe_symbol}_{timestamp}.json"
    chart_output_path = output_dir / f"historical_chart_{safe_symbol}_{timestamp}.png"

    raw_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "method_used": method_used,
        "requested_symbol": requested_symbol,
        "count": len(raw_candles),
        "candles": raw_candles,
    }
    raw_output_path.write_text(json.dumps(raw_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    normalized_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
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
        raise ValueError("At least 10 valid OHLC candles are required to generate a chart image")

    chart_base64 = generate_chart_base64(
        dataframe,
        lookback,
        title=f"QX:{symbol} - Historical candles",
        show_emas=False,
    )
    chart_output_path.write_bytes(base64.b64decode(chart_base64))

    return raw_output_path, normalized_output_path, chart_output_path


async def run() -> int:
    """Main async execution."""

    config = load_config()
    client: Quotex | None = None
    connection_result: ConnectionResult | None = None

    try:
        connection_result = await connect_with_session_strategy(config)
        client = connection_result.client

        fetch_result = await fetch_candles_via_get_candles(client, config)
        raw_candles = normalize_history_payload(fetch_result.payload)
        method_attempts = [build_attempt_diagnostics(fetch_result, len(raw_candles))]

        api_raw_output_path = write_api_raw_output(
            Path(config.output_dir),
            fetch_result,
            config.symbol,
            connection_result,
            "GET_CANDLES_API",
            method_attempts,
        )
        print(f"api_raw_output_file: {api_raw_output_path}")

        if fetch_result.error_message:
            if fetch_result.error_category in {"GET_CANDLES_ERROR", "GET_CANDLES_TIMEOUT"}:
                print(f"error_get_candles: {fetch_result.error_message}")
            else:
                print(f"error_historical_fetch: {fetch_result.error_message}")

        if not raw_candles:
            attempt_errors = [
                f"{attempt['method']}={attempt['error'] or 'INVALID_PAYLOAD'}"
                for attempt in method_attempts
            ]
            attempts_text = " | ".join(attempt_errors) if attempt_errors else "no attempts"
            print(f"error_get_candles_failed: {attempts_text}")
            print("no_ohlc_response: get_candles did not return valid OHLC data")
            return 1

        raw_candles = raw_candles[-config.candles_count :]
        normalized_candles = [
            map_raw_candle_to_candle_data(raw_candle, fetch_result.resolved_symbol)
            for raw_candle in raw_candles
        ]

        raw_output_path, normalized_output_path, chart_output_path = write_ohlc_outputs(
            Path(config.output_dir),
            fetch_result.resolved_symbol,
            config.symbol,
            raw_candles,
            normalized_candles,
            config.chart_lookback,
            fetch_result.method_used,
        )
        print(f"candles_found: {len(raw_candles)}")
        print(f"requested_symbol: {config.symbol or '<empty>'}")
        print(f"resolved_symbol: {fetch_result.resolved_symbol}")
        print(f"historical_method_used: {fetch_result.method_used}")
        print(f"raw_output_file: {raw_output_path}")
        print(f"candle_data_output_file: {normalized_output_path}")
        print(f"chart_output_file: {chart_output_path}")
        return 0
    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    except Exception as exc:
        failure_text = str(exc)
        category = classify_connection_failure(failure_text)
        if category == "AUTH_SESSION_ERROR":
            print(f"error_auth_session: {failure_text}")
        else:
            print(f"error_connection: {failure_text}")
        print("no_ohlc_response: get_candles did not return OHLC data")
        return 1
    finally:
        if client is not None:
            await client.close()


def main() -> None:
    """Entrypoint."""

    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
