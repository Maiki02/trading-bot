"""
Ejemplo de cómo leer y analizar el dataset JSONL
=================================================
Este script demuestra cómo cargar y analizar los datos del dataset
generado por el sistema de backtesting.

JSONL (JSON Lines): Cada línea es un JSON válido independiente.

Autor: TradingView Pattern Monitor Team
"""

import json
import pandas as pd
from pathlib import Path
from typing import List, Dict


def read_jsonl_simple(file_path: str) -> List[Dict]:
    """
    Método 1: Lectura simple línea por línea.
    
    Args:
        file_path: Ruta al archivo JSONL
        
    Returns:
        Lista de diccionarios con los registros
    """
    records = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:  # Ignorar líneas vacías
                record = json.loads(line)
                records.append(record)
    
    return records


def read_jsonl_pandas(file_path: str) -> pd.DataFrame:
    """
    Método 2: Lectura con pandas (recomendado para análisis).
    
    Args:
        file_path: Ruta al archivo JSONL
        
    Returns:
        DataFrame de pandas
    """
    records = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"⚠️  Línea inválida ignorada: {e}")
    
    return pd.DataFrame(records)


def analyze_dataset(df: pd.DataFrame):
    """
    Analiza el dataset y muestra estadísticas.
    
    Args:
        df: DataFrame con el dataset
    """
    print("=" * 80)
    print("📊 ANÁLISIS DEL DATASET")
    print("=" * 80)
    
    # Información básica
    print(f"\n📦 Total de registros: {len(df)}")
    print(f"📅 Rango de fechas:")
    print(f"   Primer registro: {df['timestamp'].min()}")
    print(f"   Último registro: {df['timestamp'].max()}")
    
    # Extraer columnas anidadas
    df['pattern'] = df['pattern_candle'].apply(lambda x: x['pattern'])
    df['confidence'] = df['pattern_candle'].apply(lambda x: x['confidence'])
    df['trend_score'] = df['emas'].apply(lambda x: x['trend_score'])
    df['alignment'] = df['emas'].apply(lambda x: x['alignment'])
    df['success'] = df['outcome'].apply(lambda x: x['success'])
    
    # Estadísticas por patrón
    print("\n🎯 PATRONES DETECTADOS:")
    pattern_counts = df['pattern'].value_counts()
    for pattern, count in pattern_counts.items():
        pct = (count / len(df)) * 100
        print(f"   {pattern}: {count} ({pct:.1f}%)")
    
    # Win rate por patrón
    print("\n✅ WIN RATE POR PATRÓN:")
    for pattern in df['pattern'].unique():
        pattern_df = df[df['pattern'] == pattern]
        win_rate = pattern_df['success'].mean() * 100
        wins = pattern_df['success'].sum()
        losses = len(pattern_df) - wins
        print(f"   {pattern}: {win_rate:.1f}% ({wins}W / {losses}L)")
    
    # Estadísticas de confianza
    print("\n💯 ESTADÍSTICAS DE CONFIANZA:")
    print(f"   Media: {df['confidence'].mean():.3f}")
    print(f"   Mínima: {df['confidence'].min():.3f}")
    print(f"   Máxima: {df['confidence'].max():.3f}")
    
    # Distribución de scores
    print("\n📈 DISTRIBUCIÓN DE TREND SCORES:")
    score_bins = pd.cut(df['trend_score'], bins=[-11, -6, -2, 1, 5, 11], 
                        labels=['Strong Bearish', 'Weak Bearish', 'Neutral', 'Weak Bullish', 'Strong Bullish'])
    score_dist = score_bins.value_counts().sort_index()
    for label, count in score_dist.items():
        pct = (count / len(df)) * 100
        print(f"   {label}: {count} ({pct:.1f}%)")
    
    # Alineación de EMAs
    print("\n🔀 ALINEACIÓN DE EMAs:")
    alignment_counts = df['alignment'].value_counts()
    for alignment, count in alignment_counts.items():
        pct = (count / len(df)) * 100
        print(f"   {alignment}: {count} ({pct:.1f}%)")
    
    # Win rate por alineación
    print("\n✅ WIN RATE POR ALINEACIÓN:")
    for alignment in df['alignment'].unique():
        alignment_df = df[df['alignment'] == alignment]
        win_rate = alignment_df['success'].mean() * 100
        print(f"   {alignment}: {win_rate:.1f}%")
    
    # Exchanges/símbolos
    print("\n🌐 FUENTES DE DATOS:")
    sources = df['source'].value_counts()
    for source, count in sources.items():
        print(f"   {source}: {count} registros")
    
    symbols = df['symbol'].value_counts()
    for symbol, count in symbols.items():
        print(f"   {symbol}: {count} registros")
    
    print("\n" + "=" * 80)


