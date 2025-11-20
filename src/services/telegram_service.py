"""
Telegram Service - Dual-Source Alert Notification System
=========================================================
Gestiona el envío de alertas a través de la API de Telegram.
Implementa la lógica de "Dual Source" con ventana temporal para
diferenciar entre alertas estándar y alertas confirmadas.

Author: TradingView Pattern Monitor Team
"""

import asyncio
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import aiohttp

from config import Config
from src.services.analysis_service import PatternSignal
from src.utils.logger import get_logger, log_exception


logger = get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PendingAlert:
    """Alerta pendiente esperando confirmación de segunda fuente."""
    signal: PatternSignal
    received_at: datetime
    sources: List[str] = field(default_factory=list)
    
    def is_expired(self, window_seconds: float) -> bool:
        """Verifica si la ventana de confirmación ha expirado."""
        elapsed = (datetime.now() - self.received_at).total_seconds()
        return elapsed > window_seconds


@dataclass
class AlertMessage:
    """Estructura de un mensaje de alerta."""
    title: str
    body: str
    alert_type: str  # "STANDARD" o "STRONG"
    timestamp: datetime


# =============================================================================
# TELEGRAM SERVICE
# =============================================================================

class TelegramService:
    """
    Servicio de notificaciones con lógica Dual-Source.
    
    Responsabilidades:
    - Recibir señales del Analysis Service
    - Implementar ventana de confirmación temporal
    - Enviar alertas a Telegram vía API REST
    - Diferenciar entre alertas estándar y fuertes
    """
    
    def __init__(self):
        """Inicializa el servicio de notificaciones."""
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Configuración
        self.api_url = Config.TELEGRAM.api_url
        self.api_key = Config.TELEGRAM.api_key
        self.subscription = Config.TELEGRAM.subscription
        self.confirmation_window = Config.DUAL_SOURCE_WINDOW
        
        # Buffer de alertas pendientes (key: symbol_timestamp)
        self.pending_alerts: Dict[str, PendingAlert] = {}
        
        # Tarea de limpieza de alertas expiradas
        self.cleanup_task: Optional[asyncio.Task] = None
        
        logger.info(
            f"📱 Telegram Service initialized "
            f"(Subscription: {self.subscription}, Window: {self.confirmation_window}s)"
        )
    
    async def start(self) -> None:
        """Inicia el servicio de notificaciones."""
        self.session = aiohttp.ClientSession()
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_alerts())
        logger.info("✅ Telegram Service started")
    
    async def stop(self) -> None:
        """Detiene el servicio de notificaciones."""
        logger.info("🛑 Stopping Telegram Service...")
        
        # Cancelar tarea de limpieza
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Cerrar sesión HTTP
        if self.session and not self.session.closed:
            await self.session.close()
        
        logger.info("✅ Telegram Service stopped")
    
    async def handle_pattern_signal(self, signal: PatternSignal) -> None:
        """
        Procesa una señal de patrón del Analysis Service.
        
        Implementa la lógica Dual-Source:
        1. Si es la primera fuente: Espera confirmación durante la ventana temporal
        2. Si es la segunda fuente (dentro de la ventana): Envía alerta FUERTE
        3. Si expira la ventana: Envía alerta ESTÁNDAR
        
        Args:
            signal: Señal de patrón detectada
        """
        alert_key = f"{signal.symbol}_{signal.timestamp}"
        
        logger.debug(
            f"📩 Signal received from {signal.source} | "
            f"{signal.pattern} @ {signal.timestamp}"
        )
        
        # Verificar si ya hay una alerta pendiente para este timestamp
        if alert_key in self.pending_alerts:
            pending = self.pending_alerts[alert_key]
            
            # Verificar que no sea de la misma fuente (duplicado)
            if signal.source in pending.sources:
                logger.debug(f"⚠️  Duplicate signal from {signal.source}. Ignoring.")
                return
            
            # Verificar si aún está dentro de la ventana de confirmación
            if not pending.is_expired(self.confirmation_window):
                # ¡CONFIRMACIÓN DUAL-SOURCE!
                pending.sources.append(signal.source)
                
                logger.info(
                    f"🔥 DUAL-SOURCE CONFIRMATION | {signal.symbol} | "
                    f"Sources: {', '.join(pending.sources)} | "
                    f"Window: {self.confirmation_window}s"
                )
                
                # Enviar alerta FUERTE
                await self._send_strong_alert(pending.signal, signal)
                
                # Eliminar del buffer de pendientes
                del self.pending_alerts[alert_key]
                return
            else:
                # La ventana expiró, enviar alerta estándar de la pendiente
                logger.debug(
                    f"⏱️  Confirmation window expired for {alert_key}. "
                    "Sending standard alert for previous signal."
                )
                await self._send_standard_alert(pending.signal)
                del self.pending_alerts[alert_key]
        
        # Nueva alerta: Agregar al buffer de pendientes
        self.pending_alerts[alert_key] = PendingAlert(
            signal=signal,
            received_at=datetime.now(),
            sources=[signal.source]
        )
        
        logger.debug(
            f"⏳ Alert pending confirmation | {signal.source} | "
            f"Waiting {self.confirmation_window}s for second source..."
        )
        
        # Programar envío de alerta estándar si no hay confirmación
        asyncio.create_task(
            self._wait_and_send_standard(alert_key, self.confirmation_window)
        )
    
    async def _wait_and_send_standard(self, alert_key: str, delay: float) -> None:
        """
        Espera el tiempo de confirmación y envía alerta estándar si no hay confirmación.
        
        Args:
            alert_key: Clave de la alerta en el buffer
            delay: Tiempo de espera en segundos
        """
        await asyncio.sleep(delay)
        
        # Verificar si la alerta aún está pendiente
        if alert_key in self.pending_alerts:
            pending = self.pending_alerts[alert_key]
            
            logger.info(
                f"📤 No confirmation received within {delay}s. "
                f"Sending STANDARD alert for {alert_key}."
            )
            
            await self._send_standard_alert(pending.signal)
            del self.pending_alerts[alert_key]
    
    async def _send_standard_alert(self, signal: PatternSignal) -> None:
        """
        Envía una alerta estándar (una sola fuente).
        
        Args:
            signal: Señal de patrón detectada
        """
        message = self._format_standard_message(signal)
        await self._send_to_telegram(message, signal.chart_base64)
    
    async def _send_strong_alert(
        self,
        signal1: PatternSignal,
        signal2: PatternSignal
    ) -> None:
        """
        Envía una alerta fuerte (confirmada por ambas fuentes).
        
        Args:
            signal1: Primera señal
            signal2: Segunda señal
        """
        message = self._format_strong_message(signal1, signal2)
        # Usar el gráfico del primer signal o el segundo si el primero no tiene
        chart_base64 = signal1.chart_base64 or signal2.chart_base64
        await self._send_to_telegram(message, chart_base64)
    
    def _format_standard_message(self, signal: PatternSignal) -> AlertMessage:
        """
        Formatea un mensaje de alerta estándar.
        
        Args:
            signal: Señal de patrón
            
        Returns:
            AlertMessage: Mensaje formateado
        """
        timestamp_str = datetime.fromtimestamp(signal.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        
        title = f"⚠️ POSIBLE OPORTUNIDAD | {signal.symbol}"
        
        body = (
            f"📊 **Fuente:** {signal.source}\n"
            f"📈 **Patrón:** {signal.pattern}\n"
            f"🕒 **Timestamp:** {timestamp_str}\n"
            f"💰 **OHLC:** O={signal.candle.open:.5f} H={signal.candle.high:.5f} "
            f"L={signal.candle.low:.5f} C={signal.candle.close:.5f}\n"
            f"📉 **EMA 200:** {signal.ema_200:.5f}\n"
            f"🎯 **Tendencia:** {signal.trend}\n"
            f"✨ **Confianza:** {signal.confidence:.0%}\n\n"
            f"⚡ *Verificar gráfico manualmente antes de operar.*"
        )
        
        return AlertMessage(
            title=title,
            body=body,
            alert_type="STANDARD",
            timestamp=datetime.now()
        )
    
    def _format_strong_message(
        self,
        signal1: PatternSignal,
        signal2: PatternSignal
    ) -> AlertMessage:
        """
        Formatea un mensaje de alerta fuerte (confirmación dual).
        
        Args:
            signal1: Primera señal
            signal2: Segunda señal
            
        Returns:
            AlertMessage: Mensaje formateado
        """
        timestamp_str = datetime.fromtimestamp(signal1.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        avg_confidence = (signal1.confidence + signal2.confidence) / 2
        
        title = f"🔥 ALERTA CONFIRMADA | {signal1.symbol}"
        
        body = (
            f"🎯 **CONFIRMACIÓN DUAL-SOURCE**\n"
            f"📊 **Fuentes:** {signal1.source} + {signal2.source}\n"
            f"📈 **Patrón:** {signal1.pattern}\n"
            f"🕒 **Timestamp:** {timestamp_str}\n\n"
            f"**{signal1.source}:**\n"
            f"  • OHLC: O={signal1.candle.open:.5f} H={signal1.candle.high:.5f} "
            f"L={signal1.candle.low:.5f} C={signal1.candle.close:.5f}\n"
            f"  • EMA 200: {signal1.ema_200:.5f}\n"
            f"  • Confianza: {signal1.confidence:.0%}\n\n"
            f"**{signal2.source}:**\n"
            f"  • OHLC: O={signal2.candle.open:.5f} H={signal2.candle.high:.5f} "
            f"L={signal2.candle.low:.5f} C={signal2.candle.close:.5f}\n"
            f"  • EMA 200: {signal2.ema_200:.5f}\n"
            f"  • Confianza: {signal2.confidence:.0%}\n\n"
            f"📉 **Tendencia:** {signal1.trend}\n"
            f"✨ **Confianza Promedio:** {avg_confidence:.0%}\n\n"
            f"🚀 *Alta probabilidad. Revisar retroceso del 50% en primeros 30s de la siguiente vela.*"
        )
        
        return AlertMessage(
            title=title,
            body=body,
            alert_type="STRONG",
            timestamp=datetime.now()
        )
    
    async def _send_to_telegram(self, message: AlertMessage, chart_base64: Optional[str] = None) -> None:
        """
        Envía un mensaje a la API de Telegram usando el formato broadcast con imagen.
        
        Args:
            message: Mensaje a enviar
            chart_base64: Imagen del gráfico codificada en Base64 (opcional)
        """
        if not self.session:
            logger.error("❌ Cannot send message: HTTP session not initialized")
            return
        
        # Formato del payload según el nuevo formato con image_base64
        payload = {
            "first_message": message.title,
            "image_base64": chart_base64 if chart_base64 else "",
            "entries": [
                {
                    "subscription": self.subscription,
                    "message": message.body
                }
            ]
        }
        
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        try:
            logger.info(f"📤 Sending {message.alert_type} alert to Telegram broadcast...")
            if chart_base64:
                logger.debug(f"📊 Including chart image ({len(chart_base64)} bytes Base64)")
            else:
                logger.debug("📊 No chart image included")
            
            async with self.session.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    logger.info(f"✅ Alert sent successfully ({message.alert_type})")
                else:
                    error_text = await response.text()
                    logger.error(
                        f"❌ Failed to send alert. Status: {response.status}, "
                        f"Response: {error_text}"
                    )
        
        except asyncio.TimeoutError:
            logger.error("❌ Telegram API request timeout")
        except aiohttp.ClientError as e:
            log_exception(logger, "Telegram API request failed", e)
        except Exception as e:
            log_exception(logger, "Unexpected error sending alert", e)
    
    async def _cleanup_expired_alerts(self) -> None:
        """
        Tarea periódica para limpiar alertas expiradas del buffer.
        """
        try:
            while True:
                await asyncio.sleep(self.confirmation_window + 1)
                
                # Identificar alertas expiradas
                expired_keys = [
                    key for key, alert in self.pending_alerts.items()
                    if alert.is_expired(self.confirmation_window)
                ]
                
                if expired_keys:
                    logger.debug(
                        f"🧹 Cleaning up {len(expired_keys)} expired alert(s) from buffer"
                    )
                    for key in expired_keys:
                        del self.pending_alerts[key]
        
        except asyncio.CancelledError:
            logger.debug("Cleanup task cancelled")
        except Exception as e:
            log_exception(logger, "Error in cleanup task", e)
