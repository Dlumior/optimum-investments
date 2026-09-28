"""Pruebas de la capa (iii) riesgo y escenarios, escritas antes de implementar.

Referencias: docs/formulacion.md §5 (CVaR con átomo fraccional), §7.1-7.4 (bootstrap, deriva, estrés, r_ks),
§10 (pruebas); decisiones D-06, D-09, D-11, D-14, D-15, D-16.
Convenciones: tasas y shocks en decimales; FX y equity como log-retornos; montos en S/ mm; horizonte 1 año.
"""

import copy
import math

import numpy as np
import pandas as pd
import pytest

from optimum.cleaning import FACTORS
from optimum.io.json_contract import load_input

try:
    from optimum.risk import (
        ScenarioSet,
        bootstrap_shocks,
        build_scenarios,
        drift,
        factor_changes,
        history_from_doc,
        pn_change,
        scenario_diagnostics,
        scenario_returns,
        sensitivities,
        stress_shocks,
        var_cvar,
    )
    from optimum.valuation import calibrate_spreads, horizon_value_and_flows, value_at_t0
except ImportError:  # se activa sola al implementar la interfaz en risk.py
    pytest.skip("TODO: activar cuando risk.py implemente la interfaz", allow_module_level=True)

SPOT_NODES = ["ON", "1Y", "3Y", "5Y", "10Y", "20Y"]


# ----------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def doc():
    return load_input()


@pytest.fixture(scope="module")
def spreads(doc):
    return calibrate_spreads(doc)


@pytest.fixture(scope="module")
def scenarios(doc):
    return build_scenarios(doc)


@pytest.fixture(scope="module")
def stress(doc):
    return stress_shocks(doc)


def _with_params(doc, **params):
    d = copy.deepcopy(doc)
    d["caseParameters"].update(params)
    return d


def _zero_delta(ids=("Z",)):
    return pd.DataFrame(0.0, index=list(ids), columns=FACTORS)


# ------------------------------------------------------------------- historia y cambios
def test_history_has_factor_order(doc):
    hist = history_from_doc(doc)
    assert list(hist.columns) == FACTORS
    assert len(hist) == len(doc["marketHistory"])
    assert hist.index.is_monotonic_increasing


def test_changes_from_doc_match_excel(doc, tables):
    """Los cambios derivados de input.json coinciden con la hoja Factor_Changes ya validada."""
    ours = factor_changes(doc)
    ref = tables["factor_changes"]
    assert list(ours.columns) == FACTORS
    assert len(ours) == len(ref)
    assert np.abs(ours.to_numpy() - ref.to_numpy()).max() < 1e-12


# ---------------------------------------------------------------------------- bootstrap
def _toy_changes():
    idx = pd.date_range("2021-01-31", periods=4, freq="ME")
    return pd.DataFrame({"f": [1.0, 2.0, 3.0, 4.0]}, index=idx)


def test_bootstrap_toy_single_block():
    """Centrados = [-1.5, -0.5, 0.5, 1.5]; ventanas de 2 → sumas {-2, 0, 2}, y se alcanzan todas (T-b+1 = 3)."""
    shocks = bootstrap_shocks(_toy_changes(), n=400, block_length=2, n_blocks=1, seed=1)
    assert shocks.shape == (400, 1)
    assert set(np.round(shocks[:, 0], 12)) == {-2.0, 0.0, 2.0}


def test_bootstrap_centers_windows_not_months():
    """Juguete asimétrico [0, 0, 0, 10], b = 2: ventanas brutas {0, 0, 10}, media 10/3. Centrar los meses dejaría
    sumas {-5, -5, 5} con media −5/3 ≠ 0 (los extremos pesan menos); centrar las ventanas da media exacta 0."""
    idx = pd.date_range("2021-01-31", periods=4, freq="ME")
    toy = pd.DataFrame({"f": [0.0, 0.0, 0.0, 10.0]}, index=idx)
    shocks = bootstrap_shocks(toy, n=400, block_length=2, n_blocks=1, seed=1)
    assert set(np.round(shocks[:, 0], 12)) == {round(-10 / 3, 12), round(20 / 3, 12)}


