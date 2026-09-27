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

## P02 · 2026-09-27 · uv, git init y corrección del caso asignado
**Prompt:** "usemos uv para el proyecto"; "inicializa git"; "El caso que me toca resolver es el C".
**Resultado:** Aceptado
**Detalle:** `make setup` pasó de `venv`+`pip` a `uv venv`+`uv pip install`. Se inicializó el repo git con commit inicial.
`config/caso.yaml` tenía `caseId: "B"` como placeholder de la plantilla (comentario "CAMBIAR al caso asignado");
se corrigió a `C` y `riskMeasure: CVAR`, se regeneró `input.json` y se fijó `bootstrapCount: 500` (sin valor por
defecto en `Case_Assumptions`, mínimo exigido: 100) — documentado en `docs/decisiones.md` D-05.

# Errores y simplificaciones de la IA detectados (mínimo 2 para la entrega)

<!-- ## E01 · fecha · Tema
**Prompt:** qué se pidió
**Resultado:** Corregido
**Detalle:** qué propuso la IA, por qué estaba mal, cómo se detectó (test/auditor/revisión), cómo se corrigió -->
