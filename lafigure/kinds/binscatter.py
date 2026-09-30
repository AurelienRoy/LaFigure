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

"""R4-SCAT: the 'binscatter' SeriesKind -- a large (x, y) point cloud binned
into a 2-D histogram (`_base.bin2d`) and shown as one point per non-empty
bin, colored by that bin's density.

    ax.binscatter(x, y, bins=50)
    ax.binscatter(x, y, bins=(40, 20), cmap='inferno')

**Design choice, as the work package explicitly asks to justify (colored
scatter of bin centers vs. an imshow-style image)**: this kind draws a
COLORED SCATTER OF BIN CENTERS, not an image. Reasons:

1. **Maximum reuse.** A colored scatter needs nothing beyond what
   bubblechart.py already built (`SERIES_KINDS['scatter'].create` +
   `_base.value_colors` + a `LaColorBar`) -- literally the same pattern,
   swapping `size_scale` for a plain fixed marker size. An image-based
   binscatter would need its own, separate `ImageItem`-building code
   duplicating `kinds/imshow.py` almost entirely, for the same visual
   information.
2. **Stays a real, interactive series.** A `pg.ImageItem` (imshow's own
   item) is not click-selectable and does not support brushing in this
   codebase yet (see imshow.py's own module docstring and CLAUDE.md's 3D/
   imshow "known gaps" notes) -- a scatter of bin centers IS a real
   `pg.PlotDataItem`, so it inherits click-selection and brush/delete for
   free, letting a user interact with individual density bins the same way
   as any other scatter-derived kind here.
3. **No empty-bin bookkeeping.** An image must represent every cell,
   including empty ones (typically as a masked/zero-alpha pixel); a scatter
   of bin centers simply omits a bin with zero count -- `np.nonzero(counts)`
   -- which is both simpler code and a cleaner picture for a scatter plot
   that is mostly sparse in some regions.

**Round-trip**: the RAW `(x, y)` SAMPLE arrays (not the derived bin centers)
are stashed on the item and returned by `to_dict()`, together with `bins` in
`style`, so `create()` re-bins from scratch and reproduces the identical bin
centers/colors on copy/paste or undo/redo -- feeding already-binned centers
back into `bin2d` a second time would not reproduce the same picture (it
would bin the bin centers themselves, at a different sample density).

**Colorbar**: always attached (unlike bubblechart, a binscatter's whole
point is the density mapping, so there is no "no color column" case) via
the same `LaColorBar` pattern as bubblechart.py -- see that module's
docstring for why `setImageItem` is called with an EMPTY list rather than
the scatter item itself.

**Known gaps**: 'brush' is claimed because `get_xy` (the inherited
SeriesKind default) returns the bin centers actually plotted -- a real,
parallel 1-D pair -- but a brush/delete on a binscatter acts on BIN
CENTERS, never the original raw samples that produced them (there is no way
back from "this bin was deleted" to "these original samples are gone");
document this for a caller, don't silently imply otherwise. `to_plotly`/HTML
export has no dedicated converter (falls back to the generic Scattergl one).
"""
import numpy as np
import pyqtgraph as pg

from ..colorbar import LaColorBar
from ..series import SERIES_KINDS, SeriesKind, register_series_kind
from ._base import bin2d, value_colors

DEFAULT_CMAP = 'inferno'
DEFAULT_BINS = 50
DEFAULT_SIZE = 10.0
DEFAULT_SYMBOL = 's'


class BinScatterKind(SeriesKind):
    """A 2-D histogram of (x, y) drawn as one colored point per non-empty
    bin -- see module docstring for the design choice and round-trip
    scheme."""
    name = 'binscatter'
    capabilities = frozenset({'brush', 'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               bins=DEFAULT_BINS, cmap=DEFAULT_CMAP, size=DEFAULT_SIZE,
               symbol=DEFAULT_SYMBOL, **style):
        raw_x = np.asarray(x, dtype=float)
        raw_y = np.asarray(y, dtype=float)
        counts, x_edges, y_edges = bin2d(raw_x, raw_y, bins=bins)
        xi, yi = np.nonzero(counts)
        centers_x = (x_edges[xi] + x_edges[xi + 1]) / 2.0
        centers_y = (y_edges[yi] + y_edges[yi + 1]) / 2.0
        density = counts[xi, yi]

        brushes, levels = value_colors(density, cmap=cmap)

        item = SERIES_KINDS['scatter'].create(
            plot_item, centers_x, centers_y, pen=pen, name=name,
            size=size, symbol=symbol, symbolBrush=brushes, **style)

        item._lafigure_binscatter_raw_x = raw_x
        item._lafigure_binscatter_raw_y = raw_y
        item._lafigure_binscatter_density = density
        item._lafigure_bins = bins
        item._lafigure_cmap = cmap

        color_map_obj = cmap if isinstance(cmap, pg.ColorMap) else pg.colormap.get(cmap)
        colorbar = LaColorBar(colorMap=color_map_obj, label=name)
        # Empty img_list -- see module docstring (mirrors bubblechart.py)
        # on why setImageItem is not handed the scatter item itself.
        colorbar.setImageItem([], insert_in=plot_item)
        colorbar.attach(item, lambda: item._lafigure_binscatter_density, plot_item)
        colorbar.set_levels(*levels)
        item._lafigure_colorbar = colorbar
        return item

    def to_dict(self, item):
        scatter_dict = SERIES_KINDS['scatter'].to_dict(item)
        raw_x = getattr(item, '_lafigure_binscatter_raw_x', None)
        raw_y = getattr(item, '_lafigure_binscatter_raw_y', None)
        style = {
            'bins': getattr(item, '_lafigure_bins', DEFAULT_BINS),
            'cmap': getattr(item, '_lafigure_cmap', DEFAULT_CMAP),
            'size': scatter_dict['style'].get('size', DEFAULT_SIZE),
            'symbol': scatter_dict['style'].get('symbol', DEFAULT_SYMBOL),
        }
        return {
            'x': np.array(raw_x, copy=True) if raw_x is not None else scatter_dict['x'],
            'y': np.array(raw_y, copy=True) if raw_y is not None else scatter_dict['y'],
            'pen': scatter_dict['pen'],
            'name': scatter_dict['name'],
            'style': style,
        }


register_series_kind(BinScatterKind())
