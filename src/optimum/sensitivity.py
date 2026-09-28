"""(v) Sensibilidades del Caso C (docs/formulacion.md §11; decisiones D-21, D-22).

Cada variante es una copia del documento de input.json resuelta con el mismo optimizador. Las grillas salen de
`caseParameters.sensitivities`; nada se codifica aquí. Montos en S/ mm, pesos y tasas en decimales.

- S1 `rate_shock_pnl`: shock instantáneo de tasas en t0 sobre carteras fijas (revalorización completa, spreads fijos).
- S2 `shadow_prices`: duales del LP de cada cota de peso activa, contrastados con una diferencia finita.
- S3-S9 `run_all`: costos, α, peso de la cola de estrés, semillas, deriva, estrés extra y regla de cupones.
  La matriz r_{k,s} se reutiliza siempre que la variante no cambie los escenarios ni la valorización.
"""

from __future__ import annotations

import copy
import dataclasses
import time
from collections.abc import Mapping

import numpy as np
import pandas as pd

from optimum import optimizer as opt
from optimum import risk
from optimum.valuation import calibrate_spreads, coupon_rule, value_at_t0

PP = 100.0  # puntos porcentuales por unidad de peso
EXCLUDED_LIMITS = {"assetBudget", "liabilityBudget", "nonNegativity"}  # no son límites que se puedan relajar


# ------------------------------------------------------------------ copias del documento
def with_overrides(doc: Mapping, overrides: Mapping[str, object]) -> dict:
    """Copia profunda de `doc` con `{"a.b.c": valor}` reemplazados. KeyError si la ruta no existe (evita que un
    error de tipeo cree una clave nueva que nadie lee)."""
    new = copy.deepcopy(dict(doc))
    for path, value in overrides.items():
        *parents, last = path.split(".")
        node = new
        for key in parents:
            node = node[key]
        if last not in node:
            raise KeyError(f"La ruta {path} no existe en el documento")
        node[last] = copy.deepcopy(value)
    return new


def scale_costs(doc: Mapping, multiplier: float) -> dict:
    """Copia con los costos de transacción × `multiplier` (S3)."""
    if multiplier < 0:
        raise ValueError(f"El multiplicador de costos debe ser ≥ 0: {multiplier}")
    new = copy.deepcopy(dict(doc))
    for c in new["transactionCosts"].values():
        for key in ("restructuring_cost", "reduction_prepayment_cost"):
            if c.get(key) is not None:
                c[key] = float(c[key]) * multiplier
    return new


def add_stress(doc: Mapping, scenario: Mapping) -> dict:
    """Copia con un escenario de estrés más (S8): su probabilidad se suma a `stressProbability` y se resta de
    `bootstrapProbability`, para que Σ p_s = 1."""
    new = copy.deepcopy(dict(doc))
    sid = scenario["scenario_id"]
    if any(s["scenario_id"] == sid for s in new["stressScenarios"]):
        raise ValueError(f"Ya existe un estrés con id {sid}")
    p = float(scenario["probability"])
    cp_ = new["caseParameters"]
    if not 0 < p < float(cp_["bootstrapProbability"]):
        raise ValueError(f"Probabilidad del estrés {sid} fuera de rango: {p}")
    new["stressScenarios"].append(dict(scenario))
    cp_["stressProbability"] = float(cp_["stressProbability"]) + p
    cp_["bootstrapProbability"] = float(cp_["bootstrapProbability"]) - p
    return new


def reweight_stress(
    scen: risk.ScenarioSet, stress_probability: float | None = None, drop: str | None = None
) -> risk.ScenarioSet:
    """Nuevas probabilidades del conjunto de escenarios (S5), sin tocar los Δ.

    `drop` elimina un estrés. La probabilidad conjunta P (`stress_probability`, o la original) se reparte entre los
    estrés restantes en proporción a su p original; cada bootstrap recibe (1 − P)/N_B.
    """
    kind = np.asarray(scen.kind)
    keep = np.ones(len(scen.ids), dtype=bool)
    if drop is not None:
        if drop not in scen.ids or kind[scen.ids.index(drop)] != "stress":
            raise ValueError(f"{drop} no es un escenario de estrés del conjunto")
        keep[scen.ids.index(drop)] = False
    is_stress = (kind == "stress") & keep
    if not is_stress.any():
        raise ValueError("El conjunto quedaría sin escenarios de estrés")
    p = np.asarray(scen.probs, dtype=float)
    total = float(p[kind == "stress"].sum()) if stress_probability is None else float(stress_probability)
    if not 0 < total < 1:
        raise ValueError(f"La probabilidad conjunta del estrés debe estar en (0, 1): {total}")
    is_boot = (kind == "bootstrap") & keep
    new_p = np.zeros(len(p))
    new_p[is_stress] = total * p[is_stress] / p[is_stress].sum()
    new_p[is_boot] = (1 - total) / is_boot.sum()
    ids = [i for i, k in zip(scen.ids, keep, strict=True) if k]
    return risk.ScenarioSet(
        ids=ids,
        deltas=scen.deltas.loc[ids],
        probs=new_p[keep],
        kind=[k for k, m in zip(scen.kind, keep, strict=True) if m],
    )


