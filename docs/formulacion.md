# Formulación del Caso C — Optimización del patrimonio con CVaR (fuente de verdad antes del código)

> **v2 · 2026-09-27.** Versión base acordada, corregida tras la primera revisión del subagente `auditor-financiero`
> (hallazgos C1–C2, I1–I6, M1–M10). Cada parámetro indica su clave en `input.json`.
> Decisiones: `docs/decisiones.md` D-06 a D-12. Errores de la IA corregidos: `docs/ia/registro_ia.md` E01–E03.

## 1. Alcance
- **Lados del balance que se optimizan:** ambos (activos A01–A06 y pasivos L01–L06), como estructura conjunta.
  Los instrumentos se leen de `instruments[]`; nada se codifica por id.
- **Deuda nueva (`fundingAlternatives`, N01–N06): no se incluye** en el Caso C (D-07).
- **Horizonte:** de `valuationDate` (2025-12-31) a `caseParameters.horizonDate` (2026-12-31), un año, ACT/365.
- **Exógeno:** el mercado, los flujos contractuales, los spreads de calibración y los totales
  (`constraints.common.assetBudget`, `liabilityBudget`).
- **Decisión estática:** se decide una sola vez en $t_0$ y no hay rebalanceo dentro del año.
- **Supuesto de escala:** cambiar $y_j$ equivale a emitir o recomprar más del mismo contrato, con el mismo spread
  calibrado, sin importar el monto.

## 2. Conjuntos e índices
| Símbolo | Descripción | Origen |
|---|---|---|
| $i \in \mathcal{A}$ | activos | `instruments[side == ASSET]` |
| $j \in \mathcal{L}$ | pasivos | `instruments[side == LIABILITY]` |
| $k \in \mathcal{K} = \mathcal{A} \cup \mathcal{L}$ | todos los instrumentos | `instruments[]` |
| $s \in \mathcal{S} = \mathcal{S}^{B} \cup \mathcal{S}^{E}$ | escenarios: bootstrap y estrés | `bootstrapCount`, `stressScenarios[]` |
| $g \in \mathcal{G}$ | restricciones de pesos (lado, dimensión y categoría) | `constraints.weights[]` |
| $f = 1..24$ | factores, en el orden de `optimum.cleaning.FACTORS` | `factorMapping.factorIds` |

## 3. Parámetros
| Símbolo | Descripción | Unidad | Clave input.json |
|---|---|---|---|
| $x_k^0$ | posición inicial (valor de mercado) | S/ mm | `instruments[].market_value_pen` |
| $B_A,\ B_L$ | presupuestos de activos y pasivos | S/ mm | `constraints.common.assetBudget`, `liabilityBudget` |
| $\underline{PN}$ | patrimonio mínimo | S/ mm | `constraints.common.minNetWorth` |
| $\overline{\rho}$ | máximo pasivos/activos | – | `constraints.common.maxLiabilitiesToAssets` |
| $\underline{C}$ | caja mínima | S/ mm | `constraints.common.minCash` |
| $\underline{w}_g,\ \overline{w}_g$ | pesos del grupo $g$ | – | `constraints.weights[].min_weight`, `max_weight` |
| $c_k$ | costo de reestructuración por S/ movido (simétrico) | – | `transactionCosts[k].restructuring_cost` |
| $\alpha$ | confianza del CVaR | – | `caseParameters.cvarAlpha` (0.95) |
| $\lambda$ | aversión al riesgo (valor de referencia) | – | `caseParameters.riskAversionLambda` (0.25) |
| $\Lambda$ | grilla del barrido de λ | – | `caseParameters.lambdaGrid` |
| $N_B$ | escenarios bootstrap | – | `caseParameters.bootstrapCount` (500) |
| $b,\ m$ | largo del bloque (meses) y bloques por escenario | – | `bootstrapBlockLength` (6), `bootstrapBlocksPerScenario` (2) |
| deriva | tipo de deriva por clase de factor | – | `caseParameters.drift.{rates,fx,equity}` |
| tramos | nodos de los tramos corto y largo del estrés, más transición | – | `caseParameters.stressTenors` |
| $p_s$ | probabilidad del escenario | – | `bootstrapProbability`, `stressScenarios[].probability` |
| semilla | reproducibilidad | – | `caseParameters.seed` |
| $r_{k,s}$ | resultado por S/ invertido | – | **derivado** por revalorización (§7) |
| $\sigma_k$ | spread de calibración, recalibrado para $V_0$ = valor de mercado | decimal | `calibrationSpreads` (solo referencia) |