def test_bootstrap_mean_equals_drift(doc, scenarios):
    """Tras centrar las ventanas, la media del bootstrap solo difiere de μ por ruido de muestreo (< 3 errores estándar)."""
    boot = scenarios.deltas[np.asarray(scenarios.kind) == "bootstrap"]
    mu = drift(doc, factor_changes(doc))
    se = boot.std(ddof=1) / np.sqrt(len(boot))
    for f in ["PEN_SPOT_ON", "USD_SPOT_ON", "PEN_SPOT_10Y", "FX_PENUSD", "EQUITY_USD"]:
        assert abs(boot[f].mean() - mu[f]) < 3 * se[f], f


def test_bootstrap_toy_two_blocks():
    shocks = bootstrap_shocks(_toy_changes(), n=400, block_length=2, n_blocks=2, seed=1)
    assert set(np.round(shocks[:, 0], 12)) <= {-4.0, -2.0, 0.0, 2.0, 4.0}


def test_bootstrap_constant_changes_give_zero_shocks():
    idx = pd.date_range("2021-01-31", periods=10, freq="ME")
    const = pd.DataFrame({"a": 0.003, "b": -0.01}, index=idx)
    shocks = bootstrap_shocks(const, n=50, block_length=3, n_blocks=2, seed=7)
    assert np.allclose(shocks, 0.0, atol=1e-15)


def test_bootstrap_reproducible_by_seed(doc):
    ch = factor_changes(doc)
    a = bootstrap_shocks(ch, n=20, block_length=6, n_blocks=2, seed=123)
    b = bootstrap_shocks(ch, n=20, block_length=6, n_blocks=2, seed=123)
    c = bootstrap_shocks(ch, n=20, block_length=6, n_blocks=2, seed=124)
    assert a.shape == (20, len(FACTORS))
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_bootstrap_rejects_block_longer_than_history():
    with pytest.raises(ValueError):
        bootstrap_shocks(_toy_changes(), n=5, block_length=5, n_blocks=1, seed=1)


# -------------------------------------------------------------------------------- deriva
def test_drift_values(doc):
    ch = factor_changes(doc)
    mu = drift(doc, ch)
    assert list(mu.index) == FACTORS
    rates = [f for f in FACTORS if f not in ("FX_PENUSD", "EQUITY_USD")]
    assert np.allclose(mu[rates], 0.0)  # ZERO
    spot0 = doc["marketHistory"][-1]["spot"]
    irp = math.log((1 + spot0["PEN"]["1Y"]) / (1 + spot0["USD"]["1Y"]))
    assert mu["FX_PENUSD"] == pytest.approx(irp, abs=1e-15)  # IRP, FX = PEN por USD
    assert mu["EQUITY_USD"] == pytest.approx(12 * ch["EQUITY_USD"].mean(), abs=1e-15)  # HISTORICAL


def test_history_ignores_dates_after_valuation(doc):
    """M-1: filas posteriores a valuationDate no deben entrar (información futura)."""
    d = copy.deepcopy(doc)
    future = copy.deepcopy(d["marketHistory"][-1])
    future["date"] = "2026-01-31"
    future["equityIndex"] *= 1.5
    d["marketHistory"].append(future)
    assert history_from_doc(d).index.max() == pd.Timestamp(doc["valuationDate"])
    assert drift(d, factor_changes(d))["EQUITY_USD"] == pytest.approx(
        drift(doc, factor_changes(doc))["EQUITY_USD"]
    )


def test_drift_irp_uses_horizon_tenor(doc):
    """M-3: con horizonte de 2 años, la IRP usa z(2Y) de cada curva (tasa anual por paridad a ese plazo)."""
    from optimum.valuation import base_state

    d = _with_params(doc, horizonDate="2027-12-31")
    curves = base_state(d).curves
    expected = math.log((1 + float(curves["PEN"].zero(2.0))) / (1 + float(curves["USD"].zero(2.0))))
    assert drift(d, factor_changes(d))["FX_PENUSD"] == pytest.approx(expected, abs=1e-15)


def test_drift_unknown_type_raises(doc):
    bad = _with_params(doc, drift={"rates": "ZERO", "fx": "MAGIA", "equity": "HISTORICAL"})
    with pytest.raises(ValueError):
        drift(bad, factor_changes(bad))


