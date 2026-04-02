"""Pure Quotex candles chunk fetcher.

Single responsibility: request one historical chunk from Quotex using an
injected, already-connected client.
"""

from __future__ import annotations

from typing import Any

from src.utils.quotex_bootstrap import Quotex


async def fetch_candles_chunk(
    client: Quotex,
    asset: str,
    end_time: int,
    period: int,
    offset_seconds: int,
) -> list[dict[str, Any]]:
    """Fetch one raw historical OHLC chunk with the injected client.

    Parameters
    ----------
    client:
        Connected Quotex client.
    asset:
        Broker asset symbol (e.g. EURUSD, EURUSD_otc).
    end_time:
        End timestamp (seconds) used by broker as right boundary.
    period:
        Candle timeframe in seconds.
    offset_seconds:
        Requested historical window size in seconds.
    """

    payload = await client.get_candles(asset, float(end_time), int(offset_seconds), int(period))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []
