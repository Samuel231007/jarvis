"""
Punto de entrada principal de JARVIS.
Arranca el servidor Flask (para el webhook de Telegram) usando gunicorn en Render.
"""
import os
import logging
import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import Lock, Thread
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
_bot_loop = None
_bot_loop_thread = None
_bot_thread_lock = Lock()
_bot_init_lock = None


async def get_initialized_bot():
    """Inicializa la app del bot de Telegram de forma asíncrona para modo webhook."""
    global bot_app, _bot_initialized, _bot_init_lock
    if _bot_init_lock is None:
        _bot_init_lock = asyncio.Lock()
    async with _bot_init_lock:
        if bot_app is None:
            bot_app = create_bot()
        if not _bot_initialized:
            await bot_app.initialize()
            await bot_app.start()
            _bot_initialized = True
        return bot_app


def _run_bot_loop(loop):
    """Mantiene un ciclo de Telegram vivo durante el proceso web."""
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _ensure_bot_loop():
    """Crea de forma segura el hilo y ciclo persistente del bot."""
    global _bot_loop, _bot_loop_thread
    with _bot_thread_lock:
        if _bot_loop_thread is None or not _bot_loop_thread.is_alive():
            _bot_loop = asyncio.new_event_loop()
            _bot_loop_thread = Thread(
                target=_run_bot_loop,
                args=(_bot_loop,),
                name="jarvis-telegram-loop",
                daemon=True,
            )
            _bot_loop_thread.start()
        return _bot_loop


def _run_on_bot_loop(coroutine, timeout=120):
    """Envía trabajo asíncrono al ciclo persistente desde Flask WSGI."""
    loop = _ensure_bot_loop()
    future = asyncio.run_coroutine_threadsafe(coroutine, loop)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        future.cancel()
        raise


@app.route("/", methods=["GET"])
def health_check():
    """Endpoint de salud — Render lo usa para saber si el servicio está vivo."""
    return "JARVIS está activo ✅", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Endpoint que recibe las actualizaciones de Telegram.
    Telegram llama aquí cada vez que Samuel escribe un mensaje.
    """
    try:
        from telegram import Update

        data = request.get_json(force=True)
        current_bot = _run_on_bot_loop(get_initialized_bot())
        update = Update.de_json(data, current_bot.bot)
        _run_on_bot_loop(current_bot.process_update(update))
    except Exception as e:
        logger.error("Error procesando actualización de webhook: %s", e, exc_info=True)

    return "OK", 200


@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    """Configura automáticamente el Webhook de Telegram al abrir esta URL en el navegador."""
    # Detecta automáticamente la URL pública o usa la variable de entorno
    detected_url = request.host_url.replace("http://", "https://").rstrip("/")
    webhook_url = os.environ.get("WEBHOOK_URL", "").strip() or detected_url

    target_url = f"{webhook_url.rstrip('/')}/webhook"
    async def configure_webhook():
        current_bot = await get_initialized_bot()
        return await current_bot.bot.set_webhook(url=target_url)

    success = _run_on_bot_loop(configure_webhook())

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
