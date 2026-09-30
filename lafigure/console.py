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

"""WP-L: the three CLAUDE.md Phase 2 bullets WP-F/WP-H didn't cover --
embedded Python console panel, datatip, and `DataSource.filter` UI wiring.

- **Console panel**: `ConsoleMixin.toggle_console()` shows/hides a
  `QDockWidget` wrapping `pyqtgraph.console.ConsoleWidget` (verified
  importable/API-compatible against the installed pyqtgraph -- see this
  package's report for the exact signature checked), preloaded with
  `fig`/`gca`/`gcf`/`np`. `ConsoleMixin` is not mixed into `LaFigure` from
  here -- figure.py/toolbar.py are coordinator-owned; see the report for
  the small diffs that wire the mixin in and add a toolbar toggle button.
- **Datatip**: `ax.datatip = "{col} @ {other:.2f}"` (a format string) or
  `ax.datatip = some_callable` (a `RowAccessor` -> str callable). Storage
  design is explained just above `_DATATIPS` below; `datatip_text()` is
  the one function annotation_ops.py's cursor-placement branch needs to
  call (see the report's diff for that file) to use it.
- **`src.filter(...)` wiring**: `watch_source(source)` subscribes so every
  Series sharing that exact DataSource, in any open figure, re-derives its
  displayed x/y from `source.visible_rows` whenever the source notifies
  (`on_change`) -- via `SeriesKind.set_xy` directly, never
  `Series.set_data`, so this is view state and never touches undo.
"""
import weakref

import numpy as np
import pyqtgraph.console
from pyqtgraph.Qt import QtCore, QtWidgets

from .axes import Axes, gca, gcf
from .registry import get_registry

WELCOME = (
    "LaFigure console -- fig, gca(), gcf() and np are preloaded.\n"
    ">>> gca().plot(np.sin(np.linspace(0, 10, 200)))\n"
)


