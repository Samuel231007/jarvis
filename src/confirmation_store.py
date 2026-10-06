"""Almacenamiento pequeño y persistente de confirmaciones en Google Sheets."""
from __future__ import annotations

import json
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from src.calendar_client import CalendarClient

TZ = ZoneInfo("America/Bogota")
SHEET_RANGE = "Pendientes!A1:F2"
HEADERS = ["action_id", "telegram_user_id", "created_at", "expires_at", "action_json", "status"]
MAX_READS_PER_MINUTE = 10
MAX_WRITES_PER_MINUTE = 10


class StoreRateLimitError(RuntimeError):
    """El bot llegó a su límite interno de consultas gratuitas a Sheets."""


@dataclass
class PendingAction:
    row_number: int
    action_id: str
    user_id: int
    created_at: datetime
    expires_at: datetime
    action: dict[str, Any]
    status: str


class ConfirmationStore:
    """Guarda una acción pendiente por usuario durante un máximo de diez minutos."""

    def __init__(self, spreadsheet_id: str | None = None):
        self.spreadsheet_id = (
            spreadsheet_id or os.environ.get("GOOGLE_CONFIRMATIONS_SPREADSHEET_ID", "")
        ).strip()
        if not self.spreadsheet_id:
            raise RuntimeError(
                "Configura GOOGLE_CONFIRMATIONS_SPREADSHEET_ID con el ID de la hoja "
                "privada que tiene una pestaña llamada Pendientes."
            )
        credentials = CalendarClient._authenticate()
        self.service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        self._reads: deque[float] = deque()
        self._writes: deque[float] = deque()

    def get_pending(self, user_id: int) -> PendingAction | None:
        rows = self._read_rows()
        if len(rows) < 2:
            return None
        row = rows[1]
        if len(row) < 6 or row[1] != str(user_id) or row[5] not in ("pending", "executing"):
            return None
        try:
            pending = self._to_pending(2, row)
        except (ValueError, TypeError, json.JSONDecodeError):
            self._write_status(2, "invalid")
            return None
        if datetime.now(TZ) >= pending.expires_at:
            self._write_status(2, "expired")
            return None
        return pending

    def save_pending(self, action_id: str, user_id: int, action: dict[str, Any]) -> None:
        now = datetime.now(TZ)
        row = [
            action_id,
            str(user_id),
            now.isoformat(),
            (now + timedelta(minutes=10)).isoformat(),
            json.dumps(action, ensure_ascii=False, separators=(",", ":")),
            "pending",
        ]
        self._write_values("Pendientes!A2:F2", [row])

    def set_status(self, row_number: int, status: str) -> None:
        self._write_status(row_number, status)

    def _to_pending(self, row_number: int, row: list[str]) -> PendingAction:
        created = datetime.fromisoformat(row[2])
        expires = datetime.fromisoformat(row[3])
        if created.tzinfo is None:
            created = created.replace(tzinfo=TZ)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=TZ)
        return PendingAction(
            row_number=row_number,
            action_id=row[0],
            user_id=int(row[1]),
            created_at=created,
            expires_at=expires,
            action=json.loads(row[4]),
            status=row[5],
        )

    def _read_rows(self) -> list[list[str]]:
        self._check_budget(self._reads, MAX_READS_PER_MINUTE, "lecturas")
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=SHEET_RANGE)
            .execute()
        )
        rows = result.get("values", [])
        if not rows:
            self._write_values("Pendientes!A1:F1", [HEADERS])
            return [HEADERS]
        if rows[0] != HEADERS:
            raise RuntimeError(
                "La pestaña Pendientes debe estar vacía o tener la fila de encabezados "
                "action_id, telegram_user_id, created_at, expires_at, action_json, status."
            )
        return rows

    def _write_status(self, row_number: int, status: str) -> None:
        self._write_values(f"Pendientes!F{row_number}:F{row_number}", [[status]])

    def _write_values(self, range_name: str, values: list[list[str]]) -> None:
        self._check_budget(self._writes, MAX_WRITES_PER_MINUTE, "escrituras")
        (
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="RAW",
                body={"values": values},
            )
            .execute()
        )

    @staticmethod
    def _check_budget(history: deque[float], limit: int, label: str) -> None:
        now = time.monotonic()
        while history and now - history[0] >= 60:
            history.popleft()
        if len(history) >= limit:
            raise StoreRateLimitError(
                f"Se alcanzó el límite interno de {limit} {label} a Google Sheets por minuto."
            )
        history.append(now)
