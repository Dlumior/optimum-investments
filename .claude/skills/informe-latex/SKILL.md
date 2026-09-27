---
name: informe-latex
description: Estructura, reglas y compilación del documento técnico en informe_latex/ (LuaLaTeX vía Docker). Úsalo al redactar o editar secciones del informe, anexos, o al compilar.
---

# Informe técnico (LaTeX)

- Compilar: `make report` (docker compose → `latexmk -lualatex` → `informe_latex/out/main.pdf`).
  En VS Code: LaTeX Workshop, receta "Docker LuaLaTeX". Idioma: español (`babel` spanish, `es-tabla`, punto decimal).
- **Máximo 12 páginas** de cuerpo (secciones 01–07). Anexos A (instrucciones), B (uso de IA), C (pruebas) no cuentan.
- Secciones en `sections/NN_nombre.tex`; una idea por párrafo; `\cref{}` para referencias.
- Contenido exigido: resumen ejecutivo, formulación, supuestos, función objetivo, restricciones, algoritmo,
  resultados, sensibilidad y **opinión del analista** (fortalezas/debilidades).
- Métricas mínimas: rentabilidad esperada de activos, costo esperado de pasivos, PN esperado y su cambio,
  volatilidad (y CVaR en C) del PN, pesos por moneda/tipo con límites activos, costos de transacción.
- Notación en `preamble.tex` (\SigmaF, \M, \CVaR, \PEN…). Usar `\todo{}` para pendientes (el hook de inicio los cuenta).
- Cifras: nunca escritas a mano si pueden venir de `tables/*.tex`. Si se citan en el texto, verificar contra output.json.
- Tras editar: compilar y revisar que no haya `\todo` sin resolver antes de la entrega.
