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

"""Backing logic for the Figure Manager's "Variable Browser" tab
(manager.py), kept in its own module so layout.py (the drag/drop target)
doesn't need to import manager.py, and manager.py (already large) doesn't
grow a second, unrelated responsibility.

There is no process-wide registry of DataSources anywhere in this project
(see datasource.py) and no "variable name" concept -- a DataSource is just
a dict of named columns, and a plain-array series (ax.plot(arr)) silently
builds a *private* DataSource whose columns are always literally named
'x'/'y'/'z' (Series.source, series.py). Listing those would flood the
table with meaningless duplicate names, so collect_variables below only
ever looks at a series' EXPLICIT source (Series._source, not the
lazily-built private one) -- i.e. only data a script actually shared via
`ax.plot(my_source, x=..., y=...)`.

There is likewise no "time" convention anywhere else in the codebase;
default_time_column below is this feature's own, local convention (a
column literally named "time", case-insensitive), not a project-wide one.

A drop/selection is restricted to ONE DataSource at a time (a deliberate
scope decision, confirmed with the user): plotting columns from two
unrelated sources against each other isn't something this feature offers
a gesture for.
"""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets

from .axes import DEFAULT_COLORS
from . import grid as grid_module

VARIABLE_MIME_TYPE = 'application/x-lafigure-variable'

# The actual drag payload -- a list of (DataSource, column_name) tuples --
# never fits in a QMimeData (which only carries bytes), and this is a
# single-process desktop app with at most one drag in flight at a time, so
# a plain module-level list, written right before a QDrag starts and read
# back on drop, is enough; the QMimeData's own bytes are just a format tag
# so hasFormat()/acceptProposedAction() have something to check.
_drag_payload = []


def set_drag_payload(payload):
    global _drag_payload
    _drag_payload = list(payload)


def get_drag_payload():
    return list(_drag_payload)


# -- variable discovery ----------------------------------------------------

def collect_variables(registry):
    """Every (DataSource, column) pair currently in use by an explicit
    source somewhere in an open figure, deduplicated by the source's own
    identity -- so two series sharing one DataSource list its columns once,
    not twice. Returns a list of (source, column, n_rows, dtype_str)."""
    sources = {}
    for fig in registry.figures:
        for plot_item in fig.plots:
            for series in fig._series_on(plot_item):
                src = series._source  # the EXPLICIT source only -- see module docstring
                if src is not None:
                    sources[id(src)] = src
    rows = []
    for src in sources.values():
        for col in src.columns:
            rows.append((src, col, len(src), str(src[col].dtype)))
    return rows


def default_time_column(source):
    """A column literally named "time" (case-insensitive), or None -- the
    caller then falls back to a plain row index as X."""
    for name in source.columns:
        if name.lower() == 'time':
            return name
    return None


# -- curve/subplot construction, undoable -----------------------------------

def _make_curve(fig, plot_item, source, x_col, y_col):
    """One source-linked 'line' series: Y is source[y_col]; X is
    source[x_col] if a real column was resolved, else the plain row index
    (kept as a plain array, not a fabricated DataSource column, so this
    never mutates the user's own source) -- both still reference the same
    `source`/`rows`, so brushing/linking on y_col still works."""
    rows = np.arange(len(source), dtype=np.intp)
    ys = source[y_col][rows]
    xs = source[x_col][rows] if x_col is not None else rows.astype(float)
    existing = len(fig._series_on(plot_item))
    pen = pg.mkPen(DEFAULT_COLORS[existing % len(DEFAULT_COLORS)], width=1)
    return fig._add_series(plot_item, 'line', xs, ys, pen=pen, name=y_col,
                           source=source, rows=rows, columns=(x_col, y_col))


