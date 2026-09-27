---
name: auditar
description: Lanza una auditoría financiera independiente de un módulo o de los resultados. Invocar con /auditar [archivo o tema].
disable-model-invocation: true
---

Delega en el subagente `auditor-financiero` la revisión de: $ARGUMENTS
(si no se indica nada: `src/optimum/` completo y `data/json/output.json` si existe).

Cuando vuelva el informe del auditor: preséntalo al usuario tal cual, ordenado por severidad,
sin corregir nada todavía. Pregunta qué hallazgos corregir. Registra los hallazgos confirmados
como errores de IA en `docs/ia/registro_ia.md` (skill registro-ia).
