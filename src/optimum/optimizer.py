"""(iv) Formulación y resolución del Caso C: max E[ΔPN] − λ·CVaR_α − TC (docs/formulacion.md §4-§6, §9).

Regla de oro: todo sale del dict de input.json. Ningún límite, λ, α, costo o presupuesto está escrito aquí.

- LP de Rockafellar–Uryasev con cvxpy (HiGHS); benchmark media-varianza como QP (Clarabel).
- r_{k,s} = reval + flows por revalorización completa (risk.scenario_components); se calcula una vez y se reutiliza
  en el barrido de λ (D-19).
- VaR y CVaR se recalculan ex post con átomo fraccional (risk.var_cvar), §5.
- Caja al horizonte = instrumentos CASH + flujos netos del año − TC (D-18). Los incumplimientos al horizonte se
  reportan, no se imponen (§7.5).
- Montos en S/ mm; pesos y tasas en decimales.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np
import pandas as pd

from optimum import risk
from optimum.io.json_contract import SCHEMA_VERSION
from optimum.valuation import horizon_dates

LP_SOLVER = cp.HIGHS
QP_SOLVER = cp.CLARABEL
OK_TOL = 1e-6  # tolerancia relativa para declarar cumplida una restricción
ACTIVE_TOL = 1e-7  # tolerancia relativa para declararla activa (en su cota)
OPTIMAL = {"OPTIMAL", "OPTIMAL_INACCURATE"}
HORIZON_MATURITY_MODES = ("REPORT", "ENFORCE")  # D-20
_STATUS = {
    cp.OPTIMAL: "OPTIMAL",
    cp.OPTIMAL_INACCURATE: "OPTIMAL_INACCURATE",
    cp.INFEASIBLE: "INFEASIBLE",
    cp.INFEASIBLE_INACCURATE: "INFEASIBLE",
    cp.UNBOUNDED: "UNBOUNDED",
    cp.UNBOUNDED_INACCURATE: "UNBOUNDED",
}
# Categorías de TYPE que agrupan varios `instrument_type` (§6); el resto se compara por igualdad.
TYPE_MEMBERS = {"FIXED_INCOME": {"BOND_FIXED", "BOND_FLOAT"}}
_MATURITY = re.compile(r"^(LE|LT|GE|GT)_(\d+)M$")


# ------------------------------------------------------------------------------ datos
@dataclass
class ProblemData:
    """Datos del problema, todos leídos del doc (y de los componentes de escenario ya revalorizados)."""

    ids: list[str]
    side: pd.Series  # ASSET / LIABILITY
    x0: pd.Series  # posición inicial, S/ mm
    reval: pd.DataFrame  # K × S, V^H/V^0 − 1
    flows: pd.DataFrame  # K × S, F/V^0
    probs: np.ndarray
    scenario_ids: list[str]
    scenario_kind: list[str]
    cost: pd.Series  # restructuring_cost por S/ movido (D-08)
    alpha: float
    lam: float
    groups: list[dict]  # restricciones de peso en t0
    horizon_groups: list[dict]  # los mismos grupos con la pertenencia medida desde tH (D-20)
    asset_budget: float
    liability_budget: float
    min_net_worth: float
    max_liabilities_to_assets: float
    min_cash: float
    allow_short: bool
    cash_ids: list[str]
    horizon_maturity: str  # REPORT | ENFORCE (D-20)
    base_currency: str
    instruments: pd.DataFrame = field(repr=False)
    lambda_grid: list[float] = field(default_factory=list)

    @property
    def returns(self) -> pd.DataFrame:
        """r_{k,s} = reval + flows (decimal por S/ invertido)."""
        return self.reval + self.flows

    @property
    def sign(self) -> np.ndarray:
        """+1 activos, −1 pasivos (ΔPN = Σ x r − Σ y r)."""
        return np.where(self.side.loc[self.ids] == "ASSET", 1.0, -1.0)

    def budget(self, side: str) -> float:
        return self.asset_budget if side == "ASSET" else self.liability_budget


def _is_member(inst: pd.Series, dimension: str, category: str, t_ref: pd.Timestamp) -> bool:
    """Pertenencia a un grupo de pesos por atributos del instrumento (§6), nunca por id."""
    if dimension == "CURRENCY":
        return inst["currency"] == category
    if dimension == "TYPE":
        return inst["instrument_type"] in TYPE_MEMBERS.get(category, {category})
    if dimension == "RATE_TYPE":
        floating = isinstance(inst["reference_factor"], str) and bool(inst["reference_factor"])
        if category not in ("FIXED", "FLOAT"):
            raise ValueError(f"Categoría RATE_TYPE desconocida: {category}")
        return floating == (category == "FLOAT")
    if dimension == "MATURITY":
        m = _MATURITY.match(category)
        if not m:
            raise ValueError(f"Categoría MATURITY desconocida: {category} (se espera LE_12M, GT_36M, ...)")
        if inst["maturity"] is None or pd.isna(inst["maturity"]):
            return False
        # Meses calendario desde t_ref (auditoría, menor 1): 2026-12-31 + 36 m = 2029-12-31.
        op, maturity = m.group(1), pd.Timestamp(inst["maturity"])
        limit = t_ref + pd.DateOffset(months=int(m.group(2)))
        return {"LE": maturity <= limit, "LT": maturity < limit, "GE": maturity >= limit, "GT": maturity > limit}[op]
    raise ValueError(f"Dimensión de peso desconocida: {dimension}")


def _build_groups(
    weights: list[dict], inst: pd.DataFrame, t_ref: pd.Timestamp, check_empty: bool
) -> list[dict]:
    groups = []
    for w in weights:
        side, dim, cat = w["side"], w["dimension"], w["category"]
        on_side = inst.index[inst["side"] == side]
        base = {
            "side": side,
            "dimension": dim,
            "category": cat,
            "min": w["min_weight"],
            "max": w["max_weight"],
        }
        if dim == "CONCENTRATION":
            for iid in on_side:
                groups.append({**base, "name": f"{side}:{dim}:{cat}:{iid}", "members": [iid]})
            continue
        members = [iid for iid in on_side if _is_member(inst.loc[iid], dim, cat, t_ref)]
        if check_empty and not members and float(w["min_weight"] or 0.0) > 0:
            raise ValueError(
                f"El grupo de pesos {side}/{dim}/{cat} no tiene instrumentos pero exige "
                f"min_weight = {w['min_weight']}: el problema no tiene sentido con estos datos"
            )
        groups.append({**base, "name": f"{side}:{dim}:{cat}", "members": members})
    return groups


def _validate_parameters(doc: Mapping, inst: pd.DataFrame, weights: list[dict]) -> None:
    """Parámetros inválidos fallan con un mensaje claro (auditoría, menores 2 y 5)."""
    cp_ = doc["caseParameters"]
    errors = []
    bad_cost = [i for i in inst.index if float(doc["transactionCosts"][i]["restructuring_cost"]) < 0]
    if bad_cost:
        errors.append(f"restructuring_cost < 0 en {bad_cost}")
    if not 0 < float(cp_["cvarAlpha"]) < 1:
        errors.append(f"cvarAlpha = {cp_['cvarAlpha']} debe estar en (0, 1)")
    lams = [float(cp_["riskAversionLambda"])] + [float(v) for v in cp_.get("lambdaGrid", [])]
    if min(lams) < 0:
        errors.append("riskAversionLambda y lambdaGrid deben ser ≥ 0")
    mode = cp_.get("horizonMaturityLimits", "REPORT")
    if mode not in HORIZON_MATURITY_MODES:
        errors.append(f"horizonMaturityLimits = {mode!r}; se espera uno de {HORIZON_MATURITY_MODES}")
    for side in ("ASSET", "LIABILITY"):
        cats = [w["category"] for w in weights if w["side"] == side and w["dimension"] == "TYPE"]
        if not cats:
            continue
        for iid in inst.index[inst["side"] == side]:
            n = sum(_is_member(inst.loc[iid], "TYPE", c, pd.Timestamp(doc["valuationDate"])) for c in cats)
            if n != 1:
                errors.append(
                    f"{iid} ({inst.loc[iid, 'instrument_type']}) pertenece a {n} categorías TYPE de {side}; "
                    "debe pertenecer a exactamente una"
                )
    if errors:
        raise ValueError("Parámetros inválidos:\n- " + "\n- ".join(errors))


def prepare(doc: Mapping, components: tuple | None = None) -> ProblemData:
    """Arma ProblemData desde el doc. `components` = (reval, flows, ScenarioSet) evita revalorizar (~0.1 s por
    escenario); si es None se generan con `risk.build_scenarios` y `risk.scenario_components`."""
    if components is None:
        scen = risk.build_scenarios(doc)
        reval, flows = risk.scenario_components(doc, scen.deltas)
    else:
        reval, flows, scen = components
    inst = pd.DataFrame(doc["instruments"]).set_index("id")
    ids = list(inst.index)
    t0, t_h = horizon_dates(doc)
    missing = [i for i in ids if i not in reval.index or i not in flows.index]
    if missing:
        raise ValueError(f"Faltan resultados por escenario para: {missing}")
    costs = doc["transactionCosts"]
    no_cost = [i for i in ids if i not in costs]
    if no_cost:
        raise ValueError(f"transactionCosts no trae restructuring_cost para: {no_cost}")

    cp_ = doc["caseParameters"]
    com = doc["constraints"]["common"]
    weights = doc["constraints"]["weights"]
    _validate_parameters(doc, inst, weights)
    return ProblemData(
        ids=ids,
        side=inst["side"],
        x0=inst["market_value_pen"].astype(float),
        reval=reval.loc[ids, list(scen.ids)],
        flows=flows.loc[ids, list(scen.ids)],
        probs=np.asarray(scen.probs, dtype=float),
        scenario_ids=list(scen.ids),
        scenario_kind=list(scen.kind),
        cost=pd.Series({i: float(costs[i]["restructuring_cost"]) for i in ids}),
        alpha=float(cp_["cvarAlpha"]),
        lam=float(cp_["riskAversionLambda"]),
        groups=_build_groups(weights, inst, t0, check_empty=True),
        horizon_groups=_build_groups(weights, inst, t_h, check_empty=False),
        asset_budget=float(com["assetBudget"]),
        liability_budget=float(com["liabilityBudget"]),
        min_net_worth=float(com["minNetWorth"]),
        max_liabilities_to_assets=float(com["maxLiabilitiesToAssets"]),
        min_cash=float(com["minCash"]),
        allow_short=bool(com.get("allowShort", False)),
        cash_ids=list(inst.index[(inst["side"] == "ASSET") & (inst["instrument_type"] == "CASH")]),
        horizon_maturity=cp_.get("horizonMaturityLimits", "REPORT"),
        base_currency=doc.get("baseCurrency", "PEN"),
        instruments=inst,
        lambda_grid=[float(v) for v in cp_.get("lambdaGrid", [])],
    )


# ------------------------------------------------------------------------ modelo
def _mask(data: ProblemData, members) -> np.ndarray:
    s = set(members)
    return np.array([i in s for i in data.ids], dtype=float)


def _horizon_maturity_groups(data: ProblemData) -> list[dict]:
    return [g for g in data.horizon_groups if g["dimension"] == "MATURITY"]


def _feasible_set(data: ProblemData, z: cp.Variable, horizon_maturity: str) -> list:
    """Presupuestos, pesos, caja mínima, PN0 y P/A0 (§6). Las posiciones ≥ 0 van en el dominio de z.
    Con ENFORCE se imponen además los grupos MATURITY con la pertenencia medida desde tH (D-20)."""
    a = _mask(data, [i for i in data.ids if data.side[i] == "ASSET"])
    assets, liabs = a @ z, (1.0 - a) @ z
    cons = [assets == data.asset_budget, liabs == data.liability_budget]
    enforced = data.groups + (_horizon_maturity_groups(data) if horizon_maturity == "ENFORCE" else [])
    for g in enforced:
        total = _mask(data, g["members"]) @ z
        b = data.budget(g["side"])
        cons += [total >= g["min"] * b, total <= g["max"] * b]
    cons += [
        _mask(data, data.cash_ids) @ z >= data.min_cash,
        assets - liabs >= data.min_net_worth,
        liabs <= data.max_liabilities_to_assets * assets,
    ]
    return cons


def solve_data(
    data: ProblemData,
    lam: float | None = None,
    mode: str = "cvar",
    min_net_return: float | None = None,
    horizon_maturity: str | None = None,
) -> dict:
    """Resuelve el problema. mode="cvar": max E[ΔPN] − λ·CVaR − TC (LP, λ = data.lam si es None).
    mode="variance": min Var(ΔPN) s.a. E[ΔPN] − TC ≥ min_net_return (QP, §9.3).

    Devuelve status, positions (pd.Series S/ mm, None si no es óptimo), objective, cvar_lp (ζ + Σ p u/(1−α),
    solo con λ > 0), transaction_cost y solver. Nunca lanza por infactibilidad.
    """
    lam = data.lam if lam is None else float(lam)
    horizon_maturity = horizon_maturity or data.horizon_maturity
    k, s = len(data.ids), len(data.scenario_ids)
    r = data.returns.to_numpy(dtype=float)  # K × S
    z = cp.Variable(k, nonneg=not data.allow_short)
    up, down = cp.Variable(k, nonneg=True), cp.Variable(k, nonneg=True)
    dpn = r.T @ cp.multiply(data.sign, z)
    expected = data.probs @ dpn
    tc = data.cost.loc[data.ids].to_numpy() @ (up + down)
    cons = _feasible_set(data, z, horizon_maturity) + [z - data.x0.loc[data.ids].to_numpy() == up - down]

    cvar = None
    if mode == "cvar":
        zeta, u = cp.Variable(), cp.Variable(s, nonneg=True)
        cons.append(u >= -dpn - zeta)
        cvar = zeta + data.probs @ u / (1 - data.alpha)
        problem, solver = cp.Problem(cp.Maximize(expected - lam * cvar - tc), cons), LP_SOLVER
    elif mode == "variance":
        if min_net_return is None:
            raise ValueError("mode='variance' requiere min_net_return (E* de la solución CVaR)")
        dev = cp.multiply(np.sqrt(data.probs), dpn - expected)
        cons.append(expected - tc >= min_net_return)
        problem, solver = cp.Problem(cp.Minimize(cp.sum_squares(dev)), cons), QP_SOLVER
    else:
        raise ValueError(f"mode desconocido: {mode}")

    try:
        problem.solve(solver=solver)
        status = _STATUS.get(problem.status, "ERROR")
    except cp.error.SolverError:
        status = "ERROR"
    stats = problem.solver_stats if problem.solver_stats is not None else None
    out = {
        "status": status,
        "mode": mode,
        "lambda": lam,
        "horizon_maturity": horizon_maturity,
        "positions": None,
        "objective": None,
        "cvar_lp": None,
        "transaction_cost": None,
        "solver": {
            "name": solver,
            "status": problem.status,
            "iterations": getattr(stats, "num_iters", None),
            "time": getattr(stats, "solve_time", None),
        },
    }
    if status not in OPTIMAL:
        return out
    pos = pd.Series(z.value, index=data.ids)
    out["positions"] = pos
    out["transaction_cost"] = _transaction_cost(data, pos)
    out["objective"] = float(problem.value)
    if cvar is not None and lam > 0:
        out["cvar_lp"] = float(cvar.value)
    return out


# --------------------------------------------------------------------- evaluación
def _transaction_cost(data: ProblemData, pos: pd.Series) -> float:
    return float(data.cost.loc[data.ids] @ (pos.loc[data.ids] - data.x0.loc[data.ids]).abs())


def _positions(data: ProblemData, positions: pd.Series) -> pd.Series:
    pos = pd.Series(positions, dtype=float).reindex(data.ids)
    if pos.isna().any():
        raise ValueError(f"Faltan posiciones para: {list(pos.index[pos.isna()])}")
    return pos


def _tail_stress_share(data: ProblemData, losses: np.ndarray) -> float:
    """Fracción de la masa de la cola (1 − α) que aportan los escenarios de estrés (átomo fraccional incluido)."""
    order = np.argsort(-losses, kind="stable")
    left, stress = 1 - data.alpha, 0.0
    for i in order:
        take = min(data.probs[i], left)
        if data.scenario_kind[i] == "stress":
            stress += take
        left -= take
        if left <= 1e-15:
            break
    return stress / (1 - data.alpha)


def _breach(mask: np.ndarray, probs: np.ndarray, worst: float) -> dict:
    return {"count": int(mask.sum()), "probability": float(probs[mask].sum()), "worst": float(worst)}


def _horizon_weight_breaches(
    data: ProblemData, z: np.ndarray, value_h: np.ndarray, net_cash_in: np.ndarray
) -> dict:
    """Pesos del Cuadro 4 al horizonte, por escenario (auditoría I-2, D-20).

    Tenencias en tH: V^H de cada instrumento; los flujos netos del año menos el TC (`net_cash_in`) se suman a la
    caja en moneda base (a prorrata si hay varias; a toda la caja si no hay en moneda base). La pertenencia se
    mide desde tH. Causa "estructural": el grupo se incumple aun con los montos de t0 (lo provoca el paso del
    tiempo sobre la decisión); "mercado": solo por la deriva de valores.
    """
    held = value_h.copy()
    target = [i for i in data.cash_ids if data.instruments.loc[i, "currency"] == data.base_currency] or data.cash_ids
    if target:
        idx = [data.ids.index(i) for i in target]
        share = z[idx] / z[idx].sum() if z[idx].sum() > 0 else np.full(len(idx), 1 / len(idx))
        held[idx] += share[:, None] * net_cash_in
    out = {}
    for g in data.horizon_groups:
        on_side = (data.side.loc[data.ids] == g["side"]).to_numpy()
        m = _mask(data, g["members"]).astype(bool)
        total = held[on_side].sum(0)
        w = np.divide(held[m].sum(0), total, out=np.zeros_like(total), where=total != 0)
        excess = np.maximum(g["min"] - w, w - g["max"])
        bad = excess > OK_TOL
        w0 = z[m].sum() / z[on_side].sum() if z[on_side].sum() else 0.0
        structural = w0 < g["min"] - OK_TOL or w0 > g["max"] + OK_TOL
        out[g["name"]] = {
            "count": int(bad.sum()),
            "probability": float(data.probs[bad].sum()),
            "worst": float(w[np.argmax(excess)]),
            "range": [float(w.min()), float(w.max())],
            "min": g["min"],
            "max": g["max"],
            "cause": None if not bad.any() else ("estructural" if structural else "mercado"),
        }
    return out


def evaluate(data: ProblemData, positions: pd.Series) -> dict:
    """Métricas ex post de una cartera (S/ mm): E[ΔPN], VaR/CVaR (átomo fraccional), volatilidad (desviación
    estándar ponderada por p_s), pérdida en cada estrés, peso del estrés en la cola, TC e incumplimientos al
    horizonte (§7.5, D-18, D-20): PN, P/A, caja y todos los grupos del Cuadro 4."""
    pos = _positions(data, positions)
    z = pos.to_numpy()
    reval, flows = data.reval.to_numpy(dtype=float), data.flows.to_numpy(dtype=float)
    dpn = (data.sign * z) @ (reval + flows)
    losses = -dpn
    var, cvar = risk.var_cvar(losses, data.alpha, data.probs)
    expected = float(data.probs @ dpn)
    tc = _transaction_cost(data, pos)
    is_asset = (data.side.loc[data.ids] == "ASSET").to_numpy()
    is_cash = _mask(data, data.cash_ids).astype(bool)
    mean_r = (reval + flows) @ data.probs

    # Balance al horizonte (D-18): los flujos del año y el TC pagado en t0 quedan en caja.
    value_h = z[:, None] * (1 + reval)
    flow_h = z[:, None] * flows
    cash_t = value_h[is_cash].sum(0) + flow_h[is_asset].sum(0) - flow_h[~is_asset].sum(0) - tc
    assets_t = value_h[is_asset & ~is_cash].sum(0) + cash_t
    liabs_t = value_h[~is_asset].sum(0)
    nw_t = assets_t - liabs_t
    ratio_t = liabs_t / assets_t
    breaches = {
        "minNetWorth": _breach(nw_t < data.min_net_worth - OK_TOL, data.probs, nw_t.min()),
        "maxLiabilitiesToAssets": _breach(
            ratio_t > data.max_liabilities_to_assets + OK_TOL, data.probs, ratio_t.max()
        ),
        "minCash": _breach(cash_t < data.min_cash - OK_TOL, data.probs, cash_t.min()),
    }
    breaches |= _horizon_weight_breaches(data, z, value_h, cash_t - value_h[is_cash].sum(0))

    a_total, l_total = z[is_asset].sum(), z[~is_asset].sum()
    return {
        "expected_pnl": expected,
        "var": var,
        "cvar": cvar,
        "volatility": float(np.sqrt(data.probs @ (dpn - expected) ** 2)),
        "stress_losses": {
            sid: float(losses[i])
            for i, sid in enumerate(data.scenario_ids)
            if data.scenario_kind[i] == "stress"
        },
        "tail_stress_share": _tail_stress_share(data, losses),
        "transaction_cost": tc,
        "initial_net_worth": float(a_total - l_total),
        "expected_terminal_net_worth": float(a_total - l_total - tc + expected),
        "expected_asset_return": float(z[is_asset] @ mean_r[is_asset] / a_total) if a_total else None,
        "expected_liability_cost": float(z[~is_asset] @ mean_r[~is_asset] / l_total) if l_total else None,
        "horizon_breaches": breaches,
    }


def _check(
    name: str, value: float, lo: float | None, hi: float | None, binding: bool = True, note: str = ""
) -> dict:
    def near(b, tol):
        return b is not None and abs(value - b) <= tol * max(1.0, abs(b))

    ok = (lo is None or value >= lo - OK_TOL * max(1.0, abs(lo))) and (
        hi is None or value <= hi + OK_TOL * max(1.0, abs(hi))
    )
    active = binding and (near(lo, ACTIVE_TOL) or near(hi, ACTIVE_TOL))
    return {
        "name": name,
        "value": float(value),
        "min": lo,
        "max": hi,
        "active": bool(active),
        "ok": bool(ok),
        "note": note,
    }


def check_constraints(data: ProblemData, positions: pd.Series) -> list[dict]:
    """[{name, value, min, max, active, ok, note}] de cada restricción de §6. Pesos como fracción del total del lado;
    montos en S/ mm. Los grupos vacíos se marcan como no vinculantes."""
    pos = _positions(data, positions)
    is_asset = data.side.loc[data.ids] == "ASSET"
    assets, liabs = float(pos[is_asset].sum()), float(pos[~is_asset].sum())
    checks = [
        _check("assetBudget", assets, data.asset_budget, data.asset_budget),
        _check("liabilityBudget", liabs, data.liability_budget, data.liability_budget),
    ]
    for g in data.groups:
        total = assets if g["side"] == "ASSET" else liabs
        w = float(pos.loc[g["members"]].sum() / total) if total else 0.0
        empty = not g["members"]
        checks.append(
            _check(g["name"], w, g["min"], g["max"], binding=not empty, note="grupo vacío" if empty else "")
        )
    if data.horizon_maturity == "ENFORCE":
        for g in _horizon_maturity_groups(data):
            total = assets if g["side"] == "ASSET" else liabs
            w = float(pos.loc[g["members"]].sum() / total) if total else 0.0
            checks.append(_check(f"{g['name']}@tH", w, g["min"], g["max"], binding=bool(g["members"])))
    checks += [
        _check("minCash", float(pos.loc[data.cash_ids].sum()), data.min_cash, None),
        _check("minNetWorth", assets - liabs, data.min_net_worth, None),
        _check(
            "maxLiabilitiesToAssets",
            liabs / assets if assets else np.inf,
            None,
            data.max_liabilities_to_assets,
        ),
    ]
    if not data.allow_short:
        checks.append(_check("nonNegativity", float(pos.min()), 0.0, None))
    return checks


# ------------------------------------------------------------------------ output
def _metrics_block(ev: dict, alpha: float) -> dict:
    tag = f"{alpha * 100:g}"
    return {
        "expectedAssetReturn": ev["expected_asset_return"],
        "expectedLiabilityEconomicCost": ev["expected_liability_cost"],
        "expectedNetWorthChange": ev["expected_pnl"],
        "expectedTerminalNetWorth": ev["expected_terminal_net_worth"],
        "netWorthVolatility": ev["volatility"],
        f"var{tag}Loss": ev["var"],
        f"cvar{tag}Loss": ev["cvar"],
        "cvarAlpha": alpha,
        "transactionCosts": ev["transaction_cost"],
        "stressLosses": ev["stress_losses"],
        "tailStressShare": ev["tail_stress_share"],
        "horizonBreaches": ev["horizon_breaches"],
    }


def _summary(data: ProblemData, res: dict, lam: float) -> dict:
    """Resumen de una solución para el bloque `analysis`."""
    if res["status"] not in OPTIMAL:
        return {"lambda": lam, "status": res["status"]}
    ev = evaluate(data, res["positions"])
    return {
        "lambda": lam,
        "status": res["status"],
        "objective": ev["expected_pnl"] - lam * ev["cvar"] - ev["transaction_cost"],
        "metrics": _metrics_block(ev, data.alpha),
        "weights": _weights(data, res["positions"]),
        "positions": {k: float(v) for k, v in res["positions"].items()},
    }


def _weights(data: ProblemData, pos: pd.Series) -> dict:
    """Pesos por lado y dimensión (fracción del total del lado)."""
    inst = data.instruments.loc[data.ids]
    rate_type = np.where(
        inst["reference_factor"].map(lambda v: isinstance(v, str) and bool(v)), "FLOAT", "FIXED"
    )
    out = {}
    for label, key in (
        ("byCurrency", inst["currency"]),
        ("byType", inst["instrument_type"]),
        ("byRateType", rate_type),
    ):
        out[label] = {}
        for side in ("ASSET", "LIABILITY"):
            m = (inst["side"] == side).to_numpy()
            total = float(pos[m].sum())
            grouped = pd.Series(pos[m].to_numpy(), index=np.asarray(key)[m]).groupby(level=0).sum()
            out[label][side] = {k: float(v / total) for k, v in grouped.items()} if total else {}
    return out


def _position_rows(data: ProblemData, pos: pd.Series | None, side: str) -> list[dict]:
    inst = data.instruments
    rows = []
    for iid in [i for i in data.ids if data.side[i] == side]:
        x = None if pos is None else float(pos[iid])
        rows.append(
            {
                "id": iid,
                "name": inst.loc[iid, "name"],
                "type": inst.loc[iid, "instrument_type"],
                "currency": inst.loc[iid, "currency"],
                "initial": float(data.x0[iid]),
                "optimal": x,
                "change": None if x is None else x - float(data.x0[iid]),
                "weight": None if x is None else x / data.budget(side),
            }
        )
    return rows


def _risk_model(doc: Mapping, data: ProblemData) -> dict:
    hist = risk.history_from_doc(doc)
    r = data.returns.to_numpy(dtype=float)
    mean = r @ data.probs
    cov = ((r - mean[:, None]) * data.probs) @ (r - mean[:, None]).T
    min_eig = float(np.linalg.eigvalsh(cov).min())
    cp_ = doc["caseParameters"]
    return {
        "historyStart": hist.index.min(),
        "historyEnd": hist.index.max(),
        "observations": len(hist),
        "covarianceMethod": "Sin covarianza paramétrica: escenarios (bootstrap por bloques + estrés) con "
        "revalorización completa; covarianza de r_{k,s} ponderada por p_s solo como control",
        "psdCheck": {"ok": min_eig >= -1e-12, "minEigenvalue": min_eig},
        "riskMeasure": cp_.get("riskMeasure"),
        "cvarAlpha": data.alpha,
        "scenarios": len(data.scenario_ids),
        "bootstrapScenarios": data.scenario_kind.count("bootstrap"),
        "stressScenarios": data.scenario_kind.count("stress"),
        "stressProbability": float(data.probs[np.array(data.scenario_kind) == "stress"].sum()),
        "seed": cp_.get("seed"),
    }


def _horizon_variant(data: ProblemData, base: dict) -> dict:
    """La misma λ con el modo de vencimientos opuesto al del input (D-20). `objectiveCost` = objetivo base −
    objetivo de la variante: con base REPORT es el costo de cumplir los vencimientos medidos desde tH."""
    mode = "ENFORCE" if data.horizon_maturity == "REPORT" else "REPORT"
    alt = solve_data(data, horizon_maturity=mode)
    summary = {"mode": mode, **_summary(data, alt, data.lam)}
    if alt["status"] in OPTIMAL:
        summary["objectiveCost"] = base["objective"] - summary["objective"]
    return summary


def solve(doc: Mapping, components: tuple | None = None) -> dict:
    """Output v1.0 (Anexo 1.B) de la solución con λ = riskAversionLambda, más `analysis` (D-19): posición inicial,
    barrido de `lambdaGrid` y benchmark media-varianza con el mismo retorno neto. Si no es óptimo, devuelve el
    status sin posiciones ni métricas (no lanza). Incluye la variante de vencimientos al horizonte (D-20)."""
    data = prepare(doc, components)
    res = solve_data(data)
    t0, t_h = horizon_dates(doc)
    is_asset = data.side.loc[data.ids] == "ASSET"
    out = {
        "schemaVersion": SCHEMA_VERSION,
        "caseId": doc["caseId"],
        "status": res["status"],
        "objectiveValue": res["objective"],
        "valuation": {
            "valuationDate": t0,
            "horizonDate": t_h,
            "initialAssets": float(data.x0[is_asset].sum()),
            "initialLiabilities": float(data.x0[~is_asset].sum()),
            "initialNetWorth": float(data.x0[is_asset].sum() - data.x0[~is_asset].sum()),
        },
        "metrics": {},
        "riskModel": _risk_model(doc, data),
        "positions": {
            "assets": _position_rows(data, res["positions"], "ASSET"),
            "liabilities": _position_rows(data, res["positions"], "LIABILITY"),
        },
        "weights": {},
        "constraintChecks": [],
        "solver": res["solver"],
        "riskAversionLambda": data.lam,
        "horizonMaturityLimits": data.horizon_maturity,
        "analysis": {},
    }
    if res["status"] not in OPTIMAL:
        return out

    pos = res["positions"]
    ev = evaluate(data, pos)
    out["metrics"] = _metrics_block(ev, data.alpha) | {"cvarLp": res["cvar_lp"]}
    out["weights"] = _weights(data, pos)
    out["constraintChecks"] = check_constraints(data, pos)

    ev0 = evaluate(data, data.x0)
    e_star = ev["expected_pnl"] - ev["transaction_cost"]
    mv = solve_data(data, mode="variance", min_net_return=e_star)
    out["analysis"] = {
        "initialPosition": {
            "objective": ev0["expected_pnl"] - data.lam * ev0["cvar"],
            "metrics": _metrics_block(ev0, data.alpha),
            "weights": _weights(data, data.x0),
            "violatedConstraints": [c["name"] for c in check_constraints(data, data.x0) if not c["ok"]],
        },
        "lambdaSweep": [_summary(data, solve_data(data, lam=lam), lam) for lam in data.lambda_grid],
        "meanVarianceBenchmark": {"minNetReturn": e_star, **_summary(data, mv, data.lam)},
        "horizonMaturityVariant": _horizon_variant(data, res),
    }
    return out


def out_of_sample(doc: Mapping, positions: pd.Series, seed: int) -> dict:
    """Evalúa una cartera con escenarios generados con otra semilla (§9.4): mide el sobreajuste del CVaR."""
    scen = risk.build_scenarios(doc, seed=seed)
    reval, flows = risk.scenario_components(doc, scen.deltas)
    return evaluate(prepare(doc, components=(reval, flows, scen)), positions)
