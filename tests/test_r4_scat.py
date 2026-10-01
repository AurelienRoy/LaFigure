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

"""R4-SCAT: bubblechart, swarmchart, binscatter, spy (lafigure/kinds/)."""
import numpy as np

from lafigure.axes import Axes
from lafigure.datasource import DataSource
from lafigure.kinds import _base
from tests.helpers import m


def _figure_with_plot(row=0, col=0):
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=row, col=col)
    return f, p


# -- bubblechart -----------------------------------------------------------
def test_bubblechart_appears_in_ax_series_with_right_kind():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.bubblechart([0.0, 1.0], [0.0, 1.0], size=[1.0, 4.0], name='b')
    assert s.kind == 'bubblechart'
    assert s.item in [x.item for x in ax.series]
    f.close()


def test_bubblechart_size_is_area_proportional_via_size_scale():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    size = np.array([0.0, 1.0, 4.0])
    s = ax.bubblechart([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], size=size)
    expected = _base.size_scale(size)
    np.testing.assert_allclose(s.item.opts['symbolSize'], expected)
    f.close()


def test_bubblechart_with_no_size_uses_a_plain_default_size():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.bubblechart([0.0, 1.0], [0.0, 1.0])
    # No per-point variation requested -- a single scalar size, not an
    # array computed from a missing column.
    assert not hasattr(s.item.opts['symbolSize'], '__len__')
    f.close()


def test_bubblechart_color_attaches_a_colorbar_tracking_the_color_column():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    color = np.array([10.0, 20.0, 30.0])
    s = ax.bubblechart([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], size=[1.0, 2.0, 3.0], color=color)
    cb = s.item._lafigure_colorbar
    assert cb.data_range() == (10.0, 30.0)
    f.close()


def test_bubblechart_with_no_color_attaches_no_colorbar():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.bubblechart([0.0, 1.0], [0.0, 1.0], size=[1.0, 2.0])
    assert not hasattr(s.item, '_lafigure_colorbar'), \
        "a bubblechart with no color= column must attach no colorbar"
    f.close()


def test_bubblechart_to_dict_create_round_trip():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    size = np.array([1.0, 2.0, 3.0])
    color = np.array([5.0, 15.0, 25.0])
    s = ax.bubblechart([0.0, 1.0, 2.0], [3.0, 4.0, 5.0], size=size, color=color, name='rt')
    d = s.to_dict()
    assert d['kind'] == 'bubblechart'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    np.testing.assert_allclose(s2.x, s.x)
    np.testing.assert_allclose(s2.y, s.y)
    np.testing.assert_allclose(s2.item.opts['symbolSize'], s.item.opts['symbolSize'])
    assert s2.item.name() == 'rt'
    assert s2.item._lafigure_colorbar.data_range() == s.item._lafigure_colorbar.data_range()
    f.close()


def test_bubblechart_copy_paste_across_subplots():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.bubblechart([0.0, 1.0], [2.0, 3.0], size=[1.0, 2.0], name='cp')
    f._select_curve(s.item)
    f.copy_curve()
    q = f.add_subplot(row=1, col=0)
    f.focused_plot = q
    f.paste_curve()
    (pasted,) = f._series_on(q)
    assert pasted.kind == 'bubblechart'
    np.testing.assert_allclose(pasted.x, [0.0, 1.0])
    f.close()


def test_bubblechart_from_datasource_columns():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    src = DataSource({'px': [0.0, 1.0, 2.0], 'py': [0.0, 1.0, 2.0],
                       'mass': [1.0, 2.0, 3.0], 'temp': [5.0, 10.0, 15.0]})
    s = ax.bubblechart(src, x='px', y='py', size='mass', color='temp')
    expected = _base.size_scale(np.array([1.0, 2.0, 3.0]))
    np.testing.assert_allclose(s.item.opts['symbolSize'], expected)
    assert s.item._lafigure_colorbar.data_range() == (5.0, 15.0)
    f.close()


# -- swarmchart --------------------------------------------------------------
def test_swarmchart_appears_in_ax_series_with_right_kind():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.swarmchart(['a', 'b'], [1.0, 2.0])
    assert s.kind == 'swarmchart'
    assert s.item in [x.item for x in ax.series]
    f.close()


def test_swarmchart_categories_coded_first_seen_order_with_bottom_axis_ticks():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    ax.swarmchart(['b', 'a', 'b', 'c'], [1.0, 2.0, 3.0, 4.0])
    ticks = p.getAxis('bottom')._tickLevels
    assert ticks == [[(0.0, 'b'), (1.0, 'a'), (2.0, 'c')]]
    f.close()


def test_swarmchart_x_positions_are_jittered_category_codes():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    cats = np.array(['a', 'a', 'b', 'c', 'b'])
    s = ax.swarmchart(cats, [1.0, 2.0, 3.0, 4.0, 5.0], width=0.3, seed=7)
    codes, _ = _base.categories(cats)
    expected_x = _base.jitter(codes, width=0.3, seed=7)
    np.testing.assert_array_equal(s.x, expected_x)
    np.testing.assert_array_equal(s.y, [1.0, 2.0, 3.0, 4.0, 5.0])
    f.close()


def test_swarmchart_to_dict_stores_raw_categories_not_jittered_positions():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    cats = ['x', 'y', 'x']
    s = ax.swarmchart(cats, [1.0, 2.0, 3.0])
    d = s.to_dict()
    assert list(d['x']) == cats


