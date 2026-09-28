"""Pruebas de la capa (iv) optimizador del Caso C (CVaR), escritas ANTES de la implementación.

Fuentes de verdad: docs/formulacion.md §4-§7.5, §9, §10; docs/decisiones.md D-08 (TC simétrico, fuera de L_s),
D-18 (caja al horizonte = CASH + flujos netos del año), D-19 (bloque `analysis` en output.json).

Estructura:
1. Juguete (rápido, resoluble a mano). Un `doc` mínimo con 2 activos (1 caja) y 1 pasivo, y componentes
   (reval, flows, escenarios) dados, para que `prepare` no revalorice. El pasivo único queda fijo en y = B_L, así
   que la decisión es una sola variable: la caja c ∈ [10, 60] (pesos CASH 10 %-60 % de B_A = 100); el bono es
   100 − c.

   Datos del juguete (decimal por S/ invertido; r = reval + flows):
       escenario  p      r_caja  r_bono  r_pasivo
       S1         0.40   0.03    0.08    0.03
       S2         0.30   0.03    0.06    0.03
       S3         0.20   0.03    0.04    0.03
       S4         0.06   0.03   -0.02    0.03
       S5 (estrés)0.04   0.03   -0.10    0.03
   x0 = (caja 30, bono 70, pasivo 80); costos c_caja = 0, c_bono = 0.002; α = 0.90.

   Con L_s = −ΔPN_s = 2.4 − 100 r_b,s − c (0.03 − r_b,s), el orden de pérdidas es S5 > S4 > S3 > S2 > S1 para todo
   c ∈ [10, 60], y la cola de 1 − α = 0.10 son exactamente S4 y S5 (0.06 + 0.04). Por eso:
       E[ΔPN](c)   = 2.88 − 0.0228 c
       CVaR_0.90(c) = (0.04 L5 + 0.06 L4) / 0.10 = 7.6 − 0.082 c
       TC(c)       = 0.002 |c − 30|
   Objetivo f(c) = E − λ CVaR − TC, lineal por tramos; pendientes −0.0208 + 0.082 λ (c < 30) y −0.0248 + 0.082 λ
   (c > 30). Entonces: λ < 0.2537 → c = 10; 0.2537 < λ < 0.3024 → c = 30 = x0 (TC = 0); λ > 0.3024 → c = 60.

2. Integración (input.json real, bootstrapCount = 100, marker `slow`): los componentes se calculan una vez por
   módulo y se comparten. Ninguna prueba usa ids fijos: todo se deriva de los atributos de `doc['instruments']`.

API supuesta (planificada, aún no implementada): ver el docstring de cada prueba. Se accede como `opt.<función>`
para que cada prueba falle por separado (AttributeError/NotImplementedError) mientras no exista.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd
import pytest

import optimum.optimizer as opt
import optimum.risk as risk
from optimum.cleaning import FACTORS
from optimum.io.json_contract import load_input, validate_output

TOL = 1e-6

# ============================================================================ juguete
TOY_PROBS = np.array([0.40, 0.30, 0.20, 0.06, 0.04])
TOY_SCEN = ["S1", "S2", "S3", "S4", "S5"]
TOY_KIND = ["bootstrap"] * 4 + ["stress"]
R_CASH = 0.03
R_BOND = np.array([0.08, 0.06, 0.04, -0.02, -0.10])
BOND_FLOWS = np.array([0.05, 0.05, 0.05, 0.05, 0.0])  # el bono no paga cupón en S5 (evento de crédito)
R_LIAB = 0.03
LIAB_FLOWS = 0.04


def _toy_doc(
    *,
    lam: float = 0.5,
    alpha: float = 0.90,
    cash_min: float = 0.10,
    cash_max: float = 0.60,
    bond_cost: float = 0.002,
    min_cash: float = 8.0,
    extra_weights: list[dict] | None = None,
) -> dict:
    """Doc mínimo con la forma de input.json (solo las claves que usa el optimizador)."""
    weights = [
        {
            "side": "ASSET",
            "dimension": "TYPE",
            "category": "CASH",
            "min_weight": cash_min,
            "max_weight": cash_max,
        },
        {
            "side": "ASSET",
            "dimension": "TYPE",
            "category": "FIXED_INCOME",
            "min_weight": 0.40,
            "max_weight": 0.90,
        },
        {"side": "ASSET", "dimension": "CURRENCY", "category": "PEN", "min_weight": 0.0, "max_weight": 1.0},
        {
            "side": "LIABILITY",
            "dimension": "CURRENCY",
            "category": "PEN",
            "min_weight": 0.0,
            "max_weight": 1.0,
        },
        {
            "side": "LIABILITY",
            "dimension": "RATE_TYPE",
            "category": "FIXED",
            "min_weight": 0.0,
            "max_weight": 1.0,
        },
    ] + list(extra_weights or [])
    for k, w in enumerate(weights):
        w.setdefault("index", k)
        w.setdefault("note", "")

    def inst(iid, side, typ, mv, maturity):
        return {
            "id": iid,
            "side": side,
            "name": iid,
            "instrument_type": typ,
            "currency": "PEN",
            "market_value_pen": mv,
            "notional_native": mv,
            "fixed_coupon": None,
            "frequency": None,
            "maturity": maturity,
            "reference_factor": None,
            "spread": None,
            "reset_months": None,
            "other_market_ref": None,
            "notes": "",
        }

    return {
        "schemaVersion": "1.0",
        "caseId": "C",
        "valuationDate": "2025-12-31",
        "horizonDate": "2026-12-31",
        "baseCurrency": "PEN",
        "instruments": [
            inst("C1", "ASSET", "CASH", 30.0, None),
            inst("B1", "ASSET", "BOND_FIXED", 70.0, "2030-12-31"),
            inst("L1", "LIABILITY", "BOND_FIXED", 80.0, "2030-12-31"),
        ],
        "constraints": {
            "weights": weights,
            "common": {
                "minNetWorth": 15.0,
                "maxLiabilitiesToAssets": 0.85,
                "minCash": min_cash,
                "assetBudget": 100.0,
                "liabilityBudget": 80.0,
                "allowShort": False,
            },
        },
        "transactionCosts": {
            "C1": {"side": "ASSET", "restructuring_cost": 0.0, "reduction_prepayment_cost": 0.0},
            "B1": {"side": "ASSET", "restructuring_cost": bond_cost, "reduction_prepayment_cost": 0.0},
            "L1": {"side": "LIABILITY", "restructuring_cost": 0.01, "reduction_prepayment_cost": 0.01},
        },
        "fundingAlternatives": [],
        "stressScenarios": [],
        "caseParameters": {
            "horizonDate": "2026-12-31",
            "cvarAlpha": alpha,
            "riskAversionLambda": lam,
            "lambdaGrid": [0.0, 0.1, 0.28, 0.5, 1.0, 5.0],
            "riskMeasure": "CVAR",
            "bootstrapCount": 4,
            "bootstrapProbability": 0.96,
            "stressProbability": 0.04,
            "seed": 1,
        },
    }


def _toy_components():
    """(reval, flows, ScenarioSet) del juguete; reval + flows = tabla del docstring del módulo."""
    ids = ["C1", "B1", "L1"]
    reval = pd.DataFrame(
        [np.full(5, R_CASH), R_BOND - BOND_FLOWS, np.full(5, R_LIAB - LIAB_FLOWS)],
        index=ids,
        columns=TOY_SCEN,
    )
    flows = pd.DataFrame([np.zeros(5), BOND_FLOWS, np.full(5, LIAB_FLOWS)], index=ids, columns=TOY_SCEN)
    scen = risk.ScenarioSet(
        ids=list(TOY_SCEN),
        deltas=pd.DataFrame(0.0, index=TOY_SCEN, columns=FACTORS),
        probs=TOY_PROBS.copy(),
        kind=list(TOY_KIND),
    )
    return reval, flows, scen


def _toy_data(**kw):
    return opt.prepare(_toy_doc(**kw), components=_toy_components())


def _toy_dpn(c: float) -> np.ndarray:
    """ΔPN_s a mano para caja c, bono 100 − c, pasivo 80."""
    return c * R_CASH + (100 - c) * R_BOND - 80 * R_LIAB


def _toy_hand(c: float, alpha: float = 0.90) -> dict:
    """E[ΔPN], CVaR (con risk.var_cvar, ya validado en test_risk) y TC a mano para la caja c."""
    dpn = _toy_dpn(c)
    _, cvar = risk.var_cvar(-dpn, alpha, TOY_PROBS)
    return {"E": float(TOY_PROBS @ dpn), "cvar": cvar, "tc": 0.002 * abs(c - 30)}


def _cash(pos: pd.Series) -> float:
    return float(pos["C1"])


def _checks(obj) -> list[dict]:
    """Normaliza constraintChecks (lista de dicts o dict nombre → dict) a lista."""
    return list(obj.values()) if isinstance(obj, dict) else list(obj)


# ------------------------------------------------------------------- juguete: pruebas
def test_toy_prepare_builds_problem_data():
    """`prepare` con componentes dados no revaloriza y arma los datos del problema desde el doc.

    Verifica: ids y lados de `instruments`; x0 = market_value_pen; returns = reval + flows; probabilidades, tipo de
    escenario, α y λ de `caseParameters`; costos = restructuring_cost (D-08: no se usa reduction_prepayment_cost).
    """
    data = _toy_data()
    assert list(data.ids) == ["C1", "B1", "L1"]
    assert data.side.to_dict() == {"C1": "ASSET", "B1": "ASSET", "L1": "LIABILITY"}
    assert data.x0.to_dict() == pytest.approx({"C1": 30.0, "B1": 70.0, "L1": 80.0})
    reval, flows, _ = _toy_components()
    assert np.allclose(data.returns.loc[reval.index, reval.columns], reval + flows, atol=1e-15)
    assert np.allclose(data.probs, TOY_PROBS)
    assert list(data.scenario_kind) == TOY_KIND
    assert data.alpha == pytest.approx(0.90)
    assert data.lam == pytest.approx(0.5)
    assert data.cost.to_dict() == pytest.approx({"C1": 0.0, "B1": 0.002, "L1": 0.01})


def test_toy_solution_by_hand():
    """Solución analítica del juguete con λ = 0.5 (valor de `riskAversionLambda` del doc de juguete).

    Pendiente del objetivo para c > 30: −0.0248 + 0.082·0.5 = +0.0162 > 0 ⇒ c* = 60 (cota CASH ≤ 60 %).
    Posiciones: caja 60, bono 40, pasivo 80.
    E[ΔPN] = 2.88 − 0.0228·60 = 1.512; CVaR_0.90 = 7.6 − 0.082·60 = 2.68
    (pérdidas L5 = 4.6, L4 = 1.4: (0.04·4.6 + 0.06·1.4)/0.10 = 2.68); TC = 0.002·30 = 0.06.
    Objetivo = 1.512 − 0.5·2.68 − 0.06 = 0.112. Tolerancia 1e-6.
    """
    res = opt.solve_data(_toy_data())
    assert res["status"] == "OPTIMAL"
    pos = res["positions"]
    assert pos["C1"] == pytest.approx(60.0, abs=TOL)
    assert pos["B1"] == pytest.approx(40.0, abs=TOL)
    assert pos["L1"] == pytest.approx(80.0, abs=TOL)
    assert res["objective"] == pytest.approx(0.112, abs=TOL)
    assert res["cvar_lp"] == pytest.approx(2.68, abs=TOL)
    assert res["transaction_cost"] == pytest.approx(0.06, abs=TOL)


def test_toy_evaluate_metrics_by_hand():
    """`evaluate` sobre la posición caja 10, bono 90, pasivo 80 (independiente del solver).

    ΔPN_s = 0.3 + 90 r_b,s − 2.4 = (5.1, 3.3, 1.5, −3.9, −11.1).
    E[ΔPN] = 0.4·5.1 + 0.3·3.3 + 0.2·1.5 − 0.06·3.9 − 0.04·11.1 = 2.652.
    VaR_0.90 = pérdida de S3 = −1.5 (P(L ≤ −1.5) = 0.90). CVaR_0.90 = (0.06·3.9 + 0.04·11.1)/0.10 = 6.78.
    Volatilidad = √(Σ p_s (ΔPN_s − E)²) con las probabilidades p_s (varianza poblacional ponderada) = √12.928896.
    Pérdida en el estrés S5 = 11.1. TC = 0.002·|90 − 70| = 0.04.
    """
    data = _toy_data()
    pos = pd.Series({"C1": 10.0, "B1": 90.0, "L1": 80.0})
    ev = opt.evaluate(data, pos)
    dpn = np.array([5.1, 3.3, 1.5, -3.9, -11.1])
    assert ev["expected_pnl"] == pytest.approx(2.652, abs=TOL)
    assert ev["var"] == pytest.approx(-1.5, abs=TOL)
    assert ev["cvar"] == pytest.approx(6.78, abs=TOL)
    assert ev["volatility"] == pytest.approx(math.sqrt(TOY_PROBS @ (dpn - 2.652) ** 2), abs=TOL)
    assert ev["volatility"] == pytest.approx(math.sqrt(12.928896), abs=TOL)
    assert ev["stress_losses"] == pytest.approx({"S5": 11.1}, abs=TOL)
    assert ev["transaction_cost"] == pytest.approx(0.04, abs=TOL)


def test_toy_horizon_breaches_by_hand():
    """Incumplimientos al horizonte (§7.5, D-18): se reportan, no se imponen. Posición caja 10, bono 90, pasivo 80.

    Umbrales del doc de juguete: minNetWorth = 15, maxLiabilitiesToAssets = 0.85, minCash = 8.
    - caja_T = 10·1.03 + 90·F_b,s − 80·0.04 − TC (D-18: TC se paga con caja en t0)
      = (11.56, 11.56, 11.56, 11.56, 7.06): solo S5 < 8 (el bono no paga en S5).
    - PN_T = PN0 − TC + ΔPN = 20 − 0.04 + (5.1, 3.3, 1.5, −3.9, −11.1) = (25.06, 23.26, 21.46, 16.06, 8.86): solo S5.
    - L_T = 80·(1 − 0.01) = 79.2; A_T = bono 90·(1 + reval_b) + caja_T = (104.26, 102.46, 100.66, 95.26, 88.06)
      = PN_T + L_T (el balance cuadra); P/A_T = (0.760, 0.773, 0.787, 0.831, 0.899): solo S5 > 0.85.
    Cada incumplimiento: conteo 1 y probabilidad 0.04.

    Supuesto de API: `horizon_breaches` usa como claves los nombres de `constraints.common`
    (minNetWorth, maxLiabilitiesToAssets, minCash), cada una con {'count', 'probability'}.
    """
    data = _toy_data()
    ev = opt.evaluate(data, pd.Series({"C1": 10.0, "B1": 90.0, "L1": 80.0}))
    hb = ev["horizon_breaches"]
    for key in ("minNetWorth", "maxLiabilitiesToAssets", "minCash"):
        assert hb[key]["count"] == 1, key
        assert hb[key]["probability"] == pytest.approx(0.04, abs=1e-12), key


@pytest.mark.parametrize("max_weight, breached", [(0.25, True), (1.0, False)])
def test_toy_horizon_le12m_breach_is_deterministic(max_weight, breached):
    """LE_12M al horizonte (§7.5, D-18): un pasivo que vence entre 12 y 24 meses desde t0 no está en LE_12M en t0,
    pero sí en t_H. Es determinista: se reporta con probabilidad 1 (todos los escenarios) o 0.

    L1 vence el 2027-06-30: 18 m desde t0 (grupo LE_12M vacío en t0, sin min_weight ⇒ válido) y 6 m desde t_H.
    Con y_L1 = 80 = 100 % de B_L: incumple si max_weight = 0.25, cumple si max_weight = 1.0.

    Los grupos del Cuadro 4 al horizonte se reportan con el nombre del grupo como clave (D-20), con {'count',
    'probability', 'cause'}. La causa es "estructural" porque el grupo se incumple aun con los montos de t0 (la
    pertenencia cambia por el paso del tiempo), no por el mercado.
    """
    doc = _le12m_toy_doc(max_weight)
    data = opt.prepare(doc, components=_toy_components())
    hb = opt.evaluate(data, pd.Series({"C1": 10.0, "B1": 90.0, "L1": 80.0}))["horizon_breaches"]
    entry = hb["LIABILITY:MATURITY:LE_12M"]
    assert entry["count"] == (len(TOY_SCEN) if breached else 0)
    assert entry["probability"] == pytest.approx(1.0 if breached else 0.0, abs=1e-12)
    if breached:
        assert entry["cause"] == "estructural"


def _le12m_toy_doc(max_weight: float, **kw) -> dict:
    """Juguete con un grupo LE_12M de pasivos y L1 venciendo el 2027-06-30 (18 m desde t0, 6 m desde t_H)."""
    le12 = {
        "side": "LIABILITY",
        "dimension": "MATURITY",
        "category": "LE_12M",
        "min_weight": 0.0,
        "max_weight": max_weight,
    }
    doc = _toy_doc(extra_weights=[le12], **kw)
    next(i for i in doc["instruments"] if i["id"] == "L1")["maturity"] = "2027-06-30"
    return doc


def test_toy_horizon_weight_drift_by_hand():
    """Todos los grupos del Cuadro 4 se revisan al horizonte con valores en t_H (auditoría I-2, D-20).

    Posición caja 10, bono 90, pasivo 80 (TC = 0.04). Con D-18:
    - caja_T = (11.56, 11.56, 11.56, 11.56, 7.06);
    - bono_T = 90·(1 + r_b − F_b) = (92.7, 90.9, 89.1, 83.7, 81.0);
    - A_T = (104.26, 102.46, 100.66, 95.26, 88.06).
    Peso de caja en t_H = (0.1109, 0.1128, 0.1148, 0.1214, 0.0802): solo S5 < 10 % ⇒ conteo 1, probabilidad 0.04.
    Con los montos de t0 la caja pesa 10/100 = 10 %, dentro del límite ⇒ la causa es "mercado".
    """
    data = _toy_data()
    hb = opt.evaluate(data, pd.Series({"C1": 10.0, "B1": 90.0, "L1": 80.0}))["horizon_breaches"]
    entry = hb["ASSET:TYPE:CASH"]
    assert entry["count"] == 1
    assert entry["probability"] == pytest.approx(0.04, abs=1e-12)
    assert entry["cause"] == "mercado"
    assert entry["worst"] == pytest.approx(7.06 / 88.06, abs=1e-9)
    assert {g["name"] for g in data.groups} <= set(hb)


def test_toy_maturity_uses_calendar_months():
    """Plazos por meses calendario (auditoría, menor 1): un pasivo que vence exactamente 36 meses después de t_H
    no está en GT_36M al horizonte, aunque 1461/365·12 = 48.03 > 36 lo metería con la regla días/365 desde t0.

    L1 vence el 2029-12-31: 48 meses desde t0 (GT_36M en t0) y 36 desde t_H (fuera de GT_36M en t_H).
    """
    gt36 = {
        "side": "LIABILITY",
        "dimension": "MATURITY",
        "category": "GT_36M",
        "min_weight": 0.0,
        "max_weight": 1.0,
    }
    doc = _toy_doc(extra_weights=[gt36])
    next(i for i in doc["instruments"] if i["id"] == "L1")["maturity"] = "2029-12-31"
    data = opt.prepare(doc, components=_toy_components())
    at_t0 = next(g for g in data.groups if g["name"] == "LIABILITY:MATURITY:GT_36M")
    at_th = next(g for g in data.horizon_groups if g["name"] == "LIABILITY:MATURITY:GT_36M")
    assert at_t0["members"] == ["L1"]
    assert at_th["members"] == []


def test_toy_enforce_horizon_maturity():
    """`caseParameters.horizonMaturityLimits` = ENFORCE impone los grupos MATURITY medidos desde t_H (D-20).

    En el juguete el único pasivo (L1, 80 = 100 % de B_L) entra en LE_12M al horizonte: con máx 25 % y ENFORCE el
    problema es infactible; con REPORT (lectura literal del enunciado) es óptimo y solo se reporta.
    """
    doc = _le12m_toy_doc(0.25)
    doc["caseParameters"]["horizonMaturityLimits"] = "REPORT"
    assert opt.solve_data(opt.prepare(doc, components=_toy_components()))["status"] == "OPTIMAL"
    doc["caseParameters"]["horizonMaturityLimits"] = "ENFORCE"
    assert opt.solve_data(opt.prepare(doc, components=_toy_components()))["status"] == "INFEASIBLE"


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda d: d["transactionCosts"]["B1"].update(restructuring_cost=-0.01), "restructuring_cost"),
        (lambda d: d["caseParameters"].update(cvarAlpha=1.0), "cvarAlpha"),
        (lambda d: d["caseParameters"].update(riskAversionLambda=-0.1), "riskAversionLambda"),
        (lambda d: d["caseParameters"].update(horizonMaturityLimits="MAYBE"), "horizonMaturityLimits"),
        (lambda d: d["instruments"][1].update(instrument_type="BOND_ZERO"), "TYPE"),
    ],
)
def test_toy_invalid_parameters_raise(mutate, match):
    """Parámetros inválidos fallan en `prepare` con un mensaje claro (auditoría, menores 2 y 5): costo < 0, α fuera
    de (0, 1), λ < 0, modo de vencimientos desconocido y un activo sin categoría TYPE cuando hay límites TYPE."""
    doc = _toy_doc()
    mutate(doc)
    with pytest.raises(ValueError, match=match):
        opt.prepare(doc, components=_toy_components())


def test_toy_lambda_zero_is_expected_value_corner():
    """λ = 0: el objetivo es solo E[ΔPN] − TC (§9.2) y la solución es de esquina.

    Pendientes de E − TC: −0.0208 (c < 30) y −0.0248 (c > 30) ⇒ c* = 10 (mínimo de caja, 10 %).
    Se compara además con enumeración de c en una grilla fina de [10, 60]: el objetivo del solver iguala al máximo
    enumerado 2.88 − 0.228 − 0.04 = 2.612.
    """
    res = opt.solve_data(_toy_data(), lam=0.0)
    assert res["status"] == "OPTIMAL"
    assert _cash(res["positions"]) == pytest.approx(10.0, abs=TOL)
    grid = np.linspace(10, 60, 501)
    best = max(_toy_hand(c)["E"] - _toy_hand(c)["tc"] for c in grid)
    assert best == pytest.approx(2.612, abs=1e-9)
    assert res["objective"] == pytest.approx(best, abs=TOL)


def test_toy_large_lambda_reaches_min_cvar():
    """λ grande (5): el CVaR de la solución es el mínimo alcanzable en la región factible.

    CVaR(c) = 7.6 − 0.082 c es decreciente ⇒ mínimo en c = 60: 2.68. Se verifica contra la enumeración de c en
    [10, 60] con `risk.var_cvar` (independiente del LP).
    """
    res = opt.solve_data(_toy_data(), lam=5.0)
    ev = opt.evaluate(_toy_data(), res["positions"])
    min_cvar = min(_toy_hand(c)["cvar"] for c in np.linspace(10, 60, 501))
    assert min_cvar == pytest.approx(2.68, abs=1e-9)
    assert ev["cvar"] == pytest.approx(min_cvar, abs=TOL)


@pytest.mark.parametrize("alpha", [0.90, 0.92])
@pytest.mark.parametrize("lam", [0.1, 0.25, 0.5, 2.0])
def test_toy_lp_cvar_equals_ex_post(alpha, lam):
    """Para λ > 0, el CVaR del LP (ζ + Σ p u / (1 − α)) coincide con el ex post de `evaluate` (tol 1e-6), §5.

    α = 0.90: la cola (0.10) coincide con S4 + S5 (cuantil en el borde de un átomo).
    α = 0.92: la cola (0.08) toma todo S5 (0.04) y 0.04 de los 0.06 de S4: el VaR cae dentro de un átomo y el CVaR
    usa el átomo fraccional: CVaR = (L5 + L4)/2 = 8.4 − 0.09 c. Con α = 0.92 y λ = 0.25 la pendiente es
    +0.0017 a la izquierda de 30 y −0.0023 a la derecha ⇒ c* = 30 y CVaR = 5.7 (se verifica también a mano).
    """
    data = _toy_data(alpha=alpha)
    res = opt.solve_data(data, lam=lam)
    ev = opt.evaluate(data, res["positions"])
    assert res["cvar_lp"] == pytest.approx(ev["cvar"], abs=TOL)
    c = _cash(res["positions"])
    assert ev["cvar"] == pytest.approx(_toy_hand(c, alpha)["cvar"], abs=TOL)
    if alpha == 0.92 and lam == 0.25:
        assert c == pytest.approx(30.0, abs=TOL)
        assert ev["cvar"] == pytest.approx(5.7, abs=TOL)


def test_toy_objective_identity():
    """El objetivo reportado es E[ΔPN] − λ·CVaR − TC evaluado en la solución (λ > 0, §5): 0.112 con λ = 0.5."""
    data = _toy_data()
    res = opt.solve_data(data)
    ev = opt.evaluate(data, res["positions"])
    assert res["objective"] == pytest.approx(
        ev["expected_pnl"] - 0.5 * ev["cvar"] - ev["transaction_cost"], abs=TOL
    )


def test_toy_zero_turnover_has_zero_cost():
    """Si la solución es x0, TC = 0 (D-08).

    (a) λ = 0.28 ∈ (0.2537, 0.3024): la pendiente es +0.00216 a la izquierda de 30 y −0.00184 a la derecha ⇒
        c* = 30 = x0 sin costos extremos.
    (b) Costo del bono = 10 por S/ (prohibitivo) con λ = 0.5: mover 1 S/ cuesta más de lo que mejora ⇒ c* = 30.
    """
    for kw, lam in (({}, 0.28), ({"bond_cost": 10.0}, 0.5)):
        data = _toy_data(**kw)
        res = opt.solve_data(data, lam=lam)
        assert res["positions"].to_dict() == pytest.approx(data.x0.to_dict(), abs=TOL)
        assert res["transaction_cost"] == pytest.approx(0.0, abs=TOL)
        assert opt.evaluate(data, res["positions"])["transaction_cost"] == pytest.approx(0.0, abs=TOL)


def test_toy_zero_cost_rotates_more():
    """Con c = 0 hay tanta o más rotación que con c > 0 (§10).

    λ = 0.28: con c_bono = 0.002 la solución es x0 (rotación 0); con c = 0 la pendiente es −0.0228 + 0.082·0.28 =
    +0.00016 > 0 ⇒ c* = 60, rotación Σ|x − x0| = 30 + 30 = 60.
    """
    rot = {}
    for cost in (0.002, 0.0):
        data = _toy_data(bond_cost=cost)
        pos = opt.solve_data(data, lam=0.28)["positions"]
        rot[cost] = float((pos - data.x0).abs().sum())
    assert rot[0.002] == pytest.approx(0.0, abs=TOL)
    assert rot[0.0] == pytest.approx(60.0, abs=TOL)
    assert rot[0.0] >= rot[0.002] - TOL


def test_toy_lambda_monotonicity():
    """Más aversión ⇒ CVaR no mayor y E[ΔPN] − TC no mayor (§9.1).

    Es un teorema de preferencia revelada para max f − λ g: si λ2 > λ1, (λ2 − λ1)(g(z1) − g(z2)) ≥ 0. Con
    f = E − TC y g = CVaR, lo garantizado es que CVaR y E − TC no crecen; E sola puede subir si TC baja. En el
    juguete: c* = 10, 10, 30, 60, 60, 60 para λ = 0, 0.1, 0.28, 0.5, 1, 5.
    """
    data = _toy_data()
    cash, cvar, net = [], [], []
    for lam in _toy_doc()["caseParameters"]["lambdaGrid"]:
        pos = opt.solve_data(data, lam=lam)["positions"]
        ev = opt.evaluate(data, pos)
        cash.append(_cash(pos))
        cvar.append(ev["cvar"])
        net.append(ev["expected_pnl"] - ev["transaction_cost"])
    assert cash == pytest.approx([10, 10, 30, 60, 60, 60], abs=TOL)
    assert all(b <= a + TOL for a, b in zip(cvar, cvar[1:], strict=False))
    assert all(b <= a + TOL for a, b in zip(net, net[1:], strict=False))


def test_toy_budgets_and_nonnegativity():
    """Σx = B_A = 100, Σy = B_L = 80 y posiciones ≥ 0 (allowShort = False) para toda λ de la grilla."""
    data = _toy_data()
    for lam in (0.0, 0.1, 0.28, 0.5, 5.0):
        pos = opt.solve_data(data, lam=lam)["positions"]
        assert pos[["C1", "B1"]].sum() == pytest.approx(100.0, abs=TOL)
        assert pos["L1"] == pytest.approx(80.0, abs=TOL)
        assert (pos >= -TOL).all()


def test_toy_constraint_checks_ok_and_active():
    """`check_constraints` en el óptimo: todo ok; con λ = 0 hay al menos una restricción activa (esquina c = 10:
    CASH mínimo) y toda restricción marcada activa está en una de sus cotas."""
    data = _toy_data()
    pos = opt.solve_data(data, lam=0.0)["positions"]
    checks = opt.check_constraints(data, pos)
    assert checks, "check_constraints no devolvió restricciones"
    for ch in checks:
        assert set(ch) >= {"name", "value", "min", "max", "active", "ok"}
        assert ch["ok"], ch
    active = [ch for ch in checks if ch["active"]]
    assert active
    for ch in active:
        at_min = ch["min"] is not None and abs(ch["value"] - ch["min"]) <= 1e-6 * max(1.0, abs(ch["min"]))
        at_max = ch["max"] is not None and abs(ch["value"] - ch["max"]) <= 1e-6 * max(1.0, abs(ch["max"]))
        assert at_min or at_max, ch


def test_toy_infeasible_min_cash_above_cash_max():
    """minCash = 70 > máximo de caja (60 % de 100 = 60): status INFEASIBLE, sin excepción y sin posiciones (§10)."""
    res = opt.solve_data(_toy_data(min_cash=70.0))
    assert res["status"] == "INFEASIBLE"
    assert res["positions"] is None


def test_toy_empty_group_with_min_weight_raises():
    """Un grupo sin miembros con min_weight > 0 (pasivos USD ≥ 20 %, sin pasivos USD) es un error de datos:
    `prepare` lanza ValueError con un mensaje que nombra la categoría (§6, Validación)."""
    extra = [
        {
            "side": "LIABILITY",
            "dimension": "CURRENCY",
            "category": "USD",
            "min_weight": 0.2,
            "max_weight": 0.5,
        }
    ]
    with pytest.raises(ValueError, match="USD"):
        _toy_data(extra_weights=extra)


def test_toy_empty_group_with_zero_min_is_accepted():
    """El mismo grupo vacío con min_weight = 0 no es error (es no vinculante, como LE_12M en el caso real)."""
    extra = [
        {
            "side": "LIABILITY",
            "dimension": "CURRENCY",
            "category": "USD",
            "min_weight": 0.0,
            "max_weight": 0.5,
        }
    ]
    res = opt.solve_data(_toy_data(extra_weights=extra))
    assert res["status"] == "OPTIMAL"


def test_toy_no_hardcoded_parameters():
    """Cambiar datos del doc cambia la solución: el optimizador lee límite, λ y costos del input (regla de oro 2).

    - Mínimo de caja 10 % → 20 % con λ = 0: c* pasa de 10 a 20.
    - riskAversionLambda 0.5 → 0.1 (sin pasar `lam`): c* pasa de 60 a 10.
    - Costo del bono 0.002 → 0 con λ = 0.28: c* pasa de 30 a 60.
    """
    assert _cash(opt.solve_data(_toy_data(), lam=0.0)["positions"]) == pytest.approx(10.0, abs=TOL)
    assert _cash(opt.solve_data(_toy_data(cash_min=0.20), lam=0.0)["positions"]) == pytest.approx(
        20.0, abs=TOL
    )
    assert _cash(opt.solve_data(_toy_data(lam=0.5))["positions"]) == pytest.approx(60.0, abs=TOL)
    assert _cash(opt.solve_data(_toy_data(lam=0.1))["positions"]) == pytest.approx(10.0, abs=TOL)
    assert _cash(opt.solve_data(_toy_data(bond_cost=0.0), lam=0.28)["positions"]) == pytest.approx(
        60.0, abs=TOL
    )


@pytest.mark.parametrize("lam", [0.1, 0.5])
def test_toy_mean_variance_benchmark(lam):
    """Benchmark media-varianza (§9.3): min Var(ΔPN) s.a. E[ΔPN] − TC ≥ E*, con E* = E − TC de la solución CVaR.

    Var(ΔPN)(c) = Var(a + c b) con b_s = 0.03 − r_b,s; su mínimo libre está en c = 100, así que en [10, 60] la
    varianza decrece en c. E − TC es decreciente en c, y la restricción E − TC ≥ E* obliga a c ≤ c*_CVaR:
    λ = 0.1 → c*_CVaR = 10, E* = 2.612 ⇒ MV también c = 10. λ = 0.5 → c*_CVaR = 60, E* = 1.452 ⇒ MV c = 60.
    En general: Var_MV ≤ Var_CVaR y E_MV − TC_MV ≥ E*.
    """
    data = _toy_data()
    cv = opt.solve_data(data, lam=lam)
    ev_cv = opt.evaluate(data, cv["positions"])
    e_star = ev_cv["expected_pnl"] - ev_cv["transaction_cost"]
    mv = opt.solve_data(data, mode="variance", min_net_return=e_star)
    assert mv["status"] == "OPTIMAL"
    ev_mv = opt.evaluate(data, mv["positions"])
    assert ev_mv["volatility"] ** 2 <= ev_cv["volatility"] ** 2 + TOL
    assert ev_mv["expected_pnl"] - ev_mv["transaction_cost"] >= e_star - TOL
    assert _cash(mv["positions"]) == pytest.approx(10.0 if lam == 0.1 else 60.0, abs=1e-4)


# ======================================================================== integración
def _inst_df(doc) -> pd.DataFrame:
    return pd.DataFrame(doc["instruments"]).set_index("id")


def _with(doc, fn):
    d = copy.deepcopy(doc)
    fn(d)
    return d


def _set_weight(doc, side, dimension, category, **vals):
    rows = [
        w
        for w in doc["constraints"]["weights"]
        if (w["side"], w["dimension"], w["category"]) == (side, dimension, category)
    ]
    assert rows, f"no existe el grupo {side}/{dimension}/{category} en input.json"
    for w in rows:
        w.update(vals)


def _short_segments(doc) -> set[str]:
    """Segmentos de forward contenidos en el tramo corto del estrés (`stressTenors.short.nodes`), p. ej. S1."""
    short = set(doc["caseParameters"]["stressTenors"]["short"]["nodes"])
    return {s["id"] for s in doc["curveSegments"] if s["fromNode"] in short and s["toNode"] in short}


def _short_indexed(doc) -> pd.Series:
    """True si el instrumento es caja o su cupón se indexa a un segmento del tramo corto (por atributos)."""
    segs = _short_segments(doc)
    inst = _inst_df(doc)
    ref_seg = inst["reference_factor"].map(lambda r: r.split("_")[-1] if isinstance(r, str) else None)
    return (inst["instrument_type"] == "CASH") | ref_seg.isin(segs)


@pytest.fixture(scope="module")
def doc():
    """input.json real con bootstrapCount = 100 (mínimo del enunciado) para acotar el tiempo."""
    d = copy.deepcopy(load_input())
    d["caseParameters"]["bootstrapCount"] = 100
    return d


@pytest.fixture(scope="module")
def scenarios(doc):
    return risk.build_scenarios(doc)


@pytest.fixture(scope="module")
def components(doc, scenarios):
    """(reval, flows, escenarios) calculados una sola vez (~10 s) y compartidos por las pruebas del módulo."""
    reval, flows = risk.scenario_components(doc, scenarios.deltas)
    return reval, flows, scenarios


@pytest.fixture(scope="module")
def data(doc, components):
    return opt.prepare(doc, components=components)


@pytest.fixture(scope="module")
def ref(data):
    """Solución de referencia: λ = riskAversionLambda del input."""
    return opt.solve_data(data)


@pytest.fixture(scope="module")
def output(doc, components):
    return opt.solve(doc, components=components)


@pytest.mark.slow
def test_real_prepare_matches_doc(doc, data, components):
    """`prepare` toma todo del doc: ids de `instruments`, x0 = market_value_pen, p_s del ScenarioSet, α y λ de
    caseParameters, y returns = reval + flows."""
    inst = _inst_df(doc)
    assert set(data.ids) == set(inst.index)
    assert data.x0.reindex(inst.index).to_numpy() == pytest.approx(inst["market_value_pen"].to_numpy())
    assert data.side.reindex(inst.index).tolist() == inst["side"].tolist()
    assert np.allclose(data.probs, components[2].probs)
    assert data.alpha == pytest.approx(doc["caseParameters"]["cvarAlpha"])
    assert data.lam == pytest.approx(doc["caseParameters"]["riskAversionLambda"])
    reval, flows, _ = components
    assert np.allclose(data.returns.loc[reval.index, reval.columns], reval + flows, atol=1e-15)


@pytest.mark.slow
def test_real_group_membership_by_attributes(doc, data):
    """Pertenencia de grupos por atributos (§6), nunca por id.

    - MATURITY GT_36M (pasivos): plazo remanente a t0 > 36 meses según `maturity`.
    - CONCENTRATION SINGLE_POSITION: una restricción de un solo miembro por instrumento del lado.
    Supuesto de API: cada grupo expone `side` y `members` (dict o atributo).
    """

    def get(g, k):
        return g[k] if isinstance(g, dict) else getattr(g, k)

    inst = _inst_df(doc)
    t0 = pd.Timestamp(doc["valuationDate"])
    liab = inst[inst["side"] == "LIABILITY"]
    months = (pd.to_datetime(liab["maturity"]) - t0).dt.days / 365 * 12
    gt36 = set(liab.index[months > 36])
    member_sets = [(get(g, "side"), frozenset(get(g, "members"))) for g in data.groups]
    assert ("LIABILITY", frozenset(gt36)) in member_sets
    for side in ("ASSET", "LIABILITY"):
        for iid in inst.index[inst["side"] == side]:
            assert (side, frozenset({iid})) in member_sets, f"falta SINGLE_POSITION de {iid}"


@pytest.mark.slow
def test_real_empty_group_with_min_weight_raises(doc, components):
    """LE_12M de pasivos está vacío con los datos actuales (ningún pasivo vence ≤ 12 m desde t0, §6). Si se le exige
    min_weight = 0.10, `prepare` debe fallar con ValueError claro, no resolver en silencio."""
    bad = _with(doc, lambda d: _set_weight(d, "LIABILITY", "MATURITY", "LE_12M", min_weight=0.10))
    with pytest.raises(ValueError, match="LE_12M"):
        opt.prepare(bad, components=components)


@pytest.mark.slow
def test_real_solve_output_contract(doc, output):
    """`solve` produce output v1.0 válido (Anexo 1): pasa `validate_output`, status OPTIMAL, todos los
    constraintChecks ok, y el bloque `analysis` (D-19) con posición inicial, barrido de λ (una entrada por λ de
    `lambdaGrid`) y benchmark media-varianza."""
    assert validate_output(output) == []
    assert output["status"] == "OPTIMAL"
    assert output["caseId"] == doc["caseId"]
    checks = _checks(output["constraintChecks"])
    assert checks
    assert all(ch["ok"] for ch in checks), [ch for ch in checks if not ch["ok"]]
    an = output["analysis"]
    assert {"initialPosition", "lambdaSweep", "meanVarianceBenchmark"} <= set(an)
    assert len(an["lambdaSweep"]) == len(doc["caseParameters"]["lambdaGrid"])


@pytest.mark.slow
def test_real_budgets_nonnegative_and_checks(doc, data, ref):
    """Solución de referencia: Σx = assetBudget, Σy = liabilityBudget, posiciones ≥ 0 y `check_constraints` ok."""
    assert ref["status"] == "OPTIMAL"
    pos = ref["positions"]
    com = doc["constraints"]["common"]
    side = data.side.reindex(pos.index)
    assert pos[side == "ASSET"].sum() == pytest.approx(com["assetBudget"], abs=TOL)
    assert pos[side == "LIABILITY"].sum() == pytest.approx(com["liabilityBudget"], abs=TOL)
    assert (pos >= -TOL).all()
    checks = opt.check_constraints(data, pos)
    assert all(ch["ok"] for ch in checks), [ch for ch in checks if not ch["ok"]]


@pytest.mark.slow
def test_real_lp_cvar_equals_ex_post(data, ref):
    """Con λ = riskAversionLambda > 0, el CVaR del LP coincide con el ex post (átomos de 0.0095 y 0.0125, con
    100 escenarios bootstrap y 4 de estrés; la masa de estrés es exactamente 1 − α)."""
    assert data.lam > 0
    ev = opt.evaluate(data, ref["positions"])
    assert ref["cvar_lp"] == pytest.approx(ev["cvar"], rel=TOL, abs=TOL)
    assert ref["objective"] == pytest.approx(
        ev["expected_pnl"] - data.lam * ev["cvar"] - ev["transaction_cost"], rel=TOL, abs=TOL
    )


@pytest.mark.slow
def test_real_lambda_monotonicity(doc, data):
    """En la grilla `lambdaGrid`: CVaR no creciente y E[ΔPN] − TC no creciente (preferencia revelada, §9.1).

    Se prueba E − TC (lo que garantiza la teoría) y no E sola: con costos de transacción, E puede subir si el TC baja.
    """
    cvar, net = [], []
    for lam in doc["caseParameters"]["lambdaGrid"]:
        res = opt.solve_data(data, lam=lam)
        assert res["status"] == "OPTIMAL"
        ev = opt.evaluate(data, res["positions"])
        cvar.append(ev["cvar"])
        net.append(ev["expected_pnl"] - ev["transaction_cost"])
    assert all(b <= a + 1e-5 for a, b in zip(cvar, cvar[1:], strict=False)), cvar
    assert all(b <= a + 1e-5 for a, b in zip(net, net[1:], strict=False)), net


@pytest.mark.slow
def test_real_no_hardcoded_parameters(doc, components, data, ref):
    """Cambiar datos de input.json cambia la solución (regla de oro 2):

    - Concentración máxima de activos 35 % → 30 %: ninguna posición de activo supera 0.30·B_A y la solución
      cambia (con 35 % la referencia tiene posiciones en el tope, verificado con un LP independiente).
    - riskAversionLambda 0.25 → 5: la solución cambia (sin pasar `lam` a solve_data).
    - restructuring_cost = 0 en todos: la rotación Σ|x − x0| no es menor que con los costos del input.
    """
    b_a = doc["constraints"]["common"]["assetBudget"]
    d1 = _with(doc, lambda d: _set_weight(d, "ASSET", "CONCENTRATION", "SINGLE_POSITION", max_weight=0.30))
    r1 = opt.solve_data(opt.prepare(d1, components=components))
    assets = data.side[data.side == "ASSET"].index
    assert r1["positions"][assets].max() <= 0.30 * b_a + TOL
    assert (r1["positions"] - ref["positions"]).abs().max() > 1.0

    d2 = _with(doc, lambda d: d["caseParameters"].update(riskAversionLambda=5.0))
    r2 = opt.solve_data(opt.prepare(d2, components=components))
    assert (r2["positions"] - ref["positions"]).abs().max() > 1.0

    def zero_costs(d):
        for v in d["transactionCosts"].values():
            v["restructuring_cost"] = 0.0

    data3 = opt.prepare(_with(doc, zero_costs), components=components)
    r3 = opt.solve_data(data3)
    assert r3["transaction_cost"] == pytest.approx(0.0, abs=TOL)
    rot = float((r3["positions"] - data.x0).abs().sum())
    rot_ref = float((ref["positions"] - data.x0).abs().sum())
    assert rot >= rot_ref - TOL


@pytest.mark.slow
@pytest.mark.parametrize(
    "case",
    ["equity_max_below_implied_floor", "min_cash_above_cash_max", "currency_mins_sum_over_one"],
)
def test_real_infeasible_reported_without_exception(doc, components, case):
    """Límites contradictorios ⇒ `solve` devuelve status INFEASIBLE, sin lanzar excepción, y un output que pasa
    `validate_output` (§10):

    - equity máx. 3 % < piso implícito 5 % (caja ≤ 20 % y renta fija ≤ 75 % ⇒ equity ≥ 5 %);
    - minCash = 1.25 × (máx. de caja · B_A) > máximo de caja (250 > 200 con los datos actuales);
    - activos PEN ≥ 90 % y USD ≥ 20 % (suman 110 %).
    """
    com = doc["constraints"]["common"]
    cash_max = next(
        w["max_weight"]
        for w in doc["constraints"]["weights"]
        if (w["side"], w["dimension"], w["category"]) == ("ASSET", "TYPE", "CASH")
    )

    def mutate(d):
        if case == "equity_max_below_implied_floor":
            _set_weight(d, "ASSET", "TYPE", "EQUITY", max_weight=0.03)
        elif case == "min_cash_above_cash_max":
            d["constraints"]["common"]["minCash"] = 1.25 * cash_max * com["assetBudget"]
        else:
            _set_weight(d, "ASSET", "CURRENCY", "PEN", min_weight=0.90)
            _set_weight(d, "ASSET", "CURRENCY", "USD", min_weight=0.20)

    bad = _with(doc, mutate)
    assert opt.solve_data(opt.prepare(bad, components=components))["status"] == "INFEASIBLE"
    out = opt.solve(bad, components=components)
    assert out["status"] == "INFEASIBLE"
    assert validate_output(out) == []


@pytest.mark.slow
def test_real_mean_variance_benchmark(data, ref):
    """Media-varianza con el mismo retorno neto (§9.3): con E* = E − TC de la solución CVaR de referencia, el QP
    min Var(ΔPN) s.a. E − TC ≥ E* es factible (la solución CVaR lo cumple), su varianza no supera la de la solución
    CVaR y cumple E − TC ≥ E*."""
    ev_cv = opt.evaluate(data, ref["positions"])
    e_star = ev_cv["expected_pnl"] - ev_cv["transaction_cost"]
    mv = opt.solve_data(data, mode="variance", min_net_return=e_star)
    assert mv["status"] == "OPTIMAL"
    ev_mv = opt.evaluate(data, mv["positions"])
    assert ev_mv["volatility"] ** 2 <= ev_cv["volatility"] ** 2 * (1 + 1e-6) + TOL
    assert ev_mv["expected_pnl"] - ev_mv["transaction_cost"] >= e_star - 1e-5


@pytest.mark.slow
def test_real_reference_beats_initial_position(data, ref):
    """La solución de referencia no empeora el objetivo E − λ·CVaR − TC frente a la posición inicial (TC = 0).

    Advertencia: x0 es infactible (equity 22 % > 20 %, §6), así que no es un teorema del LP; es un control de
    sensatez. Con los datos actuales la brecha es amplia (≈ +1.6 vs ≈ −7.5 con un LP independiente y 100
    escenarios). Si falla, revisar el signo de los pasivos o la definición del objetivo antes que el umbral.
    """
    ev0 = opt.evaluate(data, data.x0)
    assert ev0["transaction_cost"] == pytest.approx(0.0, abs=TOL)
    obj0 = ev0["expected_pnl"] - data.lam * ev0["cvar"]
    assert ref["objective"] >= obj0 - TOL


@pytest.mark.slow
def test_real_extreme_short_rate_shock_moves_solution(doc, scenarios, components, data, ref):
    """Shock extremo: +500 pb en los nodos cortos (ON y 1Y) de PEN y USD, sumado en todos los escenarios.

    Dirección esperada. El shock sube la tasa corta en todos los escenarios, así que:
    - la caja devenga ON0 + ½ΔON: +2.5 pp de rendimiento sin riesgo adicional (D-12);
    - los cupones indexados al segmento corto (S1: ON-1Y) suben, en el año y (D-13) en toda su vida, así que un
      activo S1 rinde más y un pasivo S1 cuesta más;
    - en cambio, la forward S2 (1Y-3Y) baja (la spot 1Y sube y la 3Y no), así que los indexados a S2 no cuentan como
      "cortos".
    Se espera que la exposición neta a la tasa corta (caja + activos S1 − pasivos S1, identificados por
    `instrument_type` y `reference_factor` contra `stressTenors.short` y `curveSegments`) aumente al menos 1 S/ mm, y
    que ni los activos cortos bajen ni los pasivos cortos suban. Con un LP independiente: activos cortos 440 → 550
    y pasivos cortos 330 → 0 (λ = 0.25).
    """
    short_factors = [
        f
        for f in FACTORS
        if "_SPOT_" in f and f.split("_SPOT_")[1] in doc["caseParameters"]["stressTenors"]["short"]["nodes"]
    ]
    assert len(short_factors) == 4  # ON y 1Y de PEN y USD
    deltas = scenarios.deltas.copy()
    deltas[short_factors] += 0.05
    reval_s, flows_s = risk.scenario_components(doc, deltas)
    scen_s = risk.ScenarioSet(scenarios.ids, deltas, scenarios.probs, scenarios.kind)
    shocked = opt.solve_data(opt.prepare(doc, components=(reval_s, flows_s, scen_s)))
    assert shocked["status"] == "OPTIMAL"

    short = _short_indexed(doc)
    side = data.side

    def agg(pos, s):
        idx = short[short & (side.reindex(short.index) == s)].index
        return float(pos.reindex(idx).sum())

    base_a, base_l = agg(ref["positions"], "ASSET"), agg(ref["positions"], "LIABILITY")
    shk_a, shk_l = agg(shocked["positions"], "ASSET"), agg(shocked["positions"], "LIABILITY")
    assert shk_a >= base_a - TOL
    assert shk_l <= base_l + TOL
    assert (shk_a - shk_l) >= (base_a - base_l) + 1.0


@pytest.mark.slow
def test_real_out_of_sample_light(doc, data, ref):
    """Fuera de muestra (§9.4): `out_of_sample` evalúa la solución con escenarios de otra semilla. Prueba ligera:
    devuelve las métricas de `evaluate`, finitas, con CVaR ≥ VaR, y distintas de las de la muestra (otra muestra)."""
    seed = int(doc["caseParameters"]["seed"]) + 1
    oos = opt.out_of_sample(doc, ref["positions"], seed)
    ins = opt.evaluate(data, ref["positions"])
    for k in ("expected_pnl", "var", "cvar", "volatility"):
        assert math.isfinite(oos[k]), k
    assert oos["cvar"] >= oos["var"] - TOL
    assert oos["expected_pnl"] != pytest.approx(ins["expected_pnl"], abs=1e-9)


@pytest.mark.slow
def test_real_horizon_reports_every_weight_group(data, ref):
    """Al horizonte se reportan todos los grupos del Cuadro 4 (auditoría I-2), cada uno con su causa."""
    hb = opt.evaluate(data, ref["positions"])["horizon_breaches"]
    for g in data.groups:
        assert g["name"] in hb, g["name"]
        assert hb[g["name"]]["cause"] in {"estructural", "mercado", None}
        assert 0.0 <= hb[g["name"]]["probability"] <= 1.0 + 1e-12


@pytest.mark.slow
def test_real_horizon_maturity_variant(doc, components, data, output):
    """Variante de vencimientos al horizonte (D-20): `analysis.horizonMaturityVariant` resuelve con el modo opuesto
    al del input. Con la base REPORT, la variante ENFORCE respeta cada grupo MATURITY medido desde t_H (con montos
    de t0) y no mejora el objetivo de la base (tiene más restricciones)."""
    assert doc["caseParameters"].get("horizonMaturityLimits", "REPORT") == "REPORT"
    var = output["analysis"]["horizonMaturityVariant"]
    assert var["mode"] == "ENFORCE"
    assert var["status"] == "OPTIMAL"
    assert var["objective"] <= output["objectiveValue"] + TOL
    assert var["objectiveCost"] == pytest.approx(output["objectiveValue"] - var["objective"], abs=1e-9)
    pos = pd.Series(var["positions"])
    liabs = pos[data.side.reindex(pos.index) == "LIABILITY"].sum()
    for g in data.horizon_groups:
        if g["dimension"] != "MATURITY":
            continue
        w = pos.reindex(g["members"]).sum() / liabs if g["side"] == "LIABILITY" else None
        if w is not None:
            assert g["min"] - TOL <= w <= g["max"] + TOL, g["name"]
