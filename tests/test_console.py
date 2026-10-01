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

"""WP-L: console panel, datatip, src.filter(...) UI wiring (console.py).

ConsoleMixin is mixed into the real LaFigure in figure.py (applied by the
coordinator alongside GroupsMixin, since both landed as diffs against
figure.py in the same wave); tests here just use LaFigure directly.
"""
import numpy as np

from lafigure.console import (
    ConsoleMixin, RowAccessor, datatip_text, watch_source, refresh_series_for_source,
)
from lafigure.datasource import DataSource
from lafigure.axes import Axes, gca, gcf

from tests.helpers import app, m


def _figure_with_two_linked_series():
    """Two subplots, two series, sharing one DataSource ('t'/'v' columns,
    10 rows)."""
    src = DataSource({'t': np.arange(10, dtype=float), 'v': np.arange(10, dtype=float) * 2})
    f = m.LaFigure(empty=True)
    p1 = f.add_subplot(row=0, col=0)
    p2 = f.add_subplot(row=1, col=0)
    s1 = Axes(f, p1).plot(src, x='t', y='v', name='s1')
    s2 = Axes(f, p2).plot(src, x='t', y='v', name='s2')
    return f, src, s1, s2


# -- console panel --------------------------------------------------------

def test_console_dock_creates_shows_and_hides_without_error():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    assert getattr(f, '_console_dock', None) is None  # not built until first toggle

    f.toggle_console()
    app.processEvents()
    assert f._console_dock is not None
    assert f._console_dock.isVisible()

    f.toggle_console()
    app.processEvents()
    assert not f._console_dock.isVisible()

    # Explicit checked=True/False, as a checkable toolbar action would send.
    f.toggle_console(checked=True)
    assert f._console_dock.isVisible()
    f.toggle_console(checked=False)
    assert not f._console_dock.isVisible()


def test_console_namespace_has_working_fig_gca_gcf_np():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    f.toggle_console()
    widget = f._console_widget

    ns = widget.localNamespace
    assert ns['fig'] is f
    assert ns['gca'] is gca
    assert ns['gcf'] is gcf
    assert ns['np'] is np

    # Actually execute code through the console's own execution API
    # (ReplWidget.handleCommand -> runCmd, synchronous here since
    # allowNonGuiExecution defaults to False) rather than only inspecting
    # the namespace dict, to prove fig/np are genuinely usable, not just
    # present.
    widget.repl.handleCommand("_wp_l_probe = (len(fig.plots), int(np.arange(3).sum()))")
    assert widget.localNamespace.get('_wp_l_probe') == (0, 3)


# -- datatip ----------------------------------------------------------------

def test_datatip_format_string_uses_real_row_values():
    src = DataSource({
        't': np.array([0.0, 1.0, 2.0, 3.0]),
        'v': np.array([10.0, 11.0, 12.0, 13.0]),
        'log': np.array(['a', 'b', 'c', 'd']),
    })
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    ax = Axes(f, p)
    series = ax.plot(src, x='t', y='v', name='s')
    ax.datatip = "{log} @ {v:.1f}"

    curve = series.item
    # Nearest point to x=2.1 is row index 2 (t=2.0).
    idx = int(np.argmin(np.abs(curve.xData - 2.1)))
    x, y = float(curve.xData[idx]), float(curve.yData[idx])
    text = datatip_text(f, p, curve, idx, x, y)
    assert text == "c @ 12.0"


def test_datatip_callable_receives_row_accessor():
    src = DataSource({'t': np.array([0.0, 1.0]), 'v': np.array([5.0, 6.0]), 'tag': np.array(['x', 'y'])})
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    ax = Axes(f, p)
    series = ax.plot(src, x='t', y='v', name='s')
    ax.datatip = lambda row: f"tag={row.tag} v={row['v']:.0f}"

    curve = series.item
    idx = 1
    x, y = float(curve.xData[idx]), float(curve.yData[idx])
    assert datatip_text(f, p, curve, idx, x, y) == "tag=y v=6"


def test_datatip_falls_back_to_default_when_unset_or_no_row():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    # No ax.datatip set at all -- default "x, y" text.
    assert datatip_text(f, p, None, None, 1.23456, 7.89) == "1.235, 7.89"


def test_row_accessor_dict_and_attribute_access_agree():
    row = RowAccessor({'a': 1, 'b': 'z'})
    assert row['a'] == 1
    assert row.a == 1
    assert row.b == 'z'


# -- src.filter(...) UI wiring ----------------------------------------------

def test_filter_wiring_refreshes_every_linked_series_without_undo():
    f, src, s1, s2 = _figure_with_two_linked_series()
    watch_source(src)

    before = len(f.undo_stack)
    src.filter('t >= 5')
    after = len(f.undo_stack)
    assert after == before, "filtering is view state -- must not push an undo entry"

    visible = src.visible_rows
    assert np.array_equal(s1.x, src['t'][visible])
    assert np.array_equal(s1.y, src['v'][visible])
    assert np.array_equal(s2.x, src['t'][visible])
    assert np.array_equal(s2.y, src['v'][visible])

    # Clearing the filter restores every row on both series.
    src.filter(None)
    assert np.array_equal(s1.x, src['t'])
    assert np.array_equal(s2.y, src['v'])


def test_filter_wiring_is_idempotent_to_watch_twice():
    f, src, s1, s2 = _figure_with_two_linked_series()
    watch_source(src)
    watch_source(src)  # must not double-subscribe (each on_change call would double-refresh, harmlessly, but let's guard anyway)
    src.filter('t < 3')
    assert np.array_equal(s1.x, src['t'][src.visible_rows])


def test_hide_rows_also_refreshes_linked_series():
    f, src, s1, s2 = _figure_with_two_linked_series()
    watch_source(src)
    src.hide_rows([0, 1])
    assert np.array_equal(s1.x, src['t'][src.visible_rows])
    src.show_all()
    assert np.array_equal(s1.x, src['t'])


def test_refresh_series_for_source_ignores_series_without_explicit_source():
    """A plain-array series (no DataSource) must be left alone by a refresh
    for an unrelated source -- series._source is None, so it's skipped."""
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    ax = Axes(f, p)
    plain = ax.plot([0, 1, 2], [0, 1, 4], name='plain')
    other_src = DataSource({'t': np.arange(5, dtype=float), 'v': np.arange(5, dtype=float)})
    watch_source(other_src)
    other_src.filter('t < 2')
    # Unaffected: still its original 3 points.
    assert len(plain.x) == 3
