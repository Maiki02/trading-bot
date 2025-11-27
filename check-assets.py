import logging
import time
import json
import threading
from iqoptionapi.stable_api import IQ_Option
import iqoptionapi.ws.client
from config import Config

# Configuración de logs silenciosa
logging.getLogger('iqoptionapi').setLevel(logging.CRITICAL)
logging.basicConfig(level=logging.INFO, format='%(message)s')

# ==========================================
# 🕵️ INTERCEPTOR SILENCIOSO (MONKEY PATCH)
# ==========================================
received_assets = set() 

_original_on_message = iqoptionapi.ws.client.WebsocketClient.on_message

def _spy_on_message(self, message):
    try:
        msg = json.loads(message)
        name = msg.get('name')
        
        # Detectamos las señales de vida del precio digital
        if name in ['client-price-generated', 'instrument-quotes-generated', 'price-splitter']:
            payload = msg.get('msg') or msg.get('body')
            
            asset_id = None
            if 'asset_id' in payload:
                asset_id = payload['asset_id']
            elif 'active_id' in payload:
                asset_id = payload['active_id']
            elif 'active' in payload:
                asset_id = payload['active']
                
            if asset_id:
                # Solo guardamos el ID, YA NO IMPRIMIMOS "🔥" PARA NO ENSUCIAR
                received_assets.add(int(asset_id))
                    
    except:
        pass
    _original_on_message(self, message)

iqoptionapi.ws.client.WebsocketClient.on_message = _spy_on_message
# ==========================================

def scan_active_assets():
    print("\n🔌 Conectando a IQ Option...")
    api = IQ_Option(Config.IQOPTION.email, Config.IQOPTION.password)
    if not api.connect()[0]:
        print("❌ Error conectando.")
        return

    api.change_balance("PRACTICE")
    print("⏳ Descargando lista de activos...")
    api.update_ACTIVES_OPCODE()
    instruments = api.get_all_ACTIVES_OPCODE()
    
    # === LISTA MAESTRA DE PARES ===
    base_pairs = [
        # Majors
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF",
        # Minors & Crosses
        "EURGBP", "EURJPY", "GBPJPY", "AUDCAD", "AUDJPY", "CADJPY", "CHFJPY",
        "EURAUD", "EURNZD", "GBPAUD", "GBPCAD", "NZDJPY", "AUDCHF", "CADCHF"
    ]
    
    # Generamos automáticamente pares Normales y OTC
    targets = []
    for pair in base_pairs:
        targets.append(pair)          # Ej: EURUSD
        targets.append(f"{pair}-OTC") # Ej: EURUSD-OTC

    print("\n" + "="*70)
    print(f"🔍 ESCANEO MASIVO DE PRECIOS SPOT ({len(targets)} Activos)")
    print("="*70)
    print(f"{'ACTIVO':<12} | {'ID':<6} | {'ESTADO'}")
    print("-" * 70)
    
    working_assets = []

    for symbol in targets:
        active_id = instruments.get(symbol)
        
        # Si no existe el ID, pasamos silenciosamente (limpieza visual)
        if not active_id: 
            continue
            
        print(f"{symbol:<12} | {active_id:<6} | ", end="", flush=True)

        # Limpiar rastro previo
        if active_id in received_assets:
            received_assets.remove(active_id)

        # Suscripción Doble (Digital + Quotes)
        try:
            api.api.subscribe_digital_price_splitter(active_id)
            api.api.subscribe_instrument_quites_generated(symbol, expiration_period=1)
        except: pass
        
        # Esperar señal (2.5 segundos es suficiente si la tubería está abierta)
        start = time.time()
        found = False
        while time.time() - start < 2.5:
            if active_id in received_assets:
                found = True
                break
            time.sleep(0.1)
            print(".", end="", flush=True)
            
        # Resultado
        if found:
            print(f" ✅ FUNCIONA")
            working_assets.append(symbol)
        else:
            print(f" ⛔ SILENCIO")

        # Limpieza rápida
        try:
            api.api.unsubscribe_digital_price_splitter(active_id)
        except: pass

    print("\n" + "="*70)
    print("🚀 LISTA PARA COPIAR A CONFIG.PY:")
    print("="*70)
    # Imprimimos la lista formateada lista para Python
    print(f"TARGET_ASSETS = {json.dumps(working_assets, indent=4).replace('null', 'None')}")
    print("="*70)
    
    api.api.close()

if __name__ == "__main__":
    scan_active_assets()



    