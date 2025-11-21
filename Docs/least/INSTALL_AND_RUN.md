# Guía de Instalación y Ejecución - Trading Bot

## 📋 Prerequisitos

- ✅ Python 3.10 o superior
- ✅ Windows 10/11
- ✅ PowerShell o CMD

## 🚀 Instalación Rápida

### 1. Verificar Python
```powershell
python --version
```
Debe mostrar Python 3.10 o superior.

### 2. Crear Entorno Virtual (si no existe)
```powershell
python -m venv .venv
```

### 3. Activar Entorno Virtual
```powershell
# En PowerShell
.venv\Scripts\Activate.ps1

# En CMD
.venv\Scripts\activate.bat
```

### 4. Instalar Dependencias
```powershell
pip install -r requirements.txt
```

Si da error, instala manualmente:
```powershell
pip install websockets==12.0 aiohttp==3.9.1 pandas==2.1.4 numpy==1.26.2 mplfinance==0.12.10b0 python-dotenv==1.0.0
```

### 5. Configurar Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto:
```powershell
cp .env.example .env
```

Edita `.env` y configura:
```env
TELEGRAM_API_URL=https://tu-api.com/broadcast
TELEGRAM_API_KEY=tu_api_key_secreto
TELEGRAM_SUBSCRIPTION=trading_signals
```

## ▶️ Ejecutar el Bot

### Opción 1: Desde PowerShell/CMD
```powershell
# Asegúrate de que el entorno virtual está activado
python main.py
```

### Opción 2: Desde VS Code
1. Abre `main.py`
2. Presiona `F5` o click en "Run > Start Debugging"
3. Selecciona "Python File"

### Opción 3: Usando el intérprete del venv directamente
```powershell
.venv\Scripts\python.exe main.py
```

## 🛑 Detener el Bot

- **Ctrl + C** en la terminal
- El bot se detendrá de forma limpia (graceful shutdown)

## 📊 Verificar que Funciona

Al ejecutar, deberías ver:

```
🚀 ==========================================
🤖 TradingView Pattern Monitor v0.0.2
🚀 ==========================================
📊 Analysis Service initialized (EMA Period: 200)
✅ All services initialized successfully
🚀 Trading Bot started. Monitoring EUR/USD for Shooting Star patterns...
📊 Primary Source: OANDA | Secondary Source: FX
```

## ⚙️ Configuración Opcional

### Cambiar el número de velas en el gráfico
En `.env`:
```env
CHART_LOOKBACK=50  # Default: 30
```

### Cambiar el período de EMA
En `.env`:
```env
EMA_PERIOD=100  # Default: 200
```

### Cambiar ventana de confirmación dual
En `.env`:
```env
DUAL_SOURCE_WINDOW=5.0  # Default: 2.0 segundos
```

### Habilitar logging a archivo
En `.env`:
```env
LOG_FILE=logs/trading_bot.log
LOG_LEVEL=DEBUG  # INFO, DEBUG, WARNING, ERROR
```

## 🔍 Verificar Instalación

### Verificar paquetes instalados:
```powershell
pip list
```

Deberías ver:
- `websockets` 12.0
- `aiohttp` 3.9.1
- `pandas` 2.1.4
- `numpy` 1.26.2
- `mplfinance` 0.12.10b0
- `python-dotenv` 1.0.0

### Verificar entorno Python:
```powershell
python -c "import sys; print(sys.executable)"
```

Debe apuntar a `.venv\Scripts\python.exe`

## ❌ Solución de Problemas

### Error: "No module named 'websockets'"
```powershell
pip install websockets==12.0
```

### Error: "No module named 'mplfinance'"
```powershell
pip install mplfinance==0.12.10b0
```

### Error: "Cannot find .env file"
- Crea el archivo `.env` en la raíz del proyecto
- Copia el contenido de `.env.example`

### Error: "Telegram configuration incomplete"
- Asegúrate de configurar `TELEGRAM_API_URL`, `TELEGRAM_API_KEY` y `TELEGRAM_SUBSCRIPTION` en `.env`

### Error en PowerShell: "cannot be loaded because running scripts is disabled"
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 📁 Estructura del Proyecto

```
trading-bot/
├── .venv/                  # Entorno virtual (creado automáticamente)
├── .env                    # Tu configuración (NO subir a Git)
├── .env.example            # Plantilla de configuración
├── main.py                 # Punto de entrada
├── config.py               # Configuración global
├── requirements.txt        # Dependencias
├── src/
│   ├── services/
│   │   ├── analysis_service.py
│   │   ├── connection_service.py
│   │   └── telegram_service.py
│   └── utils/
│       ├── charting.py     # Generación de gráficos (NUEVO)
│       └── logger.py
└── logs/                   # Logs (si está habilitado)
```

## 🎯 Próximos Pasos

1. ✅ Instalar dependencias
2. ✅ Configurar `.env`
3. ✅ Ejecutar `python main.py`
4. 📊 Monitorear los logs
5. 📱 Verificar alertas en Telegram

## 📚 Documentación Adicional

- `CHART_SNAPSHOT_IMPLEMENTATION.md` - Detalles de la implementación de gráficos
- `README.md` - Documentación general del proyecto
- `DEVELOPMENT.md` - Guía para desarrolladores

---

**¿Necesitas ayuda?** Revisa los logs en la terminal o habilita `LOG_LEVEL=DEBUG` en `.env`.
