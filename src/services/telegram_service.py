"""
Telegram Service - Dual-Source Alert Notification System
=========================================================
Gestiona el envío de alertas a través de la API de Telegram.
Implementa la lógica de "Dual Source" con ventana temporal para
diferenciar entre alertas estándar y alertas confirmadas.

Author: TradingView Pattern Monitor Team
"""

import asyncio
from typing import Dict, Optional, List, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import aiohttp
import math
import numpy as np

from config import Config
if TYPE_CHECKING:
    from src.logic.analysis_service import PatternSignal
from src.utils.logger import get_logger, log_exception
from src.services.local_notification_storage import LocalNotificationStorage


logger = get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

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
        
        # Servicio de almacenamiento local
        self.local_storage: Optional[LocalNotificationStorage] = None
        if Config.TELEGRAM.save_notifications_locally:
            self.local_storage = LocalNotificationStorage()
        
        logger.info(
            f"📱 Telegram Service inicializado "
            f"(Suscripción: {self.subscription}, "
            f"Notificaciones HTTP: {'✅ Habilitadas' if Config.TELEGRAM.enable_notifications else '❌ Deshabilitadas'}, "
            f"Guardado Local: {'✅ Habilitado' if Config.TELEGRAM.save_notifications_locally else '❌ Deshabilitado'})"
        )
    
    async def start(self) -> None:
        """Inicia el servicio de notificaciones."""
        self.session = aiohttp.ClientSession()
        logger.info("✅ Telegram Service iniciado")
    
    async def stop(self) -> None:
        """Detiene el servicio de notificaciones."""
        logger.info("🛑 Deteniendo Telegram Service...")
        
        # Cerrar sesión HTTP
        if self.session and not self.session.closed:
            await self.session.close()
        
        # Cerrar servicio de almacenamiento local
        if self.local_storage:
            await self.local_storage.close()
        
        logger.info("✅ Telegram Service detenido")
    
    async def handle_pattern_signal(self, signal: "PatternSignal") -> None:
        """
        Procesa una señal de patrón del Analysis Service.
        
        Envía inmediatamente una notificación por cada señal detectada.
        
        Args:
            signal: Señal de patrón detectada
        """
        logger.debug(
            f"📩 Señal recibida de {signal.source} | "
            f"{signal.pattern} @ {signal.timestamp}"
        )
        
        # Enviar notificación inmediatamente
        await self._send_standard_alert(signal)
    
    async def _send_standard_alert(self, signal: "PatternSignal") -> None:
        """
        Envía una alerta estándar (una sola fuente).
        
        Args:
            signal: Señal de patrón detectada
        """
        message = self._format_standard_message(signal)
        # Solo enviar gráfico si está habilitado en configuración
        chart = signal.chart_base64 if Config.TELEGRAM.send_charts else None
        await self._send_to_telegram(message, chart)
    

    def _format_symbol_for_display(self, symbol: str) -> str:
        """
        Formatea el símbolo para mostrar en el mensaje.
        Si estamos en IQOPTION, quita el sufijo -BIN.
        """
        if Config.DATA_PROVIDER == "IQOPTION":
            clean_symbol = symbol.replace("-BIN", "")
            # Insertar "/" después del tercer caracter si tiene 6 caracteres (ej: EURUSD -> EUR/USD)
            if len(clean_symbol) == 6:
                return f"{clean_symbol[:3]}/{clean_symbol[3:]}"
            return clean_symbol
        return symbol

    def _format_standard_message(self, signal: "PatternSignal") -> AlertMessage:
        """
        Formatea un mensaje de alerta estándar con sistema de clasificación de fuerza.
        
        Args:
            signal: Señal de patrón
            
        Returns:
            AlertMessage: Mensaje formateado
        """
        timestamp_str = datetime.fromtimestamp(signal.timestamp).strftime("%H:%M")
        
        # Obtener símbolo formateado
        display_symbol = self._format_symbol_for_display(signal.symbol)
        
        # ═════════════════════════════════════════════════════════════════════
        # TÍTULO BASADO EN SIGNAL_STRENGTH (Nuevo Sistema)
        # ═════════════════════════════════════════════════════════════════════
        title = self._get_title_text(signal, display_symbol)
        
        # Agregar información de debug si está habilitado
        debug_info = self._get_debug_info_text(signal)
        
        # Cuerpo del mensaje estructurado
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 Señal: {signal.signal_strength}\n"
            f"🔹 Patrón: {signal.pattern}\n"
            f"🔹 Fecha: {timestamp_str}\n"
            # f"{exhaustion_emoji} {exhaustion_text}\n"
            # f"{candle_exh_emoji} {candle_exh_text}\n"
            f"🔹 Tendencia: {signal.trend} ({signal.trend_score:+.1f}/10.0)\n"
            f"🔹 Precio Objetivo: {signal.entry_point:.6f}\n"
            f"{debug_info}"
            # f"━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        
        return AlertMessage(
            title=title,
            body=body,
            alert_type="STANDARD",
            timestamp=datetime.now()
        )

    def _get_title_text(self, signal: "PatternSignal", display_symbol: str) -> str:
        """
        Obtiene el título del mensaje basado en la fuerza de la señal.
        
        Args:
            signal: Señal de patrón detectada
            display_symbol: Símbolo formateado para mostrar
        
        Returns:
            str: Título del mensaje
        """
        title = ""
        # Definir título según fuerza y dirección esperada
        if signal.signal_strength == "VERY_HIGH":
            # 🔥 ALERTA MUY FUERTE (Patrón Principal + Ambos Exhaustion)
            if signal.pattern in ["SHOOTING_STAR"]:
                icon = "🔴"
                text = "Siguiente operación a la BAJA"
            elif signal.pattern in ["HAMMER"]:
                icon = "🟢"
                text = "Siguiente operación al ALZA"
            else:
                icon = "⚪"
                text = "Vela no reconocida"

            title = f"{icon * 3} *{display_symbol}* {icon * 3}\n{icon} {text}.\nPROBABILIDAD MUY ALTA\n"

        elif signal.signal_strength == "HIGH":
            # 🚨 ALERTA FUERTE (Patrón Principal + Bollinger Exhaustion)
            if signal.pattern in ["SHOOTING_STAR"]:
                icon = "🔴"
                text = "Siguiente operación a la BAJA"
            elif signal.pattern in ["HAMMER"]:
                icon = "🟢"
                text = "Siguiente operación al ALZA"
            else:
                icon = "⚪"
                text = "Vela no reconocida"

            title = f"{icon * 2} *{display_symbol}* {icon * 2}\n{icon} {text}.\nPROBABILIDAD ALTA\n"

        elif signal.signal_strength == "MEDIUM":
            # ⚠️ AVISO (Patrón Secundario + Ambos Exhaustion)
            
            # Patrones Bajistas
            if signal.pattern in ["INVERTED_HAMMER"]:
                title = f"⚠️ *{display_symbol}* ⚠️\n🔴 Posible operación a la BAJA\nPROBABILIDAD MEDIA\n"
            
            # Patrones Alcistas
            elif signal.pattern in ["HANGING_MAN"]:
                title = f"⚠️ *{display_symbol}* ⚠️\n🟢 Posible operación al ALZA\nPROBABILIDAD MEDIA\n"
            else:
                title = f"⚠️ *{display_symbol}* ⚠️\n⚪Vela no reconocida\nPROBABILIDAD MEDIA\n"

        elif signal.signal_strength == "LOW":
            # ℹ️ SEÑAL BAJA
            if signal.pattern in ["SHOOTING_STAR", "INVERTED_HAMMER"]:
                text = "🔴 Posible operación a la BAJA"
            elif signal.pattern in ["HAMMER", "HANGING_MAN"]:
                text = "🟢 Posible operación al ALZA"
            else:
                text = "⚪ Vela no reconocida"

            title = f"ℹ️ *{display_symbol}* ℹ️\n{text}.\nSin agotamiento detectado.\nProbabilidad baja."
        
        elif signal.signal_strength == "VERY_LOW":
            # ⚪ SEÑAL MUY BAJA
            if signal.pattern in ["SHOOTING_STAR", "INVERTED_HAMMER"]:
                text = "🔴 Posible operación a la BAJA"
            elif signal.pattern in ["HAMMER", "HANGING_MAN"]:
                text = "🟢 Posible operación al ALZA"
            else:
                text = "⚪ Vela no reconocida"

            title = f"⚪ *{display_symbol}* ⚪\n{text}.\nSin agotamiento detectado - Analizar\nPobabilidad bajísima."
        
        else:  # NONE
            title = f"*{display_symbol}*\nNada importante detectado.\n"

        return title
    
    def _get_debug_info_text(self, signal: "PatternSignal") -> str:
        """
        Obtiene la información de debug para mostrar en el mensaje.
        
        Args:
            signal: Señal de patrón detectada
        
        Returns:
            str: Información de debug
        """
        debug_info = ""
        if Config.SHOW_CANDLE_RESULT:
            from src.logic.analysis_service import get_candle_result_debug
            debug_info = get_candle_result_debug(
                pattern=signal.pattern,
                trend_status=signal.trend,
                exhaustion_type=signal.exhaustion_type,
                candle_exhaustion=signal.candle_exhaustion,
                rsi_val=signal.rsi_val
            )
        return debug_info   

    def _format_statistics_block(self, signal: "PatternSignal") -> str:
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
                f"\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 PROBABILIDAD (30d)\n"
                #f"━━━━━━━━━━━━━━━━━━━━━━\n"
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
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 PROBABILIDAD (30d)\n"
            #f"━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        
        return header + "\n".join(lines) + "\n\n"

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
        action: str,        # CALL/PUT
        result: str,        # WIN/LOSS/ATM
        entry_price: float,
        close_price: float,
        chart_base64: Optional[str] = None
    ) -> None:
        """
        Envía una notificación del resultado de la operación.
        
        Args:
            source: Fuente del dato
            symbol: Símbolo del activo
            action: Acción tomada ("CALL" o "PUT")
            result: Resultado ("WIN", "LOSS", "ATM")
            entry_price: Precio de entrada (objetivo)
            close_price: Precio de cierre real
            chart_base64: Imagen del gráfico (opcional)
        """
        display_symbol = self._format_symbol_for_display(symbol)
        
        # Iconos y formato según resultado
        if result == "WIN":
            icon = "🏆"
            status_text = "GANADA"
        elif result == "LOSS":
            icon = "❌"
            status_text = "PERDIDA"
        elif result == "NO_ENTRY":
            icon = "🚫"
            status_text = "NO ACTIVADA"
        else:
            icon = "⚪"
            status_text = "EMPATE (ATM)"
            
        # Iconos según acción
        action_icon = "🟢" if action == "CALL" else "🔴"
        
        title = f"{icon} RESULTADO: {status_text} | {display_symbol}"
        
        if result == "NO_ENTRY":
            message = (
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔹 Operación: {action_icon} {action}\n"
                f"🔹 Resultado: {status_text}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"ℹ️ El precio NO tocó la entrada.\n"
                f"🎯 Entrada: {entry_price:.5f}\n"
            )
        else:
            message = (
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔹 Operación: {action_icon} {action}\n"
                f"🔹 Resultado: {result}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 Entrada: {entry_price:.5f}\n"
                f"🏁 Cierre:   {close_price:.5f}\n"
                # f"━━━━━━━━━━━━━━━━━━━━━━\n"
            )
        
        await self._send_telegram_notification(
            title=title,
            subscription=Config.TELEGRAM.outcome_subscription,
            message=message,
            chart_base64=chart_base64
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
        # FIX: Reemplazar guiones bajos por espacios para evitar errores de Markdown
        title = title.replace("_", " ")
        message = message.replace("_", " ")

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
            "message_type": "markdown",
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
