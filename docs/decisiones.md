# Registro de decisiones de diseño

Formato: `D-NN · fecha · decisión` — contexto, alternativas, elección y por qué.

## D-01 · 2026-09-27 · Estructura del proyecto por capas
Se separan (i) JSON, (ii) valorización, (iii) riesgo, (iv) optimización y (v) resultados en módulos distintos,
como exige el caso. Los notebooks solo orquestan.

## D-02 · 2026-09-27 · Definición de cambios de factores
Δ absoluta para tasas y log-retorno para FX y equity. Verificado contra la hoja `Factor_Changes` (error < 1e-10);
la limpieza falla si el Excel no coincide con la derivación propia.

## D-03 · 2026-09-27 · Formato intermedio parquet
`data/interim` y `data/processed` en parquet (conserva tipos y fechas). Se regeneran con `make data`; no se versionan.

## D-04 · 2026-09-27 · Figuras y tablas dentro de `informe_latex/`
El contenedor de LaTeX solo monta `informe_latex/`, así que `save_fig`/`save_table` escriben ahí directamente.

## D-05 · 2026-09-27 · Caso asignado C y tamaño del bootstrap
`config/caso.yaml` traía "B" como placeholder de la plantilla; el caso asignado al alumno es **C** (CVaR).
Se corrige `caseId` y `riskMeasure: CVAR`; `cvarAlpha` (0.95), `bootstrapProbability` (0.95),
`stressProbability` (0.05) y `riskAversionLambda` (0.25, referencia) ya vienen de `Case_Assumptions` vía
`_case_defaults` y no se sobrescriben. El enunciado exige ≥100 escenarios históricos + 4 de estrés; se fija
`bootstrapCount = 500` en `caseParameters` (no hay valor por defecto en `Case_Assumptions`) para tener una
muestra más estable que el mínimo, con la misma semilla (`seed: 20251231`) para reproducibilidad. A revisar
si el costo computacional del CVaR con 504 escenarios es aceptable al implementar `optimizer.py`.
