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

## P03 · 2026-09-27 · Formulación base del Caso C (CVaR)
**Prompt:** "Dado que me tocó el caso C, cómo debo empezar"; "qué me recomiendas para la formulación"; "qué otras maneras hay de formularlo"; "vamos con lo acordado (versión base)".
**Resultado:** Aceptado
**Detalle:** La IA propuso un LP con CVaR en la forma de Rockafellar–Uryasev sobre una matriz de resultados por instrumento y escenario, obtenida por revalorización completa. También presentó alternativas (riesgo como restricción, cociente E/CVaR, PCA paramétrico, bootstrap por bloques, estrés como restricción dura, MILP) y el alumno eligió la versión base. Al revisar input.json se vio que las probabilidades de estrés ya vienen dadas (0.0125 c/u), lo que resolvió una de las preguntas que la IA había dejado abierta. Decisiones D-06 a D-12. El auditor-financiero encontró errores de la IA (E01–E03) y el alumno eligió: bloques 6×2, deriva mixta y tramos ON-1Y / 10Y-20Y con transición.

## P04 · 2026-09-27 · Valorizador por flujos (valuation.py)
**Prompt:** "sigamos con la valorización, muéstrame el plan"; "sí, vamos con (a), escribe los tests"; "sí, implementa valuation.py".
**Resultado:** Aceptado
**Detalle:** Plan → 18 tests (tests/test_valuation.py, escritos antes del código) → implementación. El alumno eligió la proyección plana del factor de referencia para los flotantes (D-13). Resultados: V0 = market_value_pen en los 12 instrumentos, spreads calibrados entre 0.34 y 0.64 pb por debajo de la hoja (sesgo sistemático, probablemente por una convención de conteo de días distinta en el Excel; la hoja es solo referencia), forwards recalculadas = Excel. La IA escribió el módulo de tests para que se omita mientras faltara la interfaz, porque el hook de cierre bloquea con tests en rojo. Pendiente: demo en el notebook 02 y auditoría.

# Errores y simplificaciones de la IA detectados (mínimo 2 para la entrega)

<!-- ## E01 · fecha · Tema
**Prompt:** qué se pidió
**Resultado:** Corregido
**Detalle:** qué propuso la IA, por qué estaba mal, cómo se detectó (test/auditor/revisión), cómo se corrigió -->

## E01 · 2026-09-27 · Bootstrap i.i.d. de 12 meses (D-09)
**Prompt:** Formulación base del Caso C.
**Resultado:** Corregido
**Detalle:** La IA propuso sumar 12 meses sorteados i.i.d. y descartó el bootstrap por bloques con un argumento equivocado: que 49 ventanas anuales no alcanzan los 100 escenarios. El mínimo se refiere a escenarios, y un bootstrap por bloques puede generar 500. Además, los cambios mensuales tienen autocorrelación de orden 1 de 0.94 a 0.96 en tasas y 0.91 en equity. La razón de varianzas a 12 meses es 5.1 (PEN ON), 6.9 (USD ON), 3.8 (equity) y 2.1 (FX), así que el i.i.d. subestima mucho la dispersión anual y el peso de la cola. Lo detectó el subagente auditor-financiero y se verificó en `factor_changes`. La skill `modelo-riesgo` ya indicaba bloques de 12 meses.

## E02 · 2026-09-27 · Doble cobro de costos al reducir pasivos (D-08)
**Prompt:** Formulación base del Caso C.
**Resultado:** Corregido
**Detalle:** La IA sumó `restructuring_cost` sobre |Δ| y `reduction_prepayment_cost` sobre las reducciones de pasivos, con lo que cada reducción pagaba ambos costos. La hoja Transaction_Costs indica usar el costo de prepago en los Casos A/E y el restructuring como penalización simétrica en los Casos B/C. Con el doble cobro, los pasivos quedaban inmóviles en la solución aproximada. Lo detectó el auditor-financiero.

## E03 · 2026-09-27 · Justificación inexacta del centrado (S1) y tratamiento asimétrico de la tasa corta
**Prompt:** Formulación base del Caso C.
**Resultado:** Corregido
**Detalle:** La IA afirmó que, con cambios centrados, E[ΔPN] "sale del carry y de las forwards". En realidad, la curva esperada al horizonte es la de t0 (roll-down) y el centrado elimina toda prima de equity y FX. Además propuso que la caja devengue la ON de t0 mientras los cupones flotantes del año se reproyectan con el escenario, incluido el cupón ya fijado antes de t0. Esa asimetría sesga la solución contra la deuda flotante. Lo detectó el auditor-financiero.
