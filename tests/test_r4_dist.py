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

"""lafigure/kinds/boxchart.py and violinplot.py (PLAN.md "R4-DIST")."""
import numpy as np

from lafigure.datasource import DataSource
from lafigure.kinds import _base
from lafigure.kinds.boxchart import BoxChartItem
from lafigure.kinds.violinplot import ViolinItem
from tests.helpers import m


def _figure_with_axes():
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0)
    return f, ax


# -- boxchart -------------------------------------------------------------
def test_boxchart_appears_in_ax_series_with_right_kind():
    f, ax = _figure_with_axes()
    s = ax.boxchart(['a', 'a', 'b', 'b'], [1.0, 2.0, 3.0, 4.0], name='box')
    assert isinstance(s.item, BoxChartItem)
    assert s.item in ax.plot_item.listDataItems()
    assert s in ax.series
    assert s.kind == 'boxchart'
    f.close()


def test_boxchart_not_click_selectable():
    f, ax = _figure_with_axes()
    s = ax.boxchart(['a', 'b'], [1.0, 2.0])
    assert not hasattr(s.item, 'curve'), "control: a composite item is not click-selectable"
    f.close()


def test_boxchart_matches_base_quantiles_per_category():
    f, ax = _figure_with_axes()
    values_a = [1, 2, 3, 4, 5, 6, 7, 8, 9, 100]
    values_b = [10.0, 20.0, 30.0]
    labels = ['a'] * len(values_a) + ['b'] * len(values_b)
    values = list(values_a) + list(values_b)
    s = ax.boxchart(labels, values)
    expect_a = _base.quantiles(values_a)
    expect_b = _base.quantiles(values_b)
    stats = s.item._stats
    # 'a' is first-seen, so its code is 0; 'b' is 1.
    assert stats[0]['q1'] == expect_a['q1']
    assert stats[0]['med'] == expect_a['med']
    assert stats[0]['q3'] == expect_a['q3']
    assert list(stats[0]['outliers']) == list(expect_a['outliers'])
    assert stats[1]['med'] == expect_b['med']
    f.close()


def test_boxchart_applies_category_ticks_in_first_seen_order():
    f, ax = _figure_with_axes()
    ax.boxchart(['z', 'z', 'a', 'a'], [1.0, 2.0, 3.0, 4.0])
    ticks = ax.plot_item.getAxis('bottom')._tickLevels
    assert ticks == [[(0.0, 'z'), (1.0, 'a')]]
    f.close()


def test_boxchart_bounding_rect_matches_bounds():
    f, ax = _figure_with_axes()
    s = ax.boxchart(['a', 'a', 'a', 'a', 'a'], [1.0, 2.0, 3.0, 4.0, 50.0])
    r = s.item.boundingRect()
    b = s.item._bounds()
    assert (r.left(), r.right()) == (b[0], b[1])
    assert (r.top(), r.bottom()) == (b[2], b[3])
    # The outlier (50.0, way outside 1.5*IQR of [1,2,3,4]) must widen the
    # bounds beyond the whisker range.
    assert b[3] >= 50.0
    f.close()


def test_boxchart_to_dict_create_round_trip_preserves_labels():
    f, ax = _figure_with_axes()
    s = ax.boxchart(['low', 'low', 'high', 'high'], [1.0, 2.0, 9.0, 10.0], name='b')
    d = s.to_dict()
    assert d['kind'] == 'boxchart'
    assert sorted(set(d['x'].tolist())) == ['high', 'low']
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'boxchart'
    assert s2.item.labels == ['low', 'high']
    assert list(q.getAxis('bottom')._tickLevels[0]) == [(0.0, 'low'), (1.0, 'high')]
    np.testing.assert_allclose(sorted(s2.item.getData()[1]), sorted(s.item.getData()[1]))
    f.close()


def test_boxchart_round_trips_through_copy_paste():
    f, ax = _figure_with_axes()
    s = ax.boxchart(['a', 'a', 'b', 'b'], [1.0, 2.0, 3.0, 4.0], name='boxy')
    f._select_curve(s.item)
    f.copy_curve()
    q = f.add_subplot(row=1, col=0)
    f.focused_plot = q
    f.paste_curve()
    (pasted,) = f._series_on(q)
    assert pasted.kind == 'boxchart'
    assert pasted.item.name() == 'boxy'
    assert pasted.item.labels == ['a', 'b']
    f.close()