class RowAccessor(dict):
    """Passed to a callable `ax.datatip`: dict-like (row['col']) and
    attribute-like (row.col) access to one DataSource row's columns."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e


# -- datatip storage ---------------------------------------------------
# axes.py's own docstring: Axes "holds no state of its own beyond the
# figure and PlotItem, so any number of Axes on the same subplot are
# interchangeable" -- a plain instance attribute set on one throwaway
# Axes (e.g. the one gca() just built) would never be visible from the
# next Axes(fig, plot_item) built later. So the datatip is stored here,
# keyed by plot_item, in a dict this module owns -- and `ax.datatip = ...`
# is made to reach it via a `property` added to the Axes *class* at the
# bottom of this module, rather than by editing axes.py (not an owned
# file for this package). This only takes effect once lafigure.console has
# actually been imported at least once in the process -- see the report
# for the one-line lafigure/__init__.py addition that makes that automatic.
_DATATIPS = {}


def set_datatip(plot_item, spec):
    """spec: a str.format string, or a callable(RowAccessor) -> str, or
    None to clear."""
    if spec is None:
        _DATATIPS.pop(plot_item, None)
    else:
        _DATATIPS[plot_item] = spec


def get_datatip(plot_item):
    return _DATATIPS.get(plot_item)


def datatip_text(figure, plot_item, curve, idx, x, y, z=None):
    """Text for a data-cursor annotation at data point (x, y[, z]). Falls
    back to "{x:.4g}, {y:.4g}" (annotation_ops.py's own original default,
    preserved exactly) or, when `z` is given (a 3D curve), "{x:.4g},
    {y:.4g}, {z:.4g}" -- whenever no datatip is configured for
    `plot_item`, there's no nearest curve/row (idx is None), or formatting
    the configured spec against the real row raises for any reason -- a
    bad user format string / callable must degrade gracefully, not crash
    annotation placement.

    `curve`/`idx` are exactly what annotation_ops.py's cursor branch
    already computes (the nearest curve/series and the index of its
    nearest point to the click) -- passed in rather than recomputed here
    so this stays a pure formatting step.
    """
    default = f"{x:.4g}, {y:.4g}" if z is None else f"{x:.4g}, {y:.4g}, {z:.4g}"
    spec = _DATATIPS.get(plot_item)
    if spec is None or curve is None or idx is None:
        return default
    series = figure._series_of(curve)
    if series is None:
        return default
    try:
        source = series.source
        rows = series.rows
        row = int(rows[idx]) if rows is not None else idx
        row_dict = {name: source[name][row] for name in source.columns}
        if z is not None:
            row_dict.setdefault('z', z)
        if callable(spec):
            return str(spec(RowAccessor(row_dict)))
        return spec.format(**row_dict)
    except Exception:
        return default


# -- src.filter(...) UI wiring ------------------------------------------
# DataSource.filter/hide_rows/show_rows/show_all (datasource.py) already
# notify via on_change; "every linked series re-derives its visible rows"
# is the missing piece, built here rather than in series.py/axes.py (not
# owned by this package) by subscribing from the outside.
_watched = weakref.WeakSet()


def watch_source(source):
    """Arm live filter refresh for `source`: from now on, every Series (in
    any open LaFigure window -- a DataSource can be shared across figures,
    e.g. via the process-wide Clipboard) built from this exact DataSource
    re-derives its displayed x/y whenever it changes. Idempotent."""
    if source in _watched:
        return
    _watched.add(source)
    source.on_change(lambda: refresh_series_for_source(source))


def _refresh_series(series, source):
    rows = series.rows  # read-only view of this series' own assigned rows
    if rows is None or series.columns is None:
        return  # not linked to an explicit source column -- nothing to re-derive
    fmask = source.filter_mask
    hidden = source.hidden_mask
    full_visible = (~hidden) if fmask is None else (fmask & ~hidden)
    visible_rows = rows[full_visible[rows]]
    xcol = series.columns[0]
    ycol = series.columns[1] if len(series.columns) > 1 else None
    new_x = np.asarray(source[xcol][visible_rows])
    new_y = np.asarray(source[ycol][visible_rows]) if ycol else None
    # Recomputed from `source` + the series' own full row assignment every
    # time (never from the currently-displayed, possibly-already-filtered
    # x/y), so repeated filter() calls never compound. A kind whose set_xy
    # rebins rather than just replacing (e.g. a histogram kind receiving
    # these filtered raw samples, per SeriesKind.create's own "a histogram
    # kind treats x as the raw samples to bin" convention) gets that for
    # free here too -- unverified against a real histogram kind, see report.
    # Raw source values: drawn through the series' display transform (WP-P7).
    series._write_raw(new_x, new_y)


def refresh_series_for_source(source):
    """The on_change callback watch_source subscribes: refresh every
    Series, in every open figure, backed by `source`."""
    for fig in get_registry().figures:
        for plot_item in fig.plots:
            for series in fig._series_on(plot_item):
                # series.source (the public property) would lazily build
                # and cache a private DataSource for a series with no
                # explicit source, just to answer this identity check --
                # read the private field instead so scanning series never
                # linked to any explicit source stays free of that.
                if series._source is source:
                    _refresh_series(series, source)


# -- the console panel ---------------------------------------------------
class ConsoleMixin:
    """Adds an embedded Python console panel. See the module docstring for
    why this isn't mixed into LaFigure from this file."""

    def _console_namespace(self):
        return {'fig': self, 'gca': gca, 'gcf': gcf, 'np': np}

    def _ensure_console_dock(self):
        dock = getattr(self, '_console_dock', None)
        if dock is not None:
            return dock
        widget = pyqtgraph.console.ConsoleWidget(namespace=self._console_namespace(), text=WELCOME)
        dock = QtWidgets.QDockWidget("Console", self)
        dock.setObjectName("lafigure_console_dock")
        dock.setWidget(widget)
        dock.setAllowedAreas(QtCore.Qt.BottomDockWidgetArea | QtCore.Qt.TopDockWidgetArea)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)
        dock.setVisible(False)
        dock.visibilityChanged.connect(self._on_console_visibility_changed)
        self._console_dock = dock
        self._console_widget = widget
        return dock

    def _on_console_visibility_changed(self, visible):
        action = getattr(self, 'console_action', None)
        if action is not None and action.isChecked() != visible:
            action.setChecked(visible)

    def toggle_console(self, checked=None):
        """Show/hide the console dock (creating it on first use). `checked`
        (from a checkable toolbar action) sets the state explicitly; left
        as None, it flips whatever the current visibility is -- view state,
        not undoable, like every other mode/panel toggle (CLAUDE.md)."""
        dock = self._ensure_console_dock()
        show = (not dock.isVisible()) if checked is None else bool(checked)
        dock.setVisible(show)
        if show:
            self._watch_plotted_sources()

    def _watch_plotted_sources(self):
        """Arm src.filter(...) live-refresh (watch_source above) for every
        DataSource already backing a series on this figure, so a user who
        opens the console and calls source.filter(...) on something already
        plotted sees it take effect without an extra call."""
        for plot_item in self.plots:
            for series in self._series_on(plot_item):
                if series._source is not None:
                    watch_source(series._source)


# Wire ax.datatip = "..."/callable onto Axes without editing axes.py --
# see the _DATATIPS comment above for why a plain instance attribute isn't
# enough. Guarded so re-importing this module twice is harmless.
if not hasattr(Axes, 'datatip'):
    Axes.datatip = property(
        lambda self: get_datatip(self.plot_item),
        lambda self, spec: set_datatip(self.plot_item, spec),
    )