# ------------------------------------------------------------------------ S1 · tasas
def rate_shock_delta(doc: Mapping, shock: Mapping) -> dict[str, float]:
    """Δ de los nodos spot para un shock de `rateShocks`: paralelo en `currencies`, o solo en el tramo `bucket` de
    `stressTenors` con la transición por t·s(t) de los estrés (D-11 v2). El resto de factores en 0."""
    node_years = {n["id"]: float(n["years"]) for n in doc["curveNodes"]}
    tenors = doc["caseParameters"]["stressTenors"]
    shift, bucket = float(shock["shift"]), shock.get("bucket")
    if bucket is not None and bucket not in tenors:
        raise ValueError(f"{shock['id']}: el tramo {bucket} no está en stressTenors ({sorted(tenors)})")
    delta = dict.fromkeys(risk.FACTORS, 0.0)
    for ccy in shock["currencies"]:
        if bucket is None:
            by_node = dict.fromkeys(node_years, shift)
        else:
            by_node = risk._stress_curve_shift(0.0, {bucket: shift}, tenors, node_years)
        for node, v in by_node.items():
            key = f"{ccy}_SPOT_{node}"
            if key not in delta:
                raise ValueError(f"{shock['id']}: factor desconocido {key}")
            delta[key] = float(v)
    return delta


def _with_rule(doc: Mapping, rule: str) -> dict:
    """Copia con `floatingCouponRule` = rule (la clave puede faltar: FLAT por defecto, D-22)."""
    new = copy.deepcopy(dict(doc))
    new["caseParameters"]["floatingCouponRule"] = rule
    return new


def rate_shock_pnl(
    doc: Mapping,
    portfolios: Mapping[str, pd.Series],
    spreads: Mapping[str, float] | None = None,
    rules: list[str] | None = None,
) -> pd.DataFrame:
    """ΔV instantáneo en t0 (S/ mm) de cada cartera bajo cada shock de `sensitivities.rateShocks` (S1).

    ΔV_k = x_k / V0_k · [V_k(t0; curva + δ) − V_k(t0)] por revalorización completa con los spreads calibrados
    fijos (flotantes reproyectados con la curva desplazada). Se repite para cada regla de cupones de `rules`
    (por defecto, solo la del documento): el tramo corto depende de D-13 (auditoría I-2). `spreads` solo se usa
    para la regla del documento; las demás se recalibran. Columnas: rule, shock, portfolio, assets (ΔV activos),
    liabilities (ΔV pasivos) y netWorth = assets − liabilities.
    """
    base_rule = coupon_rule(doc)
    inst = pd.DataFrame(doc["instruments"]).set_index("id")
    x0 = inst["market_value_pen"].astype(float)
    is_asset = inst["side"] == "ASSET"
    rows = []
    for rule in rules or [base_rule]:
        d = _with_rule(doc, rule)
        sp = spreads if (spreads is not None and rule == base_rule) else calibrate_spreads(d)
        v0 = value_at_t0(d, sp)
        for shock in doc["caseParameters"]["sensitivities"]["rateShocks"]:
            rel = ((value_at_t0(d, sp, rate_shock_delta(doc, shock)) - v0) / x0).reindex(inst.index)
            for name, pos in portfolios.items():
                change = pd.Series(pos, dtype=float).reindex(inst.index).fillna(0.0) * rel
                a, li = float(change[is_asset].sum()), float(change[~is_asset].sum())
                rows.append(
                    {
                        "rule": rule,
                        "shock": shock["id"],
                        "portfolio": name,
                        "assets": a,
                        "liabilities": li,
                        "netWorth": a - li,
                    }
                )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------- variantes
def _metrics(data: opt.ProblemData, positions: pd.Series) -> dict:
    ev = opt.evaluate(data, positions)
    return {
        "expectedNetWorthChange": ev["expected_pnl"],
        "transactionCosts": ev["transaction_cost"],
        "expectedTerminalNetWorth": ev["expected_terminal_net_worth"],
        "varLoss": ev["var"],
        "cvarLoss": ev["cvar"],
        "cvarAlpha": data.alpha,
        "netWorthVolatility": ev["volatility"],
        "stressLosses": ev["stress_losses"],
        "tailStressShare": ev["tail_stress_share"],
    }


