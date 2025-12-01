# Multi-Instrument Architecture Refactoring

## 📋 Overview

This document describes the complete refactoring of the trading bot to support **multiple instruments** simultaneously with **dual buffer system** (BID/MID) and **tick-based MID price calculation**.

### Key Changes

1. **Multi-Instrument Support**: Monitor multiple assets simultaneously (EURUSD, GBPUSD, USDJPY, etc.)
2. **Dual Buffer System**: Maintain separate BID (raw API data) and MID ((Bid+Ask)/2) candle buffers
3. **Tick Processing**: Real-time tick-based MID price calculation
4. **Isolated Processing**: Each instrument is analyzed independently without blocking others
5. **Configurable Chart Generation**: Optional historical chart generation on startup

---

## 🏗️ Architecture Components

### 1. Configuration (`config.py`)

**New Variables:**
```python
# Multi-instrument support
TARGET_ASSETS: List[str] = ["EURUSD", "GBPUSD", "USDJPY"]

# Historical chart generation (optional, default: False)
GENERATE_HISTORICAL_CHARTS: bool = False
```

**Environment Variables:**
```bash
# .env file
TARGET_ASSETS=EURUSD,GBPUSD,USDJPY
GENERATE_HISTORICAL_CHARTS=false  # Set to 'true' to enable
```

---

### 2. Instrument State Management (`src/services/instrument_state.py`)

**New Data Structures:**

#### `TickData`
Represents an individual tick with BID and ASK prices.
```python
@dataclass
class TickData:
    timestamp: float
    bid: float
    ask: float
    symbol: str
    
    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0
```

#### `CandleBuilder`
Accumulates ticks to build complete MID candles.
```python
@dataclass
class CandleBuilder:
    timestamp: int
    open: Optional[float]
    high: float
    low: float
    close: Optional[float]
    tick_count: int
```

#### `InstrumentState`
Complete state for a single instrument with dual buffers.
```python
@dataclass
class InstrumentState:
    symbol: str
    bid_candles: Deque[CandleData]  # Raw BID data
    mid_candles: Deque[CandleData]  # Synthetic MID data
    current_mid_builder: Optional[CandleBuilder]
    lock: asyncio.Lock
```

**Key Methods:**
- `process_tick()`: Processes ticks and builds MID candles
- `add_bid_candle()`: Adds BID candle to buffer
- `get_latest_bid_candle()`: Returns latest closed BID candle
- `get_latest_mid_candle()`: Returns latest closed MID candle

---

### 3. Multi-Instrument IQ Option Service (`src/services/iq_option_service_multi.py`)

#### `CandleTicker`
Asynchronous tick processor that calculates MID prices in separate tasks.

**Features:**
- Queue-based tick processing
- Non-blocking asynchronous architecture
- Real-time MID candle construction

**Flow:**
```
Tick Received → Queue → Async Processing → Calculate MID → Build Candle → Detect Minute Change → Close Candle
```

#### `IqOptionMultiService`
Core service managing multiple instruments.

**Key Features:**
- Single WebSocket connection (avoids IP bans)
- Multiple instrument subscriptions
- Dual buffer management per instrument
- Thread-safe state management

**Architecture:**
```python
{
    "EURUSD": InstrumentState(
        bid_candles=[...],
        mid_candles=[...],
        current_mid_builder=CandleBuilder(...)
    ),
    "GBPUSD": InstrumentState(...),
    "USDJPY": InstrumentState(...)
}
```

#### `IqOptionServiceMultiAsync`
Asynchronous wrapper for parallel instrument monitoring.

**Features:**
- Parallel polling for each instrument
- Independent timestamp tracking per asset
- Asynchronous historical data loading
- Optional historical chart generation

**Polling Architecture:**
```
Main Task
├── Poll EURUSD (async task)
├── Poll GBPUSD (async task)
└── Poll USDJPY (async task)
    ↓
Each task:
1. Check BID closed candle
2. Process if new
3. Get current tick
4. Send to CandleTicker
5. Repeat every 0.5s
```

---

### 4. Analysis Service Updates (`src/logic/analysis_service.py`)

**Isolated Processing:**
```python
async def _analyze_last_closed_candle(self, source_key: str, ...) -> None:
    """Non-blocking: creates isolated task per instrument."""
    await asyncio.create_task(
        self._analyze_last_closed_candle_isolated(source_key, ...)
    )
```

**Benefits:**
- EURUSD analysis doesn't block GBPUSD
- Chart generation per instrument is independent
- Pattern detection happens in parallel

---

### 5. Main Orchestrator Updates (`main.py`)

