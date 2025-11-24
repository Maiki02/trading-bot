"""
Base Market Data Service Protocol
===================================
Define la interfaz común que deben implementar todos los proveedores
de datos de mercado (TradingView, IQ Option, etc.).

Author: Trading Bot Architecture Team
"""

from typing import Protocol, Optional, Dict, Any
from datetime import datetime


class MarketDataService(Protocol):
    """
    Protocolo que define la interfaz estándar para proveedores de datos de mercado.
    
    Todos los servicios de datos (TradingView, IQ Option, etc.) deben implementar
    estos métodos para garantizar compatibilidad con el resto del sistema.
    """
    
    def connect(self) -> bool:
        """
        Establece conexión con el proveedor de datos.
        
        Returns:
            bool: True si la conexión fue exitosa, False en caso contrario
        """
        ...
    
    def disconnect(self) -> None:
        """
        Cierra la conexión con el proveedor de datos y libera recursos.
        """
        ...
    
    def get_latest_candle(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene la última vela procesada.
        
        ESTRUCTURA DE RETORNO ESTANDARIZADA:
        {
            'time': datetime,      # Timestamp de la vela (datetime object)
            'open': float,         # Precio de apertura
            'high': float,         # Precio máximo
            'low': float,          # Precio mínimo
            'close': float,        # Precio de cierre
            'volume': float        # Volumen (0 si no disponible)
        }
        
        Returns:
            Optional[Dict[str, Any]]: Diccionario con datos de la vela o None si no hay datos
        """
        ...
    
    def is_connected(self) -> bool:
        """
        Verifica si la conexión está activa.
        
        Returns:
            bool: True si está conectado, False en caso contrario
        """
        ...
