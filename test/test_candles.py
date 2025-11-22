"""
Test de Validación de Patrones - Sistema Automatizado
=======================================================
Lee casos de prueba desde test_data.json y valida que cada vela
sea detectada correctamente según su tipo esperado.

Tipos de vela VÁLIDOS (obligatorios):
- shooting_star
- hanging_man
- inverted_hammer
- hammer
"""

import json
import sys
from pathlib import Path

# Agregar el directorio raíz al path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# Importar directamente desde el archivo candle.py (evita import circular)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "candle_module",
    root_dir / "src" / "logic" / "candle.py"
)
candle_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candle_module)

# Asignar funciones importadas
is_shooting_star = candle_module.is_shooting_star
is_hanging_man = candle_module.is_hanging_man
is_inverted_hammer = candle_module.is_inverted_hammer
is_hammer = candle_module.is_hammer
_calculate_candle_metrics = candle_module._calculate_candle_metrics

# Tipos de vela válidos
VALID_CANDLE_TYPES = ["shooting_star", "hanging_man", "inverted_hammer", "hammer"]


def test_candle(test_case: dict, case_number: int) -> bool:
    """
    Prueba un caso individual de vela.
    
    Args:
        test_case: Diccionario con datos de la vela
        case_number: Número del caso de prueba
    
    Returns:
        bool: True si el test pasó, False si falló
    """
    apertura = test_case["apertura"]
    cierre = test_case["cierre"]
    maximo = test_case["maximo"]
    minimo = test_case["minimo"]
    tipo_esperado = test_case["tipo_vela"]
    
    # Validar que el tipo de vela sea válido
    if tipo_esperado not in VALID_CANDLE_TYPES:
        print(f"\n❌ ERROR CASO #{case_number}: Tipo '{tipo_esperado}' inválido. Válidos: {', '.join(VALID_CANDLE_TYPES)}")
        return False
    
    # Header compacto
    print(f"\n{'─'*80}")
    print(f"📊 Caso #{case_number} | Tipo: {tipo_esperado} | O:{apertura:.5f} H:{maximo:.5f} L:{minimo:.5f} C:{cierre:.5f}")
    
    # Calcular métricas para diagnóstico
    total_range, body_size, upper_wick, lower_wick, body_ratio = _calculate_candle_metrics(
        apertura, maximo, minimo, cierre
    )
    
    if total_range == 0:
        print(f"❌ FALLIDO: Rango total es 0 (vela sin movimiento)")
        return False
    
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    
    # Determinar si es patrón de mecha superior o inferior
    is_upper_wick = tipo_esperado in ["shooting_star", "inverted_hammer"]
    
    if is_upper_wick:
        long_wick_ratio = upper_wick_ratio
        opposite_wick_ratio = lower_wick_ratio
        long_wick_size = upper_wick
        wick_name = "superior"
    else:
        long_wick_ratio = lower_wick_ratio
        opposite_wick_ratio = upper_wick_ratio
        long_wick_size = lower_wick
        wick_name = "inferior"
    
    # Validar condiciones
    has_long_wick = long_wick_ratio >= 0.60
    has_small_body = body_ratio <= 0.30
    has_small_opposite = opposite_wick_ratio <= 0.15
    wick_to_body_ok = (long_wick_size / body_size) >= 2.0 if body_size > 0 else False
    
    # Switch para ejecutar la función correspondiente
    if tipo_esperado == "shooting_star":
        is_detected, confidence = is_shooting_star(apertura, maximo, minimo, cierre)
    elif tipo_esperado == "hanging_man":
        is_detected, confidence = is_hanging_man(apertura, maximo, minimo, cierre)
    elif tipo_esperado == "inverted_hammer":
        is_detected, confidence = is_inverted_hammer(apertura, maximo, minimo, cierre)
    elif tipo_esperado == "hammer":
        is_detected, confidence = is_hammer(apertura, maximo, minimo, cierre)
    else:
        is_detected = False
        confidence = 0.0
    
    # Mostrar resultado
    if is_detected:
        print(f"✅ PASADO - Fidelidad: {confidence:.0%}")
    else:
        print(f"❌ FALLIDO - Razones:")
        
        # Explicar cada condición que no se cumple
        failures = []
        
        if not has_long_wick:
            failures.append(f"   • Mecha {wick_name} insuficiente: {long_wick_ratio:.1%} < 60% requerido")
        
        if not has_small_body:
            failures.append(f"   • Cuerpo demasiado grande: {body_ratio:.1%} > 30% máximo permitido")
        
        if not has_small_opposite:
            failures.append(f"   • Mecha opuesta muy larga: {opposite_wick_ratio:.1%} > 15% máximo")
        
        if not wick_to_body_ok:
            actual_ratio = (long_wick_size / body_size) if body_size > 0 else 0
            failures.append(f"   • Ratio mecha/cuerpo bajo: {actual_ratio:.2f}x < 2.0x requerido")
        
        if not failures:
            failures.append(f"   • Condiciones no cumplidas (fidelidad: {confidence:.0%})")
        
        for failure in failures:
            print(failure)
    
    return is_detected


def run_tests():
    """Ejecuta todos los tests desde el archivo JSON."""
    # Cargar datos de prueba
    test_file = Path(__file__).parent / "test_data.json"
    
    if not test_file.exists():
        print(f"❌ ERROR: No se encontró el archivo {test_file}")
        return False
    
    with open(test_file, "r", encoding="utf-8") as f:
        test_cases = json.load(f)
    
    print("\n" + "🧪 " * 40)
    print("SISTEMA AUTOMATIZADO DE VALIDACIÓN DE PATRONES")
    print("🧪 " * 40)
    print(f"\n📁 Archivo de datos: {test_file}")
    print(f"📊 Total de casos: {len(test_cases)}")
    
    # Ejecutar cada test
    results = []
    for i, test_case in enumerate(test_cases, 1):
        passed = test_candle(test_case, i)
        results.append(passed)
    
    # Resumen final
    total_tests = len(results)
    tests_passed = sum(results)
    tests_failed = total_tests - tests_passed
    
    print(f"\n{'='*80}")
    print("📊 RESUMEN FINAL")
    print(f"{'='*80}")
    print(f"Total de tests: {total_tests}")
    print(f"✅ Tests pasados: {tests_passed}")
    print(f"❌ Tests fallidos: {tests_failed}")
    print(f"Porcentaje de éxito: {(tests_passed/total_tests)*100:.1f}%")
    print(f"{'='*80}")
    
    if tests_failed == 0:
        print("\n🎉 ¡TODOS LOS TESTS PASARON! 🎉\n")
        return True
    else:
        print(f"\n⚠️  {tests_failed} test(s) fallaron. Revisar casos arriba.\n")
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
