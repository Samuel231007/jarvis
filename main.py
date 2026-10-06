"""
Punto de entrada principal de JARVIS.
Arranca el servidor Flask (para el webhook de Telegram) usando gunicorn en Render.
"""
import os
import logging
from flask import Flask, request
from dotenv import load_dotenv
from src.bot import create_bot

# Cargar variables de entorno desde .env (solo en local; en Render se configuran en el dashboard)
load_dotenv()

# Configurar logging básico
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Crear la instancia del bot (se inicializa una sola vez)
bot_app = create_bot()


@app.route("/", methods=["GET"])
def health_check():
    """Endpoint de salud — Render lo usa para saber si el servicio está vivo."""
    return "JARVIS está activo ✅", 200


@app.route("/webhook", methods=["POST"])
async def webhook():
    """
    Endpoint que recibe las actualizaciones de Telegram.
    Telegram llama aquí cada vez que Samuel escribe un mensaje.
    """
    import json
    from telegram import Update

    data = request.get_json(force=True)
    logger.info("Actualización recibida de Telegram")

    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)

    return "OK", 200


if __name__ == "__main__":
    # Solo para desarrollo local con polling (sin webhook)
    from src.bot import run_polling
    run_polling()
