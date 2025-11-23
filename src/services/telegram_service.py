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
from src.services.local_notification_storage import LocalNotificationStorage


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
        
        # Servicio de almacenamiento local
        self.local_storage: Optional[LocalNotificationStorage] = None
        if Config.TELEGRAM.save_notifications_locally:
            self.local_storage = LocalNotificationStorage()
        
        # Tarea de limpieza de alertas expiradas
        self.cleanup_task: Optional[asyncio.Task] = None
        
        logger.info(
            f"📱 Telegram Service inicializado "
            f"(Suscripción: {self.subscription}, Ventana: {self.confirmation_window}s, "
            f"Notificaciones HTTP: {'✅ Habilitadas' if Config.TELEGRAM.enable_notifications else '❌ Deshabilitadas'}, "
            f"Guardado Local: {'✅ Habilitado' if Config.TELEGRAM.save_notifications_locally else '❌ Deshabilitado'})"
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
        
        # Cerrar servicio de almacenamiento local
        if self.local_storage:
            await self.local_storage.close()
        
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
        Formatea un mensaje de alerta estándar con sistema de clasificación de fuerza.
        
        Args:
            signal: Señal de patrón
            
        Returns:
            AlertMessage: Mensaje formateado
        """
        timestamp_str = datetime.fromtimestamp(signal.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        
        # ═════════════════════════════════════════════════════════════════════
        # TÍTULO BASADO EN SIGNAL_STRENGTH (Nuevo Sistema)
        # ═════════════════════════════════════════════════════════════════════
        
        if signal.signal_strength == "HIGH":
            # 🚨 ALERTA FUERTE - Patrón en zona de agotamiento (Cúspide o Base)
            if signal.pattern in ["SHOOTING_STAR", "HANGING_MAN"]:
                title = f"🚨 ALERTA FUERTE | {signal.symbol}\nAgotamiento ALCISTA confirmado (Cúspide)\n"
            else:  # HAMMER, INVERTED_HAMMER
                title = f"🚨 ALERTA FUERTE | {signal.symbol}\nAgotamiento BAJISTA confirmado (Base)\n"
        elif signal.signal_strength == "MEDIUM":
            # ⚠️ AVISO - Posible debilitamiento
            if signal.pattern in ["SHOOTING_STAR", "INVERTED_HAMMER"]:
                title = f"⚠️ AVISO | {signal.symbol}\nPosible debilitamiento alcista\n"
            else:  # HAMMER, HANGING_MAN
                title = f"⚠️ AVISO | {signal.symbol}\nPosible debilitamiento bajista\n"
        else:  # LOW
            # ℹ️ INFORMATIVO - Sin agotamiento claro
            title = f"ℹ️ PATRÓN DETECTADO | {signal.symbol}\nSolo informativo - Requiere análisis adicional\n"
        
        # Formatear EMAs (mostrar N/A si no están disponibles)
        import math
        ema_20_str = f"{signal.ema_20:.5f}" if not math.isnan(signal.ema_20) else "N/A"
        ema_30_str = f"{signal.ema_30:.5f}" if not math.isnan(signal.ema_30) else "N/A"
        ema_50_str = f"{signal.ema_50:.5f}" if not math.isnan(signal.ema_50) else "N/A"
        
        # Formatear Bollinger Bands
        bb_upper_str = f"{signal.bb_upper:.5f}" if signal.bb_upper is not None else "N/A"
        bb_lower_str = f"{signal.bb_lower:.5f}" if signal.bb_lower is not None else "N/A"
        
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
        
        # Emoji de zona de agotamiento
        exhaustion_emoji = ""
        exhaustion_text = ""
        if signal.exhaustion_type == "PEAK":
            exhaustion_emoji = "🔺"
            exhaustion_text = "Cúspide de Bollinger"
        elif signal.exhaustion_type == "BOTTOM":
            exhaustion_emoji = "🔻"
            exhaustion_text = "Base de Bollinger"
        else:
            exhaustion_emoji = "➖"
            exhaustion_text = "Zona Neutra"
        
        # Construir bloque de estadísticas si hay datos suficientes
        statistics_block = ""
        if signal.statistics:
            statistics_block = self._format_statistics_block(signal)
        else:
            logger.warning("⚠️  signal.statistics es None o no existe")
        
        # Cuerpo del mensaje estructurado (reducido para cumplir límite Telegram)
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 INFO DE VELA\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 Fuente: {signal.source}\n"
            f"🔹 Patrón: {signal.pattern}\n"
            f"🔹 Timestamp: {timestamp_str}\n"
            f"🔹 OHLC: O={signal.candle.open:.2f} | H={signal.candle.high:.2f} | L={signal.candle.low:.2f} | C={signal.candle.close:.2f}\n"
            f"🔹 Confianza Técnica: {signal.confidence:.0%}\n"
            f"🔹 Fuerza de Señal: {signal.signal_strength}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 TENDENCIA\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 Estado: {signal.trend} (Score: {signal.trend_score:+d}/10)\n"
            f"🔹 Interpretación: {trend_interpretation}\n"
            f"🔹 Estructura: {estructura}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📉 BOLLINGER BANDS\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{exhaustion_emoji} Zona: {exhaustion_text}\n"
            f"🔹 Banda Superior: {bb_upper_str}\n"
            f"🔹 Banda Inferior: {bb_lower_str}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 INDICADORES\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 EMA 200: {signal.ema_200:.5f}\n"
            f"🔹 EMA 50: {ema_50_str}\n"
            f"🔹 EMA 30: {ema_30_str}\n"
            f"🔹 EMA 20: {ema_20_str}\n\n"
            f"{statistics_block}"
            f"⚡ *Verificar gráfico manualmente antes de operar.*\n"
        )
        
        return AlertMessage(
            title=title,
            body=body,
            alert_type="STANDARD",
            timestamp=datetime.now()
        )
    
    def _format_statistics_block(self, signal: PatternSignal) -> str:
        """
        Formatea el bloque de estadísticas con diseño jerárquico y limpio.
        
        NUEVA LÓGICA:
        - Filtrado estricto por exhaustion_type (PEAK/BOTTOM/NONE)
        - 3 niveles de precisión: EXACT, BY_SCORE, BY_RANGE
        - Rachas independientes por subgrupo
        - Visualización condicional (solo muestra lo que aporta valor)
        
        Args:
            signal: Señal de patrón con estadísticas
            
        Returns:
            Bloque de estadísticas formateado o cadena vacía
        """
        if not signal.statistics:
            return ""
        
        stats = signal.statistics
        exhaustion_type = stats.get('exhaustion_type', 'NONE')
        exact = stats.get('exact', {})
        by_score = stats.get('by_score', {})
        by_range = stats.get('by_range', {})
        
        # Emoji de zona
        zone_emoji = "🔺" if exhaustion_type == "PEAK" else "🔻" if exhaustion_type == "BOTTOM" else "➖"
        
        # Verificar si hay datos mínimos (al menos 1 caso en by_range)
        if by_range.get('total_cases', 0) == 0:
            return (
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 PROBABILIDAD (30d) | {signal.pattern}\n"
                f"{zone_emoji} Zona: {exhaustion_type}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️  Sin datos históricos\n\n"
            )
        
        # Helper: Convierte lista de direcciones en emojis
        def streak_to_emojis(streak: list) -> str:
            emojis = []
            for direction in streak[:5]:
                if direction == "VERDE":
                    emojis.append("🟢")
                elif direction == "ROJA":
                    emojis.append("🔴")
                else:
                    emojis.append("⚪")
            return "".join(emojis) if emojis else "N/A"
        
        # Construir líneas de cada nivel
        lines = []
        
        # 1. EXACT (GEMELO) - Solo si tiene datos
        exact_cases = exact.get('total_cases', 0)
        if exact_cases > 0:
            exact_verde_pct = int(exact.get('verde_pct', 0.0) * 100)
            exact_roja_pct = int(exact.get('roja_pct', 0.0) * 100)
            exact_streak = streak_to_emojis(exact.get('streak', []))
            lines.append(
                f"🎯 EXACTO ({exact_cases}): {exact_verde_pct}%🟢 {exact_roja_pct}%🔴\n"
                f"   Racha: {exact_streak}"
            )
        
        # 2. BY_SCORE (PRECISIÓN MEDIA) - Solo si tiene datos
        by_score_cases = by_score.get('total_cases', 0)
        if by_score_cases > 0:
            by_score_verde_pct = int(by_score.get('verde_pct', 0.0) * 100)
            by_score_roja_pct = int(by_score.get('roja_pct', 0.0) * 100)
            by_score_streak = streak_to_emojis(by_score.get('streak', []))
            lines.append(
                f"⚖️ SCORE ({by_score_cases}): {by_score_verde_pct}%🟢 {by_score_roja_pct}%🔴\n"
                f"   Racha: {by_score_streak}"
            )
        
        # 3. BY_RANGE (MÁXIMA MUESTRA) - Solo si tiene MÁS casos que BY_SCORE
        by_range_cases = by_range.get('total_cases', 0)
        if by_range_cases > by_score_cases:
            by_range_verde_pct = int(by_range.get('verde_pct', 0.0) * 100)
            by_range_roja_pct = int(by_range.get('roja_pct', 0.0) * 100)
            by_range_streak = streak_to_emojis(by_range.get('streak', []))
            score_range = by_range.get('score_range', (0, 0))
            lines.append(
                f"📉 ZONA ({by_range_cases}): {by_range_verde_pct}%🟢 {by_range_roja_pct}%🔴\n"
                f"   Racha: {by_range_streak}"
            )
        
        # Ensamblar bloque final
        if not lines:
            return ""
        
        header = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 PROBABILIDAD (30d) | {signal.pattern}\n"
            f"{zone_emoji} Zona: {exhaustion_type} (Estricto)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        
        return header + "\n".join(lines) + "\n\n"
    
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
        
        # Signal 2 EMAs
        ema2_20 = f"{signal2.ema_20:.5f}" if not math.isnan(signal2.ema_20) else "N/A"
        ema2_30 = f"{signal2.ema_30:.5f}" if not math.isnan(signal2.ema_30) else "N/A"
        ema2_50 = f"{signal2.ema_50:.5f}" if not math.isnan(signal2.ema_50) else "N/A"
        
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
        
        body = f"🎯 CONFIRMACIÓN DUAL-SOURCE\n📊 Fuentes: {signal1.source} + {signal2.source}\n📈 Patrón: {signal1.pattern}\n🕒 Timestamp: {timestamp_str}\n\n{signal1.source}:\n  • Apertura: {signal1.candle.open:.5f}\n  • Máximo: {signal1.candle.high:.5f}\n  • Mínimo: {signal1.candle.low:.5f}\n  • Cierre: {signal1.candle.close:.5f}\n  • EMAs: 20={ema1_20} | 30={ema1_30} | 50={ema1_50} | 200={signal1.ema_200:.5f}\n  • Tendencia: {signal1.trend} (Score: {signal1.trend_score:+d})\n  • Confianza: {signal1.confidence:.0%}\n\n{signal2.source}:\n  • Apertura: {signal2.candle.open:.5f}\n  • Máximo: {signal2.candle.high:.5f}\n  • Mínimo: {signal2.candle.low:.5f}\n  • Cierre: {signal2.candle.close:.5f}\n  • EMAs: 20={ema2_20} | 30={ema2_30} | 50={ema2_50} | 200={signal2.ema_200:.5f}\n  • Tendencia: {signal2.trend} (Score: {signal2.trend_score:+d})\n  • Confianza: {signal2.confidence:.0%}\n\n📐 Estructura Promedio: {estructura}\n🔗 Alineación: {signal1.source}={'✓' if signal1.is_trend_aligned else '✗'} | {signal2.source}={'✓' if signal2.is_trend_aligned else '✗'}\n✨ Confianza Promedio: {avg_confidence:.0%}\n\n🚀 Alta probabilidad. Revisar retroceso del 50% en primeros 30s de la siguiente vela."
        
        return AlertMessage(
            title=title,
            body=body,
            alert_type="STRONG",
            timestamp=datetime.now()
        )
    
    async def _send_to_telegram(self, message: AlertMessage, chart_base64: Optional[str] = None) -> None:
        """
        Procesa una notificación: siempre genera el mensaje/imagen, luego decide si:
        1. Enviar vía HTTP a Telegram API (si ENABLE_NOTIFICATIONS=true)
        2. Guardar localmente en PNG/JSON (si SAVE_NOTIFICATIONS_LOCALLY=true)
        
        Args:
            message: Mensaje a enviar
            chart_base64: Imagen del gráfico codificada en Base64 (opcional)
        """
        # PASO 1: Guardar localmente si está habilitado
        if Config.TELEGRAM.save_notifications_locally and self.local_storage:
            try:
                await self.local_storage.save_notification(
                    title=message.title,
                    message=message.body,
                    chart_base64=chart_base64
                )
            except Exception as e:
                log_exception(logger, "Error guardando notificación localmente", e)
        
        # PASO 2: Enviar vía HTTP usando la función base
        await self._send_telegram_notification(
            title=message.title,
            subscription=self.subscription,
            message=message.body,
            chart_base64=chart_base64
        )
    
    async def send_outcome_notification(
        self,
        source: str,
        symbol: str,
        direction: str,
        chart_base64: Optional[str] = None
    ) -> None:
        """
        Envía una notificación del resultado de una vela (VERDE o ROJA).
        
        Args:
            source: Fuente del dato (ej: "BINANCE", "OANDA")
            symbol: Símbolo del activo (ej: "BTCUSDT", "EURUSD")
            direction: Dirección de la vela ("VERDE" o "ROJA")
            chart_base64: Imagen del gráfico codificada en Base64 (opcional)
        """
        title = f"📊 Resultado Vela - {source}:{symbol}"
        message = f"La vela resultante fue: {direction}"
        
        await self._send_telegram_notification(
            title=title,
            subscription=Config.TELEGRAM.outcome_subscription,
            message=message
        )
    
    async def _send_telegram_notification(
        self,
        title: str,
        subscription: str,
        message: str,
        chart_base64: Optional[str] = None
    ) -> None:
        """
        Función base para enviar notificaciones a Telegram API.
        
        Args:
            title: Título del mensaje
            subscription: Tipo de suscripción (topic)
            message: Cuerpo del mensaje
            chart_base64: Imagen del gráfico codificada en Base64 (opcional)
        """
        # Verificar si las notificaciones HTTP están habilitadas
        if not Config.TELEGRAM.enable_notifications:
            logger.debug("📵 Notificaciones HTTP deshabilitadas. Mensaje no enviado a Telegram API.")
            return
        
        if not self.session:
            logger.error("❌ No se puede enviar mensaje: Sesión HTTP no inicializada")
            return
        
        # Formato del payload según el nuevo formato con image_base64
        payload = {
            "first_message": title,
            "image_base64": chart_base64 if chart_base64 else "",
            #"message_type": "standard",
            "entries": [
                {
                    "subscription": subscription,
                    "message": message
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
                f"🔹 Título: {title}\n"
                f"🔹 Gráfico Incluido: {chart_status}\n"
                f"🔹 Tamaño Gráfico: {chart_size} bytes\n"
                f"🔹 Suscripción: {subscription}\n"
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
                        f"🔹 Suscripción: {subscription}\n"
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
