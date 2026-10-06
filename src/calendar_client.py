"""
Cliente de Google Calendar — lee y escribe eventos en el calendario de Samuel.
Usa OAuth2 con token guardado localmente (token.json).
"""
import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Solo pedimos permisos de lectura/escritura del calendario
SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = "America/Bogota"
TZ = ZoneInfo(TIMEZONE)


class CalendarClient:
    """Maneja la lectura y escritura en Google Calendar."""

    def __init__(self):
        self.service = self._authenticate()

    def _authenticate(self):
        """
        Autentica con Google usando OAuth2.
        - Primera vez: abre el navegador para que Samuel autorice.
        - Siguientes veces: usa token.json guardado localmente.
        """
        creds = None

        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)

        # Si no hay token válido, renovar o pedir autorización
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists("credentials.json"):
                    raise FileNotFoundError(
                        "No se encontró credentials.json. "
                        "Descárgalo desde Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                # Puerto fijo 8080 es más estable que puerto aleatorio en Windows
                creds = flow.run_local_server(port=8080, open_browser=True)

            # Guardar token para la próxima vez
            with open("token.json", "w") as f:
                f.write(creds.to_json())

        return build("calendar", "v3", credentials=creds)

    def get_events(
        self,
        mode: str = "week",
        days: int = 7,
    ) -> tuple[str, list[dict]]:
        """
        Retorna (título_legible, lista_eventos).
        Soporta:
        - 'today' / 'hoy': solo el día de hoy
        - 'tomorrow' / 'manana': solo el día de mañana
        - 'days' / 'dias': próximos N días
        - 'week' / 'semana': próximos 7 días
        """
        now = datetime.now(TZ)
        mode = (mode or "week").lower()

        if mode in ("today", "hoy"):
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            label = "📅 *Tu agenda para HOY:*"
        elif mode in ("tomorrow", "manana"):
            tomorrow = now + timedelta(days=1)
            start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
            end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999)
            date_name = tomorrow.strftime("%A %d de %B").capitalize()
            label = f"🌅 *Tu agenda para MAÑANA ({date_name}):*"
        elif mode in ("days", "dias") or days != 7:
            start = now
            end = now + timedelta(days=days)
            label = f"📆 *Próximos {days} días:*"
        else:
            start = now
            end = now + timedelta(days=7)
            label = "🗓️ *Toda la semana (próximos 7 días):*"

        result = self.service.events().list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            maxResults=30,
            singleEvents=True,
            orderBy="startTime",
            timeZone=TIMEZONE,
        ).execute()

        events = result.get("items", [])
        return label, [self._format_event(e) for e in events]

    def get_upcoming_events(self, days: int = 7) -> list[dict]:
        """Retorna los eventos de los próximos N días (compatibilidad)."""
        _, events = self.get_events(mode="days", days=days)
        return events

    def create_event(self, title: str, start: str, end: str, description: str = "") -> dict:
        """
        Crea un evento en el calendario principal.
        start y end deben ser strings ISO8601 con zona horaria.
        """
        event_body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start, "timeZone": TIMEZONE},
            "end": {"dateTime": end, "timeZone": TIMEZONE},
        }
        created = self.service.events().insert(
            calendarId="primary", body=event_body
        ).execute()
        logger.info("Evento creado: %s (%s)", title, created.get("id"))
        return created

    def create_recurring_event(
        self,
        title: str,
        start: str,
        end: str,
        until_date: str,
        description: str = "",
    ) -> dict:
        """
        Crea un evento recurrente semanal hasta una fecha dada (YYYYMMDD).
        """
        # until_date en formato YYYYMMDDTHHMMSSZ
        rrule = f"RRULE:FREQ=WEEKLY;UNTIL={until_date}T235959Z"
        event_body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start, "timeZone": TIMEZONE},
            "end": {"dateTime": end, "timeZone": TIMEZONE},
            "recurrence": [rrule],
        }
        created = self.service.events().insert(
            calendarId="primary", body=event_body
        ).execute()
        logger.info("Evento recurrente creado: %s (%s)", title, created.get("id"))
        return created

    def delete_event(self, event_id: str) -> None:
        """Elimina un evento por su ID."""
        self.service.events().delete(
            calendarId="primary", eventId=event_id
        ).execute()
        logger.info("Evento eliminado: %s", event_id)

    def find_events_by_title(self, title_query: str, days_ahead: int = 30) -> list[dict]:
        """Busca eventos cuyo título contenga la cadena dada."""
        all_events = self.get_upcoming_events(days=days_ahead)
        query = title_query.lower()
        return [e for e in all_events if query in e["title"].lower()]

    @staticmethod
    def _format_event(event: dict) -> dict:
        """Convierte un evento de la API a un dict legible."""
        start = event["start"].get("dateTime", event["start"].get("date", ""))
        title = event.get("summary", "Sin título")

        # Formatear la fecha para mostrar en Telegram
        try:
            dt = datetime.fromisoformat(start)
            date_str = dt.strftime("%a %d/%m %H:%M")
        except Exception:
            date_str = start

        return {
            "id": event["id"],
            "title": title,
            "start": start,
            "display": f"*{date_str}* — {title}",
        }
