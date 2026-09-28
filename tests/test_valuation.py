"""Pruebas de la capa (ii) valorización, escritas antes de implementar (docs/formulacion.md §7.4, D-10, D-12, D-13).

Convención de flotantes (D-13): cada cupón futuro = nivel del factor de referencia (p. ej. PEN_FWD_S2) en su fecha
de fijación + spread contractual; tasa × nocional / frecuencia. Fijación = fecha de pago − reset_months.
"""

import copy
import math

import numpy as np
import pandas as pd
import pytest

from optimum.curves import ZeroCurve, implied_forward
from optimum.io.json_contract import load_input

try:
    from optimum.valuation import (
        MarketState,
        calibrate_spreads,
        coupon_rates,
        horizon_value_and_flows,
        market_path,
        present_value,
        value_at_t0,
    )
except ImportError:  # se activa sola al implementar la interfaz en valuation.py
    pytest.skip("TODO: activar cuando valuation.py implemente la interfaz", allow_module_level=True)

T0 = pd.Timestamp("2025-12-31")
TH = pd.Timestamp("2026-12-31")
TENORS = np.array([0, 1, 3, 5, 10, 20.0])


# ----------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def doc():
    return load_input()


@pytest.fixture(scope="module")
def state0(doc):
    return MarketState.from_market_row(doc["marketHistory"][-1])


@pytest.fixture(scope="module")
def spreads(doc):
    return calibrate_spreads(doc)


@pytest.fixture(scope="module")
def v0(doc, spreads):
    return value_at_t0(doc, spreads)


def _inst(doc, iid):
    return next(i for i in doc["instruments"] if i["id"] == iid)


def _cf(doc, iid):
    cf = pd.DataFrame([r for r in doc["cashFlows"] if r["instrument_id"] == iid])
    cf["payment_date"] = pd.to_datetime(cf["payment_date"])
    return cf.sort_values("period").reset_index(drop=True)


def _flows(dates, amounts):
    return pd.DataFrame({"payment_date": pd.to_datetime(dates), "amount": amounts})


def _ids(doc, **attrs):
    return [i["id"] for i in doc["instruments"] if all(i[k] == v for k, v in attrs.items())]


# ------------------------------------------------------------- 1-2. descuento a mano
def test_zero_coupon_by_hand():
    """100 a 1 año, z = 4 % plana, spread 1 %: V = 100 / 1.05."""
    flat = ZeroCurve("PEN", TENORS, np.full(6, 0.04))
    pv = present_value(_flows(["2026-12-31"], [100.0]), flat, T0, spread=0.01)
    assert pv == pytest.approx(100 / 1.05, abs=1e-10)
    assert present_value(_flows(["2026-12-31"], [100.0]), flat, T0, spread=0.0) > pv


def test_two_flow_bond_by_hand_with_interpolation():
    """Flujos a 1 y 2 años (ACT/365 exactos); z(2) = promedio lineal de 1Y y 3Y."""
    curve = ZeroCurve("PEN", TENORS, np.array([0.04, 0.041, 0.043, 0.047, 0.053, 0.06]))
    pv = present_value(_flows(["2026-12-31", "2027-12-31"], [5.0, 105.0]), curve, T0, spread=0.0)
    assert pv == pytest.approx(5 / 1.041 + 105 / 1.042**2, abs=1e-10)


def test_flows_on_or_before_as_of_are_excluded():
    """Un flujo en la fecha de valorización o antes ya se pagó: no forma parte del valor."""
    flat = ZeroCurve("PEN", TENORS, np.full(6, 0.04))
    flows = _flows(["2025-06-30", "2025-12-31", "2026-12-31"], [7.0, 7.0, 100.0])
    assert present_value(flows, flat, T0) == pytest.approx(100 / 1.04, abs=1e-10)


def test_expired_instrument_is_worth_zero():
    flat = ZeroCurve("PEN", TENORS, np.full(6, 0.04))
    assert present_value(_flows(["2025-06-30"], [100.0]), flat, T0) == 0.0


