"""Pruebas de las sensibilidades (etapa v), escritas ANTES de implementar `optimum.sensitivity`.

Fuentes de verdad: docs/formulacion.md §11 (S1-S9) y docs/decisiones.md D-21, D-22.

API planificada (`optimum.sensitivity`, se accede como `sens.<función>` para que cada prueba falle por separado):
- with_overrides(doc, {"a.b.c": v}) -> dict       copia profunda; KeyError si la ruta no existe.
- scale_costs(doc, m) -> dict                     restructuring_cost × m en una copia.
- reweight_stress(scen, stress_probability=None, drop=None) -> ScenarioSet   (S5)
- add_stress(doc, scenario) -> dict               (S8) suma p a stressProbability y la resta a bootstrapProbability.
- rate_shock_delta(doc, shock) -> dict[str, float]  Δ de factores spot de un shock de `rateShocks` (S1).
- rate_shock_pnl(doc, portfolios, spreads=None) -> DataFrame  columnas shock, portfolio, assets, liabilities,
  netWorth (S/ mm; ΔV de activos, ΔV de pasivos, ΔPN = assets − liabilities).
- solve_variant(doc, components, base_positions=None) -> dict   fila de resultados de una variante:
  status, objective, expectedNetWorthChange, transactionCosts, varLoss, cvarLoss, netWorthVolatility, stressLosses,
  turnover, distanceToBase, weights, activeLimits, positions. Si no es óptima: status y el resto en None.
- shadow_prices(doc, components) -> DataFrame     índice = nombre del grupo; columnas bound (min/max),
  dualPerPp y finiteDiffPerPp (S/ mm de objetivo por 1 pp de relajación) (S2).
- run_all(doc) -> dict                            todas las sensibilidades, serializable a JSON.

Juguete: el mismo de tests/test_optimizer.py (2 activos, 1 pasivo; la decisión es la caja c). Con λ = 0.5 la
pendiente del objetivo para c > 30 es −0.0248 + 0.082·0.5 = 0.0162 S/ mm por S/ mm de caja; con máx. de caja 55 %
el óptimo es c = 55 y solo esa cota de peso limita la caja (el bono queda en 45 > 40 % mínimo de renta fija).
Como B_A = 100, 1 pp = 1 S/ mm: precio sombra = 0.0162 S/ mm por pp.
"""

from __future__ import annotations

import copy
import json
import math

import numpy as np
import pandas as pd
import pytest
from test_optimizer import R_BOND as R_BOND_TOY
from test_optimizer import TOY_KIND, TOY_PROBS, TOY_SCEN, _toy_components, _toy_doc

import optimum.optimizer as opt
import optimum.risk as risk
from optimum.cleaning import FACTORS
from optimum.curves import year_fraction
from optimum.io.json_contract import load_input
from optimum.valuation import base_state, calibrate_spreads

try:
    import optimum.sensitivity as sens
except ImportError:  # se activa sola al crear src/optimum/sensitivity.py
    pytest.skip("TODO: activar cuando exista optimum.sensitivity (formulación §11)", allow_module_level=True)

TOL = 1e-6
SLOPE = -0.0248 + 0.082 * 0.5  # d objetivo / d caja para c > 30 con λ = 0.5


def _toy(**kw) -> dict:
    d = _toy_doc(**kw)
    d["caseParameters"]["sensitivities"] = {"limitRelaxation": 0.05, "limitRelaxationSmall": 0.005}
    return d


# ============================================================== copias del documento
def test_with_overrides_copies_and_sets():
    doc = _toy()
    new = sens.with_overrides(doc, {"caseParameters.cvarAlpha": 0.99, "constraints.common.minCash": 9.0})
    assert new["caseParameters"]["cvarAlpha"] == 0.99
    assert new["constraints"]["common"]["minCash"] == 9.0
    assert doc["caseParameters"]["cvarAlpha"] == 0.90  # el original no cambia
    assert doc["constraints"]["common"]["minCash"] == 8.0


