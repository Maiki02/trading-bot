"""
Script de prueba para StatisticsService
=========================================
Verifica que el sistema de probabilidad histórica funcione correctamente
con el dataset existente.

Ejecutar con:
    python test_statistics_service.py
"""
import asyncio
from pathlib import Path
from src.services.statistics_service import StatisticsService


async def main():
    print("=" * 60)
    print("TEST: Statistics Service")
    print("=" * 60)
    
    # Verificar que exista el dataset
    dataset_path = Path("data/trading_signals_dataset.jsonl")
    if not dataset_path.exists():
        print(f"❌ Dataset no encontrado: {dataset_path}")
        print("   Ejecuta el bot primero para generar datos.")
        return
    
    # Inicializar servicio
    print("\n1. Inicializando StatisticsService...")
    stats_service = StatisticsService()
    
    # Resumen general
    print("\n2. Resumen del dataset:")
    summary = stats_service.get_stats_summary()
    print(f"   ✓ Registros cargados: {summary['records_loaded']}")
    print(f"   ✓ Última carga: {summary['last_load_time']}")
    print(f"   ✓ Win rate general: {summary['overall_win_rate']:.1%}")
    print(f"   ✓ Patrones detectados:")
    for pattern, count in summary['patterns_detected'].items():
        print(f"      - {pattern}: {count} señales")
    
    # Test: Consultar probabilidad para diferentes patrones
    print("\n3. Consultando probabilidades por patrón y score:")
    
    test_cases = [
        ("SHOOTING_STAR", 10),
        ("HAMMER", 10),
        ("HANGING_MAN", 10),
        ("HANGING_MAN", -2),
    ]
    
    for pattern, score in test_cases:
        print(f"\n   📊 {pattern} (Score: {score:+d})")
        print(f"   " + "-" * 50)
        
        prob = stats_service.get_probability(
            pattern=pattern,
            current_score=score,
            lookback_days=30,
            score_tolerance=1
        )
        
        if prob['total_cases'] > 0:
            win_rate_pct = prob['win_rate'] * 100
            
            # Emoji según win rate
            if win_rate_pct >= 70:
                emoji = "🟢"
            elif win_rate_pct >= 50:
                emoji = "🟡"
            else:
                emoji = "🔴"
            
            print(f"   {emoji} Total casos: {prob['total_cases']}")
            print(f"   {emoji} Win rate: {win_rate_pct:.1f}%")
            print(f"   {emoji} Wins/Losses: {prob['wins']}/{prob['losses']}")
            print(f"   {emoji} PnL promedio: {prob['avg_pnl_pips']:.1f} pips")
            print(f"   {emoji} Score range: [{prob['score_range'][0]}, {prob['score_range'][1]}]")
            
            # Racha reciente
            streak_str = " ".join("✓" if r else "✗" for r in prob['streak'][:5])
            print(f"   {emoji} Racha (últimos 5): {streak_str}")
        else:
            print(f"   ⚠️  No hay datos disponibles")
    
    # Test: Verificar normalización de scores
    print("\n4. Verificando normalización de scores...")
    if stats_service.df is not None and not stats_service.df.empty:
        if 'calculated_score' in stats_service.df.columns:
            valid_scores = stats_service.df['calculated_score'].notna().sum()
            total_records = len(stats_service.df)
            print(f"   ✓ Scores recalculados: {valid_scores}/{total_records}")
            
            # Mostrar distribución de scores
            score_distribution = stats_service.df['calculated_score'].value_counts().sort_index()
            print(f"\n   📊 Distribución de scores recalculados:")
            for score, count in score_distribution.items():
                if not pd.isna(score):
                    print(f"      Score {int(score):+3d}: {'█' * count} ({count})")
        else:
            print(f"   ⚠️  Columna 'calculated_score' no existe")
    
    print("\n" + "=" * 60)
    print("✅ Test completado")
    print("=" * 60)


if __name__ == "__main__":
    import pandas as pd
    asyncio.run(main())
