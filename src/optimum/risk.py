"""(iii) Factores, covarianzas y escenarios.

- 24 factores: 6 spot PEN, 5 fwd PEN, 6 spot USD, 5 fwd USD, FX_PENUSD, EQUITY_USD.
- Cambios: Δ absoluta en tasas, log-retorno en FX/equity (verificado contra Factor_Changes).
- SigmaF es singular (las forwards derivan de las spot): usar PCA/regularización para simular.
- Sensibilidades M por diferencias finitas sobre `valuation`; SigmaV = M SigmaF M^T.
- Alternativa: full revaluation aplicando cada cambio histórico a la curva de 2025-12-31.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def covariance(changes: pd.DataFrame, annualize: int = 12) -> pd.DataFrame:
    """Covarianza muestral de cambios mensuales, anualizada (x12) por defecto."""
    return changes.cov() * annualize


def nearest_psd(m: np.ndarray, eps: float = 0.0) -> np.ndarray:
    """Proyección a semidefinida positiva por recorte de autovalores."""
    m = (m + m.T) / 2
    w, v = np.linalg.eigh(m)
    return (v * np.clip(w, eps, None)) @ v.T


def pca(changes: pd.DataFrame, n_components: int | None = None):
    """Autovalores/autovectores de la covarianza; devuelve (varianza explicada, cargas)."""
    raise NotImplementedError


def sensitivities(value_fn, base_state, bump: float = 1e-4) -> pd.DataFrame:
    """Matriz M (instrumentos x factores) por diferencias finitas centrales."""
    raise NotImplementedError


def bootstrap_scenarios(
    changes: pd.DataFrame, n: int, horizon_months: int = 12, seed: int | None = None
) -> np.ndarray:
    """Escenarios a horizonte sumando bloques de cambios mensuales remuestreados."""
    raise NotImplementedError


def var_cvar(losses: np.ndarray, alpha: float = 0.95, probs: np.ndarray | None = None) -> tuple[float, float]:
    """VaR y CVaR de pérdidas (pérdida > 0), con probabilidades opcionales por escenario."""
    raise NotImplementedError
