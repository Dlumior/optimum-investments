"""Estilo único de figuras y guardado directo al informe LaTeX.

Uso en notebooks:
    from optimum.reporting.figures import new_figure, save_fig
    fig, ax = new_figure()
    ax.plot(...)
    save_fig(fig, "curvas_spot_pen")      # -> informe_latex/figures/curvas_spot_pen.pdf (+ .png)

En LaTeX:  \\includegraphics[width=\\linewidth]{figures/curvas_spot_pen.pdf}
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

from optimum import paths

# Paleta sobria y consistente (PEN / USD / activos / pasivos / patrimonio)
COLORS = {
    "PEN": "#1f4e79",
    "USD": "#c55a11",
    "ASSET": "#2e7d32",
    "LIABILITY": "#b71c1c",
    "EQUITY": "#6a1b9a",
    "neutral": "#595959",
}

# Ancho de texto de un A4 con márgenes de 2.5 cm ≈ 16 cm ≈ 6.3 in
TEXT_WIDTH_IN = 6.3


def set_style() -> None:
    mpl.rcParams.update(
        {
            "figure.figsize": (TEXT_WIDTH_IN, TEXT_WIDTH_IN * 0.55),
            "figure.dpi": 110,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.3,
            "axes.formatter.use_locale": False,
            "pdf.fonttype": 42,  # fuentes embebidas editables
        }
    )


def new_figure(nrows: int = 1, ncols: int = 1, width: float = 1.0, aspect: float = 0.55, **kw):
    """Figura con ancho relativo al ancho de texto del informe (width=1 -> \\linewidth)."""
    set_style()
    w = TEXT_WIDTH_IN * width
    return plt.subplots(nrows, ncols, figsize=(w, w * aspect), **kw)


def _slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_-]+", "_", name).strip("_").lower()


def save_fig(
    fig,
    name: str,
    formats: tuple[str, ...] = ("pdf", "png"),
    out_dir: Path = paths.FIGURES,
    close: bool = False,
) -> list[Path]:
    """Guarda la figura en informe_latex/figures/<name>.{pdf,png}. PDF = vectorial para LaTeX."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for ext in formats:
        f = out_dir / f"{_slug(name)}.{ext}"
        fig.savefig(f)
        out.append(f)
    if close:
        plt.close(fig)
    return out
