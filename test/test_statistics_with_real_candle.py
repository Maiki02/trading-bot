"""
Test de StatisticsService con valores reales de una vela detectada.

Este test simula EXACTAMENTE cómo analysis_service llama a statistics_service,
usando los valores del log de una vela SHOOTING_STAR detectada el 23/11/2025.

Valores de la vela del log:
- Timestamp: 1763878080
- Apertura: 86468.84, Máximo: 86500.00, Mínimo: 86455.56, Cierre: 86460.01
- EMAs: 20=86349.26655, 30=86323.26360, 50=86315.84033, 200=86208.50971
- Tendencia: STRONG_BULLISH (Score: +10)
- Patrón: SHOOTING_STAR (Confianza: 90%)
- Alineación: ✓ Alineado
"""
import sys
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.statistics_service import StatisticsService
from src.logic.analysis_service import get_ema_alignment_string, get_ema_order_string


def test_statistics_with_real_candle():
    """
    Test que simula la llamada exacta de analysis_service a statistics_service.
    """
    print("\n" + "="*80)
    print("🧪 TEST: StatisticsService con valores reales de vela detectada")
    print("="*80)
    
    # Valores extraídos del log (EXACTOS)
    candle_data = {
        "timestamp": 1763878080,
        "open": 86468.84,
        "high": 86500.00,
        "low": 86455.56,
        "close": 86460.01,
        "volume": 95.89
    }
    
    emas_data = {
        "ema_20": 86349.26655,
        "ema_30": 86323.26360,
        "ema_50": 86315.84033,
        "ema_200": 86208.50971
    }
    
    pattern_info = {
        "pattern": "SHOOTING_STAR",
        "confidence": 0.90,
        "trend": "STRONG_BULLISH",
        "trend_score": 10,
        "is_aligned": True
    }
    
    print("\n📊 DATOS DE LA VELA")
    print("-" * 80)
    print(f"Timestamp: {candle_data['timestamp']}")
    print(f"OHLC: O={candle_data['open']:.5f} | H={candle_data['high']:.5f} | "
          f"L={candle_data['low']:.5f} | C={candle_data['close']:.5f}")
    print(f"EMAs: 20={emas_data['ema_20']:.5f} | 30={emas_data['ema_30']:.5f} | "
          f"50={emas_data['ema_50']:.5f} | 200={emas_data['ema_200']:.5f}")
    print(f"Patrón: {pattern_info['pattern']} ({pattern_info['confidence']:.0%} confianza)")
    print(f"Tendencia: {pattern_info['trend']} (Score: {pattern_info['trend_score']:+d}/10)")
    print(f"Alineación: {'✓ Alineado' if pattern_info['is_aligned'] else '✗ No alineado'}")
    
    # Calcular alignment y ema_order IGUAL que analysis_service
    print("\n🔧 CALCULANDO VALORES PARA BÚSQUEDA")
    print("-" * 80)
    
    current_alignment = get_ema_alignment_string(emas_data)
    print(f"Alignment: {current_alignment}")
    
    current_ema_order = get_ema_order_string(candle_data['close'], emas_data)
    print(f"EMA Order: {current_ema_order}")
    
    # Inicializar StatisticsService con el dataset real
    print("\n📂 INICIALIZANDO STATISTICS SERVICE")
    print("-" * 80)
    
    stats_service = StatisticsService(
        data_path="data/trading_signals_dataset.jsonl"
    )
    
    print(f"Registros cargados: {stats_service.records_loaded}")
    
    if stats_service.df is not None and not stats_service.df.empty:
        print(f"Columnas disponibles: {list(stats_service.df.columns)}")
        print(f"Primeras 3 filas:")
        print(stats_service.df.head(3))
    else:
        print("⚠️  Dataset vacío")
    
    # Llamar a get_probability EXACTAMENTE como lo hace analysis_service
    print("\n🔍 LLAMANDO A get_probability()")
    print("-" * 80)
    print(f"Parámetros:")
    print(f"  pattern={pattern_info['pattern']}")
    print(f"  current_score={pattern_info['trend_score']}")
    print(f"  current_alignment={current_alignment}")
    print(f"  current_ema_order={current_ema_order}")
    print(f"  lookback_days=30")
    print(f"  score_tolerance=1")
    
    statistics = stats_service.get_probability(
        pattern=pattern_info['pattern'],
        current_score=pattern_info['trend_score'],
        current_alignment=current_alignment,
        current_ema_order=current_ema_order,
        lookback_days=30,
        score_tolerance=1
    )
    
    # Mostrar resultados
    print("\n📊 RESULTADOS DE ESTADÍSTICAS")
    print("="*80)
    
    # Nivel 1: EXACT (Score exacto + EMA order exacto)
    print("\n🎯 NIVEL 1: EXACT (Score exacto + EMA order exacto)")
    print("-" * 80)
    exact = statistics.get('exact', {})
    print(f"Total casos: {exact.get('total_cases', 0)}")
    print(f"Verde: {exact.get('verde_count', 0)} ({exact.get('verde_pct', 0.0):.1%})")
    print(f"Roja: {exact.get('roja_count', 0)} ({exact.get('roja_pct', 0.0):.1%})")
    print(f"Dirección esperada: {exact.get('expected_direction', 'UNKNOWN')}")
    
    # Nivel 2: BY_ALIGNMENT (Score similar + mismo alignment)
    print("\n📊 NIVEL 2: BY_ALIGNMENT (Score similar + mismo alignment)")
    print("-" * 80)
    by_alignment = statistics.get('by_alignment', {})
    print(f"Total casos: {by_alignment.get('total_cases', 0)}")
    print(f"Verde: {by_alignment.get('verde_count', 0)} ({by_alignment.get('verde_pct', 0.0):.1%})")
    print(f"Roja: {by_alignment.get('roja_count', 0)} ({by_alignment.get('roja_pct', 0.0):.1%})")
    print(f"Dirección esperada: {by_alignment.get('expected_direction', 'UNKNOWN')}")
    print(f"Rango de score: {by_alignment.get('score_range', (0, 0))}")
    
    # Nivel 3: BY_SCORE (Solo score similar)
    print("\n📈 NIVEL 3: BY_SCORE (Solo score similar)")
    print("-" * 80)
    by_score = statistics.get('by_score', {})
    print(f"Total casos: {by_score.get('total_cases', 0)}")
    print(f"Verde: {by_score.get('verde_count', 0)} ({by_score.get('verde_pct', 0.0):.1%})")
    print(f"Roja: {by_score.get('roja_count', 0)} ({by_score.get('roja_pct', 0.0):.1%})")
    print(f"Dirección esperada: {by_score.get('expected_direction', 'UNKNOWN')}")
    print(f"Rango de score: {by_score.get('score_range', (0, 0))}")
    
    # Racha reciente
    print("\n🔄 RACHA RECIENTE (últimas 5 velas)")
    print("-" * 80)
    streak = statistics.get('streak', [])
    if streak:
        print(" → ".join(streak))
    else:
        print("No hay racha disponible")
    
    print("\n" + "="*80)
    print("✅ TEST COMPLETADO")
    print("="*80)
    
    # Resumen final
    print("\n📋 RESUMEN")
    print("-" * 80)
    if by_score.get('total_cases', 0) == 0:
        print("⚠️  NO SE ENCONTRARON CASOS HISTÓRICOS")
        print("\nPosibles causas:")
        print("1. El dataset está vacío (ejecutar backfill_historical_data.py)")
        print("2. No hay patrones SHOOTING_STAR con score +10 en los últimos 30 días")
        print("3. El rango de score (9-11) no tiene coincidencias")
    else:
        print(f"✓ Se encontraron {by_score.get('total_cases', 0)} casos similares")
        print(f"✓ Dirección más probable: {by_score.get('expected_direction', 'UNKNOWN')}")
    
    return statistics


if __name__ == "__main__":
    test_statistics_with_real_candle()
