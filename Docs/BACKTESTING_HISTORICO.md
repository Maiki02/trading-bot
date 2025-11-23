# 📊 Sistema de Backtesting Histórico

## ✨ Descripción

Sistema completo para generar un dataset de backtesting obteniendo **velas históricas del último mes** de TradingView mediante peticiones por rango de fechas, detectando patrones de velas japonesas y calculando probabilidades históricas.

---

## 📦 Nuevos Archivos

### 1. `src/services/tradingview_service.py`
Servicio reutilizable para obtener velas históricas de TradingView.

**Características:**
- ✅ Conexión temporal a TradingView WebSocket
- ✅ Solicitud de N velas históricas
- ✅ Soporte para cualquier instrumento (BTCUSDT, EURUSD, etc.)
- ✅ Configuración de timeframe (1min, 5min, etc.)
- ✅ Cierre automático de conexión

**Uso:**
```python
from src.services.tradingview_service import TradingViewService

service = TradingViewService()
candles = await service.fetch_historical_candles(
    symbol="BTCUSDT",
    exchange="BINANCE",
    timeframe="1",
    num_candles=1000
)

print(f"Obtenidas {len(candles)} velas")
```

### 2. `backfill_historical_data.py`
Script ejecutable para generar el dataset de backtesting.

**Proceso:**
1. 📅 Dividir el rango de fechas (último mes) en chunks de 6 días
2. 📥 Obtener velas históricas por chunks secuencialmente (evita límite de 10k velas)
3. 🔄 Esperar 3 segundos entre peticiones (evita rate limiting)
4. ⏭️ Saltar las primeras 1,000 velas (usadas para inicializar EMAs)
5. 🔍 Recorrer velas restantes (~40,000 velas para 30 días en 1min)
6. 🎯 Para cada vela con patrón detectado:
   - Calcular EMAs (200, 50, 30, 20) con buffer de 1,000 velas anteriores
   - Calcular alineación de EMAs
   - Calcular score de tendencia
   - Obtener siguiente vela (outcome)
   - Determinar si fue WIN/LOSS
   - Calcular PnL
   - Guardar en `data/trading_signals_dataset.jsonl`

---

## 🚀 Cómo Ejecutar

### Requisitos Previos

Asegúrate de que todas las dependencias estén instaladas:
```bash
pip install -r requirements.txt
```

### Ejecutar Backtesting

```bash
python backfill_historical_data.py
```

### Configuración

Puedes modificar los parámetros en el archivo `backfill_historical_data.py`:

```python
# Instrumento a analizar
SYMBOL = "BTCUSDT"
EXCHANGE = "BINANCE"
TIMEFRAME = "1"  # 1 minuto

# Rango de fechas
END_DATE = datetime.now()  # Fecha final (ahora)
DAYS_TO_FETCH = 30  # Días hacia atrás (último mes)
START_DATE = END_DATE - timedelta(days=DAYS_TO_FETCH)

DAYS_PER_REQUEST = 6  # Días por petición (6 días = ~8,640 velas)
REQUEST_DELAY = 3  # Segundos entre peticiones

# Buffer y skip
SKIP_CANDLES = 1000    # Velas a saltar (para inicializar EMAs)
BUFFER_SIZE = 1000     # Tamaño del buffer para cálculo de EMAs
```

---

## 📊 Salida del Backtesting

### Ejemplo de Log