def test_with_overrides_unknown_path_raises():
    with pytest.raises(KeyError):
        sens.with_overrides(_toy(), {"caseParameters.cvarAlfa": 0.99})


def test_scale_costs():
    doc = _toy()
    new = sens.scale_costs(doc, 2.0)
    assert new["transactionCosts"]["B1"]["restructuring_cost"] == pytest.approx(0.004)
    assert doc["transactionCosts"]["B1"]["restructuring_cost"] == pytest.approx(0.002)


# ================================================================ S3 · costos (juguete)
def test_zero_costs_give_zero_tc_and_higher_objective():
    comps = _toy_components()
    base = sens.solve_variant(_toy(lam=0.5), comps)
    free = sens.solve_variant(sens.scale_costs(_toy(lam=0.5), 0.0), comps)
    assert free["transactionCosts"] == pytest.approx(0.0, abs=TOL)
    assert free["objective"] >= base["objective"] - TOL


def test_objective_non_increasing_in_cost_multiplier():
    comps = _toy_components()
    objs = [
        sens.solve_variant(sens.scale_costs(_toy(lam=0.28), m), comps)["objective"] for m in [0, 0.5, 1, 2, 4]
    ]
    assert all(b <= a + TOL for a, b in zip(objs, objs[1:], strict=False))


# ============================================================= variantes: fila y errores
def test_solve_variant_row_by_hand():
    """λ = 0.5, caja máx. 55 %: c = 55, TC = 0.002·25, rotación 25 + 25, distancia a sí misma 0."""
    doc = _toy(lam=0.5, cash_max=0.55)
    comps = _toy_components()
    row = sens.solve_variant(doc, comps)
    assert row["status"] == "OPTIMAL"
    assert row["positions"]["C1"] == pytest.approx(55.0, abs=1e-5)
    assert row["transactionCosts"] == pytest.approx(0.05, abs=1e-6)
    assert row["turnover"] == pytest.approx(50.0, abs=1e-5)
    again = sens.solve_variant(doc, comps, base_positions=pd.Series(row["positions"]))
    assert again["distanceToBase"] == pytest.approx(0.0, abs=1e-5)
    assert "ASSET:TYPE:CASH" in row["activeLimits"]


def test_infeasible_variant_is_reported_not_raised():
    doc = sens.with_overrides(_toy(), {"constraints.common.minCash": 70.0})  # caja máx. 60 < 70
    row = sens.solve_variant(doc, _toy_components())
    assert row["status"] == "INFEASIBLE"
    assert row["objective"] is None and row["cvarLoss"] is None


# ============================================================ S2 · precios sombra (juguete)
def test_shadow_price_by_hand():
    doc = _toy(lam=0.5, cash_max=0.55)
    sp = sens.shadow_prices(doc, _toy_components())
    row = sp.loc["ASSET:TYPE:CASH"]
    assert row["bound"] == "max"
    assert row["dualPerPp"] == pytest.approx(SLOPE, abs=1e-6)
    assert row["finiteDiffPerPp"] == pytest.approx(SLOPE, abs=1e-6)  # relajar 5 pp: c = 60, sigue lineal
    assert (sp["dualPerPp"] >= -1e-9).all()


def test_twin_limits_are_relaxed_together():
    """Auditoría I-3. Caja ≤ 55 % y renta fija ≥ 45 % son gemelas (los dos grupos cubren todos los activos y
    0.45 + 0.55 = 1): relajar solo una no mueve el óptimo. Van en una fila que las relaja juntas; la suma de duales y
    la diferencia finita dan la pendiente a mano."""
    fi = {
        "side": "ASSET",
        "dimension": "TYPE",
        "category": "FIXED_INCOME",
        "min_weight": 0.45,
        "max_weight": 0.90,
    }
    doc = _toy(lam=0.5, cash_max=0.55)
    doc["constraints"]["weights"] = [
        fi | {"index": w["index"], "note": ""} if w["category"] == "FIXED_INCOME" else w
        for w in doc["constraints"]["weights"]
    ]
    sp = sens.shadow_prices(doc, _toy_components())
    assert "ASSET:TYPE:CASH" not in sp.index and "ASSET:TYPE:FIXED_INCOME" not in sp.index
    row = sp.loc["ASSET:TYPE:FIXED_INCOME+ASSET:TYPE:CASH"]
    assert row["bound"] == "min+max"
    assert row["dualPerPp"] == pytest.approx(SLOPE, abs=1e-6)
    assert row["finiteDiffPerPp"] == pytest.approx(SLOPE, abs=1e-6)
    assert row["finiteDiffSmallPerPp"] == pytest.approx(SLOPE, abs=1e-6)


