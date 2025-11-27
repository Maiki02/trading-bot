import asyncio
import websockets
import json
import time
from iqoptionapi.stable_api import IQ_Option
import iqoptionapi.global_value as global_value
from config import Config

# --- CONFIGURACIÓN ---
# 1 = EURUSD (Real)
# 76 = EURUSD-OTC (Fin de semana / OTC)
# 1861 = BTCUSD (Crypto)
ACTIVE_ID_TO_TEST = 76  # <--- CAMBIA ESTO AL QUE QUIERAS PROBAR

CUSTOM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Origin": "https://iqoption.com",
    "Cache-Control": "no-cache"
}

async def run_sidecar():
    print("🔑 1. Obteniendo SSID...")
    api = IQ_Option(Config.IQOPTION.email, Config.IQOPTION.password)
    check, reason = api.connect()
    
    if not check:
        print(f"❌ Error Login: {reason}")
        return

    ssid = global_value.SSID
    print(f"✅ SSID: {ssid[:10]}... (Desconectando legacy)")
    api.api.close()
    
    print(f"🚀 2. Iniciando Sidecar para ID {ACTIVE_ID_TO_TEST}...")
    url = "wss://ws.iqoption.com/echo/websocket"
    
    async with websockets.connect(url, extra_headers=CUSTOM_HEADERS) as ws:
        print("🌍 Conectado. Enviando secuencia de inicio...")
        
        # -----------------------------------------------------------
        # PASO A: AUTENTICACIÓN (Protocolo 3)
        # -----------------------------------------------------------
        await ws.send(json.dumps({
            "name": "authenticate",
            "request_id": "auth_1",
            "local_time": int(time.time()),
            "msg": {
                "ssid": ssid,
                "protocol": 3,
                "session_id": "",
                "client_session_id": ""
            }
        }))

        # -----------------------------------------------------------
        # PASO B: SOLICITAR HISTÓRICO (El mensaje que encontraste)
        # Esto "despierta" al servidor para decirle que estamos viendo el gráfico
        # -----------------------------------------------------------
        t_now = int(time.time())
        await ws.send(json.dumps({
            "name": "sendMessage",
            "request_id": "history_1",
            "local_time": t_now,
            "msg": {
                "name": "get-candles",
                "version": "2.0",
                "body": {
                    "active_id": ACTIVE_ID_TO_TEST,
                    "size": 60, # 1 minuto
                    "to": t_now,
                    "count": 20, # Pide las ultimas 20 velas
                    "split_normalization": True,
                    "only_closed": True
                }
            }
        }))
        print("   -> Solicitado historial (Wake up call)...")

        # -----------------------------------------------------------
        # PASO C: SUSCRIPCIÓN A SPOT (Instrument Quotes)
        # -----------------------------------------------------------
        await ws.send(json.dumps({
            "name": "subscribeMessage",
            "request_id": "sub_spot",
            "msg": {
                "name": "instrument-quotes-generated",
                "params": {
                    "routingFilters": {
                        "active_id": ACTIVE_ID_TO_TEST,
                        "kind": "digital", 
                        "expiration_period": 60 
                    }
                },
                "version": "1.0"
            }
        }))
        print("   -> Suscrito a Spot Digital...")

        # -----------------------------------------------------------
        # PASO D: SUSCRIPCIÓN A VELAS (Fallback)
        # -----------------------------------------------------------
        await ws.send(json.dumps({
            "name": "subscribeMessage",
            "request_id": "sub_candles",
            "msg": {
                "name": "candle-generated",
                "params": {
                    "routingFilters": {
                        "active_id": ACTIVE_ID_TO_TEST,
                        "size": 60,
                        "kind": "digital"
                    }
                },
                "version": "1.0"
            }
        }))
        print("   -> Suscrito a Velas (Respaldo)...")

        print("\n👂 ESCUCHANDO... (Si esto sigue en silencio, el activo está cerrado para API)\n")
        
        try:
            while True:
                msg_raw = await ws.recv()
                data = json.loads(msg_raw)
                name = data.get("name")
                
                # 1. PRECIO SPOT REAL
                if name == "instrument-quotes-generated":
                    payload = data["msg"]
                    price = payload.get("value") or payload.get("price")
                    print(f"🔥 SPOT REAL: {price} | ID: {payload.get('active_id')}")
                
                # 2. VELA GENERADA (FOREX/BACKUP)
                elif name == "candle-generated":
                    payload = data["msg"]
                    close = payload.get("close")
                    print(f"🕯️ VELA FOREX: {close} | ID: {payload.get('active_id')}")

                # 3. CONFIRMACIÓN DE HISTÓRICO
                elif name == "candles":
                    print(f"📚 Historial recibido: {len(data['msg']['candles'])} velas.")

                # 4. TABLA DE OPCIONES (Para saber si llega algo al menos)
                elif name == "client-price-generated":
                    # print(f"🎲 Tabla de opciones recibida (ID {data['msg']['asset_id']})")
                    pass

                elif name == "timeSync":
                    pass # Latido

        except asyncio.CancelledError:
            print("🛑 Detenido.")

if __name__ == "__main__":
    try:
        asyncio.run(run_sidecar())
    except KeyboardInterrupt:
        print("Salida manual.")