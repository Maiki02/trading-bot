"""
Local Notification Storage Service
===================================
Servicio para almacenar notificaciones localmente cuando SAVE_NOTIFICATIONS_LOCALLY=true.
Guarda imágenes en formato PNG y mensajes en formato JSON.

Estructura de almacenamiento:
- data/notifications/images/    -> Imágenes PNG de los gráficos
- data/notifications/messages.json -> Array con los mensajes

Author: TradingView Pattern Monitor Team
"""

import json
import base64
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

from src.utils.logger import get_logger, log_exception


logger = get_logger(__name__)


class LocalNotificationStorage:
    """
    Servicio para almacenar notificaciones localmente.
    
    Responsabilidades:
    - Guardar imágenes Base64 como archivos PNG
    - Mantener un registro JSON con los mensajes y referencias a las imágenes
    - Gestión automática de directorios
    """
    
    def __init__(self, base_dir: str = "data/notifications"):
        """
        Inicializa el servicio de almacenamiento local.
        
        Args:
            base_dir: Directorio base para almacenamiento (default: "data/notifications")
        """
        self.base_dir = Path(base_dir)
        self.images_dir = self.base_dir / "images"
        self.messages_file = self.base_dir / "messages.json"
        
        # Crear directorios si no existen
        self._ensure_directories()
        
        # Inicializar archivo de mensajes si no existe
        self._ensure_messages_file()
        
        logger.info(
            f"💾 Local Notification Storage inicializado | "
            f"Directorio: {self.base_dir}"
        )
    
    def _ensure_directories(self) -> None:
        """Crea los directorios necesarios si no existen."""
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self.images_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"✅ Directorios verificados: {self.base_dir}")
        except Exception as e:
            log_exception(logger, f"Error creando directorios {self.base_dir}", e)
            raise
    
    def _ensure_messages_file(self) -> None:
        """Inicializa el archivo JSON de mensajes si no existe."""
        try:
            if not self.messages_file.exists():
                with open(self.messages_file, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2)
                logger.debug(f"✅ Archivo de mensajes creado: {self.messages_file}")
        except Exception as e:
            log_exception(logger, f"Error creando archivo de mensajes", e)
            raise
    
    async def save_notification(
        self,
        title: str,
        message: str,
        chart_base64: Optional[str] = None
    ) -> None:
        """
        Guarda una notificación localmente.
        
        Args:
            title: Título del mensaje
            message: Cuerpo del mensaje
            chart_base64: Imagen del gráfico en Base64 (opcional)
        """
        try:
            # Generar nombre único para la imagen usando timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            image_name = None
            
            # Guardar imagen si existe
            if chart_base64:
                image_name = f"chart_{timestamp}.png"
                await self._save_image(chart_base64, image_name)
            
            # Guardar mensaje en el array JSON
            await self._save_message(title, message, image_name, timestamp)
            
            logger.info(
                f"💾 Notificación guardada localmente | "
                f"Imagen: {image_name or 'N/A'} | "
                f"Timestamp: {timestamp}"
            )
            
        except Exception as e:
            log_exception(logger, "Error guardando notificación localmente", e)
            # NO propagar - no queremos detener el bot por errores de storage
    
    async def _save_image(self, base64_data: str, image_name: str) -> None:
        """
        Guarda una imagen Base64 como archivo PNG.
        
        Args:
            base64_data: Datos de la imagen en Base64
            image_name: Nombre del archivo PNG
        """
        try:
            # Decodificar Base64
            image_bytes = base64.b64decode(base64_data)
            
            # Guardar archivo PNG de forma asíncrona
            image_path = self.images_dir / image_name
            await asyncio.to_thread(self._sync_write_image, image_path, image_bytes)
            
            logger.debug(f"✅ Imagen guardada: {image_path}")
            
        except Exception as e:
            log_exception(logger, f"Error guardando imagen {image_name}", e)
            raise
    
    def _sync_write_image(self, path: Path, data: bytes) -> None:
        """
        Escritura síncrona de imagen (ejecutada en thread separado).
        
        Args:
            path: Ruta del archivo
            data: Datos binarios de la imagen
        """
        with open(path, "wb") as f:
            f.write(data)
    
    async def _save_message(
        self,
        title: str,
        message: str,
        image_name: Optional[str],
        timestamp: str
    ) -> None:
        """
        Guarda un mensaje en el array JSON.
        
        Args:
            title: Título del mensaje
            message: Cuerpo del mensaje
            image_name: Nombre de la imagen asociada (opcional)
            timestamp: Timestamp del mensaje
        """
        try:
            # Leer el array actual de mensajes
            messages = await asyncio.to_thread(self._sync_read_messages)
            
            # Agregar nuevo mensaje
            new_message = {
                "timestamp": timestamp,
                "datetime": datetime.now().isoformat(),
                "title": title,
                "message": message,
                "image_name": image_name or ""
            }
            messages.append(new_message)
            
            # Guardar array actualizado
            await asyncio.to_thread(self._sync_write_messages, messages)
            
            logger.debug(f"✅ Mensaje guardado en JSON (total: {len(messages)})")
            
        except Exception as e:
            log_exception(logger, "Error guardando mensaje en JSON", e)
            raise
    
    def _sync_read_messages(self) -> list:
        """
        Lectura síncrona del archivo JSON de mensajes.
        
        Returns:
            List con los mensajes existentes
        """
        try:
            with open(self.messages_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Archivo JSON corrupto, reiniciando: {self.messages_file}")
            return []
        except Exception as e:
            log_exception(logger, "Error leyendo mensajes", e)
            return []
    
    def _sync_write_messages(self, messages: list) -> None:
        """
        Escritura síncrona del archivo JSON de mensajes.
        
        Args:
            messages: Lista de mensajes a guardar
        """
        with open(self.messages_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2, ensure_ascii=False)
    
    def get_stats(self) -> dict:
        """
        Obtiene estadísticas del almacenamiento local.
        
        Returns:
            Dict con estadísticas
        """
        try:
            # Contar imágenes
            images_count = len(list(self.images_dir.glob("*.png")))
            
            # Contar mensajes
            messages = self._sync_read_messages()
            messages_count = len(messages)
            
            # Tamaño del directorio
            total_size = sum(f.stat().st_size for f in self.base_dir.rglob("*") if f.is_file())
            total_size_mb = total_size / (1024 * 1024)
            
            return {
                "images_count": images_count,
                "messages_count": messages_count,
                "total_size_mb": round(total_size_mb, 2),
                "base_dir": str(self.base_dir)
            }
        except Exception as e:
            log_exception(logger, "Error obteniendo estadísticas", e)
            return {
                "images_count": 0,
                "messages_count": 0,
                "total_size_mb": 0,
                "base_dir": str(self.base_dir)
            }
    
    async def close(self) -> None:
        """Cierra el servicio de almacenamiento local."""
        stats = self.get_stats()
        logger.info(
            f"💾 Local Notification Storage cerrando | "
            f"Imágenes: {stats['images_count']} | "
            f"Mensajes: {stats['messages_count']} | "
            f"Tamaño: {stats['total_size_mb']} MB"
        )
