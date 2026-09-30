# Copyright 2026, Aurélien ROY, <aurroy@hotmail.com>
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

"""ax.boxchart(labels, values, **style) / ax.boxchart(source, x='cat',
y='val') -- one box-and-whisker per category, all drawn as a single
`_base.CompositeSeriesItem` (PLAN.md "R4-DIST"), reusing `_base.categories`
(the categorical-axis convention swarmchart/violinplot also use) and
`_base.quantiles` (Tukey 1.5*IQR) for the box statistics themselves --
nothing here recomputes either from scratch.

**Not click-selectable** (`BoxChartItem` has no `.curve`, per
`_base.CompositeSeriesItem`'s own docstring -- `_add_series`'s
`hasattr(item, 'curve')` guard already handles this) and **not**
brush/fft/remove_average/fit-capable -- only `'copy'` (a `to_dict`/`create`
round trip) is claimed, the same conservative stance `bar.py`/`errorbar.py`
take for a composite shape that isn't a simple parallel-array curve or
scatter. An HTML export converter (`html_export.py`, coordinator-owned)
would need real, dedicated code for this shape -- the generic `Scattergl`
fallback there cannot represent a box.

Each category's box sits at its integer code (0, 1, 2, ...) with the
category's own string label shown on the bottom axis via
`_base.apply_category_ticks` -- exactly how `bar.py`'s string-category
bonus places its bars. `to_dict`/`create` round-trip through the ORIGINAL
per-point category labels (recovered from the current per-point codes via
`item.labels`, not the codes themselves), so a copy/paste or undo/redo
keeps the same visible category names, not `'0'`/`'1'`/`'2'`."""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

from ..series import SeriesKind, register_series_kind
from ._base import CompositeSeriesItem, apply_category_ticks, categories, quantiles

DEFAULT_BOX_WIDTH = 0.6
DEFAULT_FILL_ALPHA = 90
# Outlier marker radius, as a fraction of box_width -- a data-unit size
# (like the box itself), not a scene-pixel one: there is no axes-anchored
# angle/direction dependency here (unlike an annotation's arrowhead, see
# .claude/skills/lafigure-axes-geometry/SKILL.md), just a marker meant to
# read as "small relative to its own box".
OUTLIER_RADIUS_FRAC = 0.12


class BoxChartItem(CompositeSeriesItem):
    """One box per distinct category code: q1..q3 as a filled rect, the
    median as a horizontal line across it, whiskers to the most extreme
    in-range value (`_base.quantiles`'s own `lo_whisker`/`hi_whisker`), and
    outliers as small circles. See the module docstring for what this kind
    does not support yet (click-selection, brushing)."""

    def __init__(self, codes, values, labels, box_width=DEFAULT_BOX_WIDTH,
                 outlier_pen=None, **kw):
        super().__init__(**kw)
        self.labels = list(labels)
        self.box_width = float(box_width)
        self._outlier_pen = pg.mkPen(outlier_pen) if outlier_pen is not None else self.pen
        self._codes = np.zeros(0, dtype=np.intp)
        self._values = np.zeros(0, dtype=float)
        self._stats = {}
        self._set_data(codes, values)

    # -- data ------------------------------------------------------------
    def getData(self):
        """(category codes as float, raw values) -- one entry per input
        point, the representative pair Fit Vertical/Horizontal and a CSV
        export would read."""
        return self._codes.astype(float), self._values

    def _set_data(self, x, y):
        self._codes = np.asarray(x, dtype=np.intp)
        self._values = np.asarray(y, dtype=float)
        self._stats = {int(c): quantiles(self._values[self._codes == c])
                       for c in np.unique(self._codes)}

    def set_xy(self, x, y):
        self._set_data(x, y)
        self.invalidate()

    # -- geometry ----------------------------------------------------------
    def _valid_stats(self):
        return {c: s for c, s in self._stats.items() if not np.isnan(s['q1'])}

    def _bounds(self):
        valid = self._valid_stats()
        if not valid:
            return None
        half = self.box_width / 2.0
        xmin, xmax = min(valid) - half, max(valid) + half
        los, his = [], []
        for s in valid.values():
            los.append(s['lo_whisker'])
            his.append(s['hi_whisker'])
            if s['outliers'].size:
                los.append(float(np.min(s['outliers'])))
                his.append(float(np.max(s['outliers'])))
        return float(xmin), float(xmax), float(min(los)), float(max(his))

    def _paint(self, painter):
        half = self.box_width / 2.0
        r = self.box_width * OUTLIER_RADIUS_FRAC
        for code, s in self._valid_stats().items():
            x = float(code)
            painter.setPen(self.pen)
            painter.drawLine(QtCore.QPointF(x, s['lo_whisker']), QtCore.QPointF(x, s['q1']))
            painter.drawLine(QtCore.QPointF(x, s['q3']), QtCore.QPointF(x, s['hi_whisker']))
            painter.setBrush(self.brush)
            rect = QtCore.QRectF(QtCore.QPointF(x - half, s['q1']),
                                  QtCore.QPointF(x + half, s['q3'])).normalized()
            painter.drawRect(rect)
            painter.drawLine(QtCore.QPointF(x - half, s['med']), QtCore.QPointF(x + half, s['med']))
            painter.setPen(self._outlier_pen)
            painter.setBrush(pg.mkBrush(None))
            for v in s['outliers']:
                painter.drawEllipse(QtCore.QPointF(x, float(v)), r, r)


class BoxChartKind(SeriesKind):
    name = 'boxchart'
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               box_width=DEFAULT_BOX_WIDTH, brush=None, outlier_pen=None, **style):
        y = np.zeros(0) if y is None else np.asarray(y, dtype=float)
        x = np.arange(len(y)) if x is None else np.asarray(x)
        codes, labels = categories(x)
        if pen is None:
            pen = pg.mkPen('b', width=1)
        if brush is None:
            color = pg.mkPen(pen).color()
            color.setAlpha(DEFAULT_FILL_ALPHA)
            brush = pg.mkBrush(color)
        item = BoxChartItem(codes, y, labels, box_width=box_width, outlier_pen=outlier_pen,
                            pen=pen, brush=brush, name=name)
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
                'box_width': item.box_width,
                'brush': item.brush,
                'outlier_pen': item._outlier_pen,
            },
        }

    def get_xy(self, item):
        return item.getData()

    def set_xy(self, item, x, y):
        item.set_xy(x, y)


register_series_kind(BoxChartKind())
