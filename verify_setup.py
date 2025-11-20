"""
Script de Verificación de Configuración
========================================
Verifica que todas las dependencias estén instaladas y la configuración sea válida.
"""

import sys
import importlib

def check_imports():
    """Verifica que todos los módulos estén instalados."""
    required_modules = [
        'websockets',
        'aiohttp',
        'pandas',
        'numpy',
        'mplfinance',
        'dotenv'
    ]
    
    print("🔍 Verificando dependencias...\n")
    all_ok = True
    
    for module in required_modules:
        try:
            mod = importlib.import_module(module.replace('dotenv', 'python_dotenv'))
            version = getattr(mod, '__version__', 'unknown')
            print(f"✅ {module:20s} {version}")
        except ImportError:
            print(f"❌ {module:20s} NO INSTALADO")
            all_ok = False
    
    return all_ok

def check_config():
    """Verifica la configuración."""
    print("\n🔍 Verificando configuración...\n")
    
    try:
        from config import Config
        
        print(f"✅ config.py cargado correctamente")
        print(f"   EMA Period: {Config.EMA_PERIOD}")
        print(f"   Chart Lookback: {Config.CHART_LOOKBACK}")
        print(f"   Dual Source Window: {Config.DUAL_SOURCE_WINDOW}s")
        
        # Verificar Telegram
        if Config.TELEGRAM.api_url and Config.TELEGRAM.api_key:
            print(f"✅ Telegram configurado")
            print(f"   API URL: {Config.TELEGRAM.api_url}")
            print(f"   Subscription: {Config.TELEGRAM.subscription}")
        else:
            print(f"⚠️  Telegram NO configurado - necesitas editar .env")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error al cargar configuración: {e}")
        return False

def check_files():
    """Verifica que los archivos necesarios existan."""
    import os
    
    print("\n🔍 Verificando archivos del proyecto...\n")
    
    required_files = [
        'main.py',
        'config.py',
        'requirements.txt',
        'src/services/analysis_service.py',
        'src/services/telegram_service.py',
        'src/services/connection_service.py',
        'src/utils/charting.py',
        'src/utils/logger.py'
    ]
    
    all_ok = True
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            print(f"❌ {file} - NO ENCONTRADO")
            all_ok = False
    
    # Verificar .env
    if os.path.exists('.env'):
        print(f"✅ .env - Archivo de configuración encontrado")
    else:
        print(f"⚠️  .env - NO ENCONTRADO (copia .env.example a .env)")
        all_ok = False
    
    return all_ok

def main():
    """Función principal."""
    print("=" * 60)
    print("🤖 Trading Bot - Verificación de Instalación")
    print("=" * 60)
    print()
    
    # Verificar Python
    print(f"🐍 Python {sys.version.split()[0]}")
    print(f"📁 Ejecutable: {sys.executable}")
    print()
    
    # Ejecutar verificaciones
    deps_ok = check_imports()
    files_ok = check_files()
    config_ok = check_config()
    
    print("\n" + "=" * 60)
    
    if deps_ok and files_ok and config_ok:
        print("✅ TODO LISTO - Puedes ejecutar el bot con: python main.py")
    else:
        print("⚠️  HAY PROBLEMAS - Revisa los errores arriba")
        
        if not deps_ok:
            print("\n💡 Para instalar dependencias:")
            print("   pip install -r requirements.txt")
        
        if not config_ok:
            print("\n💡 Para configurar .env:")
            print("   1. Copia .env.example a .env")
            print("   2. Edita .env con tus credenciales de Telegram")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
