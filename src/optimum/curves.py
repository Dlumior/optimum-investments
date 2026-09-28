"""Curvas spot cero-cupón: convenciones del caso (sección "Información histórica").

- Tasas spot efectivas anuales; tiempo en años ACT/365 desde la fecha de valorización.
- Interpolación LINEAL de la tasa cero entre nodos; extrapolación plana fuera de [ON, 20Y].
- Nodo ON = plazo 0 años.
- Factor de descuento con spread de calibración s: DF(t) = (1 + z(t) + s) ** (-t).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

NODE_YEARS = {"ON": 0.0, "1Y": 1.0, "3Y": 3.0, "5Y": 5.0, "10Y": 10.0, "20Y": 20.0}
SEGMENT_BOUNDS = {
    "S1": ("ON", "1Y"),
    "S2": ("1Y", "3Y"),
    "S3": ("3Y", "5Y"),
    "S4": ("5Y", "10Y"),
    "S5": ("10Y", "20Y"),
}


def year_fraction(start, end) -> np.ndarray:
    """ACT/365 entre fechas (escalares, arrays, DatetimeIndex o pd.Series)."""
    delta = pd.to_datetime(end) - pd.Timestamp(start)
    days = np.asarray(pd.to_timedelta(delta) / pd.Timedelta(days=1), dtype=float)
    return days / 365.0


@dataclass(frozen=True)
class ZeroCurve:
    currency: str
    tenors: np.ndarray  # años, creciente
    rates: np.ndarray  # tasas efectivas anuales, decimales

    @classmethod
    def from_market_row(cls, row: pd.Series, currency: str) -> ZeroCurve:
        """Construye la curva desde una fila de market_history (p. ej. la del 2025-12-31)."""
        tenors = np.array(list(NODE_YEARS.values()))
        rates = np.array([row[f"{currency}_SPOT_{n}"] for n in NODE_YEARS], dtype=float)
        return cls(currency, tenors, rates)

    def zero(self, t) -> np.ndarray:
        return np.interp(np.asarray(t, dtype=float), self.tenors, self.rates)

    def discount(self, t, spread: float = 0.0) -> np.ndarray:
        t = np.asarray(t, dtype=float)
        return (1.0 + self.zero(t) + spread) ** (-t)

    def shifted(self, shifts) -> ZeroCurve:
        """Nueva curva con shocks por nodo (array de 6) o paralelo (escalar)."""
        return ZeroCurve(self.currency, self.tenors, self.rates + np.asarray(shifts, dtype=float))


def implied_forward(curve: ZeroCurve, t1: float, t2: float) -> float:
    """Forward efectiva anual implícita entre t1 y t2 (útil para chequear las FWD del Excel)."""
    g1 = (1 + curve.zero(t1)) ** t1
    g2 = (1 + curve.zero(t2)) ** t2
    return float((g2 / g1) ** (1.0 / (t2 - t1)) - 1.0)
