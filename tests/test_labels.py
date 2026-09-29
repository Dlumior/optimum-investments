"""Etiquetas en español del informe (reporting/labels.py)."""

from optimum.reporting.labels import constraint_label, coupon_rule


def test_constraint_labels():
    assert constraint_label("ASSET:TYPE:FIXED_INCOME") == "Activos · Tipo · renta fija"
    assert constraint_label("LIABILITY:CONCENTRATION:SINGLE_POSITION:L01") == "Pasivos · Concentración · L01"
    assert constraint_label("LIABILITY:MATURITY:LE_12M") == "Pasivos · Vencimiento · ≤ 12 meses"
    assert constraint_label("minCash") == "Caja mínima"


def test_unknown_labels_pass_through():
    """Datos nuevos del profesor (categorías o reglas no previstas) no rompen el reporte."""
    assert constraint_label("ASSET:SECTOR:MINING") == "Activos · SECTOR · MINING"
    assert constraint_label("otroLimite") == "otroLimite"
    assert coupon_rule("NUEVA") == "NUEVA"
