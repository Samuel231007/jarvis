"""
Módulo principal del bot de Telegram.
Registra los handlers y controla el acceso solo al usuario autorizado.
"""
import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from src.security import only_samuel
from src.gemini_client import GeminiClient
from src.calendar_client import CalendarClient

logger = logging.getLogger(__name__)


def create_bot() -> Application:
    """Construye y configura la aplicación del bot."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    application = Application.builder().token(token).build()

    # Registrar handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("ayuda", cmd_help))
    application.add_handler(CommandHandler("agenda", cmd_agenda))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Bot configurado correctamente")
    return application


def run_polling():
    """Modo polling para pruebas locales (no se usa en Render)."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("ayuda", cmd_help))
    application.add_handler(CommandHandler("agenda", cmd_agenda))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

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
    """Muestra los próximos 7 días del calendario."""
    await update.message.reply_text("📅 Consultando tu agenda...")

    try:
        calendar = CalendarClient()
        events = calendar.get_upcoming_events(days=7)

        if not events:
            await update.message.reply_text("No tienes eventos en los próximos 7 días 🎉")
            return

        lines = ["📅 *Tu agenda — próximos 7 días:*\n"]
        for event in events:
            lines.append(f"• {event['display']}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.error("Error al consultar el calendario: %s", e)
        await update.message.reply_text(
            "❌ No pude consultar el calendario. Revisa que las credenciales estén configuradas."
        )


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
