"""
Storage Service - Dataset Persistence Layer
============================================
Capa de persistencia dedicada para almacenar pares {Señal, Resultado}
con formato JSONL para backtesting y análisis de Machine Learning.

Responsabilidades:
- Escritura asíncrona sin bloqueo del Event Loop
- Garantizar integridad de datos (JSONL - una línea por registro)
- Gestión automática de directorios
- Rotación de archivos (opcional para producción)

JSONL Format: Cada línea es un JSON válido independiente.
Ventajas: No corrupción si se interrumpe la escritura, append eficiente.

Author: TradingView Pattern Monitor Team
"""

import asyncio
import json
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from src.utils.logger import get_logger, log_exception


logger = get_logger(__name__)


class StorageService:
    """
    Servicio de almacenamiento para dataset de trading.
    
    Funcionalidades:
    - Escritura asíncrona en formato JSONL
    - Gestión automática de directorios
    - Validación de estructura de datos
    - Logging de operaciones
    """
    
    def __init__(self, data_dir: str = "data", filename: str = "trading_signals_dataset.jsonl"):
        """
        Inicializa el servicio de almacenamiento.
        
        Args:
            data_dir: Directorio raíz para almacenamiento (default: "data")
            filename: Nombre del archivo JSONL (default: "trading_signals_dataset.jsonl")
        """
        self.data_dir = Path(data_dir)
        self.file_path = self.data_dir / filename
        self.records_written = 0
        
        # Crear directorio si no existe
        self._ensure_directory()
        
        logger.info(
            f"💾 Storage Service inicializado | "
            f"Archivo: {self.file_path} | "
            f"Modo: JSONL (append)"
        )
    
    def _ensure_directory(self) -> None:
        """Crea el directorio de datos si no existe."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"✅ Directorio verificado: {self.data_dir}")
        except Exception as e:
            log_exception(logger, f"Error creando directorio {self.data_dir}", e)
            raise
    
    async def save_signal_outcome(self, record: Dict[str, Any]) -> None:
        """
        Guarda un registro de {Señal, Resultado} en formato JSONL.
        
        Estructura esperada del record:
        {
            "timestamp": "ISO8601",
            "signal": {
                "pattern": "SHOOTING_STAR",
                "source": "FX",
                "symbol": "EURUSD",
                "confidence": 0.85,
                "trend": "STRONG_BULLISH",
                "trend_score": 6,
                "is_trend_aligned": false
            },
            "trigger_candle": {
                "timestamp": 1234567890,
                "open": 1.05,
                "high": 1.06,
                "low": 1.04,
                "close": 1.05,
                "volume": 1000
            },
            "outcome_candle": {
                "timestamp": 1234567950,
                "open": 1.05,
                "high": 1.055,
                "low": 1.03,
                "close": 1.03,
                "volume": 1200
            },
            "outcome": {
                "expected_direction": "ROJO",  # Bajista
                "actual_direction": "ROJO",
                "success": true,
                "pnl_pips": 20.0,
                "outcome_timestamp": "ISO8601"
            }
        }
        
        Args:
            record: Diccionario con la estructura completa del registro
        """
        try:
            # Validar estructura mínima
            self._validate_record(record)
            
            # Enriquecer con metadata
            enriched_record = self._enrich_record(record)
            
            # Escribir de forma asíncrona
            await self._write_jsonl(enriched_record)
            
            self.records_written += 1
            
            logger.info(
                f"💾 Registro guardado | "
                f"Patrón: {record['signal']['pattern']} | "
                f"Éxito: {record['outcome']['success']} | "
                f"PnL: {record['outcome']['pnl_pips']:.1f} pips | "
                f"Total registros: {self.records_written}"
            )
            
        except Exception as e:
            log_exception(logger, "Error guardando registro en JSONL", e)
            # NO propagar - no queremos detener el bot por errores de storage
    
    def _validate_record(self, record: Dict[str, Any]) -> None:
        """
        Valida que el registro tenga la estructura mínima requerida.
        
        Args:
            record: Registro a validar
            
        Raises:
            ValueError: Si faltan campos críticos
        """
        required_keys = ["timestamp", "signal", "trigger_candle", "outcome_candle", "outcome"]
        missing_keys = [key for key in required_keys if key not in record]
        
        if missing_keys:
            raise ValueError(f"Registro inválido. Faltan claves: {missing_keys}")
        
        # Validar sub-estructura de signal
        signal_keys = ["pattern", "source", "confidence"]
        missing_signal = [key for key in signal_keys if key not in record["signal"]]
        
        if missing_signal:
            raise ValueError(f"Campo 'signal' inválido. Faltan: {missing_signal}")
        
        # Validar sub-estructura de outcome
        outcome_keys = ["expected_direction", "actual_direction", "success"]
        missing_outcome = [key for key in outcome_keys if key not in record["outcome"]]
        
        if missing_outcome:
            raise ValueError(f"Campo 'outcome' inválido. Faltan: {missing_outcome}")
    
    def _enrich_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enriquece el registro con metadata adicional.
        
        Args:
            record: Registro original
            
        Returns:
            Dict con metadata adicional
        """
        enriched = record.copy()
        
        # Agregar metadata de escritura
        enriched["_metadata"] = {
            "written_at": datetime.utcnow().isoformat() + "Z",
            "record_id": self.records_written + 1,
            "version": "1.0"
        }
        
        return enriched
    
    async def _write_jsonl(self, record: Dict[str, Any]) -> None:
        """
        Escribe un registro en formato JSONL de forma asíncrona.
        
        JSONL: Cada línea es un JSON válido independiente.
        Esto previene corrupción si se interrumpe la escritura.
        
        Args:
            record: Registro a escribir
        """
        # Convertir tipos de NumPy a tipos nativos de Python
        sanitized_record = self._sanitize_numpy_types(record)
        
        # Serializar a JSON (una línea)
        json_line = json.dumps(sanitized_record, ensure_ascii=False) + "\n"
        
        # Escribir de forma asíncrona sin bloquear Event Loop
        await asyncio.to_thread(self._sync_write, json_line)
    
    def _sanitize_numpy_types(self, obj: Any) -> Any:
        """
        Convierte recursivamente tipos de NumPy a tipos nativos de Python.
        
        Args:
            obj: Objeto a sanitizar (puede ser dict, list, o valor primitivo)
            
        Returns:
            Objeto con tipos nativos de Python compatibles con JSON
        """
        if isinstance(obj, dict):
            return {key: self._sanitize_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_numpy_types(item) for item in obj]
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, (np.int_, np.intc, np.intp, np.int8, np.int16, np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.float_, np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj
    
    def _sync_write(self, json_line: str) -> None:
        """
        Escritura síncrona (ejecutada en thread separado).
        
        Args:
            json_line: Línea JSON a escribir
        """
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(json_line)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del servicio de almacenamiento.
        
        Returns:
            Dict con estadísticas de uso
        """
        try:
            file_size = self.file_path.stat().st_size if self.file_path.exists() else 0
            
            return {
                "records_written": self.records_written,
                "file_path": str(self.file_path),
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "file_exists": self.file_path.exists()
            }
        except Exception as e:
            log_exception(logger, "Error obteniendo estadísticas de storage", e)
            return {"error": str(e)}
    
    async def close(self) -> None:
        """
        Cierra el servicio de almacenamiento.
        Principalmente para logging y futura extensión.
        """
        stats = self.get_stats()
        logger.info(
            f"💾 Storage Service cerrando | "
            f"Registros escritos: {stats['records_written']} | "
            f"Tamaño archivo: {stats['file_size_mb']} MB"
        )
