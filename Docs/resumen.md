# Resumen

## 1. Objetivo del Proyecto
Integrar un monitor automatizado 24/7 que capture datos de mercado en tiempo real de TradingView mediante ingeniería inversa de WebSocket. El sistema identificará patrones de velas japonesas en temporalidad de 1 minuto y, al detectar una configuración válida alineada con la tendencia, enviará una alerta inmediata vía Telegram con gráfico visual adjunto.

### 1.1. Objetivo Versión 0.0.2 (MVP Actualizado)
Para la primera iteración funcional, el alcance se limita a probar la viabilidad técnica de monitorear una fuente de datos público:
- **Par:** Únicamente EUR/USD.
- **Fuente de Datos:** FX:EURUSD (Feed público de TradingView - **NO requiere autenticación**).
- **Patrón:** Únicamente detección de Estrella Fugaz (Shooting Star).
- **Visualización:** Generación automática de gráfico de velas (30 últimas) con EMA 200 incluida.
- **Validación:** Confirmar estabilidad de conexión WebSocket pública, convergencia de EMA 200, detección de patrones y envío de alertas con contexto visual.

### 1.2. Cambios Críticos Implementados vs Plan Original

#### ✅ **Autenticación No Requerida (Cuenta Gratuita)**
- **Plan Original:** Usar `sessionid` de cuenta TradingView autenticada.
- **Implementación Real:** TradingView proporciona **datos en tiempo real sin autenticación** para instrumentos Forex.
- **Ventaja:** No hay riesgo de bloqueo de cuenta, no se requiere renovación de tokens, sistema completamente autónomo.
- **Variable `.env`:** `TV_SESSION_ID` ahora es opcional (valor: `not_required_for_public_data`).

#### 📊 **Generación Automática de Gráficos**
- **Nueva Funcionalidad:** Cada alerta incluye un gráfico de velas japonesas codificado en Base64.
- **Implementación:**
  - Biblioteca: `mplfinance==0.12.10b0` para generación profesional de gráficos financieros.
  - Estilo: Tema oscuro (`'nightclouds'`) con velas verdes (alcistas) y rojas (bajistas).
  - EMA 200: Línea cyan superpuesta sobre el precio.
  - Lookback: 30 velas configurables vía `CHART_LOOKBACK`.
  - Ejecución: Generación en **hilo separado** (`asyncio.to_thread`) para no bloquear WebSocket.
  - Tamaño: ~76 KB en Base64 (~57 KB imagen PNG).
- **Control de Costos:** Variable `SEND_CHARTS` permite deshabilitar envío de imágenes en producción (ahorra ~10x en costos de API Gateway).

#### 🔄 **Protocolo de Heartbeat Optimizado**
- **Plan Original:** Heartbeat proactivo enviado por el cliente cada 30s.
- **Implementación Real:** Heartbeat **pasivo** - el servidor envía `~h~{id}` y el cliente responde `~h~{id}`.
- **Ventaja:** Evita errores `protocol_error: wrong data`, conexión más estable.

#### 📡 **Fuente Única en MVP (FX:EURUSD)**
- **Plan Original:** Dual-Source con OANDA (primaria) + FX (secundaria).
- **Implementación MVP:** Solo FX:EURUSD para validar estabilidad.
- **Justificación:** OANDA deshabilitado temporalmente (comentado en `config.py`) para testing inicial.
- **Roadmap:** Reactivar OANDA en v0.0.3 una vez validado el feed público.

#### 💰 **Optimización de Costos API Gateway**
- **Nueva Variable:** `SEND_CHARTS=false` (default) para enviar solo texto.
- **Comparativa:**
  - `SEND_CHARTS=false`: ~1 KB/request → $0.0000035/alerta
  - `SEND_CHARTS=true`: ~76 KB/request → $0.000035/alerta (10x más caro)
- **Recomendación:** Producción con `SEND_CHARTS=false`, debugging con `true`.

## 2. Estrategia de Alerta y Protocolo Operativo
El sistema funciona estrictamente como soporte a la decisión. NO ejecuta operaciones.

### 2.1. Pares a Monitorear (Versiones posteriores a 0.1)
EUR/USD
GBP/USD
USD/JPY
USD/CHF
USD/CAD
AUD/USD
NZD/USD
Nota: Esta lista es inicial. Se agregarán más pares e instrumentos en el futuro a medida que se valide la estrategia en los pares principales.

### 2.2. Temporalidad
Velas de 1 Minuto (1m): El análisis técnico y la notificación se generan estrictamente en el cierre de la vela ($t_{incoming} > t_{current}$).

