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

"""the 'stem' SeriesKind -- reachable as
ax.stem(x, y, baseline=0.0, marker_px=6.0, ...) once this module is
imported. Per MATLAB's stem(): a vertical line ("stem") from a baseline to
each sample, tipped with a marker.

A `_base.CompositeSeriesItem` subclass (`StemItem`), not a `DerivedKind` on
`'line'` or `'scatter'`: neither alone draws this shape. A single
`pg.PlotDataItem` with `symbol=` set draws a marker at EVERY data point --
there is no way to ask it for a marker only at every other vertex of a
connect='pairs' stem-segment path without also drawing a marker on every
baseline anchor. Two separate items (a disconnected-segment line + a
marker-only scatter) would need a companion-item bookkeeping scheme (see
`errorbar.py`'s own documented gap: its paired ErrorBarItem is orphaned by
a plain `plot_item.removeItem(primary)` delete, since `clip_ops.py` only
knows about the one tracked item) for no real benefit here, since nothing
about a stem's stems or its markers needs independent click-selection.
One `CompositeSeriesItem` drawing both primitives keeps this exactly ONE
series -- uniformly removable/undoable the same way every other kind's
single item already is, with no orphan risk.

**Not click-selectable, not brushable** (no `.curve`) -- `capabilities` is
`{'copy'}` only, the same restriction every `CompositeSeriesItem`-based
kind in this round documents.

Marker size is in constant SCREEN pixels (`pixelWidth()`/`pixelHeight()`,
pyqtgraph's own per-item "how big is one screen pixel in my local
coordinates" query) rather than a fixed size in data units, so a marker
looks the same physical size regardless of the subplot's data scale or
X/Y aspect -- the same "compute the screen-constant quantity, don't bake
it into data space" principle
`.claude/skills/lafigure-axes-geometry/SKILL.md` documents for angle/
direction-dependent geometry, applied here to SIZE instead of angle.
"""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

from ._base import CompositeSeriesItem
from ..series import SeriesKind, register_series_kind

DEFAULT_MARKER_PX = 6.0


class StemItem(CompositeSeriesItem):
    """One stem series: `_paint` draws a vertical (baseline -> y) line per
    sample with `self.pen`, then a filled marker at each tip with
    `self.brush`. `_bounds()` includes the baseline, so a stem plot whose
    values never reach 0 still frames the baseline (MATLAB's own stem()
    does the same)."""

    def __init__(self, x, y, baseline=0.0, marker_px=DEFAULT_MARKER_PX,
                 pen=None, brush=None, name=None):
        pen_obj = pg.mkPen(pen) if pen is not None else pg.mkPen('k')
        # Default the marker fill to the stem pen's own color -- `brush`
        # (if given) is a color-like spec / QBrush, never the pen object
        # itself (CLAUDE.md bug #16's family: don't assume an argument's
        # shape without checking, a raw QPen isn't a valid mkBrush() input).
        marker_brush = brush if brush is not None else pen_obj.color()
        super().__init__(name=name, pen=pen_obj, brush=marker_brush)
        self.baseline = float(baseline)
        self.marker_px = float(marker_px)
        self._x = np.zeros(0)
        self._y = np.zeros(0)
        self.set_xy(x, y)

    def getData(self):
        return self._x, self._y

    def set_xy(self, x, y):
        self._x = np.asarray(x, dtype=float)
        self._y = np.asarray(y, dtype=float)
        self.invalidate()

    def _bounds(self):
        if self._x.size == 0:
            return None
        ymin = min(float(self._y.min()), self.baseline)
        ymax = max(float(self._y.max()), self.baseline)
        return float(self._x.min()), float(self._x.max()), ymin, ymax

    def _paint(self, painter):
        if self._x.size == 0:
            return
        painter.setPen(self.pen)
        for xi, yi in zip(self._x, self._y):
            painter.drawLine(QtCore.QPointF(xi, self.baseline), QtCore.QPointF(xi, yi))
        # Constant-screen-pixel marker radius -- see module docstring.
        px, py = self.pixelWidth(), self.pixelHeight()
        rx = abs(px) * self.marker_px / 2.0 if px else self.marker_px / 2.0
        ry = abs(py) * self.marker_px / 2.0 if py else self.marker_px / 2.0
        painter.setPen(pg.mkPen(None))
        painter.setBrush(self.brush)
        for xi, yi in zip(self._x, self._y):
            painter.drawEllipse(QtCore.QPointF(xi, yi), rx, ry)


class StemKind(SeriesKind):
    """`ax.stem(x, y, baseline=0.0, marker_px=6.0, ...)` -- see module
    docstring. Not brush/fft/remove_average/fit-capable (no `.curve`,
    `get_xy` returns plain arrays but nothing downstream of brushing was
    verified against a `CompositeSeriesItem`'s hit-testing, which doesn't
    exist)."""
    name = 'stem'
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               baseline=0.0, marker_px=DEFAULT_MARKER_PX, brush=None, **style):
        x = np.zeros(0) if x is None else np.asarray(x, dtype=float)
        y = np.zeros(0) if y is None else np.asarray(y, dtype=float)
        item = StemItem(x, y, baseline=baseline, marker_px=marker_px, pen=pen, brush=brush, name=name)
        plot_item.addItem(item)
        return item

    def to_dict(self, item):
        x, y = item.getData()
        return {
            'x': np.array(x, copy=True),
            'y': np.array(y, copy=True),
            'pen': item.opts.get('pen'),
            'name': item.name(),
            'style': {
                'baseline': item.baseline,
                'marker_px': item.marker_px,
                'brush': item.brush,
            },
        }

    def get_xy(self, item):
        return item.getData()

    def set_xy(self, item, x, y):
        item.set_xy(x, y)


register_series_kind(StemKind())
