"""Genera el notebook de entrega autocontenido: input.json -> gráficos -> output.json (D-25).

El zip final solo lleva el informe, input.json, output.json y este notebook, así que el notebook no puede importar
`src/optimum/`. Cada módulo del modelo se copia **verbatim** en una celda `%%writefile` hacia un paquete temporal
`optimum/` que se agrega a `sys.path`; los imports `from optimum.x import ...` funcionan sin reescribirlos.
De `cleaning.py` y `io/json_contract.py` se extraen (por AST) solo las piezas que no dependen del Excel ni de parquet.

Uso:  .venv/bin/python scripts/build_notebook_entrega.py [--out RUTA]
Si cambia `src/optimum/`, regenerar (la prueba tests/test_notebook_entrega.py lo exige).
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "optimum"
OUT = ROOT / "notebooks" / "entrega" / "OP01_optimum_investments.ipynb"

# Módulos copiados completos, en orden de dependencia: (ruta relativa al paquete, título de la celda markdown)
VERBATIM = [
    ("curves.py", "Curvas cero-cupón"),
    ("valuation.py", "(ii) Valorización por flujos"),
    ("risk.py", "(iii) Factores, escenarios y CVaR"),
    ("optimizer.py", "(iv) Optimizador"),
    ("sensitivity.py", "(v) Sensibilidades S1–S9"),
    ("reporting/labels.py", "Etiquetas en español"),
]
# Extractos por AST: (ruta, nombres de nivel superior a conservar, imports a conservar, título)
EXTRACTS = [
    (
        "cleaning.py",
        [
            "RATE_NODES",
            "SEGMENTS",
            "CURRENCIES",
            "SPOT_FACTORS",
            "FWD_FACTORS",
            "FACTORS",
            "RATE_FACTORS",
            "LOG_FACTORS",
            "compute_factor_changes",
        ],
        ["from __future__ import annotations", "import numpy as np", "import pandas as pd"],
        "Factores de riesgo (extracto de `cleaning.py`)",
    ),
    (
        "io/json_contract.py",
        [
            "SCHEMA_VERSION",
            "REQUIRED_INPUT_KEYS",
            "REQUIRED_OUTPUT_KEYS",
            "_clean",
            "validate_input",
            "validate_output",
        ],
        [
            "from __future__ import annotations",
            "import math",
            "from typing import Any",
            "import numpy as np",
            "import pandas as pd",
            "from optimum.cleaning import FACTORS",
        ],
        "(i) Contrato JSON (extracto de `io/json_contract.py`)",
    ),
]
EMPTY = ["__init__.py", "io/__init__.py", "reporting/__init__.py"]


def md(s: str):
    return nbf.v4.new_markdown_cell(s.strip("\n"))


def code(s: str):
    return nbf.v4.new_code_cell(s.strip("\n"))


def _top_name(node: ast.stmt) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def extract(rel: str, names: list[str], imports: list[str]) -> str:
    """Docstring + imports dados + los nodos de nivel superior `names` (texto fuente original, con sus comentarios
    finales de línea). Error si falta alguno: así el generador no queda desfasado de src en silencio."""
    text = (SRC / rel).read_text(encoding="utf-8")
    lines = text.splitlines()
    tree = ast.parse(text)
    found: dict[str, str] = {}
    for node in tree.body:
        name = _top_name(node)
        if name in names:
            start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            found[name] = "\n".join(lines[start - 1 : node.end_lineno])
    missing = [n for n in names if n not in found]
    if missing:
        raise SystemExit(f"{rel}: no se encontraron {missing}; actualizar EXTRACTS")
    doc = ast.get_docstring(tree) or ""
    head = f'"""{doc.splitlines()[0] if doc else rel} (extracto para el notebook de entrega)."""'
    body = "\n\n".join(
        found[n] if not found[n].startswith(("def ", "class ")) else "\n" + found[n] for n in names
    )
    return f"{head}\n\n" + "\n".join(imports) + "\n\n" + body.strip() + "\n"


def writefile(rel: str, src: str):
    return code(f"%%writefile {{LIB}}/optimum/{rel}\n{src.rstrip()}")


def module_doc(rel: str) -> str:
    doc = ast.get_docstring(ast.parse((SRC / rel).read_text(encoding="utf-8"))) or ""
    return doc.strip()


# --------------------------------------------------------------------------- celdas fijas
INTRO = r"""
# Optimum Investments · Optimización del riesgo patrimonial (OP01)

Notebook **autocontenido** de la entrega: recibe `input.json` (contrato v1.0, Anexo 1), muestra los datos,
optimiza la cartera de activos y pasivos y escribe `output.json`.

$$\max_{x,y}\; E[\Delta PN] - \lambda\,\mathrm{CVaR}_\alpha(-\Delta PN) - TC$$

sujeto a presupuestos, límites de composición y restricciones comunes. Se resuelve como LP de
Rockafellar–Uryasev sobre escenarios a un año (bootstrap por bloques + estrés) revalorizados flujo a flujo.

**Cómo usarlo**
1. Deje `input.json` en la misma carpeta que este notebook (o escriba su ruta en `INPUT_PATH`; si no existe,
   el notebook la pide).
2. *Run All*. Tarda 2–4 minutos (pruebas incluidas); con `RUN_SENSITIVITY = True`, unos 6–8 minutos más.
3. El resultado queda en `OUTPUT_PATH` (por defecto `output.json`, junto al notebook).

**Requisitos:** Python ≥ 3.11 con `numpy pandas scipy cvxpy highspy clarabel matplotlib`
(`pip install numpy pandas scipy cvxpy highspy clarabel matplotlib`).

Ningún instrumento, límite, λ, α, costo o presupuesto está fijo en el código: todo sale de `input.json`.
Convenciones: montos en S/ millones, tasas en decimales, tiempo ACT/365; PN = V(activos) − V(pasivos) y
pérdida = −ΔPN.
"""

PARAMS = """
# Parámetros de ejecución
INPUT_PATH = "input.json"  # ruta al input; si no existe, se pide por teclado
OUTPUT_PATH = "output.json"  # dónde se escribe el resultado
RUN_SENSITIVITY = False  # True: corre las sensibilidades S1–S9 (≈ 6–8 min) y escribe sensitivity.json
SAVE_FIGURES = False  # True: guarda cada figura como PNG en la carpeta figuras/
"""

DEPS = """
import importlib
import sys

_missing = [m for m in ["numpy", "pandas", "scipy", "cvxpy", "highspy", "clarabel", "matplotlib"]
            if importlib.util.find_spec(m) is None]
if _missing:
    raise ImportError(f"Faltan paquetes: {_missing}. Instalar con: pip install {' '.join(_missing)}")

import cvxpy as cp

_solvers = {"HIGHS", "CLARABEL"} - set(cp.installed_solvers())
if _solvers:
    raise ImportError(f"cvxpy no encuentra los solvers {_solvers}: pip install highspy clarabel")
print(f"Python {sys.version.split()[0]} · cvxpy {cp.__version__} · solvers OK")
"""

LIB_SETUP = """
# Paquete temporal `optimum` con el código del modelo (las celdas %%writefile siguientes lo llenan)
import tempfile
from pathlib import Path

LIB = tempfile.mkdtemp(prefix="optimum_lib_")
for sub in ["optimum/io", "optimum/reporting"]:
    Path(LIB, sub).mkdir(parents=True, exist_ok=True)
for name in {empty}:
    Path(LIB, "optimum", name).touch()
sys.path.insert(0, LIB)
print("Código del modelo en", LIB)
"""

IMPORTS = r"""
import json
import time

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import display
from matplotlib import colormaps

for _m in [m for m in sys.modules if m == "optimum" or m.startswith("optimum.")]:
    del sys.modules[_m]  # si se re-ejecuta, recargar el código recién escrito