### 2.3. Lógica de Notificación (Dual Source)
El sistema utiliza un modelo de confirmación cruzada para filtrar el ruido inherente a los proveedores de datos.

**Notificación ESTÁNDAR:** Se envía cuando UNA de las fuentes detecta el patrón válido.
- Mensaje (Con Filtro): "⚠️ OPORTUNIDAD ALINEADA | EURUSD"
- Mensaje (Sin Filtro): "📈 PATRÓN DETECTADO | EURUSD"
- Incluye: Apertura, Máximo, Mínimo, Cierre (palabras completas, no abreviaturas)
- Formato: Negrita con asterisco simple (*), no doble (**)
- Datos: EMA 200, Tendencia, Confianza del patrón
- Gráfico: Adjunto en Base64 (si `SEND_CHARTS=true`)

**Ejemplo de mensaje estándar:**
```
📊 *Fuente:* FX
📈 *Patrón:* SHOOTING_STAR
🕒 *Timestamp:* 2025-11-20 14:32:00
💰 *Apertura:* 1.09050
💰 *Máximo:* 1.09180
💰 *Mínimo:* 1.09020
💰 *Cierre:* 1.09040
📉 *EMA 200:* 1.08950
🎯 *Tendencia:* BULLISH
✨ *Confianza:* 85%

⚡ *Verificar gráfico manualmente antes de operar.*
```

**Notificación FUERTE (Strong):** Se envía cuando AMBAS fuentes detectan el patrón válido en el mismo cierre de vela (ventana de 2s).
- Mensaje: "🔥 ALERTA CONFIRMADA | EURUSD | Coincidencia DUAL"
- Incluye: Comparativa de ambas fuentes con datos completos
- Formato: Negrita con asterisco simple (*), palabras completas
- Gráfico: Prioriza gráfico de la fuente principal

**Ejemplo de mensaje fuerte:**
```
🎯 *CONFIRMACIÓN DUAL-SOURCE*
📊 *Fuentes:* FX + OANDA
📈 *Patrón:* SHOOTING_STAR
🕒 *Timestamp:* 2025-11-20 14:32:00

*FX:*
  • *Apertura:* 1.09050
  • *Máximo:* 1.09180
  • *Mínimo:* 1.09020
  • *Cierre:* 1.09040
  • *EMA 200:* 1.08950
  • *Confianza:* 85%

*OANDA:*
  • *Apertura:* 1.09048
  • *Máximo:* 1.09175
  • *Mínimo:* 1.09018
  • *Cierre:* 1.09038
  • *EMA 200:* 1.08948
  • *Confianza:* 82%

📉 *Tendencia:* BULLISH
✨ *Confianza Promedio:* 84%

🚀 *Alta probabilidad. Revisar retroceso del 50% en primeros 30s de la siguiente vela.*
```

**Formato JSON de Telegram API:**
```json
{
  "first_message": "🔥 ALERTA CONFIRMADA | EURUSD",
  "image_base64": "iVBORw0KGgoAAAANS...",
  "message_type": "markdown",
  "entries": [
    {
      "subscription": "trade:alert",
      "message": "Cuerpo del mensaje con detalles técnicos"
    }
  ]
}
```

**⚠️ Estado Actual (MVP v0.0.2):** Solo alertas ESTÁNDAR activas (FX única fuente). Dual-Source se activará al reintegrar OANDA.

## 3. Matriz de Patrones y Tendencia

### 3.1. Definición de Tendencia (Filtro Macro)
Se utiliza la EMA 200 como el juez principal de la tendencia para filtrar operaciones contra-corriente.
Tendencia ALCISTA: Precio de Cierre > EMA 200.
Solo se buscan compras (Martillos).
Tendencia BAJISTA: Precio de Cierre < EMA 200.
Solo se buscan ventas (Estrellas Fugaces).

### 3.2. Reglas de Disparo

**IMPORTANTE:** El sistema soporta dos modos de operación configurables mediante `USE_TREND_FILTER`:

#### Modo A: CON Filtro de Tendencia (`USE_TREND_FILTER=true`) - Por Defecto
Sistema conservador que SOLO notifica patrones alineados con la tendencia dominante:

A. Escenario: Tendencia ALCISTA (Precio > EMA 200)
Patrón: Martillo (Hammer)
Acción: 🚨 ALERTA DE COMPRA.
Contexto: Señal de rebote a favor de la tendencia.
Patrón: Hombre Colgado / Estrella Fugaz
Acción: Ignorar (contra-tendencia).

