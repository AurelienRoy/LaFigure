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

"""R4-MISC: the 'barh', 'stem', 'heatmap', 'errorband' SeriesKinds
(lafigure/kinds/barh.py, stem.py, heatmap.py, errorband.py). Importing
these modules is what registers them with SERIES_KINDS --
lafigure/kinds/__init__.py already does so (this package's own diff to
it); lafigure/__init__.py (coordinator-owned) imports lafigure.kinds.
"""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

import lafigure.kinds.barh  # noqa: F401  (registers 'barh')
import lafigure.kinds.stem  # noqa: F401  (registers 'stem')
import lafigure.kinds.heatmap  # noqa: F401  (registers 'heatmap')
import lafigure.kinds.errorband  # noqa: F401  (registers 'errorband')
from lafigure.axes import Axes
from lafigure.kinds.barh import BarhKind
from lafigure.kinds.errorband import ErrorbandKind
from lafigure.kinds.stem import StemItem, StemKind
from lafigure.series import Series
from tests.helpers import app, m


def _shown_empty():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    return f


def _figure_with_axes():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    return f, ax


# -- barh -----------------------------------------------------------------

def test_barh_returns_a_series_backed_by_a_real_bargraphitem():
    f, ax = _figure_with_axes()
    s = ax.barh([0, 1, 2], [3.0, 5.0, 2.0], width=0.6)
    assert isinstance(s, Series) and s.kind == 'barh'
    assert isinstance(s.item, pg.BarGraphItem)
    assert s.item in ax.plot_item.items
    assert s in ax.series
    f.close()


def test_barh_bars_extend_along_x_with_categories_on_y():
    """Exact geometry check: category on Y (height=thickness), value on X
    from 0 (x0=0, width=value) -- the horizontal-vs-vertical swap from
    bar's own convention."""
    f, ax = _figure_with_axes()
    s = ax.barh([0.0, 1.0, 2.0], [4.0, -2.0, 6.0], width=0.5)
    item = s.item
    assert list(item.opts['y']) == [0.0, 1.0, 2.0], "category positions on Y"
    assert list(item.opts['width']) == [4.0, -2.0, 6.0], "values on X (via width)"
    assert list(np.atleast_1d(item.opts['x0'])) == [0.0, 0.0, 0.0], "bars start at X=0"
    assert item.opts['height'] == 0.5, "bar thickness on Y (via height)"
    f.close()


def test_barh_with_string_categories_sets_left_axis_tick_labels():
    f, ax = _figure_with_axes()
    s = ax.barh(['low', 'mid', 'high'], [1.0, 2.0, 3.0])
    assert list(s.x) == [0.0, 1.0, 2.0], "string categories become integer positions"
    assert list(s.y) == [1.0, 2.0, 3.0]
    ticks = ax.plot_item.getAxis('left')._tickLevels
    assert ticks and [lbl for _, lbl in ticks[0]] == ['low', 'mid', 'high']
    f.close()


def test_barh_negative_value_bar_still_starts_at_zero():
    f, ax = _figure_with_axes()
    s = ax.barh([0.0], [-3.0])
    x0, y0, x1, y1 = s.item._getNormalizedCoords()
    assert float(x0[0]) == -3.0 and float(x1[0]) == 0.0
    f.close()


def test_barh_to_dict_create_round_trip():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    x, y = np.array([0.0, 1.0, 2.0]), np.array([4.0, 1.0, 7.0])
    pen = pg.mkPen((10, 20, 30), width=2)
    s = f._add_series(p, 'barh', x, y, pen=pen, name='counts', width=0.4)
    d = s.to_dict()
    assert d['kind'] == 'barh'
    x[:] = -1  # the dict must not alias the caller's arrays
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert isinstance(s2.item, pg.BarGraphItem)
    assert np.array_equal(s2.x, [0.0, 1.0, 2.0])
    assert np.array_equal(s2.y, [4.0, 1.0, 7.0])
    assert s2.item.name() == 'counts'
    assert s2.item.opts['height'] == 0.4
    f.close()


def test_barh_set_xy_updates_the_bargraphitem_in_place():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    s = f._add_series(p, 'barh', [0.0, 1.0], [1.0, 2.0])
    kind = BarhKind()
    kind.set_xy(s.item, [0.0, 1.0], [9.0, 9.0])
    assert list(s.y) == [9.0, 9.0]
    assert list(s.item.opts['width']) == [9.0, 9.0]
    f.close()


