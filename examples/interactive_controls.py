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

"""A scatter plot driven by a separate control-panel window
(lafigure/controls.py, CLAUDE.md Phase 5): a slider and a checkbox both
narrow a `DataSource.filter(...)` mask, and a small reactive table tracks
how many rows are currently visible -- the "cross-filtering dashboard"
shape this project's controls were built for.

Two things a plot needs before `source.filter(...)` actually moves its
points, both shown below:
  1. build the series FROM the source (`ax.scatter(source, x=..., y=...)`,
     not plain arrays), so it has row assignments to re-derive from;
  2. arm live refresh for that source once, via
     `lafigure.console.watch_source(source)` -- normally this happens
     automatically the first time a user opens the embedded console
     (ConsoleMixin._watch_plotted_sources), but a script driving
     `.filter()` from its own controls, with the console dock never
     opened, has to call it itself.

Run:
    python examples/interactive_controls.py
"""
import os
import sys

import numpy as np
from pyqtgraph.Qt import QtWidgets
import pyqtgraph as pg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lafigure
_debug_log = lafigure.enable_debug_mode()
print(f"Debug log: {_debug_log}")
from lafigure.console import watch_source


def main():
    app = QtWidgets.QApplication(sys.argv)
    rng = np.random.default_rng(4)

    n = 6000
    x = rng.uniform(0, 10, n)
    y = 2 * np.sin(x) + rng.normal(scale=0.4, size=n)
    category = rng.integers(0, 2, n)  # 0 = "A", 1 = "B"
    source = lafigure.DataSource({'x': x, 'y': y, 'category': category})

    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- filtered by a control panel")
    ax = fig.subplot(0, 0, title="Cross-filtered scatter")
    series = ax.scatter(source, x='x', y='y', size=4,
                        symbolBrush=pg.mkBrush(70, 120, 200, 140), symbolPen=None)
    watch_source(source)

    # Two independent controls narrowing the SAME filter -- filter() is a
    # single, wholesale, re-appliable mask (datasource.py), so both need
    # to be combined by hand into one mask on every change, rather than
    # each calling filter() with only its own condition.
    state = {'min_x': 0.0, 'only_a': False}

    def apply_filter():
        mask = source['x'] >= state['min_x']
        if state['only_a']:
            mask = mask & (source['category'] == 0)
        source.filter(mask)

    def on_min_x(v):
        state['min_x'] = float(v)
        apply_filter()

    def on_only_a(v):
        state['only_a'] = v
        apply_filter()

    def on_reset():
        state.update(min_x=0.0, only_a=False)
        source.filter(None)

    def visible_stats():
        # source.visible_rows alone only accounts for filter()/hide_rows()
        # -- it says nothing about points a user has permanently deleted
        # from THIS series (Brush mode, Del): a delete narrows only the
        # series' own drawn `rows` (brushing.py's delete_brushed_points),
        # the DataSource itself is never shrunk (see datasource.py's own
        # "Two independent, composable visibility mechanisms" docstring
        # note -- there's deliberately no third, "deleted", mask there).
        # So the true "what's actually on screen right now" set is series
        # .rows (this series' current row assignment, already excluding
        # anything deleted from it) intersected with source.visible_rows
        # (filtered/hidden) -- combining both is what a reactive control
        # needs to do itself; DataSource has no single call that means
        # "deleted from this particular series".
        rows = series.rows
        if rows is None:
            rows = np.arange(len(source))
        shown = rows[np.isin(rows, source.visible_rows)]
        mean_y = float(np.mean(source['y'][shown])) if shown.size else float('nan')
        return {'metric': ['visible points', 'mean y'],
                'value': [str(shown.size), f"{mean_y:.3f}"]}

    win = lafigure.open_control_panel(figure=fig, title="Filter controls")
    win.slider('min x', 0, 10, value=0, on_change=on_min_x)
    win.checkbox('category A only', checked=False, on_change=on_only_a)
    win.button('Reset', on_click=on_reset)
    # depends_on=[source]: a plain filter()/hide_rows() already notifies
    # this source directly; a brush-Delete on `series` notifies it too
    # (delete_brushed_points's notify_change(), brushing.py) even though
    # it never touches source's own masks -- see visible_stats' own
    # comment above for why the delete case still needs source.visible_rows
    # combined with series.rows rather than either alone.
    win.table(visible_stats, depends_on=[source])

    fig.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
