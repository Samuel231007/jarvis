# JARVIS — Asistente Personal de Samuel 🤖

Asistente personal que conecta Telegram, Google Calendar y la API de Gemini.
Habla en español, entiende lenguaje natural y gestiona tu agenda.

## Qué puede hacer

- Ver tus próximos eventos: *«¿Qué tengo esta semana?»*
- Crear eventos: *«Agrega partido de fútbol el sábado a las 4pm»*
- Mover eventos: *«Pasa el dentista al viernes»*
- Eliminar eventos: *«Cancela la reunión del martes»*

## Tecnologías configuradas

| Componente | Servicio | Costo |
|------------|----------|-------|
| Mensajería | Telegram Bot API | No se agrega un servicio de pago |
| IA / NLP | Gemini API, modelo `gemini-3.8-flash` | Se usa la capa gratuita disponible; sus límites y modelos pueden cambiar |
| Calendario | Google Calendar API | La configuración actual usa OAuth2 |
| Hosting | Render (configuración preparada) | El costo y la continuidad deben verificarse antes de depender de él |

La regla del proyecto es mantener el costo total en $0. No habilites facturación ni un plan de pago para resolver límites. Si una opción exige tarjeta o puede generar cargos, detén el despliegue y consulta a Samuel.

## Estado conocido de la base

- El bot admite el ID de Telegram configurado y puede consultar Google Calendar.
- Para cambios del calendario, el bot pide confirmación y guarda la propuesta durante 10 minutos en una hoja dedicada. Hace falta configurar `GOOGLE_CONFIRMATIONS_SPREADSHEET_ID` y volver a autorizar Google con el permiso limitado `drive.file` antes de usar ese flujo.
- El texto enviado por Samuel se transmite a Gemini para interpretarlo. No envíes contraseñas, documentos de identidad, números de cuenta ni otros datos sensibles.
- La integración usa la biblioteca `google-generativeai`, que Google considera heredada y recomienda migrar a `google-genai` antes de ampliar la integración con Gemini.
- La configuración del webhook existe; el modo de ejecución/hosting debe revisarse según la fase y las reglas de costo $0.

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
| `credentials.json` | Google Cloud Console → APIs → Google Calendar API y Google Sheets API → Credenciales OAuth2 |

### 4. Autorizar Google Calendar (primera vez)

```bash
python -c "from src.calendar_client import CalendarClient; CalendarClient()"
```

Se abrirá el navegador para que autorices. Esto crea `token.json` localmente.

La autorización ahora incluye Calendar y el permiso `drive.file`, usado para el archivo dedicado de confirmaciones. En Google Cloud Console habilita también Google Sheets API en el mismo proyecto. Si ya tenías un `token.json` anterior, vuelve a autorizar antes de usar las confirmaciones. En Render, actualiza `GOOGLE_TOKEN_JSON` con el token nuevo desde el panel de variables; no lo pegues en el código ni en Git.

### 5. Preparar la hoja privada de confirmaciones

1. Crea en la misma cuenta de Google una hoja privada llamada `JARVIS Confirmaciones`.
2. Añade una pestaña llamada `Pendientes`; la primera fila puede dejarse vacía, el bot pondrá sus encabezados.
3. Copia el ID entre `/d/` y `/edit` de la URL y guárdalo como `GOOGLE_CONFIRMATIONS_SPREADSHEET_ID` en `.env` y en las variables del hosting.

El bot limita sus propias lecturas y escrituras de esta hoja a 10 por minuto por proceso y no reintenta si Google rechaza una solicitud por cuota. Google indica que el uso estándar de Sheets no tiene costo adicional y advierte que exceder cuotas podría generar cargos más adelante en 2026; mantén bajo el uso y no habilites facturación para resolver límites.

### 6. Probar en local (modo polling)

```bash
python main.py
```

## Seguridad

- Solo el ID de Telegram configurado puede usar el bot
- Las credenciales nunca se suben a GitHub (`.gitignore`)
- Se pide confirmación antes de crear, mover o borrar eventos
- No escribas contraseñas, documentos de identidad ni números de cuenta o tarjeta en el chat; los mensajes se envían a Gemini para interpretarlos.

## Zona horaria

`America/Bogota` (UTC-5)
