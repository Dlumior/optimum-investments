"""(ii) Valorización de instrumentos desde flujos y curvas — independiente del optimizador.

Convenciones (docs/formulacion.md §7.4; decisiones D-10, D-12, D-13):
- Descuento: DF(t) = (1 + z(t) + s)^(-t), t en años ACT/365 desde la fecha de valorización; s = spread de
  calibración (constante, recalibrado para que V0 = market_value_pen).
- Fijo: flujos contractuales de cashFlows.
- Flotante (D-13): cupón = nivel del factor de referencia (p. ej. PEN_FWD_S2) en la fecha de fijación + spread
  contractual; monto = tasa × nocional / frecuencia. Fijación = pago − reset_months (fin de mes si el pago lo es).
  Los cupones fijados en t0 o antes conservan la proyección base.
- Forwards: siempre implícitas de la curva spot del estado (D-10), nunca shockeadas por separado.
- Trayectoria dentro del año (D-12): F(τ) = F0 + θΔ, θ = (τ − t0)/(tH − t0) acotado a [0, 1].
- Montos en moneda nativa hasta la conversión final a PEN con el FX del estado (soles por dólar).
- Nunca se usa duración/DV01: las sensibilidades salen de revalorizar.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from optimum.curves import NODE_YEARS, SEGMENT_BOUNDS, ZeroCurve, implied_forward, year_fraction

PAYMENTS_PER_YEAR = {"ANNUAL": 1, "SEMIANNUAL": 2, "QUARTERLY": 4, "MONTHLY": 12}
FX_FACTOR = "FX_PENUSD"
EQUITY_FACTOR = "EQUITY_USD"

MarketAt = Callable[[pd.Timestamp], "MarketState"]


# ------------------------------------------------------------------ estado de mercado
@dataclass(frozen=True)
class MarketState:
    """Estado de mercado: curvas spot por moneda, forwards implícitas por segmento, FX y equity."""

    curves: dict[str, ZeroCurve]  # {"PEN": ..., "USD": ...}; tasas efectivas anuales (decimales)
    forwards: dict[str, float]  # {"PEN_FWD_S1": ..., ...}; implícitas de `curves`
    fx_penusd: float  # soles por dólar
    equity_index: float  # nivel del índice (USD)

    @classmethod
    def from_curves(cls, curves: dict[str, ZeroCurve], fx_penusd: float, equity_index: float) -> MarketState:
        forwards = {
            f"{ccy}_FWD_{seg}": implied_forward(curve, NODE_YEARS[a], NODE_YEARS[b])
            for ccy, curve in curves.items()
            for seg, (a, b) in SEGMENT_BOUNDS.items()
        }
        return cls(curves, forwards, float(fx_penusd), float(equity_index))

    @classmethod
    def from_market_row(cls, row: Mapping) -> MarketState:
        """Desde una fila de `marketHistory` de input.json (spot por moneda y nodo, fx, equityIndex)."""
        tenors = np.array(list(NODE_YEARS.values()))
        curves = {
            ccy: ZeroCurve(ccy, tenors, np.array([nodes[n] for n in NODE_YEARS], dtype=float))
            for ccy, nodes in row["spot"].items()
        }
        return cls.from_curves(curves, row["fx"]["PENUSD"], row["equityIndex"])

    def shocked(self, delta: Mapping[str, float], theta: float = 1.0) -> MarketState:
        """Aplica θ·Δ: aditivo en nodos spot, multiplicativo e^(θΔ) en FX y equity (Δ = log-retorno).

        Los Δ de factores forward se ignoran: las forwards se recalculan desde la spot shockeada (D-10).
        """
        shifts = {ccy: np.zeros(len(NODE_YEARS)) for ccy in self.curves}
        fx, eq = self.fx_penusd, self.equity_index
        for name, d in delta.items():
            if name == FX_FACTOR:
                fx *= math.exp(theta * d)
            elif name == EQUITY_FACTOR:
                eq *= math.exp(theta * d)
            elif "_SPOT_" in name:
                ccy, node = name.split("_SPOT_")
                if ccy not in shifts or node not in NODE_YEARS:
                    raise ValueError(f"Factor spot desconocido: {name}")
                shifts[ccy][list(NODE_YEARS).index(node)] += theta * d
            elif "_FWD_" not in name:
                raise ValueError(f"Factor desconocido: {name}")
        curves = {ccy: c.shifted(shifts[ccy]) for ccy, c in self.curves.items()}
        return MarketState.from_curves(curves, fx, eq)

    def fx_to_pen(self, currency: str) -> float:
        if currency == "PEN":
            return 1.0
        if currency == "USD":
            return self.fx_penusd
        raise ValueError(f"Moneda no soportada: {currency}")


def market_path(state0: MarketState, delta: Mapping[str, float], t0, t_h) -> MarketAt:
    """Mercado en la fecha τ bajo la trayectoria lineal F0 + θ(τ)Δ, θ acotado a [0, 1] (D-12)."""
    t0, t_h = pd.Timestamp(t0), pd.Timestamp(t_h)
    span = float(year_fraction(t0, t_h))
    cache: dict[pd.Timestamp, MarketState] = {}

    def at(date) -> MarketState:
        date = pd.Timestamp(date)
        if date not in cache:
            theta = min(max(float(year_fraction(t0, date)) / span, 0.0), 1.0)
            cache[date] = state0.shocked(delta, theta)
        return cache[date]

    return at


# ------------------------------------------------------------------------ descuento
def present_value(flows: pd.DataFrame, curve: ZeroCurve, as_of, spread: float = 0.0) -> float:
    """Σ amount · (1 + z(t) + s)^(-t) sobre flujos con payment_date > as_of; t ACT/365 desde as_of.

    `flows`: columnas payment_date, amount (moneda nativa). Devuelve moneda nativa.
    """
    as_of = pd.Timestamp(as_of)
    dates = pd.to_datetime(flows["payment_date"])
    live = dates > as_of
    if not live.any():
        return 0.0
    t = year_fraction(as_of, dates[live])
    return float(np.sum(flows.loc[live, "amount"].to_numpy() * curve.discount(t, spread)))


# ------------------------------------------------------------------ cupones y flujos
def _fixing_date(payment: pd.Timestamp, months: int) -> pd.Timestamp:
    fix = payment - pd.DateOffset(months=months)
    return fix + pd.offsets.MonthEnd(0) if payment.is_month_end else fix


def coupon_rates(cf: pd.DataFrame, reset_months, t0, market_at: MarketAt) -> np.ndarray:
    """Tasa de cupón por período (decimal) de un instrumento, en el orden de `cf`.

    FIXED: tasa contractual. FLOAT: si la fijación es ≤ t0, la proyección base (ya fijada); si no,
    nivel del factor de referencia en `market_at(fijación)` + spread contractual (D-13).
    """
    t0 = pd.Timestamp(t0)
    rates = cf["projected_coupon_rate"].to_numpy(dtype=float).copy()
    is_float = (cf["coupon_type"] == "FLOAT").to_numpy()
    if not is_float.any():
        return rates
    if reset_months is None or pd.isna(reset_months):
        raise ValueError(f"Flotante sin reset_months: {cf['instrument_id'].iloc[0]}")
    for n in np.flatnonzero(is_float):
        row = cf.iloc[n]
        fix = _fixing_date(pd.Timestamp(row["payment_date"]), int(reset_months))
        if fix <= t0:
            continue
        state = market_at(fix)
        ref = row["reference_factor"]
        if ref not in state.forwards:
            raise ValueError(f"Factor de referencia desconocido {ref} en {row['instrument_id']}")
        rates[n] = state.forwards[ref] + float(row["spread"])
    return rates


def instrument_flows(inst: Mapping, cf: pd.DataFrame, t0, market_at: MarketAt) -> pd.DataFrame:
    """Flujos en moneda nativa (payment_date, amount): contractuales si es fijo, reproyectados si es flotante."""
    amount = cf["total_cash_flow"].to_numpy(dtype=float).copy()
    is_float = (cf["coupon_type"] == "FLOAT").to_numpy()
    if is_float.any():
        freq = PAYMENTS_PER_YEAR.get(inst["frequency"])
        if freq is None:
            raise ValueError(f"Frecuencia no soportada en {inst['id']}: {inst['frequency']}")
        rates = coupon_rates(cf, inst["reset_months"], t0, market_at)
        coupon = rates * cf["notional_native"].to_numpy(dtype=float) / freq
        amount[is_float] = coupon[is_float] + cf["principal_cash_flow"].to_numpy(dtype=float)[is_float]
    return pd.DataFrame({"payment_date": pd.to_datetime(cf["payment_date"]).to_numpy(), "amount": amount})


# ------------------------------------------------------------------- lectura del doc
def horizon_dates(doc: Mapping) -> tuple[pd.Timestamp, pd.Timestamp]:
    """(t0, tH): `valuationDate` y el horizonte (`caseParameters.horizonDate` o `horizonDate`)."""
    t_h = doc.get("caseParameters", {}).get("horizonDate") or doc["horizonDate"]
    return pd.Timestamp(doc["valuationDate"]), pd.Timestamp(t_h)


def base_state(doc: Mapping) -> MarketState:
    """Mercado en la fecha de valorización (fila de marketHistory con esa fecha)."""
    t0 = pd.Timestamp(doc["valuationDate"])
    rows = [r for r in doc["marketHistory"] if pd.Timestamp(r["date"]) == t0]
    if not rows:
        raise ValueError(f"marketHistory no tiene la fecha de valorización {t0.date()}")
    return MarketState.from_market_row(rows[0])


def _cash_flows_by_instrument(doc: Mapping) -> dict[str, pd.DataFrame]:
    cf = pd.DataFrame(doc["cashFlows"])
    cf["payment_date"] = pd.to_datetime(cf["payment_date"])
    return {
        iid: g.sort_values("payment_date").reset_index(drop=True) for iid, g in cf.groupby("instrument_id")
    }


def _is_flow_instrument(inst: Mapping, cfs: Mapping) -> bool:
    return inst["instrument_type"] not in ("CASH", "EQUITY") and inst["id"] in cfs


# ---------------------------------------------------------------------- calibración
SPREAD_BRACKET = (-0.05, 0.50)  # intervalo de búsqueda numérica del spread (no es un parámetro del caso)


def check_positive_values(doc: Mapping) -> None:
    """`market_value_pen` es a la vez precio de calibración y posición inicial: debe ser > 0 en todo instrumento."""
    bad = [i["id"] for i in doc["instruments"] if not float(i["market_value_pen"] or 0.0) > 0]
    if bad:
        raise ValueError(
            f"market_value_pen debe ser > 0 (se usa para calibrar el precio y como base de r): {', '.join(bad)}"
        )


def calibrate_spreads(doc: Mapping) -> dict[str, float]:
    """Spread (decimal) por instrumento con flujos tal que V0 · FX0 = market_value_pen (tolerancia 1e-12)."""
    check_positive_values(doc)
    t0, _ = horizon_dates(doc)
    state0 = base_state(doc)
    cfs = _cash_flows_by_instrument(doc)
    spreads = {}
    for inst in doc["instruments"]:
        if not _is_flow_instrument(inst, cfs):
            continue
        flows = instrument_flows(inst, cfs[inst["id"]], t0, lambda d: state0)
        curve, fx = state0.curves[inst["currency"]], state0.fx_to_pen(inst["currency"])
        target = float(inst["market_value_pen"])
        args = (flows, curve, t0, fx, target)
        lo, hi = SPREAD_BRACKET
        if _pricing_gap(lo, *args) * _pricing_gap(hi, *args) > 0:
            raise ValueError(
                f"No se puede calibrar {inst['id']}: el spread que da V0 = {target:,.2f} S/ mm está fuera de "
                f"[{lo:.0%}, {hi:.0%}]. Revisar market_value_pen y sus flujos."
            )
        spreads[inst["id"]] = brentq(_pricing_gap, lo, hi, args=args, xtol=1e-14)
    return spreads


def _pricing_gap(s: float, flows: pd.DataFrame, curve: ZeroCurve, t0, fx: float, target: float) -> float:
    return present_value(flows, curve, t0, s) * fx - target


# ---------------------------------------------------------------------- valorización
def value_at_t0(
    doc: Mapping, spreads: Mapping[str, float], delta: Mapping[str, float] | None = None
) -> pd.Series:
    """Valor en PEN (S/ mm) por instrumento en t0, con un shock instantáneo opcional Δ (sin trayectoria).

    Caja: nocional × FX. Equity: market_value_pen × (E/E0) × (FX/FX0 si es USD).
    """
    t0, _ = horizon_dates(doc)
    state0 = base_state(doc)
    state = state0.shocked(delta or {})
    cfs = _cash_flows_by_instrument(doc)
    values = {}
    for inst in doc["instruments"]:
        iid, ccy = inst["id"], inst["currency"]
        fx_ratio = state.fx_to_pen(ccy) / state0.fx_to_pen(ccy)
        if inst["instrument_type"] == "CASH":
            values[iid] = float(inst["market_value_pen"]) * fx_ratio
        elif inst["instrument_type"] == "EQUITY":
            values[iid] = (
                float(inst["market_value_pen"]) * state.equity_index / state0.equity_index * fx_ratio
            )
        elif iid in cfs:
            flows = instrument_flows(inst, cfs[iid], t0, lambda d: state)
            values[iid] = present_value(flows, state.curves[ccy], t0, spreads[iid]) * state.fx_to_pen(ccy)
        else:
            raise ValueError(f"Instrumento sin flujos ni tipo valorizable: {iid}")
    return pd.Series(values, name="value_pen")


def horizon_value_and_flows(
    doc: Mapping, spreads: Mapping[str, float], delta: Mapping[str, float]
) -> pd.DataFrame:
    """Por instrumento, en PEN (S/ mm), bajo la trayectoria lineal del escenario Δ (D-12):

    - value_h: valor en tH de los flujos posteriores a tH, con el mercado F(tH) + spread calibrado.
    - flows: flujos cobrados/pagados en (t0, tH], cada uno convertido con FX(τ_pago); sin reinversión.
    Caja: devenga ON0 + ½ΔON (tasa simple ACT/365) y se reporta en value_h. Equity: sin dividendos.
    """
    t0, t_h = horizon_dates(doc)
    state0 = base_state(doc)
    path = market_path(state0, delta, t0, t_h)
    state_h = path(t_h)
    tau = float(year_fraction(t0, t_h))
    cfs = _cash_flows_by_instrument(doc)
    rows = {}
    for inst in doc["instruments"]:
        iid, ccy = inst["id"], inst["currency"]
        if inst["instrument_type"] == "CASH":
            on0 = float(state0.curves[ccy].zero(0.0))
            accrued = 1.0 + (on0 + 0.5 * delta.get(f"{ccy}_SPOT_ON", 0.0)) * tau
            fx_ratio = state_h.fx_to_pen(ccy) / state0.fx_to_pen(ccy)
            rows[iid] = (float(inst["market_value_pen"]) * accrued * fx_ratio, 0.0)
        elif inst["instrument_type"] == "EQUITY":
            fx_ratio = state_h.fx_to_pen(ccy) / state0.fx_to_pen(ccy)
            growth = state_h.equity_index / state0.equity_index
            rows[iid] = (float(inst["market_value_pen"]) * growth * fx_ratio, 0.0)
        elif iid in cfs:
            flows = instrument_flows(inst, cfs[iid], t0, path)
            in_year = (flows["payment_date"] > t0) & (flows["payment_date"] <= t_h)
            received = sum(
                a * path(d).fx_to_pen(ccy)
                for d, a in flows.loc[in_year, ["payment_date", "amount"]].itertuples(index=False)
            )
            value_h = present_value(flows, state_h.curves[ccy], t_h, spreads[iid]) * state_h.fx_to_pen(ccy)
            rows[iid] = (value_h, float(received))
        else:
            raise ValueError(f"Instrumento sin flujos ni tipo valorizable: {iid}")
    return pd.DataFrame.from_dict(rows, orient="index", columns=["value_h", "flows"])
