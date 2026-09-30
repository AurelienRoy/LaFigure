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

"""ax.polarhistogram(theta, bins=18, density=False, **style) -- an
angular histogram: raw angle samples `theta` (RADIANS, see
kinds/_polar_base.py for the orientation convention), binned into `bins`
equal-width sectors spanning [0, 2*pi), each drawn as a wedge whose
radius is the bin's count (or, with density=True, its fraction of the
total). A `_base.CompositeSeriesItem` (round 4's shared base) -- the
wedges are shapes, not a single existing line/scatter item, exactly the
case CompositeSeriesItem exists for -- on an ordinary cartesian PlotItem
with hidden axes and a locked 1:1 aspect; the shared polar grid
(kinds/_polar_base.py's radial rings/spokes/degree labels) is drawn/grown
under it, sized to the largest bin count/fraction any polar-family series
on the subplot has shown.

**Serializes the raw samples, not the computed bins** -- same design as
kinds/hist.py's 1-D histogram, for the same reason (its own docstring
explains it fully): a histogram is conceptually a view over raw samples,
re-binned from scratch on every rebuild, so undo/copy-paste stay correct
even if the binning itself were to change later. The raw samples aren't
recoverable from the drawn wedge geometry (lossy, like hist.py's
edges/counts), so they're kept on the item directly.

**Not click-selectable** (CompositeSeriesItem -- no `.curve`, see
_base.py's own docstring on this). **Not brush/fft/remove_average/fit-
capable**: a bin's wedge has no per-point identity to select or
transform (there is no 1:1 mapping from a raw sample back to "this pixel
of this wedge") -- only 'copy' (the to_dict/create round trip) is
claimed, matching kinds/hist.py's and kinds/bar.py's own honesty about
what they don't support yet.
"""
import math

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui

from ._base import CompositeSeriesItem
from ._polar_base import grow_polar_grid, polar_to_xy
from ..series import SeriesKind, register_series_kind

DEFAULT_BINS = 18
_RAW_ATTR = '_lafigure_polarhist_raw'
_ARC_STEP_DEG = 4.0  # how finely a wedge's outer arc is approximated


class PolarHistogramItem(CompositeSeriesItem):
    """See module docstring. `theta`: raw angle samples, radians."""

    def __init__(self, theta, bins=DEFAULT_BINS, density=False, name=None, pen=None, brush=None):
        super().__init__(name=name, pen=pen, brush=brush)
        self.bins = int(bins)
        self.density = bool(density)
        self._recompute(theta)

    def _recompute(self, theta):
        theta = np.asarray(theta, dtype=float)
        self._theta = theta
        wrapped = np.mod(theta, 2 * np.pi)
        counts, edges = np.histogram(wrapped, bins=self.bins, range=(0.0, 2 * np.pi))
        counts = counts.astype(float)
        if self.density and counts.sum() > 0:
            counts = counts / counts.sum()
        self._counts = counts
        self._edges = edges

    def set_theta(self, theta):
        self._recompute(theta)
        self.invalidate()

    def rmax(self):
        return float(self._counts.max()) if self._counts.size else 0.0

    def getData(self):
        """Representative arrays: bin centers (radians) and their
        counts/fractions -- not click-selectable data, just what
        Fit Vertical/Horizontal etc. would read if ever pointed here."""
        centers = (self._edges[:-1] + self._edges[1:]) / 2.0
        return centers, self._counts

    def _bounds(self):
        rmax = self.rmax()
        if rmax <= 0:
            return None
        return -rmax, rmax, -rmax, rmax

    def _paint(self, painter):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(self.pen)
        painter.setBrush(self.brush)
        for i, count in enumerate(self._counts):
            if count <= 0:
                continue
            a0, a1 = float(self._edges[i]), float(self._edges[i + 1])
            n = max(2, int(abs(a1 - a0) / math.radians(_ARC_STEP_DEG)) + 1)
            angles = np.linspace(a0, a1, n)
            xs, ys = polar_to_xy(angles, np.full(n, count))
            path = QtGui.QPainterPath(QtCore.QPointF(0.0, 0.0))
            for x, y in zip(xs, ys):
                path.lineTo(float(x), float(y))
            path.closeSubpath()
            painter.drawPath(path)


class PolarHistogramKind(SeriesKind):
    name = 'polarhistogram'
    capabilities = frozenset({'copy'})  # see module docstring

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               bins=DEFAULT_BINS, density=False, brush=None, **style):
        theta = np.zeros(0) if x is None else np.asarray(x, dtype=float)
        item = PolarHistogramItem(theta, bins=bins, density=density, name=name, pen=pen, brush=brush)
        if item.brush.style() == QtCore.Qt.NoBrush:
            color = pg.mkPen(pen).color() if pen is not None else pg.mkColor('b')
            color.setAlpha(150)
            item.setBrush(color)
        plot_item.addItem(item)
        setattr(item, _RAW_ATTR, theta.copy())
        grow_polar_grid(plot_item, item.rmax())
        return item

    def to_dict(self, item):
        return {
            'x': np.array(getattr(item, _RAW_ATTR, item._theta), copy=True),
            'y': None,
            'pen': item.opts.get('pen'),
            'name': item.name(),
            'style': {'bins': item.bins, 'density': item.density, 'brush': item.brush},
        }

    def get_xy(self, item):
        return item.getData()

    def set_xy(self, item, x, y):
        theta = np.asarray(x, dtype=float)
        item.set_theta(theta)
        setattr(item, _RAW_ATTR, theta.copy())


register_series_kind(PolarHistogramKind())
