# Optimum Investments — Caso OP01 (optimización de riesgo patrimonial)

Proyecto académico: optimizador ALM en Python para un balance de S/ 1,000 mm de activos y S/ 800 mm de pasivos,
con historia de mercado 2021-2025. Enunciado completo: `docs/Caso_Optimum_Investments.pdf`.
Caso asignado y parámetros: `config/caso.yaml`. El alumno es responsable de la formulación y de validar todo lo que propongas.

## Reglas de oro
1. **Formulación y pruebas antes que código.** Sigue la skill `desarrollo-por-etapas`.
2. **Todo input sale de `data/json/input.json`.** Ningún límite, λ, α, costo o presupuesto codificado en `src/`.
   El profesor cambiará datos/posiciones: nada de listas fijas de instrumentos.
3. **Datos inmutables**: `data/raw/` no se toca. `interim/`, `processed/`, `json/`, `informe_latex/{figures,tables,out}`
   solo los genera el código (hooks lo bloquean).
4. **Lógica en `src/optimum/`, no en notebooks.** Los notebooks importan, ejecutan y muestran.
5. **Prohibido** usar duración/DV01 como dato: las sensibilidades salen de revalorizar flujos.
6. Ante una ambigüedad financiera, **pregunta** en vez de asumir en silencio. Si asumes, documenta en `docs/decisiones.md`.
7. Registra prompts relevantes y errores tuyos en `docs/ia/registro_ia.md` (skill `registro-ia`). Sé honesto.

## Mapa
```
config/caso.yaml            caso asignado + parámetros → input.json
data/raw → interim → processed → json/{input,output}.json
src/optimum/
  paths.py                  rutas (usar siempre)
  io/excel.py               Excel → DataFrames crudos
  cleaning.py               limpieza + validación (FACTORS, DataValidationError, load_processed)
  io/json_contract.py       (i)  contrato Anexo 1: build/validate/load
  curves.py                 ZeroCurve: interpolación lineal, DF, forwards implícitas
  valuation.py              (ii) valorización por flujos          [por implementar]
  risk.py                   (iii) covarianzas, M, escenarios, CVaR [por implementar]
  optimizer.py              (iv) formulación cvxpy + solve(doc)    [por implementar]
  reporting/figures.py      new_figure / save_fig → informe_latex/figures
  reporting/tables.py       save_table → informe_latex/tables
  cli.py                    python -m optimum {data,json,run,all}
notebooks/00..05            exploración → limpieza → valorización → riesgo → optimización → resultados
tests/                      pytest (el hook Stop los corre si cambiaste .py)
informe_latex/              documento (LuaLaTeX local, latexmk), ≤ 12 páginas de cuerpo
docs/                       formulacion.md, decisiones.md, ia/ (registro de uso de IA)
```

## Comandos
`make setup` · `make data` · `make json` · `make run` · `make test` · `make lint` · `make notebooks` · `make report` · `make entrega`
Python del proyecto: `.venv/bin/python`. Paquete instalado en modo editable (`import optimum`).

## Convenciones
- Montos en **S/ millones**; tasas y spreads en **decimales** (0.0125, no 125 ni 1.25); tiempo ACT/365.
- Signos: PN = V(activos) − V(pasivos). Pérdida = −ΔPN.
- Identificadores de código en inglés; docstrings, comentarios, informe y mensajes en español.
- Factores en el orden de `optimum.cleaning.FACTORS` (24).

## Hechos verificados de los datos (no re-descubrir)
- Cambios de factores: Δ absoluta en tasas, log-retorno en FX/equity (= hoja Factor_Changes).
- Covarianza del Excel: mensual y **singular** (forwards derivadas de spots) → PCA / `nearest_psd`.
- Forwards del Excel = forwards implícitas de la curva spot (interp. lineal, efectiva anual): 0.0 pb de diferencia.
- `Scenario_Tree_D` tiene dos tablas apiladas (transiciones y shocks) → dos parquet separados.
- Flujos flotantes de `Cash_Flows` son solo la proyección base: reproyectar por escenario.
- `Calibration_Spreads` es referencia: recalibrar para V0 = monto de mercado.
- `notional_native` (moneda original) ≠ `market_value_pen` (valor de mercado en PEN).

## Skills y agentes del proyecto
Skills (se cargan solas según el tema): contrato-json, valorizacion-flujos, modelo-riesgo, formulacion-optimizador,
figuras-y-tablas, informe-latex, registro-ia, desarrollo-por-etapas.
Comandos: `/verificar`, `/auditar [tema]`, `/checklist-entrega`.
Subagentes: `auditor-financiero` (revisión independiente, solo lectura), `revisor-informe`, `generador-pruebas`.