def test_variant_reports_base_portfolio():
    """Con base_positions, la fila trae esa cartera evaluada con la medida de la variante (auditoría M-2)."""
    reval, flows, scen = _toy_components()
    doc = _toy(lam=0.5)
    base = sens.solve_variant(doc, (reval, flows, scen))
    x = pd.Series(base["positions"])
    new = sens.reweight_stress(scen, stress_probability=0.10)
    row = sens.solve_variant(doc, (reval, flows, new), base_positions=x)
    dpn = x["C1"] * 0.03 + x["B1"] * R_BOND_TOY - 80 * 0.03
    assert row["basePortfolio"]["expectedNetWorthChange"] == pytest.approx(float(new.probs @ dpn), abs=1e-9)


def test_solve_data_returns_duals():
    data = opt.prepare(_toy(lam=0.5, cash_max=0.55), components=_toy_components())
    res = opt.solve_data(data, duals=True)
    assert res["duals"]["ASSET:TYPE:CASH:max"] == pytest.approx(SLOPE * 100.0, abs=1e-6)  # por unidad de peso


# =========================================================== S5 · peso de la cola de estrés
def _two_stress_set() -> risk.ScenarioSet:
    ids = ["B1", "B2", "B3", "X", "Y"]
    return risk.ScenarioSet(
        ids=ids,
        deltas=pd.DataFrame(np.arange(5)[:, None] * np.ones(len(FACTORS)), index=ids, columns=FACTORS),
        probs=np.array([0.3, 0.3, 0.3, 0.06, 0.04]),
        kind=["bootstrap"] * 3 + ["stress"] * 2,
    )


def test_reweight_stress_keeps_proportions():
    new = sens.reweight_stress(_two_stress_set(), stress_probability=0.20)
    np.testing.assert_allclose(new.probs, [0.8 / 3] * 3 + [0.12, 0.08], atol=1e-12)
    assert new.ids == _two_stress_set().ids


def test_reweight_stress_drop_redistributes():
    new = sens.reweight_stress(_two_stress_set(), drop="X")
    assert new.ids == ["B1", "B2", "B3", "Y"]
    np.testing.assert_allclose(new.probs, [0.3, 0.3, 0.3, 0.10], atol=1e-12)
    assert list(new.deltas.index) == new.ids
    assert new.kind == ["bootstrap"] * 3 + ["stress"]


def test_reweight_stress_invalid():
    with pytest.raises(ValueError):
        sens.reweight_stress(_two_stress_set(), drop="B1")  # no es un estrés
    single = risk.ScenarioSet(
        TOY_SCEN, pd.DataFrame(0.0, index=TOY_SCEN, columns=FACTORS), TOY_PROBS, TOY_KIND
    )
    with pytest.raises(ValueError):
        sens.reweight_stress(single, drop="S5")  # quedaría sin estrés


def test_reweighted_scenarios_solve_on_subset_of_components():
    """Dejar fuera el único estrés del juguete no es válido; con P = 0.10 el problema sigue resolviéndose."""
    reval, flows, scen = _toy_components()
    new = sens.reweight_stress(scen, stress_probability=0.10)
    row = sens.solve_variant(_toy(lam=0.5), (reval, flows, new))
    assert row["status"] == "OPTIMAL"