# ------------------------------------------------------------------------------ estrés
def test_stress_shape_and_forwards_zero(stress, doc):
    assert list(stress.index) == [s["scenario_id"] for s in doc["stressScenarios"]]
    assert list(stress.columns) == FACTORS
    fwd = [f for f in FACTORS if "_FWD_" in f]
    assert np.allclose(stress[fwd], 0.0)  # se recalculan desde la spot shockeada (D-10)


def test_stress_matches_doc_fields(stress, doc):
    """Derivado de input.json (no de valores fijos): paralelo fuera de tramos y transiciones, override en los nodos
    del tramo cuando existe, y ln(1 + pct) en FX y equity."""
    tenors = doc["caseParameters"]["stressTenors"]
    transition = {n for spec in tenors.values() for n in spec.get("transition", [])}
    for s in doc["stressScenarios"]:
        row = stress.loc[s["scenario_id"]]
        for ccy in ["PEN", "USD"]:
            c, par = ccy.lower(), s[f"{ccy.lower()}_parallel"]
            for n in SPOT_NODES:
                bucket = next((b for b, spec in tenors.items() if n in spec["nodes"]), None)
                override = s.get(f"{c}_{bucket}_override") if bucket else None
                if override is not None:
                    assert row[f"{ccy}_SPOT_{n}"] == pytest.approx(override, abs=1e-15)
                elif n not in transition or all(s.get(f"{c}_{b}_override") is None for b in tenors):
                    assert row[f"{ccy}_SPOT_{n}"] == pytest.approx(par, abs=1e-15)
        assert math.exp(row["FX_PENUSD"]) == pytest.approx(1 + (s["fx_pct"] or 0.0))
        assert math.exp(row["EQUITY_USD"]) == pytest.approx(1 + (s["equity_pct"] or 0.0))


def _toy_stress(doc, tenors=None, **fields):
    """Doc con un único estrés de juguete (sin FX ni equity); `fields` sobrescribe los shifts."""
    d = copy.deepcopy(doc)
    scen = {"scenario_id": "T", "probability": 0.05, "pen_parallel": 0.005, "usd_parallel": 0.0}
    scen.update({f"{c}_{b}_override": None for c in ["pen", "usd"] for b in ["short", "long"]})
    scen.update({"fx_pct": 0.0, "equity_pct": 0.0, **fields})
    d["stressScenarios"] = [scen]
    if tenors is not None:
        d["caseParameters"]["stressTenors"] = tenors
    return d


def test_stress_short_transition_interpolates_t_times_s(doc):
    """D-11 v2: en la transición se interpola t·s(t) entre el último nodo del tramo y el primero fuera de él.
    Corto (ON, 1Y) = +400 pb, 5Y = paralelo +50 pb: 3·s(3) = 1·0.04 + (5·0.005 − 1·0.04)·(3 − 1)/(5 − 1)
    → s(3) = 0.0325/3 = 0.0108333."""
    row = stress_shocks(_toy_stress(doc, pen_short_override=0.04)).loc["T"]
    expected = {"ON": 0.04, "1Y": 0.04, "3Y": 0.0325 / 3, "5Y": 0.005, "10Y": 0.005, "20Y": 0.005}
    for n in SPOT_NODES:
        assert row[f"PEN_SPOT_{n}"] == pytest.approx(expected[n], abs=1e-15)
        assert row[f"USD_SPOT_{n}"] == pytest.approx(0.0, abs=1e-15)


def test_stress_long_transition_interpolates_t_times_s(doc):
    """Largo (10Y, 20Y) = +300 pb, 3Y = paralelo +50 pb: 5·s(5) = 3·0.005 + (10·0.03 − 3·0.005)·(5 − 3)/(10 − 3)
    → s(5) = (0.015 + 0.285·2/7)/5."""
    row = stress_shocks(_toy_stress(doc, pen_long_override=0.03)).loc["T"]
    expected = {
        "ON": 0.005,
        "1Y": 0.005,
        "3Y": 0.005,
        "5Y": (0.015 + 0.285 * 2 / 7) / 5,
        "10Y": 0.03,
        "20Y": 0.03,
    }
    for n in SPOT_NODES:
        assert row[f"PEN_SPOT_{n}"] == pytest.approx(expected[n], abs=1e-15)


