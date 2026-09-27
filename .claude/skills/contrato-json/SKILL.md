---
name: contrato-json
description: Contrato JSON v1.0 del caso (Anexo 1) para input.json y output.json. Úsalo al leer, construir, validar o modificar input.json/output.json, src/optimum/io/json_contract.py o cualquier función que reciba el documento de entrada.
---

# Contrato JSON v1.0 (Anexo 1)

## Flujo
`data/processed/*.parquet` + `config/caso.yaml` → `python -m optimum json` → `data/json/input.json`
→ `optimizer.solve(doc)` → `python -m optimum run` → `data/json/output.json`

Implementación: `src/optimum/io/json_contract.py` (`build_input`, `validate_input`, `validate_output`, `load_input`).

## Reglas duras
1. El optimizador recibe **solo** el dict de `load_input()`. Prohibido leer Excel/parquet o tener
   límites, λ, α, costos o presupuestos como constantes dentro de `optimizer.py`/`risk.py`.
   El profesor cambiará datos y posiciones: todo debe salir del JSON (listas de instrumentos de largo variable).
2. Nunca editar `input.json`/`output.json` a mano (un hook lo bloquea). Si falta un campo, se agrega en
   `build_input` + `caso.yaml` y se documenta en `docs/decisiones.md`.
3. El output no puede contener datos no calculados/validados (Anexo 2, prompt 8).

## Claves de input (mínimas)
schemaVersion, caseId, valuationDate, horizonDate, baseCurrency, curveNodes, curveSegments,
marketHistory[60] {date, spot{PEN,USD}{ON..20Y}, forwardSwap{PEN,USD}{S1..S5}, fx{PENUSD}, equityIndex},
instruments, cashFlows, calibrationSpreads, factorMapping{factorIds, rows}, constraints{weights, common},
transactionCosts, fundingAlternatives, stressScenarios, scenarioTree, caseParameters.

## Claves de output (mínimas)
schemaVersion, caseId, status, objectiveValue, valuation{initialAssets, initialLiabilities, initialNetWorth, ...},
metrics{expectedAssetReturn, expectedLiabilityEconomicCost, expectedTerminalNetWorth, netWorthVolatility,
(var95Loss, cvar95Loss en C), transactionCosts}, riskModel{historyStart, historyEnd, observations, covarianceMethod, psdCheck},
positions{assets[], liabilities[]}, weights{byCurrency, byType, ...}, constraintChecks[{name, value, min, max, active, ok}],
solver{name, status, iterations, time}.

## Validaciones obligatorias (Anexo 2, prompt 2)
Rechazar: observaciones duplicadas, segmentos inexistentes, flotantes que referencian factores no definidos,
flujos de instrumentos inexistentes, mapping que no cubre los instrumentos. Añadir un test en
`tests/test_json_contract.py` por cada nueva validación.