import optimum

assert Path(optimum.__file__).is_relative_to(LIB), f"se importó otro paquete optimum: {optimum.__file__}"

from optimum import optimizer as opt
from optimum import risk, sensitivity
from optimum.io.json_contract import _clean, validate_input, validate_output
from optimum.reporting.labels import SIDES, constraint_label, coupon_rule, horizon_mode
from optimum.valuation import calibrate_spreads, value_at_t0

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 30)

COLORS = {
    "PEN": "#1f4e79",
    "USD": "#c55a11",
    "ASSET": "#2e7d32",
    "LIABILITY": "#b71c1c",
    "EQUITY": "#6a1b9a",
    "neutral": "#595959",
}
mpl.rcParams.update(
    {
        "figure.figsize": (9, 4.5),
        "figure.dpi": 100,
        "font.size": 9,
        "axes.titlesize": 10,
        "legend.fontsize": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.3,
    }
)
FIG_DIR = Path("figuras")


def show(fig, name: str) -> None:
    # Muestra la figura y, si SAVE_FIGURES, la guarda en figuras/<name>.png
    fig.tight_layout()
    if SAVE_FIGURES:
        FIG_DIR.mkdir(exist_ok=True)
        fig.savefig(FIG_DIR / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.show()
"""

LOAD = """
path = Path(INPUT_PATH).expanduser()
while not path.is_file():
    answer = input(f"No se encontró '{path}'. Ruta del input.json: ").strip().strip('"').strip("'")
    if not answer:
        raise FileNotFoundError("No se indicó un input.json")
    path = Path(answer).expanduser()

doc = json.loads(path.read_text(encoding="utf-8"))
errors = validate_input(doc)
if errors:
    raise ValueError("input.json inválido:\\n- " + "\\n- ".join(errors))

cp_ = doc["caseParameters"]
com = doc["constraints"]["common"]
lam, alpha = cp_["riskAversionLambda"], cp_["cvarAlpha"]
tag = f"{alpha * 100:g}"
inst = pd.DataFrame(doc["instruments"]).set_index("id")
hist = risk.history_from_doc(doc)
print(f"{path.resolve()}")
print(f"Caso {doc['caseId']} · valorización {doc['valuationDate']} → horizonte {doc['horizonDate']} · "
      f"moneda base {doc['baseCurrency']}")
print(f"{len(doc['marketHistory'])} observaciones de mercado ({hist.index[0]:%Y-%m} a {hist.index[-1]:%Y-%m}) · "
      f"{len(inst)} instrumentos · {len(doc['cashFlows'])} flujos · {len(doc.get('stressScenarios', []))} estrés")
print(f"λ = {lam} · α = {alpha} · medida {cp_.get('riskMeasure')} · {cp_['bootstrapCount']} escenarios bootstrap "
      f"(p = {cp_['bootstrapProbability']}) · semilla {cp_['seed']}")
"""

BALANCE = """
bal = inst[["side", "name", "instrument_type", "currency", "market_value_pen", "notional_native", "maturity"]].copy()
bal["side"] = bal["side"].map(SIDES)
pn0 = inst.loc[inst["side"] == "ASSET", "market_value_pen"].sum() - inst.loc[inst["side"] == "LIABILITY", "market_value_pen"].sum()
print(f"Activos {inst.loc[inst['side'] == 'ASSET', 'market_value_pen'].sum():,.1f} · "
      f"Pasivos {inst.loc[inst['side'] == 'LIABILITY', 'market_value_pen'].sum():,.1f} · PN0 {pn0:,.1f} S/ mm")

fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
for ax, side, title in zip(axes, ["ASSET", "LIABILITY"], ["Activos", "Pasivos"], strict=True):
    t = inst[inst["side"] == side]
    ax.bar(t.index, t["market_value_pen"], color=[COLORS[c] for c in t["currency"]])
    for k, (_, r) in enumerate(t.iterrows()):
        ax.annotate(r["instrument_type"].replace("BOND_", ""), (k, r["market_value_pen"]), ha="center",
                    va="bottom", fontsize=7)
    ax.set_title(f"{title} ({t['market_value_pen'].sum():,.0f} S/ mm)")
axes[0].set_ylabel("Valor de mercado (S/ mm)")
axes[1].legend(handles=[mpl.patches.Patch(color=COLORS[c], label=c) for c in ["PEN", "USD"]])
fig.suptitle("Balance inicial por instrumento (color = moneda)")
show(fig, "balance_inicial")
bal
"""

CURVES = """
t0 = hist.index[-1]
nodes = [n["id"] for n in doc["curveNodes"]]
years = [n["years"] for n in doc["curveNodes"]]
fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
for ccy in ["PEN", "USD"]:
    axes[0].plot(years, 100 * hist.loc[t0, [f"{ccy}_SPOT_{n}" for n in nodes]], "-o", ms=4, color=COLORS[ccy],
                 label=f"{ccy} {t0:%Y-%m-%d}")
    axes[0].plot(years, 100 * hist.iloc[0][[f"{ccy}_SPOT_{n}" for n in nodes]], ":", color=COLORS[ccy],
                 label=f"{ccy} {hist.index[0]:%Y-%m-%d}")
axes[0].set(title="Curvas spot (inicio y t0)", xlabel="Plazo (años)", ylabel="Tasa spot (%)")
axes[0].legend(fontsize=7)
for ax, ccy in zip(axes[1:], ["PEN", "USD"], strict=True):
    for n, shade in zip(nodes, np.linspace(0.35, 1.0, len(nodes)), strict=True):
        ax.plot(hist.index, 100 * hist[f"{ccy}_SPOT_{n}"], color=COLORS[ccy], alpha=shade, lw=1, label=n)
    ax.set(title=f"Historia spot {ccy}", ylabel="%")
    ax.legend(fontsize=6, ncol=3)
for ax in axes[1:]:
    ax.tick_params(axis="x", labelrotation=30)
show(fig, "curvas_spot")
"""

FX_EQ = """
fig, axes = plt.subplots(1, 2, figsize=(10, 3.2))
axes[0].plot(hist.index, hist["FX_PENUSD"], color=COLORS["USD"])
axes[0].set(title="Tipo de cambio PEN por USD", ylabel="PEN/USD")
axes[1].plot(hist.index, hist["EQUITY_USD"], color=COLORS["EQUITY"])
axes[1].set(title="Índice de renta variable (USD)", ylabel="Nivel")
fig.autofmt_xdate()
show(fig, "fx_equity")
"""

CASHFLOWS = """
cf = pd.DataFrame(doc["cashFlows"])
cf["year"] = pd.to_datetime(cf["payment_date"]).dt.year
fx0 = hist.loc[t0, "FX_PENUSD"]
cf["pen"] = cf["total_cash_flow"] * np.where(cf["currency"] == "USD", fx0, 1.0)  # al tipo de cambio de t0
prof = cf.pivot_table(index="year", columns="side", values="pen", aggfunc="sum").fillna(0.0)
fig, ax = plt.subplots(figsize=(9, 3.5))
k = np.arange(len(prof))
ax.bar(k - 0.2, prof.get("ASSET", 0), 0.4, color=COLORS["ASSET"], label="Activos (cobros)")
ax.bar(k + 0.2, -prof.get("LIABILITY", 0), 0.4, color=COLORS["LIABILITY"], label="Pasivos (pagos)")
ax.axhline(0, color="black", lw=0.6)
ax.set_xticks(k, prof.index)
ax.set(title="Flujos contractuales/proyectados por año (S/ mm, FX de t0)", ylabel="S/ mm")
ax.legend()
show(fig, "perfil_flujos")
"""

FACTORS_CELL = """
chg = risk.factor_changes(doc)
corr = chg.corr()
cov = risk.covariance(chg)
eig = np.sort(np.linalg.eigvalsh(cov.to_numpy()))[::-1]

fig, axes = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [1.3, 1]})
im = axes[0].imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
axes[0].set_xticks(range(len(corr)), corr.columns, rotation=90, fontsize=6)
axes[0].set_yticks(range(len(corr)), corr.index, fontsize=6)
axes[0].grid(False)
fig.colorbar(im, ax=axes[0], shrink=0.8)
axes[0].set_title("Correlación de cambios mensuales de factores")
axes[1].semilogy(np.arange(1, len(eig) + 1), np.clip(eig, 1e-20, None), "o-", ms=3, color=COLORS["neutral"])
axes[1].set(title="Autovalores de Σ anualizada (escala log)", xlabel="Componente", ylabel="Autovalor")
show(fig, "correlacion_factores")
var_share = np.cumsum(eig) / eig.sum()
print(f"{len(chg)} cambios mensuales · 3 primeros componentes explican {100 * var_share[2]:.1f} % de la varianza · "
      f"autovalores ≈ 0 (< 1e-10 × máx.): {(eig < 1e-10 * eig.max()).sum()} (Σ singular: forwards derivadas de spots)")
