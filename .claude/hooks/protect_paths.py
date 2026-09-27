#!/usr/bin/env python3
"""PreToolUse (Edit|Write|MultiEdit|NotebookEdit|Bash): protege datos y artefactos generados.

- data/raw/**                 : insumo original, inmutable.
- data/interim|processed/**   : solo los genera `python -m optimum data`.
- data/json/*.json            : solo los genera el código (el caso prohíbe escribir en el output
                                datos no calculados).
- informe_latex/{figures,tables,out}/** : solo los generan save_fig/save_table/latexmk.
"""

import re
from fnmatch import fnmatch

from _common import block, read_input, rel

PROTECTED = {
    "data/raw/*": "data/raw es de solo lectura (insumo original del caso).",
    "data/interim/*": "data/interim se genera con `make data`; corrige src/optimum/io/excel.py.",
    "data/processed/*": "data/processed se genera con `make data`; corrige src/optimum/cleaning.py.",
    "data/json/*.json": "input/output.json los genera el código (`make json` / `make run`), no se editan a mano.",
    "informe_latex/figures/*": "Las figuras se generan con optimum.reporting.figures.save_fig().",
    "informe_latex/tables/*": "Las tablas se generan con optimum.reporting.tables.save_table().",
    "informe_latex/out/*": "Salida de latexmk; compila con `make report`.",
}
WRITE_CMD = re.compile(r"(\brm\b|\bmv\b|\bcp\b|\btruncate\b|sed\s+-i|>\s*|\btee\b|\bchmod\b)")

data = read_input()
tool = data.get("tool_name", "")
inp = data.get("tool_input", {})

if tool == "Bash":
    cmd = inp.get("command", "")
    if "data/raw" in cmd and WRITE_CMD.search(cmd):
        block(
            "Bloqueado: el comando parece modificar data/raw (inmutable). Lee el Excel con "
            "optimum.io.excel.load_workbook() y escribe resultados en data/interim o data/processed."
        )
    raise SystemExit(0)

path = inp.get("file_path") or inp.get("notebook_path") or ""
if path:
    r = rel(path)
    for pattern, why in PROTECTED.items():
        if fnmatch(r, pattern) and not r.endswith(".gitkeep"):
            block(f"Bloqueado: {r}. {why}")
