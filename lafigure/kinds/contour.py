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

"""R4-FIELD: the 'contour' SeriesKind -- marching-squares contour lines.

    ax.contour(matrix, levels=5, cmap='viridis', line_width=1.5)

`matrix` is a plain 2-D array, `matrix[row, col]`; `row` maps directly to
the Y coordinate and `col` to X (an ordinary, un-inverted grid-index
coordinate system -- unlike `kinds/imshow.py`, this kind never calls
`invertY`, so it does NOT visually match `ax.imshow` on the same array
unless the caller flips one of them; documented here rather than silently
assumed). `levels` is either an int `N` (`N` levels evenly spaced strictly
INSIDE the matrix's own finite min/max, via `np.linspace(lo, hi, N + 2)
[1:-1]` -- never exactly at the extremes, which would trace only the
matrix's own border/corners) or an explicit sequence of level values.

**Marching squares, from scratch in plain numpy** (no scipy/skimage, per
the round's own constraint) -- `marching_squares(matrix, level)` is the
core, independently testable function: for each of the `(nrows-1) *
(ncols-1)` grid cells, linearly interpolate along whichever of the 4 edges
the level crosses (comparing adjacent corner values) and connect the
resulting 2 (ordinary case) or 4 (checkerboard/"saddle" case, resolved by
comparing the level to the cell's own mean corner value -- the standard
convention) crossing points into 1 or 2 line segments. This deliberately
does NOT stitch per-cell segments into single continuous polylines --
drawing every cell's segment(s) independently for a level produces the
exact same visible contour line, since adjacent cells' segments always
share their common edge's interpolated point exactly (same two corner
values, same interpolation).

A `_base.CompositeSeriesItem` (the visual -- one polyline SET per level --
isn't a single existing item's shape); colored per level via
`_base.value_colors(levels_array, cmap=...)`, one solid color per level
mapped across the resolved levels' own min/max (a flat `matrix.min()`
level and a flat `matrix.max()` level would collapse to the same color
under this convention -- an accepted, documented simplification, since a
contour's own level spacing is rarely degenerate in practice).

**Known gaps, stated plainly rather than worked around:**
- Not click-selectable, `capabilities` is `{'copy'}` only -- no brush/fft/
  remove_average/fit (a scalar field on a grid isn't a set of
  independently selectable data points the way those actions assume).
- `Series.set_data`/`set_xy` is a documented no-op: a contour's real data
  is the 2-D matrix, not an (x, y) point pair, so there's no meaningful
  "replace x/y" operation to perform through that path (mirrors
  `CompositeSeriesItem`'s own allowance for a kind whose data doesn't fit
  x/y pairs -- see `_base.py`'s "not click-selectable" note for the
  general pattern this follows).
- No `to_plotly` converter for HTML export -- the generic `Scattergl`
  fallback in `html_export.py` (not owned by this package) would show
  nothing useful for a contour; a real converter (plotly has its own
  native `Contour` trace type) is future work, reported rather than
  attempted here.
"""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

from ._base import CompositeSeriesItem, value_colors
from ..series import SeriesKind, register_series_kind

DEFAULT_LEVELS = 5
DEFAULT_CMAP = 'viridis'
DEFAULT_LINE_WIDTH = 1.5


def _lerp_t(v0, v1, level):
    """Fraction along the v0->v1 edge where the field crosses `level`,
    clamped to [0, 1] (guards only against float round-off at an exact
    corner match -- the caller only invokes this on an edge the level is
    already known to cross)."""
    if v1 == v0:
        return 0.5
    return min(1.0, max(0.0, (level - v0) / (v1 - v0)))


def _cell_segments(a, b, c, d, level, j, i):
    """One grid cell at column `j`/row `i`, corners
    `a` = (j, i) top-left, `b` = (j+1, i) top-right,
    `c` = (j+1, i+1) bottom-right, `d` = (j, i+1) bottom-left
    -> a list of 0, 1 or 2 `((x0, y0), (x1, y1))` line segments where the
    bilinearly-interpolated field crosses `level`. See the module
    docstring for the saddle-case (4-crossing) resolution."""
    above = (a >= level, b >= level, c >= level, d >= level)
    if above[0] == above[1] == above[2] == above[3]:
        return []

    top = (j + _lerp_t(a, b, level), float(i)) if above[0] != above[1] else None
    right = (float(j + 1), i + _lerp_t(b, c, level)) if above[1] != above[2] else None
    bottom = (j + _lerp_t(d, c, level), float(i + 1)) if above[3] != above[2] else None
    left = (float(j), i + _lerp_t(a, d, level)) if above[0] != above[3] else None

    pts = [p for p in (top, right, bottom, left) if p is not None]
    if len(pts) == 2:
        return [(pts[0], pts[1])]
    if len(pts) == 4:
        # Checkerboard/"saddle" cell: all 4 edges cross. Resolve the
        # ambiguous pairing by the cell's own mean value vs. level -- the
        # standard marching-squares convention.
        avg = (a + b + c + d) / 4.0
        if avg >= level:
            return [(top, left), (right, bottom)]
        return [(top, right), (left, bottom)]
    return []   # unreachable given the all-same guard above; kept defensive


