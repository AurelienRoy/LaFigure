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

"""lafigure.plotmatrix -- a MATLAB/pandas-style scatter-plot matrix: one
subplot per (column, column) pair of a dataset, laid out on the figure's
fractional grid via `fig.subplot(row, col)`, with a histogram on the
diagonal.

    axes = lafigure.plotmatrix(my_datasource)
    axes = lafigure.plotmatrix({'x': x, 'y': y, 'z': z}, kind='scatter')
    axes = lafigure.plotmatrix(array_2d, columns=['a', 'b', 'c'])

**The whole point of this function is the linkage, not the layout**: every
off-diagonal cell is built from the very SAME `DataSource` (never a private
per-cell copy), via `ax.<kind>(source, x=col_i, y=col_j)` -- exactly what
two ordinary series sharing one source already give you for free
(`selection.py`'s `RectBrush`/brushing.py's `_brush_key`, keyed on the
source itself). So brushing a rectangle of ROWS on one cell shows those
same rows highlighted on every other cell, diagonal histogram included in
spirit (though `hist` doesn't itself accept `'brush'`, see kinds/hist.py --
its bars simply don't participate) -- no bespoke linking code needed here
at all, this module is pure layout + construction.

`data` accepts:
- a `DataSource` directly (its own `.columns`, or a `columns=` subset/
  reorder of them);
- a `dict` of array-like columns (wrapped in a fresh `DataSource`);
- a 2-D array-like, shape `(n_samples, n_variables)` (wrapped in a fresh
  `DataSource`; `columns=` supplies the `n_variables` column names, default
  `'col0', 'col1', ...`).

Construction, like `add_subplot`/`ax.plot`: pushes no undo entry -- an
N-cell grid built by one `plotmatrix()` call is one action to create, not
N ones to undo individually (mirrors `_build_demo_subplots`'s own
convention, which isn't undoable either).
"""
import numpy as np

from .datasource import DataSource
from .figure import LaFigure

DEFAULT_KIND = 'scatter'
DEFAULT_DIAGONAL = 'hist'


def _source_and_columns(data, columns):
    """(DataSource, [column names]) from any of plotmatrix's three accepted
    input shapes -- see the module docstring."""
    if isinstance(data, DataSource):
        cols = list(columns) if columns is not None else list(data.columns)
        return data, cols
    if isinstance(data, dict):
        cols = list(columns) if columns is not None else list(data.keys())
        return DataSource(data), cols
    arr = np.asarray(data)
    if arr.ndim != 2:
        raise TypeError(
            "plotmatrix(data): data must be a DataSource, a dict of array-like "
            f"columns, or a 2-D array (n_samples, n_variables); got {type(data)!r} "
            f"with ndim={arr.ndim}"
        )
    n_vars = arr.shape[1]
    if columns is not None:
        names = list(columns)
        if len(names) != n_vars:
            raise ValueError(
                f"columns has {len(names)} names, but data has {n_vars} columns"
            )
    else:
        names = [f"col{i}" for i in range(n_vars)]
    return DataSource({name: arr[:, i] for i, name in enumerate(names)}), names


def plotmatrix(data, columns=None, figure=None, kind='scatter', diagonal='hist'):
    """A scatter-plot matrix over `data`'s columns (see the module
    docstring for the accepted shapes of `data`/`columns`).

    One subplot per (row column, col column) pair, placed at grid cell
    (row, col) via `figure.subplot(row, col)`; `figure` defaults to a new,
    empty `LaFigure`. `kind` (default 'scatter') is any registered
    off-diagonal `SeriesKind` name -- 'line', 'scatter', 'stairs', 'area',
    ... -- built as `ax.<kind>(source, x=col_i, y=col_j)`. `diagonal`
    (default 'hist') draws `ax.hist(source, x=col_i)` on the (i, i) cells;
    `None` leaves them empty (still returned).

    Returns the flat list of `Axes` created, row-major (row 0's N cells,
    then row 1's, ...) -- `len(result) == len(columns) ** 2`.
    """
    source, cols = _source_and_columns(data, columns)
    if diagonal not in ('hist', None):
        raise ValueError(f"plotmatrix: diagonal={diagonal!r} is not supported (use 'hist' or None)")
    fig = figure if figure is not None else LaFigure(empty=True)
    n = len(cols)
    last = n - 1
    axes_list = []
    for row, ycol in enumerate(cols):
        for col, xcol in enumerate(cols):
            ax = fig.subplot(row, col)
            if row == col:
                if diagonal == 'hist':
                    ax.hist(source, x=xcol)
            else:
                plot_fn = ax.plot if kind == 'line' else getattr(ax, kind)
                plot_fn(source, x=xcol, y=ycol)
            # Label only the outer edge, MATLAB/pandas plotmatrix style --
            # every inner cell's axes would otherwise repeat the same text.
            if row == last:
                ax.plot_item.setLabel('bottom', xcol)
            if col == 0:
                ax.plot_item.setLabel('left', ycol)
            axes_list.append(ax)
    return axes_list
