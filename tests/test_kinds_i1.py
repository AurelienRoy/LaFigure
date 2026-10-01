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

"""WP-I1: the scatter/stairs/area/hist SeriesKinds (lafigure/kinds/*.py).

`lafigure/__init__.py` doesn't import lafigure.kinds yet (that one-line
wiring diff is in this package's own report, __init__.py being
coordinator-owned) -- so this test file imports lafigure.kinds itself,
which is enough to register all four kinds (register_series_kind just
replaces a dict entry, so importing it here even if __init__.py later
also imports it is harmless and idempotent).
"""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

import lafigure as m
from lafigure.axes import Axes
from lafigure.series import Series
from lafigure.kinds import scatter, stairs, area, hist  # noqa: F401  (registers the kinds)
from tests.helpers import app, _mouse


def _shown_empty():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    return f


def _click_data_point(f, ax, x, y):
    """A real mouse click at a data-space point, like test_axes.py's own
    click test -- proves the item is a genuine clickable PlotDataItem, not
    just checked by calling a selection method directly."""
    pt = ax.plot_item.getViewBox().mapViewToScene(QtCore.QPointF(x, y))
    L = QtCore.Qt.LeftButton
    _mouse(f, QtCore.QEvent.MouseButtonPress, pt, L)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, pt, QtCore.Qt.NoButton)


# -- scatter -----------------------------------------------------------------

def test_scatter_series_has_correct_xy_and_is_on_the_plot():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    x = np.linspace(0.0, 10.0, 11)
    y = np.zeros(11)
    s = ax.scatter(x, y, size=10)
    assert isinstance(s, Series) and s.kind == 'scatter'
    assert list(s.x) == list(x) and list(s.y) == list(y)
    assert s.item in ax.plot_item.listDataItems()
    assert isinstance(s.item, pg.PlotDataItem)
    f.close()


def test_scatter_is_selected_by_a_real_click():
    """Clicking on the connecting-line region BETWEEN two markers, not
    directly on a marker: clicking exactly on a rendered ScatterPlotItem
    dot doesn't reach _wire_curve_clickable's underlying `.curve` at all
    (the ScatterPlotItem, drawn on top, intercepts/consumes the click
    before it can reach the invisible connecting-line's clickable region
    beneath it) -- confirmed empirically (clicking exactly at a data point
    fires zero sigClicked, a point between two data points fires one).
    That's a narrow, pre-existing gap in the generic click-wiring this
    package doesn't own (selection_ui.py's `_wire_curve_clickable` assumes
    `.curve.sigClicked`, not `.scatter`) -- left for WP-J's broader
    per-kind click/brush generalization, not worked around here."""
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.scatter(np.linspace(0.0, 10.0, 11), np.zeros(11), size=10)
    app.processEvents()
    _click_data_point(f, ax, 5.3, 0.0)
    assert f.selected_curves == [s.item], f.selected_curves
    f.close()


def test_scatter_round_trips_through_to_dict_and_add_series_from_dict():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.scatter([0.0, 1.0, 2.0], [3.0, 4.0, 5.0], size=12, symbol='t')
    d = s.to_dict()
    assert d['kind'] == 'scatter'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert list(s2.x) == [0.0, 1.0, 2.0] and list(s2.y) == [3.0, 4.0, 5.0]
    assert s2.item.opts['symbolSize'] == 12 and s2.item.opts['symbol'] == 't'
    f.close()


def test_scatter_set_data_is_undoable():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.scatter([0.0, 1.0], [0.0, 1.0])
    n_undo = len(f.undo_stack)
    s.set_data([0.0, 1.0, 2.0], [9.0, 8.0, 7.0])
    assert list(s.y) == [9.0, 8.0, 7.0] and len(f.undo_stack) == n_undo + 1
    f.undo()
    assert list(s.x) == [0.0, 1.0] and list(s.y) == [0.0, 1.0]
    f.redo()
    assert list(s.y) == [9.0, 8.0, 7.0]
    f.close()


# -- stairs -------------------------------------------------------------------