B. Escenario: Tendencia BAJISTA (Precio < EMA 200)
Patrón: Estrella Fugaz (Shooting Star)
Acción: 🚨 ALERTA DE VENTA.
Contexto: Señal de rechazo a favor de la caída.
Decisión Humana: Esperar retroceso del 50% en los primeros 30s de la siguiente vela para entrar.
Patrón: Martillo Invertido / Martillo
Acción: Ignorar (contra-tendencia).

**Título de Notificación:** "⚠️ OPORTUNIDAD ALINEADA | EURUSD"

#### Modo B: SIN Filtro de Tendencia (`USE_TREND_FILTER=false`)
Sistema más agresivo que notifica CUALQUIER patrón detectado sin importar la tendencia:

- Detecta: Shooting Star, Hanging Man, Inverted Hammer, Hammer
- Acción: 🚨 NOTIFICA SIEMPRE que se cumplen los criterios matemáticos del patrón
- Contexto: El trader decide manualmente si la tendencia es apropiada
- Ventaja: Captura más oportunidades potenciales
- Desventaja: Mayor ruido, requiere análisis adicional del trader

**Título de Notificación:** "📈 PATRÓN DETECTADO | EURUSD"

#### Comparativa de Títulos:
- **Con Filtro:** "⚠️ OPORTUNIDAD ALINEADA" - Indica que el patrón está validado por tendencia
- **Sin Filtro:** "📈 PATRÓN DETECTADO" - Indica solo detección matemática del patrón

**El contenido del mensaje (entries.message) es IDÉNTICO en ambos modos**, solo cambia el título para diferenciar el nivel de validación.

## 4. Arquitectura Tecnológica Modular

### 4.1. Estructura del Programa (main.py)

**Módulo 1: Connection Service (WebSocket Público)**
- Gestiona conexión WebSocket a `data.tradingview.com` en **modo público** (sin autenticación).
- **Headers Anti-WAF:** Rotación de User-Agent para imitar navegadores reales (Chrome/Firefox).
- **Heartbeat Pasivo:** Responde a pings del servidor (`~h~{id}`) en lugar de enviar proactivamente.
- **Snapshot Inicial:** Descarga 1000 velas históricas al conectar para convergencia de EMA 200.
- **Reconexión Automática:** Backoff exponencial (5s → 300s) en caso de desconexión.
- **Graceful Shutdown:** Envía comandos `remove_series` antes de cerrar WebSocket.

**Módulo 2: Analysis Service (Core Logic)**
- **Cálculo Vectorizado:** Usa `pandas` para gestionar arrays de precios con alta eficiencia.
- **Integridad Matemática (Buffer):**
  - Se solicitan 1000 velas al conectar.
  - EMA 200 converge correctamente con mínimo 600 velas.
  - Sistema no emite señales hasta alcanzar buffer mínimo.
- **Validación de Patrones:** Detecta proporciones estrictas (Cuerpo vs Mecha) con scoring de confianza (0-100%).
- **Generación de Gráficos:**
  - Biblioteca: `mplfinance` con backend sin GUI (`matplotlib.use('Agg')`).
  - Ejecución asíncrona: `asyncio.to_thread()` para no bloquear Event Loop.
  - Output: Imagen PNG codificada en Base64.
  - Lookback: 30 velas configurables.
  - Incluye: EMA 200 (línea cyan), volumen, timestamp.

**Módulo 3: Notification Service (Output)**
- Cliente HTTP asíncrono (`aiohttp`) con timeout de 10s.
- **Dual-Source Buffer:** Ventana temporal de 2s para correlacionar señales de múltiples fuentes.
- **Limpieza Automática:** Task periódico que elimina alertas expiradas del buffer.
- **Race Condition Fix:** Verificación doble antes de eliminar alertas del diccionario.
- **Guardado Local:** Imágenes Base64 se decodifican y guardan en `logs/chart_*.png` para auditoría.
- **Control de Costos:** Variable `SEND_CHARTS` permite desactivar envío de imágenes (ahorro ~90% en transfer costs).

**Módulo 4: Charting Utilities (Nuevo)**
- **Generación de Gráficos:** `generate_chart_base64(dataframe, lookback, title)`
- **Validación:** `validate_dataframe_for_chart()` verifica columnas requeridas y datos suficientes.
- **Estilo:** Tema oscuro profesional con velas verdes/rojas, EMA 200 cyan, panel de volumen.
- **Performance:** ~100-500ms por gráfico (ejecutado en hilo separado, no bloquea WebSocket).

