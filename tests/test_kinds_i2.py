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

"""WP-I2: the 'bar' and 'errorbar' SeriesKinds (lafigure/kinds/bar.py,
lafigure/kinds/errorbar.py). Importing the two modules below is what
registers them with SERIES_KINDS -- lafigure/__init__.py (coordinator-
owned) is expected to do the same import in the shipped app; see this
package's final report for the exact diff proposed there.
"""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

import lafigure.kinds.bar  # noqa: F401  (registers 'bar')
import lafigure.kinds.errorbar  # noqa: F401  (registers 'errorbar')
from lafigure.kinds.bar import BarKind
from lafigure.kinds.errorbar import ErrorbarKind
from lafigure.series import Series
from tests.helpers import app, m, _mouse


def _shown_empty():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    return f


# -- bar ---------------------------------------------------------------

def test_bar_returns_a_series_backed_by_a_real_bargraphitem():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.bar([0, 1, 2], [3.0, 5.0, 2.0], width=0.6)
    assert isinstance(s, Series) and s.kind == 'bar'
    assert isinstance(s.item, pg.BarGraphItem)
    assert s.item in ax.plot_item.items, "the BarGraphItem must really be on the plot"
    assert list(s.x) == [0.0, 1.0, 2.0]
    assert list(s.y) == [3.0, 5.0, 2.0]
    assert s.item.opts['width'] == 0.6
    assert s in ax.series
    f.close()


def test_bar_item_has_no_curve_and_is_not_wired_clickable():
    """Documents the deliberate current limitation: _add_series's
    hasattr(item, 'curve') guard skips click-wiring for a BarGraphItem.
    Making bars click-selectable is WP-J's job."""
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.bar([0, 1], [1.0, 2.0])
    assert not hasattr(s.item, 'curve')
    f.close()


def test_bar_with_string_categories_sets_bottom_axis_tick_labels():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.bar(['low', 'mid', 'high'], [1.0, 2.0, 3.0])
    assert list(s.x) == [0.0, 1.0, 2.0], "string categories become integer positions"
    assert list(s.y) == [1.0, 2.0, 3.0]
    ticks = ax.plot_item.getAxis('bottom')._tickLevels
    assert ticks and [lbl for _, lbl in ticks[0]] == ['low', 'mid', 'high']
    f.close()


def test_bar_to_dict_create_round_trip():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    x, y = np.array([0.0, 1.0, 2.0]), np.array([4.0, 1.0, 7.0])
    pen = pg.mkPen((10, 20, 30), width=2)
    s = f._add_series(p, 'bar', x, y, pen=pen, name='counts', width=0.4)
    d = s.to_dict()
    assert d['kind'] == 'bar'
    x[:] = -1  # the dict must not alias the caller's arrays
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert isinstance(s2.item, pg.BarGraphItem)
    assert np.array_equal(s2.x, [0.0, 1.0, 2.0])
    assert np.array_equal(s2.y, [4.0, 1.0, 7.0])
    assert s2.item.name() == 'counts'
    assert s2.item.opts['width'] == 0.4
    f.close()


def test_bar_set_xy_updates_the_bargraphitem_in_place():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    s = f._add_series(p, 'bar', [0.0, 1.0], [1.0, 2.0])
    kind = BarKind()
    kind.set_xy(s.item, [0.0, 1.0], [9.0, 9.0])
    assert list(s.y) == [9.0, 9.0]
    assert list(s.item.opts['height']) == [9.0, 9.0]
    f.close()


# -- errorbar ------------------------------------------------------------

