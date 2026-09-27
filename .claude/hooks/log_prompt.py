#!/usr/bin/env python3
"""UserPromptSubmit: registra cada prompt en docs/ia/prompts.jsonl.

Es la materia prima del "Anexo de uso de IA" exigido por la entrega. La selección de
prompts principales y sus correcciones se documenta en docs/ia/registro_ia.md.
"""

import json
from datetime import datetime

from _common import ROOT, read_input

data = read_input()
prompt = data.get("prompt", "")
if prompt.strip():
    log = ROOT / "docs" / "ia" / "prompts.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "session": data.get("session_id", ""),
                    "prompt": prompt,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
