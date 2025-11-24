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
        
        Estructura esperada del record (OPTIMIZADA - DATOS CRUDOS):
        {
            "timestamp": int,
            "source": "BINANCE",
            "symbol": "BTCUSDT",
            "pattern_candle": {
                "timestamp": int,
                "open": float,
                "high": float,
                "low": float,
                "close": float,
                "volume": float,
                "pattern": "SHOOTING_STAR",
                "confidence": float
            },
            "emas": {
                "ema_200": float,
                "ema_50": float,
                "ema_30": float,
                "ema_20": float,
                "alignment": "BULLISH_ALIGNED|BEARISH_ALIGNED|MIXED|...",
                "trend_score": int
            },
            "outcome_candle": {
                "timestamp": int,
                "open": float,
                "high": float,
                "low": float,
                "close": float,
                "volume": float,
                "direction": "VERDE|ROJA|DOJI"
            },
            "outcome": {
                "expected_direction": "VERDE|ROJA",
                "actual_direction": "VERDE|ROJA|DOJI",
                "success": bool
            },
            "metadata": {
                "algo_version": "v2.0",
                "created_at": "ISO8601"
            }
        }
        
        Args:
            record: Diccionario con la estructura completa del registro
        """
        try:
            # Validar estructura mínima
            self._validate_record(record)
            
            # Enriquecer con metadata adicional
            enriched_record = self._enrich_record(record)
            
            # Escribir de forma asíncrona
            await self._write_jsonl(enriched_record)
            
            self.records_written += 1
            
            # Logging adaptado a v4.1
            pattern = record.get('pattern_candle', {}).get('pattern', record.get('pattern_name', 'UNKNOWN'))
            outcome = record.get('outcome', 'UNKNOWN')
            confidence = record.get('pattern_candle', {}).get('confidence', record.get('pattern_confidence', 0.0))
            
            logger.info(
                f"💾 Registro guardado | "
                f"Patrón: {pattern} | "
                f"Outcome: {outcome} | "
                f"Confianza: {confidence:.2f} | "
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
        # Validación flexible: solo verificar campos esenciales
        required_keys = ["timestamp", "source", "symbol", "pattern_candle", "outcome_candle", "metadata"]
        missing_keys = [key for key in required_keys if key not in record]
        
        if missing_keys:
            raise ValueError(f"Registro inválido. Faltan claves: {missing_keys}")
        
        # Validar sub-estructura de pattern_candle (mínima)
        pattern_keys = ["timestamp", "pattern", "confidence"]
        missing_pattern = [key for key in pattern_keys if key not in record["pattern_candle"]]
        
        if missing_pattern:
            raise ValueError(f"Campo 'pattern_candle' inválido. Faltan: {missing_pattern}")
        
        # Validar sub-estructura de outcome_candle (mínima)
        outcome_candle_keys = ["timestamp", "direction"]
        missing_outcome_candle = [key for key in outcome_candle_keys if key not in record["outcome_candle"]]
        
        if missing_outcome_candle:
            raise ValueError(f"Campo 'outcome_candle' inválido. Faltan: {missing_outcome_candle}")
        
        # Validar sub-estructura de metadata
        metadata_keys = ["algo_version"]
        missing_metadata = [key for key in metadata_keys if key not in record["metadata"]]
        
        if missing_metadata:
            raise ValueError(f"Campo 'metadata' inválido. Faltan: {missing_metadata}")
    
    def _enrich_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enriquece el registro con metadata adicional.
        
        Args:
            record: Registro original
            
        Returns:
            Dict con metadata adicional
        """
        enriched = record.copy()
        
        # Agregar metadata de escritura (sin duplicar metadata del usuario)
        enriched["_storage_metadata"] = {
            "written_at": datetime.utcnow().isoformat() + "Z",
            "record_id": self.records_written + 1
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