`transactionCosts[].reduction_prepayment_cost` **no se usa** en el Caso C (D-08).

## 4. Variables de decisión
| Variable | Descripción | Dominio | Unidad |
|---|---|---|---|
| $x_i$ | monto en el activo $i$ | $\ge 0$ | S/ mm |
| $y_j$ | monto en el pasivo $j$ | $\ge 0$ | S/ mm |
| $\Delta_k^+,\ \Delta_k^-$ | aumento y reducción respecto de la posición inicial | $\ge 0$ | S/ mm |
| $\zeta$ | variable auxiliar de Rockafellar–Uryasev | libre | S/ mm |
| $u_s$ | exceso de pérdida sobre $\zeta$ | $\ge 0$ | S/ mm |

## 5. Función objetivo
$$\Delta PN_s = \sum_{i\in\mathcal{A}} x_i\, r_{i,s} - \sum_{j\in\mathcal{L}} y_j\, r_{j,s}, \qquad L_s = -\Delta PN_s,
\qquad TC = \sum_{k} c_k\,(\Delta_k^+ + \Delta_k^-)$$

$$\max_{x,y,\Delta,\zeta,u}\quad \sum_{s} p_s\,\Delta PN_s \;-\; \lambda\Big(\zeta + \frac{1}{1-\alpha}\sum_s p_s\, u_s\Big) \;-\; TC
\qquad \text{s.a. } u_s \ge L_s - \zeta,\; u_s \ge 0$$

- **Costos de transacción.** $TC$ se paga en $t_0$ y es determinista. Entra una sola vez en el objetivo y **no**
  en $L_s$: el CVaR mide la pérdida de mercado. Se reporta $PN_0' = PN_0 - TC$ y $E[PN_T] = PN_0 - TC + E[\Delta PN]$.
- **VaR y CVaR.** $\zeta$ es el VaR solo si $\lambda > 0$ y el cuantil es único. Hay átomos de 0.0019 y 0.0125, y la
  masa de estrés es exactamente $1-\alpha$. Por eso VaR y CVaR **se recalculan ex post** con la definición de átomo
  fraccional: $\text{CVaR}_\alpha = \frac{1}{1-\alpha}\big[\sum_{L_s > \text{VaR}} p_s L_s + \text{VaR}\,(1-\alpha-\sum_{L_s>\text{VaR}} p_s)\big]$.
- **Unidades.** $\lambda$ es adimensional; el objetivo queda en S/ mm.

## 6. Restricciones
**Presupuestos:** $\sum_i x_i = B_A$ y $\sum_j y_j = B_L$. El denominador de cada peso después de la decisión es fijo,
así que los pesos son lineales.

**Pesos (`constraints.weights`):** $\underline{w}_g B_l \le \sum_{k\in\mathcal{K}_g} z_k \le \overline{w}_g B_l$, con $z = x$ o $y$.

| Dimensión | Categoría | Regla de pertenencia |
|---|---|---|
| CURRENCY | PEN, USD | `currency` |
| TYPE | CASH / EQUITY | `instrument_type` = CASH / EQUITY |
| TYPE | FIXED_INCOME | `instrument_type` ∈ {BOND_FIXED, BOND_FLOAT} |
| RATE_TYPE | FIXED / FLOAT | `reference_factor` nulo / no nulo |
| MATURITY | LE_12M / GT_36M | plazo remanente a $t_0$: ≤ 12 meses / > 36 meses |
| CONCENTRATION | SINGLE_POSITION | una restricción por instrumento: $z_k \le \overline{w}_g B_l$ |