ROW_KEYS = (
    "objective",
    "expectedNetWorthChange",
    "transactionCosts",
    "expectedTerminalNetWorth",
    "varLoss",
    "cvarLoss",
    "cvarAlpha",
    "netWorthVolatility",
    "stressLosses",
    "tailStressShare",
    "turnover",
    "distanceToBase",
    "weights",
    "activeLimits",
    "positions",
)


def _row(data: opt.ProblemData, res: dict, base_positions: pd.Series | None) -> dict:
    """Fila de resultados de una solución; si no es óptima, solo el status (el resto en None)."""
    if res["status"] not in opt.OPTIMAL:
        return {"status": res["status"], **dict.fromkeys(ROW_KEYS)}
    pos = res["positions"]
    x0 = data.x0.loc[data.ids]
    dist = None if base_positions is None else float((pos - base_positions.reindex(data.ids)).abs().sum())
    return {
        "status": res["status"],
        "objective": res["objective"],
        **_metrics(data, pos),
        "turnover": float((pos - x0).abs().sum()),
        "distanceToBase": dist,
        "weights": opt._weights(data, pos),
        "activeLimits": [
            c["name"]
            for c in opt.check_constraints(data, pos)
            if c["active"] and c["name"] not in EXCLUDED_LIMITS
        ],
        "positions": {k: float(v) for k, v in pos.items()},
    }


def solve_variant(doc: Mapping, components: tuple, base_positions: pd.Series | None = None) -> dict:
    """Resuelve una variante con λ = riskAversionLambda y devuelve su fila (ver `_row`). `components` =
    (reval, flows, ScenarioSet); si el ScenarioSet es un subconjunto, se usan solo sus columnas. Con
    `base_positions`, la fila trae además `basePortfolio`: esa cartera evaluada con el modelo de la variante
    (separa el efecto de la medida del de reoptimizar, auditoría M-2)."""
    data = opt.prepare(doc, components=components)
    row = _row(data, opt.solve_data(data), base_positions)
    if base_positions is not None:
        row["basePortfolio"] = _metrics(data, base_positions)
    return row


# ------------------------------------------------------------------ S2 · precios sombra
def _active_bound(check: dict) -> str | None:
    """'min' o 'max' según la cota en la que está un límite activo."""
    v = check["value"]
    if check["max"] is not None and abs(v - check["max"]) <= opt.ACTIVE_TOL * max(1.0, abs(check["max"])):
        return "max"
    if check["min"] is not None and abs(v - check["min"]) <= opt.ACTIVE_TOL * max(1.0, abs(check["min"])):
        return "min"
    return None


def _twins(data: opt.ProblemData, active: Mapping[str, str]) -> list[tuple[str, str]]:
    """Parejas de cotas activas gemelas (auditoría I-3): mismo lado y dimensión, miembros disjuntos que cubren todo
    el lado, una en su mínimo y otra en su máximo con min + max = 1 (p. ej. pasivo fijo ≥ 45 % y flotante ≤ 55 %).
    Son la misma restricción: el LP reparte el dual entre ambas de forma arbitraria. Devuelve (nombre en mínimo,
    nombre en máximo)."""
    groups = {g["name"]: g for g in data.groups}
    pairs = []
    for lo_name, lo_bound in active.items():
        if lo_bound != "min":
            continue
        lo = groups[lo_name]
        side_ids = {i for i in data.ids if data.side[i] == lo["side"]}
        for hi_name, hi_bound in active.items():
            hi = groups[hi_name]
            if (
                hi_bound == "max"
                and hi["side"] == lo["side"]
                and hi["dimension"] == lo["dimension"]
                and not set(lo["members"]) & set(hi["members"])
                and set(lo["members"]) | set(hi["members"]) == side_ids
                and abs(lo["min"] + hi["max"] - 1.0) <= opt.OK_TOL
            ):
                pairs.append((lo_name, hi_name))
    return pairs


