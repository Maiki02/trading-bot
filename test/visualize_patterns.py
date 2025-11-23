"""
Visualizador de Patrones - Test Data
=====================================
Genera gráficos con las velas detectadas en test_data.json,
normalizadas en términos porcentuales para poder visualizar patrones
de diferentes escalas de precios (forex vs crypto) en el mismo gráfico.

Valida que las velas detectadas realmente cumplan con el patrón esperado
y las colorea según su validez:
- 🟦 AZUL: Vela válida que pasó el test
- 🟥 ROJO: Vela inválida que NO pasó el test

Usage:
    python test/visualize_patterns.py
    python test/visualize_patterns.py --pattern shooting_star
    python test/visualize_patterns.py --pattern hammer
"""

import json
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np
import argparse
import sys
import importlib.util

# Cargar config.py directamente (sin __init__.py)
project_root = Path(__file__).parent.parent
config_path = project_root / "config.py"
spec = importlib.util.spec_from_file_location("config", config_path)
config_module = importlib.util.module_from_spec(spec)
sys.modules['config'] = config_module  # Registrar en sys.modules para que candle.py lo encuentre
spec.loader.exec_module(config_module)

# Cargar candle.py directamente (sin pasar por __init__.py que causa imports circulares)
candle_path = project_root / "src" / "logic" / "candle.py"
spec = importlib.util.spec_from_file_location("candle_detection", candle_path)
candle_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candle_module)

# Extraer funciones
is_shooting_star = candle_module.is_shooting_star
is_hanging_man = candle_module.is_hanging_man
is_hammer = candle_module.is_hammer
is_inverted_hammer = candle_module.is_inverted_hammer



def normalize_candle(candle: Dict[str, float]) -> Dict[str, float]:
    """
    Normaliza una vela en términos porcentuales relativos a su apertura.
    
    Args:
        candle: Diccionario con {apertura, maximo, minimo, cierre}
    
    Returns:
        Diccionario con valores normalizados en porcentaje
    """
    apertura = candle["apertura"]
    
    return {
        "apertura": 0.0,  # Siempre 0% (punto de referencia)
        "maximo": ((candle["maximo"] - apertura) / apertura) * 100,
        "minimo": ((candle["minimo"] - apertura) / apertura) * 100,
        "cierre": ((candle["cierre"] - apertura) / apertura) * 100,
        "tipo_vela": candle["tipo_vela"]
    }


def validate_pattern(candle: Dict[str, float], expected_pattern: str) -> bool:
    """
    Valida si una vela cumple realmente con el patrón esperado.
    Usa las funciones oficiales de src.logic.candle
    
    Args:
        candle: Vela original (no normalizada)
        expected_pattern: Tipo de patrón esperado
    
    Returns:
        True si la vela es válida para ese patrón
    """
    apertura = candle["apertura"]
    maximo = candle["maximo"]
    minimo = candle["minimo"]
    cierre = candle["cierre"]
    
    # Ejecutar función de validación según tipo usando candle.py
    if expected_pattern == "shooting_star":
        detected, _ = is_shooting_star(apertura, maximo, minimo, cierre)
        return detected
    elif expected_pattern == "hanging_man":
        detected, _ = is_hanging_man(apertura, maximo, minimo, cierre)
        return detected
    elif expected_pattern == "hammer":
        detected, _ = is_hammer(apertura, maximo, minimo, cierre)
        return detected
    elif expected_pattern == "inverted_hammer":
        detected, _ = is_inverted_hammer(apertura, maximo, minimo, cierre)
        return detected
    else:
        return False


def plot_candle(ax, x_pos: int, candle: Dict[str, float], is_valid: bool):
    """
    Dibuja una vela individual en el gráfico.
    
    Args:
        ax: Axes de matplotlib
        x_pos: Posición X de la vela
        candle: Datos normalizados de la vela
        is_valid: True si la vela pasó la validación
    """
    apertura = candle["apertura"]
    cierre = candle["cierre"]
    maximo = candle["maximo"]
    minimo = candle["minimo"]
    
    # Color según validez
    color = "#4488FF" if is_valid else "#FF4444"  # AZUL si válida, ROJO si inválida
    
    # Cuerpo de la vela
    body_bottom = min(apertura, cierre)
    body_height = abs(cierre - apertura)
    
    # Dibujar mechas (high/low wicks)
    ax.plot([x_pos, x_pos], [minimo, maximo], color=color, linewidth=0.8, alpha=0.6)
    
    # Dibujar cuerpo
    if body_height > 0:
        rect = plt.Rectangle(
            (x_pos - 0.3, body_bottom),
            0.6,
            body_height,
            facecolor=color,
            edgecolor=color,
            alpha=0.7
        )
        ax.add_patch(rect)
    else:
        # Doji - línea horizontal
        ax.plot([x_pos - 0.3, x_pos + 0.3], [apertura, apertura], color=color, linewidth=1.5)