**Initialization:**
```python
async def initialize(self) -> None:
    # Log multi-instrument configuration
    if Config.DATA_PROVIDER == "IQOPTION":
        logger.info(f"🎯 Target Assets: {', '.join(Config.TARGET_ASSETS)}")
        logger.info(f"📊 Generate Historical Charts: {Config.GENERATE_HISTORICAL_CHARTS}")
    
    # Services initialization (unchanged)
    ...
```

**Factory Pattern:**
The system automatically selects the correct service based on `DATA_PROVIDER`:
```python
# connection_service.py
def get_market_data_service(analysis_service, on_auth_failure_callback=None):
    if Config.DATA_PROVIDER == "IQOPTION":
        return create_iq_option_service_multi_async(...)
    elif Config.DATA_PROVIDER == "TRADINGVIEW":
        return ConnectionService(...)
```

---

## 🔄 Data Flow

### Historical Data Loading
```
1. Connect to IQ Option
2. For each TARGET_ASSET:
   a. Request 200-1000 historical BID candles
   b. Store in InstrumentState.bid_candles
   c. Load into AnalysisService
   d. [Optional] Generate historical chart if GENERATE_HISTORICAL_CHARTS=true
3. Initialize CandleTicker
4. Start polling tasks
```

### Real-Time Processing
```
[Instrument Polling Task] → Every 0.5s:
    1. Get latest closed BID candle
    2. If new timestamp detected:
       a. Add to bid_candles buffer
       b. Send to AnalysisService
       c. Trigger pattern detection
    
    3. Get current tick (BID/ASK)
    4. Calculate MID = (BID + ASK) / 2
    5. Send tick to CandleTicker
    
[CandleTicker Background Task]:
    1. Process tick from queue
    2. Add to current CandleBuilder
    3. If minute changed:
       a. Close previous MID candle
       b. Add to mid_candles buffer
       c. Start new CandleBuilder
```

---

## 📊 MID Price Calculation

### Why MID Prices Matter
**Problem:** IQ Option liquidates binary options using MID price `(Bid + Ask) / 2`, but the API only provides BID prices in historical candles.

**Solution:** Build synthetic MID candles from real-time ticks.

### Tick Aggregation
```python
# Minute: 22:36:00 - 22:36:59

Tick 1 (22:36:01): BID=1.05001, ASK=1.05003 → MID=1.05002
Tick 2 (22:36:15): BID=1.05005, ASK=1.05007 → MID=1.05006
Tick 3 (22:36:45): BID=1.04999, ASK=1.05001 → MID=1.05000
Tick 4 (22:36:59): BID=1.05003, ASK=1.05005 → MID=1.05004

MID Candle Result:
├── Open:   1.05002 (first tick)
├── High:   1.05006 (max of all ticks)
├── Low:    1.05000 (min of all ticks)
└── Close:  1.05004 (last tick)
```

---

## 🎨 Historical Chart Generation

### Configuration
```python
# config.py
GENERATE_HISTORICAL_CHARTS: bool = False  # Default: disabled
```

**Why Optional?**
- **I/O Intensive**: Generating charts on startup adds 2-5 seconds per instrument
- **Production vs Development**: Useful for debugging, unnecessary in production
- **Multi-Instrument**: With 10 instruments, startup time increases significantly

### Usage
```bash
# Enable in .env
GENERATE_HISTORICAL_CHARTS=true
```

**Result:**
Charts saved to `data/charts/{SYMBOL}/init_{timestamp}.png`

Example:
```
data/
└── charts/
    ├── EURUSD/
    │   └── init_20250125_143022.png
    ├── GBPUSD/
    │   └── init_20250125_143025.png
    └── USDJPY/
        └── init_20250125_143028.png
```

---

## 🚀 Usage

### Basic Configuration

**1. Configure instruments in `.env`:**
```bash
DATA_PROVIDER=IQOPTION
TARGET_ASSETS=EURUSD,GBPUSD,USDJPY
GENERATE_HISTORICAL_CHARTS=false

IQ_OPTION_USER=your_email@example.com
IQ_OPTION_PASS=your_password
```

**2. Run the bot:**
```bash
python main.py
```

