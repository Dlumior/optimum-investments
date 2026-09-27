---
name: figuras-y-tablas
description: Cómo crear y guardar figuras y tablas del proyecto para el informe LaTeX. Úsalo siempre que vayas a graficar en un notebook o a exportar una tabla de resultados.
---

# Figuras y tablas

```python
from optimum.reporting.figures import COLORS, new_figure, save_fig
from optimum.reporting.tables import save_table

fig, ax = new_figure()                 # ancho = \linewidth; new_figure(1, 2, aspect=0.4) para paneles
ax.plot(x, y, color=COLORS["PEN"])
save_fig(fig, "pn_vs_lambda")          # -> informe_latex/figures/pn_vs_lambda.pdf + .png

save_table(df, "posiciones_optimas", caption="…", label="tab:pos", fmt="{:,.1f}")
```
En LaTeX: `\includegraphics[width=\linewidth]{pn_vs_lambda.pdf}` y `\input{tables/posiciones_optimas}`.

## Reglas
- Nunca guardar con `plt.savefig` a mano ni escribir en `informe_latex/figures|tables` con Write (hook lo bloquea).
- Nombres en snake_case, descriptivos y estables (el .tex los referencia).
- Colores semánticos de `COLORS`: PEN, USD, ASSET, LIABILITY, EQUITY. Unidades en ejes (S/ mm, %, pb).
- Tasas en % en los gráficos (×100), pero en decimales en el código y el JSON.
- Toda cifra de una tabla del informe debe salir de `output.json` o de código versionado, nunca tipeada.
