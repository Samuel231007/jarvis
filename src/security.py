"""
Capa de seguridad: solo Samuel puede usar el bot.
Si alguien más escribe, el bot ignora el mensaje y registra el intento.
"""
import os
import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def only_samuel(handler):
    """
    Decorador que bloquea cualquier usuario que no sea Samuel.
    Aplica a todos los handlers del bot.
    """
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user:
            return

        raw_allowed = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
        allowed_id = int(raw_allowed) if raw_allowed else 0
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name

        logger.info("📩 Mensaje recibido de '%s' (ID Telegram: %d)", username, user_id)

        if user_id != allowed_id:
            logger.warning(
                "🚨 ACCESO DENEGADO: El usuario '%s' tiene ID [%d], pero en tu archivo .env está configurado TELEGRAM_ALLOWED_USER_ID=[%d]",
                username,
                user_id,
                allowed_id,
            )
            # Durante la fase de desarrollo/setup, informamos por consola
            return

        logger.info("✅ Usuario autorizado [%d]. Procesando solicitud...", user_id)
        return await handler(update, context, *args, **kwargs)

    return wrapper
