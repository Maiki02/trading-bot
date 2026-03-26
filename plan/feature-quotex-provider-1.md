---
goal: Implement Quotex data provider using API-Quotex (pyquotex) library
version: 1.0
date_created: 2026-03-26
last_updated: 2026-03-26
owner: Trading Bot Team
status: 'In progress'
tags: feature, provider, quotex, websocket
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

Implement a new market data provider for Quotex using the `pyquotex` library (installed from GitHub). This provider will follow the exact same patterns as the existing IQ Option multi-instrument service, supporting multiple instruments, 1-minute candles, historical data loading, real-time polling with Sleep & Burst strategy, and seamless integration with AnalysisService.

## 1. Requirements & Constraints

- **REQ-001**: Install `pyquotex` from GitHub: `pip install git+https://github.com/cleitonleonel/pyquotex.git`
- **REQ-002**: Create `src/services/quotex_service_multi.py` following IQ Option service patterns
- **REQ-003**: Support multi-instrument monitoring via `Config.TARGET_ASSETS`
- **REQ-004**: Load historical candles (EMA_PERIOD * 3 + 1) on startup for indicator initialization
- **REQ-005**: Transform Quotex candle data to internal `CandleData` format with `source="QX"`
- **REQ-006**: Implement Sleep & Burst polling strategy for low-latency candle detection
- **REQ-007**: Support reconnection with exponential backoff
- **REQ-008**: Update `config.py` to add `QuotexConfig` dataclass and validate QUOTEX provider
- **REQ-009**: Update `connection_service.py` factory to support `DATA_PROVIDER=QUOTEX`
- **REQ-010**: Update `.env` with Quotex-specific variables
- **SEC-001**: Never hardcode credentials — use environment variables only
- **CON-001**: No trade execution logic — alerts only
- **CON-002**: All code, comments, identifiers in English
- **CON-003**: Python 3.10+ with strict type hints
- **CON-004**: pyquotex is async-native (uses `async/await`) — no need for `run_in_executor` wrapper
- **GUD-001**: Follow existing IQ Option service structure closely for maintainability
- **PAT-001**: Quotex uses string asset names (e.g., "EURUSD_otc"), not numeric IDs like IQ Option

## 2. Implementation Steps

### Phase 1: Configuration & Dependencies

- GOAL-001: Add Quotex configuration to config.py and .env

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `QuotexConfig` dataclass to `config.py` with email, password fields | | |
| TASK-002 | Add `QUOTEX` case to `Config.validate_all()` method | | |
| TASK-003 | Add `QUOTEX_EMAIL` and `QUOTEX_PASSWORD` variables to `.env` | | |
| TASK-004 | Install pyquotex: `pip install git+https://github.com/cleitonleonel/pyquotex.git` | | |

### Phase 2: Quotex Service Implementation

- GOAL-002: Create `quotex_service_multi.py` with full multi-instrument support

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Create `QuotexMultiService` class (async, wraps pyquotex Quotex client) | | |
| TASK-006 | Implement `connect()` — authenticate with email/password, change to PRACTICE account | | |
| TASK-007 | Implement `get_historical_candles()` — fetch 1000 candles using `client.get_candles(asset, time.time(), 60000, 60)` | | |
| TASK-008 | Implement `_map_candle_data()` — transform Quotex format {time, open, close, high, low, ticks} to CandleData | | |
| TASK-009 | Implement `get_realtime_candles()` — poll `client.get_realtime_candles(asset)` for live data | | |
| TASK-010 | Implement `disconnect()` — stop streams and close connection | | |

### Phase 3: Async Wrapper & Polling

- GOAL-003: Create `QuotexServiceMultiAsync` wrapper with polling logic

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | Create `QuotexServiceMultiAsync` class with `start()`, `stop()` lifecycle | | |
| TASK-012 | Implement `_load_all_historical_candles()` — load EMA*3+1 candles, discard last (in-formation), feed to AnalysisService | | |
| TASK-013 | Implement `_poll_instrument()` — Sleep & Burst strategy identical to IQ Option | | |
| TASK-014 | Implement `_check_and_process_candle()` — detect new closed candle, handle gaps | | |
| TASK-015 | Implement `_process_new_candle()` — map dict to CandleData, send to AnalysisService | | |
| TASK-016 | Implement `_fill_data_gaps()` — request missing candles and process them | | |
| TASK-017 | Create factory function `create_quotex_service_multi_async()` | | |

### Phase 4: Integration

- GOAL-004: Wire Quotex provider into the application

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-018 | Add QUOTEX case to `get_market_data_service()` in connection_service.py | | |
| TASK-019 | Add `"QUOTEX"` to valid DATA_PROVIDER values in config validation | | |
| TASK-020 | Add pyquotex to requirements.txt | | |

### Phase 5: Validation

- GOAL-005: Verify implementation compiles and follows conventions

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-021 | Run `python -m py_compile` on all modified/created files | | |
| TASK-022 | Verify no Spanish in code/comments | | |
| TASK-023 | Verify type hints on all public methods | | |
| TASK-024 | Verify no hardcoded values | | |

## 3. Alternatives

- **ALT-001**: Use tick-based streaming (`get_realtime_price`) instead of candle polling — rejected because candle polling (Sleep & Burst) matches existing IQ Option architecture and is simpler
- **ALT-002**: Build candles from ticks using CandleBuilder — rejected because pyquotex already provides formed candles via `get_realtime_candles()`

## 4. Dependencies

- **DEP-001**: `pyquotex` library from GitHub (`git+https://github.com/cleitonleonel/pyquotex.git`)
- **DEP-002**: `playwright` for pyquotex authentication (`playwright install`)
- **DEP-003**: Existing `AnalysisService`, `CandleData`, `InstrumentState` classes

## 5. Files

- **FILE-001**: `src/services/quotex_service_multi.py` — NEW: Main Quotex provider service
- **FILE-002**: `config.py` — MODIFY: Add QuotexConfig dataclass, add QUOTEX validation
- **FILE-003**: `src/services/connection_service.py` — MODIFY: Add QUOTEX case to factory
- **FILE-004**: `.env` — MODIFY: Add QUOTEX_EMAIL, QUOTEX_PASSWORD
- **FILE-005**: `requirements.txt` — MODIFY: Add pyquotex dependency

## 6. Testing

- **TEST-001**: `python -m py_compile src/services/quotex_service_multi.py` passes
- **TEST-002**: `python -m py_compile config.py` passes
- **TEST-003**: `python -m py_compile src/services/connection_service.py` passes
- **TEST-004**: Import check: `python -c "from src.services.quotex_service_multi import QuotexServiceMultiAsync"`

## 7. Risks & Assumptions

- **RISK-001**: `pyquotex` requires Python >=3.12 per pyproject.toml — may conflict with Python 3.10 requirement
- **RISK-002**: `playwright install` must be run after pip install for auth to work
- **RISK-003**: pyquotex API may change as it's a community library
- **ASSUMPTION-001**: Quotex real-time candles dict format matches: `{timestamp: {"open", "close", "high", "low", "symbol"}}`
- **ASSUMPTION-002**: `get_candles(asset, time.time(), 60000, 60)` returns ~1000 1-minute candles
- **ASSUMPTION-003**: Asset names in TARGET_ASSETS will use Quotex format (e.g., "EURUSD_otc" or "EURUSD")

## 8. Related Specifications / Further Reading

- [pyquotex GitHub Repository](https://github.com/cleitonleonel/pyquotex)
- IQ Option reference implementation: `src/services/iq_option_service_multi.py`