def test_barh_item_has_no_curve_and_is_not_wired_clickable():
    f, ax = _figure_with_axes()
    s = ax.barh([0, 1], [1.0, 2.0])
    assert not hasattr(s.item, 'curve')
    f.close()


# -- stem -------------------------------------------------------------------

def test_stem_returns_a_series_backed_by_a_composite_item():
    f, ax = _figure_with_axes()
    s = ax.stem([0.0, 1.0, 2.0], [3.0, -1.0, 4.0])
    assert isinstance(s, Series) and s.kind == 'stem'
    assert isinstance(s.item, StemItem)
    assert s.item in ax.plot_item.listDataItems()
    assert s in ax.series
    assert not hasattr(s.item, 'curve'), "composite item is not click-selectable"
    f.close()


def test_stem_bounds_include_the_baseline():
    f, ax = _figure_with_axes()
    s = ax.stem([0.0, 1.0, 2.0], [3.0, 1.0, 5.0], baseline=0.0)
    r = s.item.boundingRect()
    assert (r.left(), r.right()) == (0.0, 2.0)
    assert (r.top(), r.bottom()) == (0.0, 5.0), "baseline (0) must be included even though all y > 0"
    f.close()


def test_stem_bounds_with_nonzero_baseline():
    f, ax = _figure_with_axes()
    s = ax.stem([0.0, 1.0], [2.0, 3.0], baseline=5.0)
    r = s.item.boundingRect()
    assert r.top() == 2.0 and r.bottom() == 5.0, "baseline above the data must extend the bounds up"
    f.close()


def test_stem_paints_a_line_per_sample_and_a_marker_per_tip():
    f, ax = _figure_with_axes()
    s = ax.stem([0.0, 1.0, 2.0], [1.0, 2.0, 3.0], marker_px=8.0)
    img = pg.QtGui.QImage(64, 64, pg.QtGui.QImage.Format_ARGB32)
    painter = pg.QtGui.QPainter(img)
    try:
        s.item.paint(painter)
    finally:
        painter.end()
    # No exception, and the item's own data is exactly what was passed in.
    x, y = s.item.getData()
    assert list(x) == [0.0, 1.0, 2.0] and list(y) == [1.0, 2.0, 3.0]
    f.close()


def test_stem_to_dict_create_round_trip():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    x, y = np.array([0.0, 1.0, 2.0]), np.array([3.0, -2.0, 5.0])
    pen = pg.mkPen((1, 2, 3), width=2)
    s = f._add_series(p, 'stem', x, y, pen=pen, name='impulses', baseline=1.0, marker_px=10.0)
    d = s.to_dict()
    assert d['kind'] == 'stem'
    assert d['style']['baseline'] == 1.0
    assert d['style']['marker_px'] == 10.0
    x[:] = -1  # the dict must not alias the caller's arrays
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert isinstance(s2.item, StemItem)
    assert list(s2.x) == [0.0, 1.0, 2.0]
    assert list(s2.y) == [3.0, -2.0, 5.0]
    assert s2.item.baseline == 1.0
    assert s2.item.marker_px == 10.0
    assert s2.item.name() == 'impulses'
    f.close()


def test_stem_set_data_undo_redo():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    s = f._add_series(p, 'stem', [0.0, 1.0], [1.0, 2.0])
    n_undo = len(f.undo_stack)
    s.set_data([0.0, 1.0, 2.0], [5.0, 6.0, 7.0])
    assert len(f.undo_stack) == n_undo + 1
    assert list(s.x) == [0.0, 1.0, 2.0] and list(s.y) == [5.0, 6.0, 7.0]
    f.undo()
    assert list(s.x) == [0.0, 1.0] and list(s.y) == [1.0, 2.0]
    f.redo()
    assert list(s.x) == [0.0, 1.0, 2.0] and list(s.y) == [5.0, 6.0, 7.0]
    f.close()


def test_stem_kind_get_xy_delegates_to_the_item():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    s = f._add_series(p, 'stem', [1.0, 2.0], [3.0, 4.0])
    kind = StemKind()
    x, y = kind.get_xy(s.item)
    assert list(x) == [1.0, 2.0] and list(y) == [3.0, 4.0]
    f.close()


# -- heatmap ----------------------------------------------------------------

