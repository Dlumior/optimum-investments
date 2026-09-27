---
name: formulacion-optimizador
description: Formulación matemática y restricciones del optimizador ALM de Optimum Investments (Cuadro 4, restricciones comunes, Casos A-E). Úsalo antes de escribir o modificar src/optimum/optimizer.py, docs/formulacion.md o la sección de formulación del informe.
---

# Formulación del optimizador

## Primero la formulación, después el código
1. Escribir/actualizar `docs/formulacion.md`: variables (unidad S/ mm), objetivo, restricciones, parámetros
   (todos con su clave en input.json), supuestos.
2. Hacerla revisar por el subagente `auditor-financiero`.
3. Escribir tests (caso simple resoluble a mano, infactible, shock extremo).
4. Recién entonces implementar con **cvxpy** (convexo: QP para volatilidad, LP para CVaR).

## Restricciones de pesos (Cuadro 4; en input.json → constraints.weights)
Activos: PEN 40–80 %, USD 20–60 %, Caja 5–20 %, Renta fija 40–75 %, Renta variable 0–20 %, una posición ≤ 35 %.
Pasivos: PEN 50–80 %, USD 20–50 %, Fija 45–80 %, Flotante 20–55 %, ≤12m 0–25 %, >36m 40–100 %, una posición ≤ 35 %.
Los límites aplican solo al lado del balance que optimiza el caso. Denominador = total de ese lado **post-decisión**.

## Restricciones comunes (constraints.common)
Sin posiciones negativas; PN económico ≥ S/ 120 mm; Pasivos/Activos ≤ 85 %; caja ≥ S/ 80 mm si se decide sobre activos;
presupuestos: activos 1,000 y pasivos 800 al inicio (modifica composición, no crea capital ni elimina deuda).
La posición inicial es benchmark y **no** necesita cumplir los límites. Sin derivados.

## Por caso
- **A** pasivos: saldo por instrumento, deuda nueva N01–N06 (máx. emisión), prepago; costo esperado + costos
  prepago/emisión + penalización HHI de vencimientos (Case_Assumptions) + λ·riesgo. Total = 800. Sensibilidad +200 pb corto plazo.
- **B** conjunto: max PN esperado − λ·riesgo − costos de reestructuración (penalización simétrica |Δ|: variables
  auxiliares Δ⁺, Δ⁻). Covarianza activo-pasivo desde factores comunes. Benchmarks: sin cambios y optimización separada.
  Mostrar un caso donde una mejora del activo empeora el riesgo del PN.
- **C** CVaR: ≥100 escenarios + 4 estrés (5 %), α ≥ 95 %, objetivo E[PN] − λ·CVaR; barrer λ; comparar con media-varianza.
- **D** árbol T/E con 3 fechas de decisión + terminal; no anticipatividad (decisiones iguales en nodos con misma historia);
  rebalanceo autofinanciado; límites en cada nodo; comparar vs. estrategia estática.
- **E** sustitución fija→flotante: variable por (deuda fija, alternativa flotante); costo esperado, volatilidad y PN
  para 0 %…máximo; punto de quiebre de tasa.

## Señales de error (revisar siempre)
Solución pegada a todos los límites; costos negativos; arbitraje por moneda; pesos que no suman 1;
signos de pasivos invertidos; status distinto de OPTIMAL tratado como éxito.
Reportar `constraintChecks` con {name, value, min, max, active, ok}.
