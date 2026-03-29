"""List valid Quotex symbols by logging in and querying available assets.

This utility reads credentials from .env and supports:
- all symbols known by the broker
- only open symbols (validated through get_available_asset)

Output is written to JSON and TXT files in a local output folder.
"""

from __future__ import annotations

import argparse
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


def _to_number(value: Any) -> int | float | None:
    """Return numeric scalar values, otherwise None."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _parse_bool(value: str, default: bool = False) -> bool:
    """Convert typical string booleans to a Python bool."""

    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> ScriptConfig:
    """Load Quotex auth settings from .env."""

    load_dotenv()
    return ScriptConfig(
        email=os.getenv("QUOTEX_EMAIL", "").strip(),
        password=os.getenv("QUOTEX_PASSWORD", "").strip(),
        auth_method=os.getenv("QUOTEX_AUTH_METHOD", "CREDENTIALS").strip().upper(),
        ssid=os.getenv("QUOTEX_SSID", "").strip(),
        ws_debug=_parse_bool(os.getenv("QUOTEX_WS_DEBUG", "false"), default=False),
    )


def build_parser() -> argparse.ArgumentParser:
    """Create command-line parser."""

    parser = argparse.ArgumentParser(
        description="Log in to Quotex and list valid symbols.",
    )
    parser.add_argument(
        "--scope",
        choices=["open", "all"],
        default="open",
        help="open: only symbols currently open; all: every discovered symbol.",
    )
    parser.add_argument(
        "--account-mode",
        choices=["PRACTICE", "REAL"],
        default="PRACTICE",
        help="Account mode to select after connect.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/quotex-symbols",
        help="Directory where output files are stored.",
    )
    return parser


async def fetch_assets(
    client: Quotex,
    scope: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Fetch symbols and rich asset metadata according to selected scope."""

    assets_map = await client.get_all_assets()
    if not isinstance(assets_map, dict):
        return [], []

    payment_map_raw = client.get_payment()
    payment_map = payment_map_raw if isinstance(payment_map_raw, dict) else {}

    all_symbols = sorted(str(symbol) for symbol in assets_map.keys())
    assets: list[dict[str, Any]] = []

    for symbol in all_symbols:
        asset_id: str | int | None = assets_map.get(symbol)
        asset_name: str | None = None
        is_open: bool | None = None

        try:
            _, asset_data = await client.get_available_asset(symbol, force_open=False)
            if isinstance(asset_data, (list, tuple)):
                if len(asset_data) > 0 and asset_data[0] not in (None, ""):
                    asset_id = asset_data[0]
                if len(asset_data) > 1 and asset_data[1] not in (None, ""):
                    asset_name = str(asset_data[1])
                if len(asset_data) > 2:
                    is_open = bool(asset_data[2])
        except Exception:
            # Keep metadata best-effort and continue processing.
            pass

        payment_entry_raw = None
        if asset_name and isinstance(payment_map.get(asset_name), dict):
            payment_entry_raw = payment_map.get(asset_name)
        elif isinstance(payment_map.get(symbol), dict):
            payment_entry_raw = payment_map.get(symbol)

        payment_entry = payment_entry_raw if isinstance(payment_entry_raw, dict) else {}
        profit_map_raw = payment_entry.get("profit")
        profit_map = profit_map_raw if isinstance(profit_map_raw, dict) else {}

        profit_24h = None
        try:
            payout_raw = client.get_payout_by_asset(symbol, timeframe="all")
            if isinstance(payout_raw, dict):
                profit_24h = _to_number(payout_raw.get("24H"))
        except Exception:
            # Older pyquotex versions may fail for unsupported assets.
            pass

        asset_payload: dict[str, Any] = {
            "id": asset_id,
            "symbol": symbol,
            "name": asset_name,
            "open": is_open,
            "payment": _to_number(payment_entry.get("payment")),
            "turbo_payment": _to_number(payment_entry.get("turbo_payment")),
            "profit_24h": profit_24h,
            "profit_1m": _to_number(profit_map.get("1M")),
            "profit_5m": _to_number(profit_map.get("5M")),
        }

        if scope == "open" and not bool(asset_payload.get("open")):
            continue

        assets.append(asset_payload)

    symbols = [asset["symbol"] for asset in assets]
    return symbols, assets


def write_outputs(
    output_dir: Path,
    scope: str,
    symbols: list[str],
    assets: list[dict[str, Any]],
) -> tuple[Path, Path]:
    """Write JSON and TXT outputs and return file paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    payload: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "count": len(symbols),
        "symbols": symbols,
        "assets": assets,
    }

    json_path = output_dir / f"valid_symbols_{scope}_{timestamp}.json"
    txt_path = output_dir / f"valid_symbols_{scope}_{timestamp}.txt"

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    txt_path.write_text("\n".join(symbols), encoding="utf-8")

    return json_path, txt_path


async def run(args: argparse.Namespace) -> int:
    """Main async execution."""

    config = load_config()

    if config.auth_method == "CREDENTIALS":
        if not config.email or not config.password:
            print("Missing QUOTEX_EMAIL or QUOTEX_PASSWORD in .env")
            return 2
        client = Quotex(email=config.email, password=config.password, lang="en")
    else:
        if not config.ssid:
            print("Missing QUOTEX_SSID in .env for SESSION auth")
            return 2
        # Keep placeholders non-empty to avoid interactive credential flow.
        client = Quotex(email="SESSION_AUTH", password="SESSION_AUTH", lang="en")
        client.set_session(user_agent="Quotex/1.0", ssid=config.ssid)

    client.debug_ws_enable = config.ws_debug

    connected = False
    try:
        check_connect, message = await client.connect()
        print(f"connect: success={check_connect} message={message}")
        if not check_connect:
            return 1

        connected = True
        await client.change_account(args.account_mode)

        symbols, assets = await fetch_assets(client, scope=args.scope)
        json_path, txt_path = write_outputs(Path(args.output_dir), args.scope, symbols, assets)

        print(f"symbols_found: {len(symbols)}")
        print(f"json_output: {json_path}")
        print(f"txt_output:  {txt_path}")
        if symbols:
            print(f"first_symbols: {symbols[:10]}")

        return 0

    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    except Exception as exc:
        print(f"error: {exc}")
        return 1
    finally:
        if connected:
            await client.close()


def main() -> None:
    """Entrypoint."""

    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
