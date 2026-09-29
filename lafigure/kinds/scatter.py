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

"""ax.scatter(x, y, size=8, symbol='o', **style) -- points with no visible
connecting line, backed by a genuine pg.PlotDataItem so it stays a real,
clickable PlotDataItem like every other kind here (see series.py's
SeriesMixin._add_series docstring on why that matters --
_wire_curve_clickable and RectBrush both key off that).

**Not `pen=None`.** PlotDataItem.updateItems (read from the installed
pyqtgraph 0.14.0 source, not guessed) only calls `self.curve.setData(...)`
-- which is what builds the PlotCurveItem's path -- when `self.opts['pen']
is not None`; with `pen=None` the internal PlotCurveItem never gets any
data at all, so its `mouseShape()` is permanently empty and a click on a
symbol never reaches `_wire_curve_clickable`'s `curve.curve.sigClicked`
(confirmed empirically: `item.curve.mouseShape().isEmpty()` is True with
pen=None, False with a fully transparent pen). A fully transparent pen
(alpha 0) makes `updateItems` treat the curve as visible-enough to build
real path data -- so hit-testing works -- while painting nothing, which
is visually identical to no connecting line at all."""
import numpy as np
import pyqtgraph as pg

from ..series import SeriesKind, register_series_kind

DEFAULT_SIZE = 8
DEFAULT_SYMBOL = 'o'
DEFAULT_COLOR = 'b'
_TRANSPARENT = (0, 0, 0, 0)


class ScatterKind(SeriesKind):
    name = 'scatter'
    # x/y are the item's real, parallel xData/yData (get_xy/set_xy aren't
    # overridden -- the base PlotDataItem behavior already fits), so
    # RectBrush (which reads curve.xData/yData directly) works unmodified.
    capabilities = frozenset({'brush', 'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               size=DEFAULT_SIZE, symbol=DEFAULT_SYMBOL, symbolBrush=None, symbolPen=None,
               **style):
        color = pg.mkPen(pen).color() if pen is not None else pg.mkColor(DEFAULT_COLOR)
        if symbolBrush is None:
            symbolBrush = pg.mkBrush(color)
        if symbolPen is None:
            symbolPen = pg.mkPen(color)
        return plot_item.plot(x, y, pen=pg.mkPen(_TRANSPARENT), symbol=symbol, symbolSize=size,
                              symbolBrush=symbolBrush, symbolPen=symbolPen, name=name)

    def to_dict(self, item):
        return {
            'x': np.array(item.xData, copy=True),
            'y': np.array(item.yData, copy=True),
            # The symbol's own pen (its outline color), reused by create()
            # as the `pen` override that derives symbolBrush/symbolPen --
            # NOT the item's actual (always-transparent) line pen.
            # _orig_symbol_pen while selected: the highlight replaces the
            # outline (selection_ui._highlight_curve_pen), not the style.
            'pen': item.opts.get('_orig_symbol_pen', item.opts.get('symbolPen')),
            'name': item.name(),
            'style': {
                'size': item.opts.get('symbolSize', DEFAULT_SIZE),
                'symbol': item.opts.get('symbol', DEFAULT_SYMBOL),
                'symbolBrush': item.opts.get('symbolBrush'),
                'symbolPen': item.opts.get('_orig_symbol_pen', item.opts.get('symbolPen')),
            },
        }


register_series_kind(ScatterKind())