**Validación:** si un grupo queda vacío y tiene `min_weight` > 0, el código debe fallar con un error claro.

**Comunes:**
- PN ≥ 120 y $P/A \le 0.85$ en $t_0$: redundantes con presupuestos fijos ($PN_0 = 200$, $P/A = 0.80$). Se mantienen en
  el modelo y se reportan.
- Caja $\ge \underline{C}$ (80), más exigente que el 5 %.

**Reestructuración:** $x_k - x_k^0 = \Delta_k^+ - \Delta_k^-$ (análogo para $y$).

**Cotas efectivas con los datos actuales** (verificadas por el auditor con LP; se recalculan y reportan, no se
codifican):

| Grupo | Efecto |
|---|---|
| LE_12M | vacío: ningún pasivo vence ≤ 12 m desde $t_0$. No vinculante |
| GT_36M | redundante: solo excluye a L01 (≤ 280), así que el mínimo implícito es 520 > 320 |
| Equity | caja ≤ 20 % y renta fija ≤ 75 % implican **equity ≥ 5 %** (A06 ≥ 50) |
| Renta fija | rango efectivo [60 %, 75 %] |
| Pasivos USD | rango [160, 400] |
| Posición inicial | factible salvo equity (22 % > 20 %) |

En `constraintChecks`, los grupos vacíos y los redundantes se marcan como no vinculantes.

## 7. Modelo de riesgo y escenarios
### 7.1 Bootstrap por bloques móviles (D-09)
1. **Cambios mensuales** de los 24 factores: Δ absoluta en tasas, log-retorno en FX y equity (D-02).
2. **Ventanas:** suma de los cambios de cada una de las $T-b+1$ ventanas de $b$ = 6 meses consecutivos.
   **Se centran las ventanas** (se resta la media de las sumas), no los meses: sin vuelta circular, los meses de
   los extremos entran en menos ventanas y centrar los meses dejaba un sesgo de media (+1.2 % en equity, −30 pb
   en PEN ON; D-09 v3, E04).
3. **Escenario:** se suman $m$ = 2 ventanas centradas, con inicio sorteado uniforme y la semilla `seed`, para
   obtener el shock a 12 meses. Esto conserva la
   persistencia: la razón de varianzas a 12 m es 5.1 en PEN ON, 6.9 en USD ON, 3.8 en equity y 2.1 en FX.
4. **Deriva anual** $\mu$ (D-06), sumada al shock centrado:
   - tasas: `ZERO` → 0, sin proyectar el ciclo alcista 2021-25;
   - FX: `IRP` → $\ln\frac{1+z_{PEN}(1Y)}{1+z_{USD}(1Y)}$ con curvas de $t_0$ (FX = PEN por USD);
   - equity: `HISTORICAL` → 12 × media del log-retorno mensual.
5. **Probabilidad:** $p_s = \text{bootstrapProbability}/N_B$.

### 7.2 Escenarios de estrés (D-11 v2, D-16)
- **Tasas.** Shift paralelo por moneda. El override (un shift, D-16) reemplaza al paralelo en los nodos del tramo
  (`stressTenors.short.nodes` = ON, 1Y; `long.nodes` = 10Y, 20Y). En los nodos de transición (3Y, 5Y) se interpola
  linealmente $t\,s(t)$ entre los nodos fijos vecinos:
  $$t\,s(t) = t_a s_a + (t_b s_b - t_a s_a)\,\frac{t - t_a}{t_b - t_a}.$$
  Así la forward implícita cambia lo mismo en todos los segmentos de la transición. El cambio **medio** de la forward
  entre $t_a$ y $t_b$, $\frac{t_b s_b - t_a s_a}{t_b - t_a}$, lo fijan los datos del estrés y ninguna regla lo evita.
  En C_STRESS_3, con +400 pb en 1Y y +50 pb en 5Y, las forwards 1Y-5Y caen −37.5 pb en promedio. Los flotantes
  indexados a S2 (A03, L04) cobran o pagan menos en ese estrés (D-11 v2, E05).
