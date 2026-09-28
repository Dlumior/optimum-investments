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

## P07 · 2026-09-28 · Auditoría de la capa (iii) y correcciones
**Prompt:** "lanza la auditoria"; elección de la regla de transición del estrés (dos rondas).
**Resultado:** Aceptado con corrección
**Detalle:** El subagente auditor-financiero no encontró errores críticos. Reprodujo las cifras y verificó var_cvar contra un LP de Rockafellar–Uryasev (diferencia < 1e-13). Hallazgos importantes: I-1 transición del estrés (→ D-11 v2, E05), I-2 riesgo de modelo de D-13 y I-4 sesgo de los estrés hacia USD (ambos pasan a sensibilidades en formulación §9), e I-3 posición 0 (→ validación). También 8 menores. Correcciones con 14 tests nuevos; los que dependían de valores fijos de input.json ahora se derivan del doc. Efecto en los resultados: ΔPN en C_STRESS_3 pasa de −22.3 a −23.3 y en C_STRESS_4 de −7.8 a −8.5; VaR y CVaR sin cambio (42.5 / 50.1). D-17 registra las correcciones de robustez.

## P08 · 2026-09-28 · Lectura del notebook 03
**Prompt:** "agrega la lectura al notebook".
**Resultado:** Aceptado con corrección
**Detalle:** La IA redactó un borrador de lectura (marcado para validación del alumno) con la descomposición de cada estrés por factor. Antes de entregarlo verificó las afirmaciones que no salían de una tabla y corrigió tres. La principal: había descrito la cola del bootstrap como "caída de tasas y equity", pero es el régimen de 2022, con tasas al alza, apreciación del PEN (FX −5 %) y equity −18 %. Esto refuerza el hallazgo I-4 de la auditoría. Las otras dos fueron el rango de subestimación de σ·√12 y el peor escenario, que eran cifras anteriores a D-09 v3.

## P09 · 2026-09-28 · Optimizador (optimizer.py): plan, pruebas primero e implementación
**Prompt:** "vamos con el plan del optimmizer"; "dale, usa el generador-pruebas"; "dale, implementa".
**Resultado:** Aceptado
**Detalle:** La IA presentó el plan (LP de Rockafellar–Uryasev, benchmark media-varianza como QP, `r_{k,s}` calculado una vez) y preguntó al alumno las ambigüedades en vez de asumirlas: caja al horizonte (D-18: CASH + flujos netos − TC), bloque `analysis` en output.json (D-19) e incumplimiento LE_12M al horizonte. El subagente `generador-pruebas` escribió las pruebas (44 casos nuevos con la parametrización) desde la formulación, sin ver la implementación, con soluciones del juguete verificadas por enumeración. Detectó que "E[ΔPN] no creciente en λ" no está garantizado con costos de transacción (lo garantizado es E − TC) y que D-18 no cerraba el balance sin restar TC. La implementación pasó las 123 pruebas sin cambios en los tests.

## P10 · 2026-09-28 · Auditoría del optimizador y límites al horizonte
**Prompt:** "o es mejor primero ejecutar el auditor financiero para saber que hacer?"; decisiones del alumno sobre LE_12M, reporte al horizonte y sensibilidad D-13.
**Resultado:** Aceptado con corrección
**Detalle:** El alumno propuso auditar antes de decidir LE_12M, y fue lo correcto: la auditoría (sin críticos) encontró que el reporte al horizonte estaba incompleto y que la mitad pasivos depende de D-13. El alumno eligió base con reporte + variante ENFORCE (D-20), reportar todos los grupos del Cuadro 4 al horizonte y dejar la sensibilidad D-13 para el notebook 05. La variante reproduce el cálculo independiente del auditor (costo 0.287 S/ mm con λ = 0.25).

## P11 · 2026-09-28 · Notebook 04 (optimización)
**Prompt:** "vamos con el notebook 04".
**Resultado:** Aceptado (lectura pendiente de validación del alumno)
**Detalle:** El notebook lee `output.json` (sin volver a optimizar) y exporta 4 figuras (posiciones, frontera λ–CVaR, composición por λ, distribución de ΔPN) y 5 tablas (posiciones, métricas, restricciones, barrido de λ, incumplimientos al horizonte). Al final regenera los escenarios y verifica que E[ΔPN] y el CVaR de `output.json` se reproducen con tolerancia 1e-6. La IA redactó un borrador de lectura y contrastó con las tablas las cifras que no salían directamente de ellas. Las ganancias en estrés llevan la advertencia de la auditoría I-1 (dependen de D-13).

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

## E05 · 2026-09-28 · Justificación falsa de la transición del estrés (D-11 v2)
**Prompt:** Formulación base (D-11) y respuesta a la auditoría I-1.
**Resultado:** Corregido
**Detalle:** La IA justificó promediar override y paralelo en 3Y/5Y como forma de "evitar forwards implícitas absurdas". El auditor-financiero mostró que solo las movía: S3 PEN caía −210 pb en C_STRESS_3. Al responder, la IA recomendó "interpolar el shift linealmente en el tiempo" sin calcularlo. Antes de implementar lo verificó y vio que en el tramo corto esa opción es idéntica al promedio, porque la curva ya interpola linealmente la tasa cero. Se lo informó al alumno antes de programar. Al derivarlo también encontró que el cambio medio de la forward entre nodos fijos lo imponen los datos (−37.5 pb entre 1Y y 5Y en C_STRESS_3). El alumno eligió interpolar t·s(t). La prueba de §10 "ningún cupón flotante cae en una subida corta" también era una afirmación de la IA que solo se cumplía por el artefacto: se reescribió para los flotantes S1 y se documentó que los S2 bajan. Durante la corrección, un error del script de edición de la IA dejó sin insertar 5 tests; se detectó porque dos tests "pasaban" sin cambios en el código, y se corrigió.

## E06 · 2026-09-28 · Reporte al horizonte incompleto y plazos por días/365 en el optimizador
**Prompt:** "dale, implementa" (optimizer.py).
**Resultado:** Corregido
**Detalle:** La IA solo revisaba al horizonte los grupos MATURITY, con los montos de t0, aunque la solución está pegada a varios límites que el mercado desplaza (renta fija ≤ 75 % se incumple con probabilidad 0.68). Además midió los plazos como días/365·12, y por el año bisiesto L02 entraba en GT_36M al horizonte cuando por calendario le quedan exactamente 36 meses. Lo detectó el subagente `auditor-financiero` (I-2 y menor 1). Se corrigió reportando todos los grupos con tenencias en t_H y causa estructural/mercado, y usando meses calendario. Se agregaron pruebas a mano para ambos casos (D-20).
