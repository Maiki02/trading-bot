"""Raw Quotex WebSocket historical probe through pyquotex connection flow.

This script authenticates with pyquotex and sends a raw history/load websocket
request through library internals, without using get_candles/get_candle_v2.
"""

from __future__ import annotations

import asyncio
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pyquotex.stable_api import Quotex


@dataclass(frozen=True)
class ScriptConfig:
    """Configuration loaded from environment variables."""

    auth_method: str
    email: str
    password: str
    ssid: str
    ws_debug: bool
    account_mode: str
    symbol: str
    offset: int
    period: int
    ws_timeout_seconds: int
    ws_poll_interval_seconds: float
    output_dir: Path


@dataclass(frozen=True)
class AuthResult:
    """Connection/authentication diagnostics from pyquotex."""

    ok: bool
    message: str
    assets_loaded: bool
    asset_count: int
    token_rejected: bool


def _parse_bool(value: str, default: bool = False) -> bool:
    """Convert common string booleans to Python bool."""

    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> ScriptConfig:
    """Load script settings from .env and environment."""

    load_dotenv()

    output_dir_raw = os.getenv("QUOTEX_HISTORY_OUTPUT_DIR", "data/quotex-history").strip()
    output_dir = (PROJECT_ROOT / output_dir_raw).resolve()

    return ScriptConfig(
        auth_method=os.getenv("QUOTEX_AUTH_METHOD", "CREDENTIALS").strip().upper(),
        email=os.getenv("QUOTEX_EMAIL", "").strip(),
        password=os.getenv("QUOTEX_PASSWORD", "").strip(),
        ssid=os.getenv("QUOTEX_SSID", "").strip(),
        ws_debug=_parse_bool(os.getenv("QUOTEX_WS_DEBUG", "false"), default=False),
        account_mode=os.getenv("QUOTEX_HISTORY_ACCOUNT_MODE", "PRACTICE").strip().upper() or "PRACTICE",
        symbol=os.getenv("QUOTEX_HISTORY_SYMBOL", "AUDJPY_otc").strip() or "AUDJPY_otc",
        offset=max(int(os.getenv("QUOTEX_HISTORY_OFFSET", "3600")), 1),
        period=max(int(os.getenv("QUOTEX_HISTORY_PERIOD", "60")), 1),
        ws_timeout_seconds=max(int(os.getenv("QUOTEX_WS_TIMEOUT", "20")), 1),
        ws_poll_interval_seconds=max(float(os.getenv("QUOTEX_WS_POLL_INTERVAL_SECONDS", "0.2")), 0.05),
        output_dir=output_dir,
    )


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


async def _send_history_load(
    sender_name: str,
    sender: Callable[..., Any],
    request_payload: dict[str, int | str],
) -> dict[str, Any]:
    """Send raw history/load through pyquotex internal websocket sender."""

    attempts: list[dict[str, Any]] = []
    send_variants: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
        ("positional_name_payload", ("history/load", request_payload), {}),
        ("positional_name_payload_request_id", ("history/load", request_payload, ""), {}),
        ("keyword_name_msg", (), {"name": "history/load", "msg": request_payload}),
        ("keyword_event_payload", (), {"event": "history/load", "payload": request_payload}),
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


async def connect_with_pyquotex(config: ScriptConfig) -> tuple[Quotex | None, AuthResult]:
    """Authenticate/connect using pyquotex with CREDENTIALS or SESSION mode."""

    if config.auth_method == "SESSION":
        if not config.ssid:
            return None, AuthResult(
                ok=False,
                message="Missing QUOTEX_SSID in .env for SESSION auth.",
                assets_loaded=False,
                asset_count=0,
                token_rejected=False,
            )
        client = Quotex(email="SESSION_AUTH", password="SESSION_AUTH", lang="en")
        client.set_session(user_agent="Quotex/1.0", ssid=config.ssid)
    else:
        if not config.email or not config.password:
            return None, AuthResult(
                ok=False,
                message="Missing QUOTEX_EMAIL or QUOTEX_PASSWORD in .env.",
                assets_loaded=False,
                asset_count=0,
                token_rejected=False,
            )
        client = Quotex(email=config.email, password=config.password, lang="en")

    client.debug_ws_enable = config.ws_debug

    try:
        success, message = await client.connect()
        message_text = str(message)
        token_rejected = "token rejected" in message_text.lower()

        if not success or token_rejected:
            return client, AuthResult(
                ok=False,
                message=message_text,
                assets_loaded=False,
                asset_count=0,
                token_rejected=token_rejected,
            )

        await client.change_account(config.account_mode)

        assets_loaded = False
        asset_count = 0
        try:
            assets = await client.get_all_assets()
            if isinstance(assets, dict):
                assets_loaded = True
                asset_count = len(assets)
        except Exception:
            assets_loaded = False

        return client, AuthResult(
            ok=True,
            message=message_text,
            assets_loaded=assets_loaded,
            asset_count=asset_count,
            token_rejected=False,
        )
    except Exception as exc:
        return client, AuthResult(
            ok=False,
            message=f"connect() failed: {exc}",
            assets_loaded=False,
            asset_count=0,
            token_rejected=False,
        )