def _relaxed_gain(data: opt.ProblemData, base_obj: float, moves: Mapping[str, str], relax: float) -> tuple:
    """(ganancia por pp, pp relajados) al relajar a la vez las cotas `moves` {grupo: 'min'|'max'} en `relax`
    (acotado a [0, 1]; el mismo paso para todas). (None, 0) si no se puede relajar."""
    groups = {g["name"]: g for g in data.groups}
    room = [groups[n]["min"] if b == "min" else 1.0 - groups[n]["max"] for n, b in moves.items()]
    step = min([relax, *room])
    if step <= 0:
        return None, 0.0
    sign = {"min": -1.0, "max": 1.0}
    relaxed = dataclasses.replace(
        data,
        groups=[
            {**g, moves[g["name"]]: g[moves[g["name"]]] + sign[moves[g["name"]]] * step}
            if g["name"] in moves
            else g
            for g in data.groups
        ],
    )
    res = opt.solve_data(relaxed)
    if res["status"] not in opt.OPTIMAL:
        return None, step * PP
    return (res["objective"] - base_obj) / (step * PP), step * PP


def shadow_prices(doc: Mapping, components: tuple) -> pd.DataFrame:
    """Precio sombra de cada cota de peso activa del Cuadro 4 (S2): S/ mm de objetivo por 1 pp de relajación.

    - dualPerPp = dual del LP / 100: derivada del objetivo al relajar la cota con las demás fijas.
    - finiteDiffPerPp / finiteDiffSmallPerPp = (objetivo relajado − objetivo) / pp, relajando `limitRelaxation` y
      `limitRelaxationSmall` (subir el máximo o bajar el mínimo, dentro de [0, 1]). El objetivo óptimo es cóncavo y
      lineal por tramos en el límite: el dual es la pendiente local (≈ paso chico) y el paso grande es la ganancia
      media del tramo, menor si la pendiente cae (auditoría M-1).
    - Cotas gemelas (`_twins`, auditoría I-3) van en una sola fila "A+B" que las relaja juntas; su dual es la suma.
    Las cotas que no se pueden relajar (mínimo 0, máximo 1) se omiten.
    """
    cfg = doc["caseParameters"]["sensitivities"]
    relax, small = float(cfg["limitRelaxation"]), float(cfg["limitRelaxationSmall"])
    data = opt.prepare(doc, components=components)
    base = opt.solve_data(data, duals=True)
    if base["status"] not in opt.OPTIMAL:
        raise ValueError(f"El problema base no es óptimo ({base['status']}): no hay precios sombra")
    groups = {g["name"]: g for g in data.groups}
    checks = {c["name"]: c for c in opt.check_constraints(data, base["positions"])}
    active = {
        n: b for n, c in checks.items() if n in groups and c["active"] and (b := _active_bound(c)) is not None
    }
    twins = _twins(data, active)
    paired = {n for pair in twins for n in pair}
    entries = [({lo: "min", hi: "max"}, f"{lo}+{hi}") for lo, hi in twins]
    entries += [({n: b}, n) for n, b in active.items() if n not in paired]

    rows = []
    for moves, name in entries:
        fd, pp = _relaxed_gain(data, base["objective"], moves, relax)
        if pp == 0:
            continue
        fd_small, pp_small = _relaxed_gain(data, base["objective"], moves, small)
        first = next(iter(moves))
        rows.append(
            {
                "name": name,
                "side": groups[first]["side"],
                "bound": "+".join(moves.values()),
                "limit": float(groups[first][moves[first]]),
                "value": checks[first]["value"],
                "dualPerPp": sum(base["duals"][f"{n}:{b}"] for n, b in moves.items()) / PP,
                "finiteDiffPerPp": fd,
                "finiteDiffSmallPerPp": fd_small,
                "relaxationPp": pp,
                "relaxationSmallPp": pp_small,
            }
        )
    cols = [
        "side",
        "bound",
        "limit",
        "value",
        "dualPerPp",
        "finiteDiffPerPp",
        "finiteDiffSmallPerPp",
        "relaxationPp",
        "relaxationSmallPp",
    ]
    return pd.DataFrame(rows, columns=["name", *cols]).set_index("name")


# ------------------------------------------------------------------ corrida completa
def _components(doc: Mapping, seed: int | None = None) -> tuple:
    scen = risk.build_scenarios(doc, seed=seed)
    reval, flows = risk.scenario_components(doc, scen.deltas)
    return reval, flows, scen


def extra_stress_components(doc: Mapping, components: tuple, scenario: Mapping) -> tuple[dict, tuple]:
    """(doc con el estrés agregado, componentes) para S8 sin revalorizar todo: solo se revaloriza el escenario
    nuevo y se concatena a r_{k,s} base. Válido porque el bootstrap no cambia (misma semilla y bootstrapCount:
    mismos ids y Δ) y `prepare` selecciona columnas por id."""
    reval, flows, _ = components
    new_doc = add_stress(doc, scenario)
    scen = risk.build_scenarios(new_doc)
    sid = scenario["scenario_id"]
    r_new, f_new = risk.scenario_components(new_doc, scen.deltas.loc[[sid]])
    return new_doc, (pd.concat([reval, r_new], axis=1), pd.concat([flows, f_new], axis=1), scen)


