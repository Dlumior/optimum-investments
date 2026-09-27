#!/usr/bin/env python3
"""PostToolUse (Edit|Write|MultiEdit): formatea con ruff y devuelve a Claude los errores que queden."""

import shutil
import subprocess

from _common import ROOT, block, read_input

data = read_input()
path = (data.get("tool_input") or {}).get("file_path", "")
if not path.endswith(".py"):
    raise SystemExit(0)

venv_ruff = ROOT / ".venv" / "bin" / "ruff"
ruff = str(venv_ruff) if venv_ruff.exists() else shutil.which("ruff")
if not ruff:
    raise SystemExit(0)

subprocess.run([ruff, "format", "-q", path], cwd=ROOT)
res = subprocess.run([ruff, "check", "--fix", "-q", path], cwd=ROOT, capture_output=True, text=True)
if res.returncode != 0:
    block(f"ruff encontró problemas en {path}:\n{res.stdout[-3000:]}")
