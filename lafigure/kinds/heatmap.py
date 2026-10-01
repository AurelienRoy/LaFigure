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

"""the 'heatmap' SeriesKind -- reachable as
ax.heatmap(matrix, x_coords=None, y_coords=None, cmap='viridis', ...) once
this module is imported. A `_base.DerivedKind` on `'imshow'`: it IS an
imshow (same `pg.ImageItem`, same `colorbar.LaColorBar` attachment, same
row-major/invertY orientation convention -- see `kinds/imshow.py`'s own
module docstring), with one addition: optional `x_coords=`/`y_coords=`
place the image over real axis coordinates instead of raw pixel/column
indices.

`x=` is reserved by `Axes._plot_kind` (the source-column-name selector for
the `ax.<kind>(source, x='col', ...)` call form), so the coordinate
keywords are named `x_coords=`/`y_coords=` rather than `x=`/`y=` -- this
was flagged explicitly in the work package brief and confirmed against
`axes.py`'s own docstring before naming them.

**Placement is via `pg.ImageItem.setRect`** (confirmed against the
installed pyqtgraph source: `setRect(x, y, w, h)` builds a `QTransform`
that translates to `(x, y)` and scales so the item's own local
`(0, 0, pixel_width, pixel_height)` rect maps onto the given one) --
`item.setRect(QRectF(x0, y0, x1 - x0, y1 - y0))` where `(x0, x1)` /
`(y0, y1)` are `x_coords`'/`y_coords`' own first/last elements. **Only the
endpoints are used**: `setRect` places a uniform rect over the whole
image, so non-uniformly-spaced coordinate arrays are NOT modeled pixel by
pixel (each column/row is still drawn the same physical width/height) --
documented here rather than silently approximated. With neither keyword
given, `heatmap` behaves exactly like `imshow` (raw pixel/column indices,
`item.setRect` never called, matching `ImageItem`'s own default
`(0, 0, ncols, nrows)` mapping).

Since `create()` delegates entirely to `'imshow'`'s own (every keyword
`heatmap` doesn't recognize flows straight through, via `DerivedKind`'s
merged-kwargs `**style`), the `LaColorBar` attachmenthappens
for free -- no code here does anything colorbar-specific.
"""
import numpy as np
from pyqtgraph.Qt import QtCore

from . import _base
from ..series import register_series_kind

_X_COORDS_ATTR = '_lafigure_x_coords'
_Y_COORDS_ATTR = '_lafigure_y_coords'


class HeatmapKind(_base.DerivedKind):
    """`ax.heatmap(matrix, x_coords=None, y_coords=None, ...)` -- see
    module docstring. `create`/`capabilities`/`to_dict`/`get_xy`/`set_xy`
    all come from `'imshow'` via `DerivedKind`'s defaults; only `setup()`
    (the coordinate-rect placement) and `to_dict` (to carry `x_coords`/
    `y_coords` through copy/paste and undo) are added here."""
    name = 'heatmap'
    base = 'imshow'

    def setup(self, plot_item, item, x_coords=None, y_coords=None, **kwargs):
        if x_coords is None and y_coords is None:
            return
        nrows, ncols = np.asarray(item.image).shape[:2]
        x_coords = np.arange(ncols, dtype=float) if x_coords is None else np.asarray(x_coords, dtype=float)
        y_coords = np.arange(nrows, dtype=float) if y_coords is None else np.asarray(y_coords, dtype=float)
        x0, x1 = float(x_coords[0]), float(x_coords[-1])
        y0, y1 = float(y_coords[0]), float(y_coords[-1])
        item.setRect(QtCore.QRectF(x0, y0, x1 - x0, y1 - y0))
        setattr(item, _X_COORDS_ATTR, x_coords)
        setattr(item, _Y_COORDS_ATTR, y_coords)

    def to_dict(self, item):
        d = self.base_kind.to_dict(item)
        x_coords = getattr(item, _X_COORDS_ATTR, None)
        y_coords = getattr(item, _Y_COORDS_ATTR, None)
        if x_coords is not None:
            d['style']['x_coords'] = np.array(x_coords, copy=True)
        if y_coords is not None:
            d['style']['y_coords'] = np.array(y_coords, copy=True)
        return d


register_series_kind(HeatmapKind())
