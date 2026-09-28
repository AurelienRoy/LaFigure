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

"""The library-facing API: the Axes facade over one subplot, returned by
LaFigure.subplot(), plus the module-level gcf()/gca().

    ax = fig.subplot(0, 0, title="Speed")
    s = ax.plot(t, v, name="v")                 # plain arrays
    s2 = ax.plot(src, x='t', y='speed')         # columns of a shared DataSource
    gca().plot(y)                               # the focused subplot

Adding a series from the API is construction, like add_subplot: it pushes
no undo entry. Editing one afterwards (Series.set_data) does.
"""
import weakref

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets

from .datasource import DataSource
from .registry import get_registry

# Default line colors for ax.plot without a pen, cycled per subplot.
DEFAULT_COLORS = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
                  (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127)]


class Axes:
    """One subplot, seen from the API. Holds no state of its own beyond the
    figure and PlotItem, so any number of Axes on the same subplot are
    interchangeable (they compare equal)."""

    def __init__(self, figure, plot_item):
        self.figure = figure
        self.plot_item = plot_item

    def __eq__(self, other):
        return (isinstance(other, Axes) and other.figure is self.figure
                and other.plot_item is self.plot_item)

    def __hash__(self):
        return hash((id(self.figure), id(self.plot_item)))

    def __repr__(self):
        return f"<Axes {self.figure.subplot_name(self.plot_item)!r}>"

    @property
    def series(self):
        """Every Series on this subplot, derived live from the plot."""
        return self.figure._series_on(self.plot_item)

    def plot(self, x_or_source, y=None, *, x=None, pen=None, name=None, rows=None, **style):
        """A line series. Either plain arrays -- plot(x, y), or plot(y) with
        x = 0..n-1 -- or plot(source, x='col', y='col', rows=None) for
        columns of a DataSource shared with other series (rows: which of its
        rows to show, default all). Other keywords go to the kind
        (clip_to_view, downsample). Returns the Series."""
        if pen is None:
            pen = pg.mkPen(DEFAULT_COLORS[len(self.series) % len(DEFAULT_COLORS)], width=1)
        if isinstance(x_or_source, DataSource):
            source = x_or_source
            if not isinstance(x, str) or not isinstance(y, str):
                raise TypeError("plot(source, x='column', y='column'): both column names are required")
            rows = np.arange(len(source)) if rows is None else np.asarray(rows, dtype=np.intp)
            xs, ys = source[x][rows], source[y][rows]
            return self.figure._add_series(self.plot_item, 'line', xs, ys, pen=pen, name=name,
                                           source=source, rows=rows, columns=(x, y), **style)
        if x is not None or rows is not None:
            raise TypeError("x=/rows= are column/row selectors, only for plot(source, ...)")
        if y is None:
            ys = np.asarray(x_or_source)
            xs = np.arange(len(ys))
        else:
            xs, ys = np.asarray(x_or_source), np.asarray(y)
        return self.figure._add_series(self.plot_item, 'line', xs, ys, pen=pen, name=name, **style)


# -- current figure / axes -------------------------------------------------
# Figures in order of last use, most recent last, as weak references: this
# list must never keep a closed window alive. "Use" = opened, its focused
# subplot changed (registry.focusChanged), or a widget inside it got the
# keyboard focus (QApplication.focusChanged -- clicking into a window,
# which the registry can't see when the focused subplot stays the same).
_recent = []
_app_hooked = []


def _touch(figure, *_):
    _hook_app()
    _recent[:] = [r for r in _recent if r() is not None and r() is not figure]
    _recent.append(weakref.ref(figure))


def _on_app_focus(_old, new):
    window = new.window() if new is not None else None
    if window in _registry.figures:
        _touch(window)


def _hook_app():
    """Connect QApplication.focusChanged once a QApplication exists -- not
    at import, which may come before the application is created."""
    app = QtWidgets.QApplication.instance()
    if app is not None and not _app_hooked:
        app.focusChanged.connect(_on_app_focus)
        _app_hooked.append(app)


_registry = get_registry()
_registry.figureOpened.connect(_touch)
_registry.focusChanged.connect(_touch)


def gcf():
    """The current LaFigure: the open figure used most recently (see
    _recent), else the last one opened; None if no figure is open."""
    open_figures = _registry.figures
    for ref in reversed(_recent):
        fig = ref()
        if fig is not None and fig in open_figures:
            return fig
    return open_figures[-1] if open_figures else None


def gca():
    """An Axes on the current figure's focused subplot, or None if there is
    no open figure or it has no subplot."""
    fig = gcf()
    if fig is None:
        return None
    plot = fig.focused_plot
    if plot is None and fig.plots:
        plot = fig.plots[0]
    return Axes(fig, plot) if plot is not None else None