"""

LIMITS = """
lim = pd.DataFrame(doc["constraints"]["weights"])
lim["Restricción"] = [constraint_label(f"{r.side}:{r.dimension}:{r.category}") for r in lim.itertuples()]
print("Restricciones comunes:", com)
display(lim.set_index("Restricción")[["min_weight", "max_weight", "note"]])
stress_in = pd.DataFrame(doc.get("stressScenarios", []))
stress_in
"""

SCEN = """
t_start = time.perf_counter()
scen = risk.build_scenarios(doc)
reval, flows = risk.scenario_components(doc, scen.deltas)  # revalorización completa por escenario
comps = (reval, flows, scen)
data = opt.prepare(doc, components=comps)
kind = np.asarray(scen.kind)
print(f"{len(scen.ids)} escenarios ({(kind == 'bootstrap').sum()} bootstrap + {(kind == 'stress').sum()} estrés), "
      f"Σp = {scen.probs.sum():.6f} · {time.perf_counter() - t_start:.0f} s")
mu = risk.drift(doc, chg)
mu[mu != 0].rename("deriva anual μ").to_frame()
"""

SPREADS = """
spreads = calibrate_spreads(doc)
v0 = value_at_t0(doc, spreads)
cal = pd.DataFrame(
    {
        "Mercado (S/ mm)": inst["market_value_pen"],
        "V0 modelo (S/ mm)": v0.reindex(inst.index),
        "Spread calibrado (pb)": 1e4 * pd.Series(spreads).reindex(inst.index),
        "Spread de referencia (pb)": 1e4 * pd.Series(doc["calibrationSpreads"]).reindex(inst.index),
    }
)
cal["Error (S/ mm)"] = cal["V0 modelo (S/ mm)"] - cal["Mercado (S/ mm)"]
print(f"Máximo error de calibración: {cal['Error (S/ mm)'].abs().max():.2e} S/ mm")
cal.round(4)
"""

SHOCKS = """
boot = scen.deltas[kind == "bootstrap"]
stress = scen.deltas[kind == "stress"]
fig, axes = plt.subplots(2, 3, figsize=(12, 5.5))
panels = [
    ("PEN_SPOT_ON", "PEN ON (pb)", 1e4, COLORS["PEN"]),
    ("PEN_SPOT_10Y", "PEN 10Y (pb)", 1e4, COLORS["PEN"]),
    ("USD_SPOT_ON", "USD ON (pb)", 1e4, COLORS["USD"]),
    ("USD_SPOT_10Y", "USD 10Y (pb)", 1e4, COLORS["USD"]),
    ("FX_PENUSD", "FX (log-ret., %)", 100, COLORS["USD"]),
    ("EQUITY_USD", "Equity (log-ret., %)", 100, COLORS["EQUITY"]),
]
for ax, (f, label, k, color) in zip(axes.flat, panels, strict=True):
    ax.hist(k * boot[f], bins=30, color=color, alpha=0.7)
    for v in k * stress[f]:
        ax.axvline(v, color="black", ls="--", lw=0.8)
    ax.set_title(label)
fig.suptitle("Shocks a un año: bootstrap (histograma) y estrés (líneas)")
show(fig, "shocks_escenarios")

R = data.returns
p = data.probs
er = pd.DataFrame(
    {
        "lado": inst["side"].map(SIDES),
        "moneda": inst["currency"],
        "E[r] (%)": 100 * (R @ p),
        "σ(r) (%)": 100 * np.sqrt(((R.sub(R @ p, axis=0)) ** 2) @ p),
        "r estrés mín. (%)": 100 * R.loc[:, kind == "stress"].min(axis=1),
        "r estrés máx. (%)": 100 * R.loc[:, kind == "stress"].max(axis=1),
    }
)
fig, ax = plt.subplots(figsize=(8, 4))
for i, r in er.iterrows():
    ax.scatter(r["σ(r) (%)"], r["E[r] (%)"], color=COLORS[r["moneda"]],
               marker="o" if r["lado"] == SIDES["ASSET"] else "s", s=40)
    ax.annotate(i, (r["σ(r) (%)"], r["E[r] (%)"]), textcoords="offset points", xytext=(4, 3), fontsize=7)
ax.set(xlabel="σ(r) a un año (%)", ylabel="E[r] a un año (%)",
       title="Resultado por S/ invertido (● activos, ■ pasivos = costo; color = moneda)")
show(fig, "riesgo_retorno_instrumentos")
er.round(2)
"""

SOLVE = """
t_start = time.perf_counter()
out = opt.solve(doc, components=comps)  # óptimo + posición inicial + barrido de λ + media-varianza + variante
errors = validate_output(out)
if errors:
    raise ValueError("output inválido:\\n- " + "\\n- ".join(errors))
Path(OUTPUT_PATH).write_text(json.dumps(_clean(out), indent=2, ensure_ascii=False), encoding="utf-8")
print(f"{Path(OUTPUT_PATH).resolve()} · status {out['status']} · objetivo {out['objectiveValue']} · "
      f"{time.perf_counter() - t_start:.0f} s")
if out["status"] not in opt.OPTIMAL:
    raise RuntimeError(f"El problema no tiene solución óptima (status {out['status']}); output.json sin posiciones.")
if out["status"] == "OPTIMAL_INACCURATE":
    print("ADVERTENCIA: solución inexacta; revisar constraintChecks.")
an = out["analysis"]
ini, mv, hv = an["initialPosition"], an["meanVarianceBenchmark"], an["horizonMaturityVariant"]
label_opt, label_mv, label_hv = f"Óptimo (λ = {lam:g})", "Mínima varianza", "Venc. exigidos al horizonte"
"""

POSITIONS = """
pos = pd.DataFrame(out["positions"]["assets"] + out["positions"]["liabilities"]).set_index("id")
pos_tab = pd.DataFrame(
    {
        "Lado": inst["side"].map(SIDES),
        "Instrumento": pos["name"],
        "Moneda": pos["currency"],
        "Inicial": pos["initial"],
        label_opt: pos["optimal"],
        "Cambio": pos["change"],
        label_mv: pd.Series(mv.get("positions", {})),
        label_hv: pd.Series(hv.get("positions", {})),
    }
)
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for ax, side in zip(axes, ["ASSET", "LIABILITY"], strict=True):
    t = pos_tab[pos_tab["Lado"] == SIDES[side]]
    k = np.arange(len(t))
    ax.bar(k - 0.2, t["Inicial"], 0.38, color=COLORS["neutral"], alpha=0.45, label="Inicial")
    ax.bar(k + 0.2, t[label_opt], 0.38, color=COLORS[side], label=label_opt)
    ax.scatter(k + 0.2, t[label_hv], marker="_", s=180, color="black", zorder=3, label=label_hv)
    ax.set_xticks(k, [f"{i}\\n{c}" for i, c in zip(t.index, t["Moneda"], strict=True)], fontsize=7)
    ax.set_title(SIDES[side])
