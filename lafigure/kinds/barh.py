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

"""R4-MISC: the 'barh' SeriesKind -- reachable as
ax.barh(categories, values, width=0.8, ...) once this module is imported.
Horizontal bars, per MATLAB's barh(): category positions run along the Y
axis, each bar's length (the value) extends along X starting at 0.

A `_base.DerivedKind` on `'bar'` -- for its `capabilities` (both bar kinds
draw with a plain `pg.BarGraphItem` and only claim `'copy'`, the same
restriction `kinds/bar.py`'s own docstring explains: brush/fft/
remove_average/fit all assume a PlotDataItem's xData/yData/setData shape
and click-selectability, never verified against a BarGraphItem). `create`/
`to_dict`/`get_xy`/`set_xy` are all overridden rather than delegated,
though: `bar.py`'s own `create()` hardcodes which axis is categorical (X,
positioned via its `x`/`width` keywords) and which is the value axis (Y,
via `height`, always starting at 0) -- baked into its calling convention,
not something a `DerivedKind.setup()` post-processing hook can undo
without re-deriving the same rectangles a second time from scratch. But
`pg.BarGraphItem` ITSELF is fully symmetric between the two axes (its own
docstring: "Likewise y, y0, y1, and height" mirrors the x/x0/x1/width
options exactly) -- so barh reuses that SAME underlying primitive
(mirroring bar.py's own pen/brush-defaulting pattern) with the axis roles
swapped: `y=category position, height=bar thickness` (the categorical
axis) and `x0=0, width=value` (the value axis extends from zero), instead
of bar's `x=category, width=thickness` / `height=value(from 0)`. This is
"the same base function/base plots" in the sense the round asked for --
the identical pyqtgraph class, the identical pen/brush/string-category
conveniences -- just with X and Y swapped, which `bar.py`'s own `create()`
signature has no parameter to express.

Known gap, same class as `errorbar.py`'s own documented one: a bar with
string categories sets tick labels on the LEFT axis (`_base.
apply_category_ticks`), separately from `bar.py`'s own inline bottom-axis
version -- the two don't share code, so a future styling change to one
won't automatically reach the other.
"""
import numpy as np
import pyqtgraph as pg

from . import _base
from ..series import register_series_kind


class BarhKind(_base.DerivedKind):
    """A horizontal bar series. See the module docstring for why `create`/
    `to_dict`/`get_xy`/`set_xy` are all overridden rather than delegated to
    `'bar'`'s own -- only `capabilities` (and the general `DerivedKind`
    plumbing/documentation) actually comes from the base."""
    name = 'barh'
    base = 'bar'

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               width=0.8, brush=None, **style):
        """x: category positions (or string labels); y: values (the bar
        length along X). `width`: bar THICKNESS along the category (Y)
        axis -- same keyword name/meaning as `bar.py`'s own `width`, just
        applied to the other axis."""
        values = np.zeros(0) if y is None else np.asarray(y, dtype=float)
        if x is None:
            cat_pos = np.arange(len(values), dtype=float)
        else:
            cats = np.asarray(x)
            if cats.dtype.kind in 'US':  # string categories -- see bar.py
                labels = [str(v) for v in cats]
                cat_pos = np.arange(len(labels), dtype=float)
                _base.apply_category_ticks(plot_item, 'left', labels)
            else:
                cat_pos = cats.astype(float)
        kwargs = dict(y=cat_pos, height=width, x0=np.zeros_like(values),
                      width=values, name=name)
        if pen is not None:
            kwargs['pen'] = pen
        if brush is not None:
            kwargs['brush'] = brush
        elif pen is not None:
            # Without this, every bar defaults to pyqtgraph's plain gray
            # fill regardless of the requested pen color -- same fix
            # bar.py's own create() applies.
            kwargs['brush'] = pg.mkBrush(pg.mkPen(pen).color())
        item = pg.BarGraphItem(**kwargs)
        plot_item.addItem(item)
        return item

    def to_dict(self, item):
        return {
            'x': np.array(item.opts.get('y'), copy=True),
            'y': np.array(item.opts.get('width'), copy=True),
            'pen': item.opts.get('pen'),
            'name': item.name(),
            'style': {
                'width': item.opts.get('height'),
                'brush': item.opts.get('brush'),
            },
        }

    def get_xy(self, item):
        cat = item.opts.get('y')
        val = item.opts.get('width')
        return (None if cat is None else np.asarray(cat)), (None if val is None else np.asarray(val))

    def set_xy(self, item, x, y):
        y = np.asarray(y, dtype=float)
        item.setOpts(y=np.asarray(x, dtype=float), x0=np.zeros_like(y), width=y)


register_series_kind(BarhKind())