def visualize_patterns(test_data_path: Path, pattern_filter: Optional[str] = None):
    """
    Genera un gráfico con las velas de test_data.json.
    
    Args:
        test_data_path: Ruta al archivo test_data.json
        pattern_filter: Filtro de patrón (shooting_star, hanging_man, hammer, inverted_hammer)
                       Si es None, muestra todos los patrones
    """
    # Leer datos
    with open(test_data_path, "r", encoding="utf-8") as f:
        all_candles = json.load(f)
    
    # Filtrar por tipo si se especifica
    if pattern_filter:
        candles = [c for c in all_candles if c["tipo_vela"] == pattern_filter]
        print(f"📊 Filtro aplicado: {pattern_filter}")
        print(f"📊 {len(candles)}/{len(all_candles)} velas seleccionadas")
    else:
        candles = all_candles
        print(f"📊 Cargadas {len(candles)} velas (todos los patrones)")
    
    if not candles:
        print(f"❌ No se encontraron velas para el patrón: {pattern_filter}")
        return
    
    # Validar cada vela
    print("\n🔍 Validando patrones...")
    validations = []
    for candle in candles:
        is_valid = validate_pattern(candle, candle["tipo_vela"])
        validations.append(is_valid)
    
    valid_count = sum(validations)
    invalid_count = len(validations) - valid_count
    accuracy = (valid_count / len(validations)) * 100 if validations else 0
    
    print(f"   ✅ Válidas: {valid_count}")
    print(f"   ❌ Inválidas: {invalid_count}")
    print(f"   📈 Precisión: {accuracy:.1f}%")
    
    # Normalizar todas las velas
    normalized_candles = [normalize_candle(c) for c in candles]
    
    # Crear figura
    fig, ax = plt.subplots(figsize=(20, 8))
    
    # Dibujar todas las velas
    for i, (candle, is_valid) in enumerate(zip(normalized_candles, validations)):
        plot_candle(ax, i, candle, is_valid)
    
    # Título según filtro
    pattern_name = pattern_filter.replace("_", " ").title() if pattern_filter else "Todos los Patrones"
    
    # Configuración del gráfico
    ax.set_xlabel("Índice de Vela", fontsize=12)
    ax.set_ylabel("Cambio Porcentual desde Apertura (%)", fontsize=12)
    ax.set_title(
        f"{pattern_name} - Validación de Patrones ({len(candles)} velas)\n"
        f"✅ Válidas: {valid_count} ({accuracy:.1f}%) | ❌ Inválidas: {invalid_count}",
        fontsize=14,
        fontweight="bold"
    )
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.axhline(y=0, color="black", linewidth=1, linestyle="-", alpha=0.5)
    
    # Leyenda
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#4488FF", label=f"Válida (pasó el test): {valid_count}"),
        Patch(facecolor="#FF4444", label=f"Inválida (NO pasó el test): {invalid_count}")
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=10)
    
    # Ajustar límites
    ax.set_xlim(-1, len(normalized_candles))
    
    # Guardar gráfico en images_patterns/
    output_dir = test_data_path.parent / "images_patterns"
    output_dir.mkdir(exist_ok=True)
    
    filename = f"{pattern_filter}.png" if pattern_filter else "all_patterns.png"
    output_path = output_dir / filename
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"\n✅ Gráfico guardado en: {output_path}")
    
    # Mostrar gráfico
    plt.show()
    
    # Estadísticas adicionales
    print("\n📊 Estadísticas de Normalización:")
    all_maximos = [c["maximo"] for c in normalized_candles]
    all_minimos = [c["minimo"] for c in normalized_candles]
    all_cierres = [c["cierre"] for c in normalized_candles]
    
    print(f"   • Rango máximo: {min(all_minimos):.3f}% a {max(all_maximos):.3f}%")
    print(f"   • Promedio de cierre: {np.mean(all_cierres):.3f}%")
    print(f"   • Volatilidad (std cierre): {np.std(all_cierres):.3f}%")


def main():
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(description="Visualizador de patrones de velas japonesas")
    parser.add_argument(
        "--pattern",
        type=str,
        choices=["shooting_star", "hanging_man", "hammer", "inverted_hammer"],
        help="Filtrar por tipo de patrón específico"
    )
    args = parser.parse_args()
    
    test_data_path = Path(__file__).parent / "test_data.json"
    
    if not test_data_path.exists():
        print(f"❌ Error: No se encontró {test_data_path}")
        return
    
    visualize_patterns(test_data_path, args.pattern)


if __name__ == "__main__":
    main()