- **Validación.** Los tramos no comparten nodos, todo `*_override` corresponde a un tramo definido y `*_parallel`
  es obligatorio.
- **FX y equity.** $\Delta\ln FX = \ln(1 + \texttt{fx\_pct})$ y $\Delta\ln E = \ln(1 + \texttt{equity\_pct})$. No se
  les suma deriva.
- **Probabilidad.** $p_s$ = `probability` (0.0125). Se valida con tolerancia que $\sum_{E} p_s$ = `stressProbability`
  y que $\sum_s p_s = 1$.

### 7.3 Coherencia del mercado
- Las forwards se **recalculan** como implícitas de la curva spot shockeada (forward = implícita, 0 pb).
- No se aplica piso a las tasas; se reporta la tasa mínima por escenario como control.

### 7.4 Resultado por instrumento (revalorización completa, sin duración ni DV01)
$$r_{k,s} = \frac{V_k^{PEN}(t_H;\ \text{mercado}_s) + CF_k^{PEN}(t_0, t_H]_s}{V_k^{PEN}(t_0)} - 1$$

**Trayectoria del mercado (D-12):** dentro del año, los factores se mueven linealmente, $F(\tau) = F_0 + \theta(\tau)\,\Delta_s$
con $\theta = (\tau - t_0)/(t_H - t_0)$. Con una regla única para tasa corta, cupones y FX:

| Elemento | Tratamiento |
|---|---|
| Cupón flotante con fijación ≤ $t_0$ | proyección base (ya fijado) |
| Cupón flotante con fijación en $(t_0, t_H]$ | forward de la curva $F(\tau_{fix})$ más spread contractual |
| Flujos posteriores a $t_H$ | se proyectan y descuentan a $t_H$ con el mercado $F(t_H)$ más $\sigma_k$ |
| Caja | devenga la ON de la trayectoria: $ON_0 + \tfrac12 \Delta ON_s$ (tasa simple, ACT/365) |
| Flujos USD del año | se convierten con $FX(\tau_{pago})$ |
| Equity | $V_0\, e^{\Delta\ln E_s}\cdot FX_s/FX_0$ si está en USD, sin dividendos |
| Devengo de cupón | convención de `cashFlows` (tasa × nocional / frecuencia) |
| Flujos cobrados o pagados en el año | no se reinvierten |

$r_{k,s}$ no depende del tamaño de la posición, así que el problema es un LP. Para los pasivos, un $r_j$ mayor
(cupones pagados o alza de valor) reduce el PN.

### 7.5 Salidas de riesgo y reporte
- E[ΔPN] y E[$PN_T$]; VaR y CVaR ex post; volatilidad de ΔPN; pérdida en cada estrés; composición de la cola
  (bootstrap vs estrés).
- Rentabilidad esperada de activos $\sum_i x_i \bar r_i / B_A$ y costo esperado de pasivos $\sum_j y_j \bar r_j / B_L$.
- **Incumplimientos por escenario al horizonte**, exigidos por el enunciado:
  - $PN_{T,s} \ge 120$;
  - $P/A$ a $t_H \le 0.85$;
  - caja a $t_H \ge 80$, con caja$_T$ = instrumentos CASH + flujos netos cobrados en el año − TC pagado en $t_0$ (D-18);
  - LE_12M a $t_H$ (L01 pasa a ≤ 12 m): determinista, se reporta con probabilidad 0 o 1 (D-18).

  - **todos los grupos de pesos del Cuadro 4** a $t_H$, con tenencias en $t_H$ y pertenencia medida desde $t_H$
    (meses calendario), clasificados como *estructurales* o *de mercado* (D-20).

  Se reporta el conteo y la probabilidad de cada incumplimiento. **Se reportan, no se imponen** en el LP base
  (`horizonMaturityLimits: REPORT`). La variante ENFORCE impone los grupos MATURITY medidos desde $t_H$ con los
  montos de $t_0$ y se reporta con su costo en el objetivo (`analysis.horizonMaturityVariant`, D-20).