# ============================================================== S1 y S8 (input.json real)
@pytest.fixture(scope="module")
def doc():
    d = copy.deepcopy(load_input())
    d["caseParameters"]["bootstrapCount"] = 100
    return d


@pytest.fixture(scope="module")
def spreads(doc):
    return calibrate_spreads(doc)


def _ids(doc, **attrs):
    return [i["id"] for i in doc["instruments"] if all(i[k] == v for k, v in attrs.items())]


def _pv_by_hand(doc, iid, spread, shift):
    """Σ amount·(1 + z(t) + shift + s)^(−t) · FX0, flujos posteriores a t0 (bono fijo, a mano)."""
    inst = next(i for i in doc["instruments"] if i["id"] == iid)
    state = base_state(doc)
    t0 = pd.Timestamp(doc["valuationDate"])
    cf = pd.DataFrame([r for r in doc["cashFlows"] if r["instrument_id"] == iid])
    cf = cf[pd.to_datetime(cf["payment_date"]) > t0]
    t = year_fraction(t0, pd.to_datetime(cf["payment_date"]))
    z = state.curves[inst["currency"]].zero(t)
    pv = np.sum(cf["total_cash_flow"].to_numpy(float) * (1 + z + shift + spread) ** (-t))
    return pv * state.fx_to_pen(inst["currency"])


def test_rate_shock_delta_parallel_and_bucket(doc):
    par = sens.rate_shock_delta(doc, {"id": "PEN+200", "currencies": ["PEN"], "shift": 0.02})
    pen_nodes = [f"PEN_SPOT_{n['id']}" for n in doc["curveNodes"]]
    assert all(par[f] == pytest.approx(0.02) for f in pen_nodes)
    assert all(
        abs(par.get(f, 0.0)) < 1e-15
        for f in FACTORS
        if f.startswith("USD_") or f in ("FX_PENUSD", "EQUITY_USD")
    )

    short = sens.rate_shock_delta(
        doc, {"id": "PEN_SHORT+200", "currencies": ["PEN"], "shift": 0.02, "bucket": "short"}
    )
    tenors = doc["caseParameters"]["stressTenors"]["short"]
    for n in tenors["nodes"]:
        assert short[f"PEN_SPOT_{n}"] == pytest.approx(0.02)
    for n in ("10Y", "20Y"):
        assert short.get(f"PEN_SPOT_{n}", 0.0) == pytest.approx(0.0)
    for n in tenors["transition"]:
        assert 0.0 < short[f"PEN_SPOT_{n}"] < 0.02


def test_rate_shock_pnl_fixed_bonds_by_hand(doc, spreads):
    """+200 pb en ambas monedas sobre la cartera inicial: ΔV de cada bono fijo = PV a mano con z + 0.02."""
    x0 = pd.Series({i["id"]: float(i["market_value_pen"]) for i in doc["instruments"]})
    shock = {"id": "ALL+200", "currencies": ["PEN", "USD"], "shift": 0.02}
    d = sens.with_overrides(doc, {"caseParameters.sensitivities.rateShocks": [shock]})

    fixed = _ids(doc, instrument_type="BOND_FIXED")
    dv = {
        iid: _pv_by_hand(doc, iid, spreads[iid], 0.02) - _pv_by_hand(doc, iid, spreads[iid], 0.0)
        for iid in fixed
    }
    assert all(v < 0 for v in dv.values())
    # cartera con una sola posición: la del primer bono fijo de activos y la del primer bono fijo de pasivos
    a = next(i for i in fixed if i in _ids(doc, side="ASSET"))
    lia = next(i for i in fixed if i in _ids(doc, side="LIABILITY"))
    pos = pd.Series(0.0, index=x0.index)
    pos[[a, lia]] = x0[[a, lia]]
    tab = sens.rate_shock_pnl(d, {"single": pos}, spreads=spreads).set_index("portfolio")
    row = tab.loc["single"]
    assert row["assets"] == pytest.approx(dv[a], abs=1e-6)
    assert row["liabilities"] == pytest.approx(dv[lia], abs=1e-6)
    assert row["netWorth"] == pytest.approx(dv[a] - dv[lia], abs=1e-6)  # pasivo que baja = PN que sube


