# JARVIS — Asistente Personal de Samuel 🤖

Asistente personal que conecta Telegram, Google Calendar y la API de Gemini.
Habla en español, entiende lenguaje natural y gestiona tu agenda.

## Qué puede hacer

- Ver tus próximos eventos: *«¿Qué tengo esta semana?»*
- Crear eventos: *«Agrega partido de fútbol el sábado a las 4pm»*
- Mover eventos: *«Pasa el dentista al viernes»*
- Eliminar eventos: *«Cancela la reunión del martes»*

## Tecnologías (todas gratuitas)

| Componente | Servicio | Costo |
|------------|----------|-------|
| Mensajería | Telegram Bot API | Gratis |
| IA / NLP | Gemini 1.5 Flash (Google AI Studio) | Gratis |
| Calendario | Google Calendar API | Gratis |
| Hosting | Render (free tier) | Gratis |

## Configuración local (para desarrollo)

### 1. Clonar y preparar el entorno

```bash
git clone https://github.com/Samuel231007/jarvis.git
cd jarvis
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

### 2. Crear el archivo .env

```bash
copy .env.example .env
# Editar .env con tus credenciales reales
```

### 3. Credenciales necesarias

| Variable | Cómo obtenerla |
|----------|----------------|
| `TELEGRAM_BOT_TOKEN` | Escríbele a [@BotFather](https://t.me/BotFather) en Telegram → `/newbot` |
| `TELEGRAM_ALLOWED_USER_ID` | Escríbele a [@userinfobot](https://t.me/userinfobot) en Telegram |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) → "Create API key" |
| `credentials.json` | Google Cloud Console → APIs → Google Calendar API → Credenciales OAuth2 |

### 4. Autorizar Google Calendar (primera vez)

```bash
python -c "from src.calendar_client import CalendarClient; CalendarClient()"
```

Se abrirá el navegador para que autorices. Esto crea `token.json` localmente.

### 5. Probar en local (modo polling)

```bash
python main.py
```

## Seguridad

- Solo el ID de Telegram configurado puede usar el bot
- Las credenciales nunca se suben a GitHub (`.gitignore`)
- Se pide confirmación antes de crear, mover o borrar eventos
- No se envían datos sensibles a la IA

## Zona horaria

`America/Bogota` (UTC-5)
