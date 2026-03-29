"""Fetch historical Quotex candles for one symbol configured in .env.

This utility uses pyquotex connection/login and sends raw websocket events
through library internals to retrieve historical data.
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
from inspect import isawaitable
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pyquotex.stable_api import Quotex

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
    asset_id: int | None
    candles_count: int
    output_dir: str
    request_timeout_seconds: int
    chart_lookback: int
    session_file: Path
    session_strategy: str
    connect_retries: int
    connect_retry_delay_seconds: float
    ws_poll_interval_seconds: float


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
    resolved_asset_id: int | None
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
    asset_id_raw = os.getenv("QUOTEX_HISTORY_ASSET_ID", "").strip()
    asset_id = int(asset_id_raw) if asset_id_raw else None
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
        symbol=os.getenv("QUOTEX_HISTORY_SYMBOL", "").strip(),
        asset_id=asset_id,
        candles_count=max(candles_count, 1),
        output_dir=os.getenv("QUOTEX_HISTORY_OUTPUT_DIR", "data/quotex-history").strip() or "data/quotex-history",
        request_timeout_seconds=max(int(os.getenv("QUOTEX_REQUEST_TIMEOUT", "20")), 1),
        chart_lookback=max(int(os.getenv("CHART_LOOKBACK", "40")), 10),
        session_file=PROJECT_ROOT / "session.json",
        session_strategy=session_strategy,
        connect_retries=max(int(os.getenv("QUOTEX_CONNECT_RETRIES", "3")), 1),
        connect_retry_delay_seconds=max(
            float(os.getenv("QUOTEX_CONNECT_RETRY_DELAY_SECONDS", "2")),
            0.1,
        ),
        ws_poll_interval_seconds=max(float(os.getenv("QUOTEX_WS_POLL_INTERVAL_SECONDS", "0.2")), 0.05),
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
        print("session_bootstrap: loaded persisted session from session.json")
    elif phase == "fresh":
        # Fresh mode intentionally avoids bootstrap to force new browser-like cookies/headers.
        print("session_bootstrap: skipped (fresh credentials login)")

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

            print(
                f"connect_phase: {phase} attempt={attempt}/{config.connect_retries} "
                f"success={success} message={message_text}"
            )

            if success and not token_rejected:
                await client.change_account(config.account_mode)
                assets_map = await client.get_all_assets()
                print(f"assets_map_loaded: {len(assets_map)}")
                print(f"account_mode: {config.account_mode}")
                return client, attempts, None

            if client is not None:
                await client.close()

            if attempt < config.connect_retries:
                delay = config.connect_retry_delay_seconds * (2 ** (attempt - 1))
                print(f"connect_backoff: phase={phase} wait_seconds={delay:.2f}")
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
            print(
                f"connect_phase_exception: phase={phase} attempt={attempt}/{config.connect_retries} "
                f"error={error_message}"
            )
            if client is not None:
                await client.close()

            if attempt < config.connect_retries:
                delay = config.connect_retry_delay_seconds * (2 ** (attempt - 1))
                print(f"connect_backoff: phase={phase} wait_seconds={delay:.2f}")
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


async def resolve_symbol(client: Quotex, requested_symbol: str, timeout_seconds: int) -> str:
    """Resolve the exact asset name through pyquotex without auto-fallback to OTC."""

    asset_name, asset_data = await asyncio.wait_for(
        client.get_available_asset(requested_symbol, force_open=False),
        timeout=timeout_seconds,
    )
    is_open = bool(asset_data and len(asset_data) > 2 and asset_data[2])
    print(f"asset_resolution: requested={requested_symbol} resolved={asset_name} is_open={is_open}")
    return asset_name or requested_symbol


async def ensure_assets_map(client: Quotex, timeout_seconds: int) -> dict[str, int]:
    """Ensure client.codes_asset is loaded and return a normalized symbol->asset_id map."""

    if not client.codes_asset:
        await asyncio.wait_for(client.get_all_assets(), timeout=timeout_seconds)

    normalized: dict[str, int] = {}
    for symbol, raw_asset_id in client.codes_asset.items():
        try:
            normalized[str(symbol)] = int(raw_asset_id)
        except (TypeError, ValueError):
            continue
    return normalized


def invert_assets_map(assets_map: dict[str, int]) -> dict[int, str]:
    """Build an asset_id->symbol map from a symbol->asset_id map."""

    return {asset_id: symbol for symbol, asset_id in assets_map.items()}


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


def _parse_event_frame(frame: str) -> tuple[str, Any] | None:
    """Parse socket.io event frame 42[...] into event and payload."""

    if not frame.startswith("42"):
        return None

    try:
        payload = json.loads(frame[2:])
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, list) or not payload:
        return None

    event_name = payload[0]
    if not isinstance(event_name, str):
        return None

    event_payload = payload[1] if len(payload) > 1 else None
    return event_name, event_payload


def _extract_history_from_object(payload: Any) -> tuple[str | None, Any]:
    """Try extracting history payload from arbitrary pyquotex state objects."""

    if isinstance(payload, str):
        event = _parse_event_frame(payload)
        if event and event[0] in {"history/list", "history/list/v2"}:
            return event[0], event[1]
        return None, None

    if isinstance(payload, dict):
        for key in ("history/list", "history/list/v2"):
            if key in payload:
                return key, payload[key]

        event_name = payload.get("name")
        if isinstance(event_name, str) and event_name in {"history/list", "history/list/v2"}:
            if "msg" in payload:
                return event_name, payload["msg"]
            if "message" in payload:
                return event_name, payload["message"]
            if "payload" in payload:
                return event_name, payload["payload"]

    if isinstance(payload, (list, tuple)):
        for item in reversed(list(payload)[-50:]):
            event_name, event_payload = _extract_history_from_object(item)
            if event_name:
                return event_name, event_payload

    return None, None


def _history_candidates(client: Quotex) -> list[tuple[str, Any]]:
    """Collect likely pyquotex in-memory stores that may contain history events."""

    candidates: list[tuple[str, Any]] = []
    api = getattr(client, "api", None)

    explicit_paths = [
        ("client.history", getattr(client, "history", None)),
        ("client.history_data", getattr(client, "history_data", None)),
        ("client.history_list", getattr(client, "history_list", None)),
        ("client.candles_data", getattr(client, "candles_data", None)),
        ("client.api.history", getattr(api, "history", None) if api is not None else None),
        ("client.api.history_data", getattr(api, "history_data", None) if api is not None else None),
        ("client.api.history_list", getattr(api, "history_list", None) if api is not None else None),
        ("client.api.candles_data", getattr(api, "candles_data", None) if api is not None else None),
        (
            "client.api.websocket_client",
            getattr(api, "websocket_client", None) if api is not None else None,
        ),
    ]
    candidates.extend((name, value) for name, value in explicit_paths if value is not None)

    for root_name, root in (("client", client), ("client.api", api)):
        if root is None:
            continue

        for attr_name in dir(root):
            if attr_name.startswith("__"):
                continue
            lowered = attr_name.lower()
            if not any(
                token in lowered
                for token in ("history", "candle", "event", "queue", "message", "ws")
            ):
                continue

            try:
                value = getattr(root, attr_name)
            except Exception:
                continue

            if callable(value):
                continue

            candidates.append((f"{root_name}.{attr_name}", value))

    return candidates


async def _resolve_send_callable(client: Quotex) -> tuple[str, Callable[..., Any]]:
    """Resolve pyquotex internal sender for raw websocket events."""

    client_sender = getattr(client, "send_websocket_request", None)
    if callable(client_sender):
        return "client.send_websocket_request", client_sender

    api = getattr(client, "api", None)
    api_sender = getattr(api, "send_websocket_request", None) if api is not None else None
    if callable(api_sender):
        return "client.api.send_websocket_request", api_sender

    raise RuntimeError("pyquotex sender not found (send_websocket_request unavailable)")


async def _send_raw_event(
    sender_name: str,
    sender: Callable[..., Any],
    event_name: str,
    event_payload: dict[str, Any],
) -> dict[str, Any]:
    """Send one raw websocket event trying compatible pyquotex signatures."""

    attempts: list[dict[str, Any]] = []
    send_variants: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
        ("positional_name_payload", (event_name, event_payload), {}),
        ("positional_name_payload_request_id", (event_name, event_payload, ""), {}),
        ("keyword_name_msg", (), {"name": event_name, "msg": event_payload}),
        ("keyword_event_payload", (), {"event": event_name, "payload": event_payload}),
    ]

    for variant_name, args, kwargs in send_variants:
        try:
            result = sender(*args, **kwargs)
            if isawaitable(result):
                result = await result

            attempts.append(
                {
                    "variant": variant_name,
                    "ok": True,
                    "sender": sender_name,
                    "event": event_name,
                    "return_type": type(result).__name__,
                    "returned_value": result,
                    "error": None,
                }
            )
            return {
                "ok": True,
                "attempts": attempts,
            }
        except Exception as exc:
            attempts.append(
                {
                    "variant": variant_name,
                    "ok": False,
                    "sender": sender_name,
                    "event": event_name,
                    "return_type": None,
                    "returned_value": None,
                    "error": str(exc),
                }
            )

    return {
        "ok": False,
        "attempts": attempts,
    }


async def _poll_history_response(
    client: Quotex,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    """Poll pyquotex memory/event stores for history/list or history/list/v2."""

    started_at = time.monotonic()
    snapshots_checked = 0
    last_candidates: list[str] = []

    while (time.monotonic() - started_at) < timeout_seconds:
        candidates = _history_candidates(client)
        last_candidates = [name for name, _ in candidates[:25]]
        snapshots_checked += len(candidates)

        for source_name, source_payload in candidates:
            event_name, event_payload = _extract_history_from_object(source_payload)
            if event_name:
                return {
                    "found": True,
                    "event": event_name,
                    "payload": event_payload,
                    "source": source_name,
                    "timed_out": False,
                    "snapshots_checked": snapshots_checked,
                    "candidates_sample": last_candidates,
                }

        await asyncio.sleep(poll_interval_seconds)

    return {
        "found": False,
        "event": None,
        "payload": None,
        "source": None,
        "timed_out": True,
        "snapshots_checked": snapshots_checked,
        "candidates_sample": last_candidates,
    }


def print_payload_diagnostics(payload: Any) -> dict[str, Any]:
    """Print a visible diagnostics summary for raw websocket payloads."""

    summary = summarize_payload(payload)
    print("api_payload_method: ws_stream")
    print(f"api_payload_summary: {json.dumps(summary, ensure_ascii=False, default=str)}")
    return summary


async def resolve_requested_asset(
    client: Quotex,
    requested_symbol: str,
    requested_asset_id: int | None,
    timeout_seconds: int,
) -> tuple[str, int | None]:
    """Resolve the target symbol and asset id from symbol or optional env asset id."""

    assets_map = await ensure_assets_map(client, timeout_seconds)
    id_to_symbol = invert_assets_map(assets_map)

    if requested_asset_id is not None:
        symbol_from_id = id_to_symbol.get(requested_asset_id)
        if not symbol_from_id:
            raise ValueError(
                f"QUOTEX_HISTORY_ASSET_ID={requested_asset_id} was not found in assets map"
            )
        resolved_symbol = await resolve_symbol(client, symbol_from_id, timeout_seconds)
        resolved_asset_id = assets_map.get(resolved_symbol, requested_asset_id)
        return resolved_symbol, resolved_asset_id

    if not requested_symbol:
        raise ValueError("Missing QUOTEX_HISTORY_SYMBOL in .env")

    resolved_symbol = await resolve_symbol(client, requested_symbol, timeout_seconds)
    resolved_asset_id = assets_map.get(resolved_symbol)
    return resolved_symbol, resolved_asset_id


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


async def fetch_raw_history_via_lib_ws(
    client: Quotex,
    requested_symbol: str,
    requested_asset_id: int | None,
    candles_count: int,
    request_timeout_seconds: int,
    poll_interval_seconds: float,
) -> FetchResult:
    """Fetch historical payload sending raw events via pyquotex internals."""

    period = 60
    end_from_time = int(time.time())
    offset = 100 #candles_count * period
    resolved_symbol = requested_symbol or "UNKNOWN"
    resolved_asset_id = requested_asset_id
    method_used = "RAW_HISTORY_LOAD_VIA_LIB_WS"

    diagnostics: dict[str, Any] = {
        "sender": None,
        "events": {},
        "poll": None,
    }
    raw_payload: Any = None
    request_metadata: dict[str, Any] = {}

    try:
        resolved_symbol, resolved_asset_id = await resolve_requested_asset(
            client,
            requested_symbol=requested_symbol,
            requested_asset_id=requested_asset_id,
            timeout_seconds=request_timeout_seconds,
        )

        request_payload = {
            "asset": resolved_symbol,
            "index": end_from_time,
            "time": end_from_time,
            "offset": offset,
            "period": period,
        }
        request_metadata = {
            "event": "history/load",
            "payload": request_payload,
            "context_events": ["instruments/update", "depth/follow"],
            "ws_timeout_seconds": request_timeout_seconds,
            "ws_poll_interval_seconds": poll_interval_seconds,
        }

        print(
            f"historical_request: symbol={resolved_symbol} candles={candles_count} "
            f"period={period} offset={offset} method={method_used}"
        )

        sender_name, sender = await _resolve_send_callable(client)
        diagnostics["sender"] = sender_name

        context_instruments = await _send_raw_event(
            sender_name,
            sender,
            "instruments/update",
            {"asset": resolved_symbol},
        )
        diagnostics["events"]["instruments/update"] = context_instruments

        context_depth = await _send_raw_event(
            sender_name,
            sender,
            "depth/follow",
            {"asset": resolved_symbol},
        )
        diagnostics["events"]["depth/follow"] = context_depth

        history_send = await _send_raw_event(
            sender_name,
            sender,
            "history/load",
            request_payload,
        )
        diagnostics["events"]["history/load"] = history_send

        if not bool(history_send.get("ok")):
            return FetchResult(
                method_used=method_used,
                resolved_symbol=resolved_symbol,
                resolved_asset_id=resolved_asset_id,
                end_from_time=end_from_time,
                offset=offset,
                period=period,
                request_metadata=request_metadata,
                payload=raw_payload,
                diagnostics=diagnostics,
                timed_out=False,
                error_message="history/load send failed via send_websocket_request",
                error_category="RAW_WS_SEND_ERROR",
            )

        poll_result = await _poll_history_response(
            client=client,
            timeout_seconds=request_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        diagnostics["poll"] = {
            "found": poll_result["found"],
            "event": poll_result["event"],
            "source": poll_result["source"],
            "timed_out": poll_result["timed_out"],
            "snapshots_checked": poll_result["snapshots_checked"],
            "candidates_sample": poll_result["candidates_sample"],
        }
        raw_payload = poll_result["payload"]

        if not poll_result["found"]:
            return FetchResult(
                method_used=method_used,
                resolved_symbol=resolved_symbol,
                resolved_asset_id=resolved_asset_id,
                end_from_time=end_from_time,
                offset=offset,
                period=period,
                request_metadata=request_metadata,
                payload=raw_payload,
                diagnostics=diagnostics,
                timed_out=bool(poll_result["timed_out"]),
                error_message="history/list response not found in pyquotex internal stores",
                error_category="RAW_WS_TIMEOUT" if poll_result["timed_out"] else "RAW_WS_NO_RESPONSE",
            )

        return FetchResult(
            method_used=method_used,
            resolved_symbol=resolved_symbol,
            resolved_asset_id=resolved_asset_id,
            end_from_time=end_from_time,
            offset=offset,
            period=period,
            request_metadata=request_metadata,
            payload=raw_payload,
            diagnostics=diagnostics,
            timed_out=bool(diagnostics.get("poll", {}).get("timed_out", False)),
            error_message=None,
            error_category=None,
        )
    except asyncio.TimeoutError:
        return FetchResult(
            method_used=method_used,
            resolved_symbol=resolved_symbol,
            resolved_asset_id=resolved_asset_id,
            end_from_time=end_from_time,
            offset=offset,
            period=period,
            request_metadata=request_metadata,
            payload=raw_payload,
            diagnostics=diagnostics,
            timed_out=True,
            error_message=f"raw history poll timed out after {request_timeout_seconds} seconds",
            error_category="RAW_WS_TIMEOUT",
        )
    except Exception as exc:
        return FetchResult(
            method_used=method_used,
            resolved_symbol=resolved_symbol,
            resolved_asset_id=resolved_asset_id,
            end_from_time=end_from_time,
            offset=offset,
            period=period,
            request_metadata=request_metadata,
            payload=raw_payload,
            diagnostics=diagnostics,
            timed_out=False,
            error_message=f"raw history request failed: {str(exc)}",
            error_category="RAW_WS_ERROR",
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
    requested_asset_id: int | None,
    connection_result: ConnectionResult,
    method_requested: str,
    method_attempts: list[dict[str, Any]],
) -> Path:
    """Persist raw diagnostics payload for analysis."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_symbol = fetch_result.resolved_symbol.replace("/", "_")
    output_path = output_dir / f"historical_api_raw_{safe_symbol}_{timestamp}.json"

    payload_summary = print_payload_diagnostics(fetch_result.payload)
    api_raw_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_symbol": requested_symbol,
        "requested_asset_id": requested_asset_id,
        "resolved_symbol": fetch_result.resolved_symbol,
        "resolved_asset_id": fetch_result.resolved_asset_id,
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
    asset_id: int | None,
    requested_symbol: str,
    requested_asset_id: int | None,
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
        "asset_id": asset_id,
        "method_used": method_used,
        "requested_symbol": requested_symbol,
        "requested_asset_id": requested_asset_id,
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

        fetch_result = await fetch_raw_history_via_lib_ws(
            client,
            requested_symbol=config.symbol,
            requested_asset_id=config.asset_id,
            candles_count=config.candles_count,
            request_timeout_seconds=config.request_timeout_seconds,
            poll_interval_seconds=config.ws_poll_interval_seconds,
        )
        raw_candles = normalize_history_payload(fetch_result.payload)
        method_attempts = [build_attempt_diagnostics(fetch_result, len(raw_candles))]

        api_raw_output_path = write_api_raw_output(
            Path(config.output_dir),
            fetch_result,
            config.symbol,
            config.asset_id,
            connection_result,
            "RAW_HISTORY_LOAD_VIA_LIB_WS",
            method_attempts,
        )
        print(f"api_raw_output_file: {api_raw_output_path}")

        if fetch_result.error_message:
            if fetch_result.error_category in {"RAW_WS_ERROR", "RAW_WS_SEND_ERROR"}:
                print(f"error_raw_ws: {fetch_result.error_message}")
            else:
                print(f"error_historical_fetch: {fetch_result.error_message}")

        if not raw_candles:
            attempt_errors = [
                f"{attempt['method']}={attempt['error'] or 'INVALID_PAYLOAD'}"
                for attempt in method_attempts
            ]
            attempts_text = " | ".join(attempt_errors) if attempt_errors else "no attempts"
            print(f"error_raw_ws_failed: {attempts_text}")
            print("no_ohlc_response: raw ws history did not return valid OHLC data")
            return 1

        raw_candles = raw_candles[-config.candles_count :]
        normalized_candles = [
            map_raw_candle_to_candle_data(raw_candle, fetch_result.resolved_symbol)
            for raw_candle in raw_candles
        ]

        raw_output_path, normalized_output_path, chart_output_path = write_ohlc_outputs(
            Path(config.output_dir),
            fetch_result.resolved_symbol,
            fetch_result.resolved_asset_id,
            config.symbol,
            config.asset_id,
            raw_candles,
            normalized_candles,
            config.chart_lookback,
            fetch_result.method_used,
        )
        print(f"candles_found: {len(raw_candles)}")
        print(f"requested_symbol: {config.symbol or '<empty>'}")
        print(f"requested_asset_id: {config.asset_id}")
        print(f"resolved_symbol: {fetch_result.resolved_symbol}")
        print(f"resolved_asset_id: {fetch_result.resolved_asset_id}")
        print(f"historical_method_used: {fetch_result.method_used}")
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
        failure_text = str(exc)
        category = classify_connection_failure(failure_text)
        if category == "AUTH_SESSION_ERROR":
            print(f"error_auth_session: {failure_text}")
        else:
            print(f"error_connection: {failure_text}")
        print("no_ohlc_response: ws_stream did not return OHLC data")
        return 1
    finally:
        if client is not None:
            await client.close()


def main() -> None:
    """Entrypoint."""

    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