def test_heatmap_returns_a_series_backed_by_a_real_imageitem_with_colorbar():
    f, ax = _figure_with_axes()
    matrix = np.arange(15, dtype=float).reshape(3, 5)
    s = ax.heatmap(matrix)
    assert isinstance(s, Series) and s.kind == 'heatmap'
    assert isinstance(s.item, pg.ImageItem)
    assert np.array_equal(s.item.image, matrix)
    assert s.item._lafigure_colorbar is not None, "must attach a LaColorBar, same as imshow"
    # Not `s in ax.series`: pg.ImageItem has no .implements('plotData')
    # (confirmed against the installed pyqtgraph), so listDataItems() never
    # lists it -- the same pre-existing limitation 'imshow' already has
    # (its own tests/test_kinds_i3.py never asserts this either).
    assert s.item in ax.plot_item.items
    f.close()


def test_heatmap_without_coords_matches_plain_imshow_default_rect():
    f, ax = _figure_with_axes()
    matrix = np.zeros((3, 5))
    s = ax.heatmap(matrix)
    rect = s.item.mapRectToParent(s.item.boundingRect())
    assert (rect.left(), rect.top()) == (0.0, 0.0)
    assert (rect.width(), rect.height()) == (5.0, 3.0), "default: raw pixel/column indices"
    f.close()


def test_heatmap_x_coords_y_coords_set_the_image_rect():
    f, ax = _figure_with_axes()
    matrix = np.zeros((3, 5))  # 3 rows, 5 cols
    x_coords = np.array([10.0, 12.0, 14.0, 16.0, 18.0])  # length 5 (ncols)
    y_coords = np.array([100.0, 200.0, 300.0])           # length 3 (nrows)
    s = ax.heatmap(matrix, x_coords=x_coords, y_coords=y_coords)
    rect = s.item.mapRectToParent(s.item.boundingRect())
    assert (rect.left(), rect.top()) == (10.0, 100.0)
    assert (rect.width(), rect.height()) == (8.0, 200.0)
    f.close()


def test_heatmap_x_coords_alone_leaves_y_at_default_row_indices():
    f, ax = _figure_with_axes()
    matrix = np.zeros((3, 5))  # 3 rows -> default y_coords = [0, 1, 2]
    s = ax.heatmap(matrix, x_coords=np.array([0.0, 1.0, 2.0, 3.0, 4.0]) * 2.0)
    rect = s.item.mapRectToParent(s.item.boundingRect())
    assert (rect.left(), rect.width()) == (0.0, 8.0)
    # y_coords omitted -> defaults to np.arange(nrows) = [0, 1, 2] -- the
    # rect spans endpoint to endpoint (0 to 2), NOT 0..nrows (3): once
    # coordinates are involved at all, they are sample positions, not raw
    # pixel-count spans (see heatmap.py's own docstring on this).
    assert (rect.top(), rect.height()) == (0.0, 2.0)
    f.close()


def test_heatmap_to_dict_create_round_trip_carries_coords():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    matrix = np.arange(6, dtype=float).reshape(2, 3)
    x_coords = np.array([0.0, 1.0, 2.0])
    y_coords = np.array([0.0, 5.0])
    s = f._add_series(p, 'heatmap', matrix, None, x_coords=x_coords, y_coords=y_coords, cmap='viridis')
    d = s.to_dict()
    assert d['kind'] == 'heatmap'
    np.testing.assert_array_equal(d['style']['x_coords'], x_coords)
    np.testing.assert_array_equal(d['style']['y_coords'], y_coords)
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert np.array_equal(s2.item.image, matrix)
    rect = s2.item.mapRectToParent(s2.item.boundingRect())
    assert (rect.left(), rect.top()) == (0.0, 0.0)
    assert (rect.width(), rect.height()) == (2.0, 5.0)
    f.close()


# -- errorband ----------------------------------------------------------------

def test_errorband_primary_item_is_a_real_clickable_plotdataitem():
    f, ax = _figure_with_axes()
    s = ax.errorband(np.linspace(0, 10, 11), np.zeros(11), yerr=0.5, pen=pg.mkPen('b', width=1))
    assert isinstance(s, Series) and s.kind == 'errorband'
    assert isinstance(s.item, pg.PlotDataItem)
    assert hasattr(s.item, 'curve') and s.item.curve.clickable
    assert s in ax.series
    f.close()


