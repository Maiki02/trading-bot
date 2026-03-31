"""Quotex market data service with one isolated client per symbol."""

import asyncio
import inspect
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Set

if TYPE_CHECKING:
    from src.logic.analysis_service import AnalysisService


def _bootstrap_local_pyquotex() -> Optional[Path]:
    """Prioritize sibling ../pyquotex repository when present."""
    repo_root = Path(__file__).resolve().parents[2]
    local_pyquotex_dir = repo_root.parent / "pyquotex"

    if not local_pyquotex_dir.is_dir():
        return None

    local_repo_root = str(local_pyquotex_dir)
    if local_repo_root in sys.path:
        sys.path.remove(local_repo_root)
    sys.path.insert(0, local_repo_root)
    return local_pyquotex_dir


_LOCAL_PYQUOTEX_DIR = _bootstrap_local_pyquotex()

try:
    from pyquotex.stable_api import Quotex
    from pyquotex.utils.processor import process_tick
except ModuleNotFoundError as exc:
    if exc.name and not exc.name.startswith("pyquotex"):
        raise

    if _LOCAL_PYQUOTEX_DIR is None:
        location_message = "Sibling repository '../pyquotex' was not found."
    else:
        location_message = (
            f"Local repository was found at '{_LOCAL_PYQUOTEX_DIR}', "
            "but import still failed."
        )

    raise ModuleNotFoundError(
        "pyquotex is required when DATA_PROVIDER=QUOTEX. "
        f"{location_message} "
        "Install local dependency with 'pip install -e ../pyquotex' "
        "or provide pyquotex in the active environment."
    ) from exc

from config import Config
from src.services.connection_service import CandleData
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def _maybe_await(result: object) -> None:
    """Await a value only when pyquotex returns a coroutine."""
    if inspect.isawaitable(result):
        await result


