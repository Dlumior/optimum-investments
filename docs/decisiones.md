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

## D-11 v2 · 2026-09-28 · Transición del estrés por interpolación de t·s(t)
La auditoría (I-1) mostró que la justificación de D-11 v1 era falsa. El promedio en 3Y/5Y no evitaba las forwards
absurdas, solo las movía: en C_STRESS_3 la forward PEN S3 caía −210 pb con todas las spot al alza, y en C_STRESS_4
la S4 subía +428 pb. Además, interpolar s(t) linealmente es idéntico al promedio en el tramo corto, porque la curva ya
interpola linealmente la tasa cero.
El cambio medio de la forward entre dos nodos fijos, (t_b·s_b − t_a·s_a)/(t_b − t_a), lo fijan los datos del estrés.
En C_STRESS_3 es −37.5 pb entre 1Y y 5Y. Ninguna transición lo evita; solo se puede elegir cómo se reparte.
**v2 (elegida por el alumno):** en los nodos de transición se interpola linealmente t·s(t) entre los nodos fijos
vecinos, de modo que la forward cambia lo mismo en todos los segmentos de la transición. Resultados:
- C_STRESS_3: S2/S3 PEN = −35/−38 pb (antes +138/−210).
- C_STRESS_4: S3/S4 = +413/+409 pb (antes +367/+428).
Consecuencia: en C_STRESS_3, los flotantes indexados a PEN S2 (A03, L04) reducen levemente sus flujos del año.
Se valida que los tramos sean disjuntos, que no haya overrides sin tramo y que exista `*_parallel` (auditoría M-2).
Error E05.

## D-17 · 2026-09-28 · Robustez de la capa de riesgo (auditoría I-3, M-1, M-3, M-4, M-5)
- `market_value_pen` sigue siendo a la vez precio de calibración y posición inicial, pero se exige > 0 con un error
  que nombra el instrumento. Separar precio y posición queda para cuando lo requiera el optimizador.
- La historia se corta en `valuationDate` para no usar información futura.
- La deriva IRP usa z(τ) al plazo del horizonte.
- `var_cvar` exige α, sin valor por defecto.
- La calibración informa el instrumento si el spread cae fuera del intervalo de búsqueda.

## D-18 · 2026-09-28 · Caja al horizonte = instrumentos CASH + flujos netos del año − TC
Para reportar incumplimientos al horizonte (caja$_T$ ≥ `minCash`, P/A$_T$ ≤ `maxLiabilitiesToAssets`):
caja$_{T,s} = \sum_{i \in CASH} x_i V^H_{i,s}/V^0_i + \sum_{i \in \mathcal{A}} x_i F_{i,s}/V^0_i - \sum_{j \in \mathcal{L}} y_j F_{j,s}/V^0_j - TC$,
donde $F$ son los flujos cobrados/pagados en el año, que no se reinvierten (S8) y quedan en caja, y
$TC$ es el costo de reestructuración, pagado con caja en $t_0$.
Así $A_T - L_T = PN_T = PN_0 - TC + \Delta PN$: el balance al horizonte cuadra.
**Incumplimiento LE_12M al horizonte:** se reporta si $\sum y_j$ de los pasivos con vencimiento ≤ 12 meses desde $t_H$
supera `max_weight`·$B_L$ (o queda bajo `min_weight`·$B_L$). No depende del escenario: probabilidad 0 o 1.
Alternativa descartada: solo los instrumentos CASH, porque los cupones quedarían fuera de todo rubro del balance.
Consecuencia: el optimizador necesita separar $r_{k,s}$ en revalorización ($V^H/V^0 - 1$) y flujos ($F/V^0$).
Decidido por el alumno.

## D-19 · 2026-09-28 · Los análisis del Caso C van en `output.json` (bloque `analysis`)
`solve()` calcula además la posición inicial, el barrido de `lambdaGrid` y el benchmark media-varianza, y los guarda
en `analysis`, para que todo número del informe salga de `output.json`. La evaluación fuera de muestra (otra semilla,
unos 50 s más) es una función de `optimizer.py` que se llama desde el notebook 05. La matriz $r_{k,s}$ se calcula una sola vez y se reutiliza (unos 50 s por conjunto de escenarios).
Decidido por el alumno.

## D-20 · 2026-09-28 · Límites al horizonte: base con reporte + variante de vencimientos (auditoría del optimizador)
**Contexto.** El enunciado exige los límites "sobre la estructura post-decisión" y pide reportar los incumplimientos
en las simulaciones del Caso C. El óptimo lleva L01 (vence 2027-12-31) al tope de 35 %; en $t_H$ le quedan 12 meses
y el grupo LE_12M de pasivos (máx. 25 %) queda incumplido con probabilidad 1: lo provoca la decisión, no el mercado.
**Decisión (alumno, opción c recomendada por el auditor):**
- **Base (`caseParameters.horizonMaturityLimits: REPORT`)**: los límites del Cuadro 4 se imponen en $t_0$.
- **Reporte al horizonte de todos los grupos del Cuadro 4** (auditoría I-2), con la pertenencia medida desde $t_H$
  y las tenencias en $t_H$ (V^H; flujos netos del año − TC en la caja en moneda base). Cada incumplimiento se
  clasifica como **estructural** (se incumple aun con los montos de $t_0$: lo provoca el paso del tiempo) o de
  **mercado** (solo por la deriva de valores).
- **Variante** (`analysis.horizonMaturityVariant`): la misma λ con el modo opuesto. Con base REPORT, la variante
  ENFORCE impone los grupos MATURITY medidos desde $t_H$ con los montos de $t_0$ (lineal y determinista, sin
  parámetros nuevos) y reporta `objectiveCost` = objetivo base − objetivo variante.
- Resultado con λ = 0.25: costo 0.287 S/ mm (objetivo 1.155 → 0.868), L01 280 → 200, CVaR 7.82 → 7.33.
**Alternativas descartadas.** (a) Solo reportar: no cuantifica el costo de cumplir. (b) Imponerlo en la base: se
aparta del texto del enunciado y, por simetría, obligaría a imponer también la deriva de mercado de los demás límites.

**Ajustes menores de la misma auditoría:**
- Plazos por **meses calendario** (`pd.DateOffset`), no días/365·12: con la regla anterior L02 (36 meses desde
  $t_H$ por calendario, 36.03 por días) entraba en GT_36M al horizonte.
- `prepare` valida: costo ≥ 0, λ ≥ 0, 0 < α < 1, modo de vencimientos conocido y que cada instrumento pertenezca a
  exactamente una categoría TYPE cuando hay límites TYPE.
- `python -m optimum run` sale con código ≠ 0 si el status no es óptimo y advierte si es OPTIMAL_INACCURATE.
- El TC se paga con caja **después** de fijar los presupuestos: Σx = $B_A$ y caja ≥ `minCash` se verifican antes del
  pago (la caja efectiva es 200 − 2.7 = 197.3). No cambia ningún límite activo.
- Para el informe: E[ΔPN] = 5.83 oculta el TC. E − TC = 3.11 < 3.96 de la posición inicial: el óptimo cede 0.85 de
  valor esperado para bajar el CVaR de 50.1 a 7.8. Con λ ≥ 2, E − TC ≤ 0.
- Pendiente (etapa de sensibilidades, notebook 05): la mitad pasivos (L01/L06) y las ganancias en C_STRESS_3/4
  dependen de la regla de cupones flotantes D-13 (auditoría I-1); la mitad activos es robusta. Sensibilidad §9.7.
