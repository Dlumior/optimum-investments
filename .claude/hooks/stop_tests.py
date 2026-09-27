#!/usr/bin/env python3
"""Stop: si Claude cambió código Python desde el último test verde, corre pytest.

Si falla, devuelve el error (exit 2) para que Claude lo arregle antes de terminar.
Se desactiva creando el archivo .claude/.skip-stop-tests (útil mientras se escribe un
test que todavía debe fallar, TDD).
"""

import subprocess
import sys

from _common import ROOT, block, read_input

data = read_input()
if data.get("stop_hook_active"):  # evita bucles infinitos
    raise SystemExit(0)
if (ROOT / ".claude" / ".skip-stop-tests").exists():
    raise SystemExit(0)

stamp = ROOT / ".claude" / ".last-green-tests"
last = stamp.stat().st_mtime if stamp.exists() else 0.0
changed = [p for d in ("src", "tests") for p in (ROOT / d).rglob("*.py") if p.stat().st_mtime > last]
if not changed:
    raise SystemExit(0)

py = ROOT / ".venv" / "bin" / "python"
res = subprocess.run(
    [str(py) if py.exists() else sys.executable, "-m", "pytest", "-q", "-x", "--no-header"],
    cwd=ROOT,
    capture_output=True,
    text=True,
    timeout=300,
)
if res.returncode == 0:
    stamp.touch()
    raise SystemExit(0)
block(
    "Las pruebas fallan después de tus cambios. Corrígelas (o explica por qué el test está mal) "
    "antes de terminar:\n" + res.stdout[-4000:]
)