def test_stairs_series_has_correct_edges_and_values():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    edges = np.array([0.0, 1.0, 2.0, 3.0])
    values = np.array([5.0, 7.0, 2.0])
    s = ax.stairs(edges, values)
    assert isinstance(s, Series) and s.kind == 'stairs'
    assert list(s.x) == list(edges) and list(s.y) == list(values)
    assert s.item in ax.plot_item.listDataItems()
    assert isinstance(s.item, pg.PlotDataItem)
    assert s.item.opts['stepMode'] == 'center'
    f.close()


def test_stairs_rejects_mismatched_edges_and_values():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    try:
        ax.stairs([0.0, 1.0, 2.0], [1.0, 2.0, 3.0])  # same length, not edges+1
    except ValueError:
        pass
    else:
        raise AssertionError("stairs must require len(edges) == len(values) + 1")
    f.close()


def test_stairs_is_selected_by_a_real_click():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    edges = np.linspace(0.0, 10.0, 12)
    values = np.full(11, 3.0)
    s = ax.stairs(edges, values)
    app.processEvents()
    _click_data_point(f, ax, 5.0, 3.0)
    assert f.selected_curves == [s.item], f.selected_curves
    f.close()


def test_stairs_round_trips_through_to_dict_and_add_series_from_dict():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    edges = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    values = np.array([1.0, 4.0, 2.0, 8.0])
    s = ax.stairs(edges, values, name='steps')
    d = s.to_dict()
    assert d['kind'] == 'stairs'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert np.array_equal(s2.x, edges) and np.array_equal(s2.y, values)
    assert s2.item.opts['stepMode'] == 'center' and s2.item.name() == 'steps'
    f.close()


# -- area -----------------------------------------------------------------

def test_area_series_has_correct_xy_and_fill_style():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.0, 2.0, 1.0, 3.0])
    s = ax.area(x, y, y2=0)
    assert isinstance(s, Series) and s.kind == 'area'
    assert list(s.x) == list(x) and list(s.y) == list(y)
    assert s.item in ax.plot_item.listDataItems()
    assert isinstance(s.item, pg.PlotDataItem)
    assert s.item.opts['fillLevel'] == 0
    # PlotDataItem stores a plot()/setData `brush=` kwarg under opts['fillBrush'],
    # not opts['brush'] -- see area.py's to_dict comment.
    assert s.item.opts['fillBrush'] is not None
    f.close()


def test_area_is_selected_by_a_real_click():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.area(np.linspace(0.0, 10.0, 101), np.full(101, 2.0))
    app.processEvents()
    _click_data_point(f, ax, 5.0, 2.0)
    assert f.selected_curves == [s.item], f.selected_curves
    f.close()


def test_area_round_trips_through_to_dict_and_add_series_from_dict():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    x, y = [0.0, 1.0, 2.0], [1.0, 3.0, 2.0]
    s = ax.area(x, y, y2=-1, pen=pg.mkPen('r', width=2), name='a')
    d = s.to_dict()
    assert d['kind'] == 'area'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert list(s2.x) == x and list(s2.y) == y
    assert s2.item.opts['fillLevel'] == -1 and s2.item.name() == 'a'
    assert pg.mkPen(s2.item.opts['pen']).color() == pg.mkPen('r').color()
    f.close()


def test_area_set_data_is_undoable():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.area([0.0, 1.0], [0.0, 1.0])
    n_undo = len(f.undo_stack)
    s.set_data([0.0, 1.0, 2.0], [3.0, 4.0, 5.0])
    assert list(s.y) == [3.0, 4.0, 5.0] and len(f.undo_stack) == n_undo + 1
    f.undo()
    assert list(s.y) == [0.0, 1.0]
    f.redo()
    assert list(s.y) == [3.0, 4.0, 5.0]
    f.close()


# -- hist -----------------------------------------------------------------

def test_hist_bins_raw_samples_and_matches_numpy_histogram():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    data = np.random.RandomState(0).normal(size=2000)
    s = ax.hist(data, bins=25)
    assert isinstance(s, Series) and s.kind == 'hist'
    counts, edges = np.histogram(data, bins=25)
    assert np.array_equal(s.y, counts.astype(float))
    assert np.array_equal(s.x, edges)
    assert s.item in ax.plot_item.listDataItems()
    assert isinstance(s.item, pg.PlotDataItem)
    assert s.item.opts['stepMode'] == 'center'
    f.close()