### 4.2. Infraestructura
- **Proveedor:** Oracle Cloud Infrastructure (OCI) - Tier "Always Free" o desarrollo local.
- **Entorno:** Windows 10/11 (desarrollo) | Linux VM (producción).
- **Runtime:** Python 3.10+, asyncio con `WindowsSelectorEventLoopPolicy`.
- **Dependencias:**
  - `websockets==12.0` - Cliente WebSocket
  - `aiohttp==3.9.1` - Cliente HTTP asíncrono
  - `pandas==2.1.4` - Procesamiento de series temporales
  - `numpy==1.26.2` - Cálculos matemáticos
  - `mplfinance==0.12.10b0` - Generación de gráficos financieros
  - `python-dotenv==1.0.0` - Gestión de variables de entorno

## 5. Flujo de Lógica y Procesos Críticos

### 5.1. Autenticación y Calidad de Datos

**🎉 Cambio Crítico Implementado:**
- **NO se requiere autenticación:** TradingView proporciona datos en tiempo real de Forex **sin login**.
- **Cuentas gratuitas funcionan:** No se necesita suscripción paga ni SessionID válido.
- **Datos NO retrasados:** Feed público de FX:EURUSD es en tiempo real (actualización cada ~5s).
- **Validación de Calidad:** Sistema verifica flag de datos al inicio. Si detecta "Delayed" o "CBOE BZX", loguea advertencia pero continúa (no detiene operación).

**Manejo de Errores del Protocolo:**
- Si TradingView envía `critical_error` o `protocol_error`, se loguea el mensaje pero NO se detiene el bot.
- Reconexión automática ante errores de conexión.
- Heartbeat pasivo previene errores `invalid_method`.

### 5.2. Inicialización y Reconexión

**Flujo de Startup:**
1. **Conexión WebSocket:** Se conecta a `wss://data.tradingview.com/socket.io/websocket`
2. **Creación de Sesión:** Se genera `quote_session_id` único (ej: `qs_abc123xyz`)
3. **Suscripción a Instrumento:** Envía `create_series` para FX:EURUSD, temporalidad 1m
4. **Snapshot Histórico:** Recibe `timescale_update` con 1000 velas
5. **Carga en Buffer:** `AnalysisService.load_historical_candles()` puebla DataFrame
6. **Cálculo Inicial EMA:** EMA 200 converge con 600+ velas
7. **Modo Streaming:** Procesa actualizaciones en tiempo real (`du` messages)
8. **Detección Activa:** Sistema comienza a emitir señales tras validar buffer mínimo

**Reconexión Automática:**
- Backoff exponencial: 5s → 10s → 20s → ... → 300s (máximo)
- Máximo 10 intentos antes de detener el servicio
- Logs detallados de cada intento
- Reset de contador tras conexión exitosa

### 5.3. Procesamiento de Velas

**Separación de Responsabilidades (Crítico):**

**📥 Snapshot Histórico (1000 velas):**
- Mensaje TradingView: `timescale_update` (al inicio)
- Método: `ConnectionService._load_historical_snapshot()`
- Destino: `AnalysisService.load_historical_candles()`
- Comportamiento:
  - ✅ Carga masiva en DataFrame
  - ✅ Calcula EMA 200 inicial
  - ❌ NO genera gráficos
  - ❌ NO emite alertas
  - ❌ NO loguea cada vela (solo log de resumen)

**🕒 Actualización en Tiempo Real (1 vela):**
- Mensaje TradingView: `du` (data update, continuo)
- Método: `ConnectionService._process_realtime_update()`
- Destino: `AnalysisService.process_candle()`
- Comportamiento:
  - ✅ Detecta cierre de vela por cambio de timestamp
  - ✅ Genera gráfico asíncrono (`asyncio.to_thread`)
  - ✅ Emite señal si detecta patrón válido
  - ✅ Loguea cada vela cerrada con detalles

**Ventajas de la Separación:**
- Evita spam de logs (330+ "GENERATING CHART" al inicio)
- Performance optimizada (no genera 1000 gráficos innecesarios)
- Lógica clara y mantenible
- Buffer se inicializa correctamente (antes solo mostraba 18/600 velas)

### 5.4. Gestión de Memoria y Recursos

**Buffer Limitado:**
- Configuración: `Config.CHART_LOOKBACK = 30` velas para gráficos
- DataFrame: Mantiene últimas 1000 velas (se purgan las más antiguas)
- EMA 200: Requiere mínimo 600 velas para convergencia (3x el período)

