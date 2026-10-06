"""
Módulo principal del bot de Telegram.
Registra los handlers y controla el acceso solo al usuario autorizado.
"""
import os
import logging
import asyncio
import re
import unicodedata
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.request import HTTPXRequest
from src.security import only_samuel
from src.gemini_client import GeminiClient
from src.calendar_client import CalendarClient
from src.confirmation_store import ConfirmationStore, StoreRateLimitError

logger = logging.getLogger(__name__)


def _register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("ayuda", cmd_help))
    application.add_handler(CommandHandler("agenda", cmd_agenda))
    application.add_handler(CommandHandler("cancelar", cmd_cancel))
    application.add_handler(
        CallbackQueryHandler(handle_agenda_callback, pattern=r"^agenda:")
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(on_error)


def _get_confirmation_store(context: ContextTypes.DEFAULT_TYPE) -> ConfirmationStore:
    store = context.application.bot_data.get("confirmation_store")
    if store is None:
        store = ConfirmationStore()
        context.application.bot_data["confirmation_store"] = store
    return store


def _confirmation_answer(text: str) -> bool | None:
    normalized = unicodedata.normalize("NFKD", text.lower().strip())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized = " ".join(normalized.split())
    if normalized in {"si", "confirmar", "confirmo", "dale", "de acuerdo"}:
        return True
    if normalized in {"no", "cancelar", "cancela", "mejor no"}:
        return False
    return None


async def _cancel_pending_for_new_request(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    if not os.environ.get("GOOGLE_CONFIRMATIONS_SPREADSHEET_ID", "").strip():
        return
    try:
        store = _get_confirmation_store(context)
        pending = await asyncio.to_thread(store.get_pending, user_id)
        if pending and context.user_data.get("confirmation_executing") != pending.action_id:
            await asyncio.to_thread(store.set_status, pending.row_number, "replaced")
        context.user_data["pending_confirmation"] = False
    except Exception:
        logger.exception("No se pudo revisar la confirmación pendiente")


def _get_request_config() -> HTTPXRequest:
    """Configura timeouts más amplios para evitar caídas por latencia de red."""
    return HTTPXRequest(
        connection_pool_size=10,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
    )


def create_bot() -> Application:
    """Construye y configura la aplicación del bot."""
    token = os.environ["TELEGRAM_BOT_TOKEN"].strip()

    application = (
        Application.builder()
        .token(token)
        .request(_get_request_config())
        .build()
    )

    _register_handlers(application)

    logger.info("Bot configurado correctamente")
    return application


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Registra cualquier excepción no controlada."""
    logger.error("❌ Excepción no controlada en el bot:", exc_info=context.error)


def run_polling():
    """Modo polling para pruebas locales (no se usa en Render)."""
    token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    application = (
        Application.builder()
        .token(token)
        .request(_get_request_config())
        .build()
    )

    _register_handlers(application)

    logger.info("Arrancando en modo polling (desarrollo local)...")
    application.run_polling()


# ──────────────────────────────────────────────
# Handlers de comandos
# ──────────────────────────────────────────────

@only_samuel
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saluda a Samuel al iniciar el bot."""
    await _cancel_pending_for_new_request(context, update.effective_user.id)
    await update.message.reply_text(
        "¡Hola, Samuel! Soy JARVIS, tu asistente personal 🤖\n\n"
        "Puedo ayudarte con tu agenda de Google Calendar.\n"
        "Escríbeme en lenguaje natural, por ejemplo:\n"
        "  • «¿Qué tengo mañana?»\n"
        "  • «Agrega reunión el viernes a las 3pm»\n"
        "  • «Mueve el dentista al lunes»\n\n"
        "Escribe /ayuda para ver todos los comandos."
    )


@only_samuel
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los comandos disponibles."""
    await _cancel_pending_for_new_request(context, update.effective_user.id)
    await update.message.reply_text(
        "📋 *Comandos disponibles:*\n\n"
        "/start — Saludo inicial\n"
        "/ayuda — Esta lista\n"
        "/agenda — Ver eventos de los próximos 7 días\n\n"
        "/cancelar — Cancelar una acción pendiente\n\n"
        "También puedes escribirme directamente en español 🇨🇴",
        parse_mode="Markdown"
    )


@only_samuel
async def cmd_agenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Permite consultar la agenda por intervalo.
    Si se escribe sin argumentos: muestra botones interactivos.
    Si se escribe con argumentos (ej: /agenda 3 o /agenda manana): responde directamente.
    """
    args = context.args
    await _cancel_pending_for_new_request(context, update.effective_user.id)

    # Si el usuario pasó argumentos (ej: /agenda 3, /agenda manana, /agenda hoy)
    if args:
        arg = args[0].lower()
        if arg in ("hoy", "today"):
            modo, dias = "hoy", 1
        elif arg in ("manana", "mañana", "tomorrow"):
            modo, dias = "manana", 1
        elif arg in ("semana", "week"):
            modo, dias = "semana", 7
        elif arg.isdigit():
            modo, dias = "dias", int(arg)
        else:
            modo, dias = "dias", 7

        await update.message.reply_text("📅 Consultando tu agenda...")
        try:
            calendar = CalendarClient()
            label, events = calendar.get_events(mode=modo, days=dias)
            if not events:
                await update.message.reply_text(
                    f"{label}\n\nNo tienes eventos registrados para este periodo 🎉",
                    parse_mode="Markdown"
                )
                return

            lines = [f"{label}\n"]
            for event in events:
                lines.append(f"• {event['display']}")

            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            logger.error("Error al consultar el calendario: %s", e)
            await update.message.reply_text("❌ No pude consultar el calendario.")
        return

    # Si no pasó argumentos: mostrar botones para que elija con un clic
    keyboard = [
        [
            InlineKeyboardButton("📅 Solo Hoy", callback_data="agenda:hoy:1"),
            InlineKeyboardButton("🌅 Solo Mañana", callback_data="agenda:manana:1"),
        ],
        [
            InlineKeyboardButton("📆 Siguientes 3 días", callback_data="agenda:dias:3"),
            InlineKeyboardButton("🗓️ Toda la semana", callback_data="agenda:semana:7"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "¿Qué periodo de tu agenda quieres consultar?",
        reply_markup=reply_markup,
    )


@only_samuel
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela una propuesta pendiente sin enviarla a Gemini."""
    try:
        store = _get_confirmation_store(context)
        pending = await asyncio.to_thread(store.get_pending, update.effective_user.id)
        if not pending:
            await update.message.reply_text("No tienes ninguna acción pendiente.")
            return
        if pending.status == "executing":
            await update.message.reply_text(
                "La acción ya se está procesando; no puedo cancelarla en este punto."
            )
            return
        await asyncio.to_thread(store.set_status, pending.row_number, "cancelled")
        context.user_data["pending_confirmation"] = False
        await update.message.reply_text("Acción cancelada. No hice cambios en el calendario.")
    except Exception:
        logger.exception("No se pudo cancelar la acción pendiente")
        await update.message.reply_text("No pude comprobar la acción pendiente. Intenta de nuevo.")


@only_samuel
async def handle_agenda_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la selección de los botones interactivos de /agenda."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    modo = parts[1] if len(parts) > 1 else "semana"
    dias = int(parts[2]) if len(parts) > 2 else 7

    try:
        calendar = CalendarClient()
        label, events = calendar.get_events(mode=modo, days=dias)

        if not events:
            text = f"{label}\n\nNo tienes eventos registrados para este periodo 🎉"
        else:
            lines = [f"{label}\n"]
            for event in events:
                lines.append(f"• {event['display']}")
            text = "\n".join(lines)

        await query.edit_message_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error("Error al consultar agenda desde botón: %s", e)
        await query.edit_message_text("❌ No se pudo consultar el calendario.")


# ──────────────────────────────────────────────
# Handler de mensajes de texto libres
# ──────────────────────────────────────────────

@only_samuel
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Procesa mensajes de texto enviados por Samuel.
    Pasa el mensaje a Gemini para interpretar la intención
    y ejecuta la acción correspondiente en el calendario.
    """
    user_text = update.message.text
    logger.info("Mensaje de texto recibido (longitud=%d)", len(user_text))

    answer = _confirmation_answer(user_text)
    store = None
    pending = None
    store_error = None
    if os.environ.get("GOOGLE_CONFIRMATIONS_SPREADSHEET_ID", "").strip():
        try:
            store = _get_confirmation_store(context)
            # Recupera estado al arrancar y vuelve a comprobarlo mientras haya una acción pendiente.
            if context.user_data.get("pending_confirmation") is not False:
                pending = await asyncio.to_thread(store.get_pending, update.effective_user.id)
                context.user_data["pending_confirmation"] = bool(pending)
        except StoreRateLimitError as e:
            await update.message.reply_text(
                "Alcancé el límite interno de consultas a la hoja. Espera un minuto y vuelve a intentarlo."
            )
            return
        except Exception as e:
            logger.exception("No se pudo leer la confirmación guardada")
            store_error = e

    if answer is not None:
        if store_error:
            await update.message.reply_text(
                "No pude consultar la confirmación guardada. Espera un momento y vuelve a intentarlo."
            )
            return
        if store is None:
            await update.message.reply_text(
                "No puedo revisar la confirmación: falta configurar la hoja privada de confirmaciones."
            )
            return
        if not pending:
            await update.message.reply_text("No tienes ninguna acción pendiente.")
            return
        if not answer:
            if pending.status == "executing":
                await update.message.reply_text(
                    "La operación ya empezó y no puedo cancelarla con seguridad. Responde «sí» para comprobar el resultado."
                )
                return
            await asyncio.to_thread(store.set_status, pending.row_number, "cancelled")
            context.user_data["pending_confirmation"] = False
            await update.message.reply_text("Acción cancelada. No hice cambios en el calendario.")
            return
        await _apply_pending_action(update, context, store, pending)
        return

    if pending:
        if pending.status == "executing":
            await update.message.reply_text(
                "Hay una operación confirmada cuyo resultado no pude guardar. Responde «sí» para comprobarla; no la sustituiré por otra solicitud."
            )
            return
        await asyncio.to_thread(store.set_status, pending.row_number, "replaced")
        context.user_data["pending_confirmation"] = False
    elif store_error:
        await update.message.reply_text(
            "No pude comprobar el estado de confirmaciones. Espera un momento y vuelve a intentarlo."
        )
        return

    # Indicador de escritura mientras se procesa
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    try:
        gemini = GeminiClient()
        calendar = CalendarClient()
        response = await gemini.process_request(
            user_text, calendar, store, update.effective_user.id
        )
        if "Responde *sí* para confirmar" in response and store:
            context.user_data["pending_confirmation"] = True
        await update.message.reply_text(response)

    except Exception as e:
        logger.error("Error procesando mensaje: %s", e)
        await update.message.reply_text(
            "❌ Ocurrió un error al procesar tu mensaje. Intenta de nuevo."
        )


async def _apply_pending_action(update, context, store, pending) -> None:
    """Ejecuta solo la operación persistida que Samuel acaba de confirmar."""
    context.user_data["confirmation_executing"] = pending.action_id
    try:
        await asyncio.to_thread(store.set_status, pending.row_number, "executing")
        action = pending.action
        calendar = CalendarClient()
        if action["action"] == "crear_evento":
            existing = await asyncio.to_thread(
                calendar.find_event_by_action_id, pending.action_id
            )
            if not existing:
                await asyncio.to_thread(
                    calendar.create_event,
                    action["title"],
                    action["start"],
                    action["end"],
                    action.get("description", ""),
                    pending.action_id,
                )
            result = "Evento creado en Google Calendar."
        elif action["action"] == "mover_evento":
            await asyncio.to_thread(
                calendar.move_event,
                action["event_id"],
                action["start"],
                action["end"],
            )
            result = f"Moví «{action['title']}» en Google Calendar."
        elif action["action"] == "eliminar_evento":
            await asyncio.to_thread(calendar.delete_event, action["event_id"])
            result = f"Eliminé «{action['title']}» de Google Calendar."
        else:
            raise ValueError("La operación pendiente no está permitida.")
        await asyncio.to_thread(store.set_status, pending.row_number, "completed")
        context.user_data["pending_confirmation"] = False
        await update.message.reply_text(result)
    except Exception:
        logger.exception("No se pudo completar la operación confirmada")
        try:
            await asyncio.to_thread(store.set_status, pending.row_number, "pending")
        except Exception:
            logger.exception("No se pudo actualizar el estado tras un error")
        await update.message.reply_text(
            "No pude confirmar el resultado. La operación queda pendiente durante el plazo restante; responde «sí» para reintentarlo."
        )
    finally:
        context.user_data.pop("confirmation_executing", None)