class _QuotexSymbolWorker:
    """Handles the full Quotex lifecycle for a single symbol."""

    _REALTIME_MISMATCH_GUARD_SECONDS = 15.0
    _MISMATCH_LOG_THROTTLE_SECONDS = 5.0
    _AMBIGUOUS_DROP_LOG_THROTTLE_SECONDS = 15.0

    def __init__(
        self,
        symbol: str,
        analysis_service: Optional["AnalysisService"],
        on_auth_failure_callback: Optional[Callable[[], None]] = None,
    ):
        self.symbol = symbol
        self.analysis_service = analysis_service
        self.on_auth_failure_callback = on_auth_failure_callback

        self.client: Optional[Quotex] = None
        self.asset_name = symbol
        self.is_active_symbol = False
        self._history_loaded = False
        self._should_run = False
        self._tasks: List[asyncio.Task] = []

        self.last_candle_timestamp = 0
        self.current_candle_timestamp = 0
        self._last_ws_generating_ts = 0
        self._last_generating_only_log_at = 0.0
        self._realtime_sync_established = False
        self._processed_closed_timestamps: Set[int] = set()
        self._tick_candle_buffer: Dict[int, dict] = {}
        self._last_realtime_symbol_mismatch_at = 0.0
        self._last_realtime_mismatch_log_at = 0.0
        self._last_ambiguous_drop_log_at = 0.0
        self._expected_realtime_symbols = self._build_safe_expected_symbols()

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Normalizes symbol names for safe comparisons across providers."""
        return symbol.strip().lower().replace("-", "_")

    @staticmethod
    def _strip_otc_suffix(normalized_symbol: str) -> str:
        """Removes OTC suffix from a normalized symbol representation."""
        if normalized_symbol.endswith("_otc"):
            return normalized_symbol[:-4]
        return normalized_symbol

    @staticmethod
    def _toggle_otc_suffix(normalized_symbol: str) -> str:
        """Adds/removes OTC suffix from a normalized symbol representation."""
        if normalized_symbol.endswith("_otc"):
            return normalized_symbol[:-4]
        return f"{normalized_symbol}_otc"

    def _build_safe_expected_symbols(self) -> Set[str]:
        """Builds the explicit and safe symbol aliases allowed for this worker."""
        normalized_symbol = self._normalize_symbol(self.symbol)
        expected = {normalized_symbol}

        configured_assets = {
            self._normalize_symbol(asset)
            for asset in Config.QUOTEX.assets
            if isinstance(asset, str) and asset.strip()
        }

        normalized_counterpart = self._toggle_otc_suffix(normalized_symbol)
        base_symbol = self._strip_otc_suffix(normalized_symbol)
        counterpart_base = self._strip_otc_suffix(normalized_counterpart)

        if (
            base_symbol == counterpart_base
            and normalized_symbol in configured_assets
            and normalized_counterpart in configured_assets
        ):
            expected.add(normalized_counterpart)

        return expected

    def _is_safe_binding_symbol(self, candidate_symbol: Optional[str]) -> bool:
        """Returns whether a resolved broker symbol is explicitly safe for this worker."""
        if not candidate_symbol or not isinstance(candidate_symbol, str):
            return False

        return self._normalize_symbol(candidate_symbol) in self._expected_realtime_symbols

    async def start(self) -> None:
        """Connects and maintains the dedicated symbol worker."""
        logger.info(f"Starting Quotex worker for {self.symbol}")

        if not await self._connect():
            logger.error(f"Failed to connect Quotex worker for {self.symbol}")
            if self.on_auth_failure_callback:
                self.on_auth_failure_callback()
            return

        self.is_active_symbol = await self._resolve_symbol_availability()
        if not self.is_active_symbol:
            logger.warning(
                f"Quotex worker for {self.symbol} will stay idle because the asset is closed"
            )
            await self._disconnect_client()
            return

        await self._subscribe_to_instrument()
        await self._load_historical_candles()

        self._should_run = True
        self._tasks = [
            asyncio.create_task(self._poll_instrument(), name=f"quotex-poll-{self.symbol}"),
            asyncio.create_task(
                self._reconnect_loop(),
                name=f"quotex-reconnect-{self.symbol}",
            ),
        ]

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info(f"Quotex worker cancelled for {self.symbol}")
        except Exception as exc:
            logger.error(
                f"Unhandled error in Quotex worker for {self.symbol}: {exc}",
                exc_info=True,
            )
        finally:
            self._tasks.clear()

    async def stop(self) -> None:
        """Stops polling and closes the dedicated client."""
        self._should_run = False

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        await self._disconnect_client()
        logger.info(f"Quotex worker stopped for {self.symbol}")

    async def _disconnect_client(self) -> None:
        """Stops the stream and closes the dedicated Quotex client."""
        if not self.client:
            return

        try:
            await _maybe_await(self.client.stop_candles_stream(self.asset_name))
        except Exception:
            pass

        try:
            if self.asset_name != self.symbol:
                await _maybe_await(self.client.stop_candles_stream(self.symbol))
        except Exception:
            pass

        try:
            await _maybe_await(self.client.close())
        except Exception:
            pass

        self.client = None

    async def _connect(self) -> bool:
        """Authenticates a dedicated Quotex client for the symbol."""
        try:
            logger.info(
                f"Connecting Quotex worker for {self.symbol} | "
                f"Timeout: {Config.QUOTEX.connect_timeout_seconds}s | "
                f"WS debug: {Config.QUOTEX.ws_debug}"
            )

            self.client = Quotex(
                email=Config.QUOTEX.email,
                password=Config.QUOTEX.password,
                lang="en",
            )
            self.client.debug_ws_enable = Config.QUOTEX.ws_debug

            started_at = time.time()
            check_connect, message = await asyncio.wait_for(
                self.client.connect(),
                timeout=Config.QUOTEX.connect_timeout_seconds,
            )
            elapsed = time.time() - started_at

            logger.info(
                f"Quotex login finished for {self.symbol} | "
                f"Success: {check_connect} | Message: {message} | "
                f"Elapsed: {elapsed:.2f}s"
            )

            if not check_connect:
                await self._disconnect_client()
                return False

            if isinstance(message, str) and "token rejected" in message.lower():
                logger.warning(
                    f"Quotex reported token rejection for {self.symbol}. The connection may be unstable."
                )

            await asyncio.wait_for(
                self.client.change_account("PRACTICE"),
                timeout=Config.QUOTEX.request_timeout_seconds,
            )
            return True

        except asyncio.TimeoutError:
            logger.critical(
                f"Quotex connect timeout for {self.symbol} after "
                f"{Config.QUOTEX.connect_timeout_seconds}s"
            )
            await self._disconnect_client()
            return False
        except Exception as exc:
            logger.error(
                f"Error connecting Quotex worker for {self.symbol}: {exc}",
                exc_info=True,
            )
            await self._disconnect_client()
            return False

    def _is_asset_open(self, asset_data: object) -> bool:
        """Best-effort check for Quotex asset open state."""
        if asset_data is None:
            return False

        if isinstance(asset_data, bool):
            return asset_data

        if isinstance(asset_data, dict):
            for key in (
                "open",
                "is_open",
                "isOpen",
                "active",
                "is_active",
                "enabled",
                "is_enabled",
            ):
                value = asset_data.get(key)
                if isinstance(value, bool):
                    return value
            return bool(asset_data)

        if isinstance(asset_data, (tuple, list)):
            if len(asset_data) >= 3 and isinstance(asset_data[2], bool):
                return asset_data[2]
            if len(asset_data) >= 2 and isinstance(asset_data[1], bool):
                return asset_data[1]
            return bool(asset_data)

        for attr in ("open", "is_open", "active", "enabled", "is_enabled"):
            value = getattr(asset_data, attr, None)
            if isinstance(value, bool):
                return value

        return bool(asset_data)

    async def _resolve_symbol_availability(self) -> bool:
        """Resolves the broker asset name and checks whether the symbol is open."""
        if not self.client:
            return False

        try:
            asset_name, asset_data = await asyncio.wait_for(
                self.client.get_available_asset(self.symbol, force_open=False),
                timeout=Config.QUOTEX.request_timeout_seconds,
            )

            if not self._is_asset_open(asset_data):
                logger.info(
                    f"Skipping Quotex worker for {self.symbol}: asset is closed"
                )
                return False

            resolved_asset_name = asset_name or self.symbol
            if not self._is_safe_binding_symbol(resolved_asset_name):
                logger.error(
                    f"Rejecting Quotex worker due to unsafe symbol remap | "
                    f"Requested: {self.symbol} | Resolved: {resolved_asset_name} | "
                    f"Allowed: {sorted(self._expected_realtime_symbols)}"
                )
                return False

            self.asset_name = resolved_asset_name
            return True

        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout checking Quotex asset status for {self.symbol} after "
                f"{Config.QUOTEX.request_timeout_seconds}s"
            )
            return False
        except Exception as exc:
            logger.warning(
                f"Error checking Quotex asset status for {self.symbol}: {exc}"
            )
            return False

    async def _subscribe_to_instrument(self) -> None:
        """Subscribes the dedicated client to its own candle stream."""
        if not self.client:
            return

        try:
            await _maybe_await(self.client.start_candles_stream(self.asset_name, period=60))
            logger.info(
                f"Subscribed Quotex candle stream for {self.symbol} using asset {self.asset_name}"
            )
        except Exception as exc:
            logger.error(f"Error subscribing Quotex stream for {self.symbol}: {exc}")

    @staticmethod
    def _extract_first_numeric(raw_candle: dict, keys: List[str]) -> Optional[float]:
        """Extracts the first numeric value available in the candidate keys."""
        for key in keys:
            if key in raw_candle and raw_candle[key] is not None:
                try:
                    return float(raw_candle[key])
                except (TypeError, ValueError):
                    continue
        return None

    def _extract_explicit_payload_symbol(self, raw_payload: object) -> Optional[str]:
        """Extracts symbol/asset when realtime payload explicitly includes one."""
        if isinstance(raw_payload, dict):
            for key in ("asset", "symbol", "instrument"):
                value = raw_payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return None

        if isinstance(raw_payload, list):
            if len(raw_payload) >= 4 and isinstance(raw_payload[0], str):
                return raw_payload[0].strip() if raw_payload[0].strip() else None

            if raw_payload and isinstance(raw_payload[0], list):
                first_tick = raw_payload[0]
                if first_tick and isinstance(first_tick[0], str) and first_tick[0].strip():
                    return first_tick[0].strip()

        return None

    def _is_realtime_payload_symbol_mismatch(self, payload_symbol: Optional[str]) -> bool:
        """Returns True when an explicit payload symbol conflicts with the worker symbol."""
        if not payload_symbol:
            return False

        expected_symbols = self._expected_realtime_symbols
        normalized_payload_symbol = self._normalize_symbol(payload_symbol)
        if normalized_payload_symbol in expected_symbols:
            return False

        now = time.time()
        self._last_realtime_symbol_mismatch_at = now
        if (now - self._last_realtime_mismatch_log_at) >= self._MISMATCH_LOG_THROTTLE_SECONDS:
            logger.warning(
                f"Discarding realtime payload due to symbol mismatch for {self.symbol} | "
                f"Payload symbol: {payload_symbol} | Expected: {sorted(expected_symbols)}"
            )
            self._last_realtime_mismatch_log_at = now
        return True

    def _has_recent_realtime_symbol_mismatch(self) -> bool:
        """Returns whether a recent mismatch suggests possible cross-symbol contamination."""
        if self._last_realtime_symbol_mismatch_at <= 0:
            return False

        return (
            time.time() - self._last_realtime_symbol_mismatch_at
        ) <= self._REALTIME_MISMATCH_GUARD_SECONDS

    def _extract_explicit_item_symbol(self, raw_item: object) -> Optional[str]:
        """Extracts symbol/asset from an individual realtime item when explicitly present."""
        if isinstance(raw_item, dict):
            for key in ("asset", "symbol", "instrument"):
                value = raw_item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return None

        if isinstance(raw_item, list) and len(raw_item) >= 4 and isinstance(raw_item[0], str):
            symbol = raw_item[0].strip()
            return symbol if symbol else None

        return None

    def _should_drop_ambiguous_payload(self) -> bool:
        """Drops symbol-ambiguous realtime payloads shortly after a mismatch event."""
        if not self._has_recent_realtime_symbol_mismatch():
            return False

        now = time.time()
        if (now - self._last_ambiguous_drop_log_at) >= self._AMBIGUOUS_DROP_LOG_THROTTLE_SECONDS:
            logger.warning(
                f"Discarding ambiguous realtime payload for {self.symbol}: "
                "no explicit symbol and recent mismatch detected"
            )
            self._last_ambiguous_drop_log_at = now
        return True

    def _normalize_realtime_candles(self, raw_payload: object) -> Dict[int, dict]:
        """Normalizes pyquotex realtime payloads into a timestamp-keyed candle map."""
        payload_symbol = self._extract_explicit_payload_symbol(raw_payload)
        if not payload_symbol and self._should_drop_ambiguous_payload():
            return {}

        if isinstance(raw_payload, dict):
            mismatched_items = 0
            for ts, candle in raw_payload.items():
                try:
                    timestamp = int(ts)
                except (TypeError, ValueError):
                    continue

                item_symbol = self._extract_explicit_item_symbol(candle)
                if self._is_realtime_payload_symbol_mismatch(item_symbol):
                    mismatched_items += 1
                    continue

                self._tick_candle_buffer[timestamp] = candle

            if mismatched_items:
                logger.debug(
                    f"Realtime dict payload filtered for {self.symbol}: "
                    f"discarded={mismatched_items} mismatched item(s)"
                )
            self._trim_tick_buffer()
            return dict(self._tick_candle_buffer)

        if isinstance(raw_payload, list):
            if len(raw_payload) >= 4 and isinstance(raw_payload[0], str):
                item_symbol = self._extract_explicit_item_symbol(raw_payload)
                if self._is_realtime_payload_symbol_mismatch(item_symbol):
                    return {}

                process_tick(raw_payload, 60, self._tick_candle_buffer)
                self._trim_tick_buffer()
                return dict(self._tick_candle_buffer)

            mismatched_items = 0
            for tick in raw_payload:
                if isinstance(tick, list) and len(tick) >= 4:
                    item_symbol = self._extract_explicit_item_symbol(tick)
                    if self._is_realtime_payload_symbol_mismatch(item_symbol):
                        mismatched_items += 1
                        continue

                    process_tick(tick, 60, self._tick_candle_buffer)

            if mismatched_items:
                logger.debug(
                    f"Realtime list payload filtered for {self.symbol}: "
                    f"discarded={mismatched_items} mismatched tick(s)"
                )

            self._trim_tick_buffer()
            return dict(self._tick_candle_buffer)

        logger.debug(
            f"Realtime payload type not supported for {self.symbol}: {type(raw_payload).__name__}"
        )
        return {}

    def _trim_tick_buffer(self) -> None:
        """Keeps only the most recent aggregated realtime candles."""
        keep_last = Config.QUOTEX_TICK_BUFFER_KEEP_LAST
        if len(self._tick_candle_buffer) <= keep_last:
            return

        sorted_keys = sorted(self._tick_candle_buffer.keys())
        for key in sorted_keys[:-keep_last]:
            self._tick_candle_buffer.pop(key, None)

    async def _load_historical_candles(self) -> None:
        """Bootstraps the analysis buffer with symbol-specific historical candles."""
        min_candles_required = Config.EMA_PERIOD * 3
        count_to_request = min_candles_required + 1

        logger.info(
            f"Historical bootstrap started for {self.symbol} | "
            f"Candles requested: {count_to_request}"
        )

        historical_candles = await self._get_historical_candles(count_to_request)
        if not historical_candles:
            logger.warning(f"No historical candles received for {self.symbol}")
            return

        last_candle = historical_candles[-1]
        now_ts = int(time.time())
        if now_ts < last_candle.timestamp + 60:
            generating_ts = last_candle.timestamp
            closed_candles = historical_candles[:-1]
        else:
            closed_candles = historical_candles
            generating_ts = last_candle.timestamp + 60

        if not closed_candles:
            logger.warning(f"Insufficient closed candles for {self.symbol}")
            return

        last_closed = closed_candles[-1]
        self.last_candle_timestamp = last_closed.timestamp
        self.current_candle_timestamp = generating_ts
        self._last_ws_generating_ts = generating_ts
        self._realtime_sync_established = False
        self._processed_closed_timestamps = {last_closed.timestamp}
        self._history_loaded = True

        if self.analysis_service:
            self.analysis_service.load_historical_candles(closed_candles)
            logger.info(
                f"{self.symbol}: loaded {len(closed_candles)} historical candles into AnalysisService"
            )

            if Config.GENERATE_HISTORICAL_CHARTS:
                source_key = f"{last_closed.source}_{self.symbol}"
                await self.analysis_service.generate_initial_chart(source_key, last_closed)

        logger.info(f"Historical bootstrap finished for {self.symbol}")

    async def _get_historical_candles(self, count: int) -> List[CandleData]:
        """Fetches historical 1-minute candles for the worker symbol."""
        if not self.client:
            return []

        try:
            end_time = time.time()
            offset_seconds = max(count * 60, 60)
            candidate_assets: List[str] = []
            for candidate in (self.asset_name, self.symbol):
                if candidate and candidate not in candidate_assets:
                    candidate_assets.append(candidate)

            fallback_offset = min(offset_seconds, 3600)
            attempt_plan = []
            if candidate_assets:
                attempt_plan.append((candidate_assets[0], offset_seconds))

            if len(candidate_assets) > 1:
                attempt_plan.append((candidate_assets[1], fallback_offset))
            elif candidate_assets:
                attempt_plan.append((candidate_assets[0], fallback_offset))

            raw_candles: List[dict] = []
            for attempt_index, (candidate_asset, candidate_offset) in enumerate(
                attempt_plan[:2],
                start=1,
            ):
                try:
                    raw_candles = await asyncio.wait_for(
                        self.client.get_candles(
                            candidate_asset,
                            end_time,
                            candidate_offset,
                            60,
                        ),
                        timeout=Config.QUOTEX.request_timeout_seconds,
                    )
                    if raw_candles:
                        break
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Historical request timeout for {self.symbol} using {candidate_asset} "
                        f"(attempt {attempt_index}/2)"
                    )
                except Exception as exc:
                    logger.warning(
                        f"Historical request error for {self.symbol} using {candidate_asset} "
                        f"(attempt {attempt_index}/2): {exc}"
                    )

            if not raw_candles:
                logger.warning(
                    f"Historical bootstrap returned empty payload for {self.symbol}"
                )
                return []

            candle_list: List[CandleData] = []
            for raw_candle in raw_candles:
                try:
                    candle_list.append(self._map_historical_candle(raw_candle))
                except Exception:
                    continue

            candle_list.sort(key=lambda candle: candle.timestamp)
            return candle_list

        except asyncio.TimeoutError:
            logger.error(
                f"Timeout fetching historical candles for {self.symbol} after "
                f"{Config.QUOTEX.request_timeout_seconds}s"
            )
            return []
        except Exception as exc:
            logger.error(f"Error fetching candles for {self.symbol}: {exc}")
            return []

    def _mark_closed_timestamp_processed(self, timestamp: int) -> None:
        """Tracks processed closed candles with bounded memory."""
        self._processed_closed_timestamps.add(int(timestamp))
        max_items = Config.QUOTEX_PROCESSED_TS_MAX
        if len(self._processed_closed_timestamps) <= max_items:
            return

        sorted_timestamps = sorted(self._processed_closed_timestamps)
        for old_timestamp in sorted_timestamps[:-max_items]:
            self._processed_closed_timestamps.discard(old_timestamp)

    def _is_closed_timestamp_processed(self, timestamp: int) -> bool:
        """Returns whether a closed candle timestamp has already been processed."""
        return int(timestamp) in self._processed_closed_timestamps

    def _should_log_generating_only(self) -> bool:
        """Throttles generating-only logs to once per minute."""
        now = time.time()
        if (now - self._last_generating_only_log_at) < 60:
            return False
        self._last_generating_only_log_at = now
        return True

    def _validate_realtime_timestamps(
        self,
        closed_ts: int,
        generating_ts: int,
        last_stored_ts: int,
    ) -> bool:
        """Applies non-fatal sanity checks on realtime timestamps."""
        if generating_ts <= closed_ts:
            logger.warning(
                f"Realtime frame rejected for {self.symbol}: generating_ts={generating_ts} "
                f"must be greater than closed_ts={closed_ts}"
            )
            return False

        if last_stored_ts > 0 and closed_ts < last_stored_ts:
            logger.warning(
                f"Realtime frame out of order for {self.symbol}: closed_ts={closed_ts} "
                f"< last_stored_ts={last_stored_ts}"
            )
            return False

        return True

    async def _poll_instrument(self) -> None:
        """Runs the sleep-and-burst polling loop for the worker symbol."""
        logger.info(f"Starting polling loop for {self.symbol}")

        while self._should_run:
            try:
                await self._check_and_process_candle()

                now = datetime.now()
                target_time = now.replace(second=59, microsecond=0)
                if now > target_time:
                    target_time += timedelta(minutes=1)

                wait_seconds = (target_time - now).total_seconds()
                if wait_seconds > 0.1:
                    await asyncio.sleep(wait_seconds)

                burst_start = time.time()
                while self._should_run and (time.time() - burst_start < 5.0):
                    if await self._check_and_process_candle():
                        break
                    await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                logger.info(f"Polling cancelled for {self.symbol}")
                break
            except Exception as exc:
                logger.error(
                    f"Error in polling loop for {self.symbol}: {exc}",
                    exc_info=True,
                )
                await asyncio.sleep(1.0)

    async def _check_and_process_candle(self) -> bool:
        """Reads realtime candles for the symbol and processes newly closed ones."""
        try:
            if not self.client:
                return False

            candles = await asyncio.wait_for(
                self.client.get_realtime_candles(self.asset_name),
                timeout=Config.QUOTEX.request_timeout_seconds,
            )
            explicit_symbol = self._extract_explicit_payload_symbol(candles)
            if self._is_realtime_payload_symbol_mismatch(explicit_symbol):
                return False

            candles = self._normalize_realtime_candles(candles)

            if (not candles) and self.asset_name != self.symbol:
                fallback_candles = await asyncio.wait_for(
                    self.client.get_realtime_candles(self.symbol),
                    timeout=Config.QUOTEX.request_timeout_seconds,
                )
                explicit_symbol = self._extract_explicit_payload_symbol(fallback_candles)
                if self._is_realtime_payload_symbol_mismatch(explicit_symbol):
                    return False

                candles = self._normalize_realtime_candles(fallback_candles)

            if not candles:
                return False

            timestamps = sorted(int(ts) for ts in candles.keys())
            if len(timestamps) == 1:
                single_generating_ts = timestamps[-1]
                if self._last_ws_generating_ts != single_generating_ts:
                    logger.debug(
                        f"Websocket generating timestamp changed for {self.symbol}: "
                        f"{self._last_ws_generating_ts} -> {single_generating_ts}"
                    )
                    self._last_ws_generating_ts = single_generating_ts

                self.current_candle_timestamp = single_generating_ts
                if self._should_log_generating_only():
                    logger.debug(
                        f"Realtime payload has only a generating candle for {self.symbol}: "
                        f"{single_generating_ts}"
                    )
                return False

            if len(timestamps) < 2:
                return False

            closed_ts = timestamps[-2]
            generating_ts = timestamps[-1]
            closed_candle_dict = candles.get(closed_ts)
            generating_candle_dict = candles.get(generating_ts)

            if closed_candle_dict is None or generating_candle_dict is None:
                return False

            if self._last_ws_generating_ts != generating_ts:
                logger.debug(
                    f"Websocket update for {self.symbol} | "
                    f"Generating TS: {self._last_ws_generating_ts} -> {generating_ts}"
                )
                self._last_ws_generating_ts = generating_ts

            if not self._validate_realtime_timestamps(
                closed_ts,
                generating_ts,
                self.last_candle_timestamp,
            ):
                return False

            if not self._realtime_sync_established:
                if (
                    self.current_candle_timestamp > 0
                    and closed_ts < self.current_candle_timestamp
                ):
                    self.current_candle_timestamp = generating_ts
                    return False

                self._realtime_sync_established = True
                logger.debug(
                    f"Realtime continuity established for {self.symbol} | "
                    f"Bootstrap generating: {self.current_candle_timestamp} | "
                    f"Closed: {closed_ts} | Generating: {generating_ts}"
                )

            if (
                self.last_candle_timestamp > 0
                and (closed_ts - self.last_candle_timestamp) > 60
            ):
                missing_intermediates = max(
                    int((closed_ts - self.last_candle_timestamp) / 60) - 1,
                    0,
                )
                logger.warning(
                    f"Gap detected for {self.symbol}: last={self.last_candle_timestamp} | "
                    f"new={closed_ts} | missing={missing_intermediates}"
                )
                await self._fill_data_gaps(self.last_candle_timestamp, closed_ts)

            if closed_ts <= self.last_candle_timestamp:
                return False

            if self._is_closed_timestamp_processed(closed_ts):
                self.current_candle_timestamp = generating_ts
                return False

            await self._process_new_candle(
                closed_candle_dict,
                closed_ts,
                generating_ts,
            )
            return True

        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout reading realtime candles for {self.symbol} after "
                f"{Config.QUOTEX.request_timeout_seconds}s"
            )
            return False
        except Exception as exc:
            logger.error(
                f"Error in check_and_process_candle for {self.symbol}: {exc}"
            )
            return False

    async def _fetch_authoritative_closed_candle(
        self,
        closed_ts: int,
    ) -> Optional[CandleData]:
        """Fetches server-authoritative OHLC for a recently closed candle."""
        if not self.client:
            return None

        try:
            end_time = float(closed_ts + 62)
            raw_candles = await asyncio.wait_for(
                self.client.get_candles(self.asset_name, end_time, 180, 60),
                timeout=Config.QUOTEX.request_timeout_seconds,
            )
            if not raw_candles:
                return None

            for raw_candle in raw_candles:
                raw_timestamp = int(raw_candle.get("time", raw_candle.get("timestamp", 0)))
                if raw_timestamp == closed_ts:
                    return self._map_historical_candle(raw_candle)

            return None

        except Exception as exc:
            logger.debug(
                f"Authoritative fetch failed for {self.symbol} @ {closed_ts}: {exc}"
            )
            return None

    async def _process_new_candle(
        self,
        closed_candle_dict: dict,
        closed_ts: int,
        generating_ts: int,
    ) -> None:
        """Normalizes a closed candle and forwards it to the analysis service."""
        self.last_candle_timestamp = closed_ts
        self.current_candle_timestamp = generating_ts
        self._mark_closed_timestamp_processed(closed_ts)

        closed_candle = await self._fetch_authoritative_closed_candle(closed_ts)
        if closed_candle is None:
            closed_candle = self._map_realtime_candle(closed_candle_dict, closed_ts)

        if closed_candle and self.analysis_service:
            await self.analysis_service.process_realtime_candle(closed_candle)
            closed_time_str = datetime.fromtimestamp(closed_ts).strftime("%H:%M:%S")
            logger.info(
                f"Candle processed for {self.symbol} @ {closed_time_str} | Close: {closed_candle.close}"
            )

    async def _fill_data_gaps(self, last_stored_ts: int, current_ts: int) -> None:
        """Backfills missing candles after a disconnect or stream interruption."""
        try:
            candles_needed = int((current_ts - last_stored_ts) / 60)
            if candles_needed <= 0:
                return

            historical_candles = await self._get_historical_candles(candles_needed + 2)
            if not historical_candles:
                logger.warning(f"Could not recover gap candles for {self.symbol}")
                return

            by_timestamp = {
                candle.timestamp: candle
                for candle in historical_candles
                if last_stored_ts < candle.timestamp < current_ts
            }
            gap_candles = [by_timestamp[ts] for ts in sorted(by_timestamp.keys())]

            for candle in gap_candles:
                if self._is_closed_timestamp_processed(candle.timestamp):
                    continue

                self._mark_closed_timestamp_processed(candle.timestamp)
                if self.analysis_service:
                    await self.analysis_service.process_realtime_candle(candle)

            if gap_candles:
                self.last_candle_timestamp = gap_candles[-1].timestamp

        except Exception as exc:
            logger.error(
                f"Error filling gap for {self.symbol}: {exc}",
                exc_info=True,
            )

    def _map_historical_candle(self, raw_candle: dict) -> CandleData:
        """Maps a Quotex historical candle payload to CandleData."""
        return CandleData(
            timestamp=int(raw_candle["time"]),
            open=float(raw_candle["open"]),
            high=float(raw_candle["high"]),
            low=float(raw_candle["low"]),
            close=float(raw_candle["close"]),
            volume=float(raw_candle.get("ticks", 0)),
            source="QX",
            symbol=self.symbol,
        )

    def _map_realtime_candle(self, raw_candle: dict, timestamp: int) -> Optional[CandleData]:
        """Maps a Quotex realtime candle payload to CandleData."""
        try:
            open_price = self._extract_first_numeric(raw_candle, ["open", "o"])
            close_price = self._extract_first_numeric(raw_candle, ["close", "c"])
            high = self._extract_first_numeric(raw_candle, ["high", "max", "h"])
            low = self._extract_first_numeric(raw_candle, ["low", "min", "l"])

            if (
                open_price is None
                or close_price is None
                or high is None
                or low is None
            ):
                return None

            if high < low:
                logger.debug(
                    f"Invalid realtime OHLC range for {self.symbol} @ {timestamp}: high={high}, low={low}"
                )
                return None

            raw_volume = self._extract_first_numeric(
                raw_candle,
                ["ticks", "tick_volume", "volume", "v"],
            )

            return CandleData(
                timestamp=int(timestamp),
                open=float(open_price),
                high=high,
                low=low,
                close=float(close_price),
                volume=0.0 if raw_volume is None else raw_volume,
                source="QX",
                symbol=self.symbol,
            )
        except Exception as exc:
            logger.error(f"Error mapping realtime candle for {self.symbol}: {exc}")
            return None

    async def _reconnect_loop(self) -> None:
        """Reconnects the dedicated worker with exponential backoff."""
        attempt = 0
        current_timeout = Config.RECONNECT_INITIAL_TIMEOUT

        while self._should_run:
            await asyncio.sleep(1)
            if not self._should_run:
                break

            if self.client is None:
                await self._attempt_reconnect(attempt, current_timeout)
                if self.client is not None:
                    attempt = 0
                    current_timeout = Config.RECONNECT_INITIAL_TIMEOUT
                else:
                    attempt += 1
                    current_timeout = min(
                        max(current_timeout * 2, Config.RECONNECT_INITIAL_TIMEOUT),
                        Config.RECONNECT_MAX_TIMEOUT,
                    )
                continue

            try:
                candles = await asyncio.wait_for(
                    self.client.get_realtime_candles(self.asset_name),
                    timeout=Config.QUOTEX.request_timeout_seconds,
                )
                if candles is not None:
                    if attempt > 0:
                        logger.info(f"Quotex liveness restored for {self.symbol}")
                    attempt = 0
                    current_timeout = Config.RECONNECT_INITIAL_TIMEOUT
                    continue
            except asyncio.TimeoutError:
                logger.warning(
                    f"Liveness check timeout for {self.symbol} after "
                    f"{Config.QUOTEX.request_timeout_seconds}s"
                )
            except Exception:
                pass

            await self._attempt_reconnect(attempt, current_timeout)
            if self.client is not None:
                attempt = 0
                current_timeout = Config.RECONNECT_INITIAL_TIMEOUT
            else:
                attempt += 1
                current_timeout = min(
                    max(current_timeout * 2, Config.RECONNECT_INITIAL_TIMEOUT),
                    Config.RECONNECT_MAX_TIMEOUT,
                )

    async def _attempt_reconnect(self, attempt: int, current_timeout: int) -> None:
        """Reconnects the dedicated client and re-subscribes the symbol stream."""
        logger.warning(
            f"Quotex worker reconnect scheduled for {self.symbol} in {current_timeout}s "
            f"(attempt {attempt + 1})"
        )
        await asyncio.sleep(current_timeout)

        if not self._should_run:
            return

        await self._disconnect_client()

        if not await self._connect():
            logger.error(f"Reconnection failed for {self.symbol}")
            return

        self.is_active_symbol = await self._resolve_symbol_availability()
        if not self.is_active_symbol:
            logger.warning(
                f"Reconnected Quotex worker for {self.symbol}, but the asset is closed"
            )
            await self._disconnect_client()
            return

        await self._subscribe_to_instrument()
        self._realtime_sync_established = False
        self._tick_candle_buffer.clear()

        if not self._history_loaded:
            await self._load_historical_candles()

        logger.info(f"Reconnection successful for {self.symbol}")


class QuotexServiceMultiAsync:
    """Coordinates one independent Quotex worker per configured symbol."""

    def __init__(
        self,
        analysis_service: Optional["AnalysisService"],
        on_auth_failure_callback: Optional[Callable[[], None]] = None,
    ):
        self.analysis_service = analysis_service
        self.on_auth_failure_callback = on_auth_failure_callback

        self._workers: Dict[str, _QuotexSymbolWorker] = {}
        self._worker_tasks: List[asyncio.Task] = []
        self._auth_failure_reported = False

    @property
    def client(self) -> Optional[Quotex]:
        """Compatibility accessor returning the first live client if available."""
        for worker in self._workers.values():
            if worker.client is not None:
                return worker.client
        return None

    @property
    def poll_tasks(self) -> List[asyncio.Task]:
        """Compatibility accessor exposing running worker tasks."""
        return list(self._worker_tasks)

    @property
    def last_candle_timestamps(self) -> Dict[str, int]:
        """Compatibility accessor for per-symbol closed candle timestamps."""
        return {
            symbol: worker.last_candle_timestamp
            for symbol, worker in self._workers.items()
            if worker.last_candle_timestamp > 0
        }

    @property
    def current_candle_timestamps(self) -> Dict[str, int]:
        """Compatibility accessor for per-symbol generating candle timestamps."""
        return {
            symbol: worker.current_candle_timestamp
            for symbol, worker in self._workers.items()
            if worker.current_candle_timestamp > 0
        }

    async def start(self) -> None:
        """Starts one independent Quotex worker per configured symbol in parallel."""
        symbols = list(dict.fromkeys(Config.QUOTEX.assets))
        logger.info(
            f"Starting QuotexServiceMultiAsync with {len(symbols)} independent workers"
        )

        self._auth_failure_reported = False
        self._workers = {
            symbol: _QuotexSymbolWorker(
                symbol=symbol,
                analysis_service=self.analysis_service,
                on_auth_failure_callback=self._notify_auth_failure_once,
            )
            for symbol in symbols
        }

        self._worker_tasks = [
            asyncio.create_task(worker.start(), name=f"quotex-worker-{symbol}")
            for symbol, worker in self._workers.items()
        ]

        try:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        finally:
            self._worker_tasks.clear()

    async def stop(self) -> None:
        """Stops all independent Quotex workers and their dedicated clients."""
        if not self._workers:
            return

        await asyncio.gather(
            *(worker.stop() for worker in self._workers.values()),
            return_exceptions=True,
        )

        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)

        self._worker_tasks.clear()
        logger.info("Quotex service stopped")

    def _notify_auth_failure_once(self) -> None:
        """Reports authentication failure only once across all symbol workers."""
        if self._auth_failure_reported:
            return

        self._auth_failure_reported = True
        if self.on_auth_failure_callback:
            self.on_auth_failure_callback()


def create_quotex_service_multi_async(
    analysis_service: Optional["AnalysisService"],
    on_auth_failure_callback: Optional[Callable[[], None]] = None,
) -> QuotexServiceMultiAsync:
    """Factory function for the multi-worker Quotex service."""
    return QuotexServiceMultiAsync(analysis_service, on_auth_failure_callback)
