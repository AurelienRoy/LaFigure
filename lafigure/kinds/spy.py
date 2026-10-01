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

"""the 'spy' SeriesKind -- MATLAB's `spy(matrix)`: a scatter of the
nonzero entries of a 2-D matrix, one point per nonzero, at (column, row).

    ax.spy(matrix)

Built as a `_base.DerivedKind`-style delegation to the registered 'scatter'
kind (not literally `_base.DerivedKind` itself, since converting a 2-D
matrix into point coordinates has to happen BEFORE the base kind's `create`
is called, which `DerivedKind.create` doesn't have a hook for early enough
-- see its own docstring: `setup()` only runs AFTER the base already built
the item). `create()` here does the matrix -> (x, y) conversion itself, then
calls `SERIES_KINDS['scatter'].create(...)` directly -- the same "delegate,
don't hand-roll a new item" reuse this round requires, just via an explicit
call instead of subclassing `DerivedKind`.

**Y inverted, matching `kinds/imshow.py`'s own convention** (see its module
docstring): `plot_item.getViewBox().invertY(True)` is applied so row 0
sits at the TOP and row index increases downward, same as
`matplotlib.pyplot.spy`/`imshow` (`origin='upper'`) -- rather than the
plain-Cartesian "row 0 at the bottom" a bare scatter of `(col, row)` would
otherwise show.

**Two entry points into `create()`, disambiguated by `y`** (frozen, see
tests): `y is None` means "x is the whole 2-D matrix -- extract the nonzero
entries" (`ax.spy(matrix)`, via `Axes._plot_kind`'s single-array-argument
call); `y is not None` means "x/y are ALREADY the extracted (col, row) point
arrays" -- exactly the shape `to_dict()` (delegated to the scatter kind's
own) returns, so a copy/paste or undo/redo's `create()` call round-trips
through the second branch without re-scanning a matrix that no longer
exists on the item at all (only the extracted points do -- `spy` does not
keep the original matrix around after construction, so it cannot report the
original cell VALUES back, only the nonzero PATTERN, which is all `spy`
ever showed in the first place).

**Known gaps**: `capabilities` includes 'brush' because `get_xy` (the
inherited SeriesKind default) returns exactly the plotted (col, row)
points, a real parallel 1-D pair -- brushing/deleting one acts on that
matrix ENTRY's position, not on any underlying value (spy never drew one).
`to_plotly`/HTML export has no dedicated converter (falls back to the
generic Scattergl one, which will still show the right points since they
are plain x/y, just without the Y-inversion applied by
`plot_item.getViewBox().invertY` -- a plotly-side fix, not attempted here).
"""
import numpy as np

from ..series import SERIES_KINDS, SeriesKind, register_series_kind

DEFAULT_SYMBOL = 'o'
DEFAULT_SIZE = 4.0


class SpyKind(SeriesKind):
    """Nonzero entries of a matrix as a scatter -- see module docstring."""
    name = 'spy'
    capabilities = frozenset({'brush', 'copy'})

    def create(self, plot_item, x, y=None, pen=None, name=None, source=None, rows=None,
               size=DEFAULT_SIZE, symbol=DEFAULT_SYMBOL, **style):
        if y is None:
            matrix = np.asarray(x)
            row_idx, col_idx = np.nonzero(matrix)
            xs = col_idx.astype(float)
            ys = row_idx.astype(float)
        else:
            xs = np.asarray(x, dtype=float)
            ys = np.asarray(y, dtype=float)

        item = SERIES_KINDS['scatter'].create(
            plot_item, xs, ys, pen=pen, name=name, source=source, rows=rows,
            size=size, symbol=symbol, **style)
        # Row 0 at the top, matching kinds/imshow.py's own convention.
        plot_item.getViewBox().invertY(True)
        return item

    def to_dict(self, item):
        return SERIES_KINDS['scatter'].to_dict(item)


register_series_kind(SpyKind())
