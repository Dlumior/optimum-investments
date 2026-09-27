---
name: modelo-riesgo
description: Factores de riesgo, covarianzas, sensibilidades, PCA, bootstrap, VaR/CVaR y escenarios de estrés del caso Optimum. Úsalo al trabajar en src/optimum/risk.py, en el notebook 03, o al construir escenarios para los casos B, C o D.
---

# Modelo de riesgo

## Factores (24, orden fijo = `optimum.cleaning.FACTORS`)
PEN_SPOT_{ON,1Y,3Y,5Y,10Y,20Y}, USD_SPOT_{…}, PEN_FWD_S1..S5, USD_FWD_S1..S5, FX_PENUSD, EQUITY_USD.

## Hechos verificados en los datos
- Cambios mensuales: **Δ absoluta** en tasas; **log-retorno** en FX y equity (el Excel coincide con error < 1e-10).
- 59 cambios (60 niveles). SigmaF del Excel es **mensual y singular** (autovalores ~1e-20): las forwards son
  combinación de spots. No invertirla; usar PCA/recorte de autovalores (`nearest_psd`) o reducir factores.
- `Factor_Mapping` es **incidencia 0/1**, no sensibilidades. Explicar cómo se convierte en M.

## Métodos aceptados por el caso
1. Local: M (instrumentos × factores) por **diferencias finitas centrales** sobre el valorizador (bump 1 pb en tasas,
   1 % relativo en FX/equity); ΔV ≈ M ΔF; SigmaV = M SigmaF Mᵀ.
2. Full revaluation: aplicar cada cambio histórico a la curva del 31-12-2025 y revalorizar flujos actuales.
3. Simulación: bootstrap histórico (bloques de 12 meses para horizonte 1 año), PCA o descomposición espectral.
   Semilla desde `caseParameters.seed`. **≥100 escenarios** en C (recomendado 500 + 4 de estrés con prob. total 5 %).

## Chequeos obligatorios (tests)
- Dimensiones, simetría, PSD (autovalor mínimo ≥ −1e-12 tras regularizar).
- Escalamiento temporal explícito (mensual ×12 para anual) y documentado.
- Coherencia: la volatilidad de PN por método local vs. full revaluation debe ser del mismo orden.
- Sin información futura: en D, los escenarios de un nodo solo usan su historia.

## VaR / CVaR (Caso C)
Pérdida = −(PN_T − PN_0). CVaR_α con formulación de Rockafellar–Uryasev (lineal, apta para cvxpy):
min ζ + 1/((1−α)) Σ p_s u_s,  u_s ≥ L_s − ζ, u_s ≥ 0. Con probabilidades no uniformes (estrés) usar p_s.
