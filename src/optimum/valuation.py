"""(ii) Valorización de instrumentos desde flujos y curvas — independiente del optimizador.

Convenciones obligatorias (ver .claude/skills/valorizacion-flujos/SKILL.md):
- Bono fijo: flujos conocidos descontados con la spot de su moneda + spread de calibración.
- Flotante: cupón = forward del segmento de referencia + spread contractual; descuento spot + calibración.
- USD -> PEN con el FX del escenario.
- Nunca usar duración/DV01 como input: las sensibilidades salen de revalorizar.

Orden de desarrollo sugerido (Anexo 2, regla 4): bono fijo de pocos flujos -> flotante
con una sola forward -> portafolio completo -> test de calibración (V0 == monto de mercado).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from optimum.curves import ZeroCurve


@dataclass
class MarketState:
    """Estado de mercado en una fecha/escenario: curvas, forwards por segmento, FX y equity."""

    curves: dict[str, ZeroCurve]  # {"PEN": ..., "USD": ...}
    forwards: dict[str, dict[str, float]]  # {"PEN": {"S1": ..}, "USD": {...}}
    fx_penusd: float
    equity_index: float

    @classmethod
    def from_market_row(cls, row: pd.Series) -> MarketState:
        raise NotImplementedError


def price_fixed(cash_flows: pd.DataFrame, state: MarketState, valuation_date, calib_spread: float) -> float:
    """Valor en moneda nativa de un instrumento de tasa fija."""
    raise NotImplementedError


def price_floating(
    cash_flows: pd.DataFrame,
    state: MarketState,
    valuation_date,
    calib_spread: float,
    reference_factor: str,
    contract_spread: float,
) -> float:
    """Valor en moneda nativa de un instrumento flotante (reproyecta cupones con el escenario)."""
    raise NotImplementedError


def value_portfolio(
    instruments: pd.DataFrame,
    cash_flows: pd.DataFrame,
    state: MarketState,
    valuation_date,
    calib_spreads: dict[str, float],
) -> pd.Series:
    """Valor en PEN por instrumento (activos positivos; el signo de pasivos se decide en risk/optimizer)."""
    raise NotImplementedError


def calibrate_spread(instrument_id: str, target_value_pen: float, **kw) -> float:
    """Spread que iguala valor teórico = valor de mercado base (la hoja es solo referencia)."""
    raise NotImplementedError
