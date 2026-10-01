# Copyright 2026, Aurélien ROY, <lafigure@proton.me>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""ax.violinplot(labels, values, **style) / ax.violinplot(source, x='cat',
y='val') -- one violin per category, all drawn as a single
`_base.CompositeSeriesItem` (PLAN.md "R4-DIST"), reusing `_base.categories`
(the same categorical-axis convention boxchart/swarmchart use) and
`_base.kde` (a plain-numpy Gaussian KDE, Silverman bandwidth) for the
per-category density -- nothing here recomputes either from scratch.

A violin's outline is the category's KDE curve, normalized to its own peak
and scaled to `violin_width / 2`, drawn on BOTH sides of the category's
integer code (mirrored, the classic violin shape) as one closed filled
polygon; an optional horizontal median line matches boxchart's median bar.

**Not click-selectable** (`ViolinItem` has no `.curve`, per
`_base.CompositeSeriesItem`'s own docstring) and **not**
brush/fft/remove_average/fit-capable -- only `'copy'` is claimed, the same
conservative stance `boxchart.py` takes for a composite shape that isn't a
simple parallel-array curve or scatter. An HTML export converter
(`html_export.py`, coordinator-owned) would need real, dedicated code for
this shape too -- the generic `Scattergl` fallback there cannot represent
a filled violin outline.

`to_dict`/`create` round-trip through the ORIGINAL per-point category
labels (recovered from the current per-point codes via `item.labels`, not
the codes themselves) -- see `boxchart.py`'s module docstring for exactly
why this is needed for an exact round trip."""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui

from ..series import SeriesKind, register_series_kind
from ._base import CompositeSeriesItem, apply_category_ticks, categories, kde

DEFAULT_VIOLIN_WIDTH = 0.6
DEFAULT_FILL_ALPHA = 90
DEFAULT_KDE_POINTS = 128


class ViolinItem(CompositeSeriesItem):
    """One mirrored KDE outline per distinct category code, normalized to
    its own peak density and scaled to `violin_width / 2`, plus an optional
    horizontal median line. See the module docstring for what this kind
    does not support yet (click-selection, brushing)."""

    def __init__(self, codes, values, labels, violin_width=DEFAULT_VIOLIN_WIDTH,
                 kde_points=DEFAULT_KDE_POINTS, show_median=True, **kw):
        super().__init__(**kw)
        self.labels = list(labels)
        self.violin_width = float(violin_width)
        self.kde_points = int(kde_points)
        self.show_median = bool(show_median)
        self._codes = np.zeros(0, dtype=np.intp)
        self._values = np.zeros(0, dtype=float)
        self._violins = {}   # code -> (grid, density normalized to its own peak, median)
        self._set_data(codes, values)

    # -- data ------------------------------------------------------------
    def getData(self):
        """(category codes as float, raw values) -- one entry per input
        point, mirroring BoxChartItem.getData's convention."""
        return self._codes.astype(float), self._values

    def _set_data(self, x, y):
        self._codes = np.asarray(x, dtype=np.intp)
        self._values = np.asarray(y, dtype=float)
        self._violins = {}
        for c in np.unique(self._codes):
            vals = self._values[self._codes == c]
            grid, density = kde(vals, points=self.kde_points)
            peak = float(density.max()) if density.size else 0.0
            norm = density / peak if peak > 0 else density
            finite_vals = vals[np.isfinite(vals)]
            med = float(np.median(finite_vals)) if finite_vals.size else float('nan')
            self._violins[int(c)] = (grid, norm, med)

    def set_xy(self, x, y):
        self._set_data(x, y)
        self.invalidate()

    # -- geometry ----------------------------------------------------------
    def _bounds(self):
        if not self._violins:
            return None
        half = self.violin_width / 2.0
        codes = list(self._violins.keys())
        xmin, xmax = min(codes) - half, max(codes) + half
        grids = [g for g, d, m in self._violins.values() if g.size]
        if not grids:
            return None
        ylo = min(float(g.min()) for g in grids)
        yhi = max(float(g.max()) for g in grids)
        return float(xmin), float(xmax), float(ylo), float(yhi)

    def _paint(self, painter):
        half = self.violin_width / 2.0
        painter.setPen(self.pen)
        painter.setBrush(self.brush)
        for code, (grid, norm, med) in self._violins.items():
            if grid.size == 0:
                continue
            x = float(code)
            poly = QtGui.QPolygonF()
            for gy, d in zip(grid, norm):
                poly.append(QtCore.QPointF(x + float(d) * half, float(gy)))
            for gy, d in zip(grid[::-1], norm[::-1]):
                poly.append(QtCore.QPointF(x - float(d) * half, float(gy)))
            painter.drawPolygon(poly)
            if self.show_median and not np.isnan(med):
                painter.drawLine(QtCore.QPointF(x - half, med), QtCore.QPointF(x + half, med))


class ViolinKind(SeriesKind):
    name = 'violinplot'
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               violin_width=DEFAULT_VIOLIN_WIDTH, brush=None, kde_points=DEFAULT_KDE_POINTS,
               show_median=True, **style):
        y = np.zeros(0) if y is None else np.asarray(y, dtype=float)
        x = np.arange(len(y)) if x is None else np.asarray(x)
        codes, labels = categories(x)
        if pen is None:
            pen = pg.mkPen('b', width=1)
        if brush is None:
            color = pg.mkPen(pen).color()
            color.setAlpha(DEFAULT_FILL_ALPHA)
            brush = pg.mkBrush(color)
        item = ViolinItem(codes, y, labels, violin_width=violin_width, kde_points=kde_points,
                          show_median=show_median, pen=pen, brush=brush, name=name)
        plot_item.addItem(item)
        apply_category_ticks(plot_item, 'bottom', labels)
        return item

    def to_dict(self, item):
        codes, values = item.getData()
        labels = item.labels
        x = np.array([labels[int(c)] if 0 <= int(c) < len(labels) else str(c) for c in codes],
                     dtype=object)
        return {
            'x': x,
            'y': np.array(values, copy=True),
            'pen': item.opts.get('pen'),
            'name': item.name(),
            'style': {
                'violin_width': item.violin_width,
                'brush': item.brush,
                'kde_points': item.kde_points,
                'show_median': item.show_median,
            },
        }

    def get_xy(self, item):
        return item.getData()

    def set_xy(self, item, x, y):
        item.set_xy(x, y)


register_series_kind(ViolinKind())
