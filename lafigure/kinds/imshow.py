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

"""The 'imshow' SeriesKind -- a heatmap/image, with a colorbar.

    ax.imshow(matrix, cmap='viridis', levels=None)

**Orientation convention** (checked empirically against the installed
pyqtgraph 0.14 -- ImageItem's default `axisOrder` is 'col-major', which
transposes a plain numpy row/column matrix relative to what
matplotlib.pyplot.imshow shows for the same array): the item is built with
`axisOrder='row-major'`, under which pyqtgraph stores `item.image` as
exactly the input matrix, no transpose (verified: `item.image is matrix`'s
data, `np.array_equal(item.image, matrix)` for an asymmetric (3, 5) input).
`matrix[row, col]` therefore has axis 0 = row = vertical, axis 1 = col =
horizontal, matching numpy/matplotlib indexing. The subplot's ViewBox is
also set to `invertY(True)`, so row 0 is drawn at the TOP and row index
increases downward -- the same default visual orientation as
`matplotlib.pyplot.imshow` (`origin='upper'`).

**`.x`/`.y` convention**: `Series.x` is the 2D matrix itself (a read-only
view of `item.image`); `Series.y` is always `None`. There's no separate
per-axis coordinate array in this pass -- an image has no natural per-row
index for brushing/set_data yet (that's a later design question, out of
this package's scope per its brief).

**Colorbar**: a `colorbar.LaColorBar` (R4-CBAR, 2026-09-30) -- a
`pg.ColorBarItem` subclass with two fixed dashed lines at the plotted
matrix's own min/max (live, via `LaColorBar.attach`) and two independently
draggable level-limit lines (dragging one never perturbs the other's
value -- see colorbar.py's own module docstring for the full model),
attached to the SAME subplot via `ColorBarItem.setImageItem(item,
insert_in=plot_item)` (inherited, unchanged). That call inserts the
colorbar into `plot_item.layout` -- pyqtgraph's own *internal*
QGraphicsGridLayout that every PlotItem already keeps for its axes/title
(rows/columns around its ViewBox cell), not lafigure's own fractional grid
(lafigure/grid.py, lafigure/layout.py) -- so this needed no change to
either of those files. The colorbar is kept reachable at
`item._lafigure_colorbar` for tests/introspection (not read anywhere else
in this package).

**Known gap in the Series abstraction (reported, not worked around):**
`Series.name` (series.py) does `self.item.name()` unconditionally --
`pg.ImageItem` has no `.name()` method (unlike PlotDataItem/BarGraphItem's
`.opts`-based one), so `some_imshow_series.name` raises AttributeError.
None of this package's own code, nor _add_series/_add_series_from_dict,
nor the acceptance tests, read `.name` on an image series (the 'copy'
capability only exercises to_dict/create, not naming), so this is not
blocking -- but a future package (e.g. a rename UI, or WP-J generalizing
selection) will hit it the moment it calls `.name` on an imshow Series.
Minimal fix, for whoever owns series.py next: change `Series.name` to
`getattr(self.item, 'name', lambda: None)()`, mirroring how this file's
own `get_xy`/`set_xy` overrides already route around ImageItem's missing
PlotDataItem protocol.
"""
import numpy as np
import pyqtgraph as pg

from ..colorbar import LaColorBar
from ..series import SeriesKind, register_series_kind

DEFAULT_CMAP = 'viridis'


class ImshowKind(SeriesKind):
    """A heatmap/image series, `ax.imshow(matrix)` -- see module docstring
    for the axis-order and colorbar-attachment design decisions."""
    name = 'imshow'
    # Brushing/fft/remove_average/fit don't apply to a 2D image in this
    # pass -- a much bigger design question (per-pixel rows?), out of scope.
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               cmap=DEFAULT_CMAP, levels=None, **style):
        """x is the 2D matrix (imshow's single-array convention, like a
        histogram's raw samples -- y is unused). `cmap`: a pyqtgraph
        colormap name (str, e.g. 'viridis') or a pg.ColorMap instance.
        `levels`: (min, max) shown range; None autoscales from the data."""
        matrix = np.asarray(x)
        item = pg.ImageItem(matrix, axisOrder='row-major')
        color_map = cmap if isinstance(cmap, pg.ColorMap) else pg.colormap.get(cmap)
        item.setColorMap(color_map)
        if levels is not None:
            item.setLevels(levels)
        plot_item.addItem(item)
        plot_item.getViewBox().invertY(True)  # row 0 at the top, matplotlib-style

        colorbar = LaColorBar(colorMap=color_map, label=name)
        colorbar.setImageItem(item, insert_in=plot_item)
        # values_fn reads item.image fresh every call (never cached), so the
        # two fixed dashed lines track set_xy/setImage -- see attach()'s own
        # docstring for the other two live-refresh paths.
        colorbar.attach(item, lambda: item.image, plot_item)
        # Kept for to_dict()/tests/introspection; nothing else in this
        # module reads it back off the item.
        item._lafigure_colorbar = colorbar
        item._lafigure_cmap = cmap  # the original spec (name or ColorMap), for a faithful to_dict
        return item

    def to_dict(self, item):
        return {
            'x': np.array(item.image, copy=True),
            'y': None,
            'pen': None,
            'name': None,
            'style': {
                'cmap': getattr(item, '_lafigure_cmap', DEFAULT_CMAP),
                'levels': item.getLevels(),
            },
        }

    def get_xy(self, item):
        return item.image, None

    def set_xy(self, item, x, y):
        item.setImage(np.asarray(x))


register_series_kind(ImshowKind())