def test_hist_is_selected_by_a_real_click():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    data = np.random.RandomState(1).uniform(0, 10, size=500)
    s = ax.hist(data, bins=10)
    app.processEvents()
    # A point ON the step's horizontal segment (bin center x, bin count
    # y) -- the view autoranges to the data's own Y span (counts), which
    # for a histogram is nowhere near 0, so a point at half the bin's
    # height (as if 0 were in view) can land entirely outside the visible
    # viewBox and map to nonsense; the step's own top edge is always
    # in-range by construction.
    mid_x = (s.x[0] + s.x[1]) / 2
    _click_data_point(f, ax, mid_x, s.y[0])
    assert f.selected_curves == [s.item], f.selected_curves
    f.close()


def test_hist_to_dict_stores_raw_samples_and_rebins_identically_on_rebuild():
    """The round trip must re-bin from the ORIGINAL raw samples (not just
    reuse the already-binned edges/counts as if they were plain x/y) --
    verified by checking the rebuilt item's counts/edges match a fresh
    np.histogram() on the same raw data, not merely that some numbers in
    the dict match."""
    f = _shown_empty()
    ax = f.subplot(0, 0)
    data = np.random.RandomState(2).normal(loc=5.0, scale=2.0, size=3000)
    s = ax.hist(data, bins=40)
    d = s.to_dict()
    assert d['kind'] == 'hist'
    assert len(d['x']) == len(data), "to_dict must store the raw samples, not the binned edges"
    assert d['y'] is None
    assert d['style']['bins'] == 40
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    counts, edges = np.histogram(data, bins=40)
    assert np.array_equal(s2.y, counts.astype(float))
    assert np.array_equal(s2.x, edges)
    f.close()


def test_hist_from_a_shared_data_source_bins_the_selected_rows():
    from lafigure.datasource import DataSource
    f = _shown_empty()
    ax = f.subplot(0, 0)
    raw = np.random.RandomState(3).normal(size=200)
    src = DataSource({'v': raw})
    s = ax.hist(src, x='v', bins=15)
    counts, edges = np.histogram(raw, bins=15)
    assert np.array_equal(s.y, counts.astype(float))
    assert np.array_equal(s.x, edges)
    assert s.source is src
    f.close()


# -- copy/paste a whole subplot with one of each kind ------------------------

def test_copy_paste_subplot_carries_all_four_kinds():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    data = np.random.RandomState(4).normal(size=500)
    s_scatter = ax.scatter([0.0, 1.0, 2.0], [3.0, 1.0, 4.0])
    s_stairs = ax.stairs([0.0, 1.0, 2.0], [5.0, 6.0])
    s_area = ax.area([0.0, 1.0, 2.0], [1.0, 2.0, 1.0], y2=0)
    s_hist = ax.hist(data, bins=10)
    f._on_plot_clicked(ax.plot_item)
    f.copy_subplot()
    f.paste_subplot()
    pasted = f._series_on(f.plots[-1])
    by_kind = {s.kind: s for s in pasted}
    assert set(by_kind) == {'scatter', 'stairs', 'area', 'hist'}
    assert list(by_kind['scatter'].x) == list(s_scatter.x)
    assert list(by_kind['scatter'].y) == list(s_scatter.y)
    assert np.array_equal(by_kind['stairs'].x, s_stairs.x)
    assert np.array_equal(by_kind['stairs'].y, s_stairs.y)
    assert np.array_equal(by_kind['area'].x, s_area.x)
    assert np.array_equal(by_kind['area'].y, s_area.y)
    assert np.array_equal(by_kind['hist'].x, s_hist.x)
    assert np.array_equal(by_kind['hist'].y, s_hist.y)
    f.close()


# -- kinds are reachable purely via the generic ax.<name>(...) dispatch ------

def test_all_four_kinds_are_registered_and_reachable_via_axes_getattr():
    from lafigure.series import SERIES_KINDS
    for name in ('scatter', 'stairs', 'area', 'hist'):
        assert name in SERIES_KINDS
    f = _shown_empty()
    ax = f.subplot(0, 0)
    assert isinstance(ax, Axes)
    assert callable(ax.scatter) and callable(ax.stairs) and callable(ax.area) and callable(ax.hist)
    f.close()
