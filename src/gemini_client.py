"""
Cliente de Gemini — interpreta los mensajes de Samuel en lenguaje natural
y decide qué acción tomar con el calendario.

Usa el modelo gemini-3.8-flash mediante la biblioteca heredada google-generativeai.
Google recomienda migrar a google-genai; verificar el nivel gratuito y sus límites
vigentes antes de depender de ellos.
"""
import os
import logging
import json
import asyncio
import uuid
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
- ver_agenda: params: { "modo": "<hoy|manana|dias|semana>", "dias": N }
  Ejemplos:
  - "solo mañana" o "¿qué tengo mañana?" -> { "modo": "manana" }
  - "¿qué tengo hoy?" -> { "modo": "hoy" }
  - "siguientes 3 días" -> { "modo": "dias", "dias": 3 }
  - "toda la semana" o "esta semana" -> { "modo": "semana", "dias": 7 }
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
            model_name="gemini-3.8-flash",
            system_instruction=self._build_system_prompt(),
        )

    def _build_system_prompt(self) -> str:
        """Inyecta la fecha/hora actual de Bogotá en el prompt."""
        now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M (%A)")
        return SYSTEM_PROMPT.replace("{fecha_actual}", now)

    async def process_request(
        self, user_text: str, calendar_client, confirmation_store, user_id: int
    ) -> str:
        """
        Envía el mensaje de Samuel a Gemini y ejecuta la acción detectada.
        Retorna el texto de respuesta final para enviar por Telegram.
        """
        import re
        logger.info("Enviando solicitud a Gemini (longitud=%d)", len(user_text))

        response = self.model.generate_content(user_text)
        raw = response.text.strip()

        logger.info("Respuesta de Gemini recibida (longitud=%d)", len(raw))

        # Buscar el bloque JSON { ... } dentro de la respuesta
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as e:
                logger.warning("La respuesta JSON de Gemini no se pudo leer: %s", e)
            else:
                try:
                    return await self._execute_action(
                        data, calendar_client, confirmation_store, user_id
                    )
                except Exception:
                    logger.exception("No se pudo procesar la solicitud de calendario")
                    return "No pude procesar esa solicitud. No hice cambios en tu calendario."

        # Si no tiene JSON, es una respuesta conversacional directa
        return raw

    async def _execute_action(
        self, data: dict, calendar_client, confirmation_store, user_id: int
    ) -> str:
        """Ejecuta la acción del calendario según lo que Gemini interpretó."""
        action = data.get("action", "ninguna")
        params = data.get("params", {})

        if action == "ninguna":
            return data.get("mensaje_confirmacion", "¿En qué más puedo ayudarte?")

        if action == "ver_agenda":
            modo = params.get("modo", "semana")
            try:
                dias = int(params.get("dias", 7))
            except (ValueError, TypeError):
                dias = 7

            label, events = calendar_client.get_events(mode=modo, days=dias)
            if not events:
                return f"{label}\n\nNo tienes eventos registrados para este periodo 🎉"
            lines = [f"{label}\n"]
            for e in events:
                lines.append(f"• {e['display']}")
            return "\n".join(lines)

        if action not in ("crear_evento", "eliminar_evento", "mover_evento"):
            return "No reconocí esa operación. No hice cambios en tu calendario."
        if confirmation_store is None:
            return (
                "No puedo pedir una confirmación segura porque falta configurar la hoja privada. "
                "No hice cambios en tu calendario."
            )

        try:
            proposal = self._prepare_calendar_action(action, params, calendar_client)
        except ValueError as exc:
            return f"No hice cambios: {exc}"
        if isinstance(proposal, str):
            return proposal

        action_id = str(uuid.uuid4())
        try:
            await asyncio.to_thread(
                confirmation_store.save_pending, action_id, user_id, proposal
            )
        except Exception:
            logger.exception("No se pudo guardar la confirmación pendiente")
            return "No pude guardar la confirmación de forma segura; no hice cambios."

        return (
            f"⚠️ {self._describe_action(proposal)}\n\n"
            "Responde *sí* para confirmar o *no* para cancelar. "
            "La confirmación vence en 10 minutos."
        )

    @staticmethod
    def _prepare_calendar_action(action: str, params: dict, calendar_client) -> dict | str:
        if action == "crear_evento":
            title = str(params.get("titulo", "")).strip()
            start = GeminiClient._normalize_datetime(params.get("fecha_inicio"))
            end = GeminiClient._normalize_datetime(params.get("fecha_fin"))
            if not title or not start or not end:
                raise ValueError("faltan el título o las fechas de inicio y fin.")
            if datetime.fromisoformat(end) <= datetime.fromisoformat(start):
                raise ValueError("la hora de fin debe ser posterior a la de inicio.")
            return {
                "action": action,
                "title": title,
                "start": start,
                "end": end,
                "description": str(params.get("descripcion", "")),
            }

        title_query = str(params.get("titulo_aproximado", "")).strip()
        if not title_query:
            raise ValueError("necesito el título del evento que quieres cambiar.")
        matches = calendar_client.find_events_by_title(title_query)
        if not matches:
            return f"No encontré un evento próximo que coincida con «{title_query}». No hice cambios."
        if len(matches) > 1:
            choices = "\n".join(f"• {item['display']}" for item in matches[:5])
            return (
                f"Encontré varios eventos parecidos. Dime la fecha o el título exacto:\n{choices}"
            )

        event = matches[0]
        if action == "eliminar_evento":
            return {"action": action, "event_id": event["id"], "title": event["title"]}

        start = GeminiClient._normalize_datetime(params.get("nueva_fecha_inicio"))
        end = GeminiClient._normalize_datetime(params.get("nueva_fecha_fin"))
        if not start or not end:
            raise ValueError("faltan la nueva fecha de inicio y fin.")
        if datetime.fromisoformat(end) <= datetime.fromisoformat(start):
            raise ValueError("la hora de fin debe ser posterior a la de inicio.")
        return {
            "action": action,
            "event_id": event["id"],
            "title": event["title"],
            "start": start,
            "end": end,
        }

    @staticmethod
    def _normalize_datetime(value) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = TIMEZONE.localize(parsed)
        return parsed.isoformat()

    @staticmethod
    def _describe_action(action: dict) -> str:
        kind = action["action"]
        if kind == "crear_evento":
            return f"¿Confirmas crear «{action['title']}» de {action['start']} a {action['end']}?"
        if kind == "mover_evento":
            return f"¿Confirmas mover «{action['title']}» a {action['start']}–{action['end']}?"
        return f"¿Confirmas eliminar «{action['title']}»?"
