# Sistema de Proveedor de Datos Dinámico

## Descripción

Este sistema permite alternar entre **TradingView** e **IQ Option** (o futuros proveedores) como fuente de datos de mercado mediante configuración simple en el archivo `.env`, sin necesidad de modificar código.

## Arquitectura

### Componentes Principales

1. **Protocol Base** (`src/services/base_market_data_service.py`)
   - Define la interfaz común que todos los proveedores deben implementar
   - Métodos: `connect()`, `disconnect()`, `get_latest_candle()`, `is_connected()`

2. **IQ Option Service** (`src/services/iq_option_service.py`)
   - Implementación para IQ Option API
   - Manejo de conexión/reconexión automática
   - Mapeo de datos de IQ Option al formato estándar
   - Thread-safe para acceso concurrente
   - Wrapper asíncrono para compatibilidad con el sistema

3. **Factory Function** (`src/services/connection_service.py`)
   - `get_market_data_service()`: Instancia el proveedor correcto según configuración
   - Interfaz unificada para ambos proveedores

4. **Main Orchestrator** (`main.py`)
   - Usa la factory para obtener el servicio de datos
   - No necesita conocer cuál proveedor está activo

## Instalación

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

Esto instalará automáticamente:
- `websockets` (para TradingView)
- `iqoptionapi` (para IQ Option)
- Otras dependencias necesarias

### 2. Configuración

Copia el archivo de ejemplo:

```bash
cp .env.example .env
```

Edita `.env` y configura las variables según el proveedor que quieras usar.

## Configuración por Proveedor

### Opción 1: TradingView

```env
# Seleccionar proveedor
DATA_PROVIDER=TRADINGVIEW

# Configuración de TradingView
TV_SESSION_ID=your_session_id_here
TV_WS_URL=wss://data.tradingview.com/socket.io/websocket
TV_WS_ORIGIN=https://data.tradingview.com
SNAPSHOT_CANDLES=1000
```

**Nota:** El `TV_SESSION_ID` no es crítico para feeds públicos. Los headers Anti-WAF (User-Agent, Origin) son suficientes para bypass.

### Opción 2: IQ Option

```env
# Seleccionar proveedor
DATA_PROVIDER=IQOPTION

# Configuración de IQ Option
IQ_OPTION_USER=your_email@example.com
IQ_OPTION_PASS=your_password
IQ_ASSET=EURUSD-OTC
```

**Activos soportados:**
- `EURUSD-OTC` (Over The Counter - 24/7)
- `EURUSD` (Forex regular)
- `GBPUSD`, `USDJPY`, etc.

**Importante:** El bot usará la cuenta **PRACTICE** (demo) por defecto. Para operar en real, modifica `iq_option_service.py` línea 66:

```python
self.api.change_balance("REAL")  # Cambiar de "PRACTICE" a "REAL"
```

## Estructura de Datos Estandarizada

Ambos proveedores retornan velas en el mismo formato:

```python
{
    'time': datetime,      # Timestamp (datetime object UTC)
    'open': float,         # Precio de apertura
    'high': float,         # Precio máximo
    'low': float,          # Precio mínimo
    'close': float,        # Precio de cierre
    'volume': float        # Volumen (0 si no disponible)
}
```

### Mapeo IQ Option → Formato Estándar

| IQ Option | Estándar |
|-----------|----------|
| `max`     | `high`   |
| `min`     | `low`    |
| `at`      | `time`   |
| `open`    | `open`   |
| `close`   | `close`  |
| N/A       | `volume` (0) |

## Uso

### Iniciar el bot

```bash
python main.py
```

El bot:
1. Leerá `DATA_PROVIDER` de `.env`
2. Instanciará el servicio correcto automáticamente
3. Se conectará al proveedor seleccionado
4. Comenzará a recibir y procesar velas en tiempo real

### Cambiar de proveedor

1. Edita `.env` y cambia `DATA_PROVIDER`
2. Configura las credenciales del nuevo proveedor
3. Reinicia el bot

**¡No se requieren cambios de código!**

## Características de Seguridad

### IQ Option Service

