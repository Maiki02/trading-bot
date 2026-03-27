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


async def fetch_symbols(
    client: Quotex,
    scope: str,
) -> list[str]:
    """Fetch symbols from Quotex according to selected scope."""

    assets_map = await client.get_all_assets()
    all_symbols = sorted(assets_map.keys())

    if scope == "all":
        return all_symbols

    open_symbols: list[str] = []
    for symbol in all_symbols:
        try:
            _, asset_data = await client.get_available_asset(symbol, force_open=False)
            is_open = bool(asset_data and len(asset_data) > 2 and asset_data[2])
            if is_open:
                open_symbols.append(symbol)
        except Exception:
            # Skip noisy assets and keep processing the rest.
            continue

    return sorted(open_symbols)


def write_outputs(output_dir: Path, scope: str, symbols: list[str]) -> tuple[Path, Path]:
    """Write JSON and TXT outputs and return file paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    payload: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "count": len(symbols),
        "symbols": symbols,
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

        symbols = await fetch_symbols(client, scope=args.scope)
        json_path, txt_path = write_outputs(Path(args.output_dir), args.scope, symbols)

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
