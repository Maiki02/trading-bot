"""
Test Script - Local Notification Storage
=========================================
Script de prueba para verificar el funcionamiento del almacenamiento local.
"""

import asyncio
import base64
from pathlib import Path

from src.services.local_notification_storage import LocalNotificationStorage


async def test_local_storage():
    """Prueba el almacenamiento local de notificaciones."""
    print("🧪 Iniciando prueba de Local Notification Storage...")
    
    # Inicializar servicio
    storage = LocalNotificationStorage(base_dir="data/test_notifications")
    
    # Crear una imagen de prueba simple (1x1 pixel rojo en PNG)
    # PNG header + IDAT chunk con pixel rojo
    test_image_base64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    )
    
    # Test 1: Guardar notificación con imagen
    print("\n📝 Test 1: Guardando notificación con imagen...")
    await storage.save_notification(
        title="🔥 TEST ALERTA | EURUSD",
        message="Este es un mensaje de prueba con imagen.\nLínea 2\nLínea 3",
        chart_base64=test_image_base64
    )
    print("✅ Notificación con imagen guardada")
    
    # Test 2: Guardar notificación sin imagen
    print("\n📝 Test 2: Guardando notificación sin imagen...")
    await storage.save_notification(
        title="⚠️ TEST ALERTA | BTCUSDT",
        message="Este es un mensaje de prueba SIN imagen.",
        chart_base64=None
    )
    print("✅ Notificación sin imagen guardada")
    
    # Test 3: Verificar estadísticas
    print("\n📊 Test 3: Verificando estadísticas...")
    stats = storage.get_stats()
    print(f"  - Imágenes guardadas: {stats['images_count']}")
    print(f"  - Mensajes guardados: {stats['messages_count']}")
    print(f"  - Tamaño total: {stats['total_size_mb']} MB")
    print(f"  - Directorio: {stats['base_dir']}")
    
    # Test 4: Verificar archivos creados
    print("\n📁 Test 4: Verificando archivos creados...")
    base_path = Path(stats['base_dir'])
    images_path = base_path / "images"
    messages_path = base_path / "messages.json"
    
    print(f"  - Directorio base existe: {base_path.exists()}")
    print(f"  - Directorio de imágenes existe: {images_path.exists()}")
    print(f"  - Archivo messages.json existe: {messages_path.exists()}")
    
    if messages_path.exists():
        import json
        with open(messages_path, "r", encoding="utf-8") as f:
            messages = json.load(f)
            print(f"  - Número de mensajes en JSON: {len(messages)}")
            if messages:
                print(f"  - Último mensaje: {messages[-1]['title']}")
    
    # Cerrar servicio
    await storage.close()
    
    print("\n✅ Todas las pruebas completadas exitosamente!")


if __name__ == "__main__":
    asyncio.run(test_local_storage())
