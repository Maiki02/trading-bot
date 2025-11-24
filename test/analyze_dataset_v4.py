"""
Dataset Analysis Script v4.1
=============================
Analiza el dataset generado por backfill_historical_data_v41.py

Funcionalidades:
- Filtra por algo_version="4.1" y símbolo
- Agrupa por pattern_name y signal_strength
- Calcula Win Rate (ITM), Total Signals, Distribution

Usage:
    python test/analyze_dataset_v4.py
    python test/analyze_dataset_v4.py --symbol EUR USD
    python test/analyze_dataset_v4.py --file data/custom_dataset.jsonl

Author: Trading Bot Team
"""

import pandas as pd
import json
import argparse
from pathlib import Path
from typing import Dict, List
from collections import defaultdict


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

DEFAULT_DATASET_PATH = "data/trading_signals_dataset.jsonl"
ALGO_VERSION = "4.1"


# =============================================================================
# CARGA DE DATOS
# =============================================================================

def load_dataset(file_path: str, symbol_filter: str = None) -> pd.DataFrame:
    """
    Carga el dataset JSONL y filtra por versión y símbolo.
    
    Args:
        file_path: Ruta al archivo JSONL
        symbol_filter: Símbolo a filtrar (opcional, ej: "EURUSD")
        
    Returns:
        DataFrame con los datos filtrados
    """
    print("=" * 80)
    print("📂 CARGANDO DATASET")
    print("=" * 80)
    print(f"Archivo: {file_path}")
    
    if not Path(file_path).exists():
        raise FileNotFoundError(f"❌ No se encontró el archivo: {file_path}")
    
    # Leer JSONL
    records = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                record = json.loads(line.strip())
                records.append(record)
            except json.JSONDecodeError:
                continue
    
    print(f"✅ Total registros leídos: {len(records)}")
    
    # Crear DataFrame
    df = pd.DataFrame(records)
    
    # Filtrar por algo_version
    df = df[df['algo_version'] == ALGO_VERSION]
    print(f"✅ Registros con algo_version={ALGO_VERSION}: {len(df)}")
    
    # Filtrar por símbolo (opcional)
    if symbol_filter:
        df = df[df['symbol'] == symbol_filter]
        print(f"✅ Registros con symbol={symbol_filter}: {len(df)}")
    
    if df.empty:
        print("⚠️ No se encontraron registros con los filtros aplicados")
        return df
    
    # Mostrar símbolos disponibles
    print(f"\n📊 Símbolos disponibles: {df['symbol'].unique().tolist()}")
    print(f"📊 Rango de fechas: {pd.to_datetime(df['timestamp'], unit='s').min()} a {pd.to_datetime(df['timestamp'], unit='s').max()}")
    
    return df


# =============================================================================
# ANÁLISIS DE WIN RATE
# =============================================================================

def calculate_expected_direction(pattern_name: str) -> str:
    """
    Determina la dirección esperada según el patrón.
    
    Args:
        pattern_name: Nombre del patrón
        
    Returns:
        "VERDE" (alcista) o "ROJA" (bajista)
    """
    if pattern_name in ["SHOOTING_STAR", "HANGING_MAN"]:
        return "ROJA"  # Patrones bajistas
    elif pattern_name in ["INVERTED_HAMMER", "HAMMER"]:
        return "VERDE"  # Patrones alcistas
    else:
        return "DOJI"