**3. Expected output:**
```
🔧 Initializing services...
🎯 Target Assets (Multi-Instrument): EURUSD, GBPUSD, USDJPY
📊 Generate Historical Charts: Disabled
✅ All services initialized successfully

🔌 Using IQ Option Multi-Instrument as data provider | Instruments: EURUSD, GBPUSD, USDJPY
📥 Cargando 350 velas BID para EURUSD...
✅ 350 velas BID cargadas para EURUSD
📥 Cargando 350 velas BID para GBPUSD...
✅ 350 velas BID cargadas para GBPUSD
📥 Cargando 350 velas BID para USDJPY...
✅ 350 velas BID cargadas para USDJPY

🚀 IQ Option Multi-Service iniciado | Monitoreando 3 instrumentos
🕐 Polling iniciado para EURUSD
🕐 Polling iniciado para GBPUSD
🕐 Polling iniciado para USDJPY

🕯️ VELA BID CERRADA | EURUSD | 14:30:00 | Cierre: 1.05001
🕯️ VELA MID CERRADA | EURUSD | T=1738160400 | O=1.05002 H=1.05006 L=1.04999 C=1.05004
🎯 PATTERN DETECTED | IQO | SHOOTING_STAR | Trend=STRONG_BULLISH...
```

---

## 🔧 Technical Details

### Thread Safety
All instrument state operations are protected with `asyncio.Lock`:
```python
async with self.lock:
    self.bid_candles.append(candle)
```

### Memory Management
Buffers use `collections.deque` with `maxlen=500` to prevent memory growth:
```python
bid_candles: Deque[CandleData] = deque(maxlen=500)
```

### Performance Optimization
- **Parallel polling**: Each instrument monitored independently
- **Async I/O**: Non-blocking operations throughout
- **Queue-based processing**: Tick processing doesn't block data retrieval
- **Optional charting**: Disable on production for faster startup

---

## 📈 Comparison: Before vs After

| Feature | Before | After |
|---------|--------|-------|
| Instruments | Single (EURUSD) | Multiple (configurable) |
| Price Data | BID only | BID + MID (dual buffer) |
| MID Calculation | ❌ Not available | ✅ Real-time from ticks |
| Processing | Sequential | Parallel (isolated tasks) |
| WebSocket | Single connection | Single connection (maintained) |
| Chart Generation | Always on startup | Optional (configurable) |
| Scalability | Limited to 1 asset | Scales to N assets |

---

## 🎯 Benefits

1. **Accuracy**: MID prices match IQ Option liquidation logic
2. **Scalability**: Monitor 10+ instruments simultaneously
3. **Performance**: Non-blocking architecture prevents bottlenecks
4. **Flexibility**: Dual buffers allow BID/MID comparison
5. **Development**: Optional charts for debugging without production overhead

---

## ⚠️ Important Notes

### IQ Option API Limitations
- **BID/ASK separation**: The API doesn't expose real-time BID/ASK separately
- **Workaround**: Current implementation estimates spread and simulates BID/ASK
- **Future improvement**: Implement WebSocket tick stream if API supports it

### Tick Approximation
```python
# Current implementation (approximation)
close_price = candle["close"]
estimated_spread = 0.00002  # 0.2 pips for EURUSD
bid = close_price - spread/2
ask = close_price + spread/2
```

**Recommendation:** If IQ Option provides real-time tick data, replace `get_current_tick()` with actual tick stream subscription.

---

## 📚 Files Modified/Created

### Created Files
- `src/services/instrument_state.py` - State management
- `src/services/iq_option_service_multi.py` - Multi-instrument service
- `MULTI_INSTRUMENT_REFACTORING.md` - This documentation

### Modified Files
- `config.py` - Added TARGET_ASSETS and GENERATE_HISTORICAL_CHARTS
- `main.py` - Updated initialization logging
- `src/services/connection_service.py` - Factory pattern update
- `src/logic/analysis_service.py` - Isolated async processing

### Preserved Files (Backward Compatible)
- `src/services/iq_option_service.py` - Original single-instrument version (kept for reference)

---

## 🔮 Future Enhancements

1. **Real Tick Streams**: Replace tick approximation with actual WebSocket tick feed
2. **Historical MID Candles**: Backfill MID candles from historical BID/ASK if available
3. **Spread Analysis**: Track and analyze spread patterns per instrument
4. **Performance Metrics**: Add monitoring for tick processing latency
5. **Database Integration**: Store both BID and MID candles for backtesting

---

## 🐛 Troubleshooting

### Issue: "Cola de ticks llena para {symbol}"
**Cause:** Tick processing slower than tick arrival rate
**Solution:** Increase queue size or optimize `_process_tick_queue()`

### Issue: Charts not generating
**Cause:** `GENERATE_HISTORICAL_CHARTS=false`
**Solution:** Set to `true` in `.env` if charts are needed

### Issue: Missing MID candles
**Cause:** Tick data not arriving or minute detection failing
**Solution:** Check `get_current_tick()` implementation and logs

---

## 📞 Support

For questions or issues, review:
1. This documentation
2. Code comments in refactored files
3. Logs during bot execution (look for 🕯️ emoji markers)

---

**Author:** Trading Bot Team  
**Date:** January 2025  
**Version:** Multi-Instrument v2.0