def _records(df: pd.DataFrame) -> list[dict]:
    return [
        {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in r.items()}
        for r in df.to_dict("records")
    ]


def run_all(doc: Mapping, log=print) -> dict:
    """Todas las sensibilidades de `caseParameters.sensitivities` (S1-S9), serializable a JSON.

    Cada fila de reoptimización trae la distancia L1 a la cartera óptima base y esa cartera evaluada con el modelo
    de la variante (`basePortfolio`; en S6 se llama `outOfSample`). S1 se reporta con la regla de cupones del
    documento y con cada una de `floatingCouponRules`. `log` recibe mensajes de avance (None = silencio).
    """
    log = log or (lambda *_: None)
    cfg = doc["caseParameters"]["sensitivities"]
    start = time.perf_counter()

    log("base: escenarios y revalorización…")
    comps = _components(doc)
    reval, flows, scen = comps
    data = opt.prepare(doc, components=comps)
    res = opt.solve_data(data)
    base = _row(data, res, None)
    if res["status"] not in opt.OPTIMAL:
        return {"base": base, "error": "El problema base no es óptimo: no se corren sensibilidades"}
    x_star = res["positions"]
    e_star = base["expectedNetWorthChange"] - base["transactionCosts"]
    mv = opt.solve_data(data, mode="variance", min_net_return=e_star)
    portfolios = {"initial": data.x0.loc[data.ids], "optimal": x_star}
    if mv["status"] in opt.OPTIMAL:
        portfolios["meanVariance"] = mv["positions"]

    out: dict = {"base": base}
    log("S1 tasas, S2 precios sombra…")
    rules = [coupon_rule(doc), *(r for r in cfg["floatingCouponRules"] if r != coupon_rule(doc))]
    out["rateShocks"] = _records(rate_shock_pnl(doc, portfolios, rules=rules))
    out["shadowPrices"] = _records(shadow_prices(doc, comps).reset_index())

    log("S3 costos, S4 α, S5 cola de estrés…")
    out["costs"] = [
        {"multiplier": float(m), **solve_variant(scale_costs(doc, m), comps, x_star)}
        for m in cfg["costMultipliers"]
    ]
    out["alphas"] = [
        {
            "alpha": float(a),
            **solve_variant(with_overrides(doc, {"caseParameters.cvarAlpha": a}), comps, x_star),
        }
        for a in cfg["cvarAlphas"]
    ]
    out["stressWeight"] = [
        {
            "stressProbability": float(p),
            **solve_variant(doc, (reval, flows, reweight_stress(scen, stress_probability=p)), x_star),
        }
        for p in cfg["stressProbabilities"]
    ]
    stress_ids = [s for s, k in zip(scen.ids, scen.kind, strict=True) if k == "stress"]
    out["stressLeaveOneOut"] = (
        [
            {"dropped": s, **solve_variant(doc, (reval, flows, reweight_stress(scen, drop=s)), x_star)}
            for s in stress_ids
        ]
        if cfg.get("stressLeaveOneOut")
        else []
    )

    out["seeds"] = []
    for seed in cfg["seeds"]:
        log(f"S6 semilla {seed}…")
        row = solve_variant(doc, _components(doc, seed=int(seed)), x_star)
        out["seeds"].append({"seed": int(seed), "outOfSample": row.pop("basePortfolio"), **row})

    out["drift"] = []
    for name, spec in cfg["driftVariants"].items():
        log(f"S7 deriva {name}…")
        dd = with_overrides(doc, {"caseParameters.drift": spec})
        out["drift"].append({"variant": name, **solve_variant(dd, _components(dd), x_star)})

    out["extraStress"] = []
    for extra in cfg["extraStress"]:
        log(f"S8 estrés {extra['scenario_id']}…")
        dd, c = extra_stress_components(doc, comps, extra)
        out["extraStress"].append({"scenario": extra["scenario_id"], **solve_variant(dd, c, x_star)})

    out["floatingCouponRule"] = []
    for rule in cfg["floatingCouponRules"]:
        log(f"S9 regla de cupones {rule}…")
        dd = _with_rule(doc, rule)
        out["floatingCouponRule"].append({"rule": rule, **solve_variant(dd, _components(dd), x_star)})

    out["meta"] = {
        "caseId": doc["caseId"],
        "riskAversionLambda": data.lam,
        "baseSeed": doc["caseParameters"]["seed"],
        "config": copy.deepcopy(dict(cfg)),
        "runtimeSeconds": time.perf_counter() - start,
    }
    return out