def create_new_subplot_with_variables(fig, source, y_columns, x_col):
    """One new subplot (first empty grid cell, else a new row -- the same
    placement add_new_subplot uses), with one curve per y_columns entry,
    all y_columns vs x_col (or the row index). One undo entry: undo removes
    the whole subplot, redo rebuilds it the same way -- nothing here needs
    delete_subplot's snapshot/restore machinery, since nothing is ever
    deleted; `source` is the same live object both times."""
    if not y_columns:
        return
    cell = grid_module.first_empty_cell(list(fig.boxes.values()),
                                        fig._n_tracks('row'), fig._n_tracks('col'))
    row, col = cell if cell is not None else (fig._n_tracks('row'), 0)
    xlabel = x_col or 'index'
    title = (f"{y_columns[0]} vs {xlabel}" if len(y_columns) == 1
             else f"{len(y_columns)} variables vs {xlabel}")

    def build():
        plot_item = fig.add_subplot(row=row, col=col, title=title)
        plot_item.setLabel('bottom', xlabel)
        for y_col in y_columns:
            _make_curve(fig, plot_item, source, x_col, y_col)
        if len(y_columns) > 1 and plot_item.legend is None:
            fig._show_legend(plot_item)
        fig.focused_plot = plot_item
        fig._mark_active(plot_item)
        return plot_item

    holder = {'plot': build()}

    def undo_fn():
        p = holder.get('plot')
        if p is not None:
            fig._remove_subplot(p)
            holder['plot'] = None

    def redo_fn():
        holder['plot'] = build()

    fig._push_history(undo_fn, redo_fn)


def add_variables_to_subplot(fig, plot_item, source, y_columns, x_col):
    """Add one curve per y_columns entry to an EXISTING subplot, as one
    undo entry -- mirrors ClipOpsMixin.paste_curve's own holder/undo_fn/
    redo_fn shape exactly."""
    if not y_columns:
        return

    def build():
        items = [_make_curve(fig, plot_item, source, x_col, y_col).item for y_col in y_columns]
        if len(fig._series_on(plot_item)) > 1 and plot_item.legend is None:
            fig._show_legend(plot_item)
        fig.focused_plot = plot_item
        return items

    holder = {'curves': build()}

    def undo_fn():
        for c in holder.get('curves', []):
            plot_item.removeItem(c)
            fig._forget_curve_selection(c)
        holder['curves'] = []

    def redo_fn():
        holder['curves'] = build()

    fig._push_history(undo_fn, redo_fn)


def ask_create_or_add(parent, plot_name):
    """Modal chooser for a drop on an existing subplot. Returns 'new',
    'existing', or None (cancelled)."""
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle("Drop Variable")
    box.setText(f"Create a new subplot, or add to subplot ‘{plot_name}’?")
    new_btn = box.addButton("Create New Subplot", QtWidgets.QMessageBox.AcceptRole)
    add_btn = box.addButton(f"Add to Subplot ‘{plot_name}’", QtWidgets.QMessageBox.AcceptRole)
    box.addButton(QtWidgets.QMessageBox.Cancel)
    box.exec_()
    clicked = box.clickedButton()
    if clicked is new_btn:
        return 'new'
    if clicked is add_btn:
        return 'existing'
    return None


def handle_drop(fig, scene_pos, payload):
    """Entry point from LayoutMixin.eventFilter's Drop branch. `payload`:
    a list of (DataSource, column) as the drag started with -- only the
    entries sharing the FIRST one's source are used (see module docstring
    on the one-source-at-a-time restriction)."""
    if not payload:
        return
    source = payload[0][0]
    y_columns = []
    for src, col in payload:
        if src is source and col not in y_columns:
            y_columns.append(col)
    x_col = default_time_column(source)

    plot_item = fig._plot_at(scene_pos)
    if plot_item is None:
        create_new_subplot_with_variables(fig, source, y_columns, x_col)
        return

    plot_name = fig.subplot_name(plot_item) or "(untitled subplot)"
    choice = ask_create_or_add(fig, plot_name)
    if choice == 'new':
        create_new_subplot_with_variables(fig, source, y_columns, x_col)
    elif choice == 'existing':
        add_variables_to_subplot(fig, plot_item, source, y_columns, x_col)
