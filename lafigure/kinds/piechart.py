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

"""ax.piechart(values, labels=None, colors=None, **style) -- a pie chart:
one wedge per (non-negative) value, its angular span proportional to the
value's fraction of the total, each drawn in its own color from a
qualitative color cycle (or `colors=`, one entry per slice) with its
label and percentage drawn directly beside it. A `_base.CompositeSeriesItem`
(the wedges are shapes, not a single existing line/scatter item) on an
ordinary cartesian PlotItem with hidden axes and a locked 1:1 aspect
(kinds/_polar_base.py's `setup_polar_axes`) -- but, unlike polar/
polarhistogram, a piechart does NOT call `draw_polar_grid`: a pie's
wedges are already each 100% of their own radius (there is no radial
*scale* -- "how far out" never means anything beyond "this is a slice" --
for rings to usefully annotate), so only the axis-hiding/aspect-lock half
of _polar_base.py is used here.

**Per-slice "legend-friendly" names, the simple route** (this package's
own brief explicitly offers this as the accepted alternative: "or just
make each wedge item carry a label string used by your kind's own
to_dict"). This is still ONE PlotItem-owned item (CompositeSeriesItem,
same as polarhistogram -- not click-selectable, no `.curve`) -- there is
no per-slice `PlotDataItem` for `_refresh_legend_order`/the figure's real
legend to give its own row, and building that would mean one real item
per slice, a materially bigger design change out of this package's scope
(reported, not silently worked around). Instead every slice's label +
percentage is drawn directly on the chart next to its wedge -- readable
without opening a legend at all -- and the labels/colors are kept on the
item (`item.slice_labels`) and round-tripped through `to_dict`'s 'style'
so copy/paste and undo/redo preserve them exactly.

**Not brush/fft/remove_average/fit-capable**: a slice has no per-point
identity (`'copy'` only, same honesty as polarhistogram.py/bar.py/hist.py).
"""
import math

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui

from ._base import CompositeSeriesItem
from ._polar_base import polar_to_xy, setup_polar_axes
from ..series import SeriesKind, register_series_kind

# A qualitative (not sequential) color cycle -- matplotlib's tab10, the
# same colors axes.py's DEFAULT_COLORS already uses for ax.plot's own
# per-subplot cycling, reused here for visual consistency across kinds.
QUALITATIVE_COLORS = [
    (31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
    (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127),
    (188, 189, 34), (23, 190, 207),
]
_ARC_STEP_DEG = 4.0
_VIEW_MARGIN = 1.3  # data-space half-extent shown, beyond the unit pie


class PieChartItem(CompositeSeriesItem):
    """See module docstring. `values`: one non-negative number per slice
    (negative values are clipped to 0, not dropped, so `labels`/`colors`
    stay aligned by index)."""

    def __init__(self, values, labels=None, colors=None, name=None, pen=None):
        super().__init__(name=name, pen=pen)
        self._recompute(values, labels, colors)

    def _recompute(self, values, labels, colors):
        values = np.clip(np.asarray(values, dtype=float), 0.0, None)
        n = len(values)
        total = float(values.sum())
        self._values = values
        self._fractions = (values / total) if total > 0 else np.zeros(n)
        if labels is not None:
            self.slice_labels = [str(v) for v in labels]
        elif not hasattr(self, 'slice_labels') or len(self.slice_labels) != n:
            self.slice_labels = [f"Slice {i + 1}" for i in range(n)]
        if colors is not None:
            self._colors = [pg.mkColor(c) for c in colors]
        else:
            self._colors = [pg.mkColor(QUALITATIVE_COLORS[i % len(QUALITATIVE_COLORS)])
                            for i in range(n)]
        self._edges = np.concatenate([[0.0], np.cumsum(self._fractions)]) * 2 * np.pi

    def set_values(self, values, labels=None, colors=None):
        self._recompute(values, labels, colors if colors is not None else
                        [c.getRgb() for c in self._colors])
        self.invalidate()

    def getData(self):
        return self._values, self._fractions

    def _bounds(self):
        if self._values.size == 0 or self._values.sum() <= 0:
            return None
        return -_VIEW_MARGIN, _VIEW_MARGIN, -_VIEW_MARGIN, _VIEW_MARGIN

    def _paint(self, painter):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        outline = pg.mkPen((255, 255, 255), width=1)
        label_pen = pg.mkPen((30, 30, 30))
        for i in range(len(self._values)):
            if self._fractions[i] <= 0:
                continue
            a0, a1 = float(self._edges[i]), float(self._edges[i + 1])
            n = max(2, int(abs(a1 - a0) / math.radians(_ARC_STEP_DEG)) + 1)
            angles = np.linspace(a0, a1, n)
            xs, ys = polar_to_xy(angles, np.full(n, 1.0))
            path = QtGui.QPainterPath(QtCore.QPointF(0.0, 0.0))
            for x, y in zip(xs, ys):
                path.lineTo(float(x), float(y))
            path.closeSubpath()
            painter.setPen(outline)
            painter.setBrush(pg.mkBrush(self._colors[i]))
            painter.drawPath(path)
            mid = (a0 + a1) / 2.0
            lx, ly = polar_to_xy(np.array([mid]), np.array([1.15]))
            painter.setPen(label_pen)
            text = f"{self.slice_labels[i]} ({100 * self._fractions[i]:.0f}%)"
            painter.drawText(QtCore.QRectF(float(lx[0]) - 0.4, float(ly[0]) - 0.08, 0.8, 0.16),
                             QtCore.Qt.AlignCenter, text)


class PieChartKind(SeriesKind):
    name = 'piechart'
    capabilities = frozenset({'copy'})  # see module docstring

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               labels=None, colors=None, **style):
        values = np.zeros(0) if x is None else np.asarray(x, dtype=float)
        item = PieChartItem(values, labels=labels, colors=colors, name=name, pen=pen)
        plot_item.addItem(item)
        setup_polar_axes(plot_item)
        vb = plot_item.getViewBox()
        vb.setRange(xRange=(-_VIEW_MARGIN, _VIEW_MARGIN), yRange=(-_VIEW_MARGIN, _VIEW_MARGIN),
                    padding=0)
        return item

    def to_dict(self, item):
        return {
            'x': np.array(item._values, copy=True),
            'y': None,
            'pen': item.opts.get('pen'),
            'name': item.name(),
            'style': {'labels': list(item.slice_labels),
                      'colors': [c.getRgb() for c in item._colors]},
        }

    def get_xy(self, item):
        return item.getData()

    def set_xy(self, item, x, y):
        item.set_values(np.asarray(x, dtype=float))


register_series_kind(PieChartKind())