def marching_squares(matrix, level):
    """Every line segment where `matrix` (2-D array, `matrix[row, col]`,
    row=Y, col=X, in plain grid-index coordinates) crosses `level` --
    classic marching squares, cell by cell. Returns a list of
    `((x0, y0), (x1, y1))` tuples, not stitched into continuous polylines
    (see the module docstring for why that's fine to draw directly)."""
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("contour: matrix must be 2-D")
    nrows, ncols = matrix.shape
    segments = []
    for i in range(nrows - 1):
        for j in range(ncols - 1):
            a = matrix[i, j]
            b = matrix[i, j + 1]
            c = matrix[i + 1, j + 1]
            d = matrix[i + 1, j]
            if not (np.isfinite(a) and np.isfinite(b) and np.isfinite(c) and np.isfinite(d)):
                continue
            segments.extend(_cell_segments(float(a), float(b), float(c), float(d), float(level), j, i))
    return segments


def _resolve_levels(matrix, levels):
    """`levels` as int N -> N values evenly spaced strictly inside the
    matrix's own finite min/max; a sequence -> used as-is (float array)."""
    if isinstance(levels, (int, np.integer)):
        finite = matrix[np.isfinite(matrix)]
        if finite.size == 0:
            return np.zeros(0)
        lo, hi = float(finite.min()), float(finite.max())
        if lo == hi:
            return np.array([lo])
        return np.linspace(lo, hi, int(levels) + 2)[1:-1]
    return np.asarray(levels, dtype=float)


class ContourItem(CompositeSeriesItem):
    """One `marching_squares` polyline set per resolved level, each drawn
    in its own `_base.value_colors` color. See the module docstring."""

    def __init__(self, matrix, levels, pen=None, name=None, cmap=DEFAULT_CMAP,
                 line_width=DEFAULT_LINE_WIDTH):
        super().__init__(name=name, pen=pen)
        self.line_width = float(line_width)
        self._set_data(matrix, levels, cmap)

    def _set_data(self, matrix, levels, cmap):
        self._matrix = np.asarray(matrix, dtype=float)
        self._levels_spec = levels
        self._cmap = cmap
        self._levels = _resolve_levels(self._matrix, levels)
        if len(self._levels):
            brushes, _ = value_colors(self._levels, cmap=cmap)
            self._level_colors = [b.color() for b in brushes]
        else:
            self._level_colors = []
        self._segments_by_level = [marching_squares(self._matrix, lv) for lv in self._levels]
        self.invalidate()

    def _bounds(self):
        nrows, ncols = self._matrix.shape
        if nrows < 2 or ncols < 2:
            return None
        return 0.0, float(ncols - 1), 0.0, float(nrows - 1)

    def _paint(self, painter):
        for color, segments in zip(self._level_colors, self._segments_by_level):
            if not segments:
                continue
            pen = pg.mkPen(color, width=self.line_width)
            pen.setCosmetic(True)
            painter.setPen(pen)
            for (x0, y0), (x1, y1) in segments:
                painter.drawLine(QtCore.QPointF(x0, y0), QtCore.QPointF(x1, y1))

    def set_xy(self, x, y):
        """No-op -- a contour's data is the 2-D matrix, not an (x, y)
        point pair. See the module docstring's "Known gaps"."""
        pass


class ContourKind(SeriesKind):
    name = 'contour'
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               levels=DEFAULT_LEVELS, cmap=DEFAULT_CMAP, line_width=DEFAULT_LINE_WIDTH, **style):
        matrix = x
        if matrix is None:
            raise TypeError("contour(matrix, levels=...): matrix is required")
        item = ContourItem(matrix, levels, pen=pen, name=name, cmap=cmap, line_width=line_width)
        plot_item.addItem(item)
        return item

    def to_dict(self, item):
        return {
            'x': np.array(item._matrix, copy=True),
            'y': None,
            'pen': item.opts.get('pen'),
            'name': item.name(),
            'style': {
                # The RESOLVED level values (not the original int N), so a
                # round trip through a copy of the matrix reproduces the
                # exact same contour lines rather than re-resolving N
                # levels against whatever the copy's own min/max computes to.
                'levels': [float(v) for v in item._levels],
                'cmap': item._cmap,
                'line_width': item.line_width,
            },
        }

    def get_xy(self, item):
        return item.getData()

    def set_xy(self, item, x, y):
        item.set_xy(x, y)


register_series_kind(ContourKind())
