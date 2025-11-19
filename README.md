# TradingView Pattern Monitor (MVP v0.0.1)

Sistema automatizado de soporte a la decisión que consume datos de mercado en tiempo real a través de ingeniería inversa del protocolo WebSocket de TradingView. Analiza la formación de velas japonesas (1m) y detecta patrones de reversión (Estrella Fugaz) filtrados por tendencia (EMA 200).

Este proyecto implementa una arquitectura de **confirmación cruzada (Dual-Source)** entre dos fuentes de datos (OANDA y FX:EURUSD) para reducir el ruido y garantizar la integridad de la señal antes de enviar notificaciones a Telegram.

---

## ⚡ Quick Start

**¿Quieres empezar YA?** → Lee **[QUICKSTART.md](./QUICKSTART.md)** (5 minutos)

```powershell
# 1. Instalar dependencias
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configurar .env (obtén SessionID de TradingView)
copy .env.example .env
notepad .env

# 3. Ejecutar
python main.py
```

**Documentación completa más abajo** ⬇️

---

## 🚀 Características Principales

* **Ingestión de Datos:** Cliente WebSocket asíncrono con **multiplexación** para monitorear múltiples instrumentos sin bloqueo de IP.
* **Análisis Cuantitativo:** Cálculo vectorizado con `pandas` para la EMA 200 y detección matemática de patrones sobre un buffer dinámico de 1000 velas.
* **Dual-Source Validation:** Lógica de comparación entre una fuente primaria (OANDA) y secundaria (FX) para emitir alertas de "Alta Probabilidad".
* **Bypass de Restricciones:** Gestión de `SessionID` y headers `Origin` para acceder a datos en tiempo real y evitar el retraso de datos retrasados.
* **Notificaciones:** Integración vía API REST con Telegram para alertas "Estándar" y "Fuertes".

## 🛠 Arquitectura del Proyecto

El sistema funciona bajo un bucle de eventos asíncrono (`asyncio`) dividido en tres servicios modulares:

1.  **Connection Service:** Gestiona la conexión persistente con `data.tradingview.com`, maneja el *handshake*, la autenticación y los *heartbeats*.
2.  **Analysis Service:** Procesa los paquetes de datos crudos, gestiona el DataFrame de velas históricas y ejecuta la lógica de negocio (EMA + Patrones).
3.  **Notification Service:** Orquesta el envío de señales a la API de Telegram basándose en la coincidencia temporal de las fuentes.

## 📋 Requisitos Previos

* Python 3.10+
* Cuenta de TradingView (Gratuita o Pro) para obtención de `sessionid`.
* API Key propia para el servicio de Telegram.

## ⚙️ Instalación y Configuración

### 1. Clonar el repositorio
```bash
git clone https://github.com/Maiki02/trading-bot.git
cd trading-bot
```

### 2. Crear entorno virtual e instalar dependencias

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Obtener el SessionID de TradingView

Este es el paso **MÁS CRÍTICO**. El bot no funcionará sin un `sessionid` válido.

