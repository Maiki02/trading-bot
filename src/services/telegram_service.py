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
import math
import numpy as np

from config import Config
from src.logic.analysis_service import PatternSignal
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
            f"📱 Telegram Service inicializado "
            f"(Suscripción: {self.subscription}, Ventana: {self.confirmation_window}s)"
        )
    
    async def start(self) -> None:
        """Inicia el servicio de notificaciones."""
        self.session = aiohttp.ClientSession()
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_alerts())
        logger.info("✅ Telegram Service iniciado")
    
    async def stop(self) -> None:
        """Detiene el servicio de notificaciones."""
        logger.info("🛑 Deteniendo Telegram Service...")
        
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
        
        logger.info("✅ Telegram Service detenido")
    
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
            f"📩 Señal recibida de {signal.source} | "
            f"{signal.pattern} @ {signal.timestamp}"
        )
        
        # Verificar si ya hay una alerta pendiente para este timestamp
        if alert_key in self.pending_alerts:
            pending = self.pending_alerts[alert_key]
            
            # Verificar que no sea de la misma fuente (duplicado)
            if signal.source in pending.sources:
                logger.debug(f"⚠️  Señal duplicada de {signal.source}. Ignorando.")
                return
            
            # Verificar si aún está dentro de la ventana de confirmación
            if not pending.is_expired(self.confirmation_window):
                # ¡CONFIRMACIÓN DUAL-SOURCE!
                pending.sources.append(signal.source)
                
                logger.info(
                    f"🔥 CONFIRMACIÓN DUAL-SOURCE | {signal.symbol} | "
                    f"Fuentes: {', '.join(pending.sources)} | "
                    f"Ventana: {self.confirmation_window}s"
                )
                
                # Enviar alerta FUERTE
                await self._send_strong_alert(pending.signal, signal)
                
                # Eliminar del buffer de pendientes
                del self.pending_alerts[alert_key]
                return
            else:
                # La ventana expiró, enviar alerta estándar de la pendiente
                logger.debug(
                    f"⏱️  Ventana de confirmación expirada para {alert_key}. "
                    "Enviando alerta estándar de la señal anterior."
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
            f"⏳ Alerta pendiente de confirmación | {signal.source} | "
            f"Esperando {self.confirmation_window}s por segunda fuente..."
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
                f"📤 No se recibió confirmación en {delay}s. "
                f"Enviando alerta ESTÁNDAR para {alert_key}."
            )
            
            await self._send_standard_alert(pending.signal)
            # Verificar nuevamente antes de eliminar (puede haber sido limpiado)
            if alert_key in self.pending_alerts:
                del self.pending_alerts[alert_key]
    
    async def _send_standard_alert(self, signal: PatternSignal) -> None:
        """
        Envía una alerta estándar (una sola fuente).
        
        Args:
            signal: Señal de patrón detectada
        """
        message = self._format_standard_message(signal)
        # Solo enviar gráfico si está habilitado en configuración
        chart = signal.chart_base64 if Config.TELEGRAM.send_charts else None
        await self._send_to_telegram(message, chart)
    
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
        # Solo enviar si está habilitado en configuración
        chart = None
        if Config.TELEGRAM.send_charts:
            chart = signal1.chart_base64 or signal2.chart_base64
        await self._send_to_telegram(message, chart)
    
    def _format_standard_message(self, signal: PatternSignal) -> AlertMessage:
        """
        Formatea un mensaje de alerta estándar.
        
        Args:
            signal: Señal de patrón
            
        Returns:
            AlertMessage: Mensaje formateado
        """
        timestamp_str = datetime.fromtimestamp(signal.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        
        # Determinar tipo de alerta basado en tendencia y patrón
        # ALERTA FUERTE: Patrón de reversión alineado con tendencia fuerte
        # ADVERTENCIA: Patrón de reversión en tendencia débil/neutral
        # DETECCIÓN: Solo informativo
        
        is_strong_bullish = signal.trend in ["STRONG_BULLISH", "WEAK_BULLISH"]
        is_strong_bearish = signal.trend in ["STRONG_BEARISH", "WEAK_BEARISH"]
        
        # Caso 1: ALERTA FUERTE - Reversión bajista en tendencia alcista
        if is_strong_bullish and signal.pattern == "SHOOTING_STAR":
            title = f"🔴 ALERTA FUERTE | {signal.symbol}\nAlta probabilidad de apertura BAJISTA\n"
        # Caso 2: ALERTA FUERTE - Reversión alcista en tendencia bajista
        elif is_strong_bearish and signal.pattern == "HAMMER":
            title = f"🟢 ALERTA FUERTE | {signal.symbol}\nAlta probabilidad de apertura ALCISTA\n"
        # Caso 3: AVISO - Martillo invertido en tendencia alcista (debilitamiento)
        elif is_strong_bullish and signal.pattern == "INVERTED_HAMMER":
            title = f"⚠️ AVISO | {signal.symbol}\nPosible debilitamiento alcista\n"
        # Caso 4: AVISO - Hombre colgado en tendencia bajista (debilitamiento)
        elif is_strong_bearish and signal.pattern == "HANGING_MAN":
            title = f"⚠️ AVISO | {signal.symbol}\nPosible debilitamiento bajista\n"
        # Caso 5: DETECCIÓN - Resto de casos (informativo)
        else:
            title = f"📊 PATRÓN DETECTADO | {signal.symbol}\nSolo informativo\n"
        
        # Formatear EMAs (mostrar N/A si no están disponibles)
        import math
        ema_20_str = f"{signal.ema_20:.5f}" if not math.isnan(signal.ema_20) else "N/A"
        ema_30_str = f"{signal.ema_30:.5f}" if not math.isnan(signal.ema_30) else "N/A"
        ema_50_str = f"{signal.ema_50:.5f}" if not math.isnan(signal.ema_50) else "N/A"
        ema_100_str = f"{signal.ema_100:.5f}" if not math.isnan(signal.ema_100) else "N/A"
        
        # Determinar estructura de EMAs para mensaje
        if not math.isnan(signal.ema_20) and not math.isnan(signal.ema_200):
            if signal.candle.close > signal.ema_20 > signal.ema_200:
                estructura = f"Precio > EMA20 > EMA200 (Alineación alcista)"
            elif signal.candle.close < signal.ema_20 < signal.ema_200:
                estructura = f"Precio < EMA20 < EMA200 (Alineación bajista)"
            else:
                estructura = f"EMAs mixtas (Sin alineación clara)"
        else:
            estructura = "Datos insuficientes"
        
        # Determinar interpretación de tendencia
        if signal.trend_score >= 6:
            trend_interpretation = "Tendencia alcista muy fuerte"
        elif signal.trend_score >= 1:
            trend_interpretation = "Tendencia alcista débil"
        elif signal.trend_score >= -1:
            trend_interpretation = "Sin tendencia clara (Mercado lateral)"
        elif signal.trend_score >= -5:
            trend_interpretation = "Tendencia bajista débil"
        else:
            trend_interpretation = "Tendencia bajista muy fuerte"
        
        # Cuerpo del mensaje estructurado
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 INFORMACIÓN DE LA VELA\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 Fuente: {signal.source}\n"
            f"🔹 Patrón: {signal.pattern}\n"
            f"🔹 Timestamp: {timestamp_str}\n"
            f"🔹 Apertura: {signal.candle.open:.5f}\n"
            f"🔹 Máximo: {signal.candle.high:.5f}\n"
            f"🔹 Mínimo: {signal.candle.low:.5f}\n"
            f"🔹 Cierre: {signal.candle.close:.5f}\n"
            f"🔹 Confianza del Patrón: {signal.confidence:.0%}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📉 ANÁLISIS DE EMAS\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 EMA 20: {ema_20_str}\n"
            f"🔹 EMA 30: {ema_30_str}\n"
            f"🔹 EMA 50: {ema_50_str}\n"
            f"🔹 EMA 100: {ema_100_str}\n"
            f"🔹 EMA 200: {signal.ema_200:.5f}\n"
            f"🔹 Estructura: {estructura}\n"
            f"🔹 Alineación: {'✓ Confirmada' if signal.is_trend_aligned else '✗ No confirmada'}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 ANÁLISIS DE TENDENCIA\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 Estado: {signal.trend}\n"
            f"🔹 Score: {signal.trend_score:+d}/10\n"
            f"🔹 Interpretación: {trend_interpretation}\n\n"
            f"⚡ IMPORTANTE: Verificar gráfico y contexto de mercado antes de operar."
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
        Formatea un mensaje de alerta fuerte (confirmada por ambas fuentes).
        
        Args:
            signal1: Primera señal
            signal2: Segunda señal
            
        Returns:
            AlertMessage: Mensaje formateado
        """
        timestamp_str = datetime.fromtimestamp(signal1.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        avg_confidence = (signal1.confidence + signal2.confidence) / 2
        
        title = f"🔥 ALERTA CONFIRMADA | {signal1.symbol}"
        
        # Formatear EMAs de ambas señales
        import math
        
        # Signal 1 EMAs
        ema1_20 = f"{signal1.ema_20:.5f}" if not math.isnan(signal1.ema_20) else "N/A"
        ema1_30 = f"{signal1.ema_30:.5f}" if not math.isnan(signal1.ema_30) else "N/A"
        ema1_50 = f"{signal1.ema_50:.5f}" if not math.isnan(signal1.ema_50) else "N/A"
        ema1_100 = f"{signal1.ema_100:.5f}" if not math.isnan(signal1.ema_100) else "N/A"
        
        # Signal 2 EMAs
        ema2_20 = f"{signal2.ema_20:.5f}" if not math.isnan(signal2.ema_20) else "N/A"
        ema2_30 = f"{signal2.ema_30:.5f}" if not math.isnan(signal2.ema_30) else "N/A"
        ema2_50 = f"{signal2.ema_50:.5f}" if not math.isnan(signal2.ema_50) else "N/A"
        ema2_100 = f"{signal2.ema_100:.5f}" if not math.isnan(signal2.ema_100) else "N/A"
        
        # Determinar estructura de EMAs promedio
        avg_ema_20 = (signal1.ema_20 + signal2.ema_20) / 2 if not math.isnan(signal1.ema_20) and not math.isnan(signal2.ema_20) else np.nan
        avg_ema_200 = (signal1.ema_200 + signal2.ema_200) / 2
        avg_close = (signal1.candle.close + signal2.candle.close) / 2
        
        if not math.isnan(avg_ema_20):
            if avg_close > avg_ema_20 > avg_ema_200:
                estructura = f"Precio > EMA20 > EMA200 (Alcista fuerte)"
            elif avg_close < avg_ema_20 < avg_ema_200:
                estructura = f"Precio < EMA20 < EMA200 (Bajista fuerte)"
            else:
                estructura = f"EMAs mixtas"
        else:
            estructura = "Datos insuficientes"
        
        body = f"🎯 CONFIRMACIÓN DUAL-SOURCE\n📊 Fuentes: {signal1.source} + {signal2.source}\n📈 Patrón: {signal1.pattern}\n🕒 Timestamp: {timestamp_str}\n\n{signal1.source}:\n  • Apertura: {signal1.candle.open:.5f}\n  • Máximo: {signal1.candle.high:.5f}\n  • Mínimo: {signal1.candle.low:.5f}\n  • Cierre: {signal1.candle.close:.5f}\n  • EMAs: 20={ema1_20} | 30={ema1_30} | 50={ema1_50} | 100={ema1_100} | 200={signal1.ema_200:.5f}\n  • Tendencia: {signal1.trend} (Score: {signal1.trend_score:+d})\n  • Confianza: {signal1.confidence:.0%}\n\n{signal2.source}:\n  • Apertura: {signal2.candle.open:.5f}\n  • Máximo: {signal2.candle.high:.5f}\n  • Mínimo: {signal2.candle.low:.5f}\n  • Cierre: {signal2.candle.close:.5f}\n  • EMAs: 20={ema2_20} | 30={ema2_30} | 50={ema2_50} | 100={ema2_100} | 200={signal2.ema_200:.5f}\n  • Tendencia: {signal2.trend} (Score: {signal2.trend_score:+d})\n  • Confianza: {signal2.confidence:.0%}\n\n📐 Estructura Promedio: {estructura}\n🔗 Alineación: {signal1.source}={'✓' if signal1.is_trend_aligned else '✗'} | {signal2.source}={'✓' if signal2.is_trend_aligned else '✗'}\n✨ Confianza Promedio: {avg_confidence:.0%}\n\n🚀 Alta probabilidad. Revisar retroceso del 50% en primeros 30s de la siguiente vela."
        
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
            logger.error("❌ No se puede enviar mensaje: Sesión HTTP no inicializada")
            return
        
        # Formato del payload según el nuevo formato con image_base64
        payload = {
            "first_message": message.title,
            "image_base64": chart_base64 if chart_base64 else "",
            #"message_type": "standard",
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

        logger.info("🔔 MENSAJE LISTO PARA ENVIAR | Preparando envío de alerta a Telegram")

        try:
            chart_status = 'SÍ' if chart_base64 else 'NO'
            chart_size = len(chart_base64) if chart_base64 else 0
            
            logger.info(
                f"\n{'='*80}\n"
                f"📤 INICIANDO PETICIÓN HTTP A TELEGRAM\n"
                f"{'='*80}\n"
                f"🔹 URL: {self.api_url}\n"
                f"🔹 Tipo Alerta: {message.alert_type}\n"
                f"🔹 Título: {message.title}\n"
                f"🔹 Gráfico Incluido: {chart_status}\n"
                f"🔹 Tamaño Gráfico: {chart_size} bytes\n"
                f"🔹 Suscripción: {self.subscription}\n"
                f"{'='*80}"
            )
            
            async with self.session.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)  # Aumentado para múltiples usuarios
            ) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    logger.info(
                        f"\n{'='*80}\n"
                        f"✅ PETICIÓN HTTP EXITOSA\n"
                        f"{'='*80}\n"
                        f"🔹 Estado HTTP: {response.status}\n"
                        f"🔹 Tipo Alerta: {message.alert_type}\n"
                        f"🔹 Respuesta: {response_text[:200]}\n"
                        f"{'='*80}"
                    )
                else:
                    logger.error(
                        f"\n{'='*80}\n"
                        f"❌ PETICIÓN HTTP FALLÓ\n"
                        f"{'='*80}\n"
                        f"🔹 Estado HTTP: {response.status}\n"
                        f"🔹 URL: {self.api_url}\n"
                        f"🔹 Respuesta: {response_text}\n"
                        f"🔹 Headers Enviados: {headers}\n"
                        f"{'='*80}"
                    )
        
        except asyncio.TimeoutError:
            logger.error("❌ Timeout en solicitud a Telegram API")
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
                        f"🧹 Limpiando {len(expired_keys)} alerta(s) expirada(s) del buffer"
                    )
                    for key in expired_keys:
                        # Verificar que aún exista antes de eliminar (evitar race condition)
                        if key in self.pending_alerts:
                            del self.pending_alerts[key]
        
        except asyncio.CancelledError:
            logger.debug("Tarea de limpieza cancelada")
        except Exception as e:
            log_exception(logger, "Error in cleanup task", e)
