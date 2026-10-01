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

"""ax.bubblechart3d(x, y, z=z, size=values, pen=color) -- points in a 3D
cell sized by a per-point value (MATLAB's bubblechart3d), or
ax.bubblechart3d(source, x='a', y='b', z='c', size='col') for columns of a
DataSource (then brushing links its rows with every other series of that
source, 2D or 3D, exactly like kinds/scatter3d.py -- Kind3D's rows_in_rect/
show_rows don't care which Series3DItem subclass they're given). Only on a
subplot made with axes_type='3d' (Kind3D._check_plot, via create()).

**Per-point size is DEGRADED, not exact -- read this before assuming it
draws a genuine per-vertex size.** view3d.py's rendering primitives (both
backends) only support ONE size per *primitive* (one GL draw call's
`u_point_size` uniform, or the QPainter fallback's single pen width per
primitive -- which even averages per-vertex COLOR down to one flat color
per primitive, see view3d.paint_fallback). There is no per-vertex point
size anywhere in this renderer, unlike pyqtgraph's own 2D ScatterPlotItem
(which is how the 2D `bubblechart` kind, R4-SCAT, gets an exact per-point
size for free). Rather than either (a) silently ignoring `size=` and
drawing every bubble identically -- indistinguishable from a plain
scatter3d -- or (b) claiming a per-point size that doesn't actually render
differently, `Bubble3DItem` buckets the per-point values (through
`_base.size_scale`, so it's area- not diameter-proportional) into up to
`Bubble3DItem.SIZE_BUCKETS` discrete groups and draws one Primitive per
non-empty bucket, each at its own point size. This is an honest, coarse
approximation: points within one bucket render identically, but different
buckets are genuinely, visibly different sizes on screen (checked against
real rendered pixels in this package's own test, via the QPainter
fallback -- there is no GL context under QT_QPA_PLATFORM=offscreen,
CLAUDE.md bug #10).

z is a keyword because Axes._plot_kind routes exactly two positional
coordinates (x, y) to every kind, same as scatter3d/line3d/plot3."""
import numpy as np

from ..series import register_series_kind
from ..view3d import Kind3D, Primitive, Series3DItem
from ._base import size_scale

DEFAULT_LO_PX = 4.0
DEFAULT_HI_PX = 24.0


class Bubble3DItem(Series3DItem):
    """A Series3DItem whose points are drawn at a size approximating a
    per-point value -- see the module docstring for the degrade mechanism
    and why it's necessary. `raw_sizes` is the per-point value column,
    same length and same row order as `xyz`; `lo_px`/`hi_px` are the pixel
    range `_base.size_scale` maps it into before bucketing.

    Sizes are pre-scaled from the FULL `raw_sizes` array once, at
    construction, not re-scaled from whatever subset happens to be
    visible at draw time -- so a bubble's apparent size stays stable as
    Hide Brushed Points / src.filter narrow what's drawn, instead of
    rescaling (and hence visually changing) every time the visible subset
    changes. Known limitation: if the item's positions are later replaced
    wholesale with a different-length array (Series.set_data on a 3D
    series -- an unusual, edge-case path; see Kind3D.set_xy's own
    docstring), `raw_sizes`/the cached pixel sizes are NOT re-derived and
    can go out of alignment with the new positions; no round4 kind
    package exercises that path today."""
    SIZE_BUCKETS = 6

    def __init__(self, xyz, raw_sizes, pen=None, name=None, source=None,
                 lo_px=DEFAULT_LO_PX, hi_px=DEFAULT_HI_PX):
        raw_sizes = np.asarray(raw_sizes, dtype=float).ravel()
        pixel_sizes = size_scale(raw_sizes, lo_px, hi_px)
        super().__init__(xyz, pen=pen, name=name,
                         size=float(pixel_sizes.mean()) if len(pixel_sizes) else lo_px,
                         source=source)
        self._raw_sizes = raw_sizes
        self._pixel_sizes = pixel_sizes
        self.lo_px, self.hi_px = float(lo_px), float(hi_px)

    def _build_primitives(self, xyz):
        if not len(xyz):
            return []
        visible = self.visible_entries()
        px = self._pixel_sizes if visible is None else self._pixel_sizes[visible]
        color = self.color()
        lo, hi = float(px.min()), float(px.max())
        if hi <= lo:
            # Every point maps to (about) the same pixel size -- one
            # primitive, no bucketing needed.
            return [Primitive('points', xyz, color, float(px[0]))]
        n_buckets = min(self.SIZE_BUCKETS, len(xyz))
        edges = np.linspace(lo, hi, n_buckets + 1)
        bucket = np.clip(np.digitize(px, edges[1:-1], right=True), 0, n_buckets - 1)
        prims = []
        for b in range(n_buckets):
            mask = bucket == b
            if not mask.any():
                continue
            prims.append(Primitive('points', xyz[mask], color, float(px[mask].mean())))
        return prims


class BubbleChart3DKind(Kind3D):
    name = 'bubblechart3d'

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               z=None, size=None, lo_px=DEFAULT_LO_PX, hi_px=DEFAULT_HI_PX):
        self._check_plot(plot_item)
        x = self._column(x, None, None, None, 'x')
        y = self._column(y, None, None, len(x), 'y')
        z = self._column(z, source, rows, len(x), 'z')
        sizes = self._column(size, source, rows, len(x), 'size')
        item = Bubble3DItem(np.column_stack([x, y, z]), sizes, pen=pen, name=name,
                            source=source, lo_px=lo_px, hi_px=hi_px)
        plot_item.addItem(item, ignoreBounds=True)
        return item

    def to_dict(self, item):
        xyz = np.array(item.positions(), copy=True)
        return {'x': xyz[:, 0], 'y': xyz[:, 1], 'pen': item.opts['pen'], 'name': item.name(),
                'style': {'z': xyz[:, 2], 'size': np.array(item._raw_sizes, copy=True),
                         'lo_px': item.lo_px, 'hi_px': item.hi_px}}


register_series_kind(BubbleChart3DKind())
