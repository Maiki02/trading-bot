# 🚀 Quick Start Guide - Trading Bot MVP v0.0.1

## Inicio Rápido (5 minutos)

### 1️⃣ Instalar dependencias

```powershell
# Desde el directorio del proyecto
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2️⃣ Obtener SessionID de TradingView

1. Abre https://www.tradingview.com en tu navegador
2. Inicia sesión con tu cuenta
3. Presiona **F12** → **Application** → **Cookies** → `tradingview.com`
4. Copia el valor de la cookie **`sessionid`**

### 3️⃣ Configurar variables de entorno

```powershell
# Crear archivo .env desde la plantilla
copy .env.example .env

# Editar .env con tu editor favorito
notepad .env
```

**Configuración MÍNIMA requerida:**

```env
TV_SESSION_ID=tu_sessionid_aqui
TELEGRAM_API_URL=https://api.tu-dominio.com/admin/bots/12345/broadcast
TELEGRAM_API_KEY=tu_api_key
TELEGRAM_SUBSCRIPTION=trading_signals
```

### 4️⃣ Ejecutar el bot

```powershell
python main.py
```

### 5️⃣ Verificar que funciona

Deberías ver:

```
✅ Configuration validated
📱 Telegram Service initialized
📊 Analysis Service initialized  
📡 Connecting to wss://data.tradingview.com...
✅ WebSocket connected successfully
🔐 Authenticating with TradingView...
✅ Authentication successful
📊 Subscribing to OANDA:EURUSD (primary)...
```

---

## ❓ Troubleshooting Rápido

### ❌ "CRITICAL AUTH FAILURE"

➡️ **Tu SessionID expiró.** Obtén uno nuevo (Paso 2) y actualiza `.env`

### ❌ "Telegram API request failed"

➡️ Verifica que `TELEGRAM_API_URL` y `TELEGRAM_API_KEY` sean correctos

### ❌ No detecta patrones

➡️ Es normal. El patrón Shooting Star solo aparece en tendencia bajista. Espera a que el mercado esté en condiciones apropiadas.

### ⚠️ "Import error: websockets"

➡️ No instalaste las dependencias. Ejecuta: `pip install -r requirements.txt`

---

## 🎯 ¿Qué hace el bot?

1. ✅ Se conecta a TradingView vía WebSocket
2. ✅ Monitorea EUR/USD (1 minuto) desde **2 fuentes** (OANDA + FX)
3. ✅ Calcula la **EMA 200** en tiempo real
4. ✅ Detecta patrones **Shooting Star** cuando `Close < EMA 200`
5. ✅ Envía alertas a Telegram:
   - **⚠️ Estándar:** Una sola fuente detectó el patrón
   - **🔥 Fuerte:** AMBAS fuentes detectaron el mismo patrón

---

## 📚 Documentación Completa

- **README.md** → Instalación detallada y configuración
- **DEVELOPMENT.md** → Arquitectura, extensiones y deployment
- **Docs/resumen.md** → Especificación del proyecto
- **Docs/deep_search.md** → Investigación técnica

---

## 🛑 Detener el bot

Presiona **Ctrl + C** (se detendrá de forma limpia)

---

## 📊 Estructura de Archivos Generados

```
trading-bot/
├── .env                         ← TU CONFIGURACIÓN (crear)
├── .env.example                 ← Plantilla
├── config.py                    ← Gestor de configuración
├── main.py                      ← EJECUTAR ESTO
├── requirements.txt             ← Dependencias
├── README.md                    ← Documentación principal
├── DEVELOPMENT.md               ← Guía para desarrolladores
├── QUICKSTART.md                ← Este archivo
├── Docs/
└── src/
    ├── services/
    │   ├── connection_service.py    ← WebSocket
    │   ├── analysis_service.py      ← Detección de patrones
    │   └── telegram_service.py      ← Notificaciones
    └── utils/
        └── logger.py                ← Sistema de logs
```

---

## 🔥 Siguiente Paso

Una vez que el bot esté corriendo, monitorea los logs y espera las alertas en Telegram.

Para desarrollo avanzado y deployment en servidor, consulta **DEVELOPMENT.md**.

---

**¿Problemas?** Abre un issue en GitHub: https://github.com/Maiki02/trading-bot/issues
