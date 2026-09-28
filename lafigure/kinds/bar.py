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

"""The 'bar' SeriesKind -- reachable as ax.bar(categories, values, ...) once
this module is imported (see register_series_kind below).

Built on pg.BarGraphItem, which is NOT a pg.PlotDataItem: it stores its
data in item.opts['x']/item.opts['height'] (verified against the installed
pyqtgraph -- BarGraphItem.__init__ takes **opts and keeps them verbatim in
self.opts; setOpts(**opts) updates that dict and recomputes the bar
geometry) rather than xData/yData/setData, and it has no `.curve` attribute
at all, so _add_series's `hasattr(item, 'curve')` guard correctly leaves a
bar series non-click-selectable for now (WP-J's job later). get_xy/set_xy
are overridden accordingly.

Bonus (not required by the work package, documented per its own
suggestion): if the categories passed to ax.bar are strings rather than
numbers, they're placed at integer positions 0..n-1 and set as the
subplot's bottom-axis tick labels via AxisItem.setTicks -- verified this
pyqtgraph version's AxisItem accepts that call. Numeric categories (bin
centers) are the baseline and always work; string categories are the
bonus.
"""
import numpy as np
import pyqtgraph as pg

from ..series import SeriesKind, register_series_kind


class BarKind(SeriesKind):
    name = 'bar'
    # Deliberately NOT 'brush'/'fft'/'remove_average'/'fit': none of those
    # code paths were verified to work against a BarGraphItem (they assume
    # a PlotDataItem's xData/yData/setData shape and click-selectability),
    # so only 'copy' (to_dict/create round trip) is claimed.
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               width=0.8, brush=None, **style):
        y = np.zeros(0) if y is None else np.asarray(y, dtype=float)
        if x is None:
            x = np.arange(len(y), dtype=float)
        else:
            x = np.asarray(x)
        if x.dtype.kind in 'US':  # string categories -- see module docstring
            labels = [str(v) for v in x]
            x = np.arange(len(labels), dtype=float)
            plot_item.getAxis('bottom').setTicks([list(zip(x.tolist(), labels))])
        else:
            x = x.astype(float)
        kwargs = dict(x=x, height=y, width=width, name=name)
        if pen is not None:
            kwargs['pen'] = pen
        if brush is not None:
            kwargs['brush'] = brush
        elif pen is not None:
            # Without this, every bar defaults to pyqtgraph's plain gray
            # fill regardless of the requested pen color.
            kwargs['brush'] = pg.mkBrush(pg.mkPen(pen).color())
        item = pg.BarGraphItem(**kwargs)
        plot_item.addItem(item)
        return item

    def to_dict(self, item):
        return {
            'x': np.array(item.opts.get('x'), copy=True),
            'y': np.array(item.opts.get('height'), copy=True),
            'pen': item.opts.get('pen'),
            'name': item.name(),
            'style': {
                'width': item.opts.get('width'),
                'brush': item.opts.get('brush'),
            },
        }

    def get_xy(self, item):
        x = item.opts.get('x')
        y = item.opts.get('height')
        return (None if x is None else np.asarray(x)), (None if y is None else np.asarray(y))

    def set_xy(self, item, x, y):
        item.setOpts(x=np.asarray(x, dtype=float), height=np.asarray(y, dtype=float))


register_series_kind(BarKind())
