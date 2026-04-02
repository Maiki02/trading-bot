"""Quotex authentication helper.

Single responsibility: return one connected Quotex client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.utils.quotex_bootstrap import Quotex


def _parse_bool(value: str, default: bool = False) -> bool:
    """Parse environment-style boolean values."""
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_persisted_session(email: str, session_file: Path) -> dict[str, Any] | None:
    """Load persisted session from session.json for one account."""
    if not email or not session_file.exists():
        return None

    try:
        payload = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    account_data = payload.get(email)
    if not isinstance(account_data, dict):
        return None

    user_agent = str(account_data.get("user_agent") or "").strip()
    token = str(account_data.get("token") or "").strip()
    cookies_raw = account_data.get("cookies")
    cookies = str(cookies_raw).strip() if cookies_raw is not None else ""

    if not user_agent or not token:
        return None

    return {
        "user_agent": user_agent,
        "token": token,
        "cookies": cookies or None,
    }


async def get_connected_client(
    email: str,
    password: str,
    ssid: str,
    account_mode: str,
) -> Quotex:
    """Return a connected Quotex client using SSID or persisted/fresh credentials.

    Strategy:
    - If SSID is provided, connect with explicit token session.
    - Otherwise, try persisted session.json for this email if available.
    - Fallback to fresh credentials.
    """

    mode = (account_mode or "PRACTICE").strip().upper() or "PRACTICE"
    ws_debug = _parse_bool(os.getenv("QUOTEX_WS_DEBUG", "false"), default=False)
    session_file = Path(__file__).resolve().parents[2] / "session.json"

    if ssid:
        client = Quotex(email="SESSION_AUTH", password="SESSION_AUTH", lang="en")
        client.session_data = {
            "user_agent": "Quotex/1.0",
            "cookies": None,
            "token": ssid,
        }
        client.debug_ws_enable = ws_debug
        client.set_account_mode(mode)

        ok, reason = await client.connect()
        if not ok:
            await client.close()
            raise ConnectionError(f"SESSION_SSID_CONNECTION_ERROR: {reason}")

        await client.change_account(mode)
        return client

    if not email or not password:
        raise ValueError("Missing QUOTEX_EMAIL or QUOTEX_PASSWORD")

    persisted = _load_persisted_session(email=email, session_file=session_file)
    phases = ["persisted", "fresh"] if persisted else ["fresh"]

    last_reason = "Unknown connection failure"
    for phase in phases:
        client = Quotex(email=email, password=password, lang="en")
        client.debug_ws_enable = ws_debug
        client.set_account_mode(mode)

        if phase == "persisted" and persisted is not None:
            client.session_data = {
                "user_agent": persisted["user_agent"],
                "cookies": persisted["cookies"],
                "token": persisted["token"],
            }

        ok, reason = await client.connect()
        reason_text = str(reason)
        token_rejected = "token rejected" in reason_text.lower()
        if ok and not token_rejected:
            await client.change_account(mode)
            return client

        last_reason = reason_text
        await client.close()

    raise ConnectionError(f"CREDENTIALS_CONNECTION_ERROR: {last_reason}")
