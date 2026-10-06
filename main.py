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
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# En modo webhook (Render/Gunicorn), bot_app se inicializa bajo demanda
bot_app = None

def get_bot_app():
    global bot_app
    if bot_app is None:
        bot_app = create_bot()
    return bot_app


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

    current_bot = get_bot_app()
    update = Update.de_json(data, current_bot.bot)
    await current_bot.process_update(update)

    return "OK", 200


@app.route("/set_webhook", methods=["GET"])
async def set_webhook():
    """Configura automáticamente el Webhook de Telegram al abrir esta URL en el navegador."""
    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
    if not webhook_url:
        return (
            "⚠️ No has configurado la variable WEBHOOK_URL en el panel de Render.<br>"
            "Agrega la URL pública de tu servicio (ejemplo: https://mi-jarvis.onrender.com) en Environment y reintenta.",
            400,
        )

    target_url = f"{webhook_url.rstrip('/')}/webhook"
    current_bot = get_bot_app()
    success = await current_bot.bot.set_webhook(url=target_url)

    if success:
        return (
            f"🎉 <b>¡Webhook configurado con éxito!</b><br>"
            f"JARVIS está conectado a Telegram 24/7 en: <code>{target_url}</code>",
            200,
        )
    return "❌ Telegram no aceptó el webhook. Verifica el token y la URL.", 500


def acquire_single_instance_lock(port: int = 49999):
    """Evita ejecutar dos instancias del bot al mismo tiempo en la misma PC."""
    import socket
    import sys
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", port))
        return sock
    except OSError:
        print("\n" + "=" * 65)
        print("⚠️  AVISO: Ya tienes otra ventana de JARVIS corriendo en tu PC.")
        print("   Ciérrala o presiona Ctrl + C en esa ventana antes de abrir otra.")
        print("=" * 65 + "\n")
        sys.exit(0)


if __name__ == "__main__":
    # Solo para desarrollo local con polling (sin webhook)
    _lock = acquire_single_instance_lock()
    from src.bot import run_polling
    run_polling()
