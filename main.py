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

bot_app = None
_bot_initialized = False


async def get_initialized_bot():
    """Inicializa la app del bot de Telegram de forma asíncrona para modo webhook."""
    global bot_app, _bot_initialized
    if bot_app is None:
        bot_app = create_bot()
    if not _bot_initialized:
        await bot_app.initialize()
        await bot_app.start()
        _bot_initialized = True
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
    from telegram import Update

    data = request.get_json(force=True)
    current_bot = await get_initialized_bot()
    update = Update.de_json(data, current_bot.bot)
    await current_bot.process_update(update)

    return "OK", 200


@app.route("/set_webhook", methods=["GET"])
async def set_webhook():
    """Configura automáticamente el Webhook de Telegram al abrir esta URL en el navegador."""
    # Detecta automáticamente la URL pública o usa la variable de entorno
    detected_url = request.host_url.replace("http://", "https://").rstrip("/")
    webhook_url = os.environ.get("WEBHOOK_URL", "").strip() or detected_url

    target_url = f"{webhook_url.rstrip('/')}/webhook"
    current_bot = await get_initialized_bot()
    success = await current_bot.bot.set_webhook(url=target_url)

    if success:
        return (
            f"<h2>🎉 ¡Webhook configurado con éxito!</h2>"
            f"<p>JARVIS está conectado a Telegram 24/7 en:<br><code>{target_url}</code></p>"
            f"<p><b>¡Ya puedes abrir Telegram y escribirle a JARVIS desde cualquier lugar!</b></p>",
            200,
        )
    return "❌ Telegram no aceptó el webhook. Verifica el token del bot.", 500


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