def test_rate_shock_zero_and_currency_isolation(doc, spreads):
    x0 = pd.Series({i["id"]: float(i["market_value_pen"]) for i in doc["instruments"]})
    usd = [i for i in _ids(doc, currency="USD")]
    pen_only = x0.copy()
    pen_only[usd] = 0.0
    shocks = [
        {"id": "ZERO", "currencies": ["PEN", "USD"], "shift": 0.0},
        {"id": "USD+200", "currencies": ["USD"], "shift": 0.02},
    ]
    d = sens.with_overrides(doc, {"caseParameters.sensitivities.rateShocks": shocks})
    tab = sens.rate_shock_pnl(d, {"x0": x0, "pen": pen_only}, spreads=spreads).set_index(
        ["shock", "portfolio"]
    )
    assert tab.loc[("ZERO", "x0"), "netWorth"] == pytest.approx(0.0, abs=1e-9)
    assert tab.loc[("USD+200", "pen"), "netWorth"] == pytest.approx(0.0, abs=1e-9)


def test_rate_shock_floating_liability_sign(doc, spreads):
    """Auditoría M-6: cartera solo con el primer pasivo flotante; ΔPN = −ΔV del pasivo, con ΔV recalculado aparte."""
    from optimum.valuation import value_at_t0

    x0 = pd.Series({i["id"]: float(i["market_value_pen"]) for i in doc["instruments"]})
    lia = next(i["id"] for i in doc["instruments"] if i["side"] == "LIABILITY" and i["reference_factor"])
    pos = pd.Series(0.0, index=x0.index)
    pos[lia] = x0[lia]
    shock = {"id": "ALL+200", "currencies": ["PEN", "USD"], "shift": 0.02}
    d = sens.with_overrides(doc, {"caseParameters.sensitivities.rateShocks": [shock]})
    row = sens.rate_shock_pnl(d, {"p": pos}, spreads=spreads).iloc[0]
    dv = value_at_t0(doc, spreads, sens.rate_shock_delta(doc, shock))[lia] - value_at_t0(doc, spreads)[lia]
    assert row["assets"] == pytest.approx(0.0, abs=1e-12)
    assert row["liabilities"] == pytest.approx(dv, abs=1e-9)
    assert row["netWorth"] == pytest.approx(-dv, abs=1e-9)


def test_rate_shock_pnl_by_rule(doc, spreads):
    """Auditoría I-2: una fila por regla de cupones; la regla del documento reproduce la corrida sin `rules`."""
    x0 = pd.Series({i["id"]: float(i["market_value_pen"]) for i in doc["instruments"]})
    shock = {"id": "SHORT+200", "currencies": ["PEN", "USD"], "shift": 0.02, "bucket": "short"}
    d = sens.with_overrides(doc, {"caseParameters.sensitivities.rateShocks": [shock]})
    one = sens.rate_shock_pnl(d, {"x0": x0}, spreads=spreads)
    both = sens.rate_shock_pnl(d, {"x0": x0}, spreads=spreads, rules=["FLAT", "PERIOD_FORWARD"]).set_index(
        "rule"
    )
    assert set(both.index) == {"FLAT", "PERIOD_FORWARD"}
    assert both.loc["FLAT", "netWorth"] == pytest.approx(one["netWorth"].iloc[0], abs=1e-12)
    assert both.loc["PERIOD_FORWARD", "netWorth"] != pytest.approx(both.loc["FLAT", "netWorth"], abs=1e-3)


