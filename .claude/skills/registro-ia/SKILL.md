---
name: registro-ia
description: Mantiene el registro de uso de IA exigido por la entrega (prompts principales, decisiones y errores de la IA corregidos). Úsalo al terminar una tarea relevante, cuando el usuario corrige una propuesta tuya, o cuando detectes un error o simplificación inadecuada en código generado.
---

# Registro de uso de IA

La entrega exige un anexo con prompts principales, decisiones tomadas con ayuda de IA y
**al menos dos errores/simplificaciones de la IA** que requirieron revisión humana.

## Fuentes
- `docs/ia/prompts.jsonl` — registro automático de TODOS los prompts (hook UserPromptSubmit). No editar.
- `docs/ia/registro_ia.md` — selección curada. Aquí escribes tú.
- `scripts/ia_log_to_tex.py` — convierte registro_ia.md → `informe_latex/appendices/B_prompts_generado.tex`.

## Cuándo añadir una entrada
- Al cerrar una etapa (parser, valorizador, riesgo, optimizador, output).
- Cuando el usuario rechaza o corrige tu propuesta → tipo **Corregido** o **Descartado**, con la causa.
- Cuando un test, el auditor o el usuario encuentran un error tuyo → también en la sección "Errores de la IA".

## Formato (respetarlo: el script lo parsea)
```
## P07 · 2026-10-02 · Valorizador flotante
**Prompt:** (resumen fiel del pedido del usuario)
**Resultado:** Aceptado | Corregido | Descartado
**Detalle:** qué se hizo / qué estaba mal / cómo se detectó / cómo se corrigió
```
Sé honesto: no minimizes errores propios. No inventes entradas que no ocurrieron.
