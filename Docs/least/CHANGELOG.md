# Actualización del Sistema - Respuesta a Consultas

## 📝 Cambios Más Recientes (22 Nov 2025)

### 1. ✅ Notificaciones de Resultado (Outcome Notifications)

**Archivos modificados:**
- ✅ `.env` - Agregado `TELEGRAM_OUTCOME_SUBSCRIPTION`
- ✅ `config.py` - `TelegramConfig` ahora incluye `outcome_subscription`
- ✅ `src/services/telegram_service.py` - Nueva función `send_outcome_notification()`
- ✅ `src/logic/analysis_service.py` - Envío de notificación en `_close_signal_cycle()`
- ✅ `src/logic/candle.py` - Nueva función `get_candle_direction()`
- ✅ `main.py` - Paso de `telegram_service` al constructor de `AnalysisService`

**Funcionalidad:**
El sistema ahora envía **dos notificaciones separadas**:
1. **Notificación de Patrón** (inmediata): Cuando se detecta un patrón (Shooting Star, Hammer, etc.)
2. **Notificación de Resultado** (después de 1 min): Cuando cierra la vela siguiente, informando si fue VERDE, ROJA o DOJI

**Nuevo campo en .env:**
```env
# Subscription para notificaciones de resultados (puede ser igual o diferente a la de patrones)
TELEGRAM_OUTCOME_SUBSCRIPTION=trade:alert
```

**Nueva función pública en TelegramService:**
```python
async def send_outcome_notification(
    self,
    source: str,
    symbol: str,
    direction: str,  # "VERDE", "ROJA", o "DOJI"
    chart_base64: Optional[str] = None
) -> None:
    """Envía notificación del resultado de la vela."""
```

**Refactorización interna:**
- `_send_telegram_notification()`: Nueva función base reutilizable
- `_send_to_telegram()`: Ahora llama a la función base
- `send_outcome_notification()`: Nueva función para resultados

**Utilidad añadida:**
```python
def get_candle_direction(open_price: float, close: float) -> str:
    """Retorna 'VERDE', 'ROJA', o 'DOJI'"""
```

---

### 2. ✅ Script de Visualización de Patrones

**Archivo nuevo:**
- ✅ `test/visualize_patterns.py` - Herramienta de análisis visual de patrones detectados

**Funcionalidad:**
- Genera gráficos normalizados (porcentajes) de todas las velas en `test_data.json`
- Valida cada vela contra las reglas oficiales de `candle.py`
- Colorea según validez: 🟦 AZUL (válida) | 🟥 ROJO (inválida)
- Filtra por tipo de patrón específico
- Guarda imágenes en `test/images_patterns/`

**Uso:**
```bash
# Todos los patrones
python test/visualize_patterns.py

# Filtro por patrón específico
python test/visualize_patterns.py --pattern shooting_star
python test/visualize_patterns.py --pattern hammer
python test/visualize_patterns.py --pattern hanging_man
python test/visualize_patterns.py --pattern inverted_hammer
```

**Métricas reportadas:**
- Precisión de detección por patrón
- Distribución de velas válidas/inválidas
- Estadísticas de normalización (rango, volatilidad)

**Implementación técnica:**
- Importa funciones de `candle.py` usando `importlib.util` (evita imports circulares)
- Normalización: Cada vela usa su apertura como 0%, calcula el resto como % de cambio
- Valida con las mismas funciones que usa el bot en producción

---

### 3. ✅ Limpieza de Referencias Residuales

**Contexto:**
Después del git revert del sistema de confianza por niveles, quedaron referencias a `ema_100` que causaban `AttributeError` en runtime.

**Archivos limpiados:**
- ✅ `src/services/telegram_service.py` - Removido `ema_100_str` de formateo
- ✅ `src/logic/analysis_service.py` - Removidas 5 referencias a `ema_100`:
  - Variable `ema_100_val`
  - Formateo `ema_100_str`
  - Log output
  - Diccionario `emas_dict`
  - Constructor de `PatternSignal`

