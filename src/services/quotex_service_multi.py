"""
Quotex Multi-Instrument Market Data Service
=============================================
Async-native service for handling multiple instruments simultaneously via pyquotex.
Implements Sleep & Burst polling strategy for low-latency candle detection.

ARCHITECTURE:
- Single async Quotex client connection
- Multiple instrument subscriptions via candle streams
- Sleep & Burst polling for candle close detection
- Historical candle loading for indicator initialization
- Exponential backoff reconnection

KEY DIFFERENCE FROM IQ OPTION:
pyquotex is async-native, so all API calls use await directly
without needing run_in_executor wrappers.

Author: Trading Bot Team
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Callable, List

from pyquotex.stable_api import Quotex
from pyquotex.utils.processor import process_tick

from config import Config
from src.services.connection_service import CandleData
from src.utils.logger import get_logger

logger = get_logger(__name__)


class QuotexServiceMultiAsync:
    """
    Async multi-instrument market data service for Quotex.
    Polls real-time candle streams and detects new closed candles
    using the Sleep & Burst strategy.
    """

    def __init__(
        self,
        analysis_service,
        on_auth_failure_callback: Optional[Callable] = None
    ):
        """
        Initialize the Quotex async service.

        Args:
            analysis_service: AnalysisService instance for candle processing.
            on_auth_failure_callback: Optional callback invoked on authentication failure.
        """
        self.analysis_service = analysis_service
        self.on_auth_failure_callback = on_auth_failure_callback

        self.client: Optional[Quotex] = None
        self._should_poll = False
        self.poll_tasks: List[asyncio.Task] = []

        # Per-instrument timestamp tracking
        self.last_candle_timestamps: Dict[str, int] = {}
        self.current_candle_timestamps: Dict[str, int] = {}

        # Mapping from config symbol to Quotex asset name
        self._asset_name_map: Dict[str, str] = {}

        # Track websocket generating-candle timestamps for diagnostics
        self._last_ws_generating_ts: Dict[str, int] = {}

        # Rolling tick-to-candle buffers when pyquotex returns single tick payloads
        self._tick_candle_buffers: Dict[str, Dict[int, dict]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the service: connect, load history, and begin polling."""
        logger.info("Starting QuotexServiceMultiAsync...")

        success = await self._connect()
        if not success:
            logger.error("Failed to connect to Quotex")
            if self.on_auth_failure_callback:
                self.on_auth_failure_callback()
            return

        # Subscribe to real-time streams
        await self._subscribe_to_instruments()

        # Load historical candles before polling
        await self._load_all_historical_candles()

        # Start polling tasks
        self._should_poll = True
        for symbol in Config.QUOTEX.assets:
            task = asyncio.create_task(self._poll_instrument(symbol))
            self.poll_tasks.append(task)

        # Start reconnection monitor
        reconnect_task = asyncio.create_task(self._reconnect_loop())
        self.poll_tasks.append(reconnect_task)

        logger.info(
            f"Quotex Multi-Service started | "
            f"Monitoring {len(Config.QUOTEX.assets)} instruments | "
            f"Poll tasks: {len(self.poll_tasks)}"
        )

        try:
            await asyncio.gather(*self.poll_tasks)
        except asyncio.CancelledError:
            logger.info("Polling tasks cancelled")
        except Exception as e:
            logger.error(f"Error in polling tasks: {e}", exc_info=True)

    async def stop(self) -> None:
        """Stop polling and disconnect from Quotex."""
        self._should_poll = False

        for task in self.poll_tasks:
            task.cancel()

        if self.poll_tasks:
            await asyncio.gather(*self.poll_tasks, return_exceptions=True)

        if self.client:
            try:
                for symbol in Config.QUOTEX.assets:
                    self.client.stop_candles_stream(symbol)
            except Exception:
                pass
            try:
                self.client.close()
            except Exception:
                pass

        logger.info("Quotex service stopped")

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _inject_session_file(self) -> None:
        """
        Create or overwrite pyquotex session.json with a token-based session.

        pyquotex reads session data from session.json keyed by user-agent.
        With default Quotex constructor settings, that key is "Quotex/1.0".
        """
        session_path = Path.cwd() / "session.json"
        session_payload = {
            "Quotex/1.0": {
                "cookies": None,
                "token": Config.QUOTEX.ssid,
                "user_agent": "Quotex/1.0",
            }
        }
        session_path.write_text(json.dumps(session_payload, indent=4), encoding="utf-8")
        logger.info(
            "Quotex session.json injected for SESSION auth method | "
            f"Path: {session_path} | Token length: {len(Config.QUOTEX.ssid)}"
        )

    async def _connect(self) -> bool:
        """
        Authenticate and connect to Quotex.

        Returns:
            True if connection succeeded, False otherwise.
        """
        try:
            logger.info(
                "Connecting to Quotex | "
                f"Method: {Config.QUOTEX.auth_method} | "
                f"Assets: {', '.join(Config.QUOTEX.assets)} | "
                f"Timeout: {Config.QUOTEX.connect_timeout_seconds}s | "
                f"WS debug: {Config.QUOTEX.ws_debug}"
            )

            if Config.QUOTEX.auth_method == "SESSION":
                self._inject_session_file()
                # Non-empty placeholders avoid pyquotex prompting for credentials.
                self.client = Quotex(
                    email="SESSION_AUTH",
                    password="SESSION_AUTH",
                    lang="en",
                )
            else:
                self.client = Quotex(
                    email=Config.QUOTEX.email,
                    password=Config.QUOTEX.password,
                    lang="en",
                )

            self.client.debug_ws_enable = Config.QUOTEX.ws_debug

            logger.info("Quotex login flow started (before client.connect)")
            connect_started_at = time.time()
            check_connect, message = await asyncio.wait_for(
                self.client.connect(),
                timeout=Config.QUOTEX.connect_timeout_seconds,
            )
            connect_elapsed = time.time() - connect_started_at

            logger.info(
                "Quotex login flow finished (after client.connect) | "
                f"Success: {check_connect} | Message: {message} | "
                f"Elapsed: {connect_elapsed:.2f}s"
            )

            if not check_connect:
                if Config.QUOTEX.auth_method == "SESSION":
                    logger.critical(
                        "Quotex SESSION authentication failed. Token may be expired. "
                        "No credentials fallback will be attempted."
                    )
                logger.error(f"Quotex connection failed: {message}")
                return False

            if (
                Config.QUOTEX.auth_method == "SESSION"
                and isinstance(message, str)
                and "token rejected" in message.lower()
            ):
                logger.critical(
                    "Quotex SESSION token rejected. No credentials fallback will be attempted."
                )
                return False

            if isinstance(message, str) and "token rejected" in message.lower():
                logger.warning(
                    "Quotex reported 'Token Rejected' during connect. "
                    "Connection may be unstable for historical candles."
                )

            logger.info("Connected to Quotex successfully")

            # Switch to practice account
            logger.info("Switching Quotex account mode to PRACTICE")
            await asyncio.wait_for(
                self.client.change_account("PRACTICE"),
                timeout=Config.QUOTEX.request_timeout_seconds,
            )
            logger.info("Using PRACTICE account")

            return True

        except asyncio.TimeoutError:
            logger.critical(
                "Quotex connect timeout reached. "
                f"No response in {Config.QUOTEX.connect_timeout_seconds}s"
            )
            return False

        except Exception as e:
            logger.error(f"Error connecting to Quotex: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    async def _subscribe_to_instruments(self) -> None:
        """Subscribe to real-time candle streams for all target instruments."""
        if not self.client:
            return

        for symbol in Config.QUOTEX.assets:
            try:
                logger.info(f"Resolving Quotex asset availability for symbol: {symbol}")
                asset_name, asset_data = await asyncio.wait_for(
                    self.client.get_available_asset(symbol, force_open=False),
                    timeout=Config.QUOTEX.request_timeout_seconds,
                )
                if not asset_data or (isinstance(asset_data, tuple) and not asset_data[2]):
                    logger.warning(f"Asset {symbol} is not available/open, skipping")
                    continue

                if asset_name != symbol:
                    logger.warning(
                        f"Resolved asset differs from requested symbol | "
                        f"Requested: {symbol} | Resolved: {asset_name}"
                    )

                self._asset_name_map[symbol] = asset_name
                self.client.start_candles_stream(asset_name, period=60)
                logger.info(
                    f"Subscribed to candle stream for {asset_name} "
                    f"(requested symbol: {symbol})"
                )

            except asyncio.TimeoutError:
                logger.error(
                    f"Timeout resolving/subscribing asset {symbol} after "
                    f"{Config.QUOTEX.request_timeout_seconds}s"
                )
            except Exception as e:
                logger.error(f"Error subscribing to {symbol}: {e}")

    # ------------------------------------------------------------------
    # Historical loading
    # ------------------------------------------------------------------

    def _resolve_asset_name(self, symbol: str) -> str:
        """Resolves the Quotex asset name for a given symbol."""
        return self._asset_name_map.get(symbol, symbol)

    def _normalize_realtime_candles(
        self, raw_payload: object, symbol: str
    ) -> Dict[int, dict]:
        """
        Normalize realtime payload from pyquotex across versions.

        pyquotex may return either:
        - dict[timestamp] -> candle dict
        - list of ticks in format [symbol, timestamp, price, direction]
        """
        buffer = self._tick_candle_buffers.setdefault(symbol, {})

        if isinstance(raw_payload, dict):
            # Merge dict payload into rolling buffer to keep candle continuity.
            for ts, candle in raw_payload.items():
                buffer[int(ts)] = candle
            self._trim_tick_buffer(symbol)
            return raw_payload

        if isinstance(raw_payload, list):
            # Single tick format: [symbol, timestamp, price, direction]
            if len(raw_payload) >= 4 and isinstance(raw_payload[0], str):
                process_tick(raw_payload, 60, buffer)
                self._trim_tick_buffer(symbol)
                return dict(buffer)

            # Batch tick format: [[symbol, timestamp, price, direction], ...]
            for tick in raw_payload:
                if isinstance(tick, list) and len(tick) >= 4:
                    process_tick(tick, 60, buffer)
            if buffer:
                self._trim_tick_buffer(symbol)
                logger.debug(
                    f"Realtime payload normalized from list to candles for {symbol} | "
                    f"Count: {len(buffer)}"
                )
            return dict(buffer)

        logger.debug(
            f"Realtime payload type not supported for {symbol}: {type(raw_payload).__name__}"
        )
        return {}

    def _trim_tick_buffer(self, symbol: str, keep_last: int = 300) -> None:
        """Keep only the most recent N aggregated realtime candles per symbol."""
        buffer = self._tick_candle_buffers.get(symbol)
        if not buffer or len(buffer) <= keep_last:
            return

        sorted_keys = sorted(buffer.keys())
        for key in sorted_keys[:-keep_last]:
            buffer.pop(key, None)

    async def _load_all_historical_candles(self) -> None:
        """
        Load historical candles to initialize indicator buffers.
        Strategy: request (EMA_PERIOD * 3) + 1 candles, discard the last
        (in-formation) and feed the rest to AnalysisService.
        """
        min_candles_required = Config.EMA_PERIOD * 3
        count_to_request = min_candles_required + 1

        logger.info(
            f"INIT: Requesting {count_to_request} historical candles per asset..."
        )

        for symbol in Config.QUOTEX.assets:
            try:
                logger.info(f"Historical bootstrap started for {symbol}")
                historical_candles = await self._get_historical_candles(
                    symbol, count_to_request
                )

                if not historical_candles:
                    logger.warning(f"No historical candles received for {symbol}")
                    continue

                # Discard last candle (currently forming)
                current_generating_candle = historical_candles[-1]
                closed_candles = historical_candles[:-1]

                if not closed_candles:
                    logger.warning(f"Insufficient closed candles for {symbol}")
                    continue

                last_closed = closed_candles[-1]
                self.last_candle_timestamps[symbol] = last_closed.timestamp
                self.current_candle_timestamps[symbol] = (
                    current_generating_candle.timestamp
                )

                if self.analysis_service:
                    self.analysis_service.load_historical_candles(closed_candles)
                    logger.info(
                        f"{symbol}: {len(closed_candles)} historical candles "
                        f"loaded into AnalysisService"
                    )

                    if Config.GENERATE_HISTORICAL_CHARTS:
                        source_key = f"{last_closed.source}_{symbol}"
                        await self.analysis_service.generate_initial_chart(
                            source_key, last_closed
                        )

                logger.info(f"Historical bootstrap finished for {symbol}")

            except Exception as e:
                logger.error(
                    f"Critical error loading history for {symbol}: {e}",
                    exc_info=True,
                )

    async def _get_historical_candles(
        self, symbol: str, count: int
    ) -> List[CandleData]:
        """
        Fetch historical 1-minute candles from Quotex.

        Args:
            symbol: Instrument symbol (e.g. "EURUSD_otc").
            count: Number of candles to request.

        Returns:
            Sorted list of CandleData, oldest first.
        """
        if not self.client:
            return []

        try:
            logger.info(f"Requesting {count} historical candles for {symbol}...")
            end_time = time.time()
            offset_seconds = max(count * 60, 60)
            asset_name = self._resolve_asset_name(symbol)

            candidate_assets: List[str] = []
            for candidate in (asset_name, symbol):
                if candidate and candidate not in candidate_assets:
                    candidate_assets.append(candidate)

            # Keep bootstrap bounded: at most 2 attempts before continuing startup.
            fallback_offset = min(offset_seconds, 3600)
            attempt_plan: List[tuple[str, int]] = []

            if candidate_assets:
                attempt_plan.append((candidate_assets[0], offset_seconds))

            if len(candidate_assets) > 1:
                attempt_plan.append((candidate_assets[1], fallback_offset))
            elif candidate_assets:
                attempt_plan.append((candidate_assets[0], fallback_offset))

            attempt_plan = attempt_plan[:2]

            history_timeout = Config.QUOTEX.request_timeout_seconds

            raw_candles: List[dict] = []
            selected_asset: Optional[str] = None
            selected_offset: Optional[int] = None

            for attempt_index, (candidate_asset, candidate_offset) in enumerate(
                attempt_plan, start=1
            ):
                logger.debug(
                    f"Historical request payload | Symbol: {symbol} | "
                    f"Attempt: {attempt_index}/2 | Candidate asset: {candidate_asset} | "
                    f"Offset seconds: {candidate_offset}"
                )
                try:
                    raw_candles = await asyncio.wait_for(
                        self.client.get_candles(
                            candidate_asset, end_time, candidate_offset, 60
                        ),
                        timeout=history_timeout,
                    )
                    if raw_candles:
                        selected_asset = candidate_asset
                        selected_offset = candidate_offset
                        break
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Historical request timeout for {candidate_asset} "
                        f"with offset={candidate_offset}s (attempt {attempt_index}/2)"
                    )
                except Exception as request_error:
                    logger.warning(
                        f"Historical request error for {candidate_asset} "
                        f"with offset={candidate_offset}s (attempt {attempt_index}/2): "
                        f"{request_error}"
                    )

            if not raw_candles:
                logger.warning(
                    f"Historical request returned empty payload for {symbol} "
                    f"after {len(attempt_plan)} attempts. Continuing without historical bootstrap. "
                    f"Attempt plan={attempt_plan}"
                )
                return []

            logger.debug(
                f"Raw historical candle count for {symbol}: {len(raw_candles)} | "
                f"Selected asset: {selected_asset} | Offset: {selected_offset}s"
            )

            candle_list: List[CandleData] = []
            for raw in raw_candles:
                try:
                    candle_list.append(self._map_historical_candle(raw, symbol))
                except Exception:
                    continue

            candle_list.sort(key=lambda c: c.timestamp)
            logger.info(f"Received {len(candle_list)} candles for {symbol}")
            return candle_list

        except asyncio.TimeoutError:
            logger.error(
                f"Timeout fetching historical candles for {symbol} after "
                f"{Config.QUOTEX.request_timeout_seconds}s"
            )
            return []
        except Exception as e:
            logger.error(f"Error fetching candles for {symbol}: {e}")
            return []

    # ------------------------------------------------------------------
    # Polling (Sleep & Burst)
    # ------------------------------------------------------------------

    async def _poll_instrument(self, symbol: str) -> None:
        """
        Polling loop for a single instrument using Sleep & Burst strategy.

        1. Sleep until second 59 of the current minute.
        2. Burst-poll at 100 ms intervals for up to 5 seconds.
        3. Detect a new candle by comparing timestamps.

        Args:
            symbol: Instrument symbol to poll.
        """
        logger.info(f"Starting intelligent polling loop for {symbol}...")

        while self._should_poll:
            try:
                # PHASE 0: Pre-check (cover boundary crossing during startup)
                await self._check_and_process_candle(symbol)

                # PHASE 1: Sleep until second 59
                now = datetime.now()
                target_time = now.replace(second=59, microsecond=0)

                if now > target_time:
                    target_time += timedelta(minutes=1)

                wait_seconds = (target_time - now).total_seconds()
                if wait_seconds > 0.1:
                    logger.debug(
                        f"{symbol} sleeping {wait_seconds:.2f}s until burst..."
                    )
                    await asyncio.sleep(wait_seconds)

                # PHASE 2: Burst polling
                logger.debug(f"{symbol} starting BURST polling...")
                candle_detected = False
                burst_start = time.time()

                while self._should_poll and (time.time() - burst_start < 5.0):
                    if await self._check_and_process_candle(symbol):
                        candle_detected = True
                        break

                    await asyncio.sleep(0.1)

                if not candle_detected:
                    logger.debug(f"{symbol} burst finished without new candle")

            except asyncio.CancelledError:
                logger.info(f"Polling cancelled for {symbol}")
                break
            except Exception as e:
                logger.error(
                    f"Error in polling loop for {symbol}: {e}", exc_info=True
                )
                await asyncio.sleep(1.0)

    async def _check_and_process_candle(self, symbol: str) -> bool:
        """
        Check if a new closed candle is available and process it.
        Also detects and fills data gaps from disconnections.

        Args:
            symbol: Instrument symbol.

        Returns:
            True if a new candle was detected and processed.
        """
        try:
            if not self.client:
                return False

            asset_name = self._resolve_asset_name(symbol)
            candles = await asyncio.wait_for(
                self.client.get_realtime_candles(asset_name),
                timeout=Config.QUOTEX.request_timeout_seconds,
            )
            candles = self._normalize_realtime_candles(candles, symbol)

            if (not candles) and asset_name != symbol:
                logger.debug(
                    f"Realtime fallback request for {symbol} because {asset_name} returned empty"
                )
                fallback_candles = await asyncio.wait_for(
                    self.client.get_realtime_candles(symbol),
                    timeout=Config.QUOTEX.request_timeout_seconds,
                )
                candles = self._normalize_realtime_candles(fallback_candles, symbol)

            if not candles:
                logger.debug(f"Realtime websocket payload empty for {symbol}")
                return False

            timestamps = sorted(candles.keys())
            if len(timestamps) < 2:
                logger.debug(
                    f"Realtime websocket payload has insufficient points for {symbol}: "
                    f"{len(timestamps)}"
                )
                return False

            # Second-to-last is the most recent closed candle
            closed_ts = int(timestamps[-2])
            closed_candle_dict = candles[timestamps[-2]]
            new_generating_candle_dict = candles[timestamps[-1]]
            generating_ts = int(timestamps[-1])

            previous_generating_ts = self._last_ws_generating_ts.get(symbol)
            if previous_generating_ts != generating_ts:
                logger.debug(
                    f"WebSocket update {symbol} | "
                    f"Generating TS changed: {previous_generating_ts} -> {generating_ts}"
                )
                self._last_ws_generating_ts[symbol] = generating_ts

            last_stored_ts = self.last_candle_timestamps.get(symbol, 0)

            # Gap detection
            if last_stored_ts > 0 and (closed_ts - last_stored_ts) > 60:
                logger.warning(
                    f"GAP DETECTED in {symbol}: Last {last_stored_ts} -> "
                    f"New {closed_ts} (Diff: {closed_ts - last_stored_ts}s)"
                )
                await self._fill_data_gaps(symbol, last_stored_ts, closed_ts)
                last_stored_ts = self.last_candle_timestamps.get(symbol, 0)

            # New candle detection
            if closed_ts > last_stored_ts:
                logger.info(
                    f"NEW CANDLE DETECTED {symbol} | "
                    f"TS: {closed_ts} (Previous: {last_stored_ts})"
                )
                await self._process_new_candle(
                    symbol, closed_candle_dict, new_generating_candle_dict,
                    closed_ts, generating_ts
                )
                return True

            return False

        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout reading realtime candles for {symbol} after "
                f"{Config.QUOTEX.request_timeout_seconds}s"
            )
            return False
        except Exception as e:
            logger.error(
                f"Error in check_and_process_candle {symbol}: {e}"
            )
            return False

    async def _process_new_candle(
        self,
        symbol: str,
        closed_candle_dict: dict,
        new_generating_candle_dict: dict,
        closed_ts: int,
        generating_ts: int,
    ) -> None:
        """
        Process a newly closed candle: map to CandleData and send to AnalysisService.

        Args:
            symbol: Instrument symbol.
            closed_candle_dict: Raw dict of the closed candle.
            new_generating_candle_dict: Raw dict of the currently forming candle.
            closed_ts: Timestamp of the closed candle.
            generating_ts: Timestamp of the generating candle.
        """
        try:
            self.last_candle_timestamps[symbol] = closed_ts
            self.current_candle_timestamps[symbol] = generating_ts

            closed_candle = self._map_realtime_candle(
                closed_candle_dict, closed_ts, symbol
            )

            if closed_candle and self.analysis_service:
                await self.analysis_service.process_realtime_candle(closed_candle)

                closed_time_str = datetime.fromtimestamp(closed_ts).strftime(
                    "%H:%M:%S"
                )
                logger.info(
                    f"Candle processed {symbol} @ {closed_time_str} | "
                    f"Close: {closed_candle.close}"
                )

        except Exception as e:
            logger.error(
                f"Error processing new candle {symbol}: {e}", exc_info=True
            )

    # ------------------------------------------------------------------
    # Gap filling
    # ------------------------------------------------------------------

    async def _fill_data_gaps(
        self, symbol: str, last_stored_ts: int, current_ts: int
    ) -> None:
        """
        Fill data gaps by fetching missing historical candles.

        Args:
            symbol: Instrument symbol.
            last_stored_ts: Timestamp of the last known closed candle.
            current_ts: Timestamp of the newest closed candle detected.
        """
        try:
            missing_seconds = current_ts - last_stored_ts
            candles_needed = int(missing_seconds / 60)

            if candles_needed <= 0:
                return

            logger.info(
                f"Filling GAP of {candles_needed} candles for {symbol}..."
            )

            historical_candles = await self._get_historical_candles(
                symbol, candles_needed + 2
            )

            if not historical_candles:
                logger.warning(
                    f"Could not recover candles for gap in {symbol}"
                )
                return

            gap_candles = [
                c
                for c in historical_candles
                if last_stored_ts < c.timestamp <= current_ts
            ]

            if gap_candles:
                logger.info(
                    f"Recovered {len(gap_candles)} gap candles for {symbol}"
                )
                for candle in gap_candles:
                    if self.analysis_service:
                        await self.analysis_service.process_realtime_candle(
                            candle
                        )

                self.last_candle_timestamps[symbol] = gap_candles[-1].timestamp

        except Exception as e:
            logger.error(
                f"Error filling gap for {symbol}: {e}", exc_info=True
            )

    # ------------------------------------------------------------------
    # Candle mapping
    # ------------------------------------------------------------------

    def _map_historical_candle(self, raw_candle: dict, symbol: str) -> CandleData:
        """
        Map a Quotex historical candle dict to CandleData.

        Quotex format: {"time": int, "open": float, "close": float,
                        "high": float, "low": float, "ticks": int}

        Args:
            raw_candle: Raw candle dict from pyquotex.
            symbol: Instrument symbol.

        Returns:
            CandleData instance with source="QX".
        """
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

    def _map_realtime_candle(
        self, raw_candle: dict, timestamp: int, symbol: str
    ) -> Optional[CandleData]:
        """
        Map a Quotex real-time candle dict to CandleData.

        Quotex real-time format: {"open": float, "close": float,
                                  "high": float, "low": float, "symbol": str}
        The timestamp comes from the dict key, not the candle body.

        Args:
            raw_candle: Raw candle dict from pyquotex real-time stream.
            timestamp: Unix timestamp (dict key) for the candle.
            symbol: Instrument symbol.

        Returns:
            CandleData instance with source="QX", or None on error.
        """
        try:
            high = float(raw_candle.get("high") or raw_candle.get("max", 0))
            low = float(raw_candle.get("low") or raw_candle.get("min", 0))
            if high == 0:
                return None

            return CandleData(
                timestamp=int(timestamp),
                open=float(raw_candle["open"]),
                high=high,
                low=low,
                close=float(raw_candle["close"]),
                volume=0.0,
                source="QX",
                symbol=symbol,
            )
        except Exception as e:
            logger.error(f"Error mapping real-time candle: {e}")
            return None

    # ------------------------------------------------------------------
    # Reconnection
    # ------------------------------------------------------------------

    async def _reconnect_loop(self) -> None:
        """
        Reconnection loop with exponential backoff.
        Uses Config.RECONNECT_INITIAL_TIMEOUT and Config.RECONNECT_MAX_TIMEOUT.
        """
        attempt = 0
        current_timeout = Config.RECONNECT_INITIAL_TIMEOUT

        while self._should_poll:
            await asyncio.sleep(1)

            if not self._should_poll:
                break

            # Simple liveness check — if the client lost connection
            if self.client is None:
                continue

            try:
                # Attempt a lightweight operation to verify connectivity
                first_symbol = Config.QUOTEX.assets[0]
                first_asset = self._resolve_asset_name(first_symbol)
                candles = await asyncio.wait_for(
                    self.client.get_realtime_candles(first_asset),
                    timeout=Config.QUOTEX.request_timeout_seconds,
                )
                if candles is not None:
                    logger.debug("Reconnection liveness check OK")
                    # Connection is alive — reset backoff
                    if attempt > 0:
                        attempt = 0
                        current_timeout = Config.RECONNECT_INITIAL_TIMEOUT
                    continue
            except asyncio.TimeoutError:
                logger.warning(
                    "Reconnection liveness check timeout after "
                    f"{Config.QUOTEX.request_timeout_seconds}s"
                )
            except Exception:
                pass

            logger.warning(
                f"Connection lost. Reconnecting in {current_timeout}s... "
                f"(Attempt {attempt + 1})"
            )
            await asyncio.sleep(current_timeout)

            if await self._connect():
                logger.info("Reconnection successful")
                await self._subscribe_to_instruments()
                attempt = 0
                current_timeout = Config.RECONNECT_INITIAL_TIMEOUT
            else:
                attempt += 1
                current_timeout = min(
                    current_timeout * 2, Config.RECONNECT_MAX_TIMEOUT
                )
                logger.error(
                    f"Reconnection failed. Next attempt in {current_timeout}s"
                )


# =============================================================================
# FACTORY
# =============================================================================


def create_quotex_service_multi_async(
    analysis_service,
    on_auth_failure_callback: Optional[Callable] = None,
) -> QuotexServiceMultiAsync:
    """
    Factory function to create the Quotex async multi-instrument service.

    Args:
        analysis_service: AnalysisService instance for candle processing.
        on_auth_failure_callback: Optional callback for auth failures.

    Returns:
        Configured QuotexServiceMultiAsync instance.
    """
    return QuotexServiceMultiAsync(analysis_service, on_auth_failure_callback)
