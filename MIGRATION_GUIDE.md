# Migration Guide: Single to Multi-Instrument

This guide helps you migrate from the old single-instrument architecture to the new multi-instrument system.

## 📋 Pre-Migration Checklist

- [ ] Backup your current `.env` file
- [ ] Backup your `data/` directory (datasets, notifications)
- [ ] Review `MULTI_INSTRUMENT_REFACTORING.md` for architecture details
- [ ] Test with 1-2 instruments before scaling to many

---

## 🔄 Step-by-Step Migration

### Step 1: Update Environment Variables

**Old `.env` (single instrument):**
```bash
DATA_PROVIDER=IQOPTION
IQ_OPTION_USER=your_email@example.com
IQ_OPTION_PASS=your_password
IQ_ASSET=EURUSD-OTC
```

**New `.env` (multi-instrument):**
```bash
DATA_PROVIDER=IQOPTION
IQ_OPTION_USER=your_email@example.com
IQ_OPTION_PASS=your_password

# NEW: List of assets to monitor
TARGET_ASSETS=EURUSD,GBPUSD,USDJPY

# NEW: Optional historical chart generation
GENERATE_HISTORICAL_CHARTS=false

# Legacy variable (kept for backward compatibility)
IQ_ASSET=EURUSD-OTC
```

**What Changed:**
- `IQ_ASSET` is now primarily used for single-instrument fallback
- `TARGET_ASSETS` controls which instruments are monitored
- Add `GENERATE_HISTORICAL_CHARTS` (recommended: `false` for production)

---

### Step 2: Update Dependencies (if needed)

The refactoring doesn't require new packages, but ensure you have:
```bash
pip install -r requirements.txt
```

**Core dependencies:**
- `iqoptionapi` - IQ Option API wrapper
- `asyncio` - Already in Python 3.7+
- `pandas`, `numpy` - Data processing
- `mplfinance` - Chart generation

---

### Step 3: Choose Your Configuration

#### Option A: Conservative Migration (Recommended)
Start with 1-2 instruments to test:
```bash
TARGET_ASSETS=EURUSD,GBPUSD
GENERATE_HISTORICAL_CHARTS=false
```

#### Option B: Full Multi-Instrument
Monitor many assets:
```bash
TARGET_ASSETS=EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD
GENERATE_HISTORICAL_CHARTS=false
```

#### Option C: Development/Testing
Enable charts for debugging:
```bash
TARGET_ASSETS=EURUSD
GENERATE_HISTORICAL_CHARTS=true
```

---

### Step 4: Test the New System

**1. Dry Run (Console Only):**
```bash
# Disable Telegram notifications for testing
ENABLE_NOTIFICATIONS=false
```

**2. Run the bot:**
```bash
python main.py
```

**3. Expected Output (Multi-Instrument):**
```
🔧 Initializing services...
🎯 Target Assets (Multi-Instrument): EURUSD, GBPUSD, USDJPY
📊 Generate Historical Charts: Disabled
✅ All services initialized successfully

🔌 Using IQ Option Multi-Instrument as data provider | Instruments: EURUSD, GBPUSD, USDJPY

📥 Cargando 350 velas BID para EURUSD...
✅ 350 velas BID cargadas para EURUSD
📊 Analysis Service inicializado (Período EMA: 50, Storage: ✓)

📥 Cargando 350 velas BID para GBPUSD...
✅ 350 velas BID cargadas para GBPUSD

📥 Cargando 350 velas BID para USDJPY...
✅ 350 velas BID cargadas para USDJPY

🚀 IQ Option Multi-Service iniciado | Monitoreando 3 instrumentos
🕐 Polling iniciado para EURUSD
🕐 Polling iniciado para GBPUSD
🕐 Polling iniciado para USDJPY
```

**4. Verify Parallel Processing:**
Look for simultaneous log entries from different instruments:
```
🕯️ VELA BID CERRADA | EURUSD | 14:30:00 | Cierre: 1.05001
🕯️ VELA BID CERRADA | GBPUSD | 14:30:00 | Cierre: 1.27834
🕯️ VELA BID CERRADA | USDJPY | 14:30:00 | Cierre: 149.223
```

---

### Step 5: Verify MID Price Calculation

**Look for MID candle logs:**
```
🕯️ VELA MID CERRADA | EURUSD | T=1738160400 | O=1.05002 H=1.05006 L=1.04999 C=1.05004
```

**How to verify:**
1. Compare BID and MID close prices (should be slightly different)
2. MID price should be between BID and ASK (simulated)
3. Check `data/charts/` for visual confirmation (if `GENERATE_HISTORICAL_CHARTS=true`)

---

### Step 6: Enable Production Features

Once testing is successful:

```bash
# Re-enable Telegram notifications
ENABLE_NOTIFICATIONS=true

# Keep charts disabled for performance
GENERATE_HISTORICAL_CHARTS=false

# Monitor desired instruments
TARGET_ASSETS=EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD
```

---

## 🔍 Troubleshooting

### Issue: Bot starts but no instruments monitored

**Check:**
```bash
# Ensure TARGET_ASSETS is set
echo $TARGET_ASSETS

# Should output: EURUSD,GBPUSD,USDJPY
```