**Estado final:**
Sistema funciona solo con EMAs: 20, 30, 50, 200 (como estaba antes del revert).

---

## 📝 Cambios Anteriores

## Cambios Realizados

### 1. ✅ Eliminación de TELEGRAM_CHAT_ID

**Archivos modificados:**
- ✅ `.env` - Eliminado `TELEGRAM_CHAT_ID`, agregado `TELEGRAM_SUBSCRIPTION`
- ✅ `.env.example` - Actualizado con nuevo formato
- ✅ `config.py` - `TelegramConfig` ahora usa `subscription` en lugar de `chat_id`
- ✅ `src/services/telegram_service.py` - Adaptado al endpoint `/admin/bots/{id}/broadcast`
- ✅ `QUICKSTART.md` - Documentación actualizada

**Nuevo formato de configuración:**
```env
# URL completa del endpoint (incluyendo el bot ID)
TELEGRAM_API_URL=https://api.tu-dominio.com/admin/bots/12345/broadcast

# API Key para header x-api-key
TELEGRAM_API_KEY=tu_api_key_aqui

# Topic/Subscription para el broadcast
TELEGRAM_SUBSCRIPTION=trading_signals
```

**Nuevo formato del payload HTTP:**
```json
{
  "first_message": "🔥 ALERTA CONFIRMADA | EURUSD",
  "entries": [
    {
      "subscription": "trading_signals",
      "message": "📊 **Fuentes:** OANDA + FX\n..."
    }
  ]
}
```

El sistema ahora es compatible con tu endpoint `BroadcastRequest` que acepta múltiples entradas por suscripción.

---

### 2. ✅ Mejora del Graceful Shutdown

**Archivo modificado:**
- ✅ `src/services/connection_service.py` - Método `stop()` mejorado

**Cambios implementados:**

#### Antes:
```python
async def stop(self) -> None:
    self.is_running = False
    # Cancelar heartbeat
    if self.heartbeat_task:
        self.heartbeat_task.cancel()
    # Cerrar WebSocket directamente
    if self.websocket:
        await self.websocket.close()
```

#### Ahora:
```python
async def stop(self) -> None:
    self.is_running = False
    
    # 1. Cancelar heartbeat
    if self.heartbeat_task:
        self.heartbeat_task.cancel()
    
    # 2. Enviar mensajes de cierre a TradingView
    if self.websocket and not self.websocket.closed:
        # Cerrar cada chart session
        for chart_session_id in self.chart_sessions.values():
            close_chart_msg = encode_message("remove_series", [chart_session_id, "s1"])
            await self.websocket.send(close_chart_msg)
        
        # Cerrar quote session
        close_quote_msg = encode_message("quote_remove_symbols", [self.quote_session_id])
        await self.websocket.send(close_quote_msg)
        
        # Esperar a que se envíen los mensajes
        await asyncio.sleep(0.5)
        
        # 3. Cerrar WebSocket
        await self.websocket.close()
```

**Beneficios del nuevo shutdown:**

✅ **Limpieza de sesiones:** Envía comandos `remove_series` y `quote_remove_symbols` a TradingView  
✅ **Notificación al servidor:** TradingView sabe que cerramos intencionalmente (no es un timeout)  
✅ **Prevención de recursos huérfanos:** Las sesiones del servidor se liberan correctamente  
✅ **Mejor gestión de recursos:** Evita que TradingView mantenga sesiones zombie  
✅ **Logs detallados:** Se registra cada paso del cierre con `logger.debug()`  

**Flujo completo del shutdown:**
```
Usuario presiona Ctrl+C
    ↓
main.py detecta KeyboardInterrupt
    ↓
TradingBot.stop() se ejecuta
    ↓
1. Connection Service:
   - Cancela heartbeat task
   - Envía "remove_series" para cada chart
   - Envía "quote_remove_symbols"
   - Espera 0.5s para que se envíen
   - Cierra WebSocket
    ↓
2. Telegram Service:
   - Cancela cleanup task
   - Cierra sesión HTTP aiohttp
    ↓
3. Analysis Service:
   - No requiere cleanup (solo memoria)
    ↓
Logs: "Graceful shutdown completed"
```

