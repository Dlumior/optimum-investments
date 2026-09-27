---
name: valorizacion-flujos
description: Convenciones para valorizar bonos fijos, flotantes, caja y renta variable desde flujos y curvas spot (Caso Optimum). Úsalo al trabajar en src/optimum/curves.py o valuation.py, al calibrar spreads o al revalorizar bajo escenarios.
---

# Valorización por flujos

## Convenciones del caso (no negociables)
- Tasas spot = **efectivas anuales** en decimales (0.0412 = 4.12 %). Tiempo = años **ACT/365** desde la fecha de valorización.
- Nodos: ON(0), 1Y, 3Y, 5Y, 10Y, 20Y. Interpolación **lineal de la tasa cero**; fuera de rango, plana.
- Segmentos forward: S1 ON–1Y, S2 1Y–3Y, S3 3Y–5Y, S4 5Y–10Y, S5 10Y–20Y. Verificado: las FWD del Excel
  coinciden (0.0 pb) con las forwards implícitas de la curva spot con esta convención (notebook 02).
- DF(t) = (1 + z(t) + s_calib)^(−t). `ZeroCurve.discount(t, spread)` ya lo implementa.
- **Fijo**: flujos contractuales de `cashFlows`, descontados con spot de su moneda + spread de calibración.
- **Flotante**: cupón futuro = forward del segmento de referencia (`reference_factor`, p. ej. PEN_FWD_S2) + spread
  contractual; se **reproyecta en cada escenario** (la columna `projected_coupon_rate` es solo la proyección base).
  Respeta la frecuencia/reset (`reset_months`) y la fracción de periodo al calcular el cupón.
- **USD → PEN** con el FX del escenario (`FX_PENUSD`, soles por dólar). `market_value_pen` ≠ `notional_native`.
- **Caja A01**: remunera PEN_SPOT_ON; valor ≈ nominal. **Renta variable A06**: valor ∝ EQUITY_USD × FX.
- Spread de calibración: constante; la hoja es referencia — recalibrar para que V0 = monto de mercado al
  31-12-2025 (test obligatorio, tolerancia 1e-6). No es un factor de riesgo.

## Prohibido
- Usar duración, DV01 o convexidad como input. Las sensibilidades se obtienen revalorizando.
- Mezclar tasas en % y en decimales; mezclar años 30/360 con ACT/365.

## Orden de desarrollo (Anexo 2, regla 4)
1. Bono cupón cero de 1 flujo → comparar con cálculo a mano en un test.
2. A02 (fijo PEN) → calibrar → V0 = 180.
3. Flotante con una sola forward constante → luego A03 con curva completa.
4. Portafolio completo en PEN; test: activos = 1,000, pasivos = 800.
5. Revalorización bajo un shock paralelo +100 pb: signo esperado (bonos de activo bajan).
