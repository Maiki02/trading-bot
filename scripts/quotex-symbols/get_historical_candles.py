"""Fetch historical Quotex candles for one symbol configured in .env.

This utility is intentionally minimal and split into two clear steps:
1. login_to_quotex()
2. fetch_historical_candles(symbol, candles_count)

It writes the raw response to a JSON file for inspection.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pyquotex.stable_api import Quotex


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


def _parse_bool(value: str, default: bool = False) -> bool:
    """Convert common string booleans to a Python bool."""

    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> ScriptConfig:
    """Load script configuration from .env."""

    load_dotenv()

    candles_count_raw = os.getenv("QUOTEX_HISTORY_CANDLES", "151").strip()
    candles_count = int(candles_count_raw) if candles_count_raw else 151

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
    )


async def login_to_quotex(config: ScriptConfig) -> Quotex:
    """Authenticate and return a connected Quotex client."""

    if config.auth_method == "CREDENTIALS":
        if not config.email or not config.password:
            raise ValueError("Missing QUOTEX_EMAIL or QUOTEX_PASSWORD in .env")
        client = Quotex(email=config.email, password=config.password, lang="en")
    else:
        if not config.ssid:
            raise ValueError("Missing QUOTEX_SSID in .env for SESSION auth")
        client = Quotex(email="SESSION_AUTH", password="SESSION_AUTH", lang="en")
        client.set_session(user_agent="Quotex/1.0", ssid=config.ssid)

    client.debug_ws_enable = config.ws_debug

    check_connect, message = await client.connect()
    print(f"connect: success={check_connect} message={message}")
    if not check_connect:
        raise RuntimeError(f"Connection failed: {message}")

    await client.change_account(config.account_mode)
    print(f"account_mode: {config.account_mode}")
    return client


async def fetch_historical_candles(
    client: Quotex,
    symbol: str,
    candles_count: int,
    request_timeout_seconds: int,
) -> list[dict[str, Any]]:
    """Fetch historical candles for the requested symbol and count."""

    if not symbol:
        raise ValueError("Missing QUOTEX_HISTORY_SYMBOL in .env")

    period = 60
    end_from_time = datetime.now(timezone.utc).timestamp()
    offset = candles_count * period

    print(
        f"historical_request: symbol={symbol} candles={candles_count} "
        f"period={period} offset={offset}"
    )

    try:
        candles = await asyncio.wait_for(
            client.get_candles(
                asset=symbol,
                end_from_time=end_from_time,
                offset=offset,
                period=period,
            ),
            timeout=request_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"Historical request timed out after {request_timeout_seconds}s "
            f"for symbol={symbol} offset={offset}"
        ) from exc

    return candles or []


def write_output(output_dir: Path, symbol: str, candles: list[dict[str, Any]]) -> Path:
    """Persist raw historical candle payload to disk."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_symbol = symbol.replace("/", "_")
    output_path = output_dir / f"historical_{safe_symbol}_{timestamp}.json"

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "count": len(candles),
        "candles": candles,
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


async def run() -> int:
    """Main async execution."""

    config = load_config()
    client: Quotex | None = None

    try:
        client = await login_to_quotex(config)
        candles = await fetch_historical_candles(
            client,
            symbol=config.symbol,
            candles_count=config.candles_count,
            request_timeout_seconds=config.request_timeout_seconds,
        )

        output_path = write_output(Path(config.output_dir), config.symbol, candles)
        print(f"candles_found: {len(candles)}")
        print(f"output_file: {output_path}")
        if candles:
            print(f"first_candle: {candles[0]}")
            print(f"last_candle: {candles[-1]}")
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