---

## 🔍 Respuestas a tus Consultas

### Consulta 1: ¿Podemos eliminar TELEGRAM_CHAT_ID?

**✅ SÍ - IMPLEMENTADO**

Ahora el sistema usa:
- `TELEGRAM_API_URL` → URL completa del endpoint broadcast (incluye bot ID)
- `TELEGRAM_API_KEY` → Para el header `x-api-key`
- `TELEGRAM_SUBSCRIPTION` → El topic/subscription donde se envían las alertas

El payload se construye automáticamente en el formato `BroadcastRequest`:
```json
{
  "first_message": "Título de la alerta",
  "entries": [
    {
      "subscription": "trading_signals",
      "message": "Cuerpo del mensaje con detalles"
    }
  ]
}
```

---

### Consulta 2: ¿Se limpian las conexiones a TradingView de manera segura?

**✅ SÍ - MEJORADO**

El sistema ahora implementa un **graceful shutdown completo** en 3 niveles:

#### Nivel 1: Detección de señales
- `main.py` captura `SIGINT` (Ctrl+C) y `SIGTERM` (kill)
- Windows: `KeyboardInterrupt` en el try-except
- Linux: `signal.SIGINT` y `signal.SIGTERM` handlers

#### Nivel 2: Cascada de shutdown
```python
# Orden de detención (inverso a la inicialización)
1. Connection Service → Cierra WebSocket con protocolo
2. Telegram Service → Cierra sesión HTTP
3. Analysis Service → Libera memoria
```

#### Nivel 3: Protocolo TradingView
Antes de cerrar el socket, se envían:
1. `remove_series` para cada gráfico suscrito
2. `quote_remove_symbols` para cerrar la sesión de cotizaciones
3. Delay de 0.5s para garantizar envío
4. Cierre limpio del WebSocket

**Resultado:** TradingView recibe notificación explícita de cierre, no detecta un timeout.

---

## 🧪 Pruebas Recomendadas

### Probar el nuevo formato de Telegram:

```python
# Ejecutar el bot y forzar una alerta (modo debug)
LOG_LEVEL=DEBUG python main.py
```

Verifica en los logs:
```
📤 Sending STRONG alert to Telegram broadcast...
Payload: {"first_message": "...", "entries": [{"subscription": "trading_signals", ...}]}
✅ Alert sent successfully (STRONG)
```

### Probar el graceful shutdown:

```bash
# Iniciar el bot
python main.py

# Esperar a que conecte (verás "✅ WebSocket connected")

# Presionar Ctrl+C

# Deberías ver:
# 🛑 Stopping Connection Service...
# 📤 Sending close messages to TradingView...
# ✅ Closed chart session: cs_oanda_eurusd
# ✅ Closed chart session: cs_fx_eurusd
# ✅ Closed quote session: qs_xxxxx
# 🔌 WebSocket connection closed
# ✅ Connection Service stopped cleanly
# Graceful shutdown completed. All services stopped.
```

---

## 📊 Comparación Antes/Después

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| **Variables .env** | 3 (URL, KEY, CHAT_ID) | 3 (URL, KEY, SUBSCRIPTION) |
| **Formato API** | Custom | BroadcastRequest estándar |
| **Shutdown WebSocket** | Cierre directo | Protocolo de cierre + comandos |
| **Logs de cierre** | Básicos | Detallados con debug |
| **Limpieza de sesiones** | ❌ No | ✅ Sí (remove_series) |
| **Gestión de recursos** | Parcial | Completa |

---

## ✅ Estado Final

- ✅ Sistema adaptado al endpoint `/admin/bots/{id}/broadcast`
- ✅ Formato `BroadcastRequest` implementado
- ✅ Graceful shutdown mejorado con protocolo TradingView
- ✅ Documentación actualizada
- ✅ Configuración simplificada (misma cantidad de variables)

**El bot está listo para usar con tu API y maneja las conexiones de forma segura.**