def test_swarmchart_to_dict_create_round_trip_reproduces_identical_jitter():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    cats = np.array(['a', 'a', 'b', 'c', 'b'])
    s = ax.swarmchart(cats, [1.0, 2.0, 3.0, 4.0, 5.0], seed=3, name='sw')
    d = s.to_dict()
    assert d['kind'] == 'swarmchart'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    np.testing.assert_allclose(s2.x, s.x)
    np.testing.assert_allclose(s2.y, s.y)
    assert s2.item.name() == 'sw'
    f.close()


def test_swarmchart_from_datasource_columns():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    src = DataSource({'group': ['a', 'b', 'a'], 'val': [1.0, 2.0, 3.0]})
    s = ax.swarmchart(src, x='group', y='val')
    codes, labels = _base.categories(np.asarray(['a', 'b', 'a']))
    assert labels == ['a', 'b']
    np.testing.assert_array_equal(s.y, [1.0, 2.0, 3.0])
    f.close()


# -- binscatter --------------------------------------------------------------
def test_binscatter_appears_in_ax_series_with_right_kind():
    rng = np.random.default_rng(0)
    x, y = rng.uniform(0, 1, 50), rng.uniform(0, 1, 50)
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.binscatter(x, y, bins=5)
    assert s.kind == 'binscatter'
    assert s.item in [i.item for i in ax.series]
    f.close()


def test_binscatter_density_sums_to_the_sample_count():
    rng = np.random.default_rng(1)
    x, y = rng.uniform(0, 1, 200), rng.uniform(0, 1, 200)
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.binscatter(x, y, bins=10)
    assert s.item._lafigure_binscatter_density.sum() == 200


def test_binscatter_point_count_matches_nonempty_bins():
    rng = np.random.default_rng(2)
    x, y = rng.uniform(0, 1, 100), rng.uniform(0, 1, 100)
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.binscatter(x, y, bins=10)
    counts, _, _ = _base.bin2d(x, y, bins=10)
    assert len(s.x) == int(np.count_nonzero(counts))
    f.close()


def test_binscatter_colorbar_tracks_density_min_max():
    rng = np.random.default_rng(3)
    x, y = rng.uniform(0, 1, 300), rng.uniform(0, 1, 300)
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.binscatter(x, y, bins=8)
    cb = s.item._lafigure_colorbar
    density = s.item._lafigure_binscatter_density
    assert cb.data_range() == (float(density.min()), float(density.max()))
    f.close()


def test_binscatter_to_dict_create_round_trip_rebins_identically():
    rng = np.random.default_rng(4)
    x, y = rng.uniform(0, 1, 150), rng.uniform(0, 1, 150)
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.binscatter(x, y, bins=6, name='bs')
    d = s.to_dict()
    assert d['kind'] == 'binscatter'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    np.testing.assert_allclose(s2.x, s.x)
    np.testing.assert_allclose(s2.y, s.y)
    assert s2.item.name() == 'bs'
    f.close()


# -- spy -----------------------------------------------------------------------
def test_spy_appears_in_ax_series_with_right_kind():
    matrix = np.array([[0.0, 1.0], [2.0, 0.0]])
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.spy(matrix)
    assert s.kind == 'spy'
    assert s.item in [i.item for i in ax.series]
    f.close()


def test_spy_points_are_the_nonzero_entries_at_col_row():
    matrix = np.array([[0.0, 1.0, 0.0], [2.0, 0.0, 0.0], [0.0, 0.0, 3.0]])
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.spy(matrix)
    row_idx, col_idx = np.nonzero(matrix)
    np.testing.assert_array_equal(s.x, col_idx.astype(float))
    np.testing.assert_array_equal(s.y, row_idx.astype(float))
    f.close()


def test_spy_y_axis_is_inverted_like_imshow():
    matrix = np.eye(3)
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    ax.spy(matrix)
    assert p.getViewBox().yInverted(), "row 0 must draw at the top, like imshow"
    f.close()


def test_spy_empty_matrix_produces_no_points():
    matrix = np.zeros((3, 3))
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.spy(matrix)
    # A zero-length pg.PlotDataItem leaves xData/yData as None (verified
    # against the installed pyqtgraph), not an empty array -- "no points"
    # either way.
    assert s.x is None or len(s.x) == 0
    f.close()


def test_spy_to_dict_create_round_trip():
    matrix = np.array([[0.0, 1.0, 0.0], [2.0, 0.0, 0.0], [0.0, 0.0, 3.0]])
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.spy(matrix, name='sp')
    d = s.to_dict()
    assert d['kind'] == 'spy'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    np.testing.assert_array_equal(s2.x, s.x)
    np.testing.assert_array_equal(s2.y, s.y)
    assert s2.item.name() == 'sp'
    f.close()


def test_spy_copy_paste_across_subplots():
    matrix = np.array([[0.0, 1.0], [2.0, 0.0]])
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.spy(matrix, name='spcp')
    f._select_curve(s.item)
    f.copy_curve()
    q = f.add_subplot(row=1, col=0)
    f.focused_plot = q
    f.paste_curve()
    (pasted,) = f._series_on(q)
    assert pasted.kind == 'spy'
    np.testing.assert_array_equal(pasted.x, s.x)
    f.close()