async def probe_history_raw_ws_via_lib(client: Quotex, config: ScriptConfig) -> dict[str, Any]:
    """Send raw history/load through pyquotex and capture history/list response."""

    now = int(time.time())
    request_payload: dict[str, int | str] = {
        "asset": config.symbol,
        "index": now,
        "time": now,
        "offset": config.offset,
        "period": config.period,
    }

    diagnostics: dict[str, Any] = {
        "sender": None,
        "send": None,
        "poll": None,
        "error": None,
    }

    try:
        sender_name, sender = await _resolve_send_callable(client)
        diagnostics["sender"] = sender_name

        send_result = await _send_history_load(sender_name, sender, request_payload)
        diagnostics["send"] = send_result

        if not bool(send_result.get("ok")):
            return {
                "request": request_payload,
                "history": {
                    "found": False,
                    "event": None,
                    "payload": None,
                    "source": None,
                    "timed_out": False,
                },
                "diagnostics": diagnostics,
            }

        poll_result = await _poll_history_response(
            client=client,
            timeout_seconds=config.ws_timeout_seconds,
            poll_interval_seconds=config.ws_poll_interval_seconds,
        )
        diagnostics["poll"] = {
            "timed_out": poll_result["timed_out"],
            "source": poll_result["source"],
            "event": poll_result["event"],
            "snapshots_checked": poll_result["snapshots_checked"],
            "candidates_sample": poll_result["candidates_sample"],
        }

        return {
            "request": request_payload,
            "history": {
                "found": poll_result["found"],
                "event": poll_result["event"],
                "payload": poll_result["payload"],
                "source": poll_result["source"],
                "timed_out": poll_result["timed_out"],
            },
            "diagnostics": diagnostics,
        }
    except Exception as exc:
        diagnostics["error"] = str(exc)
        return {
            "request": request_payload,
            "history": {
                "found": False,
                "event": None,
                "payload": None,
                "source": None,
                "timed_out": False,
            },
            "diagnostics": diagnostics,
        }


def write_probe_output(config: ScriptConfig, payload: dict[str, Any]) -> Path:
    """Persist probe output JSON to configured directory."""

    config.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_name = f"historical_api_raw_ws_{config.symbol}_{timestamp}.json"
    output_path = config.output_dir / file_name
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


async def run() -> int:
    """Run full raw probe flow and return exit code."""

    config = load_config()
    client: Quotex | None = None

    try:
        client, auth_result = await connect_with_pyquotex(config)
        if auth_result.ok and client is not None:
            probe_result = await probe_history_raw_ws_via_lib(client, config)
        else:
            now = int(time.time())
            probe_result = {
                "request": {
                    "asset": config.symbol,
                    "index": now,
                    "time": now,
                    "offset": config.offset,
                    "period": config.period,
                },
                "history": {
                    "found": False,
                    "event": None,
                    "payload": None,
                    "source": None,
                    "timed_out": False,
                },
                "diagnostics": {
                    "sender": None,
                    "send": None,
                    "poll": None,
                    "error": "WS history/load skipped because pyquotex auth/connect failed.",
                },
            }

        output_payload: dict[str, Any] = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "raw_ws_history_probe",
            "method_used": "RAW_HISTORY_LOAD_VIA_LIB_WS",
            "request_metadata": {
                "symbol": config.symbol,
                "offset": config.offset,
                "period": config.period,
                "ws_timeout_seconds": config.ws_timeout_seconds,
                "ws_poll_interval_seconds": config.ws_poll_interval_seconds,
                "account_mode": config.account_mode,
                "auth_method": config.auth_method,
            },
            "auth_status": {
                "ok": auth_result.ok,
                "message": auth_result.message,
                "auth_method": config.auth_method,
                "token_rejected": auth_result.token_rejected,
                "assets_loaded": auth_result.assets_loaded,
                "asset_count": auth_result.asset_count,
            },
            "request": probe_result["request"],
            "history": probe_result["history"],
            "diagnostics": probe_result["diagnostics"],
        }

        output_path = write_probe_output(config, output_payload)

        auth_ok = bool(output_payload["auth_status"].get("ok"))
        history_found = bool(output_payload["history"].get("found"))

        print(f"auth: {'ok' if auth_ok else 'fail'}")
        print(f"history_found: {'yes' if history_found else 'no'}")
        print(f"output_path: {output_path}")

        if not history_found:
            return 1
        return 0
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