def analyze_win_rate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula Win Rate por patrón y signal_strength.
    
    Args:
        df: DataFrame con el dataset
        
    Returns:
        DataFrame con resultados agregados
    """
    print("\n" + "=" * 80)
    print("📊 ANÁLISIS DE WIN RATE")
    print("=" * 80)
    
    # Calcular dirección esperada
    df['expected_direction'] = df['pattern_name'].apply(calculate_expected_direction)
    
    # Calcular si fue WIN (ITM)
    df['is_win'] = df['outcome'] == df['expected_direction']
    
    # Agrupar por pattern_name y signal_strength
    results = []
    
    for (pattern, strength), group in df.groupby(['pattern_name', 'signal_strength']):
        total_signals = len(group)
        total_wins = group['is_win'].sum()
        total_losses = total_signals - total_wins
        win_rate = (total_wins / total_signals) * 100 if total_signals > 0 else 0
        
        # Distribution de outcomes
        verde_count = (group['outcome'] == 'VERDE').sum()
        roja_count = (group['outcome'] == 'ROJA').sum()
        doji_count = (group['outcome'] == 'DOJI').sum()
        
        results.append({
            'Pattern': pattern,
            'Signal Strength': strength,
            'Total Signals': total_signals,
            'Wins (ITM)': total_wins,
            'Losses (OTM)': total_losses,
            'Win Rate %': round(win_rate, 2),
            'Verde Next': verde_count,
            'Roja Next': roja_count,
            'Doji Next': doji_count
        })
    
    # Crear DataFrame de resultados
    results_df = pd.DataFrame(results)
    
    # Ordenar por Signal Strength y Win Rate
    strength_order = ['VERY_HIGH', 'HIGH', 'MEDIUM', 'LOW', 'VERY_LOW', 'NONE']
    results_df['strength_sort'] = results_df['Signal Strength'].apply(
        lambda x: strength_order.index(x) if x in strength_order else 999
    )
    results_df = results_df.sort_values(['strength_sort', 'Win Rate %'], ascending=[True, False])
    results_df = results_df.drop('strength_sort', axis=1)
    
    return results_df


# =============================================================================
# ANÁLISIS DETALLADO POR EXHAUSTION
# =============================================================================

def analyze_by_exhaustion(df: pd.DataFrame) -> None:
    """
    Analiza Win Rate según combinaciones de exhaustion.
    
    Args:
        df: DataFrame con el dataset
    """
    print("\n" + "=" * 80)
    print("🔥 ANÁLISIS POR EXHAUSTION")
    print("=" * 80)
    
    df['expected_direction'] = df['pattern_name'].apply(calculate_expected_direction)
    df['is_win'] = df['outcome'] == df['expected_direction']
    
    results = []
    
    for (pattern, boll_exh, candle_exh), group in df.groupby(['pattern_name', 'bollinger_exhaustion', 'candle_exhaustion']):
        total = len(group)
        wins = group['is_win'].sum()
        win_rate = (wins / total) * 100 if total > 0 else 0
        
        results.append({
            'Pattern': pattern,
            'Bollinger Exh': '✅' if boll_exh else '❌',
            'Candle Exh': '✅' if candle_exh else '❌',
            'Total': total,
            'Wins': wins,
            'Win Rate %': round(win_rate, 2)
        })
    
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(['Pattern', 'Win Rate %'], ascending=[True, False])
    
    print(results_df.to_string(index=False))


# =============================================================================
# ANÁLISIS POR TENDENCIA
# =============================================================================

def analyze_by_trend(df: pd.DataFrame) -> None:
    """
    Analiza Win Rate según el estado de tendencia.
    
    Args:
        df: DataFrame con el dataset
    """
    print("\n" + "=" * 80)
    print("📈 ANÁLISIS POR TENDENCIA")
    print("=" * 80)
    
    df['expected_direction'] = df['pattern_name'].apply(calculate_expected_direction)
    df['is_win'] = df['outcome'] == df['expected_direction']
    
    results = []
    
    for (pattern, trend_status), group in df.groupby(['pattern_name', 'trend_status']):
        total = len(group)
        wins = group['is_win'].sum()
        win_rate = (wins / total) * 100 if total > 0 else 0
        avg_score = group['trend_score'].mean()
        
        results.append({
            'Pattern': pattern,
            'Trend Status': trend_status,
            'Avg Score': round(avg_score, 2),
            'Total': total,
            'Wins': wins,
            'Win Rate %': round(win_rate, 2)
        })
    
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(['Pattern', 'Win Rate %'], ascending=[True, False])
    
    print(results_df.to_string(index=False))


# =============================================================================
# RESUMEN GLOBAL
# =============================================================================

def print_summary(df: pd.DataFrame) -> None:
    """
    Imprime resumen global del dataset.
    
    Args:
        df: DataFrame con el dataset
    """
    print("\n" + "=" * 80)
    print("📋 RESUMEN GLOBAL")
    print("=" * 80)
    
    df['expected_direction'] = df['pattern_name'].apply(calculate_expected_direction)
    df['is_win'] = df['outcome'] == df['expected_direction']
    
    total_signals = len(df)
    total_wins = df['is_win'].sum()
    global_win_rate = (total_wins / total_signals) * 100 if total_signals > 0 else 0
    
    print(f"Total Señales: {total_signals}")
    print(f"Total Wins (ITM): {total_wins}")
    print(f"Total Losses (OTM): {total_signals - total_wins}")
    print(f"Win Rate Global: {global_win_rate:.2f}%")
    
    print(f"\n📊 Distribución por Patrón:")
    pattern_counts = df['pattern_name'].value_counts()
    for pattern, count in pattern_counts.items():
        print(f"  {pattern}: {count} señales")
    
    print(f"\n🔥 Distribución por Signal Strength:")
    strength_counts = df['signal_strength'].value_counts()
    strength_order = ['VERY_HIGH', 'HIGH', 'MEDIUM', 'LOW', 'VERY_LOW', 'NONE']
    for strength in strength_order:
        if strength in strength_counts.index:
            print(f"  {strength}: {strength_counts[strength]} señales")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Función principal."""
    parser = argparse.ArgumentParser(description='Análisis de dataset v4.1')
    parser.add_argument('--file', type=str, default=DEFAULT_DATASET_PATH,
                        help=f'Ruta al archivo JSONL (default: {DEFAULT_DATASET_PATH})')
    parser.add_argument('--symbol', type=str, default=None,
                        help='Filtrar por símbolo (ej: EURUSD)')
    
    args = parser.parse_args()
    
    try:
        # Cargar dataset
        df = load_dataset(args.file, args.symbol)
        
        if df.empty:
            print("\n❌ No hay datos para analizar")
            return
        
        # Resumen global
        print_summary(df)
        
        # Análisis de Win Rate
        results_df = analyze_win_rate(df)
        print("\n" + "=" * 80)
        print("📊 RESULTADOS POR PATRÓN Y SIGNAL STRENGTH")
        print("=" * 80)
        print(results_df.to_string(index=False))
        
        # Análisis por exhaustion
        analyze_by_exhaustion(df)
        
        # Análisis por tendencia
        analyze_by_trend(df)
        
        # Guardar resultados en CSV
        output_file = f"test/analysis_results_v41_{args.symbol if args.symbol else 'ALL'}.csv"
        results_df.to_csv(output_file, index=False)
        print(f"\n💾 Resultados guardados en: {output_file}")
        
        print("\n" + "=" * 80)
        print("✅ ANÁLISIS COMPLETADO")
        print("=" * 80)
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