```
================================================================================
🚀 INICIANDO BACKTESTING HISTÓRICO
================================================================================
📊 Instrumento: BINANCE:BTCUSDT
⏱️  Timeframe: 1 minuto(s)
📅 Rango: 2025-10-24 a 2025-11-23 (30 días)
📦 Estrategia: Peticiones de 6 días cada una
⏭️  Velas a saltar: 1,000
================================================================================

📥 PASO 1: Obteniendo datos históricos de TradingView...
📦 Dividiendo 30 días en 5 peticiones de ~6 días

📥 Chunk 1/5: 2025-11-17 a 2025-11-23 (~6 días, ~8,640 velas)
✅ Recibidas: 8,640 velas | Filtradas al rango: 8,640 velas
⏳ Esperando 3s antes de la siguiente petición...

📥 Chunk 2/5: 2025-11-11 a 2025-11-17 (~6 días, ~8,640 velas)
✅ Recibidas: 8,640 velas | Filtradas al rango: 8,640 velas
⏳ Esperando 3s antes de la siguiente petición...

... [chunks 3-5] ...

📊 Resumen de obtención:
   Total recibidas: 43,200 velas
   Duplicados eliminados: 0
   Total únicas: 43,200 velas
✅ Total obtenidas: 43,200 velas históricas
🔍 Velas a analizar: 42,200

🔍 PASO 2: Procesando velas y detectando patrones...
📊 Progreso: 0.0% (0/42,200 velas procesadas)
💾 Patrón guardado: SHOOTING_STAR | Score: -7 | Outcome: WIN | PnL: 15.30
💾 Patrón guardado: HAMMER | Score: 5 | Outcome: LOSS | PnL: -8.50
...
📊 Progreso: 100.0% (42,200/42,200 velas procesadas)

================================================================================
✅ BACKTESTING COMPLETADO
================================================================================
🎯 Patrones detectados: 1,247
💾 Patrones guardados: 1,247
📊 Dataset: data/trading_signals_dataset.jsonl
================================================================================
```

### Estructura del Dataset Generado

Cada línea en `data/trading_signals_dataset.jsonl` contiene:

```json
{
  "timestamp": 1732320000,
  "pattern": "SHOOTING_STAR",
  "trend": "WEAK_BEARISH",
  "trend_score": -3,
  "is_trend_aligned": true,
  "outcome_timestamp": 1732320060,
  "outcome_direction": "ROJA",
  "expected_direction": "ROJA",
  "outcome_result": "WIN",
  "pnl": 15.30,
  "raw_data": {
    "ema_200": 86500.45,
    "ema_50": 86450.23,
    "ema_30": 86420.78,
    "ema_20": 86380.12,
    "close": 86316.00,
    "open": 86329.54,
    "algo_version": "v2.0"
  }
}
```

---

## 🔧 Integración con Connection Service

El `ConnectionService` ya puede usar el `TradingViewService` si necesita obtener datos históricos de forma programática.

**Ejemplo de uso en otros scripts:**

```python
from src.services.tradingview_service import get_historical_candles

# Obtener 5000 velas de EUR/USD
candles = await get_historical_candles(
    symbol="EURUSD",
    exchange="OANDA",
    timeframe="1",
    num_candles=5000
)
```

---

## 📈 Análisis del Dataset

Una vez generado el dataset, puedes usar `StatisticsService` para análisis avanzado:

```bash
python test_statistics_service.py
```

O usar el script de análisis:

```bash
python scripts/analyze_dataset.py
```

---

## ⚠️ Limitaciones y Consideraciones

### 1. **Sistema de Chunks por Fecha**
- ✅ **NUEVO SISTEMA**: Obtiene datos por rangos de fechas en lugar de número fijo de velas
- El script divide el rango total (ej: 30 días) en chunks de **6 días** cada uno
- **Ventajas**:
  - Obtiene datos completos del último mes (~43,200 velas para 1min)
  - Evita el límite de 10k velas de TradingView
  - Mayor control sobre el rango temporal exacto
- **Configuración**:
  ```python
  DAYS_TO_FETCH = 30  # Último mes
  DAYS_PER_REQUEST = 6  # Chunks de 6 días
  REQUEST_DELAY = 3  # 3 segundos entre peticiones
  ```

### 2. **Tiempo de Ejecución**
- Obtener y procesar ~8,000-10,000 velas puede tomar **2-5 minutos** dependiendo de:
  - Velocidad de conexión
  - Latencia a TradingView
  - CPU disponible para cálculos de EMAs

### 3. **Optimización de Detección de Patrones**
- ✅ **OPTIMIZADO**: Solo verifica patrones compatibles con el color de la vela
- **Velas ROJAS**: Solo verifica Shooting Star y Hanging Man (2 verificaciones)
- **Velas VERDES**: Solo verifica Hammer e Inverted Hammer (2 verificaciones)
- **Velas DOJI**: No se analizan (sin patrón claro)
- **Resultado**: 50% menos verificaciones innecesarias