def test_stress_transition_spreads_forward_change_evenly(doc):
    """El cambio medio de la forward entre 1Y y 5Y lo fijan los datos: (5·50 − 1·400)/4 = −37.5 pb. Con t·s(t)
    lineal se reparte parejo entre S2 y S3 (antes: S2 +138, S3 −210 pb)."""
    from optimum.valuation import base_state

    d = _toy_stress(doc, pen_short_override=0.04)
    state0 = base_state(d)
    shocked = state0.shocked(stress_shocks(d).loc["T"].to_dict())
    for seg in ["S2", "S3"]:
        change = shocked.forwards[f"PEN_FWD_{seg}"] - state0.forwards[f"PEN_FWD_{seg}"]
        assert -0.0045 < change < -0.0030, (seg, change)


def test_stress_overlapping_tenors_raise(doc):
    tenors = {
        "short": {"nodes": ["ON", "1Y"], "transition": ["3Y", "5Y"]},
        "long": {"nodes": ["10Y", "20Y"], "transition": ["5Y"]},
    }
    with pytest.raises(ValueError):
        stress_shocks(_toy_stress(doc, tenors=tenors, pen_long_override=0.02))


def test_stress_override_without_bucket_raises(doc):
    with pytest.raises(ValueError):
        stress_shocks(_toy_stress(doc, pen_mid_override=0.01))


def test_stress_missing_parallel_raises(doc):
    d = _toy_stress(doc)
    del d["stressScenarios"][0]["usd_parallel"]
    with pytest.raises(ValueError):
        stress_shocks(d)


# ------------------------------------------------------------------ conjunto de escenarios
def test_scenario_set_sizes_and_probabilities(scenarios, doc):
    cp = doc["caseParameters"]
    n_b, n_e = cp["bootstrapCount"], len(doc["stressScenarios"])
    assert isinstance(scenarios, ScenarioSet)
    assert len(scenarios.ids) == n_b + n_e
    assert scenarios.deltas.shape == (n_b + n_e, len(FACTORS))
    assert list(scenarios.deltas.columns) == FACTORS
    kinds = pd.Series(scenarios.kind)
    assert (kinds == "bootstrap").sum() == n_b and (kinds == "stress").sum() == n_e
    assert scenarios.probs.sum() == pytest.approx(1.0, abs=1e-12)
    assert scenarios.probs[kinds.to_numpy() == "stress"].sum() == pytest.approx(
        cp["stressProbability"], abs=1e-12
    )
    assert np.allclose(scenarios.probs[kinds.to_numpy() == "bootstrap"], cp["bootstrapProbability"] / n_b)


def test_scenario_set_reproducible(doc, scenarios):
    again = build_scenarios(doc)
    assert np.array_equal(again.deltas.to_numpy(), scenarios.deltas.to_numpy())


def test_drift_added_only_to_bootstrap(doc, scenarios):
    """Con la misma semilla, pasar de deriva ZERO a la mixta suma μ exacto a cada escenario bootstrap y no toca el estrés."""
    flat = build_scenarios(_with_params(doc, drift={"rates": "ZERO", "fx": "ZERO", "equity": "ZERO"}))
    mu = drift(doc, factor_changes(doc))
    diff = scenarios.deltas - flat.deltas
    boot = np.asarray(scenarios.kind) == "bootstrap"
    assert np.allclose(diff[boot].to_numpy(), mu.to_numpy()[None, :], atol=1e-15)
    assert np.allclose(diff[~boot].to_numpy(), 0.0)


def test_stress_probability_mismatch_raises(doc):
    with pytest.raises(ValueError):
        build_scenarios(_with_params(doc, stressProbability=0.06))


def test_horizon_inconsistent_with_blocks_raises(doc):
    """D-15: b·m debe coincidir con los meses entre valuationDate y horizonDate."""
    with pytest.raises(ValueError):
        build_scenarios(_with_params(doc, bootstrapBlockLength=3))


# ------------------------------------------------------------------ resultados r_{k,s}
def test_returns_zero_shock_is_carry(doc, spreads):
    r = scenario_returns(doc, _zero_delta(), spreads)
    h = horizon_value_and_flows(doc, spreads, {})
    v0 = pd.Series({i["id"]: i["market_value_pen"] for i in doc["instruments"]})
    expected = (h["value_h"] + h["flows"]) / v0 - 1
    assert list(r.columns) == ["Z"]
    assert np.allclose(r["Z"].reindex(expected.index), expected, atol=1e-12)
    on0 = doc["marketHistory"][-1]["spot"]["PEN"]["ON"]
    assert r.loc["A01", "Z"] == pytest.approx(on0 * 365 / 365, abs=1e-12)  # caja: ON0 · τ
    assert r.loc["A06", "Z"] == pytest.approx(0.0, abs=1e-15)  # equity sin shock ni dividendos