# ------------------------------------------------------- 3. estado base == Excel
def test_recomputed_forwards_match_excel(doc, state0):
    """D-10: las forwards son implícitas de la spot; en t0 coinciden con FWD_S* del Excel."""
    row = doc["marketHistory"][-1]
    for ccy, segs in row["forwardSwap"].items():
        for seg, value in segs.items():
            assert state0.forwards[f"{ccy}_FWD_{seg}"] == pytest.approx(value, abs=1e-10)


def test_base_coupon_projection_matches_cash_flows(doc, state0):
    """Convención (a): con el mercado base se reproduce projected_coupon_rate de todos los flotantes."""
    for iid in _ids(doc):
        inst = _inst(doc, iid)
        if not inst["reference_factor"]:
            continue
        cf = _cf(doc, iid)
        rates = coupon_rates(cf, inst["reset_months"], T0, lambda d: state0)
        np.testing.assert_allclose(rates, cf["projected_coupon_rate"].to_numpy(), atol=1e-12)


# --------------------------------------------------------------- 4-5. calibración
def test_calibration_reproduces_market_value(doc, v0):
    for inst in doc["instruments"]:
        assert v0[inst["id"]] == pytest.approx(inst["market_value_pen"], abs=1e-6), inst["id"]


def test_calibrated_spreads_close_to_sheet(doc, spreads):
    """La hoja Calibration_Spreads es referencia: se exige cercanía, no igualdad."""
    for iid, s in spreads.items():
        assert s == pytest.approx(doc["calibrationSpreads"][iid], abs=1e-4), iid


def test_balance_totals(doc, v0):
    common = doc["constraints"]["common"]
    assert v0[_ids(doc, side="ASSET")].sum() == pytest.approx(common["assetBudget"], abs=1e-6)
    assert v0[_ids(doc, side="LIABILITY")].sum() == pytest.approx(common["liabilityBudget"], abs=1e-6)


# ------------------------------------------------------------ 6. shock de tasas
def test_shocked_state_is_consistent(state0):
    """θ escala el shock; FX multiplicativo; las forwards siguen siendo implícitas de la spot."""
    delta = {"PEN_SPOT_5Y": 0.01, "FX_PENUSD": math.log(1.1)}
    half = state0.shocked(delta, theta=0.5)
    assert half.curves["PEN"].zero(5.0) == pytest.approx(state0.curves["PEN"].zero(5.0) + 0.005)
    assert half.fx_penusd == pytest.approx(state0.fx_penusd * math.exp(0.5 * math.log(1.1)))
    assert half.forwards["PEN_FWD_S3"] == pytest.approx(implied_forward(half.curves["PEN"], 3.0, 5.0))


def test_parallel_shock_on_coupons(doc, state0):
    """+100 pb paralelo: el cupón fijado en t0 no cambia; los demás de L01 (ref. S1 = z(1Y)) suben 100 pb exactos."""
    shocked = state0.shocked(_parallel(0.01))
    inst = _inst(doc, "L01")
    cf = _cf(doc, "L01")
    base = coupon_rates(cf, inst["reset_months"], T0, lambda d: state0)
    new = coupon_rates(cf, inst["reset_months"], T0, lambda d: shocked)
    assert new[0] == pytest.approx(base[0], abs=1e-12)
    np.testing.assert_allclose(new[1:] - base[1:], 0.01, atol=1e-12)


def test_parallel_shock_on_values(doc, spreads, v0):
    """+100 pb: los bonos fijos bajan; los flotantes bajan proporcionalmente menos que el fijo de su moneda."""
    v = value_at_t0(doc, spreads, delta=_parallel(0.01))
    fixed = _ids(doc, instrument_type="BOND_FIXED")
    for iid in fixed:
        assert v[iid] < v0[iid], iid
    drop = lambda iid: v[iid] / v0[iid] - 1  # noqa: E731
    assert drop("A03") > drop("A02")  # PEN: flotante vs fijo
    assert drop("A05") > drop("A04")  # USD
    assert v["A01"] == pytest.approx(v0["A01"])
    assert v["A06"] == pytest.approx(v0["A06"])


