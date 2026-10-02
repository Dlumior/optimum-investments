"""Pruebas del notebook de entrega autocontenido (D-25).

1. El notebook versionado está al día con `src/optimum/` (se regenera en memoria y se comparan las fuentes).
2. `slow`: ejecutado en una carpeta aislada con una copia de input.json, produce el mismo output.json que
   `python -m optimum run` (salvo el tiempo del solver) e importa el modelo desde su paquete temporal, no desde src.
"""

import importlib.util
import json
import math

import nbformat
import pytest

from optimum import paths

SPEC = importlib.util.spec_from_file_location(
    "build_nb", paths.ROOT / "scripts" / "build_notebook_entrega.py"
)
build_nb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_nb)


def _sources(nb) -> list[tuple[str, str]]:
    return [(c.cell_type, c.source) for c in nb.cells]


def test_notebook_up_to_date_with_src():
    assert build_nb.OUT.exists(), "Falta el notebook: python scripts/build_notebook_entrega.py"
    on_disk = nbformat.read(build_nb.OUT, as_version=4)
    assert _sources(on_disk) == _sources(build_nb.build()), (
        "El notebook de entrega está desfasado de src/: python scripts/build_notebook_entrega.py"
    )


def test_notebook_has_no_project_imports():
    """El notebook no depende de rutas del repo: no usa `paths`, `load_processed` ni lee el Excel."""
    code = "\n".join(c.source for c in build_nb.build().cells if c.cell_type == "code")
    for banned in ["from optimum import paths", "load_processed", "data/raw", "openpyxl", "import yaml"]:
        assert banned not in code, banned


def _diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            yield from _diff(a.get(k), b.get(k), f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            yield from _diff(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        if not math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-8):
            yield path, a, b
    elif a != b:
        yield path, a, b


@pytest.mark.slow
def test_notebook_reproduces_output_json(tmp_path):
    from nbclient import NotebookClient

    (tmp_path / "input.json").write_bytes(paths.INPUT_JSON.read_bytes())
    nb = build_nb.build()
    NotebookClient(nb, timeout=1200, resources={"metadata": {"path": str(tmp_path)}}).execute()

    produced = json.loads((tmp_path / "output.json").read_text(encoding="utf-8"))
    expected = json.loads(paths.OUTPUT_JSON.read_text(encoding="utf-8"))
    diffs = [d for d in _diff(expected, produced) if not d[0].startswith(".solver.time")]
    assert diffs == [], f"output.json del notebook difiere de data/json/output.json: {diffs[:10]}"
