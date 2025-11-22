"""
Análisis de Dataset de Backtesting
===================================
Script para analizar el dataset generado por StorageService.
Proporciona estadísticas, visualizaciones y métricas de performance.

Usage:
    python scripts/analyze_dataset.py
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Any
from datetime import datetime


def load_dataset(file_path: str = "data/trading_signals_dataset.jsonl") -> List[Dict[str, Any]]:
    """
    Carga el dataset completo desde el archivo JSONL.
    
    Args:
        file_path: Ruta al archivo JSONL
        
    Returns:
        Lista de registros
    """
    records = []
    file = Path(file_path)
    
    if not file.exists():
        print(f"❌ Archivo no encontrado: {file_path}")
        return records
    
    with open(file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                print(f"⚠️  Error en línea {line_num}: {e}")
    
    print(f"✅ Cargados {len(records)} registros desde {file_path}")
    return records


def analyze_success_rate_by_pattern(records: List[Dict]) -> Dict[str, Dict]:
    """
    Calcula tasa de éxito por patrón.
    
    Returns:
        Dict con estadísticas por patrón
    """
    stats = defaultdict(lambda: {"total": 0, "success": 0, "pnl_total": 0.0})
    
    for record in records:
        pattern = record["signal"]["pattern"]
        success = record["outcome"]["success"]
        pnl = record["outcome"]["pnl_pips"]
        
        stats[pattern]["total"] += 1
        if success:
            stats[pattern]["success"] += 1
        stats[pattern]["pnl_total"] += pnl
    
    # Calcular tasas
    results = {}
    for pattern, data in stats.items():
        success_rate = (data["success"] / data["total"]) * 100 if data["total"] > 0 else 0
        avg_pnl = data["pnl_total"] / data["total"] if data["total"] > 0 else 0
        
        results[pattern] = {
            "total": data["total"],
            "success": data["success"],
            "success_rate": success_rate,
            "total_pnl": data["pnl_total"],
            "avg_pnl": avg_pnl
        }
    
    return results


def analyze_by_trend_score(records: List[Dict]) -> Dict[str, Dict]:
    """
    Analiza performance por rango de trend_score.
    
    Returns:
        Dict con estadísticas por rango de score
    """
    ranges = {
        "STRONG_BULLISH (≥6)": [],
        "WEAK_BULLISH (1-5)": [],
        "NEUTRAL (-1 to 1)": [],
        "WEAK_BEARISH (-5 to -1)": [],
        "STRONG_BEARISH (≤-6)": []
    }
    
    for record in records:
        score = record["signal"]["trend_score"]
        
        if score >= 6:
            ranges["STRONG_BULLISH (≥6)"].append(record)
        elif score >= 1:
            ranges["WEAK_BULLISH (1-5)"].append(record)
        elif score >= -1:
            ranges["NEUTRAL (-1 to 1)"].append(record)
        elif score >= -5:
            ranges["WEAK_BEARISH (-5 to -1)"].append(record)
        else:
            ranges["STRONG_BEARISH (≤-6)"].append(record)
    
    results = {}
    for range_name, range_records in ranges.items():
        if not range_records:
            continue
        
        total = len(range_records)
        success = sum(1 for r in range_records if r["outcome"]["success"])
        total_pnl = sum(r["outcome"]["pnl_pips"] for r in range_records)
        
        results[range_name] = {
            "total": total,
            "success": success,
            "success_rate": (success / total) * 100,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / total
        }
    
    return results


def analyze_by_confidence(records: List[Dict]) -> Dict[str, Dict]:
    """
    Analiza performance por nivel de confianza del patrón.
    
    Returns:
        Dict con estadísticas por rango de confianza
    """
    ranges = {
        "Alta (≥0.90)": [],
        "Media (0.80-0.89)": [],
        "Baja (0.70-0.79)": []
    }
    
    for record in records:
        confidence = record["signal"]["confidence"]
        
        if confidence >= 0.90:
            ranges["Alta (≥0.90)"].append(record)
        elif confidence >= 0.80:
            ranges["Media (0.80-0.89)"].append(record)
        else:
            ranges["Baja (0.70-0.79)"].append(record)
    
    results = {}
    for range_name, range_records in ranges.items():
        if not range_records:
            continue
        
        total = len(range_records)
        success = sum(1 for r in range_records if r["outcome"]["success"])
        total_pnl = sum(r["outcome"]["pnl_pips"] for r in range_records)
        
        results[range_name] = {
            "total": total,
            "success": success,
            "success_rate": (success / total) * 100,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / total
        }
    
    return results


def print_analysis(title: str, results: Dict[str, Dict]) -> None:
    """
    Imprime análisis en formato tabular.
    
    Args:
        title: Título del análisis
        results: Diccionario con estadísticas
    """
    print(f"\n{'='*80}")
    print(f" {title}")
    print(f"{'='*80}")
    print(f"{'Categoría':<30} {'Total':<8} {'Éxito':<8} {'Tasa %':<10} {'PnL Total':<12} {'PnL Avg':<12}")
    print(f"{'-'*80}")
    
    for category, stats in results.items():
        print(
            f"{category:<30} "
            f"{stats['total']:<8} "
            f"{stats['success']:<8} "
            f"{stats['success_rate']:>6.1f}%   "
            f"{stats['total_pnl']:>9.1f}   "
            f"{stats['avg_pnl']:>9.1f}"
        )


def generate_summary(records: List[Dict]) -> None:
    """
    Genera resumen general del dataset.
    
    Args:
        records: Lista de registros
    """
    if not records:
        print("\n⚠️  No hay registros para analizar")
        return
    
    total = len(records)
    success = sum(1 for r in records if r["outcome"]["success"])
    total_pnl = sum(r["outcome"]["pnl_pips"] for r in records)
    
    # Fechas
    timestamps = [datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) for r in records]
    first_signal = min(timestamps)
    last_signal = max(timestamps)
    duration_days = (last_signal - first_signal).days
    
    print(f"\n{'='*80}")
    print(f" RESUMEN GENERAL DEL DATASET")
    print(f"{'='*80}")
    print(f"📊 Total de señales: {total}")
    print(f"✅ Señales exitosas: {success} ({(success/total)*100:.1f}%)")
    print(f"❌ Señales fallidas: {total - success} ({((total-success)/total)*100:.1f}%)")
    print(f"💰 PnL Total: {total_pnl:+.1f} pips")
    print(f"💰 PnL Promedio: {total_pnl/total:+.1f} pips por señal")
    print(f"📅 Primera señal: {first_signal.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📅 Última señal: {last_signal.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  Duración: {duration_days} días")
    print(f"📈 Frecuencia: {total / max(duration_days, 1):.1f} señales/día")


def main():
    """Función principal."""
    print("\n🔍 Trading Bot - Análisis de Dataset de Backtesting")
    print("="*80)
    
    # Cargar dataset
    records = load_dataset()
    
    if not records:
        return
    
    # Resumen general
    generate_summary(records)
    
    # Análisis por patrón
    pattern_stats = analyze_success_rate_by_pattern(records)
    print_analysis("ANÁLISIS POR PATRÓN", pattern_stats)
    
    # Análisis por trend score
    score_stats = analyze_by_trend_score(records)
    print_analysis("ANÁLISIS POR TREND SCORE", score_stats)
    
    # Análisis por confianza
    confidence_stats = analyze_by_confidence(records)
    print_analysis("ANÁLISIS POR CONFIANZA DEL PATRÓN", confidence_stats)
    
    print(f"\n{'='*80}")
    print("✅ Análisis completado")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
