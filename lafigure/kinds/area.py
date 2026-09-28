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

"""ax.area(x, y, y2=0, **style) -- a filled line, backed by a genuine
pg.PlotDataItem (fillLevel=y2, brush=...).

Plain pyqtgraph's fillLevel is only a constant baseline, not a second
curve -- true "fill between two curves" would need pyqtgraph's
FillBetweenItem, which fills between two OTHER PlotDataItems rather than
being one itself; using it here would mean this kind's own item isn't a
plain PlotDataItem, losing click-selection (_wire_curve_clickable assumes
`.curve`) and needing get_xy/set_xy overrides, for a shape (arbitrary
second curve) nothing in this package's four kinds actually needs. So
`y2` here is kept a scalar baseline (default 0), same as MATLAB's
`area(x, y, basevalue)` -- a real, clickable PlotDataItem, consistent with
scatter/stairs/hist in this same directory."""
import numpy as np
import pyqtgraph as pg

from ..series import SeriesKind, register_series_kind

DEFAULT_ALPHA = 80


class AreaKind(SeriesKind):
    name = 'area'
    # x/y are the item's real, parallel xData/yData -- unmodified get_xy/
    # set_xy, so RectBrush (reads curve.xData/yData directly) works as-is.
    capabilities = frozenset({'brush', 'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               y2=0, brush=None, **style):
        if pen is None:
            pen = pg.mkPen('b', width=1)
        if brush is None:
            color = pg.mkPen(pen).color()
            color.setAlpha(DEFAULT_ALPHA)
            brush = pg.mkBrush(color)
        return plot_item.plot(x, y, pen=pen, name=name, fillLevel=y2, brush=brush)

    def to_dict(self, item):
        return {
            'x': np.array(item.xData, copy=True),
            'y': np.array(item.yData, copy=True),
            'pen': item.opts.get('_orig_pen', item.opts.get('pen')),
            'name': item.name(),
            'style': {
                'y2': item.opts.get('fillLevel', 0),
                # PlotDataItem.setData's own `brush=` kwarg is stored under
                # opts['fillBrush'], not opts['brush'] (confirmed by reading
                # the installed pyqtgraph source: setData translates
                # kwargs['brush'] -> kwargs['fillBrush'] before applying it) --
                # create()'s own `brush=` kwarg name still matches setData's,
                # only the opts dict key differs.
                'brush': item.opts.get('fillBrush'),
            },
        }


register_series_kind(AreaKind())