- **Thread-Safety:** Uso de locks para acceso concurrente a la última vela
- **Reconexión Automática:** Monitoreo continuo con backoff exponencial
- **Validación de Datos:** Manejo de velas incompletas o inválidas
- **Modo Demo por Defecto:** Protección contra operaciones reales accidentales

### TradingView Service

- **Anti-WAF:** Rotación de User-Agents
- **Heartbeat:** Keepalive automático
- **Graceful Shutdown:** Cierre limpio de conexiones
- **Multiplexación:** Un solo WebSocket para múltiples suscripciones

## API de Desarrollo

### Agregar un Nuevo Proveedor

1. **Crear el servicio:**

```python
# src/services/mi_proveedor_service.py

class MiProveedorService:
    def connect(self) -> bool:
        # Conectar al proveedor
        pass
    
    def disconnect(self) -> None:
        # Desconectar
        pass
    
    def get_latest_candle(self) -> Optional[Dict[str, Any]]:
        # Retornar vela en formato estándar
        return {
            'time': datetime.now(timezone.utc),
            'open': 1.0,
            'high': 1.1,
            'low': 0.9,
            'close': 1.05,
            'volume': 1000
        }
    
    def is_connected(self) -> bool:
        return True
```

2. **Agregar al factory:**

```python
# src/services/connection_service.py

def get_market_data_service(analysis_service, on_auth_failure_callback=None):
    if Config.DATA_PROVIDER == "MI_PROVEEDOR":
        from src.services.mi_proveedor_service import MiProveedorService
        return MiProveedorService()
    # ... otros proveedores
```

3. **Actualizar validación:**

```python
# config.py

if cls.DATA_PROVIDER not in ["TRADINGVIEW", "IQOPTION", "MI_PROVEEDOR"]:
    raise ValueError(...)
```

## Troubleshooting

### Error: "No se ha podido resolver la importación iqoptionapi"

**Solución:** Instala la librería manualmente:

```bash
pip install git+https://github.com/iqoptionapi/iqoptionapi.git
```

### Error: "Failed to connect to IQ Option"

**Causas posibles:**
1. Credenciales incorrectas en `.env`
2. Cuenta bloqueada o suspendida
3. Problemas de red/firewall

**Solución:**
1. Verifica `IQ_OPTION_USER` e `IQ_OPTION_PASS` en `.env`
2. Prueba iniciar sesión en el sitio web de IQ Option
3. Revisa los logs para más detalles

### Velas no se procesan (IQ Option)

**Causa:** El activo puede no estar disponible o el mercado está cerrado

**Solución:**
1. Prueba con activos OTC (disponibles 24/7): `EURUSD-OTC`
2. Verifica que el mercado esté abierto para activos Forex regulares
3. Revisa logs para ver si hay errores en el stream de velas

## Ventajas del Sistema

✅ **Flexibilidad:** Cambia de proveedor sin modificar código  
✅ **Escalabilidad:** Fácil agregar nuevos proveedores  
✅ **Mantenibilidad:** Interfaz estandarizada  
✅ **Testabilidad:** Mockear proveedores es simple  
✅ **Robustez:** Manejo de reconexión automático  
✅ **Transparencia:** El resto del sistema no sabe qué proveedor se usa  

## Comandos Útiles

```bash
# Instalar dependencias
pip install -r requirements.txt

# Instalar IQ Option API manualmente
pip install git+https://github.com/iqoptionapi/iqoptionapi.git

# Ejecutar el bot
python main.py

# Ver logs en tiempo real (si LOG_FILE está configurado)
tail -f trading_bot.log

# Validar configuración sin ejecutar
python -c "from config import Config; Config.validate_all(); print('✅ OK')"
```

## Contribuir

Para agregar soporte a nuevos proveedores:

1. Fork el repositorio
2. Crea una rama: `git checkout -b feature/nuevo-proveedor`
3. Implementa el servicio siguiendo el protocolo base
4. Agrega tests
5. Actualiza documentación
6. Envía un Pull Request

## Licencia

[Incluir licencia del proyecto]

## Soporte

Para preguntas o issues:
- GitHub Issues: [URL del repo]
- Email: [tu email]
- Discord/Telegram: [comunidad]
