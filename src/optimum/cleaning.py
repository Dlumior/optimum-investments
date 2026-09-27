"""Limpieza: data/interim (hojas crudas) -> data/processed (tablas tipadas y validadas).

Reglas:
- No se inventan ni imputan valores. Si algo falla, se lanza `DataValidationError`.
- Nombres de columnas en snake_case; fechas como datetime; tasas en decimales (0.05 = 5 %).
- Cada función `clean_*` es pura (DataFrame -> DataFrame) para poder testearla.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from optimum import paths
from optimum.io.excel import load_workbook

RATE_NODES = ["ON", "1Y", "3Y", "5Y", "10Y", "20Y"]
SEGMENTS = ["S1", "S2", "S3", "S4", "S5"]
CURRENCIES = ["PEN", "USD"]

SPOT_FACTORS = [f"{c}_SPOT_{n}" for c in CURRENCIES for n in RATE_NODES]
FWD_FACTORS = [f"{c}_FWD_{s}" for c in CURRENCIES for s in SEGMENTS]
FACTORS = SPOT_FACTORS + FWD_FACTORS + ["FX_PENUSD", "EQUITY_USD"]  # 24 factores
RATE_FACTORS = SPOT_FACTORS + FWD_FACTORS  # cambian por diferencia absoluta
LOG_FACTORS = ["FX_PENUSD", "EQUITY_USD"]  # cambian por log-retorno


class DataValidationError(ValueError):
    pass


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise DataValidationError(msg)


def snake(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()  # sin tildes
    s = re.sub(r"\(.*?\)", "", s)  # quita "(S/ mm)" etc.
    s = s.replace("/", " ").replace("%", "pct").replace(".", " ")
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", s)
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_").lower()
    return s


def _snake_cols(df: pd.DataFrame, keep: set[str] = frozenset()) -> pd.DataFrame:
    return df.rename(columns={c: c if c in keep else snake(c) for c in df.columns})


# --------------------------------------------------------------------------- mercado
def clean_market_history(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    df.index.name = "date"
    _check(list(df.columns) == FACTORS, f"Columnas de mercado inesperadas: {list(df.columns)}")
    _check(df.index.is_unique, "Fechas duplicadas en Historical_Market")
    _check(bool((df.index == df.index + pd.offsets.MonthEnd(0)).all()), "Fechas que no son fin de mes")
    df = df.astype(float)
    _check(not df.isna().any().any(), "Valores faltantes en Historical_Market")
    _check(bool((df[RATE_FACTORS].abs() < 0.5).all().all()), "Tasas fuera de rango: ¿vienen en %?")
    _check(bool((df[LOG_FACTORS] > 0).all().all()), "FX/equity no positivos")
    return df


def compute_factor_changes(history: pd.DataFrame) -> pd.DataFrame:
    """Cambios mensuales: Δ absoluta en tasas, log-retorno en FX y equity."""
    out = history[RATE_FACTORS].diff()
    out[LOG_FACTORS] = np.log(history[LOG_FACTORS]).diff()
    return out[FACTORS].dropna()


def clean_factor_changes(df: pd.DataFrame, history: pd.DataFrame, tol: float = 1e-10) -> pd.DataFrame:
    """Usa la hoja del Excel pero verifica que coincide con nuestra propia derivación."""
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index().astype(float)
    df.index.name = "date"
    ours = compute_factor_changes(history)
    err = (df - ours).abs().max().max()
    _check(err < tol, f"Factor_Changes del Excel no coincide con la derivación (máx. dif. {err:.2e})")
    return df


def clean_square_matrix(df: pd.DataFrame) -> pd.DataFrame:
    m = df.set_index(df.columns[0]).astype(float)
    m.index.name = "factor"
    _check(list(m.index) == list(m.columns) == FACTORS, "Matriz sin el orden de factores esperado")
    _check(np.allclose(m.values, m.values.T, atol=1e-14), "Matriz no simétrica")
    return m


# ---------------------------------------------------------------------- instrumentos
def clean_instruments(df: pd.DataFrame) -> pd.DataFrame:
    df = _snake_cols(df).rename(
        columns={"position_pen_equiv": "market_value_pen", "notional_native": "notional_native"}
    )
    df["maturity"] = pd.to_datetime(df["maturity"])
    df["reset_months"] = df["reset_months"].astype("Int64")
    _check(df["id"].is_unique, "IDs de instrumento duplicados")
    refs = set(df["reference_factor"].dropna()) | set(df["other_market_ref"].dropna())
    _check(refs <= set(FACTORS), f"Factores de referencia no definidos: {refs - set(FACTORS)}")
    floating = df["instrument_type"].str.contains("FLOAT")
    _check(bool(df.loc[floating, "reference_factor"].notna().all()), "Flotante sin factor de referencia")
    return df.set_index("id")


def clean_cash_flows(df: pd.DataFrame, instruments: pd.DataFrame) -> pd.DataFrame:
    df = _snake_cols(df).rename(
        columns={"forward_ref_31_12_2025": "forward_ref_base", "notional_native": "notional_native"}
    )
    df["payment_date"] = pd.to_datetime(df["payment_date"])
    _check(set(df["instrument_id"]) <= set(instruments.index), "Flujos de instrumentos inexistentes")
    total = df["coupon_cash_flow"] + df["principal_cash_flow"]
    _check(bool(np.allclose(total, df["total_cash_flow"])), "cupón + principal != total")
    _check(not df.duplicated(["instrument_id", "period"]).any(), "Periodos duplicados")
    # el principal debe pagarse una sola vez, en la última fecha, por el nocional
    last = df.sort_values("period").groupby("instrument_id").tail(1).set_index("instrument_id")
    _check(
        bool(np.allclose(last["principal_cash_flow"], last["notional_native"])),
        "Principal al vencimiento distinto del nocional",
    )
    return df


def clean_factor_mapping(df: pd.DataFrame) -> pd.DataFrame:
    m = df.set_index("InstrumentID")[FACTORS].astype(int)
    m.index.name = "instrument_id"
    _check(bool(m.isin([0, 1]).all().all()), "La matriz de mapeo debe ser 0/1")
    return m


def clean_constraints(df: pd.DataFrame) -> pd.DataFrame:
    df = _snake_cols(df).rename(columns={"denominator_note": "note"})
    _check(bool((df["min_weight"] <= df["max_weight"]).all()), "Límite mínimo > máximo")
    return df


def clean_simple(df: pd.DataFrame) -> pd.DataFrame:
    return _snake_cols(df)


def clean_funding_alternatives(df: pd.DataFrame) -> pd.DataFrame:
    df = _snake_cols(df).rename(columns={"max_issue": "max_issue_pen"})
    df["maturity_date"] = pd.to_datetime(df["maturity_date"])
    df["reset_months"] = df["reset_months"].astype("Int64")
    return df.set_index("id")


def clean_case_assumptions(df: pd.DataFrame) -> pd.DataFrame:
    df = _snake_cols(df)
    df["value"] = df["value"].astype(str)  # mixto (fechas, números, listas): se tipa al usarlo
    return df


def split_scenario_tree(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """La hoja Scenario_Tree_D contiene dos tablas apiladas: transiciones y shocks."""
    cut = df.index[df["Current state"] == "State"][0]
    trans = df.loc[: cut - 1, ["Current state", "Code", "P(next T)", "P(next E)"]].copy()
    trans.columns = ["state", "code", "p_next_t", "p_next_e"]
    trans[["p_next_t", "p_next_e"]] = trans[["p_next_t", "p_next_e"]].astype(float)
    _check(np.allclose(trans["p_next_t"] + trans["p_next_e"], 1.0), "Probabilidades no suman 1")
    shocks = df.loc[cut + 1 :, ["Current state", "Code", "P(next T)", "P(next E)"]].copy()
    shocks.columns = ["state", "component", "shock", "interpretation"]
    shocks["shock"] = shocks["shock"].astype(float)
    return trans.reset_index(drop=True), shocks.reset_index(drop=True)


def clean_stress_scenarios(df: pd.DataFrame) -> pd.DataFrame:
    df = _snake_cols(df).rename(columns={"fx_pct": "fx_pct", "equity_pct": "equity_pct"})
    _check(abs(df["probability"].sum() - 0.05) < 1e-12, "Probabilidad conjunta de estrés != 5 %")
    return df.set_index("scenario_id")


# -------------------------------------------------------------------------- pipeline
def build_processed(raw: dict[str, pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    raw = raw if raw is not None else load_workbook()
    hist = clean_market_history(raw["Historical_Market"])
    inst = clean_instruments(raw["Instruments"])
    tree_trans, tree_shocks = split_scenario_tree(raw["Scenario_Tree_D"])
    return {
        "market_history": hist,
        "factor_changes": clean_factor_changes(raw["Factor_Changes"], hist),
        "covariance_excel": clean_square_matrix(raw["Covariance"]),
        "correlation_excel": clean_square_matrix(raw["Correlation"]),
        "curve_nodes": clean_simple(raw["Curve_Nodes"]),
        "curve_segments": clean_simple(raw["Curve_Segments"]),
        "instruments": inst,
        "cash_flows": clean_cash_flows(raw["Cash_Flows"], inst),
        "factor_mapping": clean_factor_mapping(raw["Factor_Mapping"]),
        "constraints": clean_constraints(raw["Constraints"]),
        "calibration_spreads": clean_simple(raw["Calibration_Spreads"]).set_index("instrument_id"),
        "funding_alternatives": clean_funding_alternatives(raw["Funding_Alternatives"]),
        "transaction_costs": clean_simple(raw["Transaction_Costs"]).set_index("instrument_id"),
        "case_assumptions": clean_case_assumptions(raw["Case_Assumptions"]),
        "stress_scenarios_c": clean_stress_scenarios(raw["Stress_Scenarios_C"]),
        "scenario_tree_d_transitions": tree_trans,
        "scenario_tree_d_shocks": tree_shocks,
    }


def save_processed(tables: dict[str, pd.DataFrame], out_dir: Path = paths.PROCESSED) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, df in tables.items():
        f = out_dir / f"{name}.parquet"
        df.to_parquet(f)
        written.append(f)
    return written


def load_processed(name: str) -> pd.DataFrame:
    """Atajo para notebooks: `load_processed("market_history")`."""
    f = paths.PROCESSED / f"{name}.parquet"
    if not f.exists():
        raise FileNotFoundError(f"{f} no existe: ejecuta `make data` primero")
    return pd.read_parquet(f)
