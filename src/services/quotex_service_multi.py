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
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Callable, List

from quotexpy import Quotex

from config import Config
from src.services.connection_service import CandleData

logger = logging.getLogger(__name__)


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
        for symbol in Config.TARGET_ASSETS:
            task = asyncio.create_task(self._poll_instrument(symbol))
            self.poll_tasks.append(task)

        # Start reconnection monitor
        reconnect_task = asyncio.create_task(self._reconnect_loop())
        self.poll_tasks.append(reconnect_task)

        logger.info(
            f"Quotex Multi-Service started | "
            f"Monitoring {len(Config.TARGET_ASSETS)} instruments | "
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
                for symbol in Config.TARGET_ASSETS:
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

    async def _connect(self) -> bool:
        """
        Authenticate and connect to Quotex.

        Returns:
            True if connection succeeded, False otherwise.
        """
        try:
            logger.info("Connecting to Quotex...")
            self.client = Quotex(
                email=Config.QUOTEX.email,
                password=Config.QUOTEX.password,
                lang="en",
            )

            check_connect, message = await self.client.connect()

            if not check_connect:
                logger.error(f"Quotex connection failed: {message}")
                return False

            logger.info("Connected to Quotex successfully")

            # Switch to practice account
            await self.client.change_account("PRACTICE")
            logger.info("Using PRACTICE account")

            return True

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

        for symbol in Config.TARGET_ASSETS:
            try:
                asset_name, asset_data = await self.client.get_available_asset(
                    symbol, force_open=True
                )
                if not asset_data or (isinstance(asset_data, tuple) and not asset_data[2]):
                    logger.warning(f"Asset {symbol} is not available/open, skipping")
                    continue

                self._asset_name_map[symbol] = asset_name
                self.client.start_candles_stream(asset_name, period=60)
                logger.info(f"Subscribed to candle stream for {asset_name}")

            except Exception as e:
                logger.error(f"Error subscribing to {symbol}: {e}")

    # ------------------------------------------------------------------
    # Historical loading
    # ------------------------------------------------------------------

    def _resolve_asset_name(self, symbol: str) -> str:
        """Resolves the Quotex asset name for a given symbol."""
        return self._asset_name_map.get(symbol, symbol)

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

        for symbol in Config.TARGET_ASSETS:
            try:
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
            offset_seconds = count * 60
            asset_name = self._resolve_asset_name(symbol)
            raw_candles = await self.client.get_candles(
                asset_name, end_time, offset_seconds, 60
            )

            if not raw_candles:
                return []

            candle_list: List[CandleData] = []
            for raw in raw_candles:
                try:
                    candle_list.append(self._map_historical_candle(raw, symbol))
                except Exception:
                    continue

            candle_list.sort(key=lambda c: c.timestamp)
            logger.info(f"Received {len(candle_list)} candles for {symbol}")
            return candle_list

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
            candles = await self.client.get_realtime_candles(asset_name)

            if not candles:
                return False

            timestamps = sorted(candles.keys())
            if len(timestamps) < 2:
                return False

            # Second-to-last is the most recent closed candle
            closed_ts = int(timestamps[-2])
            closed_candle_dict = candles[timestamps[-2]]
            new_generating_candle_dict = candles[timestamps[-1]]

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
                    closed_ts, int(timestamps[-1])
                )
                return True

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
                candles = await self.client.get_realtime_candles(
                    Config.TARGET_ASSETS[0]
                )
                if candles is not None:
                    # Connection is alive — reset backoff
                    if attempt > 0:
                        attempt = 0
                        current_timeout = Config.RECONNECT_INITIAL_TIMEOUT
                    continue
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
