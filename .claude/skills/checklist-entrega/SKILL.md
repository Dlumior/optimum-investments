---
name: checklist-entrega
description: Verifica los entregables contra los requisitos y la rúbrica del caso antes de generar el ZIP. Invocar con /checklist-entrega.
disable-model-invocation: true
---

Revisa cada punto con evidencia (archivo/comando), marca ✅/❌ y di qué falta:

**Entregables**
- [ ] Código fuente reproducible (`make setup all` desde cero funciona).
- [ ] `data/json/input.json` conforme al Anexo 1 (validate_input sin errores).
- [ ] `data/json/output.json` generado por el programa (status, métricas, posiciones, pesos, constraintChecks, riskModel).
- [ ] ≥ 5 pruebas automáticas activas: caso simple, cambio extremo de tasas, restricciones infactibles (+2).
- [ ] Informe ≤ 12 páginas de cuerpo, sin `\todo`, compila con `make report`.
- [ ] Anexo IA: prompts principales, decisiones, ≥ 2 errores de IA corregidos.
- [ ] Instrucciones de ejecución (Anexo A y README).

**Rúbrica (20 pts)**: formulación (5) · implementación y restricciones (5) · validación/sensibilidad (4) ·
calidad técnica y reproducibilidad (3) · interpretación y uso crítico de IA (3). Para cada criterio indica
el punto más débil actual.

**Requisitos técnicos**: sin parámetros codificados en el optimizador; sin duración/DV01 como input;
covarianza derivada de cambios históricos; separación de las 5 capas; estadísticas mínimas reportadas.

Si todo está ✅, sugiere `make entrega`.
