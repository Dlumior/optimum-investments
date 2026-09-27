"""docs/ia/registro_ia.md -> informe_latex/appendices/B_prompts_generado.tex"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "ia" / "registro_ia.md"
OUT = ROOT / "informe_latex" / "appendices" / "B_prompts_generado.tex"

ESC = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def esc(s: str) -> str:
    return "".join(ESC.get(c, c) for c in s)


text = re.sub(r"<!--.*?-->", "", SRC.read_text(encoding="utf-8"), flags=re.S)
entries = re.findall(r"^## (.+?)\n(.*?)(?=^## |^# |\Z)", text, flags=re.S | re.M)

lines = ["% Generado por scripts/ia_log_to_tex.py — no editar a mano", r"\begin{description}"]
for title, body in entries:
    fields = dict(re.findall(r"\*\*(\w+):\*\*\s*(.+)", body))
    lines.append(rf"\item[{esc(title.strip())}] \hfill\\")
    for key in ("Prompt", "Resultado", "Detalle"):
        if key in fields:
            lines.append(rf"\textit{{{key}:}} {esc(fields[key].strip())}\\")
lines.append(r"\end{description}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{len(entries)} entradas -> {OUT.relative_to(ROOT)}")
