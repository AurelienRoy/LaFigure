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

"""WP-J (Phase 3): brushing on every kind through the rows_in_rect/
show_rows protocol, DataSource-row linking (replacing SelectionModel/
LinkedScatter), Hide Brushed Points / Show All, derived columns, and
pasted series staying linked to their source."""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

from lafigure import selection as sel_mod
from lafigure.brushing import ROW_VIEW_ATTR
from lafigure.datasource import DataSource
from lafigure.series import SeriesKind, register_series_kind
from tests.helpers import app, m, shown_figure, _brush_drag


# -- stand-in kinds: the protocol must work for kinds this package never saw --
class _PointsKind(SeriesKind):
    """A point kind whose item is NOT a PlotDataItem (a ScatterPlotItem, as
    a scatter kind would use) and that defines no brushing method at all --
    the default protocol must cover it through get_xy alone."""
    name = 'test_j_points'
    capabilities = frozenset({'brush', 'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None):
        item = pg.ScatterPlotItem(x=x, y=y, size=5, name=name)
        plot_item.addItem(item)
        return item

    def to_dict(self, item):
        x, y = item.getData()
        return {'x': np.array(x), 'y': np.array(y), 'pen': None, 'name': item.name(), 'style': {}}

    def get_xy(self, item):
        return item.getData()

    def set_xy(self, item, x, y):
        item.setData(x=x, y=y)


class _HistKind(SeriesKind):
    """A histogram as pyqtgraph draws one (stepMode='center': len(x) ==
    len(y) + 1, so it is NOT point-like), opting into bar<->row linking
    through the optional brush_bins hook."""
    name = 'test_j_hist'
    capabilities = frozenset({'brush'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None, bins=10):
        values = np.asarray(x, dtype=float)
        counts, edges = np.histogram(values, bins=bins)
        item = pg.PlotDataItem(edges, counts, stepMode='center', fillLevel=0,
                               brush=(100, 100, 200, 120), name=name)
        plot_item.addItem(item)
        item._values = values
        return item

    def to_dict(self, item):
        return {'x': item._values.copy(), 'y': None, 'pen': None, 'name': item.name(), 'style': {}}

    def brush_bins(self, item, series):
        return item._values, item.xData


class _NoBrushKind(_PointsKind):
    name = 'test_j_nobrush'
    capabilities = frozenset({'copy'})


for _kind in (_PointsKind(), _HistKind(), _NoBrushKind()):
    register_series_kind(_kind)


def _figure(n_plots=1):
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    axes = [f.subplot(i, 0) for i in range(n_plots)]
    return f, axes


def _set_range(ax, xr, yr):
    ax.plot_item.getViewBox().setRange(xRange=xr, yRange=yr, padding=0)
    app.processEvents()


def _brush_rows(f, series, rows, additive=False):
    """Brush exact rows, as a finished drag on series' subplot would."""
    plot = next(p for p in f.plots if series.item in p.listDataItems())
    f._on_rect_brush_finished(plot, {series.item: np.asarray(rows)}, additive)


def _highlight(f, series):
    for brusher in f._brushers.values():
        hl = brusher._highlights.get(series.item)
        if hl is not None:
            return hl
    return None


def _ramp_source(n=100):
    t = np.arange(n, dtype=float)
    return DataSource({'t': t, 'a': t * 2.0, 'b': 100.0 - t})


# -- near-zero overhead when Brush is off -----------------------------------
def test_million_row_series_with_brush_off_has_no_brush_overhead():
    f, (ax,) = _figure()
    n = 1_000_000
    src = DataSource({'t': np.arange(n, dtype=float), 'v': np.sin(np.arange(n) * 1e-3)})
    vb = ax.plot_item.getViewBox()
    brusher = f._brushers[ax.plot_item]
    s = ax.plot(src, x='t', y='v', clip_to_view=True, downsample='peak')
    assert not f.brushing, "control: Brush starts off"
    assert 'mouseDragEvent' not in vb.__dict__, "no brush drag handler may be connected while off"
    assert brusher.selection == {} and brusher._highlights == {} and brusher._bins == {}
    assert src._listeners == [], "no change subscription on the source"
    assert getattr(s.item, ROW_VIEW_ATTR, None) is None, "no row view/mask on the series"
    assert [i for i in vb.addedItems if i is not s.item] == [], "no overlay item"
    f.brush_action.trigger()
    assert 'mouseDragEvent' in vb.__dict__, "Brush on connects the drag handler"
    assert brusher.selection == {} and brusher._bins == {}, "turning Brush on computes nothing yet"
    f.brush_action.trigger()
    assert 'mouseDragEvent' not in vb.__dict__, "Brush off disconnects it again"
    f.close()


def test_line_hit_test_uses_full_data_not_the_clipped_display():
    f, (ax,) = _figure()
    n = 200_000
    t = np.linspace(0, 1000, n)
    s = ax.plot(t, np.sin(t), clip_to_view=True, downsample='peak')
    _set_range(ax, (0, 10), (-1.5, 1.5))  # the display only holds x in [0, 10]
    rect = QtCore.QRectF(500, -2, 100, 4)   # entirely off screen
    rows = sel_mod.rows_in_rect(s, rect)
    expected = np.nonzero((t >= 500) & (t <= 600))[0]
    assert np.array_equal(rows, expected), (rows.size, expected.size)
    f.close()


def test_show_rows_highlights_exactly_the_given_rows_of_a_line():
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    hl = sel_mod.show_rows(s, np.array([3, 7, 50]))
    x, y = hl.getData()
    assert list(x) == [3, 7, 50] and list(y) == [6, 14, 100]
    assert sel_mod.show_rows(s, np.array([], dtype=int)) is None
    f.close()


# -- brushing through real drags, on any kind --------------------------------
def test_real_drag_brushes_a_non_plotdataitem_point_kind_via_the_default_protocol():
    f, (ax,) = _figure()
    x = np.linspace(0, 100, 101)
    s = ax.test_j_points(x, x)
    _set_range(ax, (0, 100), (0, 100))
    f.brush_action.trigger()
    _brush_drag(f, ax.plot_item, (20, 80), (40, 10))
    items = f._figure_brush_items()
    assert len(items) == 1 and items[0][0] is s.item, items
    brushed = np.nonzero(items[0][1])[0]  # x == row here; endpoints are pixel-snapped
    assert brushed.min() in (20, 21) and brushed.max() in (39, 40), brushed
    assert np.array_equal(brushed, np.arange(brushed.min(), brushed.max() + 1))
    f.close()


def test_kind_without_brush_capability_is_never_brushed():
    f, (ax,) = _figure()
    x = np.linspace(0, 100, 101)
    ax.test_j_nobrush(x, x)
    line = ax.plot(x, x)
    _set_range(ax, (0, 100), (0, 100))
    f.brush_action.trigger()
    _brush_drag(f, ax.plot_item, (20, 80), (40, 10))
    assert [item for item, _ in f._figure_brush_items()] == [line.item]
    f.close()


def test_demo_scatters_brush_link_through_one_shared_source():
    """The two demo scatter subplots are now two series of one DataSource:
    a real brush drag on one highlights the same rows on the other."""
    f = shown_figure()
    p3, p4 = f.plots[2], f.plots[3]
    (s3,), (s4,) = f._series_on(p3), f._series_on(p4)
    src = s3.source
    assert s4.source is src and s3.rows is not None, "control: one explicit shared source"
    assert not hasattr(f, 'selection_model') and not hasattr(f, 'scatter1')

    def _no_visible_line(item):
        # The scatter kind uses a fully-transparent pen, not a NoPen style,
        # so its connecting line stays invisible without breaking click
        # hit-testing (see kinds/scatter.py's own module docstring for
        # why pen=None can't be used here) -- either style is "no line".
        pen = pg.mkPen(item.opts['pen'])
        return pen.style() == QtCore.Qt.NoPen or pen.color().alpha() == 0

    assert _no_visible_line(s3.item), "dots, no line through them"
    f._select_curve(s3.item)  # a selected scatter outlines its dots, still no line
    assert _no_visible_line(s3.item)
    f._deselect_curve()
    p3.getViewBox().setRange(xRange=(-3, 3), yRange=(-3, 3), padding=0)
    app.processEvents()
    f.brush_action.trigger()
    _brush_drag(f, p3, (0.0, 1.0), (1.0, 0.0))
    xa, xb = src[s3.columns[0]], src[s3.columns[1]]
    expected = np.nonzero((xa >= 0) & (xa <= 1) & (xb >= 0) & (xb <= 1))[0]
    assert expected.size > 50, "control: the rectangle catches a fair number of points"
    got3 = f._brushers[p3].selection[s3.item]
    got4 = f._brushers[p4].selection[s4.item]
    tol = 0.02  # the drag endpoints are pixel-snapped
    assert abs(got3.size - expected.size) <= max(3, tol * expected.size), (got3.size, expected.size)
    assert np.array_equal(got3, got4), "the other scatter highlights the very same rows"
    hx, hy = _highlight(f, s4).getData()
    assert np.array_equal(hx, src[s4.columns[0]][got4]) and np.array_equal(hy, src[s4.columns[1]][got4])
    # A plain (non-Shift) brush elsewhere unbrushes the linked pair.
    _brush_drag(f, p3, (-3.0, -2.0), (-2.9, -2.9))
    f.brush_action.trigger()
    assert all(not b.selection for b in f._brushers.values())
    f.close()


def test_shift_brush_adds_rows_across_linked_subplots():
    f, (ax1, ax2) = _figure(2)
    src = _ramp_source()
    s1 = ax1.plot(src, x='t', y='a')
    s2 = ax2.test_j_points(src, x='a', y='b')
    f.brush_action.trigger()
    _brush_rows(f, s1, [1, 2, 3])
    _brush_rows(f, s2, [10, 11], additive=True)
    assert list(f._brushers[ax1.plot_item].selection[s1.item]) == [1, 2, 3, 10, 11]
    assert list(f._brushers[ax2.plot_item].selection[s2.item]) == [1, 2, 3, 10, 11]
    _brush_rows(f, s2, [50])
    assert list(f._brushers[ax1.plot_item].selection[s1.item]) == [50]
    f.close()


def test_histogram_bars_link_to_rows_through_a_bin_index_computed_once():
    f, (ax_line, ax_hist) = _figure(2)
    rng = np.random.default_rng(1)
    src = DataSource({'t': np.arange(1000, dtype=float), 'v': rng.uniform(0, 10, 1000)})
    line = ax_line.plot(src, x='t', y='v')
    hist = ax_hist.test_j_hist(src, x='v', bins=10)  # bins of width 1 on [~0, ~10]
    f.brush_action.trigger()

    calls = []
    real_digitize = sel_mod.np.digitize
    sel_mod.np.digitize = lambda *a, **k: (calls.append(1), real_digitize(*a, **k))[1]
    try:
        # Brush the 4th bar (v in [edges[3], edges[4]]) on the histogram.
        edges = hist.item.xData
        mid = (edges[3] + edges[4]) / 2
        rect = QtCore.QRectF(mid - 0.01, 0.5, 0.02, 1)
        rows = f._brushers[ax_hist.plot_item].compute_matches(rect)[hist.item]
        v = src['v']
        in_bar = np.nonzero((v >= edges[3]) & (v < edges[4]))[0]
        assert np.array_equal(rows, in_bar)
        f._on_rect_brush_finished(ax_hist.plot_item, {hist.item: rows}, False)
        assert np.array_equal(f._brushers[ax_line.plot_item].selection[line.item], in_bar), \
            "brushing a bar selects its rows on the linked time series"

        # Brushing time-series points shows partial bars: bincount of their bins.
        _brush_rows(f, line, np.arange(100))
        hl = _highlight(f, hist)
        heights = hl.opts['height']
        expected = np.histogram(v[:100], bins=edges)[0]
        assert np.array_equal(heights, expected), (heights, expected)
        assert len(calls) == 1, f"np.digitize must run once per histogram, ran {len(calls)}x"
    finally:
        sel_mod.np.digitize = real_digitize
    f.close()


def test_histogram_like_kind_without_a_linked_partner_is_harmless():
    f, (ax,) = _figure()
    hist = ax.test_j_hist(np.random.default_rng(2).normal(size=500), bins=8)
    f.brush_action.trigger()
    _brush_drag(f, ax.plot_item, (-0.5, 5), (0.5, 0))
    assert f._figure_brush_items() == [], "bars are not points: the point actions skip them"
    f.hide_brushed_points()  # nothing point-like to hide: no crash
    f.close()


# -- Hide Brushed Points / Show All ----------------------------------------
def test_hide_brushed_points_hides_rows_in_every_linked_series_and_undoes():
    f, (ax1, ax2) = _figure(2)
    src = _ramp_source()
    a_before = np.array(src['a'])
    s1 = ax1.plot(src, x='t', y='a')
    s2 = ax2.test_j_points(src, x='a', y='b')
    f.brush_action.trigger()
    _brush_rows(f, s1, [5, 6, 7])
    f.hide_brushed_points()
    hidden = {5, 6, 7}
    for s in (s1, s2):
        assert hidden.isdisjoint(s.rows) and len(s.x) == 97, s
    assert list(np.nonzero(src.hidden_mask)[0]) == [5, 6, 7]
    assert np.array_equal(src['a'], a_before), "the dataset stays intact"
    assert all(not b.selection for b in f._brushers.values()), "hidden points are no longer brushed"
    f.undo()
    for s in (s1, s2):
        assert len(s.x) == 100 and list(s.rows) == list(range(100))
    assert not src.hidden_mask.any()
    f.redo()
    assert len(s1.x) == 97 and src.hidden_mask[5]
    f.show_all_hidden_points()
    assert len(s1.x) == 100 and len(s2.x) == 100 and not src.hidden_mask.any()
    np.testing.assert_array_equal(s1.y, a_before)
    f.undo()  # Show All is undoable too
    assert len(s1.x) == 97 and len(s2.x) == 97
    f.close()


def test_hide_keeps_values_edited_while_hidden():
    """set_data on the visible rows while some are hidden: Show All must
    bring the hidden rows back without losing the edit."""
    f, (ax,) = _figure()
    s = ax.plot(np.arange(10.0), np.arange(10.0))  # plain arrays: a private series
    f.brush_action.trigger()
    _brush_rows(f, s, [0, 1])
    f.hide_brushed_points()
    assert list(s.x) == list(range(2, 10))
    s.set_data(s.x, s.y + 100)
    f.show_all_hidden_points()
    assert list(s.y) == [0, 1] + [v + 100 for v in range(2, 10)]
    f.close()


def test_hidden_rows_follow_copy_paste_and_delete_undo():
    f, (ax1, ax2) = _figure(2)
    src = _ramp_source(20)
    s1 = ax1.plot(src, x='t', y='a')
    f.brush_action.trigger()
    _brush_rows(f, s1, [0, 1, 2])
    f.hide_brushed_points()
    f._select_curve(s1.item)
    f.copy_curve()
    f.focused_plot = ax2.plot_item
    f.paste_curve()
    (pasted,) = f._series_on(ax2.plot_item)
    assert pasted.source is src and len(pasted.x) == 17, "pasted: same source, same rows hidden"
    f.show_all_hidden_points()
    assert len(pasted.x) == 20, "the hidden rows came along and reappear"
    f.undo()
    f.delete_curve(s1.item)
    f.undo()
    (restored,) = f._series_on(ax1.plot_item)
    assert len(restored.x) == 17
    f.show_all_hidden_points()
    assert len(restored.x) == 20, "undoing a delete keeps the hidden rows too"
    f.close()


def test_delete_brushed_points_on_a_source_series_keeps_it_linked():
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    f.brush_action.trigger()
    _brush_rows(f, s, [0, 1])
    f.delete_brushed_points()
    assert s.source is src and list(s.rows) == list(range(2, 100))
    assert len(src) == 100, "the dataset is untouched"
    f.undo()
    assert list(s.rows) == list(range(100))
    f.close()


# -- derived columns ---------------------------------------------------------
def test_remove_average_on_a_source_series_writes_a_derived_column():
    f, (ax,) = _figure()
    t = np.arange(50, dtype=float)
    src = DataSource({'t': t, 'v': t + 7.0})
    s = ax.plot(src, x='t', y='v')
    f.focused_plot = ax.plot_item
    f.remove_average()
    derived = s.columns[1]
    assert derived != 'v' and derived in src.columns
    np.testing.assert_array_equal(src['v'], t + 7.0)  # original never overwritten
    np.testing.assert_allclose(src[derived], t - t.mean())
    np.testing.assert_allclose(s.y, t - t.mean())
    assert s.source is src
    f.undo()
    assert s.columns == ('t', 'v')
    np.testing.assert_array_equal(s.y, t + 7.0)
    f.redo()
    assert s.columns[1] == derived
    np.testing.assert_allclose(s.y, t - t.mean())
    f.close()


def test_transform_on_a_source_series_writes_a_derived_column():
    f, (ax,) = _figure()
    src = _ramp_source(10)
    s = ax.plot(src, x='t', y='a')
    f.brush_action.trigger()
    _brush_rows(f, s, [2, 3])
    saved = QtWidgets.QInputDialog.getText
    QtWidgets.QInputDialog.getText = staticmethod(lambda *a, **k: ("y * 10", True))
    try:
        f.transform_brushed_points()
    finally:
        QtWidgets.QInputDialog.getText = saved
    derived = s.columns[1]
    assert derived != 'a' and derived in src.columns
    np.testing.assert_array_equal(src['a'], np.arange(10) * 2.0)
    assert list(s.y) == [0, 2, 40, 60, 8, 10, 12, 14, 16, 18]
    f.undo()
    assert s.columns[1] == 'a' and list(s.y) == list(np.arange(10) * 2.0)
    f.close()


def test_transform_and_remove_average_stay_in_place_for_plain_arrays():
    f, (ax,) = _figure()
    s = ax.plot(np.arange(4.0), np.array([1.0, 2.0, 3.0, 6.0]))
    f.focused_plot = ax.plot_item
    f.remove_average()
    assert s.rows is None and list(s.y) == [-2, -1, 0, 3]
    f.undo()
    assert list(s.y) == [1, 2, 3, 6]
    f.close()


def test_fft_of_a_source_series_gets_its_own_source():
    f, (ax,) = _figure()
    t = np.linspace(0, 1, 256, endpoint=False)
    src = DataSource({'t': t, 'v': np.sin(2 * np.pi * 8 * t)})
    s = ax.plot(src, x='t', y='v')
    f.focused_plot = ax.plot_item
    f.fft_below()
    (fft_series,) = f._series_on(f.plots[-1])
    assert fft_series.source is not src and fft_series.rows is not None
    assert set(fft_series.columns) <= set(fft_series.source.columns)
    assert src.columns == ('t', 'v'), "the time series' own source is untouched"
    assert abs(fft_series.x[np.argmax(fft_series.y)] - 8) < 1e-9
    f.close()


# -- pasted series stay linked ----------------------------------------------
def test_subplot_pasted_into_another_window_stays_linked_to_its_source():
    fa, (ax,) = _figure()
    fb, _ = _figure()
    src = _ramp_source(30)
    s = ax.plot(src, x='t', y='a')
    fa._on_plot_clicked(ax.plot_item)
    fa.copy_subplot()
    fb.paste_subplot()
    (pasted,) = fb._series_on(fb.plots[-1])
    assert pasted.source is src and s.source is src
    # Hiding in one window reaches the other: hidden rows live on the source.
    fa.brush_action.trigger()
    _brush_rows(fa, s, [0, 1, 2, 3])
    fa.hide_brushed_points()
    assert len(pasted.x) == 26 and 0 not in pasted.rows
    fa.undo()
    assert len(pasted.x) == 30
    fa.close()
    fb.close()
