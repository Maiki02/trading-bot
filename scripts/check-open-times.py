import logging
from iqoptionapi.stable_api import IQ_Option
from config import Config

# Configuración de logs
logging.basicConfig(level=logging.INFO, format='%(message)s')

def check_market_status():
    print("🔌 Conectando...")
    api = IQ_Option(Config.IQOPTION.email, Config.IQOPTION.password)
    api.connect()
    
    api.change_balance("PRACTICE")
    
    print("⏳ Obteniendo horarios de mercado (get_all_open_time)...")
    all_assets = api.get_all_open_time()
    
    # Pares a investigar
    targets = ["EURUSD", "EURUSD-OTC", "AUDUSD", "GBPUSD"]
    
    print("\n" + "="*50)
    print("🔍 ESTADO DE MERCADOS PARA TU CUENTA")
    print("="*50)
    
    for symbol in targets:
        print(f"\n👉 {symbol}:")
        
        # Revisar BINARIAS (Normales)
        try:
            is_open = all_assets["binary"][symbol]["open"]
            print(f"   - Binary:  {'🟢 ABIERTO' if is_open else '🔴 CERRADO'}")
        except:
            print(f"   - Binary:  ⚪ NO EXISTE")
            
        # Revisar TURBO (Binarias Rápidas)
        try:
            is_open = all_assets["turbo"][symbol]["open"]
            print(f"   - Turbo:   {'🟢 ABIERTO' if is_open else '🔴 CERRADO'}")
        except:
            print(f"   - Turbo:   ⚪ NO EXISTE")
            
        # Revisar DIGITALES
        try:
            is_open = all_assets["digital"][symbol]["open"]
            print(f"   - Digital: {'🟢 ABIERTO' if is_open else '🔴 CERRADO'}")
        except:
            print(f"   - Digital: ⚪ NO EXISTE")

    print("\n" + "="*50)

if __name__ == "__main__":
    check_market_status()