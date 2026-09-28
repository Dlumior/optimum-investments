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

## P05 · 2026-09-27 · Cierre de los notebooks 00, 01 y 02
**Prompt:** "y los notebooks en que momento se realiza?"; "cierra primero los notebooks 00, 01 y 02".
**Resultado:** Aceptado
**Detalle:** Los tres notebooks seguían siendo la plantilla y no se habían ejecutado. La IA los completó sin agregar lógica fuera de `src/`. 00: hojas, series de tasas, FX y equity, tabla de persistencia (autocorrelación y razón de varianzas a 12 m, que reproduce las cifras de D-09), autovalores de la covarianza y hallazgos enlazados a D-xx. 01: pipeline, controles (cambios vs. Excel 7.6e-16, balance 1,000/800/200, estrés = 5 %) y construcción y validación de input.json, sin cambios respecto de la versión previa. 02: curvas, forwards (0.0 pb), spreads calibrados vs. Excel, carry sin shock por instrumento y sensibilidad del PN por revalorización (PEN +100 pb: +9.1; USD +100 pb: −1.9; FX +10 %: +27.0; equity −10 %: −22.0 S/ mm). Figuras y tablas nuevas: `fx_equity_historico`, `autovalores_covarianza`, `sensibilidad_pn_shocks`, `persistencia_factores`, `spreads_calibrados` y `carry_base`. La IA corrigió en el notebook una frase propia que atribuía la diferencia de spreads a una convención de conteo de días sin haberlo verificado.

## P06 · 2026-09-28 · Modelo de riesgo (risk.py) y notebook 03
**Prompt:** "vamos con el plan de risk"; "estoy de acuerdo con las recomendaciones"; "continuemos con la implementación".
**Resultado:** Aceptado con corrección
**Detalle:** Plan → decisiones D-14 a D-16 (el alumno aceptó las recomendaciones) → 29 tests escritos antes del código → implementación. Al revisar las salidas, la IA detectó un sesgo de media en su propia formulación del bootstrap (E04); el alumno eligió centrar las ventanas (D-09 v3) y se agregaron 2 tests. Resultados: 504 escenarios, σ del bootstrap a 12 m entre 0.86 y 1.09 veces la histórica, R de 12 × 504 en unos 45 s. Posición inicial: E[ΔPN] = +4.0, σ = 25.4, VaR95 = 42.5 y CVaR95 = 50.1 S/ mm; 25 % de la probabilidad de la cola viene del estrés. Coherencia (D-14): σ local con Σ bootstrap = 24.9 vs. 25.2 por revalorización completa; con Σ i.i.d. × 12 da 12.8, lo que confirma la persistencia. En el notebook 03 queda para el alumno la sección "Lectura".

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

## E04 · 2026-09-28 · Centrado mensual en un bootstrap por bloques (D-09 v3)
**Prompt:** "continuemos con la implementación" (risk.py).
**Resultado:** Corregido
**Detalle:** La formulación que propuso la IA centraba cada cambio mensual y asumía que así el bootstrap quedaba con media cero ("centrado da media 0 antes de la deriva"). Con bloques móviles no circulares eso es falso: los meses de los extremos entran en menos ventanas, y la suma esperada de un bloque pondera más el tramo central de la muestra. Se detectó al revisar los resultados de la implementación: el rendimiento medio del equity (8.3 %) no cuadraba con la deriva (6.0 %). Un cálculo exacto sobre las 54 ventanas mostró que el sesgo no era ruido: +1.2 % en equity y −30 pb en PEN ON. Los tests iniciales no lo detectaron porque el juguete [1, 2, 3, 4] es simétrico. Se corrigió centrando las ventanas, con dos tests nuevos (juguete asimétrico y media del bootstrap = μ dentro de 3 errores estándar) que fallaron antes de corregir el código.
