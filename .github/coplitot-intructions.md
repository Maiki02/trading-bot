# AI DEVELOPMENT GUIDELINES - TRADINGVIEW PATTERN MONITOR

## 1. PROJECT IDENTITY & GOAL
**Role:** Senior Python Engineer specialized in Algorithmic Trading and Real-Time Systems.
[cite_start]**Objective:** Build a robust MVP (v0.0.1) to detect "Shooting Star" candlestick patterns on EUR/USD (1m timeframe) using a "Dual Source" validation strategy (OANDA + FX:EURUSD) via TradingView WebSockets[cite: 8, 9, 11].
**Critical Constraint:** The system is strictly for ALERTING via Telegram. [cite_start]NO trade execution[cite: 15].

## 2. ARCHITECTURE & DESIGN PATTERNS
The system must follow a modular, event-driven architecture using `asyncio`.

### Core Modules:
1.  **Connection Service (Input):** Handles WebSocket multiplexing. [cite_start]It MUST NOT open parallel sockets for different instruments; it must subscribe to multiple channels over a single socket to avoid IP bans[cite: 218]. [cite_start]It manages the Heartbeat and SessionID injection[cite: 200, 230].
2.  **Analysis Service (Processing):** Owns the `pandas` DataFrame buffer. Responsible for vector calculations (EMA 200) and pattern recognition. [cite_start]It enforces the "Snapshot" logic (waiting for 1000 historical candles before processing real-time data)[cite: 66, 127].
3.  **Notification Service (Output):** Manages Telegram API requests. [cite_start]Implements the "Dual Source" time-window logic to distinguish between "Standard Alerts" and "Strong Confirmed Alerts"[cite: 29, 32].

## 3. CODING CONVENTIONS
* **Language:** Python 3.10+.
* **Typing:** Strict static typing (Type Hints) for all functions and method signatures.
* **Style:** PEP 8 compliant.
* **Async:** Use `async/await` for all I/O operations (WebSockets, HTTP requests).
* **Configuration:** NO HARDCODED VALUES. All constants (EMA period, timeouts, symbols, API keys) must come from `config.py` or environment variables (`.env`).
* **Error Handling:** Fail gracefully. [cite_start]If `SessionID` expires/fails, log a CRITICAL error[cite: 78]. [cite_start]Use exponential backoff for reconnections[cite: 235].

## 4. FILE STRUCTURE
```text
/
├── .env                # Secrets (SessionID, API Keys)
├── main.py             # Entry point & Event Loop Orchestrator
├── config.py           # Configuration loader & Environment management
├── requirements.txt    # Dependencies
└── src/
    ├── __init__.py
    ├── services/
    │   ├── __init__.py
    │   ├── connection_service.py   # WebSocket Wrapper & Multiplexer
    │   ├── analysis_service.py     # Pandas Logic & Pattern Detection
    │   └── telegram_service.py     # Notification Logic & API Client
    └── utils/
        └── logger.py   # Centralized logging formatting

        Excelente decisión. Definir las reglas del juego antes de escribir una sola línea de código evitará que la IA (y tú en el futuro) se desvíen con "código espagueti" o arquitecturas improvisadas.

Aquí tienes los dos archivos clave. El primero es un archivo de contexto (puedes llamarlo AI_GUIDELINES.md o .cursorrules si usas Cursor) para "alinear" al modelo. El segundo es el README.md profesional.

1. Archivo de Instrucciones para la IA (AI_GUIDELINES.md)
Este archivo define la "Constitución" del proyecto. Cópialo tal cual.

Markdown

# AI DEVELOPMENT GUIDELINES - TRADINGVIEW PATTERN MONITOR

## 1. PROJECT IDENTITY & GOAL
**Role:** Senior Python Engineer specialized in Algorithmic Trading and Real-Time Systems.
[cite_start]**Objective:** Build a robust MVP (v0.0.1) to detect "Shooting Star" candlestick patterns on EUR/USD (1m timeframe) using a "Dual Source" validation strategy (OANDA + FX:EURUSD) via TradingView WebSockets[cite: 8, 9, 11].
**Critical Constraint:** The system is strictly for ALERTING via Telegram. [cite_start]NO trade execution[cite: 15].

## 2. ARCHITECTURE & DESIGN PATTERNS
The system must follow a modular, event-driven architecture using `asyncio`.

### Core Modules:
1.  **Connection Service (Input):** Handles WebSocket multiplexing. [cite_start]It MUST NOT open parallel sockets for different instruments; it must subscribe to multiple channels over a single socket to avoid IP bans[cite: 218]. [cite_start]It manages the Heartbeat and SessionID injection[cite: 200, 230].
2.  **Analysis Service (Processing):** Owns the `pandas` DataFrame buffer. Responsible for vector calculations (EMA 200) and pattern recognition. [cite_start]It enforces the "Snapshot" logic (waiting for 1000 historical candles before processing real-time data)[cite: 66, 127].
3.  **Notification Service (Output):** Manages Telegram API requests. [cite_start]Implements the "Dual Source" time-window logic to distinguish between "Standard Alerts" and "Strong Confirmed Alerts"[cite: 29, 32].

## 3. CODING CONVENTIONS
* **Language:** Python 3.10+.
* **Typing:** Strict static typing (Type Hints) for all functions and method signatures.
* **Style:** PEP 8 compliant.
* **Async:** Use `async/await` for all I/O operations (WebSockets, HTTP requests).
* **Configuration:** NO HARDCODED VALUES. All constants (EMA period, timeouts, symbols, API keys) must come from `config.py` or environment variables (`.env`).
* **Error Handling:** Fail gracefully. [cite_start]If `SessionID` expires/fails, log a CRITICAL error[cite: 78]. [cite_start]Use exponential backoff for reconnections[cite: 235].

## 4. FILE STRUCTURE
```text
/
├── .env                # Secrets (SessionID, API Keys)
├── main.py             # Entry point & Event Loop Orchestrator
├── config.py           # Configuration loader & Environment management
├── requirements.txt    # Dependencies
└── src/
    ├── __init__.py
    ├── services/
    │   ├── __init__.py
    │   ├── connection_service.py   # WebSocket Wrapper & Multiplexer
    │   ├── analysis_service.py     # Pandas Logic & Pattern Detection
    │   └── telegram_service.py     # Notification Logic & API Client
    └── utils/
        └── logger.py   # Centralized logging formatting

5. CRITICAL BUSINESS LOGIC (DO NOT VIOLATE)

Anti-WAF: HTTP Headers must always include Origin: https://data.tradingview.com and a rotatable User-Agent.



Data Integrity: Before analyzing stream data, the system MUST successfully download a Snapshot of ~1000 candles to ensure EMA 200 convergence.

Dual Source: The logic must handle OANDA (Primary) and FX (Secondary). An alert is "STRONG" only if both sources trigger within a configurable time window (e.g., 2 seconds).


Trend Filter: ONLY look for "Shooting Stars" if Close Price < EMA 200.

6. DOCUMENTATION
Docstrings are mandatory for every public method, explaining parameters and return types.