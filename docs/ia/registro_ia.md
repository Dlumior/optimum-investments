# Registro de uso de IA

Herramienta: Claude Code con configuración del proyecto (`CLAUDE.md`, `.claude/skills`, `.claude/agents`, hooks).
Todos los prompts se guardan automáticamente en `prompts.jsonl`; aquí se seleccionan los principales.
`python scripts/ia_log_to_tex.py` genera el anexo LaTeX.

<!-- Formato de cada entrada (no cambiar: el script lo parsea)
## P01 · AAAA-MM-DD · Tema
**Prompt:** ...
**Resultado:** Aceptado | Corregido | Descartado
**Detalle:** ...
-->

## P01 · 2026-09-27 · Estructura del proyecto
**Prompt:** Estructurar un proyecto Python con notebooks, datos crudos/intermedios/procesados, utilidades de figuras, informe LaTeX con Docker y un espacio para Claude Code con skills y arneses.
**Resultado:** Aceptado
**Detalle:** Se generó el andamiaje, el pipeline de limpieza con validaciones y el contrato JSON. La lógica financiera (valorización, riesgo, optimizador) quedó sin implementar a propósito.

# Errores y simplificaciones de la IA detectados (mínimo 2 para la entrega)

<!-- ## E01 · fecha · Tema
**Prompt:** qué se pidió
**Resultado:** Corregido
**Detalle:** qué propuso la IA, por qué estaba mal, cómo se detectó (test/auditor/revisión), cómo se corrigió -->