def test_errorbar_primary_item_is_a_real_clickable_plotdataitem():
    """Real mouse events to the viewport, mirroring test_axes.py's own
    plotted-series click test -- an errorbar series' primary item stays
    click-selectable, unlike bar's."""
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.errorbar(np.linspace(0, 10, 11), np.zeros(11), yerr=0.5,
                     pen=pg.mkPen('b', width=1))
    app.processEvents()
    assert isinstance(s.item, pg.PlotDataItem)
    assert s.item.curve.clickable, "_add_series must wire the curve clickable"
    # Off a data point on purpose: right on a symbol's center, the
    # ScatterPlotItem half of the PlotDataItem sits on top and swallows the
    # hit-test before it reaches the clickable PlotCurveItem underneath --
    # confirmed against a plain (non-errorbar) symbol='o' curve too, so it's
    # a pre-existing pyqtgraph/pen-clickable-width interaction, not
    # something this kind's pairing with ErrorBarItem introduced.
    pt = ax.plot_item.getViewBox().mapViewToScene(QtCore.QPointF(5.3, 0))
    L = QtCore.Qt.LeftButton
    _mouse(f, QtCore.QEvent.MouseButtonPress, pt, L)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, pt, QtCore.Qt.NoButton)
    assert f.selected_curves == [s.item], f.selected_curves
    f.close()


def test_errorbar_creates_a_paired_errorbaritem_matching_the_input():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    x, y, yerr = np.array([0.0, 1.0, 2.0]), np.array([1.0, 4.0, 9.0]), np.array([0.5, 1.0, 1.5])
    s = ax.errorbar(x, y, yerr=yerr)
    eb = s.item._lafigure_errorbar
    assert isinstance(eb, pg.ErrorBarItem)
    assert eb in ax.plot_item.items
    assert np.array_equal(eb.opts['x'], x)
    assert np.array_equal(eb.opts['y'], y)
    assert np.array_equal(np.asarray(eb.opts['height']), 2.0 * yerr)
    f.close()


def test_errorbar_to_dict_create_round_trip_matches_original_yerr():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    x, y, yerr = np.array([0.0, 1.0, 2.0]), np.array([1.0, 2.0, 3.0]), np.array([0.1, 0.2, 0.3])
    pen = pg.mkPen((5, 6, 7), width=2)
    s = f._add_series(p, 'errorbar', x, y, pen=pen, name='meas', yerr=yerr)
    d = s.to_dict()
    assert d['kind'] == 'errorbar'
    assert np.allclose(d['style']['yerr'], yerr)
    x[:] = -1  # the dict must not alias the caller's arrays
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert np.array_equal(s2.x, [0.0, 1.0, 2.0])
    assert np.array_equal(s2.y, [1.0, 2.0, 3.0])
    eb2 = s2.item._lafigure_errorbar
    assert np.allclose(np.asarray(eb2.opts['height']) / 2.0, yerr)
    assert s2.item.name() == 'meas'
    f.close()


def test_errorbar_set_data_moves_marker_and_whiskers_together_and_survives_undo_redo():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    s = f._add_series(p, 'errorbar', [0.0, 1.0], [1.0, 2.0], yerr=0.5)
    eb = s.item._lafigure_errorbar
    n_undo = len(f.undo_stack)

    s.set_data([0.0, 1.0, 2.0], [5.0, 6.0, 7.0])
    assert len(f.undo_stack) == n_undo + 1
    assert list(s.x) == [0.0, 1.0, 2.0] and list(s.y) == [5.0, 6.0, 7.0]
    assert np.array_equal(eb.opts['x'], [0.0, 1.0, 2.0])
    assert np.array_equal(eb.opts['y'], [5.0, 6.0, 7.0])

    f.undo()
    assert list(s.x) == [0.0, 1.0] and list(s.y) == [1.0, 2.0]
    assert np.array_equal(eb.opts['x'], [0.0, 1.0])
    assert np.array_equal(eb.opts['y'], [1.0, 2.0])

    f.redo()
    assert list(s.x) == [0.0, 1.0, 2.0] and list(s.y) == [5.0, 6.0, 7.0]
    assert np.array_equal(eb.opts['x'], [0.0, 1.0, 2.0])
    assert np.array_equal(eb.opts['y'], [5.0, 6.0, 7.0])
    f.close()


def test_errorbar_kind_get_xy_delegates_to_the_primary_item():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    s = f._add_series(p, 'errorbar', [1.0, 2.0], [3.0, 4.0], yerr=0.1)
    kind = ErrorbarKind()
    x, y = kind.get_xy(s.item)
    assert list(x) == [1.0, 2.0] and list(y) == [3.0, 4.0]
    f.close()