axes[0].set_ylabel("S/ mm")
axes[1].legend(fontsize=7)
fig.suptitle("Posiciones inicial y óptima")
show(fig, "posiciones_inicial_optima")
pos_tab.round(2)
"""

METRICS = """
def metric_rows(m: dict, objective: float) -> dict:
    return {
        "Objetivo (E − λ·CVaR − TC)": objective,
        "E[ΔPN]": m["expectedNetWorthChange"],
        "Costo de transacción": m["transactionCosts"],
        "E[ΔPN] − TC": m["expectedNetWorthChange"] - m["transactionCosts"],
        "E[PN] al horizonte": m["expectedTerminalNetWorth"],
        "σ(ΔPN)": m["netWorthVolatility"],
        f"VaR {tag} %": m[f"var{tag}Loss"],
        f"CVaR {tag} %": m[f"cvar{tag}Loss"],
        "Rentabilidad esperada activos (%)": 100 * m["expectedAssetReturn"],
        "Costo esperado pasivos (%)": 100 * m["expectedLiabilityEconomicCost"],
        "Estrés en la cola (%)": 100 * m["tailStressShare"],
        **{f"Pérdida {k}": v for k, v in m["stressLosses"].items()},
    }


cols = {"Inicial": metric_rows(ini["metrics"], ini["objective"]),
        label_opt: metric_rows(out["metrics"], out["objectiveValue"])}
for name, alt in [(label_mv, mv), (label_hv, hv)]:
    if alt.get("metrics"):
        cols[name] = metric_rows(alt["metrics"], alt["objective"])
met = pd.DataFrame(cols)
print("Límites que incumple la posición inicial:", [constraint_label(c) for c in ini["violatedConstraints"]] or "ninguno")
met.round(2)
"""

DIST = """
positions = {"Inicial": data.x0, label_opt: pos["optimal"]}
if mv.get("positions"):
    positions[label_mv] = pd.Series(mv["positions"])
ev = {k: opt.evaluate(data, v) for k, v in positions.items()}
assert abs(ev[label_opt]["cvar"] - out["metrics"][f"cvar{tag}Loss"]) < 1e-6  # coherencia con output.json

r = data.returns.to_numpy()
styles = {"Inicial": COLORS["neutral"], label_opt: COLORS["ASSET"], label_mv: COLORS["USD"]}
dpns = {name: (data.sign * x.reindex(data.ids).to_numpy()) @ r for name, x in positions.items()}
bins = np.linspace(np.floor(min(d.min() for d in dpns.values())), np.ceil(max(d.max() for d in dpns.values())), 61)
fig, ax = plt.subplots(figsize=(10, 4.2))
for j, (name, dpn) in enumerate(dpns.items()):
    ax.hist(dpn[kind == "bootstrap"], bins=bins, histtype="step", lw=1.4, color=styles[name], label=name)
    ax.scatter(dpn[kind == "stress"], np.full((kind == "stress").sum(), -2.0 - 3 * j), marker="v", s=28,
               color=styles[name], zorder=3)
    ax.axvline(-ev[name]["cvar"], color=styles[name], ls=":", lw=1.2)
ax.set(xlabel="ΔPN a un año (S/ mm)", ylabel="Escenarios bootstrap",
       title=f"Distribución de ΔPN (▼ estrés; punteada: −CVaR {tag} %)")
ax.legend(fontsize=8)
show(fig, "distribucion_dpn")

sl = pd.DataFrame({"Inicial": ini["metrics"]["stressLosses"], label_opt: out["metrics"]["stressLosses"]})
fig, ax = plt.subplots(figsize=(8, 3.2))
k = np.arange(len(sl))
ax.barh(k + 0.2, sl["Inicial"], 0.4, color=COLORS["neutral"], alpha=0.6, label="Inicial")
ax.barh(k - 0.2, sl[label_opt], 0.4, color=COLORS["ASSET"], label=label_opt)
ax.axvline(0, color="black", lw=0.6)
ax.set_yticks(k, sl.index)
ax.set(xlabel="Pérdida (S/ mm; < 0 = ganancia)", title="Pérdida en cada escenario de estrés")
ax.legend(fontsize=8)
show(fig, "perdidas_estres")
"""

CHECKS = """
chk = pd.DataFrame(out["constraintChecks"])
chk_tab = pd.DataFrame(
    {"Valor": chk["value"], "Mín.": chk["min"], "Máx.": chk["max"], "Cumple": np.where(chk["ok"], "sí", "NO"),
     "Activa": np.where(chk["active"], "sí", ""), "Nota": chk["note"]}
)
chk_tab.index = chk["name"].map(constraint_label)
print(f"{chk['active'].sum()} restricciones activas de {len(chk)} · incumplidas: {(~chk['ok']).sum()}")

dims = chk["name"].str.split(":")
wt = chk[dims.str.len().ge(3) & dims.str[1].isin(["CURRENCY", "TYPE", "RATE_TYPE", "MATURITY"])]
fig, ax = plt.subplots(figsize=(9, 0.32 * len(wt) + 1))
y = np.arange(len(wt))[::-1]
lo = wt["min"].astype(float).fillna(0.0).to_numpy()
hi = wt["max"].astype(float).fillna(1.0).to_numpy()
ax.barh(y, 100 * (hi - lo), left=100 * lo, color=COLORS["neutral"], alpha=0.2, label="Rango permitido")
ax.scatter(100 * wt["value"], y, color=np.where(wt["active"], COLORS["LIABILITY"], COLORS["ASSET"]), zorder=3,
           label="Peso óptimo (rojo = activa)")
ax.set_yticks(y, wt["name"].map(constraint_label), fontsize=7)
ax.set(xlabel="% del lado", title="Pesos del óptimo frente a los límites")
ax.legend(fontsize=7, loc="lower right")
show(fig, "pesos_limites")
chk_tab
"""

SWEEP = """
def w(s, dim, side, cat):
    return 100 * s["weights"][dim][side].get(cat, 0.0) if s.get("weights") else np.nan


sweep = pd.DataFrame(
    [
        {
            "λ": s["lambda"],
            "Status": s["status"],
            "E[ΔPN]": s["metrics"].get("expectedNetWorthChange"),
            "TC": s["metrics"].get("transactionCosts"),
            "E[ΔPN] − TC": s["metrics"].get("expectedNetWorthChange", np.nan) - s["metrics"].get("transactionCosts", np.nan),
            "σ(ΔPN)": s["metrics"].get("netWorthVolatility"),
            f"CVaR {tag} %": s["metrics"].get(f"cvar{tag}Loss"),
            "Activos USD (%)": w(s, "byCurrency", "ASSET", "USD"),
            "Equity (%)": w(s, "byType", "ASSET", "EQUITY"),
            "Pasivos USD (%)": w(s, "byCurrency", "LIABILITY", "USD"),
            "Pasivos flotantes (%)": w(s, "byRateType", "LIABILITY", "FLOAT"),
        }
        for s in an["lambdaSweep"]
    ]
).set_index("λ")

fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), gridspec_kw={"width_ratios": [1.2, 1, 1]})
ax = axes[0]
ax.plot(sweep[f"CVaR {tag} %"], sweep["E[ΔPN] − TC"], "-o", color=COLORS["ASSET"], ms=4, label="Frontera CVaR (λ)")
for lam_k, r in sweep.iterrows():
    ax.annotate(f"λ={lam_k:g}", (r[f"CVaR {tag} %"], r["E[ΔPN] − TC"]), textcoords="offset points", xytext=(4, 4), fontsize=7)
for name, alt, color, marker in [("Inicial", ini, COLORS["neutral"], "s"), (label_mv, mv, COLORS["USD"], "D"),
                                 (label_hv, hv, COLORS["LIABILITY"], "^")]:
    if alt.get("metrics"):
        m = alt["metrics"]
        ax.scatter(m[f"cvar{tag}Loss"], m["expectedNetWorthChange"] - m["transactionCosts"], color=color,
                   marker=marker, s=40, zorder=3, label=name)
ax.set(xlabel=f"CVaR {tag} % (S/ mm)", ylabel="E[ΔPN] − TC (S/ mm)", title="Frontera resultado neto vs. CVaR")
ax.legend(fontsize=7)

comp = pd.DataFrame([s.get("positions") or {} for s in an["lambdaSweep"]], index=[f"{v:g}" for v in sweep.index])
cmaps = {"PEN": "Blues", "USD": "Oranges"}
for ax, side in zip(axes[1:], ["ASSET", "LIABILITY"], strict=True):
    ids = inst.index[inst["side"] == side]
    bottom = np.zeros(len(comp))
    for ccy in sorted(inst["currency"].unique()):
        sub = [i for i in ids if inst.loc[i, "currency"] == ccy and i in comp]
        shades = colormaps[cmaps.get(ccy, "Greys")](np.linspace(0.45, 0.9, max(len(sub), 1)))
        for i, c in zip(sub, shades, strict=False):
            ax.bar(comp.index, comp[i].fillna(0.0), bottom=bottom, color=c, label=f"{i} ({ccy})", width=0.7)
            bottom += comp[i].fillna(0.0).to_numpy()
    ax.set(title=f"Composición de {SIDES[side].lower()} por λ", xlabel="λ")
    ax.legend(fontsize=6, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.15))
axes[1].set_ylabel("S/ mm")
show(fig, "barrido_lambda")
sweep.round(2)
"""

HORIZON = """
breaches = pd.DataFrame(
    {
        "Prob. (%)": {k: 100 * v["probability"] for k, v in out["metrics"]["horizonBreaches"].items()},
        "Peor valor": {k: v["worst"] for k, v in out["metrics"]["horizonBreaches"].items()},
        "Causa": {k: v.get("cause") or "" for k, v in out["metrics"]["horizonBreaches"].items()},
    }
)
breaches.index = breaches.index.map(constraint_label)
print(f"Modo de vencimientos al horizonte: {horizon_mode(out['horizonMaturityLimits'])} · "
      f"costo de exigirlos en t_H: {hv.get('objectiveCost', float('nan')):.3f} S/ mm de objetivo")
breaches[breaches["Prob. (%)"] > 0].round(3)
"""

TESTS_SETUP = """
import copy

TOL = 1e-6
test_results = []


def run_test(name: str, what: str, fn) -> None:
    # Ejecuta una prueba (función sin argumentos con asserts) y guarda el resultado; no detiene el notebook
    t_start = time.perf_counter()
    try:
        detail = fn() or ""
        ok = True
    except Exception as exc:  # noqa: BLE001 - se reporta cualquier falla en la tabla
        detail, ok = f"{type(exc).__name__}: {exc}", False
    test_results.append({"Prueba": name, "Qué verifica": what, "Resultado": "pasa" if ok else "FALLA",
                         "Detalle": detail, "s": round(time.perf_counter() - t_start, 1)})
    print(f"[{'pasa' if ok else 'FALLA'}] {name} · {detail}")


def with_changes(fn) -> dict:
    # Copia profunda de `doc` con una modificación; el input original no se toca
    d = copy.deepcopy(doc)
    fn(d)
    return d


def set_weight(d: dict, side: str, dimension: str, category: str, **vals) -> None:
    rows = [w for w in d["constraints"]["weights"] if (w["side"], w["dimension"], w["category"]) == (side, dimension, category)]
    assert rows, f"no existe el grupo {side}/{dimension}/{category} en input.json"
    for w in rows:
        w.update(vals)
"""

TEST_TOY = """
# Balance de juguete: caja C1 y bono B1 (activos, B_A = 100) y un pasivo L1 fijo en 80; cinco escenarios.
# La única decisión es la caja c ∈ [10, 60]. La cola del 10 % son S4 y S5, así que, a mano:
#   E[ΔPN] = 2.88 − 0.0228 c,  CVaR_0.90 = 7.6 − 0.082 c,  TC = 0.002 |c − 30|.
# Con λ = 0.5 la pendiente para c > 30 es −0.0248 + 0.041 > 0  ⇒  c* = 60 (tope de caja).
#   E = 1.512, CVaR = 2.68, TC = 0.06, objetivo = 1.512 − 0.5·2.68 − 0.06 = 0.112.
TOY_SCEN = ["S1", "S2", "S3", "S4", "S5"]
TOY_PROBS = np.array([0.40, 0.30, 0.20, 0.06, 0.04])
TOY_R_BOND = np.array([0.08, 0.06, 0.04, -0.02, -0.10])
TOY_BOND_FLOWS = np.array([0.05, 0.05, 0.05, 0.05, 0.0])


def toy_doc(min_cash: float = 8.0) -> dict:
    def inst_(iid, side, typ, mv, maturity):
        return {"id": iid, "side": side, "name": iid, "instrument_type": typ, "currency": "PEN",
                "market_value_pen": mv, "notional_native": mv, "fixed_coupon": None, "frequency": None,
                "maturity": maturity, "reference_factor": None, "spread": None, "reset_months": None,
                "other_market_ref": None, "notes": ""}

    weights = [("ASSET", "TYPE", "CASH", 0.10, 0.60), ("ASSET", "TYPE", "FIXED_INCOME", 0.40, 0.90),
               ("ASSET", "CURRENCY", "PEN", 0.0, 1.0), ("LIABILITY", "CURRENCY", "PEN", 0.0, 1.0),
               ("LIABILITY", "RATE_TYPE", "FIXED", 0.0, 1.0)]
    return {
        "schemaVersion": "1.0", "caseId": "TOY", "valuationDate": "2025-12-31", "horizonDate": "2026-12-31",
        "baseCurrency": "PEN",
        "instruments": [inst_("C1", "ASSET", "CASH", 30.0, None), inst_("B1", "ASSET", "BOND_FIXED", 70.0, "2030-12-31"),
                        inst_("L1", "LIABILITY", "BOND_FIXED", 80.0, "2030-12-31")],
        "constraints": {
            "weights": [{"index": k, "side": s, "dimension": dm, "category": c, "min_weight": lo, "max_weight": hi,
                         "note": ""} for k, (s, dm, c, lo, hi) in enumerate(weights)],
            "common": {"minNetWorth": 15.0, "maxLiabilitiesToAssets": 0.85, "minCash": min_cash, "assetBudget": 100.0,
                       "liabilityBudget": 80.0, "allowShort": False},
        },
        "transactionCosts": {
            "C1": {"side": "ASSET", "restructuring_cost": 0.0, "reduction_prepayment_cost": 0.0},
            "B1": {"side": "ASSET", "restructuring_cost": 0.002, "reduction_prepayment_cost": 0.0},
            "L1": {"side": "LIABILITY", "restructuring_cost": 0.01, "reduction_prepayment_cost": 0.01},
        },
        "fundingAlternatives": [], "stressScenarios": [],
        "caseParameters": {"horizonDate": "2026-12-31", "cvarAlpha": 0.90, "riskAversionLambda": 0.5,
                           "lambdaGrid": [0.0, 0.5], "riskMeasure": "CVAR", "bootstrapCount": 4,
                           "bootstrapProbability": 0.96, "stressProbability": 0.04, "seed": 1},
    }