def test_add_stress_keeps_probabilities(doc):
    mirror = {
        "scenario_id": "C_STRESS_PEN_UP",
        "probability": 0.0125,
        "pen_parallel": 0.03,
        "usd_parallel": 0.015,
        "fx_pct": -0.20,
        "equity_pct": -0.25,
    }
    new = sens.add_stress(doc, mirror)
    cp0, cp1 = doc["caseParameters"], new["caseParameters"]
    assert cp1["stressProbability"] == pytest.approx(cp0["stressProbability"] + 0.0125)
    assert cp1["bootstrapProbability"] == pytest.approx(cp0["bootstrapProbability"] - 0.0125)
    assert len(new["stressScenarios"]) == len(doc["stressScenarios"]) + 1  # el original no cambia
    scen = risk.build_scenarios(new)
    assert scen.probs.sum() == pytest.approx(1.0)
    assert scen.deltas.loc["C_STRESS_PEN_UP", "FX_PENUSD"] == pytest.approx(math.log(0.8))


# ============================================================== corrida completa (lenta)
@pytest.mark.slow
def test_run_all_invariants(doc):
    """Con grillas reducidas: estructura serializable y coherencia con la base (m = 1, α base, P base, semilla
    base fuera de muestra = en muestra)."""
    cp = doc["caseParameters"]
    d = sens.with_overrides(
        doc,
        {
            "caseParameters.sensitivities": {
                "rateShocks": [{"id": "ALL+200", "currencies": ["PEN", "USD"], "shift": 0.02}],
                "limitRelaxation": 0.05,
                "limitRelaxationSmall": 0.005,
                "costMultipliers": [0.0, 1.0],
                "cvarAlphas": [cp["cvarAlpha"], 0.99],
                "stressProbabilities": [cp["stressProbability"], 0.10],
                "stressLeaveOneOut": True,
                "seeds": [cp["seed"]],
                "driftVariants": {},
                "extraStress": [],
                "floatingCouponRules": [],
            }
        },
    )
    out = sens.run_all(d)
    json.dumps(out)  # serializable
    base = out["base"]["objective"]
    by = lambda rows, key, v: next(r for r in rows if r[key] == v)  # noqa: E731
    assert by(out["costs"], "multiplier", 1.0)["objective"] == pytest.approx(base, abs=1e-6)
    assert by(out["alphas"], "alpha", cp["cvarAlpha"])["objective"] == pytest.approx(base, abs=1e-6)
    assert by(out["stressWeight"], "stressProbability", cp["stressProbability"])[
        "objective"
    ] == pytest.approx(base, abs=1e-6)
    assert len(out["stressLeaveOneOut"]) == len(doc["stressScenarios"])
    oos = by(out["seeds"], "seed", cp["seed"])
    assert oos["outOfSample"]["cvarLoss"] == pytest.approx(out["base"]["cvarLoss"], abs=1e-6)
    assert {r["portfolio"] for r in out["rateShocks"]} >= {"initial", "optimal", "meanVariance"}


@pytest.mark.slow
def test_extra_stress_components_match_full_recompute(doc):
    """Auditoría M-6: concatenar solo el estrés nuevo da la misma r_{k,s} que revalorizar todo el conjunto."""
    extra = {
        "scenario_id": "C_STRESS_PEN_UP",
        "probability": 0.0125,
        "pen_parallel": 0.03,
        "usd_parallel": 0.015,
        "fx_pct": -0.20,
        "equity_pct": -0.25,
    }
    scen = risk.build_scenarios(doc)
    reval, flows = risk.scenario_components(doc, scen.deltas)
    new_doc, (r_cat, f_cat, s_cat) = sens.extra_stress_components(doc, (reval, flows, scen), extra)
    full = risk.build_scenarios(new_doc)
    r_full, f_full = risk.scenario_components(new_doc, full.deltas)
    assert s_cat.ids == full.ids
    np.testing.assert_allclose(s_cat.probs, full.probs, atol=1e-15)
    pd.testing.assert_frame_equal(r_cat[full.ids], r_full[full.ids], atol=1e-12)
    pd.testing.assert_frame_equal(f_cat[full.ids], f_full[full.ids], atol=1e-12)
