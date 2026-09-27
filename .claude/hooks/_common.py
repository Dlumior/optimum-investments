"""Utilidades compartidas por los hooks. Los hooks reciben un JSON por stdin.

Códigos de salida (Claude Code):
  0  -> continuar (stdout se muestra en modo verbose; en SessionStart/UserPromptSubmit se añade al contexto)
  2  -> bloquear / devolver feedback: stderr se le muestra a Claude
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))


def read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def rel(path: str) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def block(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(2)
