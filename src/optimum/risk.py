"""(iii) Factores, escenarios y medidas de riesgo — independiente del optimizador.

Convenciones (docs/formulacion.md §5, §7.1-7.4; decisiones D-06, D-09, D-11, D-14, D-15, D-16):
- 24 factores en el orden de `FACTORS`. Cambios mensuales: Δ absoluta en tasas, log-retorno en FX y equity.
- Bootstrap por bloques móviles: cada escenario suma `n_blocks` ventanas centradas de `block_length` meses
  consecutivos con inicio uniforme. Se añade la deriva anual μ escalada por (b·m)/12 (D-06, D-15).
- Estrés: shift paralelo por moneda; el override (un shift, D-16) reemplaza al paralelo en los nodos del tramo; en
  los de transición se interpola t·s(t) entre los nodos fijos vecinos, para que la forward cambie parejo (D-11 v2).
  Sin deriva.
- Forwards: sus Δ se ignoran al revalorizar; se recalculan desde la spot shockeada (D-10).
- r_{k,s} = (V_k(tH) + CF_k(t0, tH]) / V_k(t0) − 1, por revalorización completa (valuation.py).
- Pérdida = −ΔPN. VaR y CVaR con átomo fraccional y probabilidades por escenario.
- Todo parámetro sale del documento de input.json; nada se codifica por instrumento.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from optimum.cleaning import FACTORS, LOG_FACTORS, RATE_FACTORS, SPOT_FACTORS, compute_factor_changes
from optimum.curves import year_fraction
from optimum.valuation import (
    base_state,
    calibrate_spreads,
    check_positive_values,
    horizon_dates,
    horizon_value_and_flows,
)

MONTHS_PER_YEAR = 12  # los cambios históricos son mensuales
PROB_TOL = 1e-9


# ------------------------------------------------------------------ historia y cambios
def history_from_doc(doc: Mapping) -> pd.DataFrame:
    """Niveles de los 24 factores (fechas × FACTORS) desde `marketHistory`, hasta `valuationDate` inclusive (sin
    información futura). Tasas en decimales."""
    rows = {}
    for r in doc["marketHistory"]:
        row = {}
        for ccy, nodes in r["spot"].items():
            row.update({f"{ccy}_SPOT_{n}": v for n, v in nodes.items()})
        for ccy, segs in r["forwardSwap"].items():
            row.update({f"{ccy}_FWD_{s}": v for s, v in segs.items()})
        row["FX_PENUSD"] = r["fx"]["PENUSD"]
        row["EQUITY_USD"] = r["equityIndex"]
        rows[pd.Timestamp(r["date"])] = row
    hist = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    missing = set(FACTORS) - set(hist.columns)
    if missing:
        raise ValueError(f"marketHistory no trae los factores {sorted(missing)}")
    hist.index.name = "date"
    return hist.loc[: horizon_dates(doc)[0], FACTORS].astype(float)


def factor_changes(doc: Mapping) -> pd.DataFrame:
    """Cambios mensuales (Δ absoluta en tasas, log-retorno en FX y equity) desde `marketHistory`."""
    return compute_factor_changes(history_from_doc(doc))


# ------------------------------------------------------------------------- deriva
def drift(doc: Mapping, changes: pd.DataFrame) -> pd.Series:
    """Deriva anual μ por factor (decimales; log-retorno en FX y equity), según `caseParameters.drift` (D-06).

    - rates: ZERO → 0 | HISTORICAL → 12 × media mensual.
    - fx: ZERO | HISTORICAL | IRP → ln((1 + z_PEN(τ)) / (1 + z_USD(τ))), τ = plazo del horizonte, curvas de t0
      (FX = PEN por USD; tasa anual, de modo que μ·τ es la forward de paridad al horizonte).
    - equity: ZERO | HISTORICAL.
    """
    cfg = doc["caseParameters"]["drift"]
    historical = MONTHS_PER_YEAR * changes.mean()
    mu = pd.Series(0.0, index=FACTORS)

    def pick(kind: str, cls: str, factors: list[str], allowed: set[str]) -> None:
        if kind not in allowed:
            raise ValueError(f"Deriva '{kind}' no soportada para {cls} (opciones: {sorted(allowed)})")
        if kind == "HISTORICAL":
            mu[factors] = historical[factors]

    pick(cfg["rates"], "rates", RATE_FACTORS, {"ZERO", "HISTORICAL"})
    pick(cfg["fx"], "fx", ["FX_PENUSD"], {"ZERO", "HISTORICAL", "IRP"})
    pick(cfg["equity"], "equity", ["EQUITY_USD"], {"ZERO", "HISTORICAL"})
    if cfg["fx"] == "IRP":
        curves = base_state(doc).curves
        tau = float(year_fraction(*horizon_dates(doc)))
        mu["FX_PENUSD"] = math.log(
            (1 + float(curves["PEN"].zero(tau))) / (1 + float(curves["USD"].zero(tau)))
        )
    return mu


# ---------------------------------------------------------------------- bootstrap
def bootstrap_shocks(
    changes: pd.DataFrame, n: int, block_length: int, n_blocks: int, seed: int | None = None
) -> np.ndarray:
    """Shocks (n × factores) = suma de `n_blocks` ventanas de `block_length` cambios consecutivos, centradas.

    Cada inicio se sortea uniforme entre las T − b + 1 ventanas. Se centran las sumas de las ventanas (no los meses):
    sin vuelta circular, los meses de los extremos entran en menos ventanas, y centrar los meses deja un sesgo de
    media (D-09 v3). Así la media esperada del shock es exactamente 0. No incluye deriva.
    """
    x = changes.to_numpy(dtype=float)
    t = len(x)
    if not 1 <= block_length <= t:
        raise ValueError(f"block_length = {block_length} fuera de [1, {t}] (meses de historia)")
    if n < 1 or n_blocks < 1:
        raise ValueError("n y n_blocks deben ser ≥ 1")
    csum = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(x, axis=0)])
    windows = csum[block_length:] - csum[:-block_length]  # (T − b + 1) × factores
    windows = windows - windows.mean(axis=0)
    starts = np.random.default_rng(seed).integers(0, len(windows), size=(n, n_blocks))
    return windows[starts].sum(axis=1)


# ------------------------------------------------------------------------- estrés
def _isnull(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


_OVERRIDE_KEY = re.compile(r"^([a-z]+)_(\w+)_override$")


def _check_tenors(tenors: Mapping, node_years: Mapping[str, float]) -> None:
    """Los nodos de cada tramo y de su transición existen, no se repiten entre tramos y la transición no incluye t = 0."""
    seen: dict[str, str] = {}
    for bucket, spec in tenors.items():
        for node in list(spec.get("nodes", [])) + list(spec.get("transition", [])):
            if node not in node_years:
                raise ValueError(f"stressTenors.{bucket} usa el nodo inexistente {node}")
            if node in seen:
                raise ValueError(
                    f"El nodo {node} está en dos tramos de stressTenors ({seen[node]} y {bucket})"
                )
            seen[node] = bucket
        if any(node_years[n] <= 0 for n in spec.get("transition", [])):
            raise ValueError(f"stressTenors.{bucket}: un nodo de transición no puede estar en t = 0")


def _stress_curve_shift(
    parallel: float, overrides: Mapping[str, float], tenors: Mapping, node_years: Mapping[str, float]
) -> dict[str, float]:
    """Shift por nodo spot de una moneda (D-11 v2, D-16).

    Nodos fijos: el override en los nodos de un tramo con override y el paralelo en el resto, salvo las transiciones
    de tramos con override. En cada transición se interpola linealmente t·s(t) entre los nodos fijos vecinos: la
    forward implícita cambia lo mismo en todos los segmentos de la transición.
    """
    shift, pending = {}, []
    for node in node_years:
        bucket = next((b for b, spec in tenors.items() if node in spec.get("nodes", [])), None)
        trans = next((b for b, spec in tenors.items() if node in spec.get("transition", [])), None)
        if bucket in overrides:
            shift[node] = overrides[bucket]
        elif trans in overrides:
            pending.append(node)
        else:
            shift[node] = parallel
    for node in pending:
        t = node_years[node]
        left = max((n for n in shift if node_years[n] < t), key=node_years.get, default=None)
        right = min((n for n in shift if node_years[n] > t), key=node_years.get, default=None)
        if left is None or right is None:
            raise ValueError(f"El nodo de transición {node} necesita nodos fijos a ambos lados")
        tl, tr = node_years[left], node_years[right]
        acc = tl * shift[left] + (tr * shift[right] - tl * shift[left]) * (t - tl) / (tr - tl)
        shift[node] = acc / t
    return shift


def stress_shocks(doc: Mapping) -> pd.DataFrame:
    """Δ por escenario de estrés (escenarios × FACTORS), según D-11 v2 y D-16. Forwards en 0 (se recalculan).

    Exige `<ccy>_parallel` por moneda y rechaza `<ccy>_<tramo>_override` de tramos no definidos en `stressTenors`.
    """
    tenors = doc["caseParameters"]["stressTenors"]
    node_years = {n["id"]: float(n["years"]) for n in doc["curveNodes"]}
    _check_tenors(tenors, node_years)
    currencies = list(doc["marketHistory"][-1]["spot"])
    out = {}
    for s in doc["stressScenarios"]:
        sid = s["scenario_id"]
        for key in s:
            m = _OVERRIDE_KEY.match(key)
            if m and m.group(2) not in tenors:
                raise ValueError(
                    f"{sid}: {key} no corresponde a ningún tramo de stressTenors ({sorted(tenors)})"
                )
        d = dict.fromkeys(FACTORS, 0.0)
        for ccy in currencies:
            c = ccy.lower()
            if _isnull(s.get(f"{c}_parallel")):
                raise ValueError(f"{sid}: falta {c}_parallel")
            overrides = {
                b: float(s[f"{c}_{b}_override"]) for b in tenors if not _isnull(s.get(f"{c}_{b}_override"))
            }
            shift = _stress_curve_shift(float(s[f"{c}_parallel"]), overrides, tenors, node_years)
            d.update({f"{ccy}_SPOT_{n}": v for n, v in shift.items()})
        fx, eq = s.get("fx_pct"), s.get("equity_pct")
        d["FX_PENUSD"] = 0.0 if _isnull(fx) else math.log(1 + float(fx))
        d["EQUITY_USD"] = 0.0 if _isnull(eq) else math.log(1 + float(eq))
        out[sid] = d
    return pd.DataFrame.from_dict(out, orient="index")[FACTORS]


# ------------------------------------------------------------ conjunto de escenarios
@dataclass(frozen=True)
class ScenarioSet:
    """Escenarios a horizonte: ids, Δ de factores (S × FACTORS), probabilidades p_s y tipo (bootstrap/stress)."""

    ids: list[str]
    deltas: pd.DataFrame
    probs: np.ndarray
    kind: list[str]


def _horizon_months(doc: Mapping) -> int:
    t0, t_h = horizon_dates(doc)
    return (t_h.year - t0.year) * 12 + (t_h.month - t0.month)


def build_scenarios(doc: Mapping, seed: int | None = None) -> ScenarioSet:
    """Bootstrap (centrado + μ) y estrés, con p_s = bootstrapProbability / N_B y `probability` de cada estrés.

    `seed` reemplaza a `caseParameters.seed` (p. ej. para la prueba fuera de muestra).
    """
    cp = doc["caseParameters"]
    b, m = int(cp["bootstrapBlockLength"]), int(cp["bootstrapBlocksPerScenario"])
    months = _horizon_months(doc)
    if b * m != months:
        raise ValueError(
            f"bootstrapBlockLength × bootstrapBlocksPerScenario = {b * m} ≠ {months} meses de horizonte"
        )
    n_b = int(cp["bootstrapCount"])

    changes = factor_changes(doc)
    mu = drift(doc, changes).to_numpy()
    boot = bootstrap_shocks(changes, n_b, b, m, cp["seed"] if seed is None else seed)
    boot = boot + mu * (b * m / MONTHS_PER_YEAR)
    stress = stress_shocks(doc)

    p_stress = np.array([float(s["probability"]) for s in doc["stressScenarios"]])
    if abs(p_stress.sum() - float(cp["stressProbability"])) > PROB_TOL:
        raise ValueError(
            f"Σ p de estrés = {p_stress.sum():.6f} ≠ stressProbability = {cp['stressProbability']}"
        )
    p_boot = np.full(n_b, float(cp["bootstrapProbability"]) / n_b)
    probs = np.concatenate([p_boot, p_stress])
    if abs(probs.sum() - 1.0) > PROB_TOL:
        raise ValueError(f"Las probabilidades de los escenarios suman {probs.sum():.6f}, no 1")

    width = len(str(n_b))
    ids = [f"B{i + 1:0{width}d}" for i in range(n_b)] + list(stress.index)
    deltas = pd.DataFrame(np.vstack([boot, stress.to_numpy()]), index=ids, columns=FACTORS)
    return ScenarioSet(ids, deltas, probs, ["bootstrap"] * n_b + ["stress"] * len(stress))


# ---------------------------------------------------------------- resultados r_{k,s}
def scenario_returns(
    doc: Mapping, deltas: pd.DataFrame, spreads: Mapping[str, float] | None = None
) -> pd.DataFrame:
    """r_{k,s} (instrumentos × escenarios, decimal por S/ invertido) por revalorización completa al horizonte."""
    check_positive_values(doc)
    spreads = calibrate_spreads(doc) if spreads is None else spreads
    v0 = pd.Series({i["id"]: float(i["market_value_pen"]) for i in doc["instruments"]})
    cols = {}
    for sid, row in deltas.iterrows():
        h = horizon_value_and_flows(doc, spreads, row.to_dict())
        cols[sid] = (h["value_h"] + h["flows"]) / v0.reindex(h.index) - 1
    return pd.DataFrame(cols)


def pn_change(returns: pd.DataFrame, positions: pd.Series, sides: pd.Series) -> np.ndarray:
    """ΔPN_s = Σ_i x_i r_{i,s} − Σ_j y_j r_{j,s} (S/ mm), con `sides` ∈ {ASSET, LIABILITY}."""
    bad = set(sides.reindex(positions.index)) - {"ASSET", "LIABILITY"}
    if bad:
        raise ValueError(f"Lados desconocidos: {bad}")
    sign = np.where(sides.reindex(positions.index) == "ASSET", 1.0, -1.0)
    return (sign * positions.to_numpy(dtype=float)) @ returns.loc[positions.index].to_numpy(dtype=float)


# ------------------------------------------------------------------------ VaR / CVaR
def var_cvar(losses: np.ndarray, alpha: float, probs: np.ndarray | None = None) -> tuple[float, float]:
    """VaR_α = min{ℓ : P(L ≤ ℓ) ≥ α} y CVaR_α = [Σ_{L>VaR} p L + VaR (1 − α − Σ_{L>VaR} p)] / (1 − α).

    Pérdidas en S/ mm (pérdida > 0). Probabilidades uniformes si `probs` es None.
    """
    if not 0 < alpha < 1:
        raise ValueError(f"alpha = {alpha} debe estar en (0, 1)")
    losses = np.asarray(losses, dtype=float)
    probs = np.full(len(losses), 1 / len(losses)) if probs is None else np.asarray(probs, dtype=float)
    if probs.shape != losses.shape or (probs < 0).any() or abs(probs.sum() - 1) > PROB_TOL:
        raise ValueError("probs debe tener la forma de losses, ser ≥ 0 y sumar 1")
    order = np.argsort(losses, kind="stable")
    l_sorted, cum = losses[order], np.cumsum(probs[order])
    var = float(l_sorted[np.searchsorted(cum, alpha - 1e-12)])
    tail = losses > var
    p_tail = probs[tail].sum()
    cvar = (probs[tail] @ losses[tail] + var * (1 - alpha - p_tail)) / (1 - alpha)
    return var, float(cvar)


# ------------------------------------------------------------------------- controles
def scenario_diagnostics(doc: Mapping, scenarios: ScenarioSet) -> dict[str, pd.Series | pd.DataFrame]:
    """Controles de los escenarios.

    - sigma: σ del shock bootstrap vs. σ histórica de la suma móvil de b·m meses (sin centrar), por factor.
    - min_rate: tasa spot mínima (nodos) de cada escenario al horizonte, sin piso (§7.3).
    """
    cp = doc["caseParameters"]
    window = int(cp["bootstrapBlockLength"]) * int(cp["bootstrapBlocksPerScenario"])
    changes = factor_changes(doc)
    boot = scenarios.deltas[np.asarray(scenarios.kind) == "bootstrap"]
    sigma = pd.DataFrame(
        {"bootstrap_12m": boot.std(ddof=1), "historical_12m": changes.rolling(window).sum().std(ddof=1)}
    )
    t0_row = history_from_doc(doc).loc[horizon_dates(doc)[0], SPOT_FACTORS]
    min_rate = (scenarios.deltas[SPOT_FACTORS] + t0_row).min(axis=1)
    return {"sigma": sigma, "min_rate": min_rate}


# ------------------------------------------------------------ chequeo local (D-14)
def sensitivities(
    value_fn: Callable[[Mapping[str, float]], pd.Series],
    factors: Sequence[str],
    bump_rate: float = 1e-4,
    bump_log: float = 0.01,
) -> pd.DataFrame:
    """Matriz M (instrumentos × factores) por diferencias finitas centrales: ∂V/∂F en S/ mm por unidad del factor
    (1.0 = 100 % en tasas; 1.0 de log-retorno en FX/equity). Bump de 1 pb en tasas y 1 % en log-factores.

    Solo para el chequeo de coherencia local vs. revalorización completa (D-14), no para el modelo.
    """
    cols = {}
    for f in factors:
        h = bump_log if f in LOG_FACTORS else bump_rate
        cols[f] = (value_fn({f: h}) - value_fn({f: -h})) / (2 * h)
    return pd.DataFrame(cols)


def covariance(changes: pd.DataFrame, annualize: int = MONTHS_PER_YEAR) -> pd.DataFrame:
    """Covarianza muestral de cambios mensuales, anualizada (×12, i.i.d.) por defecto."""
    return changes.cov() * annualize


def nearest_psd(m: np.ndarray, eps: float = 0.0) -> np.ndarray:
    """Proyección a semidefinida positiva por recorte de autovalores."""
    m = (m + m.T) / 2
    w, v = np.linalg.eigh(m)
    return (v * np.clip(w, eps, None)) @ v.T