def test_returns_equity_and_fx_shocks(doc, spreads):
    d = _zero_delta(["EQ", "FX"])
    d.loc["EQ", "EQUITY_USD"] = math.log(0.75)
    d.loc["FX", "FX_PENUSD"] = math.log(1.20)
    r = scenario_returns(doc, d, spreads)
    assert r.loc["A06", "EQ"] == pytest.approx(-0.25, abs=1e-12)
    assert r.loc["A06", "FX"] == pytest.approx(0.20, abs=1e-12)
    on0 = doc["marketHistory"][-1]["spot"]["PEN"]["ON"]
    assert r.loc["A01", "FX"] == pytest.approx(on0, abs=1e-12)  # caja PEN no depende del FX


def test_fixed_bond_flows_in_year_are_contractual(doc, spreads):
    """Independiente de la fórmula de r: los flujos del año de un bono fijo PEN son los del cronograma."""
    t0, th = pd.Timestamp(doc["valuationDate"]), pd.Timestamp(doc["caseParameters"]["horizonDate"])
    fixed_pen = next(
        i["id"] for i in doc["instruments"] if i["currency"] == "PEN" and i["instrument_type"] == "BOND_FIXED"
    )
    cf = pd.DataFrame(doc["cashFlows"])
    cf = cf[(cf["instrument_id"] == fixed_pen) & (pd.to_datetime(cf["payment_date"]) > t0)]
    expected = cf.loc[pd.to_datetime(cf["payment_date"]) <= th, "total_cash_flow"].sum()
    assert horizon_value_and_flows(doc, spreads, {}).loc[fixed_pen, "flows"] == pytest.approx(
        expected, abs=1e-12
    )


def test_cash_accrues_half_on_shock(doc, spreads):
    """D-12: la caja devenga ON0 + ½ΔON (τ = 1): con ΔON = +150 pb, r = ON0 + 0.0075."""
    d = _zero_delta()
    d.loc["Z", "PEN_SPOT_ON"] = 0.015
    on0 = doc["marketHistory"][-1]["spot"]["PEN"]["ON"]
    assert scenario_returns(doc, d, spreads).loc["A01", "Z"] == pytest.approx(on0 + 0.0075, abs=1e-12)


def test_fx_shock_scales_usd_values_and_converts_flows_on_path(doc, spreads):
    """FX +20 %: V(tH) de todo instrumento USD × 1.20 exacto, PEN sin cambio (una cobertura con igual V(tH) USD en
    activos y pasivos queda inmune). Flujos USD del año convertidos con FX(τ) = FX0·1.2^θ(τ), no con FX(tH)."""
    from optimum.curves import year_fraction

    base = horizon_value_and_flows(doc, spreads, {})
    fx = horizon_value_and_flows(doc, spreads, {"FX_PENUSD": math.log(1.2)})
    ccy = pd.Series({i["id"]: i["currency"] for i in doc["instruments"]})
    ratio = fx["value_h"] / base["value_h"]
    assert np.allclose(ratio[ccy == "USD"], 1.2, atol=1e-12)
    assert np.allclose(ratio[ccy == "PEN"], 1.0, atol=1e-12)

    t0, th = pd.Timestamp(doc["valuationDate"]), pd.Timestamp(doc["caseParameters"]["horizonDate"])
    fixed_usd = next(
        i["id"] for i in doc["instruments"] if i["currency"] == "USD" and i["instrument_type"] == "BOND_FIXED"
    )
    cf = pd.DataFrame(doc["cashFlows"])
    pay = pd.to_datetime(cf["payment_date"])
    cf = cf[(cf["instrument_id"] == fixed_usd) & (pay > t0) & (pay <= th)]
    theta = np.asarray(year_fraction(t0, pd.to_datetime(cf["payment_date"]))) / float(year_fraction(t0, th))
    fx0 = doc["marketHistory"][-1]["fx"]["PENUSD"]
    expected = float(np.sum(cf["total_cash_flow"].to_numpy() * fx0 * 1.2**theta))
    assert fx.loc[fixed_usd, "flows"] == pytest.approx(expected, rel=1e-12)
    assert expected < 1.2 * base.loc[fixed_usd, "flows"]  # no se convierte todo con FX(tH)


