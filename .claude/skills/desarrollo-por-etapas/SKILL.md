---
name: desarrollo-por-etapas
description: Flujo de trabajo obligatorio para implementar cualquier componente del modelo (valorizador, riesgo, optimizador, output) en este proyecto. Úsalo cuando el usuario pida implementar, programar o construir una parte del modelo.
---

# Desarrollo por etapas (Anexo 2, reglas prácticas)

Arquitectura en 5 capas separadas: (i) JSON → `io/json_contract.py`, (ii) valorización → `valuation.py`,
(iii) factores/covarianzas/escenarios → `risk.py`, (iv) optimización → `optimizer.py`, (v) resultados → `reporting/`, `cli.py`.

Para cada componente:
1. **Plan** (sin código): variables, fórmulas, unidades, supuestos, qué input.json usa. Mostrarlo al usuario.
2. **Tests primero** en `tests/` con casos resolubles a mano (y un caso límite). Deben fallar.
3. **Implementación mínima** en `src/optimum/` (no en notebooks). Docstrings con unidades.
4. `make test` en verde (el hook Stop lo exige). Luego ejemplo visible en el notebook correspondiente.
5. **Auditoría**: para piezas financieras, invocar el subagente `auditor-financiero`.
6. **Registro**: entrada en `docs/ia/registro_ia.md`; decisiones de diseño en `docs/decisiones.md`.

Reglas: pedir aclaración ante ambigüedad financiera en vez de asumir en silencio; no inventar variables
ni parámetros que no estén en input.json; un componente por vez; cambios pequeños y verificables.
