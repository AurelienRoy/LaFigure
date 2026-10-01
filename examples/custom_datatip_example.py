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

"""Four subplots showing `ax.datatip` (lafigure/console.py), the format
that drives a data-cursor annotation's text -- normally set once, then
just used implicitly every time a user drops a "cursor" annotation on
that subplot from the toolbar. Set it BEFORE placing a cursor; it has no
effect on cursors already placed.

    ax.datatip = "ID: {id} | Value: {value:.2f}"   # a str.format string
    ax.datatip = lambda row: f"{row.sensor}: ..."   # or a callable

Either form is called with one `RowAccessor` (console.py): the plotted
point's own `DataSource` row, dict-like (`row['id']`) AND attribute-like
(`row.id`) -- every column of that source is available by name. A format
string is also just a plain string, so it can embed a literal newline for
a multi-line datatip (editable_text.py's annotation text already supports
multiple lines).

**Format string vs. callable -- when to use which.** A format string is
enough for "pick a few columns, maybe round a float" and, unlike a
callable, can be written into a config file, shown in a UI, or (in
principle; not built yet) translated into a plotly `hovertemplate` for
HTML export (CLAUDE.md's Phase 4: "ax.datatip format strings translate
directly to a plotly hovertemplate"). A Python callable can express
anything (conditional text, cross-column math, unit conversion) but is
Python code living in memory -- `html_export.py` can't run it inside a
static HTML page, so an HTML export of a callable-datatip subplot falls
back to a generic x/y + every-column hover instead of the exact text
shown live in the app. Both forms are demonstrated below so the
difference is visible side by side.

A data cursor is normally placed interactively (pick "Data Cursor" from
the toolbar's "Annotate" dropdown, click a point). A script that wants
one without a mouse mirrors annotation_ops.py's own placement code: find
the nearest sample, compute its text through `datatip_text` (so the
configured `ax.datatip` is actually exercised, not hand-formatted here),
then call `LaFigure._create_annotation('cursor', 'axes', ...)` the same
way annotation_ops.py's own placement handler does -- see CLAUDE.md's
"Annotations" feature entry for why `_create_annotation` is the one
documented exception to "never call a private method from example code".

Run (from anywhere -- this file adds the repo root to sys.path itself,
since lafigure isn't pip-installed):
    python examples/custom_datatip_example.py
"""
import os
import sys

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lafigure
_debug_log = lafigure.enable_debug_mode()
print(f"Debug log: {_debug_log}")
from lafigure.console import datatip_text


def _place_cursor_2d(fig, ax, series, row_idx, offset):
    """Mirrors annotation_ops.py's `_handle_placement_click`'s 'cursor'
    branch for a 2D curve: compute the text through `datatip_text` (so
    `ax.datatip` is actually exercised) and drop the annotation at the
    curve's own row_idx-th sample."""
    item = series.item
    x, y = float(item.xData[row_idx]), float(item.yData[row_idx])
    text = datatip_text(fig, ax.plot_item, item, row_idx, x, y)
    fig._create_annotation('cursor', 'axes', ax.plot_item,
                            QtCore.QPointF(x, y), QtCore.QPointF(*offset), text=text)


def _place_cursor_3d(fig, ax, series, row_idx, offset):
    """Same idea as `_place_cursor_2d`, but for a 3D scatter -- mirrors
    annotation_ops.py's 3D 'cursor' branch: the cursor's local position on
    an 'axes'-anchored 3D cell is the item's current PROJECTED screen
    position (view3d.py's own pinned-pixel convention), read via the
    ViewBox's cached `projected()`, never the raw 3D (x, y, z)."""
    item = series.item
    xyz = item.positions()[row_idx]
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    vb = ax.plot_item.getViewBox()
    sx, sy, _front = vb.projected(item)
    local_pos = QtCore.QPointF(float(sx[row_idx]), float(sy[row_idx]))
    text = datatip_text(fig, ax.plot_item, item, row_idx, x, y, z=z)
    fig._create_annotation('cursor', 'axes', ax.plot_item, local_pos,
                            QtCore.QPointF(*offset), text=text)


def main():
    app = QtWidgets.QApplication(sys.argv)
    rng = np.random.default_rng(7)

    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- custom data-cursor formats")

    # -- subplot 1: a format string pulling in two extra columns ----------
    n = 60
    source1 = lafigure.DataSource({
        'id': np.arange(n),
        'x': rng.uniform(0, 10, n),
        'y': rng.uniform(0, 10, n),
        'value': rng.normal(50, 12, n),
    })
    ax1 = fig.subplot(0, 0, title="Format string: ID + value")
    s1 = ax1.scatter(source1, x='x', y='y', size=7,
                     symbolBrush=pg.mkBrush(70, 120, 200, 180), symbolPen=None)
    ax1.datatip = "ID: {id} | Value: {value:.2f}"
    _place_cursor_2d(fig, ax1, s1, row_idx=0, offset=(1.5, 1.5))

    # -- subplot 2: a Python callable, free-form text ----------------------
    sensors = np.array(['temp', 'pressure', 'humidity'])
    source2 = lafigure.DataSource({
        'x': rng.uniform(0, 10, n),
        'y': rng.uniform(0, 10, n),
        'sensor': sensors[rng.integers(0, len(sensors), n)],
        'reading': rng.uniform(0, 100, n),
        'unit': np.where(rng.integers(0, len(sensors), n) == 0, 'C', 'units'),
    })
    ax2 = fig.subplot(0, 1, title="Callable: free-form text")
    s2 = ax2.scatter(source2, x='x', y='y', size=7,
                     symbolBrush=pg.mkBrush(200, 90, 60, 180), symbolPen=None)
    # A callable receives one RowAccessor -- dict- AND attribute-style
    # access to every column of this point's row. See the module
    # docstring above for why this form can't be replayed in HTML export.
    ax2.datatip = lambda row: f"{row.sensor}: {row.reading:.1f} {row.unit}"
    _place_cursor_2d(fig, ax2, s2, row_idx=3, offset=(1.5, 1.5))

    # -- subplot 3: a multi-line format string ------------------------------
    categories = np.array(['A', 'B', 'C'])
    source3 = lafigure.DataSource({
        'x': rng.uniform(0, 10, n),
        'y': rng.uniform(0, 10, n),
        'category': categories[rng.integers(0, len(categories), n)],
        'value': rng.normal(0, 1, n),
    })
    ax3 = fig.subplot(0, 2, title="Format string: multi-line")
    s3 = ax3.scatter(source3, x='x', y='y', size=7,
                     symbolBrush=pg.mkBrush(90, 170, 90, 180), symbolPen=None)
    ax3.datatip = "Category {category}\nvalue = {value:.3f}"
    _place_cursor_2d(fig, ax3, s3, row_idx=10, offset=(1.5, -2.0))

    # -- subplot 4: a 3D curve -- {x}/{y}/{z} are available too -------------
    t = np.linspace(0, 6 * np.pi, 400)
    x3, y3, z3 = np.cos(t), np.sin(t), t / 4
    ax4 = fig.subplot(1, 0, axes_type='3d', title="3D: format string with z")
    s4 = ax4.scatter3d(x3, y3, z=z3, pen=(150, 80, 200), size=4)
    ax4.datatip = "x={x:.2f}, y={y:.2f}, z={z:.2f}"
    _place_cursor_3d(fig, ax4, s4, row_idx=200, offset=(24, -24))

    fig.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
