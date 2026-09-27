---
name: verificar
description: Corre el pipeline completo y todas las verificaciones del proyecto y resume el estado. Invocar con /verificar.
disable-model-invocation: true
---

Ejecuta en orden y detente en el primer fallo, explicando la causa probable:

1. `make data` — limpieza y validaciones.
2. `make json` — construye y valida input.json.
3. `make test` — pruebas.
4. `make lint`.
5. Si `optimizer.solve` ya está implementado: `make run` y valida output.json (status, constraintChecks todos ok).
6. Cuenta `NotImplementedError` en src/ y `\todo{` en informe_latex/.

Resume en una tabla: paso, resultado, observación. No modifiques código en este comando.
