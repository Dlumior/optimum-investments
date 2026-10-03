# Optimum Investments — Caso OP01: optimización de riesgo patrimonial

Prototipo en Python que lee el contrato `input.json` (Anexo 1), valoriza activos y pasivos desde flujos y curvas,
estima el riesgo con factores históricos 2021-2025 y resuelve el problema de optimización del caso asignado
(Caso C: minimización de CVaR sobre escenarios bootstrap por bloques; ver `config/caso.yaml`).

**Estado:** pipeline completo (datos → `input.json` → `output.json`), sensibilidades S1-S9, informe LaTeX y notebook de entrega listos.

## Inicio rápido
```bash
make setup        # .venv + paquete editable + kernel Jupyter "Python (optimum)" + nbstripout
make data         # Excel → data/interim → data/processed (con validaciones)
make json         # → data/json/input.json (caso definido en config/caso.yaml)
make test         # pruebas
make run          # → data/json/output.json
make all          # data + json + run
make sensitivity  # → data/json/sensitivity.json (sensibilidades S1-S9, 5-8 min)
make notebooks    # ejecuta los notebooks 00-05 en orden (verifica reproducibilidad)
make report       # informe_latex/out/main.pdf (LuaLaTeX local, latexmk)
make notebook-entrega   # regenera y ejecuta el notebook autocontenido; verifica que su output.json coincida
make entrega            # ZIP en entrega/: informe PDF, input.json, output.json y notebook ejecutado
make entrega-completa   # ZIP con todo el proyecto (código, pruebas, datos, docs e informe)
```
`make help` lista todos los objetivos; `make lint` y `make fmt` corren ruff.
Sin `make`: `python -m venv .venv && .venv/bin/pip install -e ".[dev]"` y `.venv/bin/python -m optimum {data,json,run}`.

## Estructura
```
├── config/caso.yaml              Caso asignado y parámetros (fuente del input.json)
├── data/
│   ├── raw/                      Excel original — solo lectura
│   ├── interim/                  Hojas del Excel en parquet, sin transformar      (generado)
│   ├── processed/                Tablas limpias, tipadas y validadas              (generado)
│   └── json/                     input.json / output.json (entregables)          (generado)
├── notebooks/                    00 exploración · 01 limpieza · 02 valorización · 03 riesgo · 04 optimización · 05 resultados y sensibilidad
│   └── entrega/                  OP01_optimum_investments.ipynb: notebook autocontenido (generado por scripts/build_notebook_entrega.py)
├── src/optimum/                  Paquete: io/, cleaning, curves, valuation, risk, optimizer, sensitivity, reporting/, cli
├── entrega/                      ZIPs de entrega y build del notebook                (generado)
├── tests/                        pytest
├── informe_latex/                main.tex, preamble.tex, sections/, appendices/, figures/, tables/, out/
├── docs/                         Enunciado, formulacion.md, decisiones.md, ia/ (registro de uso de IA)
├── scripts/                      Utilidades (anexo IA → LaTeX, generación de notebooks, notebook de entrega)
├── .claude/                      Configuración de Claude Code: settings, hooks, skills, agentes
├── CLAUDE.md                     Memoria/instrucciones del proyecto para Claude Code
└── Makefile · pyproject.toml
```

## Flujo de datos
`raw (xlsx)` → **io/excel.py** → `interim` → **cleaning.py** (valida) → `processed` → **json_contract.py** + `caso.yaml`
→ `input.json` → **valuation / risk / optimizer** → `output.json` → **sensitivity** → `sensitivity.json`
→ **reporting** → `informe_latex/{figures,tables}`

El optimizador lee solo `input.json`: límites, λ, α, costos y posiciones no están codificados en `src/`.
Decisiones y supuestos: `docs/decisiones.md`; formulación matemática: `docs/formulacion.md`.

## Trabajo con Claude Code
- `CLAUDE.md` fija las reglas del proyecto; las **skills** de `.claude/skills/` aportan el conocimiento del caso
  (contrato JSON, convenciones de valorización, modelo de riesgo, formulación, figuras, informe, registro de IA).
- Comandos: `/verificar`, `/auditar <tema>`, `/checklist-entrega`.
- Subagentes: `auditor-financiero`, `revisor-informe`, `generador-pruebas`.
- **Hooks** (`.claude/settings.json`):

| Evento | Script | Qué hace |
|---|---|---|
| SessionStart | `session_context.py` | Inyecta caso, estado del pipeline, stubs y TODOs pendientes |
| UserPromptSubmit | `log_prompt.py` | Guarda cada prompt en `docs/ia/prompts.jsonl` (anexo de IA) |
| PreToolUse | `protect_paths.py` | Bloquea editar `data/raw`, datos generados, JSON y figuras a mano |
| PostToolUse | `lint_python.py` | `ruff format` + `ruff check --fix`; devuelve errores a Claude |
| Stop | `stop_tests.py` | Si cambió código, corre pytest; si falla, Claude debe corregir antes de terminar |

Para desactivar temporalmente el hook de pruebas (TDD con tests en rojo): `touch .claude/.skip-stop-tests`.

## Anexo de uso de IA
`docs/ia/registro_ia.md` (entradas curadas) → `python scripts/ia_log_to_tex.py` → `informe_latex/appendices/B_prompts_generado.tex`.