def toy_components():
    # Rendimientos por S/ (reval + flujos): caja 3 %, bono TOY_R_BOND, pasivo 3 % en todos los escenarios
    ids = ["C1", "B1", "L1"]
    reval = pd.DataFrame([np.full(5, 0.03), TOY_R_BOND - TOY_BOND_FLOWS, np.full(5, 0.03 - 0.04)], index=ids,
                         columns=TOY_SCEN)
    flows = pd.DataFrame([np.zeros(5), TOY_BOND_FLOWS, np.full(5, 0.04)], index=ids, columns=TOY_SCEN)
    scen_ = risk.ScenarioSet(ids=list(TOY_SCEN), deltas=pd.DataFrame(0.0, index=TOY_SCEN, columns=risk.FACTORS),
                             probs=TOY_PROBS.copy(), kind=["bootstrap"] * 4 + ["stress"])
    return reval, flows, scen_


def test_toy_by_hand():
    res = opt.solve_data(opt.prepare(toy_doc(), components=toy_components()))
    assert res["status"] == "OPTIMAL", res["status"]
    got = {k: float(res["positions"][k]) for k in ["C1", "B1", "L1"]}
    for k, v in {"C1": 60.0, "B1": 40.0, "L1": 80.0}.items():
        assert abs(got[k] - v) < TOL, (k, got[k])
    assert abs(res["objective"] - 0.112) < TOL, res["objective"]
    assert abs(res["cvar_lp"] - 2.68) < TOL, res["cvar_lp"]
    assert abs(res["transaction_cost"] - 0.06) < TOL, res["transaction_cost"]
    return f"caja {got['C1']:.4f}, bono {got['B1']:.4f}, objetivo {res['objective']:.6f} (a mano 0.112)"


run_test("1. Caso simple resuelto a mano", "Juguete de 2 activos, 1 pasivo y 5 escenarios: posiciones, CVaR, TC "
         "y objetivo iguales a la solución analítica (tol. 1e-6)", test_toy_by_hand)
"""

TEST_REAL = """
def test_lp_cvar_ex_post():
    # El CVaR del LP (ζ + Σ p u / (1 − α)) coincide con el CVaR recalculado ex post, en el óptimo y en el barrido
    ev_opt = opt.evaluate(data, pos["optimal"])
    gaps = [abs(ev_opt["cvar"] - out["metrics"][f"cvar{tag}Loss"])]
    for lam_k in doc["caseParameters"]["lambdaGrid"]:
        if lam_k > 0:
            res = opt.solve_data(data, lam=lam_k)
            gaps.append(abs(res["cvar_lp"] - opt.evaluate(data, res["positions"])["cvar"]))
    assert max(gaps) < 1e-5, gaps
    return f"máx. diferencia {max(gaps):.1e} S/ mm en {len(gaps)} soluciones"


def test_budgets_and_limits():
    # Presupuestos, no negatividad y todos los límites del input en la solución óptima
    x = pos["optimal"]
    side = inst["side"].reindex(x.index)
    gap_a = abs(x[side == "ASSET"].sum() - com["assetBudget"])
    gap_l = abs(x[side == "LIABILITY"].sum() - com["liabilityBudget"])
    assert gap_a < TOL and gap_l < TOL, (gap_a, gap_l)
    assert (x >= -TOL).all(), x[x < -TOL]
    bad = [c["name"] for c in out["constraintChecks"] if not c["ok"]]
    assert not bad, bad
    return f"Σ activos = {com['assetBudget']:g}, Σ pasivos = {com['liabilityBudget']:g}, mín. posición {x.min():.2e}, " \\
           f"{len(out['constraintChecks'])} límites ok"


def test_short_rate_shock():
    # +500 pb en los nodos cortos (stressTenors.short) de PEN y USD en todos los escenarios: la exposición neta a la
    # tasa corta (caja + activos indexados al tramo corto − pasivos indexados a él) debe subir
    short_nodes = doc["caseParameters"]["stressTenors"]["short"]["nodes"]
    short_factors = [f for f in risk.FACTORS if "_SPOT_" in f and f.split("_SPOT_")[1] in short_nodes]
    segs = {s["id"] for s in doc["curveSegments"] if s["fromNode"] in short_nodes and s["toNode"] in short_nodes}
    ref_seg = inst["reference_factor"].map(lambda r: r.split("_")[-1] if isinstance(r, str) else None)
    short = (inst["instrument_type"] == "CASH") | ref_seg.isin(segs)
    deltas = scen.deltas.copy()
    deltas[short_factors] += 0.05
    reval_s, flows_s = risk.scenario_components(doc, deltas)
    scen_s = risk.ScenarioSet(scen.ids, deltas, scen.probs, scen.kind)
    shocked = opt.solve_data(opt.prepare(doc, components=(reval_s, flows_s, scen_s)))
    assert shocked["status"] == "OPTIMAL", shocked["status"]

    def agg(x, s):
        return float(x.reindex(inst.index[short & (inst["side"] == s)]).sum())

    a0, l0 = agg(pos["optimal"], "ASSET"), agg(pos["optimal"], "LIABILITY")
    a1, l1 = agg(shocked["positions"], "ASSET"), agg(shocked["positions"], "LIABILITY")
    assert a1 >= a0 - TOL and l1 <= l0 + TOL, (a0, a1, l0, l1)
    assert (a1 - l1) >= (a0 - l0) + 1.0, (a0 - l0, a1 - l1)
    return f"activos cortos {a0:.1f} → {a1:.1f}; pasivos cortos {l0:.1f} → {l1:.1f} S/ mm"


def test_infeasible():
    # Límites contradictorios: el programa informa INFEASIBLE, sin excepción y con un output que cumple el contrato
    cash_max = next(w["max_weight"] for w in doc["constraints"]["weights"]
                    if (w["side"], w["dimension"], w["category"]) == ("ASSET", "TYPE", "CASH"))
    cases = {
        "caja mínima > caja máxima": lambda d: d["constraints"]["common"].update(
            minCash=1.25 * cash_max * com["assetBudget"]),
        "mínimos de moneda suman 110 %": lambda d: (set_weight(d, "ASSET", "CURRENCY", "PEN", min_weight=0.90),
                                                    set_weight(d, "ASSET", "CURRENCY", "USD", min_weight=0.20)),
    }
    for label, mutate in cases.items():
        bad = with_changes(mutate)
        res = opt.solve(bad, components=comps)
        assert res["status"] == "INFEASIBLE", (label, res["status"])
        assert validate_output(res) == [], (label, validate_output(res))
    toy = opt.solve_data(opt.prepare(toy_doc(min_cash=70.0), components=toy_components()))
    assert toy["status"] == "INFEASIBLE" and toy["positions"] is None, toy["status"]
    return f"{len(cases) + 1} casos → INFEASIBLE con output válido"


def test_no_hardcoded_parameters():
    # Cambiar datos de input.json cambia la solución: concentración máx. de activos 30 % y λ = 5
    b_a = com["assetBudget"]
    conc = with_changes(lambda d: set_weight(d, "ASSET", "CONCENTRATION", "SINGLE_POSITION", max_weight=0.30))
    r1 = opt.solve_data(opt.prepare(conc, components=comps))
    assets = inst.index[inst["side"] == "ASSET"]
    assert r1["positions"][assets].max() <= 0.30 * b_a + TOL, r1["positions"][assets].max()
    d1 = (r1["positions"] - pos["optimal"]).abs().max()
    r2 = opt.solve_data(opt.prepare(with_changes(lambda d: d["caseParameters"].update(riskAversionLambda=5.0)),
                                    components=comps))
    d2 = (r2["positions"] - pos["optimal"]).abs().max()
    assert d1 > 1.0 and d2 > 1.0, (d1, d2)
    return f"concentración 30 %: máx. activo {r1['positions'][assets].max():.1f} (≤ {0.30 * b_a:g}); " \\
           f"cambio máx. {d1:.1f} y {d2:.1f} (λ = 5) S/ mm"