1. Abre [TradingView](https://www.tradingview.com) en tu navegador (Chrome/Firefox/Edge)
2. Inicia sesión con tu cuenta (gratuita o Pro)
3. Presiona **F12** para abrir las DevTools
4. Ve a la pestaña **Application** (Chrome/Edge) o **Storage** (Firefox)
5. En el panel izquierdo, expande **Cookies** > `https://www.tradingview.com`
6. Busca la cookie llamada **`sessionid`**
7. Copia su **Valor** (es una cadena larga, ej: `a1b2c3d4e5f6...`)

⚠️ **IMPORTANTE:** Este token expira. Si el bot deja de funcionar, repite este proceso.

### 4. Configurar Variables de Entorno

Crea un archivo **`.env`** en la raíz del proyecto (copia desde `.env.example`):

```bash
# Windows
copy .env.example .env

# Linux/macOS
cp .env.example .env
```

Edita el archivo `.env` y completa los siguientes campos **OBLIGATORIOS**:

```env
# ============= CRÍTICO =============
TV_SESSION_ID=pega_aqui_tu_sessionid_de_tradingview

# ============= TELEGRAM =============
TELEGRAM_API_URL=https://api.tu-dominio.com/telegram
TELEGRAM_API_KEY=tu_api_key_secreta
TELEGRAM_CHAT_ID=tu_chat_id_o_canal

# ============= OPCIONAL (Ya tienen valores por defecto) =============
SNAPSHOT_CANDLES=1000
EMA_PERIOD=200
DUAL_SOURCE_WINDOW=2.0
LOG_LEVEL=INFO
```

### 5. Ejecutar el Bot

```bash
python main.py
```

Deberías ver la siguiente salida si todo está correcto:

```
INFO     | 2024-11-19 14:30:00 | main | ╔══════════════════════════════════════════════════════════════╗
INFO     | 2024-11-19 14:30:00 | main | ║  TradingView Pattern Monitor - MVP v0.0.1                     ║
INFO     | 2024-11-19 14:30:00 | main | ║  Shooting Star Detection System                               ║
INFO     | 2024-11-19 14:30:00 | main | ║  Dual-Source Validation: OANDA + FX:EURUSD                    ║
INFO     | 2024-11-19 14:30:00 | main | ╚══════════════════════════════════════════════════════════════╝
INFO     | 2024-11-19 14:30:01 | main | ✅ Configuration validated
INFO     | 2024-11-19 14:30:01 | main | 📱 Telegram Service initialized
INFO     | 2024-11-19 14:30:01 | main | 📊 Analysis Service initialized
INFO     | 2024-11-19 14:30:02 | main | 📡 Connecting to wss://data.tradingview.com/socket.io/websocket...
INFO     | 2024-11-19 14:30:03 | main | ✅ WebSocket connected successfully
INFO     | 2024-11-19 14:30:03 | main | 🔐 Authenticating with TradingView...
```

### 6. Detener el Bot

Presiona **Ctrl+C** para detener el bot de forma limpia (graceful shutdown).

---

## 🔧 Estructura del Proyecto

```
trading-bot/
├── .env                          # Variables de entorno (NO COMMITEAR)
├── .env.example                  # Plantilla de configuración
├── config.py                     # Configuración centralizada
├── main.py                       # Punto de entrada
├── requirements.txt              # Dependencias Python
├── README.md                     # Este archivo
├── Docs/
│   ├── deep_search.md           # Investigación técnica
│   └── resumen.md               # Especificación del proyecto
└── src/
    ├── __init__.py
    ├── services/
    │   ├── __init__.py
    │   ├── connection_service.py    # WebSocket Multiplexer
    │   ├── analysis_service.py      # Pattern Detection Engine
    │   └── telegram_service.py      # Notification System
    └── utils/
        ├── __init__.py
        └── logger.py                # Centralized Logging
```

---

## 🧪 Testing y Debugging

### Ver logs detallados

Cambia el nivel de log en `.env`:

```env
LOG_LEVEL=DEBUG
```

Esto mostrará información detallada de cada vela recibida y cálculos internos.

### Guardar logs en archivo

Configura la ruta del archivo de logs:

```env
LOG_FILE=logs/trading_bot.log
```

Los logs se guardarán tanto en consola como en el archivo especificado.

---

## 📊 Funcionamiento del Sistema

### Lógica de Detección

1. **Conexión:** Se establece una única conexión WebSocket multiplexada a TradingView
2. **Suscripción:** Se suscriben dos canales: `OANDA:EURUSD` y `FX:EURUSD`
3. **Buffer:** Se descargan 1000 velas históricas para calcular EMA 200
4. **Análisis en Tiempo Real:**
   - Cada vela cerrada se analiza para detectar el patrón "Shooting Star"
   - Solo se emiten señales si `Close < EMA 200` (tendencia bajista)
5. **Dual-Source Validation:**
   - Si **UNA** fuente detecta el patrón: ⚠️ **Alerta Estándar**
   - Si **AMBAS** fuentes detectan el patrón en <2s: 🔥 **Alerta Fuerte**

### Ejemplo de Alerta Fuerte

```
🔥 ALERTA CONFIRMADA | EURUSD

🎯 CONFIRMACIÓN DUAL-SOURCE
📊 Fuentes: OANDA + FX
📈 Patrón: SHOOTING_STAR
🕒 Timestamp: 2024-11-19 14:35:00

OANDA:
  • Close: 1.05432
  • EMA 200: 1.05680
  • Confianza: 87%

FX:
  • Close: 1.05428
  • EMA 200: 1.05675
  • Confianza: 91%

📉 Tendencia: BEARISH
✨ Confianza Promedio: 89%

🚀 Alta probabilidad. Revisar retroceso del 50% en primeros 30s de la siguiente vela.
```

---

## 🚨 Troubleshooting

### Error: "CRITICAL AUTH FAILURE"

**Causa:** El `TV_SESSION_ID` ha expirado o es inválido.

**Solución:**
1. Obtén un nuevo `sessionid` siguiendo la sección 3 de instalación
2. Actualiza el valor en `.env`
3. Reinicia el bot

### Error: "Telegram API request failed"

**Causa:** La URL o API Key de Telegram son incorrectas.

**Solución:**
1. Verifica que `TELEGRAM_API_URL` y `TELEGRAM_API_KEY` estén bien configurados
2. Prueba la API manualmente con `curl` o Postman

### El bot no detecta patrones

**Causa:** Puede ser que:
- El mercado no esté generando el patrón
- No hay suficientes velas en el buffer
- La tendencia no es bajista

**Solución:**
1. Verifica que aparezca el mensaje: `✅ OANDA_EURUSD initialized with 1000 candles`
2. Cambia a `LOG_LEVEL=DEBUG` para ver cada vela recibida
3. Espera a condiciones de mercado bajistas (Close < EMA 200)

## ⚠️ Descargo de Responsabilidad
Este software es una herramienta de análisis técnico y **NO** ejecuta operaciones financieras. El uso de APIs no oficiales de TradingView puede conllevar riesgos de bloqueo temporal de IP. Utilice este software bajo su propia responsabilidad.