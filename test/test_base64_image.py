"""
Script de prueba para validar generación de Base64 de imágenes
===============================================================
Genera una imagen de prueba y la guarda en diferentes formatos
para comparar con lo que se envía a Telegram.
"""

import base64
from pathlib import Path


def test_base64_from_file():
    """Lee una imagen guardada y la convierte a Base64."""
    logs_dir = Path("logs")
    
    # Buscar la última imagen PNG guardada
    png_files = sorted(logs_dir.glob("chart_*.png"))
    
    if not png_files:
        print("❌ No se encontraron imágenes en logs/")
        return
    
    latest_png = png_files[-1]
    print(f"📁 Leyendo: {latest_png}")
    
    # Leer imagen como bytes
    image_bytes = latest_png.read_bytes()
    print(f"📦 Tamaño imagen: {len(image_bytes)} bytes")
    
    # Codificar a Base64
    base64_string = base64.b64encode(image_bytes).decode('utf-8')
    
    # Análisis
    print(f"\n{'='*80}")
    print("🔍 ANÁLISIS DEL BASE64")
    print(f"{'='*80}")
    print(f"✓ Longitud: {len(base64_string)} caracteres")
    print(f"✓ Tiene saltos de línea: {'SÍ' if '\\n' in base64_string or '\\r' in base64_string else 'NO'}")
    print(f"✓ Tiene espacios: {'SÍ' if ' ' in base64_string else 'NO'}")
    print(f"✓ Tiene prefijo data:image: {'SÍ' if base64_string.startswith('data:image') else 'NO'}")
    print(f"\n✓ Primeros 100 chars:")
    print(f"  {base64_string[:100]}")
    print(f"\n✓ Últimos 100 chars:")
    print(f"  {base64_string[-100:]}")
    
    # Guardar en archivo .txt
    output_file = logs_dir / "base64_from_png.txt"
    output_file.write_text(base64_string, encoding='utf-8')
    print(f"\n💾 Base64 guardado en: {output_file}")
    
    # Verificar decodificación
    try:
        decoded = base64.b64decode(base64_string)
        print(f"\n✅ Base64 VÁLIDO - Decodifica a {len(decoded)} bytes")
        
        if len(decoded) == len(image_bytes):
            print("✅ Tamaño coincide con original")
        else:
            print(f"⚠️ Tamaño diferente: Original {len(image_bytes)} vs Decodificado {len(decoded)}")
    except Exception as e:
        print(f"\n❌ Error al decodificar Base64: {e}")
    
    print(f"{'='*80}\n")
    
    return base64_string


def compare_with_generated():
    """Compara el Base64 del archivo .txt guardado (generado por el código) con el PNG."""
    logs_dir = Path("logs")
    
    # Buscar el último archivo .txt
    txt_files = sorted(logs_dir.glob("chart_*.txt"))
    
    if not txt_files:
        print("❌ No se encontraron archivos .txt en logs/")
        return
    
    latest_txt = txt_files[-1]
    print(f"📁 Leyendo Base64 generado: {latest_txt}")
    
    base64_generated = latest_txt.read_text(encoding='utf-8')
    
    print(f"\n{'='*80}")
    print("🔍 ANÁLISIS DEL BASE64 GENERADO POR EL CÓDIGO")
    print(f"{'='*80}")
    print(f"✓ Longitud: {len(base64_generated)} caracteres")
    print(f"✓ Tiene saltos de línea: {'SÍ' if '\\n' in base64_generated or '\\r' in base64_generated else 'NO'}")
    print(f"✓ Tiene espacios: {'SÍ' if ' ' in base64_generated else 'NO'}")
    print(f"✓ Tiene prefijo data:image: {'SÍ' if base64_generated.startswith('data:image') else 'NO'}")
    print(f"\n✓ Primeros 100 chars:")
    print(f"  {base64_generated[:100]}")
    print(f"\n✓ Últimos 100 chars:")
    print(f"  {base64_generated[-100:]}")
    
    # Verificar decodificación
    try:
        decoded = base64.b64decode(base64_generated)
        print(f"\n✅ Base64 VÁLIDO - Decodifica a {len(decoded)} bytes")
    except Exception as e:
        print(f"\n❌ Error al decodificar Base64: {e}")
    
    print(f"{'='*80}\n")


if __name__ == "__main__":
    print("\n🧪 TEST DE BASE64 DE IMÁGENES\n")
    
    # Test 1: Leer PNG y convertir
    print("=" * 80)
    print("TEST 1: Convertir PNG a Base64")
    print("=" * 80)
    base64_from_png = test_base64_from_file()
    
    print("\n" + "=" * 80)
    print("TEST 2: Analizar Base64 generado por el código")
    print("=" * 80)
    compare_with_generated()
    
    print("\n✅ TESTS COMPLETADOS")
    print("\nRECOMENDACIONES:")
    print("1. Compara el contenido de 'base64_from_png.txt' con el que envías en Postman")
    print("2. Si el de Postman funciona, copia ese Base64 y compáralo carácter por carácter")
    print("3. Busca diferencias en: prefijos, espacios, saltos de línea, padding (=)")