## 8. Supuestos y simplificaciones (con justificación)
| # | Supuesto | Justificación | Decisión |
|---|---|---|---|
| S1 | Deriva mixta: tasas centradas, FX por paridad de tasas, equity con su media histórica | Con todo centrado, la curva esperada es la de $t_0$ (roll-down) y no hay prima de equity ni FX: equity quedaría fijo en su piso | D-06 |
| S2 | Sin deuda nueva N01–N06 | El Caso C no la menciona | D-07 |
| S3 | Solo `restructuring_cost`, simétrico | La hoja Transaction_Costs lo indica para B/C; evita el doble cobro | D-08 |
| S4 | Bloques móviles 6 × 2 | Conserva la persistencia sin repetir solo 49 ventanas | D-09 |
| S5 | Forwards implícitas de la spot shockeada | Coherencia sin arbitraje | D-10 |
| S6 | Tramos del estrés ON-1Y y 10Y-20Y, con transición por $t\,s(t)$ lineal | El Excel no los define; reparte parejo el cambio de forward que imponen los datos | D-11 v2 |
| S7 | Trayectoria lineal del mercado dentro del año | Trato simétrico de caja y deuda flotante | D-12 |
| S8 | Spread de calibración constante; flujos sin reinvertir | No hay datos de dinámica de spreads; efecto de segundo orden | D-10 |
| S9 | TC fuera de $L_s$ | Es un costo cierto en $t_0$, no un riesgo | D-08 |

**Alternativas descartadas:**
- Riesgo como restricción o cociente E/CVaR: misma frontera, pero el enunciado pide λ.
- Bootstrap i.i.d.: subestima la varianza anual (E01).
- Bloque único de 12 m o bootstrap estacionario.
- PCA paramétrico.
- Estrés como restricción dura.
- MILP con costos fijos.
- CVaR a varios niveles.

## 9. Análisis y benchmarks
1. **Barrido de λ ∈ `lambdaGrid`:** frontera E[ΔPN] vs CVaR, pesos por moneda y tipo, límites activos. Con λ = 0 se
   espera una solución de esquina.
2. **Solo valor esperado:** λ = 0.
3. **Media-varianza con el mismo retorno neto:** $\min \mathrm{Var}(\Delta PN)$ s.a. $E[\Delta PN] - TC \ge E^*_{CVaR}$,
   con las mismas restricciones y escenarios (QP). Se comparan VaR, CVaR, pérdidas en estrés e incumplimientos.
4. **Fuera de muestra:** las soluciones se evalúan con escenarios generados con otra semilla, para medir el
   sobreajuste del CVaR en muestra.
5. **Posición inicial:** métricas sin optimizar.
6. **Sensibilidades:** definición de los tramos de estrés y deriva (todo centrado vs mixto).
7. **Riesgo de modelo de los flotantes (auditoría I-2):** con D-13, L06 y A05 dependen de la tasa corta USD durante
   toda su vida (en C_STRESS_3, L06 explica −21.3 de −22.3 S/ mm). Sensibilidad con cupón = forward implícita por
   período (fijación → pago).
8. **Sesgo del conjunto de estrés (auditoría I-4):** los cuatro estrés deprecian el PEN; ninguno castiga una posición
   larga en USD. Sensibilidad con un estrés de apreciación del PEN, fuera de input.json y sin cambiar el caso base.