def calculate_pnl(row: Dict) -> float:
    """
    Calcula el PnL en pips desde los datos crudos.
    
    Args:
        row: Registro del dataset
        
    Returns:
        PnL en pips
    """
    pattern = row['pattern_candle']['pattern']
    pattern_close = row['pattern_candle']['close']
    outcome_close = row['outcome_candle']['close']
    
    # Patrones bajistas (SHORT)
    if pattern in ['SHOOTING_STAR', 'HANGING_MAN']:
        return (pattern_close - outcome_close) * 10000
    # Patrones alcistas (LONG)
    else:
        return (outcome_close - pattern_close) * 10000


def advanced_analysis(df: pd.DataFrame):
    """
    Análisis avanzado con cálculos derivados.
    
    Args:
        df: DataFrame con el dataset
    """
    print("\n" + "=" * 80)
    print("🔬 ANÁLISIS AVANZADO")
    print("=" * 80)
    
    # Extraer campos
    df['pattern'] = df['pattern_candle'].apply(lambda x: x['pattern'])
    df['success'] = df['outcome'].apply(lambda x: x['success'])
    
    # Calcular PnL para todos los registros
    df['pnl_pips'] = df.apply(calculate_pnl, axis=1)
    
    # PnL por patrón
    print("\n💰 PnL PROMEDIO POR PATRÓN:")
    for pattern in df['pattern'].unique():
        pattern_df = df[df['pattern'] == pattern]
        avg_pnl = pattern_df['pnl_pips'].mean()
        total_pnl = pattern_df['pnl_pips'].sum()
        print(f"   {pattern}: {avg_pnl:+.2f} pips promedio | Total: {total_pnl:+.2f} pips")
    
    # PnL acumulado
    df_sorted = df.sort_values('timestamp')
    df_sorted['cumulative_pnl'] = df_sorted['pnl_pips'].cumsum()
    
    print(f"\n📊 PnL ACUMULADO:")
    print(f"   Inicial: 0.00 pips")
    print(f"   Final: {df_sorted['cumulative_pnl'].iloc[-1]:+.2f} pips")
    print(f"   Máximo drawdown: {df_sorted['cumulative_pnl'].min():+.2f} pips")
    print(f"   Máximo peak: {df_sorted['cumulative_pnl'].max():+.2f} pips")
    
    # Mejor/peor operación
    best_trade = df.loc[df['pnl_pips'].idxmax()]
    worst_trade = df.loc[df['pnl_pips'].idxmin()]
    
    print(f"\n🏆 MEJOR OPERACIÓN:")
    print(f"   Patrón: {best_trade['pattern_candle']['pattern']}")
    print(f"   PnL: {best_trade['pnl_pips']:+.2f} pips")
    print(f"   Timestamp: {best_trade['timestamp']}")
    
    print(f"\n💔 PEOR OPERACIÓN:")
    print(f"   Patrón: {worst_trade['pattern_candle']['pattern']}")
    print(f"   PnL: {worst_trade['pnl_pips']:+.2f} pips")
    print(f"   Timestamp: {worst_trade['timestamp']}")
    
    print("\n" + "=" * 80)


def main():
    """Función principal."""
    dataset_path = Path("data/trading_signals_dataset.jsonl")
    
    if not dataset_path.exists():
        print(f"❌ Dataset no encontrado: {dataset_path}")
        return
    
    print(f"📂 Cargando dataset: {dataset_path}")
    print()
    
    # Método 1: Lectura simple
    print("🔧 Método 1: Lectura simple")
    records = read_jsonl_simple(str(dataset_path))
    print(f"✅ Cargados {len(records)} registros")
    
    if len(records) > 0:
        print("\n📋 Estructura del primer registro:")
        print(f"   Claves principales: {list(records[0].keys())}")
        print(f"   Source: {records[0]['source']}")
        print(f"   Symbol: {records[0]['symbol']}")
        print(f"   Pattern: {records[0]['pattern_candle']['pattern']}")
        print(f"   Confidence: {records[0]['pattern_candle']['confidence']:.3f}")
        print(f"   Success: {records[0]['outcome']['success']}")
    
    # Método 2: Con pandas (para análisis)
    print("\n🔧 Método 2: Lectura con pandas")
    df = read_jsonl_pandas(str(dataset_path))
    print(f"✅ DataFrame creado: {df.shape[0]} filas × {df.shape[1]} columnas")
    
    # Análisis completo
    if not df.empty:
        analyze_dataset(df)
        advanced_analysis(df)


if __name__ == "__main__":
    main()
