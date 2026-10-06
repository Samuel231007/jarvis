# AGENTS.md — Proyecto Jarvis

Asistente personal para Samuel (Telegram + Google Calendar + Gemini API gratuita). El plan completo está en `JARVIS_PLAN.md`: **léelo entero antes de empezar y trabaja por fases, empezando por la Fase 0.**

## Reglas permanentes

1. **Todo gratis, siempre.** No usar ni sugerir nada que cobre, pida pago o sea una prueba gratuita que vence. Si un servicio "gratuito" pide tarjeta, aunque sea solo para verificar, detente y consulta a Samuel.
2. **Consulta las decisiones, no las tomes solo.** Ante opciones reales (servicio, herramienta, diseño que cambia el comportamiento, riesgo), para y pregunta. Formato: qué hay que decidir, 2 o 3 opciones, qué implica cada una en costo, esfuerzo y riesgo, tu recomendación. Una decisión a la vez.
3. **Explica en términos de decisión, sin jerga.** Samuel cursa 3.er semestre; el detalle técnico solo si lo pide.
4. **Mientras esperas respuesta**, avanza en lo que no dependa de esa decisión.
5. **Verifica los límites vigentes** de cualquier servicio gratuito en su documentación oficial antes de depender de él.
6. **Secretos fuera del código:** solo en `.env`; `.gitignore` desde el primer commit; `.env.example` sin valores.
7. **Pasos pequeños.** Cada fase termina con algo que Samuel pueda probar y con sus criterios de aceptación revisados. No pases a la siguiente fase sin su visto bueno.
8. **Al cerrar cada fase**, resume en lenguaje simple qué se hizo, qué puede probar y qué sigue.
9. **Idioma:** habla con Samuel en español. Código con nombres en inglés; comentarios, README y mensajes del asistente en español.

## Seguridad

- El bot solo atiende el ID de Telegram de Samuel.
- Confirmación obligatoria antes de crear, mover o borrar eventos.
- No enviar datos sensibles (contraseñas, documentos) a la IA: la capa gratuita puede usar lo enviado para mejorar productos de Google.
- Zona horaria: America/Bogota.

## Alcance de trabajo acordado: Fases 0, 1 y 2

Samuel indicó que la Fase 1 debe cubrir tanto completar la gestión de agenda como estabilizar las consultas y la seguridad; después seguirá la Fase 2. Los detalles de interacción que aparecen como pregunta quedan pendientes de su respuesta.

### Fase 0 — Revisión de la base

- Leer el código, configuración y documentación antes de cambiar la arquitectura.
- Confirmar qué archivos tienen secretos y que no estén versionados.
- Registrar brechas existentes sin reescribir funciones que ya sirven.
- Corregir documentación que describa capacidades, modelos o costos de forma obsoleta.

**Criterio de salida:** Samuel revisa la lista de capacidades y brechas de la base antes de dar por cerrada la fase.

### Fase 1 — Agenda confiable y segura

- Mantener la consulta de agenda y restringir todas las interacciones al ID de Telegram configurado.
- Completar el flujo de creación, movimiento y eliminación: mostrar la operación exacta, pedir confirmación explícita, ejecutar solo tras una respuesta afirmativa y cancelar ante una negativa, una solicitud nueva o una confirmación vencida.
- Si la petición es ambigua, pedir aclaración y no modificar el calendario.
- Mantener los comandos deterministas separados de la interpretación con IA cuando se definan los comandos de esta fase.
- No enviar datos sensibles a Gemini y no registrar el contenido de mensajes o credenciales en logs.
- La confirmación pendiente vale hasta 10 minutos y debe sobrevivir al reinicio del bot; la ubicación de ese estado todavía está por decidir.

**Criterios de aceptación propuestos:** consultas válidas responden; crear/mover/borrar no modifica nada antes de confirmar; confirmar ejecuta solo la operación mostrada; cancelar o dejar vencer no hace cambios; otro usuario no obtiene respuesta ni puede operar el calendario.

**Decisiones registradas:** Samuel eligió conservar la confirmación pendiente al reiniciar, con vencimiento máximo de 10 minutos, y guardarla en una hoja de Google dedicada con un límite interno estricto de uso.

**Protección de costo registrada:** el bot limita sus propias lecturas y escrituras de Sheets a 10 por minuto por proceso, y no reintenta ante rechazo por cuota. La API requiere el permiso `drive.file`, limitado al archivo usado por la aplicación. La documentación oficial dice que el uso estándar no tiene costo adicional, pero advierte que exceder cuotas podría generar cargos más adelante en 2026. No habilitar facturación para resolver límites.

**Estado:** hay cambios preparados para la Fase 1, pero no se considera aprobada hasta configurar la hoja, renovar OAuth, hacer las pruebas de aceptación y recibir el visto bueno de Samuel. La Fase 2 no comienza antes de ese visto bueno.

### Fase 2 — Recordatorios y resumen matutino

- Añadir recordatorios nativos de Google Calendar a eventos creados por el bot.
- Revisar cada minuto los próximos eventos y avisar por Telegram una sola vez por evento y aviso.
- Evitar avisos duplicados tras reinicios.
- Enviar el resumen diario a la hora acordada por Samuel.
- Incluir botones «Hecho», «Recuérdamelo en 1 hora» y «Mañana»; queda por decidir qué efecto tiene «Hecho» y cómo se registran los aplazamientos.

**Criterios de aceptación:** un recordatorio de prueba llega a la hora y una sola vez; el resumen llega a la hora elegida; tras reiniciar no se repiten avisos anteriores.

**Decisiones pendientes para cerrar el diseño de Fase 2:** hora del resumen; qué eventos generan aviso; significado de «Hecho»; si el resumen se envía también fines de semana; y dónde guardar las marcas de envío para que sobrevivan al reinicio sin costo.