9. **Vencimientos al horizonte (D-20):** costo en el objetivo de imponer LE_12M/GT_36M medidos desde $t_H$.

## 10. Pruebas que validan la formulación
- **Curvas y fechas:** `year_fraction` acepta escalares, arrays y `pd.Series` (hallazgo I6, ya corregido).
- **Valorización:**
  - $V_0$ = `market_value_pen` tras la calibración (tolerancia 1e-6).
  - Bono fijo de 2 flujos resuelto a mano; flotante con una sola forward.
  - Un cupón con fijación ≤ $t_0$ no cambia con el escenario.
  - Signo de pasivos: si sube $V$ del pasivo, baja ΔPN.
- **Escenarios:**
  - $\sum p_s = 1$ con tolerancia.
  - Shock nulo da carry puro; las ventanas centradas dan media esperada 0 antes de la deriva (juguete asimétrico).
  - Misma semilla, mismos escenarios.
  - σ de los escenarios de tasas en el orden de σ de los cambios históricos a 12 m (no de σ√12 mensual).
  - En un estrés de subida corta, los flotantes indexados a un segmento dentro del tramo corto (S1) no reducen sus
    flujos; los indexados al segmento de transición (S2) sí (consecuencia documentada de D-11 v2).
  - `fx_pct` = 0.2 da $FX_s/FX_0$ = 1.2.
  - Cobertura USD perfecta: ΔPN insensible a FX.
- **CVaR:**
  - Coincide con un cálculo a mano de átomo fraccional con probabilidades no uniformes.
  - El CVaR del LP (λ > 0) coincide con el CVaR ex post.
- **Optimizador:**
  - Juguete de 2 activos y 1 pasivo.
  - λ = 0 maximiza solo el retorno esperado; con λ grande, CVaR ≈ mínimo alcanzable.
  - Costo de transacción cero si $x = x^0$; con $c = 0$ hay más rotación.
  - Casos INFEASIBLE, reportados como error: equity máx. < 5 % (piso implícito), `minCash` > 200, grupo vacío con
    `min_weight` > 0.
  - Todo `constraintChecks` en `ok`.

## 11. Sensibilidades (etapa v, notebook 05, D-21, D-22)
Todas las grillas salen de `caseParameters.sensitivities` (input.json ← `config/caso.yaml`). Cada variante se arma
sobre una **copia** del documento (`with_overrides`) y se resuelve con el mismo optimizador; los resultados van a
`data/json/sensitivity.json` (`python -m optimum sensitivity`), no a `output.json`. La matriz $r_{k,s}$ se reutiliza
siempre que la variante no cambie los escenarios ni la valorización (S2–S5).

Por variante se reporta: status, $E[\Delta PN]$, TC, $E[PN_T]$, VaR y CVaR$_\alpha$, volatilidad, pérdida en cada estrés,
pesos por moneda y tipo, límites activos, rotación $\sum_k |x_k - x^0_k|$ y distancia $\sum_k |x_k - x^*_k|$ al óptimo base.
Una variante infactible se registra con su status y sin métricas; nunca detiene la corrida.

- **S1 · Tasas ±Δ (evaluación instantánea, sin reoptimizar).** Para las carteras inicial, óptima y media-varianza:
  $\Delta PN = \sum_{k} \pm\,[V_k(t_0; \text{curva} + \delta) - V_k(t_0)]$ con `valuation.value_at_t0` (revalorización
  completa, spreads calibrados fijos, flotantes reproyectados con la curva desplazada). Shocks de
  `rateShocks`: paralelo por moneda y, con `bucket`, solo un tramo de `stressTenors` (transición por t·s(t), D-11 v2).
  Caja y renta variable no cambian (el shock es solo de tasas). Se reporta ΔV de activos, de pasivos y ΔPN, con la
  regla de cupones base y con cada una de `floatingCouponRules`: el tramo corto depende de D-13 (D-23, I-2).