**Generación Asíncrona de Gráficos:**
- Ejecución en hilo separado: `await asyncio.to_thread(generate_chart_base64, ...)`
- No bloquea Event Loop principal
- WebSocket continúa procesando ticks durante generación
- Timeout implícito: Si falla, continúa sin gráfico (no detiene alertas)

### 5.5. Definiciones Técnicas Finales

**Simbología:**
- **MVP Actual:** `FX:EURUSD` (fuente única, pública, sin auth)
- **Roadmap:** Reactivar `OANDA:EURUSD` como primaria en v0.0.3

**Gestión de Buffer:**
- Mínimo: 600 velas (3x EMA 200)
- Recomendado: 1000 velas (5x EMA 200) ← **Implementado**
- Snapshot: Se solicitan 1000 velas al conectar

**Variables Críticas `.env`:**
- `TV_SESSION_ID`: Opcional (valor: `not_required_for_public_data`)
- `TELEGRAM_API_URL`: URL completa del endpoint broadcast
- `TELEGRAM_API_KEY`: API Key para header `x-api-key`
- `TELEGRAM_SUBSCRIPTION`: Topic de suscripción (ej: `trade:alert`)
- `SEND_CHARTS`: `true` o `false` para controlar envío de imágenes
- `USE_TREND_FILTER`: `true` o `false` - Habilita/deshabilita filtro de tendencia
  - `true` (default): Solo notifica patrones alineados con tendencia EMA 200
  - `false`: Notifica cualquier patrón detectado sin importar tendencia
- `CHART_LOOKBACK`: Número de velas en gráfico (default: 30)
- `EMA_PERIOD`: Período de EMA (default: 200)
- `DUAL_SOURCE_WINDOW`: Ventana de confirmación en segundos (default: 2.0)
- `LOG_LEVEL`: `DEBUG` o `INFO` (producción recomendado: `INFO`)

---

## 6. Mejoras Implementadas Post-Especificación Inicial

### 6.1. Sistema de Gráficos Visuales
- ✅ Generación automática con `mplfinance`
- ✅ Codificación Base64 para envío por API
- ✅ Guardado local en `logs/` para auditoría
- ✅ Ejecución asíncrona (no bloquea WebSocket)
- ✅ Control de costos con flag `SEND_CHARTS`

### 6.2. Autenticación Simplificada
- ✅ Modo público sin SessionID
- ✅ Sin riesgo de baneos o expiración de tokens
- ✅ Datos en tiempo real sin suscripción paga
- ✅ Sistema completamente autónomo

### 6.3. Protocolo WebSocket Optimizado
- ✅ Heartbeat pasivo (respuesta vs proactivo)
- ✅ Graceful shutdown con comandos de limpieza
- ✅ Logs truncados para mensajes grandes (>500 bytes)
- ✅ Reconexión exponencial con límite de intentos

### 6.4. Manejo de Race Conditions
- ✅ Verificación doble antes de eliminar alertas del buffer
- ✅ Sincronización correcta entre cleanup task y wait tasks
- ✅ Sin errores `KeyError` en Dual-Source logic

### 6.5. Optimización de Costos API Gateway
- ✅ Control granular de envío de imágenes Base64
- ✅ Documentación de impacto económico (10x diferencia)
- ✅ Modo producción vs debugging claramente diferenciado

---

## 7. Próximos Pasos (Roadmap Post-MVP)

### v0.0.3 - Dual-Source Completo
- [ ] Reactivar OANDA como fuente primaria
- [ ] Validar lógica de confirmación cruzada (ventana 2s)
- [ ] Implementar alertas FUERTE con comparativa de fuentes

### v0.1.0 - Expansión de Instrumentos
- [ ] Agregar GBP/USD, USD/JPY, USD/CHF
- [ ] Configuración multi-instrumento simultánea
- [ ] Dashboard de monitoreo en tiempo real

### v0.2.0 - Nuevos Patrones
- [ ] Martillo (Hammer) para compras
- [ ] Doji, Envolvente, Estrella de la Mañana/Tarde
- [ ] Configuración flexible de patrones por instrumento

### v0.3.0 - Persistencia y Analytics
- [ ] Base de datos PostgreSQL/SQLite
- [ ] Historial de señales y backtesting
- [ ] Métricas de precisión por patrón

---

**Versión del Documento:** v0.0.2  
**Última Actualización:** 20 de noviembre de 2025  
**Estado del Proyecto:** ✅ MVP Operativo - Testing en Producción
