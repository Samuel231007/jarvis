"""Crea una hoja privada de confirmaciones para Jarvis usando OAuth local."""
from __future__ import annotations

import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.calendar_client import SCOPES
from src.confirmation_store import HEADERS

PROJECT_DIR = Path(__file__).resolve().parent
TOKEN_PATH = PROJECT_DIR / "token.json"


def create_confirmation_sheet(service) -> dict[str, str]:
    """Crea la hoja y deja lista la pestaña Pendientes con sus encabezados."""
    result = (
        service.spreadsheets()
        .create(
            body={
                "properties": {"title": "JARVIS Confirmaciones"},
                "sheets": [{"properties": {"title": "Pendientes"}}],
            },
            fields="spreadsheetId,spreadsheetUrl",
        )
        .execute()
    )
    spreadsheet_id = result["spreadsheetId"]
    (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range="Pendientes!A1:F1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        )
        .execute()
    )
    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": result["spreadsheetUrl"],
    }


def main() -> int:
    if not TOKEN_PATH.is_file():
        print("No encuentro token.json. Autoriza Google Calendar primero desde README.md.")
        return 1

    try:
        credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if not credentials.has_scopes(SCOPES):
            print(
                "El token no incluye Calendar y drive.file. Vuelve a autorizar Google "
                "con el comando indicado en README.md."
            )
            return 1
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        if not credentials.valid:
            print("El token de Google no es válido. Vuelve a autorizar Google y reintenta.")
            return 1

        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        result = create_confirmation_sheet(service)
    except Exception as error:
        print(f"No pude crear la hoja: {error}")
        return 1

    print("Hoja privada creada. Ábrela para comprobarla:")
    print(result["spreadsheet_url"])
    print("Copia este ID en GOOGLE_CONFIRMATIONS_SPREADSHEET_ID en Render:")
    print(result["spreadsheet_id"])
    print("Ejecuta este asistente una sola vez para evitar crear hojas duplicadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
