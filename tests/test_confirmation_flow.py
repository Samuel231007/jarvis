import asyncio
import os
import sys
import time
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import bot
from src.confirmation_store import (
    ConfirmationStore,
    HEADERS,
    MAX_READS_PER_MINUTE,
    StoreRateLimitError,
)
from src.gemini_client import GeminiClient


class FakeRequest:
    def __init__(self, callback):
        self.callback = callback

    def execute(self):
        return self.callback()


class FakeSheetValues:
    def __init__(self):
        self.rows = []

    def get(self, **kwargs):
        return FakeRequest(lambda: {"values": [row[:] for row in self.rows]})

    def update(self, range, body, **kwargs):
        def apply():
            start = range.split("!")[1].split(":")[0]
            row_num = int("".join(c for c in start if c.isdigit()))
            col_letters = "".join(c for c in start if c.isalpha())
            start_col = ord(col_letters[0].upper()) - ord("A")
            while len(self.rows) < row_num:
                self.rows.append([])
            for offset, values in enumerate(body["values"]):
                row_index = row_num - 1 + offset
                while len(self.rows[row_index]) < start_col + len(values):
                    self.rows[row_index].append("")
                for col_offset, value in enumerate(values):
                    self.rows[row_index][start_col + col_offset] = value
            return {"updatedRows": len(body["values"])}

        return FakeRequest(apply)


class FakeSheetService:
    def __init__(self):
        self.values_api = FakeSheetValues()

    def spreadsheets(self):
        return self

    def values(self):
        return self.values_api


class ConfirmationStoreTests(unittest.TestCase):
    def make_store(self):
        store = object.__new__(ConfirmationStore)
        store.spreadsheet_id = "private-sheet"
        store.service = FakeSheetService()
        store._reads = deque()
        store._writes = deque()
        return store

    def test_pending_action_survives_store_recreation(self):
        store = self.make_store()
        self.assertIsNone(store.get_pending(123))
        self.assertEqual(store.service.values_api.rows[0], HEADERS)

        action = {"action": "crear_evento", "title": "Prueba", "start": "2026-10-07T10:00:00-05:00", "end": "2026-10-07T11:00:00-05:00"}
        store.save_pending("action-1", 123, action)

        restarted_store = object.__new__(ConfirmationStore)
        restarted_store.spreadsheet_id = "private-sheet"
        restarted_store.service = store.service
        restarted_store._reads = deque()
        restarted_store._writes = deque()
        pending = restarted_store.get_pending(123)

        self.assertIsNotNone(pending)
        self.assertEqual(pending.action_id, "action-1")
        self.assertEqual(pending.action, action)
        self.assertEqual(pending.status, "pending")

    def test_expired_action_is_marked_expired(self):
        store = self.make_store()
        store.get_pending(123)
        store.save_pending("action-2", 123, {"action": "eliminar_evento"})
        store.service.values_api.rows[1][3] = "2000-01-01T00:00:00-05:00"

        self.assertIsNone(store.get_pending(123))
        self.assertEqual(store.service.values_api.rows[1][5], "expired")

    def test_internal_read_limit_stops_requests(self):
        store = self.make_store()
        now = time.monotonic()
        store._reads.extend([now] * MAX_READS_PER_MINUTE)

        with self.assertRaises(StoreRateLimitError):
            store.get_pending(123)


class ActionPreparationTests(unittest.TestCase):
    def test_create_action_requires_valid_ordered_times(self):
        action = GeminiClient._prepare_calendar_action(
            "crear_evento",
            {"titulo": "Parcial", "fecha_inicio": "2026-10-07T10:00:00", "fecha_fin": "2026-10-07T11:00:00"},
            None,
        )
        self.assertEqual(action["action"], "crear_evento")
        self.assertEqual(action["title"], "Parcial")
        self.assertTrue(action["start"].endswith("-05:00"))

        with self.assertRaises(ValueError):
            GeminiClient._prepare_calendar_action(
                "crear_evento",
                {"titulo": "Parcial", "fecha_inicio": "2026-10-07T11:00:00", "fecha_fin": "2026-10-07T10:00:00"},
                None,
            )

    def test_ambiguous_event_is_not_proposed_for_mutation(self):
        calendar = SimpleNamespace(
            find_events_by_title=lambda _title: [
                {"id": "one", "title": "Dentista", "display": "*mar 07/10 10:00* — Dentista"},
                {"id": "two", "title": "Dentista", "display": "*jue 09/10 10:00* — Dentista"},
            ]
        )
        response = GeminiClient._prepare_calendar_action(
            "eliminar_evento", {"titulo_aproximado": "dentista"}, calendar
        )
        self.assertIsInstance(response, str)
        self.assertIn("varios eventos", response)


class GeminiRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_calendar_change_always_asks_for_confirmation(self):
        response = SimpleNamespace(
            text=(
                '{"action":"crear_evento","params":{"titulo":"Parcial",'
                '"fecha_inicio":"2026-10-07T10:00:00-05:00",'
                '"fecha_fin":"2026-10-07T11:00:00-05:00"},'
                '"confirmacion_requerida":false}'
            )
        )
        client = object.__new__(GeminiClient)
        client.model = SimpleNamespace(generate_content=Mock(return_value=response))
        store = SimpleNamespace(save_pending=Mock())

        message = await client.process_request("crea un parcial", object(), store, 123)

        self.assertIn("Responde *sí* para confirmar", message)
        store.save_pending.assert_called_once()
        self.assertEqual(store.save_pending.call_args.args[1], 123)
        self.assertEqual(store.save_pending.call_args.args[2]["action"], "crear_evento")

    async def test_change_is_refused_when_confirmation_storage_is_unavailable(self):
        response = SimpleNamespace(
            text=(
                '{"action":"crear_evento","params":{"titulo":"Parcial",'
                '"fecha_inicio":"2026-10-07T10:00:00-05:00",'
                '"fecha_fin":"2026-10-07T11:00:00-05:00"}}'
            )
        )
        client = object.__new__(GeminiClient)
        client.model = SimpleNamespace(generate_content=Mock(return_value=response))

        message = await client.process_request("crea un parcial", object(), None, 123)

        self.assertIn("No hice cambios", message)


class TelegramConfirmationTests(unittest.IsolatedAsyncioTestCase):
    def make_pending(self, action, status="pending"):
        return SimpleNamespace(
            row_number=2,
            action_id="action-3",
            user_id=123,
            action=action,
            status=status,
        )

    def make_update_context(self, text, store):
        message = SimpleNamespace(text=text, reply_text=AsyncMock())
        user = SimpleNamespace(id=123, username="samuel", first_name="Samuel")
        update = SimpleNamespace(
            message=message,
            effective_user=user,
            effective_chat=SimpleNamespace(id=123),
        )
        context = SimpleNamespace(
            application=SimpleNamespace(bot_data={"confirmation_store": store}),
            user_data={},
            bot=SimpleNamespace(send_chat_action=AsyncMock()),
        )
        return update, context

    async def test_yes_executes_saved_action_and_marks_complete(self):
        action = {"action": "crear_evento", "title": "Parcial", "start": "2026-10-07T10:00:00-05:00", "end": "2026-10-07T11:00:00-05:00", "description": ""}
        pending = self.make_pending(action)
        store = SimpleNamespace(
            get_pending=lambda _user_id: pending,
            set_status=Mock(),
        )
        calendar = SimpleNamespace(
            find_event_by_action_id=lambda _action_id: None,
            create_event=Mock(),
        )
        update, context = self.make_update_context("sí", store)

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USER_ID": "123", "GOOGLE_CONFIRMATIONS_SPREADSHEET_ID": "private-sheet"}), patch.object(bot, "CalendarClient", return_value=calendar):
            await bot.handle_message(update, context)

        calendar.create_event.assert_called_once_with(
            "Parcial", action["start"], action["end"], "", "action-3"
        )
        self.assertEqual(store.set_status.call_args_list[0].args[1], "executing")
        self.assertEqual(store.set_status.call_args_list[-1].args[1], "completed")
        self.assertIn("Evento creado", update.message.reply_text.await_args.args[0])

    async def test_no_cancels_without_calling_calendar(self):
        pending = self.make_pending({"action": "crear_evento"})
        store = SimpleNamespace(
            get_pending=lambda _user_id: pending,
            set_status=Mock(),
        )
        update, context = self.make_update_context("no", store)

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USER_ID": "123", "GOOGLE_CONFIRMATIONS_SPREADSHEET_ID": "private-sheet"}), patch.object(bot, "CalendarClient") as calendar_class:
            await bot.handle_message(update, context)

        calendar_class.assert_not_called()
        store.set_status.assert_called_once_with(2, "cancelled")
        self.assertIn("Acción cancelada", update.message.reply_text.await_args.args[0])

    async def test_other_telegram_user_is_rejected(self):
        store = SimpleNamespace(get_pending=AsyncMock())
        update, context = self.make_update_context("sí", store)
        update.effective_user.id = 456

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USER_ID": "123", "GOOGLE_CONFIRMATIONS_SPREADSHEET_ID": "private-sheet"}):
            await bot.handle_message(update, context)

        store.get_pending.assert_not_called()


if __name__ == "__main__":
    unittest.main()
