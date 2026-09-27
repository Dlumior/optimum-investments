#!/usr/bin/env python3
"""SessionStart: inyecta en el contexto el estado del proyecto (caso, pipeline, pendientes)."""

import re

from _common import ROOT

cfg = (ROOT / "config" / "caso.yaml").read_text(encoding="utf-8")
case = re.search(r'caseId:\s*"?(\w)"?', cfg)
case = case.group(1) if case else "?"


def ok(p):
    return "OK" if (ROOT / p).exists() else "FALTA"


todos = 0
for tex in (ROOT / "informe_latex").rglob("*.tex"):
    txt = tex.read_text(encoding="utf-8", errors="ignore")
    todos += txt.count("\\todo{") - txt.count("newcommand{\\todo}")
stubs = sum(
    f.read_text(encoding="utf-8").count("raise NotImplementedError")
    for f in (ROOT / "src" / "optimum").rglob("*.py")
)

print(f"""[Estado del proyecto Optimum Investments]
Caso asignado: {case}   (config/caso.yaml)
processed/: {ok("data/processed/market_history.parquet")} | input.json: {ok("data/json/input.json")} | output.json: {ok("data/json/output.json")} | informe PDF: {ok("informe_latex/out/main.pdf")}
Funciones pendientes (NotImplementedError): {stubs} | TODOs en el informe: {todos}
Formulación: docs/formulacion.md | Decisiones: docs/decisiones.md | Registro IA: docs/ia/registro_ia.md""")