- **S2 · Precios sombra.** Dual $\mu_g \ge 0$ de cada cota de peso activa en el LP base:
  ganancia de objetivo por 1 pp de relajación $= \mu_g \cdot B_{lado} / 100$ (S/ mm por pp). Se contrasta con
  diferencias finitas al relajar `limitRelaxationSmall` (0.5 pp, ≈ pendiente local) y `limitRelaxation` (5 pp,
  ganancia media del tramo). El valor óptimo es cóncavo y lineal por tramos en el límite: el dual es la pendiente local y
  el paso grande da menos si la pendiente cae (D-23, M-1). Las **cotas gemelas** (mismo lado y dimensión, miembros
  complementarios, min + max = 1) son la misma restricción y se relajan juntas en una fila con la suma de duales (I-3).
  El dual mide la relajación de **esa** restricción con las demás fijas; en los presupuestos (igualdades) no
  equivale a subir $B_A$ en el input, porque las cotas de peso son fracciones de $B_A$ y se mueven con él
  (juguete: dual 0.029 vs diferencia finita 0.038). Por eso S2 reporta solo cotas de peso.
- **S3 · Costos.** $c_k \to m \cdot c_k$, $m \in$ `costMultipliers`.
- **S4 · Confianza.** $\alpha \in$ `cvarAlphas` (≥ 0.95 por enunciado); λ fijo.
- **S5 · Peso de la cola.** Para $P \in$ `stressProbabilities`: $p_j^{estrés} \leftarrow P \cdot p_j / \sum_i p_i$
  (se conservan las proporciones entre estrés) y $p_s^{boot} = (1 - P)/N_B$. *Dejar uno fuera*: se elimina el estrés
  $j$ y su probabilidad se reparte proporcionalmente entre los demás, para mantener la probabilidad conjunta (≥ 5 %).
  Eso sube el peso de los demás estrés; por eso cada fila trae `basePortfolio` ($x^*$ con la medida de la variante)
  además de la cartera reoptimizada (D-23, M-2). Con P alto los estrés, que deprecian todos el PEN, pasan a ser
  fuente de ganancia: se lee junto con S8 (M-4).
- **S6 · Muestreo.** Para cada semilla de `seeds`: (a) la cartera óptima base evaluada con los escenarios de esa
  semilla (fuera de muestra, §9.4); (b) reoptimización con esa semilla (estabilidad de las posiciones). Solo se
  remuestrea el bootstrap: no mide sobreajuste respecto de los estrés, que son los mismos (M-3).
- **S7 · Deriva.** Cada variante de `driftVariants` reemplaza `caseParameters.drift` (p. ej. todo ZERO, §9.6).
- **S8 · Estrés extra.** Cada escenario de `extraStress` se agrega a `stressScenarios` con su probabilidad;
  `stressProbability` sube en esa cantidad y `bootstrapProbability` baja lo mismo. Base: espejo de C_STRESS_1 con
  `fx_pct` = −0.20 (apreciación del PEN), p = 0.0125 (D-21, §9.8).
- **S9 · Regla de cupones flotantes** (`floatingCouponRule`, D-22). FLAT (base, D-13): cupón = nivel del factor de
  referencia en la fijación + spread. PERIOD_FORWARD: con fecha de información $d = \min(\tau_{fix}, t_{as\,of})$,
  cupón $= f(d;\, \tau_{fix} - d,\, \tau_{pago} - d)$ + spread, donde $f$ es la forward implícita efectiva anual de la
  curva spot de la moneda del factor en el estado $F(d)$, y $t_{as\,of}$ es la fecha de valorización ($t_0$ al calibrar,
  $t_H$ al horizonte). Los spreads se recalibran para que $V_0$ = `market_value_pen` bajo cada regla.
- **λ** ya está en `analysis.lambdaSweep` (notebook 04); el informe lo cita.
