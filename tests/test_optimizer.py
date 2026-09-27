"""Pruebas mínimas exigidas por la Entrega (>= 5). Se activan al implementar optimizer.solve.

Cada una debe poder explicarse en el informe (sección Validación).
"""

import pytest

pytestmark = pytest.mark.skip(reason="TODO: activar cuando optimizer.solve esté implementado")


def test_simple_case_solvable_by_hand():
    """Problema reducido (2-3 instrumentos) con solución conocida analíticamente."""


def test_valuation_reproduces_base_market_value():
    """Con los spreads de calibración, V0 de cada instrumento == monto de mercado (±1e-6)."""


def test_extreme_rate_shock_moves_solution_sensibly():
    """+500 pb en tasas cortas: la solución debe moverse en la dirección financieramente esperada."""


def test_infeasible_constraints_reported():
    """Límites contradictorios (p. ej. PEN min 90 % y USD min 20 %) -> status INFEASIBLE, sin excepción."""


def test_all_constraints_satisfied_at_optimum():
    """Cada constraintCheck del output tiene ok == True con tolerancia 1e-6."""


def test_higher_risk_aversion_reduces_risk():
    """Aumentar lambda no debe aumentar la volatilidad/CVaR del patrimonio."""


def test_no_hardcoded_parameters():
    """Cambiar un límite en input.json cambia la solución (el optimizador no ignora el JSON)."""
