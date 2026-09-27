"""Rutas del proyecto. Todo el código usa estas constantes: nunca rutas relativas sueltas.

Funciona igual desde notebooks/, tests/ o la raíz, porque se ancla a la ubicación
de este archivo y no al directorio de trabajo.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "data"
RAW = DATA / "raw"  # insumos originales: SOLO LECTURA
INTERIM = DATA / "interim"  # hojas del Excel tal cual, ya legibles (parquet)
PROCESSED = DATA / "processed"  # tablas limpias y tipadas, listas para el modelo
JSON_DIR = DATA / "json"  # input.json / output.json del contrato (Anexo 1)

CONFIG = ROOT / "config"
NOTEBOOKS = ROOT / "notebooks"
DOCS = ROOT / "docs"

REPORT = ROOT / "informe_latex"
FIGURES = REPORT / "figures"  # las figuras viven junto al .tex (Docker solo monta informe_latex/)
TABLES = REPORT / "tables"

RAW_EXCEL = RAW / "Optimum_Investments_DatosCaso.xlsx"
INPUT_JSON = JSON_DIR / "input.json"
OUTPUT_JSON = JSON_DIR / "output.json"
CASE_CONFIG = CONFIG / "caso.yaml"


def ensure_dirs() -> None:
    """Crea las carpetas de salida si no existen (no toca data/raw)."""
    for d in (INTERIM, PROCESSED, JSON_DIR, FIGURES, TABLES):
        d.mkdir(parents=True, exist_ok=True)
