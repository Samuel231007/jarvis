"""
Módulo principal del bot de Telegram.
Registra los handlers y controla el acceso solo al usuario autorizado.
"""
import os
import logging
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

logger = logging.getLogger(__name__)


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

    # Registrar handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("ayuda", cmd_help))
    application.add_handler(CommandHandler("agenda", cmd_agenda))
    application.add_handler(CallbackQueryHandler(handle_agenda_callback, pattern=r"^agenda:"))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_error_handler(on_error)

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

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("ayuda", cmd_help))
    application.add_handler(CommandHandler("agenda", cmd_agenda))
    application.add_handler(CallbackQueryHandler(handle_agenda_callback, pattern=r"^agenda:"))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_error_handler(on_error)

    logger.info("Arrancando en modo polling (desarrollo local)...")
    application.run_polling()


# ──────────────────────────────────────────────
# Handlers de comandos
# ──────────────────────────────────────────────

@only_samuel
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saluda a Samuel al iniciar el bot."""
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
    await update.message.reply_text(
        "📋 *Comandos disponibles:*\n\n"
        "/start — Saludo inicial\n"
        "/ayuda — Esta lista\n"
        "/agenda — Ver eventos de los próximos 7 días\n\n"
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
    logger.info("Mensaje recibido: %s", user_text)

    # Indicador de escritura mientras se procesa
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    try:
        gemini = GeminiClient()
        calendar = CalendarClient()
        response = await gemini.process_request(user_text, calendar)
        await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.error("Error procesando mensaje: %s", e)
        await update.message.reply_text(
            "❌ Ocurrió un error al procesar tu mensaje. Intenta de nuevo."
        )