def test_boxchart_from_datasource_columns_stays_linked():
    f, ax = _figure_with_axes()
    src = DataSource({'cat': np.array(['a', 'a', 'b', 'b']), 'val': np.array([1.0, 2.0, 3.0, 4.0])})
    s = ax.boxchart(src, x='cat', y='val')
    assert s.source is src
    assert list(s.item.labels) == ['a', 'b']
    f.close()


# -- violinplot -------------------------------------------------------------
def test_violinplot_appears_in_ax_series_with_right_kind():
    f, ax = _figure_with_axes()
    rng = np.random.default_rng(0)
    values = list(rng.normal(size=50)) + list(rng.normal(loc=5, size=50))
    labels = ['a'] * 50 + ['b'] * 50
    s = ax.violinplot(labels, values, name='violin')
    assert isinstance(s.item, ViolinItem)
    assert s.item in ax.plot_item.listDataItems()
    assert s in ax.series
    assert s.kind == 'violinplot'
    f.close()


def test_violinplot_not_click_selectable():
    f, ax = _figure_with_axes()
    s = ax.violinplot(['a', 'b'], [1.0, 2.0])
    assert not hasattr(s.item, 'curve'), "control: a composite item is not click-selectable"
    f.close()


def test_violinplot_matches_base_kde_per_category():
    f, ax = _figure_with_axes()
    rng = np.random.default_rng(1)
    values_a = list(rng.normal(size=200))
    labels = ['a'] * len(values_a)
    s = ax.violinplot(labels, values_a, kde_points=256)
    expect_grid, expect_density = _base.kde(values_a, points=256)
    grid, norm, med = s.item._violins[0]
    np.testing.assert_allclose(grid, expect_grid)
    peak = expect_density.max()
    np.testing.assert_allclose(norm, expect_density / peak)
    assert norm.max() == 1.0
    assert med == float(np.median(values_a))
    f.close()


def test_violinplot_applies_category_ticks_in_first_seen_order():
    f, ax = _figure_with_axes()
    ax.violinplot(['z', 'z', 'a', 'a'], [1.0, 2.0, 3.0, 4.0])
    ticks = ax.plot_item.getAxis('bottom')._tickLevels
    assert ticks == [[(0.0, 'z'), (1.0, 'a')]]
    f.close()


def test_violinplot_bounding_rect_matches_bounds():
    f, ax = _figure_with_axes()
    s = ax.violinplot(['a', 'a', 'a'], [1.0, 2.0, 3.0])
    r = s.item.boundingRect()
    b = s.item._bounds()
    assert (r.left(), r.right()) == (b[0], b[1])
    assert (r.top(), r.bottom()) == (b[2], b[3])
    half = s.item.violin_width / 2.0
    assert b[0] == -half and b[1] == half
    f.close()


def test_violinplot_to_dict_create_round_trip_preserves_labels():
    f, ax = _figure_with_axes()
    s = ax.violinplot(['low', 'low', 'high', 'high'], [1.0, 2.0, 9.0, 10.0], name='v')
    d = s.to_dict()
    assert d['kind'] == 'violinplot'
    assert sorted(set(d['x'].tolist())) == ['high', 'low']
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'violinplot'
    assert s2.item.labels == ['low', 'high']
    assert list(q.getAxis('bottom')._tickLevels[0]) == [(0.0, 'low'), (1.0, 'high')]
    np.testing.assert_allclose(sorted(s2.item.getData()[1]), sorted(s.item.getData()[1]))
    f.close()


def test_violinplot_round_trips_through_copy_paste():
    f, ax = _figure_with_axes()
    s = ax.violinplot(['a', 'a', 'b', 'b'], [1.0, 2.0, 3.0, 4.0], name='vio')
    f._select_curve(s.item)
    f.copy_curve()
    q = f.add_subplot(row=1, col=0)
    f.focused_plot = q
    f.paste_curve()
    (pasted,) = f._series_on(q)
    assert pasted.kind == 'violinplot'
    assert pasted.item.name() == 'vio'
    assert pasted.item.labels == ['a', 'b']
    f.close()


def test_violinplot_from_datasource_columns_stays_linked():
    f, ax = _figure_with_axes()
    src = DataSource({'cat': np.array(['a', 'a', 'b', 'b']), 'val': np.array([1.0, 2.0, 3.0, 4.0])})
    s = ax.violinplot(src, x='cat', y='val')
    assert s.source is src
    assert list(s.item.labels) == ['a', 'b']
    f.close()


def test_violinplot_single_value_category_does_not_raise():
    f, ax = _figure_with_axes()
    s = ax.violinplot(['a', 'a', 'a'], [5.0, 5.0, 5.0])
    grid, norm, med = s.item._violins[0]
    assert med == 5.0
    assert norm.sum() > 0
    f.close()
