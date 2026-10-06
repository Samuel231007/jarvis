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
        allowed_id = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
        user_id = update.effective_user.id

        if user_id != allowed_id:
            logger.warning(
                "Acceso denegado — usuario no autorizado: %s (ID: %d)",
                update.effective_user.username,
                user_id,
            )
            # No respondemos nada: el bot simplemente ignora al intruso
            return

        return await handler(update, context, *args, **kwargs)

    return wrapper