### 4. **Espacio en Disco**
- El dataset JSONL puede crecer a **varios MB** con 1,000+ patrones
- Cada registro ocupa ~300-500 bytes
- Dataset de 30 días típicamente genera **2,000-5,000 patrones** (~1-2 MB)

### 5. **Calidad de Datos**
- Las primeras 1,000 velas se usan solo para inicializar EMAs
- Los patrones detectados en las primeras 200 velas pueden tener EMAs incompletas (se saltan)
- Sistema de chunks elimina automáticamente duplicados por timestamp

---

## 🎯 Casos de Uso

### 1. **Backtesting de Estrategias**
Evalúa el rendimiento histórico de tus patrones de velas.

### 2. **Entrenamiento de Modelos ML**
Usa el dataset como input para entrenar modelos de machine learning.

### 3. **Análisis de Probabilidades**
Calcula win rates históricos por patrón, score y condiciones de mercado.

### 4. **Optimización de Parámetros**
Prueba diferentes configuraciones de EMAs y scoring para maximizar probabilidad.

---

## 🔄 Actualización del Dataset

Para cambiar el rango de fechas:

```bash
# Modificar parámetros en backfill_historical_data.py
DAYS_TO_FETCH = 60  # Cambiar a 60 días (2 meses)
DAYS_PER_REQUEST = 6  # Mantener chunks de 6 días

# Ejecutar nuevamente
python backfill_historical_data.py
```

**NOTA:** El script no elimina datos existentes, solo agrega nuevos registros al JSONL.

**Para diferentes instrumentos:**
```python
# Cambiar instrumento
SYMBOL = "EURUSD"
EXCHANGE = "OANDA"
TIMEFRAME = "5"  # 5 minutos (más velas por día)
```

---

## 📚 Documentación Relacionada

- **Sistema de Probabilidad Histórica:** `Docs/sistema_probabilidad_historica.md`
- **Guía de Inicio Rápido:** `Docs/GUIA_PROBABILIDAD_HISTORICA.md`
- **Análisis de Dataset:** `Docs/dataset.md`

---

## ✅ Estado

**Sistema:** ✅ **OPERATIVO Y LISTO PARA PRODUCCIÓN**

**Próximos pasos:**
1. Ejecutar `python backfill_historical_data.py`
2. Esperar a que complete el backtesting
3. Analizar dataset con `StatisticsService`
4. ¡Empezar a operar con datos históricos!

---

## 🆘 Troubleshooting

### Error: "No se obtuvieron suficientes velas"

**Causa:** Las peticiones no retornaron suficientes datos.

**Solución:**
- Verifica tu conexión a internet
- Reduce `DAYS_TO_FETCH` a 15 o 20 días
- Aumenta `DAYS_PER_REQUEST` a 7 u 8 días
- Intenta con otro instrumento (EURUSD, BTCUSDT)

### Error: "Timeout esperando datos"

**Causa:** TradingView tardó más de 30s en responder un chunk.

**Solución:**
- Aumenta el timeout en `tradingview_service.py`:
  ```python
  await asyncio.wait_for(self.data_received.wait(), timeout=60.0)  # 60s
  ```
- Reduce `DAYS_PER_REQUEST` a 4 o 5 días (menos velas por petición)

### El dataset tiene pocos patrones

**Causa:** Los patrones son raros en el mercado elegido.

**Solución:**
- Aumenta `DAYS_TO_FETCH` a 60 o 90 días
- Prueba con un instrumento más volátil (criptomonedas)
- Reduce timeframe a 1 minuto (más velas = más patrones potenciales)

### Muchos duplicados en el resumen

**Causa:** Overlap entre chunks (normal en el sistema).

**Solución:**
- No requiere acción, el sistema elimina duplicados automáticamente
- Los duplicados se muestran solo para transparencia
- Solo las velas únicas se procesan

---

¡Listo para generar tu dataset de backtesting! 🚀
