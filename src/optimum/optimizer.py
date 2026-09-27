"""(iv) Formulación y resolución del problema del caso asignado.

Regla de oro: `solve(doc)` recibe SOLO el dict de input.json. Ningún parámetro relevante
(límites, λ, α, costos, presupuestos) puede estar escrito aquí como constante.

Estructura sugerida:
    build_problem(doc)  -> variables, objetivo, restricciones (cvxpy)
    solve(doc)          -> dict con el contrato de output (Anexo 1.B)
    check_constraints() -> lista de {name, value, min, max, active, ok}
"""

from __future__ import annotations


def build_problem(doc: dict):
    raise NotImplementedError("Formular primero en docs/formulacion.md, luego implementar.")


def check_constraints(doc: dict, solution: dict) -> list[dict]:
    raise NotImplementedError


def solve(doc: dict) -> dict:
    """Devuelve el output v1.0: status, objectiveValue, valuation, metrics, riskModel,
    positions, weights, constraintChecks (+ diagnóstico del solver)."""
    raise NotImplementedError
