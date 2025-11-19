# Resumen

## 1. Objetivo del Proyecto
Integrar un monitor automatizado 24/7 que capture datos de mercado en tiempo real de TradingView mediante ingeniería inversa de WebSocket. El sistema identificará patrones de velas japonesas en temporalidad de 1 minuto y, al detectar una configuración válida alineada con la tendencia, enviará una alerta inmediata vía Telegram.

### 1.1. Objetivo Versión 0.0.1 (MVP)
Para la primera iteración funcional, el alcance se limita a probar la viabilidad técnica de monitorear dos fuentes simultáneas:
- Par: Únicamente EUR/USD.
- Fuentes de Datos: Se conectará a OANDA (Principal) y FX:EURUSD (Secundaria/Respaldo) simultáneamente para validar la calidad de los datos.
- Patrón: Únicamente detección de Estrella Fugaz (Shooting Star).
- Validación: Confirmar estabilidad de doble conexión WebSocket, convergencia de EMA 200 y lógica de notificación condicional.

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
Notificación ESTÁNDAR: Se envía cuando UNA de las fuentes (OANDA o FX) detecta el patrón válido.
Mensaje: "Posible oportunidad. Verificar gráfico manualmente."
Notificación FUERTE (Strong): Se envía cuando AMBAS fuentes (OANDA y FX) detectan el patrón válido en el mismo cierre de vela.
Mensaje: "🔥 ALERTA CONFIRMADA. Coincidencia en OANDA y FXCM."

## 3. Matriz de Patrones y Tendencia

### 3.1. Definición de Tendencia (Filtro Macro)
Se utiliza la EMA 200 como el juez principal de la tendencia para filtrar operaciones contra-corriente.
Tendencia ALCISTA: Precio de Cierre > EMA 200.
Solo se buscan compras (Martillos).
Tendencia BAJISTA: Precio de Cierre < EMA 200.
Solo se buscan ventas (Estrellas Fugaces).

### 3.2. Reglas de Disparo
A. Escenario: Tendencia ALCISTA (Precio > EMA 200)
Patrón: Martillo (Hammer)
Acción: 🚨 ALERTA DE COMPRA.
Contexto: Señal de rebote a favor de la tendencia.
Patrón: Hombre Colgado / Estrella Fugaz
Acción: Ignorar (o alerta leve de "Posible Cierre").
B. Escenario: Tendencia BAJISTA (Precio < EMA 200)
Patrón: Estrella Fugaz (Shooting Star)
Acción: 🚨 ALERTA DE VENTA.
Contexto: Señal de rechazo a favor de la caída.
Decisión Humana: Esperar retroceso del 50% en los primeros 30s de la siguiente vela para entrar.
Patrón: Martillo Invertido / Martillo
Acción: Ignorar.

## 4. Arquitectura Tecnológica Modular
### 4.1. Estructura del Programa (main.py)
Módulo 1: Connection Service (Multiplexado)
Gestiona conexiones WebSocket paralelas a data.tradingview.com.
Headers Avanzados (Anti-WAF): Rotación de User-Agent y spoofing para imitar navegadores reales (Chrome/Firefox).
Keep-Alive: Implementación de "Heartbeat" para mantener los túneles abiertos.
Módulo 2: Analysis Service (Core Logic)
Cálculo Vectorizado: Usa pandas para gestionar los arrays de precios.
Integridad Matemática (Buffer):
Se solicita un Snapshot de 1000 velas al conectar.
Esto es crítico para que la EMA 200 converja correctamente. Si buffer < 600, el sistema no emite señales.
Validación de Patrones: Detecta proporciones estrictas (Cuerpo vs Mecha) en cada fuente por separado.
Módulo 3: Notification Service (Output)
Conexión bidireccional con Telegram.
Discrimina si la alerta proviene de una sola fuente o si es una "Alerta Doble".
### 4.2. Infraestructura
Proveedor: Oracle Cloud Infrastructure (OCI) - Tier "Always Free".
Entorno: VM Linux, Python 3.10+.

## 5. Flujo de Lógica y Procesos Críticos
### 5.1. Autenticación y Calidad de Datos
Regla de Oro: Verificar flag de datos. Si es "Delayed" o "CBOE BZX" (datos genéricos retrasados), el sistema se detiene.
Manejo de Sesión: Si TradingView invalida la sessionid, se envía alerta crítica: ⚠️ CRITICAL AUTH FAIL.
### 5.2. Inicialización y Reconexión
Conexión Dual: Se conecta a OANDA y FX.
Snapshot: Descarga de 1000 velas históricas para ambas fuentes.
Warm-up: Cálculo de EMA 200 inicial.
Stream: Inicio del bucle de detección en tiempo real.
### 5.3. Dudas y Definiciones Finales
Simbología: Se resuelve usar OANDA:EURUSD como primaria y FX:EURUSD como secundaria.
Gestión de Buffer: Se establece un mínimo de 3 a 5 veces el periodo de la EMA mayor. Para EMA 200, requerimos 600 a 1000 velas en memoria.
