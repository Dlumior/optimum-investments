"""Exporta DataFrames como tablas booktabs a informe_latex/tables/ y JSON de resultados.

save_table(df, "posiciones_optimas", caption="...", label="tab:pos", fmt="{:,.1f}")
% en LaTeX:  \\input{tables/posiciones_optimas}
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from optimum import paths


def save_table(
    df: pd.DataFrame,
    name: str,
    caption: str | None = None,
    label: str | None = None,
    fmt: str = "{:,.2f}",
    index: bool = True,
    out_dir: Path = paths.TABLES,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = df.rename_axis(index=None, columns=None)  # evita una fila extra con el nombre del índice
    num_cols = df.select_dtypes("number").columns
    styler = df.style.format(escape="latex", na_rep="--")  # texto: escapa _ % & #
    styler = styler.format(fmt, subset=num_cols, na_rep="--")  # números: formato pedido
    styler = styler.format_index(escape="latex", axis=0).format_index(escape="latex", axis=1)
    if not index:
        styler = styler.hide(axis="index")
    tex = styler.to_latex(
        hrules=True,  # booktabs: \toprule \midrule \bottomrule
        caption=caption,
        label=label,
        position="htbp",
        position_float="centering",
    )
    f = out_dir / f"{name}.tex"
    f.write_text(tex, encoding="utf-8")
    return f


def pct(x: float) -> str:
    return f"{100 * x:.2f}\\%"
