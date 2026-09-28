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

## D-06 · 2026-09-27 · Deriva mixta de los factores (revisada tras la auditoría)
**v1:** centrar todos los cambios. El auditor mostró que eso elimina toda prima de equity y FX: equity queda fijo en su
piso y la curva esperada es la de t0 (no "las forwards", como decía la v1).
**v2 (elegida por el alumno):** se centran los cambios y se suma una deriva anual por clase de factor
(`caseParameters.drift`):
- tasas `ZERO`, para no proyectar el ciclo alcista 2021-25 (+62 pb/año en ON);
- FX `IRP` = ln((1+z_PEN(1Y))/(1+z_USD(1Y))), paridad de tasas con las curvas de t0;
- equity `HISTORICAL` = 12 × media mensual del log-retorno (≈ +6 %/año).

Alternativas descartadas: todo centrado, o sin centrar. Se reporta una sensibilidad con todo centrado.

## D-07 · 2026-09-27 · Sin deuda nueva (N01–N06) en el Caso C
El enunciado del Caso C pide optimizar la estructura conjunta de activos y pasivos existentes; `fundingAlternatives`
corresponde a los Casos A y E. **Confirmado por el alumno (2026-09-27): queda fuera del caso.**

## D-08 · 2026-09-27 · Costos de transacción (revisada tras la auditoría)
**v1:** `restructuring_cost` sobre |Δ| más `reduction_prepayment_cost` sobre las reducciones de pasivos. Esto cobraba
dos veces cada reducción de pasivos (error E02).
**v2:** solo `restructuring_cost`, como penalización simétrica sobre Δ⁺ + Δ⁻, según la nota de la hoja
Transaction_Costs para B/C. TC se paga en t0: entra una sola vez en el objetivo y no en la pérdida L_s. Se reporta
PN0' = PN0 − TC.

## D-09 · 2026-09-27 · Bootstrap por bloques móviles 6 × 2 (revisada tras la auditoría)
**v1:** 12 meses i.i.d. Estaba mal (E01): la autocorrelación de orden 1 es 0.94 (PEN ON), 0.96 (USD ON), 0.91
(equity) y 0.56 (FX), y la razón de varianzas a 12 m es 5.1 / 6.9 / 3.8 / 2.1. Por eso el i.i.d. subestima el riesgo
anual.
**v2 (elegida por el alumno):** cada escenario concatena 2 bloques de 6 meses consecutivos (`bootstrapBlockLength`,
`bootstrapBlocksPerScenario`), con inicio sorteado entre las 54 ventanas (59 cambios mensuales): 54² = 2,916 combinaciones posibles.

Alternativas descartadas:
- bloque único de 12 m: solo 49 ventanas distintas;
- bootstrap estacionario: más difícil de explicar y de testear.

## D-10 · 2026-09-27 · Convenciones de revalorización al horizonte
Resultado por instrumento = revalorización a t_H con el mercado del escenario, más los flujos del año.
- Forwards implícitas de la spot shockeada.
- Flujos del año sin reinvertir.
- Spread de calibración constante.
- Equity sin dividendos.
- Devengo de cupón según la convención de `cashFlows`.

## D-11 · 2026-09-27 · Tramos de los escenarios de estrés
Stress_Scenarios_C no define qué nodos forman el tramo "corto" y el "largo". Elegido por el alumno
(`caseParameters.stressTenors`):
- corto = ON y 1Y;
- largo = 10Y y 20Y;
- en los nodos de transición (3Y y 5Y), el promedio entre el override y el shift paralelo.

Sin transición, el escalón de la curva spot generaba forwards implícitas en sentido contrario (S2 de 4.40 % a 3.19 %
en C_STRESS_3). Se reporta una sensibilidad del CVaR a esta definición.

## D-12 · 2026-09-27 · Trayectoria lineal del mercado dentro del año
Hallazgo I3: la v1 trataba de forma asimétrica la caja (ON de t0) y los cupones flotantes (reproyectados con el
escenario, incluso los ya fijados). Regla única: F(τ) = F0 + θ(τ)·Δ.
- Los cupones fijados antes de t0 no cambian.
- Los que se fijan en el año usan la forward de F(τ_fix).
- La caja devenga ON0 + ½ΔON.
- Los flujos USD del año se convierten con FX(τ_pago).

## D-13 · 2026-09-27 · Proyección de cupones flotantes: nivel plano del factor de referencia
Cada cupón futuro = valor del factor que indexa el contrato (`reference_factor`, p. ej. PEN_FWD_S2) en su fecha de
fijación, más el spread contractual. Monto = tasa × nocional / frecuencia. Fijación = fecha de pago − `reset_months`.
Es la convención del Excel: reproduce `projected_coupon_rate` y los spreads de Calibration_Spreads, y es la lectura
literal de "forward del segmento de referencia + spread". Alternativa descartada: forward implícita por período según
la estructura de plazos, que se aparta de la base del Excel e impide validar contra la hoja. Consecuencia
documentada: L06 queda expuesto solo al tramo S1 USD durante 10 años, como indica su contrato. Elegida por el alumno.

## D-14 · 2026-09-27 · Sensibilidades locales solo como chequeo; sin PCA
El Caso C usa revalorización completa (§7.4). `risk.sensitivities` (diferencias finitas centrales sobre
`value_at_t0`, bump de 1 pb en tasas y 1 % en log-FX/equity) solo sirve para el chequeo de coherencia que exige la skill
`modelo-riesgo`: volatilidad del PN local (M Σ Mᵀ) vs. revalorización completa. Se elimina `pca`: la singularidad
de la covarianza ya se muestra con sus autovalores (notebook 00) y el modelo no simula desde Σ. Elegido por el alumno.

## D-15 · 2026-09-27 · Consistencia horizonte–bootstrap
`bootstrapBlockLength × bootstrapBlocksPerScenario` (meses) debe coincidir con los meses entre `valuationDate` y
`horizonDate`. Si no coinciden, `build_scenarios` lanza un error en vez de reescalar en silencio. La deriva anual μ se
escala por (b·m)/12 (hoy = 1). Elegido por el alumno.

## D-16 · 2026-09-27 · Los overrides de estrés son shifts, no niveles
`*_short_override` y `*_long_override` de `stressScenarios` se leen como **cambios** (0.04 = +400 pb) que
reemplazan al shift paralelo en los nodos del tramo (D-11), no como niveles de tasa. Leídos como nivel, 4 % casi no
movería el tramo corto PEN (ON = 4.03 %), lo que contradice la nota "Shock concentrado en tasas cortas".
Confirmado por el alumno.

## D-09 v3 · 2026-09-28 · Centrar las ventanas del bootstrap, no los meses
Al implementar `risk.py` se vio que centrar los cambios mensuales no deja al bootstrap por bloques con media cero:
sin vuelta circular, los meses de los extremos de la muestra entran en menos ventanas. El sesgo exacto (sobre las 54
ventanas, 2 bloques) era +1.2 % en equity, −30 pb en PEN ON, −13 pb en USD ON y −0.19 % en FX. Se centran las
sumas de las ventanas, con lo que E[shock] = 0 exacto y la media del bootstrap = μ. Alternativas descartadas: bootstrap
circular (5 de 59 ventanas unirían dic-2025 con ene-2021) o documentar el sesgo. Elegido por el alumno. Error E04.
