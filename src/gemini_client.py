"""
Cliente de Gemini — interpreta los mensajes de Samuel en lenguaje natural
y decide qué acción tomar con el calendario.

Usa el modelo gemini-1.5-flash (gratuito en Google AI Studio).
Límites gratuitos verificados oct-2024: 15 RPM, 1 500 RPD, 1M tokens/min.
"""
import os
import logging
import json
from datetime import datetime
import pytz
import google.generativeai as genai

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone("America/Bogota")

# Prompt del sistema: define la personalidad y capacidades de JARVIS
SYSTEM_PROMPT = """Eres JARVIS, el asistente personal de Samuel. Hablas siempre en español.
Eres conciso, amable y directo. Samuel cursa tercer semestre universitario.

Tu única función en este momento es ayudar con el Google Calendar de Samuel.
Cuando Samuel te pida algo relacionado con su agenda, responde con un JSON estructurado.
Cuando sea una pregunta casual o saludo, responde normalmente en texto.

Para acciones de calendario, responde SOLO con este JSON (sin markdown, sin texto extra):
{
  "action": "<ver_agenda|crear_evento|eliminar_evento|mover_evento|ninguna>",
  "params": { ... parámetros según la acción ... },
  "confirmacion_requerida": true/false,
  "mensaje_confirmacion": "texto para pedirle confirmación a Samuel si aplica"
}

Acciones disponibles:
- ver_agenda: params: { dias: N }
- crear_evento: params: { titulo, fecha_inicio (ISO8601), fecha_fin (ISO8601), descripcion }
- eliminar_evento: params: { titulo_aproximado }
- mover_evento: params: { titulo_aproximado, nueva_fecha_inicio (ISO8601), nueva_fecha_fin (ISO8601) }
- ninguna: para saludos o preguntas que no son del calendario

Zona horaria: America/Bogota. Fecha y hora actual: {fecha_actual}

IMPORTANTE: No envíes información sensible. No proceses documentos ni contraseñas.
"""


class GeminiClient:
    """Maneja la comunicación con la API de Gemini."""

    def __init__(self):
        api_key = os.environ["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=self._build_system_prompt(),
        )

    def _build_system_prompt(self) -> str:
        """Inyecta la fecha/hora actual de Bogotá en el prompt."""
        now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M (%A)")
        return SYSTEM_PROMPT.format(fecha_actual=now)

    async def process_request(self, user_text: str, calendar_client) -> str:
        """
        Envía el mensaje de Samuel a Gemini y ejecuta la acción detectada.
        Retorna el texto de respuesta final para enviar por Telegram.
        """
        logger.info("Enviando a Gemini: %s", user_text[:80])

        response = self.model.generate_content(user_text)
        raw = response.text.strip()

        logger.debug("Respuesta de Gemini: %s", raw[:200])

        # Intentar parsear como JSON (acción de calendario)
        try:
            # Limpiar posibles bloques markdown que Gemini agregue
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            data = json.loads(raw)
            return await self._execute_action(data, calendar_client)

        except (json.JSONDecodeError, KeyError):
            # No es JSON — es una respuesta de texto normal
            return raw

    async def _execute_action(self, data: dict, calendar_client) -> str:
        """Ejecuta la acción del calendario según lo que Gemini interpretó."""
        action = data.get("action", "ninguna")
        params = data.get("params", {})
        requiere_confirmacion = data.get("confirmacion_requerida", False)
        msg_confirmacion = data.get("mensaje_confirmacion", "")

        if action == "ninguna":
            return data.get("mensaje_confirmacion", "¿En qué más puedo ayudarte?")

        if action == "ver_agenda":
            dias = params.get("dias", 7)
            events = calendar_client.get_upcoming_events(days=dias)
            if not events:
                return f"No tienes eventos en los próximos {dias} días 🎉"
            lines = [f"📅 *Próximos {dias} días:*\n"]
            for e in events:
                lines.append(f"• {e['display']}")
            return "\n".join(lines)

        # Para crear/mover/eliminar: siempre pedir confirmación
        if requiere_confirmacion and msg_confirmacion:
            # Guardar la acción pendiente para cuando Samuel confirme
            # (se implementa en Fase 2 con estados de conversación)
            return (
                f"⚠️ {msg_confirmacion}\n\n"
                "_(Responde *sí* para confirmar o *no* para cancelar)_"
            )

        return "Entendido. ¿Puedes darme más detalles?"