def test_errorband_band_item_traces_the_upper_and_lower_edges():
    f, ax = _figure_with_axes()
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([1.0, 2.0, 3.0])
    yerr = np.array([0.5, 1.0, 0.25])
    s = ax.errorband(x, y, yerr=yerr)
    band = s.item._lafigure_band
    assert isinstance(band, pg.PlotDataItem)
    assert band in ax.plot_item.items
    expected_x = np.concatenate([x, x[::-1]])
    expected_y = np.concatenate([y + yerr, (y - yerr)[::-1]])
    np.testing.assert_array_equal(band.xData, expected_x)
    np.testing.assert_array_equal(band.yData, expected_y)
    assert band.opts.get('fillLevel') == 'enclosed'
    f.close()


def test_errorband_asymmetric_bounds_via_y_lower_y_upper():
    f, ax = _figure_with_axes()
    x = np.array([0.0, 1.0])
    y = np.array([0.0, 0.0])
    s = ax.errorband(x, y, y_lower=np.array([-1.0, -2.0]), y_upper=np.array([3.0, 4.0]))
    band = s.item._lafigure_band
    expected_x = np.concatenate([x, x[::-1]])
    expected_y = np.concatenate([[3.0, 4.0], [-2.0, -1.0]])
    np.testing.assert_array_equal(band.xData, expected_x)
    np.testing.assert_array_equal(band.yData, expected_y)
    f.close()


def test_errorband_to_dict_create_round_trip_matches_original_bounds():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    x, y, yerr = np.array([0.0, 1.0, 2.0]), np.array([1.0, 2.0, 3.0]), np.array([0.1, 0.2, 0.3])
    pen = pg.mkPen((5, 6, 7), width=2)
    s = f._add_series(p, 'errorband', x, y, pen=pen, name='meas', yerr=yerr)
    d = s.to_dict()
    assert d['kind'] == 'errorband'
    np.testing.assert_allclose(d['style']['y_lower'], y - yerr)
    np.testing.assert_allclose(d['style']['y_upper'], y + yerr)
    x[:] = -1  # the dict must not alias the caller's arrays
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert np.array_equal(s2.x, [0.0, 1.0, 2.0])
    assert np.array_equal(s2.y, [1.0, 2.0, 3.0])
    band2 = s2.item._lafigure_band
    expected_x = np.concatenate([[0.0, 1.0, 2.0], [2.0, 1.0, 0.0]])
    expected_y = np.concatenate([y + yerr, (y - yerr)[::-1]])
    np.testing.assert_allclose(band2.xData, expected_x)
    np.testing.assert_allclose(band2.yData, expected_y)
    assert s2.item.name() == 'meas'
    f.close()


def test_errorband_set_data_moves_line_and_band_together_and_survives_undo_redo():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    s = f._add_series(p, 'errorband', [0.0, 1.0], [1.0, 2.0], yerr=0.5)
    band = s.item._lafigure_band
    n_undo = len(f.undo_stack)

    s.set_data([0.0, 1.0, 2.0], [5.0, 6.0, 7.0])
    assert len(f.undo_stack) == n_undo + 1
    assert list(s.x) == [0.0, 1.0, 2.0] and list(s.y) == [5.0, 6.0, 7.0]
    # The band's error widths are preserved (0.5) and follow the new y.
    np.testing.assert_allclose(band.yData, np.concatenate([[5.5, 6.5, 7.5], [6.5, 5.5, 4.5]]))

    f.undo()
    assert list(s.x) == [0.0, 1.0] and list(s.y) == [1.0, 2.0]
    np.testing.assert_allclose(band.yData, [1.5, 2.5, 1.5, 0.5])

    f.redo()
    assert list(s.x) == [0.0, 1.0, 2.0] and list(s.y) == [5.0, 6.0, 7.0]
    f.close()


def test_errorband_kind_get_xy_delegates_to_the_primary_item():
    f = _shown_empty()
    p = f.add_subplot(row=0, col=0)
    s = f._add_series(p, 'errorband', [1.0, 2.0], [3.0, 4.0], yerr=0.1)
    kind = ErrorbandKind()
    x, y = kind.get_xy(s.item)
    assert list(x) == [1.0, 2.0] and list(y) == [3.0, 4.0]
    f.close()


def test_errorband_band_pen_is_fully_transparent():
    f, ax = _figure_with_axes()
    s = ax.errorband([0.0, 1.0], [0.0, 0.0], yerr=1.0)
    band = s.item._lafigure_band
    assert band.opts['pen'].color().alpha() == 0
    f.close()
