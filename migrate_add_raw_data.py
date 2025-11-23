"""
Script de Migración - Agregar raw_data a Registros Antiguos
=============================================================
Este script actualiza registros antiguos del dataset JSONL que no tienen
el campo 'raw_data', agregándolo con valores estimados basados en los
datos de 'signal' existentes.

⚠️ IMPORTANTE: Este script crea un backup automático antes de modificar.

Ejecutar con:
    python migrate_add_raw_data.py
"""
import json
import shutil
from pathlib import Path
from datetime import datetime


def backup_dataset(original_path: Path) -> Path:
    """
    Crea un backup del dataset original.
    
    Args:
        original_path: Ruta al archivo original
        
    Returns:
        Path: Ruta al backup creado
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = original_path.parent / f"{original_path.stem}_backup_{timestamp}.jsonl"
    
    shutil.copy2(original_path, backup_path)
    print(f"✅ Backup creado: {backup_path}")
    
    return backup_path


def migrate_dataset(dataset_path: Path) -> None:
    """
    Migra el dataset agregando 'raw_data' a registros antiguos.
    
    Args:
        dataset_path: Ruta al archivo JSONL
    """
    if not dataset_path.exists():
        print(f"❌ Dataset no encontrado: {dataset_path}")
        return
    
    print(f"📂 Procesando: {dataset_path}")
    
    # Crear backup
    backup_path = backup_dataset(dataset_path)
    
    # Leer todos los registros
    records = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                print(f"⚠️  Línea {line_num} inválida, omitida: {e}")
    
    print(f"📊 Total registros cargados: {len(records)}")
    
    # Migrar registros
    migrated_count = 0
    skipped_count = 0
    
    for idx, record in enumerate(records, 1):
        # Verificar si ya tiene raw_data
        if 'raw_data' in record:
            skipped_count += 1
            continue
        
        # Extraer datos de trigger_candle y signal
        try:
            trigger_candle = record.get('trigger_candle', {})
            signal = record.get('signal', {})
            
            # Intentar estimar EMAs desde el contexto (si no están disponibles, usar valores NaN)
            # IMPORTANTE: Estos son valores ESTIMADOS, no datos reales
            # El StatisticsService detectará NaN y no usará estos registros para recalcular scores
            
            raw_data = {
                "ema_200": None,  # No disponible en registros antiguos
                "ema_50": None,
                "ema_30": None,
                "ema_20": None,
                "close": trigger_candle.get('close'),
                "open": trigger_candle.get('open'),
                "algo_version": "v1.0_migrated"  # Marcar como migrado
            }
            
            # Agregar raw_data al registro
            record['raw_data'] = raw_data
            migrated_count += 1
            
            print(f"✓ Registro {idx}/{len(records)} migrado")
            
        except Exception as e:
            print(f"⚠️  Error migrando registro {idx}: {e}")
            skipped_count += 1
    
    # Escribir dataset migrado
    print(f"\n💾 Escribiendo dataset migrado...")
    with open(dataset_path, 'w', encoding='utf-8') as f:
        for record in records:
            json_line = json.dumps(record, ensure_ascii=False)
            f.write(json_line + '\n')
    
    print(f"\n{'=' * 60}")
    print(f"✅ MIGRACIÓN COMPLETADA")
    print(f"{'=' * 60}")
    print(f"Total registros: {len(records)}")
    print(f"Migrados: {migrated_count}")
    print(f"Ya tenían raw_data: {skipped_count}")
    print(f"\n⚠️  NOTA IMPORTANTE:")
    print(f"Los registros migrados tienen raw_data.algo_version='v1.0_migrated'")
    print(f"y valores None para EMAs (no disponibles en registros antiguos).")
    print(f"StatisticsService NO usará estos registros para recalcular scores.")
    print(f"\nSolo los registros nuevos (con EMAs completas) se usarán para")
    print(f"análisis de probabilidad con scores recalculados.")
    print(f"\n📂 Backup guardado en: {backup_path}")


def main():
    print("=" * 60)
    print("SCRIPT DE MIGRACIÓN - Agregar raw_data")
    print("=" * 60)
    print("\nEste script agrega el campo 'raw_data' a registros antiguos.")
    print("Los registros migrados tendrán valores None para EMAs.")
    print("\n⚠️  SE CREARÁ UN BACKUP AUTOMÁTICAMENTE\n")
    
    response = input("¿Continuar con la migración? (s/n): ").lower().strip()
    
    if response != 's':
        print("❌ Migración cancelada")
        return
    
    dataset_path = Path("data/trading_signals_dataset.jsonl")
    migrate_dataset(dataset_path)


if __name__ == "__main__":
    main()
