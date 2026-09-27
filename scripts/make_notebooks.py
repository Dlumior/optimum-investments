"""Genera los notebooks base del proyecto (solo se usa una vez para el andamiaje)."""

from pathlib import Path

import nbformat as nbf

NB = Path(__file__).resolve().parents[1] / "notebooks"

SETUP = """%load_ext autoreload
%autoreload 2

import numpy as np
import pandas as pd

from optimum import paths
from optimum.cleaning import load_processed
from optimum.reporting.figures import COLORS, new_figure, save_fig
from optimum.reporting.tables import save_table

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 30)"""


def md(s):
    return nbf.v4.new_markdown_cell(s)


def code(s):
    return nbf.v4.new_code_cell(s)


NOTEBOOKS = {
    "00_exploracion_datos.ipynb": [
        md(
            "# 00 · Exploración del Excel del caso\n\n**Objetivo:** entender el contenido de `data/raw/` antes de limpiar. "
            "Este notebook **no escribe** en `data/`; solo lee y grafica.\n\n"
            "> Regla: los notebooks orquestan y muestran; la lógica reutilizable vive en `src/optimum/`."
        ),
        code(SETUP),
        code(
            "from optimum.io.excel import load_workbook\n\nraw = load_workbook()\n"
            "pd.DataFrame({h: df.shape for h, df in raw.items()}, index=['filas', 'columnas']).T"
        ),
        code('raw["Léeme"]'),
        code('raw["Notes"]'),
        md("## Series históricas"),
        code('hist = raw["Historical_Market"].set_index("Date")\nhist.describe().T.round(4)'),
        code(
            "fig, axes = new_figure(1, 2, aspect=0.4, sharey=True)\n"
            'for ax, ccy in zip(axes, ["PEN", "USD"]):\n'
            '    for n in ["ON", "1Y", "5Y", "20Y"]:\n'
            '        ax.plot(hist.index, 100 * hist[f"{ccy}_SPOT_{n}"], label=n)\n'
            '    ax.set_title(f"Spot {ccy}")\n'
            'axes[0].set_ylabel("%")\naxes[1].legend(title="Nodo")\n'
            'save_fig(fig, "curvas_spot_historicas")'
        ),
        md(
            "## Hallazgos / preguntas\n\n- [ ] ...\n\n*(Anotar aquí y trasladar lo relevante a `docs/decisiones.md`.)*"
        ),
    ],
    "01_limpieza.ipynb": [
        md(
            "# 01 · Limpieza: raw → interim → processed\n\n"
            "Ejecuta el mismo pipeline que `make data` y muestra las validaciones. "
            "Si una validación falla, se corrige en `src/optimum/cleaning.py` (con test), nunca a mano en los datos."
        ),
        code(SETUP),
        code(
            "from optimum.cleaning import build_processed, save_processed\nfrom optimum.io.excel import export_interim\n\n"
            "export_interim()\ntables = build_processed()\nsave_processed(tables)\n"
            "pd.Series({k: v.shape for k, v in tables.items()}, name='shape')"
        ),
        md(
            "## Controles\n\n- Cambios de factores: Δ absoluta en tasas; log-retorno en FX y equity (verificado contra `Factor_Changes`).\n"
            "- Balance inicial: activos 1,000 / pasivos 800 / patrimonio 200."
        ),
        code('inst = tables["instruments"]\ninst.groupby("side")["market_value_pen"].sum()'),
        code(
            'tables["cash_flows"].groupby("instrument_id").agg(n=("period", "size"), ultimo=("payment_date", "max"), '
            'principal=("principal_cash_flow", "sum"))'
        ),
        code(
            "# SigmaF del Excel: el caso advierte que puede ser singular\n"
            'w = np.linalg.eigvalsh(tables["covariance_excel"].values)\n'
            'pd.Series(w[::-1], name="autovalor").head(8)'
        ),
    ],
    "02_valorizacion.ipynb": [
        md(
            "# 02 · Curvas y valorización por flujos\n\n"
            "Orden (Anexo 2, regla 4): bono fijo simple → flotante con una forward → portafolio → "
            "**test de calibración** (valor teórico = monto de mercado al 31-12-2025)."
        ),
        code(SETUP),
        code(
            "from optimum.curves import ZeroCurve, implied_forward\n\n"
            'hist = load_processed("market_history")\nbase = hist.loc["2025-12-31"]\n'
            'curves = {c: ZeroCurve.from_market_row(base, c) for c in ["PEN", "USD"]}\n'
            "t = np.linspace(0, 20, 201)\n"
            "fig, ax = new_figure()\n"
            "for c, cv in curves.items():\n"
            "    ax.plot(t, 100 * cv.zero(t), color=COLORS[c], label=c)\n"
            "    ax.scatter(cv.tenors, 100 * cv.rates, color=COLORS[c], s=12)\n"
            'ax.set(xlabel="Años", ylabel="Tasa cero (%)", title="Curvas spot al 31-12-2025")\nax.legend()\n'
            'save_fig(fig, "curvas_spot_base")'
        ),
        code(
            "# Chequeo: forwards implícitas vs. forwards del Excel\n"
            "from optimum.curves import NODE_YEARS, SEGMENT_BOUNDS\n"
            "rows = []\n"
            "for c, cv in curves.items():\n"
            "    for s, (a, b) in SEGMENT_BOUNDS.items():\n"
            "        t1, t2 = max(NODE_YEARS[a], 1e-9), NODE_YEARS[b]\n"
            '        rows.append({"ccy": c, "seg": s, "implícita": implied_forward(cv, t1, t2), "excel": base[f"{c}_FWD_{s}"]})\n'
            'pd.DataFrame(rows).assign(dif_pb=lambda d: 1e4 * (d["implícita"] - d["excel"])).round(5)'
        ),
        md(
            "## TODO: valorizador (`src/optimum/valuation.py`)\n\n"
            "1. `price_fixed` con A02 → comparar con 180.\n2. `price_floating` con A03.\n"
            "3. Todos los instrumentos → tabla valor teórico vs. mercado.\n4. Mover a tests lo que ya funcione."
        ),
    ],
    "03_riesgo_factores.ipynb": [
        md(
            "# 03 · Factores, covarianzas y escenarios\n\n"
            "24 factores. SigmaF singular → PCA / regularización. Sensibilidades M por diferencias finitas "
            "sobre el valorizador (nunca duración/DV01 como input)."
        ),
        code(SETUP),
        code(
            'from optimum.risk import covariance\n\nchg = load_processed("factor_changes")\n'
            "S = covariance(chg)  # anualizada\nw, v = np.linalg.eigh(S.values)\n"
            'expl = pd.Series(w[::-1] / w.sum(), name="var. explicada").cumsum()\nexpl.head(6).round(4)'
        ),
        code(
            "fig, ax = new_figure(width=0.8, aspect=0.85)\n"
            'corr = chg.corr()\nim = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)\n'
            "ax.set_xticks(range(len(corr)), corr.columns, rotation=90, fontsize=6)\n"
            "ax.set_yticks(range(len(corr)), corr.index, fontsize=6)\nax.grid(False)\n"
            'fig.colorbar(im, ax=ax, shrink=0.8)\nax.set_title("Correlación de cambios de factores")\n'
            'save_fig(fig, "correlacion_factores")'
        ),
        md(
            "## TODO\n- `sensitivities()` → M (12 × 24)\n- SigmaV = M SigmaF Mᵀ y comparación con full revaluation\n"
            "- Escenarios (bootstrap / PCA) según el caso"
        ),
    ],
    "04_optimizacion.ipynb": [
        md(
            "# 04 · Optimización\n\n**Antes de codificar:** completar `docs/formulacion.md` "
            "(variables, objetivo, restricciones, unidades) y revisarlo con el subagente `auditor-financiero`.\n\n"
            "El optimizador solo lee `data/json/input.json`."
        ),
        code(SETUP),
        code(
            "from optimum.io.json_contract import load_input\n\ndoc = load_input()\n"
            'doc["caseId"], doc["caseParameters"], doc["constraints"]["common"]'
        ),
        code('pd.DataFrame(doc["constraints"]["weights"])'),
        code("# from optimum.optimizer import solve\n# out = solve(doc)\n# out['status'], out['metrics']"),
    ],
    "05_resultados_sensibilidad.ipynb": [
        md(
            "# 05 · Resultados y sensibilidad\n\nLee `output.json`, produce tablas/figuras para el informe "
            "(`informe_latex/tables`, `informe_latex/figures`) y corre sensibilidades (λ, +200 pb, límites, costos)."
        ),
        code(SETUP),
        code(
            "import json\n\nif paths.OUTPUT_JSON.exists():\n"
            '    out = json.loads(paths.OUTPUT_JSON.read_text())\n    display(out["status"], out["metrics"])\n'
            'else:\n    print("Aún no hay output.json: ejecuta `make run`")'
        ),
        code(
            "# Ejemplo de tabla para el informe (balance inicial)\n"
            'inst = load_processed("instruments")\n'
            'tab = inst[["side", "name", "currency", "market_value_pen"]].rename(columns={\n'
            '    "side": "Lado", "name": "Posición", "currency": "Moneda", "market_value_pen": "Monto (S/ mm)"})\n'
            'save_table(tab, "balance_inicial", caption="Balance inicial al 31-12-2025", label="tab:balance", fmt="{:,.1f}")'
        ),
    ],
}

for name, cells in NOTEBOOKS.items():
    nb = nbf.v4.new_notebook(cells=cells)
    nb.metadata["kernelspec"] = {"name": "optimum", "display_name": "Python (optimum)", "language": "python"}
    nbf.write(nb, NB / name)
    print("->", name)
