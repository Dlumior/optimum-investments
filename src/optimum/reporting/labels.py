"""Etiquetas en español para tablas y figuras del informe (los identificadores del JSON quedan en inglés)."""

from __future__ import annotations

SIDES = {"ASSET": "Activos", "LIABILITY": "Pasivos"}
DIMENSIONS = {
    "CURRENCY": "Moneda",
    "TYPE": "Tipo",
    "RATE_TYPE": "Tasa",
    "MATURITY": "Vencimiento",
    "CONCENTRATION": "Concentración",
}
CATEGORIES = {
    "CASH": "caja",
    "FIXED_INCOME": "renta fija",
    "EQUITY": "renta variable",
    "FIXED": "fija",
    "FLOAT": "flotante",
    "LE_12M": "≤ 12 meses",
    "GT_36M": "> 36 meses",
    "SINGLE_POSITION": "",
}
SCALARS = {
    "assetBudget": "Presupuesto de activos",
    "liabilityBudget": "Presupuesto de pasivos",
    "minCash": "Caja mínima",
    "minNetWorth": "PN mínimo",
    "maxLiabilitiesToAssets": "P/A máximo",
    "nonNegativity": "No negatividad",
}
COUPON_RULES = {"FLAT": "nivel plano", "PERIOD_FORWARD": "forward del período"}
HORIZON_MODES = {"ENFORCE": "vencimientos exigidos al horizonte", "REPORT": "vencimientos solo reportados"}


def constraint_label(name: str) -> str:
    """'ASSET:TYPE:FIXED_INCOME' → 'Activos · Tipo · renta fija'; 'LIABILITY:CONCENTRATION:SINGLE_POSITION:L01' →
    'Pasivos · Concentración · L01'; escalares ('minCash') → nombre en español. Categorías desconocidas quedan igual."""
    if name in SCALARS:
        return SCALARS[name]
    parts = name.split(":")
    if len(parts) < 2:
        return name
    out = [SIDES.get(parts[0], parts[0]), DIMENSIONS.get(parts[1], parts[1])]
    out += [CATEGORIES.get(p, p) for p in parts[2:]]
    return " · ".join(p for p in out if p)


def coupon_rule(rule: str) -> str:
    return COUPON_RULES.get(rule, rule)


def horizon_mode(mode: str) -> str:
    return HORIZON_MODES.get(mode, mode)
