# TradingView Pattern Monitor (MVP v0.0.1)

Sistema automatizado de soporte a la decisión que consume datos de mercado en tiempo real a través de ingeniería inversa del protocolo WebSocket de TradingView. Analiza la formación de velas japonesas (1m) y detecta patrones de reversión (Estrella Fugaz) filtrados por tendencia (EMA 200).

Este proyecto implementa una arquitectura de **confirmación cruzada (Dual-Source)** entre dos fuentes de datos (OANDA y FXCM) para reducir el ruido y garantizar la integridad de la señal antes de enviar notificaciones a Telegram[cite: 6, 11, 29].

## 🚀 Características Principales

* **Ingestión de Datos:** Cliente WebSocket asíncrono con **multiplexación** para monitorear múltiples instrumentos sin bloqueo de IP[cite: 219].
* **Análisis Cuantitativo:** Cálculo vectorizado con `pandas` para la EMA 200 y detección matemática de patrones sobre un buffer dinámico de 1000 velas[cite: 64, 127].
* **Dual-Source Validation:** Lógica de comparación entre una fuente primaria (OANDA) y secundaria (FX) para emitir alertas de "Alta Probabilidad"[cite: 29].
* **Bypass de Restricciones:** Gestión de `SessionID` y headers `Origin` para acceder a datos en tiempo real y evitar el retraso de datos `CBOE BZX`[cite: 77, 113].
* **Notificaciones:** Integración vía API REST con Telegram para alertas "Estándar" y "Fuertes"[cite: 71].

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

1.  **Clonar el repositorio:**
    ```bash
    git clone [https://github.com/tu-usuario/tv-pattern-monitor.git](https://github.com/tu-usuario/tv-pattern-monitor.git)
    cd tv-pattern-monitor
    ```

2.  **Crear entorno virtual e instalar dependencias:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # En Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Configurar Variables de Entorno:**
    Crear un archivo `.env` en la raíz basado en el siguiente esquema:

    ```env
    # TradingView Auth (Extraído de cookies del navegador F12)
    TV_SESSION_ID=tu_session_id_aqui

    # Configuración de Red
    WS_ORIGIN=[https://data.tradingview.com](https://data.tradingview.com)
    USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64)..."

    # Telegram API
    TELEGRAM_API_URL=[https://api.tu-dominio.com/telegram](https://api.tu-dominio.com/telegram)
    TELEGRAM_API_KEY=tu_api_key_secreta
    ```

4.  **Ejecución:**
    ```bash
    python main.py
    ```

## ⚠️ Descargo de Responsabilidad
Este software es una herramienta de análisis técnico y **NO** ejecuta operaciones financieras. El uso de APIs no oficiales de TradingView puede conllevar riesgos de bloqueo temporal de IP. Utilice este software bajo su propia responsabilidad.