def test_zero_market_value_raises_clear_error(doc):
    """I-3: market_value_pen es precio y posición; 0 debe fallar con un mensaje que nombre el instrumento."""
    d = copy.deepcopy(doc)
    d["instruments"][1]["market_value_pen"] = 0.0
    iid = d["instruments"][1]["id"]
    with pytest.raises(ValueError, match=iid):
        calibrate_spreads(d)
    with pytest.raises(ValueError, match=iid):
        scenario_returns(d, _zero_delta())


def test_calibration_out_of_bracket_names_instrument(doc):
    """M-5: si el spread no está en el intervalo de búsqueda, el error nombra el instrumento."""
    d = copy.deepcopy(doc)
    d["instruments"][1]["market_value_pen"] = 1e6
    with pytest.raises(ValueError, match=d["instruments"][1]["id"]):
        calibrate_spreads(d)


def _floaters_by_segment(doc, keep):
    """Flotantes cuyo segmento de referencia (fromNode, toNode) cumple `keep`, por moneda: {ccy: [ids]}."""
    segs = {s["id"]: (s["fromNode"], s["toNode"]) for s in doc["curveSegments"]}
    out = {}
    for i in doc["instruments"]:
        ref = i["reference_factor"]
        if ref and "_FWD_" in ref:
            ccy, seg = ref.split("_FWD_")
            if keep(*segs[seg]):
                out.setdefault(ccy, []).append(i["id"])
    return out


def test_short_rate_stress_never_lowers_short_floating_coupons(doc, spreads, stress):
    """En todo estrés con override corto > paralelo, los flotantes indexados a un segmento dentro del tramo corto
    (hoy S1: ON-1Y) no reducen sus flujos del año respecto de Δ = 0."""
    short = set(doc["caseParameters"]["stressTenors"]["short"]["nodes"])
    inside = _floaters_by_segment(doc, lambda a, b: a in short and b in short)
    base = horizon_value_and_flows(doc, spreads, {})
    for s in doc["stressScenarios"]:
        shocked = horizon_value_and_flows(doc, spreads, stress.loc[s["scenario_id"]].to_dict())
        for ccy, ids in inside.items():
            ov, par = s.get(f"{ccy.lower()}_short_override"), s[f"{ccy.lower()}_parallel"]
            if ov is not None and ov > par:
                assert (shocked.loc[ids, "flows"] >= base.loc[ids, "flows"] - 1e-12).all(), (
                    s["scenario_id"],
                    ids,
                )


def test_short_rate_stress_lowers_coupons_on_transition_segment(doc, spreads):
    """Consecuencia documentada de D-11 v2 + D-13: con +400 pb en ON-1Y y +50 pb desde 5Y, la forward 1Y-3Y cae
    (≈ −35 pb, inevitable en promedio entre 1Y y 5Y), así que los flotantes indexados a ella cobran/pagan menos."""
    short = doc["caseParameters"]["stressTenors"]["short"]
    straddle = _floaters_by_segment(doc, lambda a, b: a in short["nodes"] and b in short["transition"])
    ids = straddle.get("PEN", [])
    if not ids:
        pytest.skip("Ningún flotante PEN indexado al segmento de transición corto")
    d = _toy_stress(doc, pen_short_override=0.04)
    shocked = horizon_value_and_flows(d, spreads, stress_shocks(d).loc["T"].to_dict())
    base = horizon_value_and_flows(doc, spreads, {})
    assert (shocked.loc[ids, "flows"] < base.loc[ids, "flows"]).all()


def test_pn_change_signs():
    r = pd.DataFrame({"s1": [0.10, 0.05], "s2": [-0.20, 0.00]}, index=["A", "L"])
    pos = pd.Series({"A": 100.0, "L": 80.0})
    sides = pd.Series({"A": "ASSET", "L": "LIABILITY"})
    # s1: 100·0.10 − 80·0.05 = 6 ; s2: 100·(−0.20) − 0 = −20
    assert np.allclose(pn_change(r, pos, sides), [6.0, -20.0])