# ------------------------------------------------------------------- 7. FX
def test_fx_shock_scales_usd_only(doc, spreads, v0):
    v = value_at_t0(doc, spreads, delta={"FX_PENUSD": math.log(1.1)})
    for inst in doc["instruments"]:
        factor = 1.1 if inst["currency"] == "USD" else 1.0
        assert v[inst["id"]] == pytest.approx(v0[inst["id"]] * factor, rel=1e-10), inst["id"]


# ------------------------------------------------------------- 8. horizonte
def test_market_path_is_linear_and_capped(state0):
    """D-12: F(τ) = F0 + θΔ con θ = (τ − t0)/(tH − t0), acotado a [0, 1]."""
    path = market_path(state0, {"PEN_SPOT_1Y": 0.01}, T0, TH)
    z1 = lambda s: float(s.curves["PEN"].zero(1.0))  # noqa: E731
    assert z1(path(pd.Timestamp("2026-03-31"))) == pytest.approx(z1(state0) + 0.01 * 90 / 365)
    assert z1(path(T0 - pd.Timedelta(days=90))) == pytest.approx(z1(state0))
    assert z1(path(pd.Timestamp("2030-12-31"))) == pytest.approx(z1(state0) + 0.01)


def test_horizon_zero_shock_cash_and_equity(doc, spreads, state0):
    h = horizon_value_and_flows(doc, spreads, delta={})
    on0 = float(state0.curves["PEN"].zero(0.0))
    assert h.loc["A01", "value_h"] + h.loc["A01", "flows"] == pytest.approx(150.0 * (1 + on0))
    assert h.loc["A06", "value_h"] == pytest.approx(220.0)
    assert h.loc["A06", "flows"] == 0.0


def test_horizon_no_double_counting(doc, spreads, state0):
    """El flujo del 2026-12-31 va en flows y no en value_h; value_h descuenta desde tH."""
    h = horizon_value_and_flows(doc, spreads, delta={})
    cf = _cf(doc, "A02")
    assert h.loc["A02", "flows"] == pytest.approx(cf.loc[cf.payment_date <= TH, "total_cash_flow"].sum())
    later = cf.loc[cf.payment_date > TH].rename(columns={"total_cash_flow": "amount"})
    expected = present_value(later[["payment_date", "amount"]], state0.curves["PEN"], TH, spreads["A02"])
    assert h.loc["A02", "value_h"] == pytest.approx(expected, rel=1e-12)


def test_horizon_cash_accrues_half_on_shock(doc, spreads, state0):
    """D-12: la caja devenga ON0 + ½ΔON."""
    h = horizon_value_and_flows(doc, spreads, delta={"PEN_SPOT_ON": 0.02})
    on0 = float(state0.curves["PEN"].zero(0.0))
    assert h.loc["A01", "value_h"] + h.loc["A01", "flows"] == pytest.approx(150.0 * (1 + on0 + 0.01))


# --------------------------------------------------------------- 9. errores
def test_unknown_reference_factor_raises(doc, spreads):
    bad = copy.deepcopy(doc)
    for row in bad["instruments"] + bad["cashFlows"]:
        if row.get("instrument_id", row.get("id")) == "L01":
            row["reference_factor"] = "PEN_FWD_S9"
    with pytest.raises(ValueError, match="PEN_FWD_S9"):
        value_at_t0(bad, spreads)


# ----------------------------------------------------------------------- helpers
def _parallel(bp: float) -> dict:
    return {f"{c}_SPOT_{n}": bp for c in ("PEN", "USD") for n in ("ON", "1Y", "3Y", "5Y", "10Y", "20Y")}