def test_lambda_monotonicity():
    # Más aversión al riesgo ⇒ CVaR y E[ΔPN] − TC no crecen (preferencia revelada)
    sw = [s for s in an["lambdaSweep"] if s["status"] in opt.OPTIMAL]
    cvar = [s["metrics"][f"cvar{tag}Loss"] for s in sw]
    net = [s["metrics"]["expectedNetWorthChange"] - s["metrics"]["transactionCosts"] for s in sw]
    assert len(sw) == len(an["lambdaSweep"]), "hay λ sin solución óptima"
    assert all(b <= a + 1e-5 for a, b in zip(cvar, cvar[1:], strict=False)), cvar
    assert all(b <= a + 1e-5 for a, b in zip(net, net[1:], strict=False)), net
    return f"CVaR {cvar[0]:.1f} → {cvar[-1]:.1f}; E − TC {net[0]:.2f} → {net[-1]:.2f} ({len(sw)} valores de λ)"


def test_calibration():
    # Los spreads calibrados reproducen el valor de mercado en t0
    err = float(cal["Error (S/ mm)"].abs().max())
    assert err < TOL, err
    return f"máx. |V0 − mercado| = {err:.1e} S/ mm"


run_test("2. CVaR del LP = CVaR ex post", "ζ + Σ p u/(1 − α) del LP coincide con el CVaR recalculado, en el óptimo "
         "y en cada λ del barrido", test_lp_cvar_ex_post)
run_test("3. Presupuestos y límites", "Σ activos = B_A, Σ pasivos = B_L, sin cortos y todos los límites cumplidos",
         test_budgets_and_limits)
run_test("4. Shock extremo de tasas (+500 pb)", "Con +500 pb en los nodos cortos de ambas curvas sube la exposición "
         "neta a la tasa corta", test_short_rate_shock)
run_test("5. Restricciones infactibles", "Límites contradictorios ⇒ INFEASIBLE sin excepción y output válido",
         test_infeasible)
run_test("6. Sin parámetros en el código", "Cambiar la concentración máxima o λ en el input cambia la solución",
         test_no_hardcoded_parameters)
run_test("7. Monotonía en λ", "Al subir λ, CVaR y E[ΔPN] − TC no crecen", test_lambda_monotonicity)
run_test("8. Calibración de spreads", "V0 del modelo = valor de mercado en t0 (tol. 1e-6)", test_calibration)
"""

TESTS_SUMMARY = """
tests_tab = pd.DataFrame(test_results).set_index("Prueba")
display(tests_tab)
n_fail = int((tests_tab["Resultado"] != "pasa").sum())
print(f"{len(tests_tab) - n_fail} de {len(tests_tab)} pruebas pasan")
assert n_fail == 0, f"{n_fail} pruebas fallan: revisar la tabla"
"""

SENS = """
if RUN_SENSITIVITY:
    sens = sensitivity.run_all(doc)
    Path(OUTPUT_PATH).with_name("sensitivity.json").write_text(
        json.dumps(_clean(sens), indent=2, ensure_ascii=False), encoding="utf-8")
    if "error" in sens:
        raise RuntimeError(sens["error"])
    print(f"Sensibilidades en {sens['meta']['runtimeSeconds']:.0f} s → sensitivity.json")
else:
    sens = None
    print("RUN_SENSITIVITY = False: se omiten S1–S9")
"""

SENS_S1 = """
if sens:
    cfg = cp_["sensitivities"]
    base_rule = cp_.get("floatingCouponRule") or "FLAT"
    rs = pd.DataFrame(sens["rateShocks"])
    names = {"initial": "Inicial", "optimal": label_opt, "meanVariance": "Mínima varianza"}
    order = [s["id"] for s in cfg["rateShocks"]]
    s1 = (rs[rs["rule"] == base_rule].pivot(index="shock", columns="portfolio", values="netWorth")
          .reindex(index=order, columns=[c for c in names if c in set(rs["portfolio"])]).rename(columns=names))
    for rule in sorted(set(rs["rule"]) - {base_rule}):
        sub = rs[(rs["rule"] == rule) & (rs["portfolio"] == "optimal")].set_index("shock")["netWorth"]
        s1[f"Óptimo, cupones {coupon_rule(rule)}"] = sub.reindex(order)
    fig, ax = plt.subplots(figsize=(11, 4))
    k = np.arange(len(s1))
    colors = [COLORS["neutral"], COLORS["ASSET"], COLORS["USD"], COLORS["PEN"], COLORS["EQUITY"]]
    width = 0.8 / len(s1.columns)
    for j, (c, color) in enumerate(zip(s1.columns, colors, strict=False)):
        ax.bar(k + (j - (len(s1.columns) - 1) / 2) * width, s1[c], width, color=color, label=c,
               alpha=0.5 if c == "Inicial" else 1.0)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xticks(k, s1.index, fontsize=7)
    ax.set(ylabel="ΔPN (S/ mm)", title="S1 · ΔPN instantáneo ante shocks de tasas (revalorización completa)")
    ax.legend(fontsize=7, ncol=4)
    show(fig, "sensibilidad_tasas")
    display(s1.round(2))
"""

SENS_S2 = """
if sens:
    sp = pd.DataFrame(sens["shadowPrices"])
    if len(sp):
        sp["Límite"] = [" / ".join(constraint_label(n) for n in name.split("+")) for name in sp["name"]]
        s2 = sp.set_index("Límite")[["bound", "limit", "dualPerPp", "finiteDiffSmallPerPp", "finiteDiffPerPp"]]
        s2 = s2.sort_values("dualPerPp")
        fig, ax = plt.subplots(figsize=(9, 0.35 * len(s2) + 1))
        ax.barh(np.arange(len(s2)), s2["dualPerPp"], color=COLORS["ASSET"])
        ax.set_yticks(np.arange(len(s2)), s2.index, fontsize=7)
        ax.set(xlabel="S/ mm de objetivo por 1 pp de relajación", title="S2 · Precios sombra de los límites activos")
        show(fig, "precios_sombra")
        display(s2.round(4))