# ------------------------------------------------------------------------------ VaR/CVaR
def test_cvar_fractional_atom_by_hand():
    """α = 0.95. P(L ≤ 5) = 0.98 ≥ 0.95 y P(L ≤ 1) = 0.94 < 0.95 → VaR = 5.
    CVaR = [0.02·10 + 5·(0.05 − 0.02)] / 0.05 = 7."""
    losses = np.array([0.0, 10.0, 1.0, 5.0])
    probs = np.array([0.50, 0.02, 0.44, 0.04])
    var, cvar = var_cvar(losses, 0.95, probs)
    assert var == pytest.approx(5.0)
    assert cvar == pytest.approx(7.0)


def test_cvar_uniform_equals_tail_mean():
    losses = np.arange(1.0, 101.0)  # 100 escenarios equiprobables
    var, cvar = var_cvar(losses, 0.95)
    assert var == pytest.approx(95.0)
    assert cvar == pytest.approx(np.mean([96, 97, 98, 99, 100]))


def test_cvar_at_least_var_and_bad_inputs():
    rng = np.random.default_rng(0)
    losses = rng.normal(size=1000)
    var, cvar = var_cvar(losses, 0.95)
    assert cvar >= var
    with pytest.raises(TypeError):
        var_cvar(losses)  # M-4: α sale de input.json, sin valor por defecto
    with pytest.raises(ValueError):
        var_cvar(losses, 1.2)
    with pytest.raises(ValueError):
        var_cvar(np.array([1.0, 2.0]), 0.95, np.array([0.5, 0.6]))  # no suman 1


# --------------------------------------------------------------------------- controles
def test_bootstrap_sigma_is_annual_order(doc, scenarios):
    """σ del shock bootstrap a 12 m del orden de la σ histórica de la suma móvil a 12 m (no σ_mensual·√12 si hay
    persistencia; D-09)."""
    diag = scenario_diagnostics(doc, scenarios)
    sig = diag["sigma"]
    for f in ["PEN_SPOT_ON", "USD_SPOT_ON", "FX_PENUSD", "EQUITY_USD"]:
        ratio = sig.loc[f, "bootstrap_12m"] / sig.loc[f, "historical_12m"]
        assert 0.5 < ratio < 2.0, (f, ratio)


def test_min_rate_diagnostic(doc, scenarios):
    diag = scenario_diagnostics(doc, scenarios)
    assert list(diag["min_rate"].index) == list(scenarios.ids)
    assert np.isfinite(diag["min_rate"]).all()
    base_min = min(min(c.values()) for c in doc["marketHistory"][-1]["spot"].values())
    lowest = min(doc["stressScenarios"], key=lambda s: min(s["pen_parallel"], s["usd_parallel"]))
    if min(lowest["pen_parallel"], lowest["usd_parallel"]) < 0:  # estrés con caída de tasas
        assert diag["min_rate"][lowest["scenario_id"]] < base_min


# ---------------------------------------------------------------- sensibilidades (D-14)
def test_sensitivities_linear_toy():
    def value_fn(delta):
        return pd.Series({"X": 3.0 * delta.get("f1", 0.0) - 2.0 * delta.get("f2", 0.0), "Y": 5.0})

    m = sensitivities(value_fn, ["f1", "f2"])
    assert m.loc["X", "f1"] == pytest.approx(3.0)
    assert m.loc["X", "f2"] == pytest.approx(-2.0)
    assert np.allclose(m.loc["Y"], 0.0)


def test_sensitivities_match_full_revaluation_small_shock(doc, spreads):
    """Para +10 pb en toda la curva PEN, M·ΔF aproxima la revalorización completa (error < 2 %)."""
    factors = [f"PEN_SPOT_{n}" for n in SPOT_NODES]
    m = sensitivities(lambda d: value_at_t0(doc, spreads, d), factors)
    shock = {f: 0.001 for f in factors}
    full = value_at_t0(doc, spreads, shock) - value_at_t0(doc, spreads)
    local = m[factors] @ pd.Series(shock)
    big = full.abs() > 0.1
    assert np.allclose(local[big], full[big], rtol=0.02)