**Fix:**
Add to `.env`:
```bash
TARGET_ASSETS=EURUSD,GBPUSD
```

---

### Issue: "Module not found: instrument_state"

**Cause:** New files not in Python path

**Fix:**
```bash
# Ensure files exist
ls src/services/instrument_state.py
ls src/services/iq_option_service_multi.py

# If missing, re-download or check file permissions
```

---

### Issue: High CPU usage with many instruments

**Cause:** Too many instruments + chart generation enabled

**Fix:**
```bash
# Disable chart generation
GENERATE_HISTORICAL_CHARTS=false

# Reduce number of instruments
TARGET_ASSETS=EURUSD,GBPUSD,USDJPY  # Max 5-10 recommended
```

---

### Issue: MID candles not appearing

**Cause:** Tick data not arriving or minute detection failing

**Debug:**
```bash
# Enable debug logging
LOG_LEVEL=DEBUG
```

**Check logs for:**
```
📊 CandleTicker inicializado
🔄 Iniciando loop de procesamiento de ticks...
```

If missing, verify `get_current_tick()` in `iq_option_service_multi.py`.

---

### Issue: Patterns detected for wrong price

**Cause:** Using BID instead of MID for liquidation comparison

**Solution:** The new system automatically handles this:
- **Pattern Detection**: Uses BID candles (raw data from API)
- **Outcome Calculation**: Should use MID candles (future enhancement)

**Current Status:** 
- BID buffers: ✅ Implemented
- MID buffers: ✅ Implemented
- Pattern detection on BID: ✅ Working
- Outcome validation on MID: ⚠️ Future enhancement (requires linking MID to analysis)

---

## 📊 Performance Comparison

### Startup Time

| Configuration | Old System | New System |
|---------------|------------|------------|
| 1 instrument, no charts | 3-5s | 3-5s |
| 1 instrument, with charts | 5-8s | 5-8s |
| 3 instruments, no charts | N/A | 5-8s |
| 3 instruments, with charts | N/A | 10-15s |
| 10 instruments, no charts | N/A | 15-20s |

**Recommendation:** Use `GENERATE_HISTORICAL_CHARTS=false` in production.

---

### Memory Usage

| Configuration | Old System | New System |
|---------------|------------|------------|
| 1 instrument | ~50 MB | ~50 MB |
| 3 instruments | N/A | ~80 MB |
| 10 instruments | N/A | ~150 MB |

**Note:** Buffers are capped at 500 candles per instrument using `deque(maxlen=500)`.

---

## ✅ Post-Migration Validation

### 1. Verify Multi-Instrument Monitoring
```bash
# Check logs for each instrument
grep "Polling iniciado para" logs/bot.log

# Should show:
# Polling iniciado para EURUSD
# Polling iniciado para GBPUSD
# Polling iniciado para USDJPY
```

### 2. Verify Dual Buffers
```bash
# Check for both BID and MID candles in logs
grep "VELA BID CERRADA" logs/bot.log
grep "VELA MID CERRADA" logs/bot.log
```

### 3. Verify Isolated Processing
```bash
# Pattern detection should happen for each instrument independently
grep "PATTERN DETECTED" logs/bot.log

# Should show multiple instruments:
# PATTERN DETECTED | IQOPTION_BID | SHOOTING_STAR | EURUSD
# PATTERN DETECTED | IQOPTION_BID | HAMMER | GBPUSD
```

### 4. Verify Dataset Storage
```bash
# Check that outcomes are being saved
tail -f data/trading_signals_dataset.jsonl

# Should show entries with proper symbol field:
# {"symbol": "EURUSD", "pattern": "SHOOTING_STAR", ...}
# {"symbol": "GBPUSD", "pattern": "HAMMER", ...}
```

---

## 🎯 Rollback Plan (If Needed)

If you encounter issues and need to revert:

### Option 1: Use Old Service (Single Instrument)
```python
# In connection_service.py, temporarily revert factory:
if Config.DATA_PROVIDER == "IQOPTION":
    from src.services.iq_option_service import create_iq_option_service_async
    return create_iq_option_service_async(...)
```

### Option 2: Restore Backup
```bash
# Restore old .env
cp .env.backup .env

# Restart bot
python main.py
```

---

## 🚀 Next Steps After Migration

1. **Monitor Performance**: Watch CPU/memory usage for 24 hours
2. **Validate Accuracy**: Compare MID prices with IQ Option platform
3. **Optimize Configuration**: Adjust `TARGET_ASSETS` based on performance
4. **Review Outcomes**: Check if MID-based liquidation logic improves accuracy
5. **Scale Gradually**: Add more instruments one at a time

---

## 📞 Support Resources

- **Architecture Documentation**: `MULTI_INSTRUMENT_REFACTORING.md`
- **Configuration Reference**: `.env.example`
- **Code Comments**: All new files have detailed docstrings
- **Logs**: Check `logs/` directory for detailed execution traces

---

**Migration Completed?** ✅

Test thoroughly before deploying to production!

---

**Version:** Multi-Instrument v2.0  
**Date:** January 2025  
**Author:** Trading Bot Team
