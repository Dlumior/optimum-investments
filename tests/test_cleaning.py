import numpy as np
import pandas as pd
import pytest

from optimum.cleaning import FACTORS, DataValidationError, clean_market_history, compute_factor_changes


def test_market_history_shape(tables):
    h = tables["market_history"]
    assert h.shape == (60, 24)
    assert list(h.columns) == FACTORS
    assert h.index.min().strftime("%Y-%m") == "2021-01"
    assert h.index.max().strftime("%Y-%m-%d") == "2025-12-31"


def test_base_date_matches_case_pdf(tables):
    """Anexo 1 muestra la fila 2025-12-31: PEN ON 4.03 %, FX 3.3574."""
    last = tables["market_history"].iloc[-1]
    assert last["PEN_SPOT_ON"] == pytest.approx(0.0403, abs=5e-5)
    assert last["FX_PENUSD"] == pytest.approx(3.3574, abs=5e-5)  # el PDF redondea a 4 decimales


def test_factor_changes_definition(tables):
    ours = compute_factor_changes(tables["market_history"])
    assert np.allclose(ours.values, tables["factor_changes"].values)


def test_duplicate_dates_rejected(raw):
    bad = raw["Historical_Market"].copy()
    bad.loc[1, "Date"] = bad.loc[0, "Date"]
    with pytest.raises(DataValidationError):
        clean_market_history(bad)


def test_rates_in_percent_rejected(raw):
    bad = raw["Historical_Market"].copy()
    bad["PEN_SPOT_1Y"] = bad["PEN_SPOT_1Y"] * 100
    with pytest.raises(DataValidationError):
        clean_market_history(bad)


def test_balance_totals(tables):
    inst = tables["instruments"]
    by_side = inst.groupby("side")["market_value_pen"].sum()
    assert by_side["ASSET"] == pytest.approx(1000.0)
    assert by_side["LIABILITY"] == pytest.approx(800.0)


def test_excel_covariance_is_singular(tables):
    """El caso advierte que SigmaF puede ser singular: el modelo debe tolerarlo."""
    w = np.linalg.eigvalsh(tables["covariance_excel"].values)
    assert w.min() < 1e-15


def test_stress_probabilities_not_hardcoded():
    """Auditoría final I-1: otras probabilidades de estrés no rompen la limpieza (la suma se valida en risk.py)."""
    from optimum.cleaning import clean_stress_scenarios

    raw = pd.DataFrame({"Scenario_ID": ["S1", "S2"], "Probability": [0.03, 0.04]})
    assert clean_stress_scenarios(raw)["probability"].sum() == pytest.approx(0.07)
    with pytest.raises(DataValidationError):
        clean_stress_scenarios(raw.assign(Probability=[-0.01, 0.04]))