"""

SENS_S39 = """
if sens:
    def net(m: dict) -> float:
        return m["expectedNetWorthChange"] - m["transactionCosts"]

    def summary(group: str, label: str, row: dict) -> dict:
        ev_ = row.get("basePortfolio") or row.get("outOfSample")
        ok = row["status"] in opt.OPTIMAL
        return {"Grupo": group, "Variante": label, "Status": row["status"], "E − TC": net(row) if ok else None,
                "CVaR": row["cvarLoss"], "Distancia L1 a x*": row["distanceToBase"],
                "E − TC de x*": net(ev_) if ev_ else None, "CVaR de x*": ev_["cvarLoss"] if ev_ else None}

    base = sens["base"]
    rows = [summary("Base", "Base", {**base, "distanceToBase": 0.0, "basePortfolio": base})]
    rows += [summary("S3 costos", f"TC × {r['multiplier']:g}", r) for r in sens["costs"]]
    rows += [summary("S4 α", f"α = {r['alpha']:g}", r) for r in sens["alphas"]]
    rows += [summary("S5 cola", f"P estrés = {r['stressProbability']:g}", r) for r in sens["stressWeight"]]
    rows += [summary("S5 cola", f"sin {r['dropped']}", r) for r in sens["stressLeaveOneOut"]]
    rows += [summary("S6 semillas", f"semilla {r['seed']}", r) for r in sens["seeds"]]
    rows += [summary("S7 deriva", f"deriva {r['variant']}", r) for r in sens["drift"]]
    rows += [summary("S8 estrés", f"+ {r['scenario']}", r) for r in sens["extraStress"]]
    rows += [summary("S9 cupones", f"cupones {coupon_rule(r['rule'])}", r) for r in sens["floatingCouponRule"]]
    s39 = pd.DataFrame(rows).set_index("Variante")

    fig_rows = s39[~s39["Grupo"].isin(["S3 costos", "S4 α"])].iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(fig_rows) + 1.2))
    k = np.arange(len(fig_rows))
    ax.barh(k + 0.2, fig_rows["CVaR de x*"], 0.4, color=COLORS["neutral"], alpha=0.6, label="x* sin reoptimizar")
    ax.barh(k - 0.2, fig_rows["CVaR"], 0.4, color=COLORS["ASSET"], label="Reoptimizada")
    ax.axvline(base["cvarLoss"], color="black", ls=":", lw=1, label=f"CVaR base ({base['cvarLoss']:.1f})")
    ax.set_yticks(k, fig_rows.index, fontsize=7)
    ax.set(xlabel=f"CVaR {tag} % (S/ mm)", title="S3–S9 · Robustez del CVaR ante cambios de modelo")
    ax.legend(fontsize=7, loc="lower right")
    show(fig, "robustez_cvar")
    display(s39.round(2))
"""

OUTRO = """
## Resultado

`output.json` (ruta en `OUTPUT_PATH`) sigue el contrato v1.0 del Anexo 1.B:

- `status`, `objectiveValue`: estado del solver y valor de $E[\\Delta PN] - \\lambda\\,\\mathrm{CVaR} - TC$.
- `positions`: montos inicial, óptimo y cambio por instrumento (S/ mm).
- `metrics`: $E[\\Delta PN]$, TC, σ, VaR/CVaR, pérdidas por estrés e incumplimientos al horizonte.
- `weights`, `constraintChecks`: composición por moneda, tipo, tasa y vencimiento y holgura de cada límite.
- `riskModel`: escenarios, semilla, deriva y covarianza usados.
- `analysis`: posición inicial, barrido de λ, benchmark media-varianza y variante con vencimientos exigidos al
  horizonte.

Si se activó `RUN_SENSITIVITY`, junto a él queda `sensitivity.json` con S1–S9.
"""


def build() -> nbf.NotebookNode:
    cells = [md(INTRO), code(PARAMS), md("## 1. Entorno"), code(DEPS)]
    cells += [
        md(
            "## 2. Código del modelo\n\nCada celda escribe un módulo del paquete `optimum` en una carpeta temporal "
            "(copia exacta del código fuente del proyecto). Las capas son: (i) contrato JSON, (ii) valorización "
            "por flujos, (iii) riesgo y escenarios, (iv) optimizador y (v) sensibilidades."
        ),
        code(LIB_SETUP.replace("{empty}", repr(EMPTY))),
    ]
    for rel, names, imports, title in EXTRACTS[:1]:
        cells += [md(f"### {title}"), writefile(rel, extract(rel, names, imports))]
    cells += [
        md(f"### {VERBATIM[0][1]}\n\n{module_doc(VERBATIM[0][0])}"),
        writefile(VERBATIM[0][0], (SRC / VERBATIM[0][0]).read_text(encoding="utf-8")),
    ]
    for rel, names, imports, title in EXTRACTS[1:]:
        cells += [md(f"### {title}"), writefile(rel, extract(rel, names, imports))]
    for rel, title in VERBATIM[1:]:
        doc = module_doc(rel)
        cells += [md(f"### {title}\n\n{doc}"), writefile(rel, (SRC / rel).read_text(encoding="utf-8"))]
    cells += [md("### Importación y estilo de gráficos"), code(IMPORTS)]

    cells += [
        md("## 3. Input\n\nSe lee y valida `input.json` contra el contrato v1.0."),
        code(LOAD),
        md("## 4. Datos de entrada\n\n### Balance inicial"),
        code(BALANCE),
        md("### Curvas de tasas"),
        code(CURVES),
        md("### Tipo de cambio y renta variable"),
        code(FX_EQ),
        md(
            "### Perfil de flujos de caja\n\nFlujos de `cashFlows` (los flotantes son la proyección base; en cada "
            "escenario se reproyectan)."
        ),
        code(CASHFLOWS),
        md(
            "### Factores de riesgo\n\nCambios mensuales: Δ absoluta en tasas, log-retorno en FX y equity. "
            "La covarianza es singular porque las forwards se derivan de las spots."
        ),
        code(FACTORS_CELL),
        md("### Límites y escenarios de estrés"),
        code(LIMITS),
        md(
            "## 5. Modelo de riesgo\n\n### Escenarios a un año y revalorización completa\n\n"
            "Bootstrap por bloques de los cambios históricos más los escenarios de estrés; cada instrumento se "
            "revaloriza flujo a flujo en cada escenario (sin duración ni DV01)."
        ),
        code(SCEN),
        md(
            "### Calibración de spreads\n\nEl spread de cada instrumento se calibra para que el valor del modelo "
            "en $t_0$ iguale el valor de mercado."
        ),
        code(SPREADS),
        md("### Shocks y resultado por instrumento"),
        code(SHOCKS),
        md("## 6. Optimización → `output.json`"),
        code(SOLVE),
        md("## 7. Resultados\n\n### Posiciones"),
        code(POSITIONS),
        md("### Métricas: inicial, óptimo y alternativas\n\nPérdida > 0 significa que el patrimonio cae."),
        code(METRICS),
        md("### Distribución de ΔPN y estrés"),
        code(DIST),
        md(
            "### Restricciones en el óptimo\n\nPesos como fracción del total del lado; *activa* = en su cota."
        ),
        code(CHECKS),
        md("### Barrido de aversión al riesgo (λ)"),
        code(SWEEP),
        md(
            "### Incumplimientos al horizonte\n\nSe reportan, no se imponen: el balance se revaloriza en $t_H$."
        ),
        code(HORIZON),
        md(
            "## 8. Pruebas mínimas\n\n"
            "Pruebas reproducibles del modelo, adaptadas de la batería del proyecto (`tests/`, pytest) para que "
            "corran aquí sin instalar nada más. Usan el mismo `input.json` y no modifican `output.json`: cada "
            "variante trabaja sobre una copia del input. Al final, una tabla resume el resultado y la celda falla "
            "si alguna prueba no pasa. Tardan menos de un minuto."
        ),
        code(TESTS_SETUP),
        md(
            "### Caso simple resuelto a mano\n\nBalance de juguete con solución analítica (detalle en los "
            "comentarios de la celda)."
        ),
        code(TEST_TOY),
        md(
            "### Pruebas sobre el input real\n\nCVaR del LP, presupuestos y límites, shock extremo de tasas, "
            "restricciones infactibles, parámetros leídos del input, monotonía en λ y calibración."
        ),
        code(TEST_REAL),
        md("### Resumen"),
        code(TESTS_SUMMARY),
        md("## 9. Sensibilidades (opcional)\n\nSe corren solo si `RUN_SENSITIVITY = True`."),
        code(SENS),
        code(SENS_S1),
        code(SENS_S2),
        code(SENS_S39),
        md(OUTRO),
    ]
    nb = nbf.v4.new_notebook(cells=cells)
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.metadata["language_info"] = {"name": "python"}
    return nb


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    nb = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, args.out)
    print(f"{args.out} ({len(nb.cells)} celdas)")


if __name__ == "__main__":
    main()
