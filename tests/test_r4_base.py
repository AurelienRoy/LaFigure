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

"""lafigure/kinds/_base.py -- CompositeSeriesItem, DerivedKind, and the
plain-numpy helpers every round-4 kind package builds on."""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

from lafigure.axes import Axes
from lafigure.kinds import _base
from lafigure.series import SeriesKind, register_series_kind
from tests.helpers import m


def _figure_with_plot():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    return f, p


# -- a minimal CompositeSeriesItem subclass, for testing only -----------------
class _DummyComposite(_base.CompositeSeriesItem):
    """Not click-selectable (no .curve) -- accepted, per the base class's
    own docstring; this is a test double, not a real kind."""

    def __init__(self, x, y, **kw):
        super().__init__(**kw)
        self._x = np.asarray(x, dtype=float)
        self._y = np.asarray(y, dtype=float)
        self.paint_calls = 0

    def _bounds(self):
        if len(self._x) == 0:
            return None
        return float(self._x.min()), float(self._x.max()), float(self._y.min()), float(self._y.max())

    def _paint(self, painter):
        self.paint_calls += 1
        painter.setPen(self.pen)
        for x, y in zip(self._x, self._y):
            painter.drawPoint(QtCore.QPointF(x, y))

    def getData(self):
        return self._x, self._y

    def set_xy(self, x, y):
        self._x = np.asarray(x, dtype=float)
        self._y = np.asarray(y, dtype=float)
        self.invalidate()


class _DummyCompositeKind(SeriesKind):
    name = 'test_r4base_composite'
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None, **style):
        item = _DummyComposite(x, y, name=name, pen=pen)
        plot_item.addItem(item)
        return item

    def to_dict(self, item):
        x, y = item.getData()
        return {'x': np.array(x, copy=True), 'y': np.array(y, copy=True),
                'pen': item.opts.get('pen'), 'name': item.name(), 'style': {}}

    def get_xy(self, item):
        return item.getData()

    def set_xy(self, item, x, y):
        item.set_xy(x, y)


register_series_kind(_DummyCompositeKind())


def test_composite_series_item_appears_in_list_data_items_and_ax_series():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'test_r4base_composite', [0.0, 1.0, 2.0], [3.0, 1.0, 4.0], name='d')
    assert isinstance(s.item, _base.CompositeSeriesItem)
    assert s.item in p.listDataItems(), "implements('plotData') must file it into listDataItems()"
    ax = Axes(f, p)
    assert s.item in [x.item for x in ax.series]
    assert not hasattr(s.item, 'curve'), "control: a composite item is not click-selectable"
    f.close()


def test_composite_series_item_bounding_rect_matches_bounds():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'test_r4base_composite', [0.0, 2.0, 5.0], [1.0, 4.0, -1.0])
    r = s.item.boundingRect()
    assert (r.left(), r.right()) == (0.0, 5.0)
    assert (r.top(), r.bottom()) == (-1.0, 4.0)
    f.close()


def test_composite_series_item_empty_bounds_is_an_empty_rect():
    item = _DummyComposite([], [])
    r = item.boundingRect()
    assert r.isEmpty() or (r.width() == 0 and r.height() == 0)


def test_composite_series_item_invalidate_recomputes_bounds_and_repaints():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'test_r4base_composite', [0.0, 1.0], [0.0, 1.0])
    r0 = s.item.boundingRect()
    assert (r0.right(), r0.bottom()) == (1.0, 1.0)
    s.item.set_xy([0.0, 10.0], [0.0, 10.0])
    r1 = s.item.boundingRect()
    assert (r1.right(), r1.bottom()) == (10.0, 10.0), "invalidate() must drop the cached bounds"
    f.close()


def test_composite_series_item_paints_without_raising():
    f, p = _figure_with_plot()
    f.show()
    s = f._add_series(p, 'test_r4base_composite', [0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    img = pg.QtGui.QImage(64, 64, pg.QtGui.QImage.Format_ARGB32)
    painter = pg.QtGui.QPainter(img)
    try:
        s.item.paint(painter)
    finally:
        painter.end()
    assert s.item.paint_calls == 1
    f.close()


def test_composite_series_item_get_xy_and_set_xy_round_trip_through_series():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'test_r4base_composite', [0.0, 1.0], [2.0, 3.0])
    assert list(s.x) == [0.0, 1.0] and list(s.y) == [2.0, 3.0]
    s.set_data([5.0, 6.0, 7.0], [8.0, 9.0, 10.0])
    assert list(s.x) == [5.0, 6.0, 7.0] and list(s.y) == [8.0, 9.0, 10.0]
    f.undo()
    assert list(s.x) == [0.0, 1.0]
    f.close()


# -- DerivedKind ---------------------------------------------------------------
class _DerivedOnLine(_base.DerivedKind):
    name = 'test_r4base_derived'
    base = 'line'
    create_defaults = {'clip_to_view': False}

    def setup(self, plot_item, item, **kwargs):
        item._test_setup_kwargs = dict(kwargs)


register_series_kind(_DerivedOnLine())


def test_derived_kind_delegates_create_to_its_base():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'test_r4base_derived', [0.0, 1.0], [2.0, 3.0], name='d')
    assert isinstance(s.item, pg.PlotDataItem), "base='line' must build a real PlotDataItem"
    assert s.item in p.listDataItems()
    assert s.item.opts['clipToView'] is False, "create_defaults must reach the base kind's create()"
    f.close()


def test_derived_kind_setup_hook_runs_after_create_with_the_merged_kwargs():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'test_r4base_derived', [0.0], [0.0])
    assert s.item._test_setup_kwargs == {'clip_to_view': False}
    f.close()


def test_derived_kind_caller_style_overrides_create_defaults():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'test_r4base_derived', [0.0], [0.0], clip_to_view=True)
    assert s.item.opts['clipToView'] is True, "the caller's own style must win over create_defaults"
    assert s.item._test_setup_kwargs == {'clip_to_view': True}
    f.close()


def test_derived_kind_capabilities_default_to_the_base_kinds():
    from lafigure.series import SERIES_KINDS
    derived = SERIES_KINDS['test_r4base_derived']
    line = SERIES_KINDS['line']
    assert derived.capabilities == line.capabilities


class _DerivedNarrowedCapabilities(_base.DerivedKind):
    name = 'test_r4base_derived_narrow'
    base = 'line'
    capabilities = frozenset({'copy'})  # a plain class attribute overrides the property


register_series_kind(_DerivedNarrowedCapabilities())


def test_derived_kind_subclass_can_override_capabilities_directly():
    from lafigure.series import SERIES_KINDS
    narrowed = SERIES_KINDS['test_r4base_derived_narrow']
    assert narrowed.capabilities == frozenset({'copy'})


def test_derived_kind_get_xy_set_xy_delegate_to_the_base():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'test_r4base_derived', [0.0, 1.0], [2.0, 3.0])
    assert list(s.x) == [0.0, 1.0] and list(s.y) == [2.0, 3.0]
    s.set_data([9.0], [9.0])
    assert list(s.x) == [9.0] and list(s.y) == [9.0]
    f.close()


def test_derived_kind_round_trips_through_copy_paste():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'test_r4base_derived', [0.0, 1.0, 2.0], [3.0, 4.0, 5.0], name='abc')
    f._select_curve(s.item)
    f.copy_curve()
    q = f.add_subplot(row=1, col=0)
    f.focused_plot = q
    f.paste_curve()
    (pasted,) = f._series_on(q)
    assert pasted.kind == 'test_r4base_derived'
    assert list(pasted.x) == [0.0, 1.0, 2.0] and list(pasted.y) == [3.0, 4.0, 5.0]
    assert pasted.item.name() == 'abc'
    f.close()


def test_derived_kind_to_dict_create_round_trip_directly():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'test_r4base_derived', [0.0, 1.0], [2.0, 3.0], name='xyz')
    d = s.to_dict()
    assert d['kind'] == 'test_r4base_derived'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'test_r4base_derived' and list(s2.y) == [2.0, 3.0]
    assert s2.item.name() == 'xyz'
    f.close()


# -- categories / apply_category_ticks / clear_category_ticks -----------------
def test_categories_are_coded_in_first_seen_order():
    codes, labels = _base.categories(['b', 'a', 'b', 'c', 'a'])
    assert labels == ['b', 'a', 'c']
    assert list(codes) == [0, 1, 0, 2, 1]


def test_categories_numeric_input_is_bucketed_by_value():
    codes, labels = _base.categories([10, 20, 10, 30])
    assert labels == ['10', '20', '30']
    assert list(codes) == [0, 1, 0, 2]


def test_apply_and_clear_category_ticks():
    f, p = _figure_with_plot()
    _base.apply_category_ticks(p, 'bottom', ['low', 'mid', 'high'])
    ticks = p.getAxis('bottom')._tickLevels
    assert ticks == [[(0.0, 'low'), (1.0, 'mid'), (2.0, 'high')]]
    _base.clear_category_ticks(p, 'bottom')
    assert p.getAxis('bottom')._tickLevels is None
    f.close()


# -- jitter ---------------------------------------------------------------------
def test_jitter_is_deterministic_for_the_same_seed():
    codes = np.array([0, 0, 1, 1, 2])
    a = _base.jitter(codes, width=0.3, seed=42)
    b = _base.jitter(codes, width=0.3, seed=42)
    np.testing.assert_array_equal(a, b)
    assert np.all(np.abs(a - codes) <= 0.3 + 1e-12)


def test_jitter_different_seeds_differ():
    codes = np.array([0, 0, 0, 0, 0])
    a = _base.jitter(codes, width=0.3, seed=1)
    b = _base.jitter(codes, width=0.3, seed=2)
    assert not np.array_equal(a, b)


# -- value_colors -----------------------------------------------------------------
def test_value_colors_maps_min_and_max_to_the_colormap_ends():
    values = np.array([0.0, 5.0, 10.0])
    brushes, (lo, hi) = _base.value_colors(values, cmap='viridis')
    assert (lo, hi) == (0.0, 10.0)
    assert len(brushes) == 3
    cmap = pg.colormap.get('viridis')
    lo_color, hi_color = cmap.map([0.0, 1.0], mode='qcolor')
    assert brushes[0].color().getRgb() == lo_color.getRgb()
    assert brushes[2].color().getRgb() == hi_color.getRgb()


def test_value_colors_respects_explicit_levels():
    values = np.array([5.0, 15.0])
    brushes, (lo, hi) = _base.value_colors(values, cmap='viridis', levels=(0.0, 20.0))
    assert (lo, hi) == (0.0, 20.0)
    cmap = pg.colormap.get('viridis')
    expect_low = cmap.map([0.25], mode='qcolor')[0]
    assert brushes[0].color().getRgb() == expect_low.getRgb()


def test_value_colors_constant_input_does_not_raise():
    brushes, (lo, hi) = _base.value_colors(np.array([3.0, 3.0, 3.0]))
    assert lo == hi == 3.0
    assert len(brushes) == 3


# -- size_scale ----------------------------------------------------------------
def test_size_scale_is_area_proportional_not_diameter_proportional():
    sizes = _base.size_scale(np.array([0.0, 1.0, 4.0]), lo_px=0.0, hi_px=10.0)
    # normalized values 0, 0.25, 1 -> sqrt -> 0, 0.5, 1 -> sizes 0, 5, 10
    np.testing.assert_allclose(sizes, [0.0, 5.0, 10.0])


def test_size_scale_min_and_max_hit_lo_px_and_hi_px():
    sizes = _base.size_scale(np.array([2.0, 9.0]), lo_px=4.0, hi_px=24.0)
    np.testing.assert_allclose(sizes, [4.0, 24.0])


def test_size_scale_constant_input_does_not_raise():
    sizes = _base.size_scale(np.array([7.0, 7.0]), lo_px=4.0, hi_px=24.0)
    np.testing.assert_allclose(sizes, [4.0, 4.0])


# -- bin2d --------------------------------------------------------------------
def test_bin2d_counts_sum_to_n_points():
    rng = np.random.default_rng(0)
    x, y = rng.uniform(0, 1, 500), rng.uniform(0, 1, 500)
    counts, x_edges, y_edges = _base.bin2d(x, y, bins=10)
    assert counts.shape == (10, 10)
    assert counts.sum() == 500
    assert x_edges[0] <= x.min() and x_edges[-1] >= x.max()
    assert y_edges[0] <= y.min() and y_edges[-1] >= y.max()


# -- quantiles -------------------------------------------------------------------
def test_quantiles_matches_numpy_percentile_and_flags_outliers():
    values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
    q = _base.quantiles(values)
    q1, med, q3 = np.percentile(values, [25, 50, 75])
    assert (q['q1'], q['med'], q['q3']) == (q1, med, q3)
    assert 100 in q['outliers']
    assert q['hi_whisker'] < 100, "the whisker must stop at a real in-range data point"


def test_quantiles_empty_input_returns_nan_not_a_crash():
    q = _base.quantiles([])
    assert np.isnan(q['q1']) and q['outliers'].size == 0


# -- kde --------------------------------------------------------------------------
def test_kde_integrates_to_approximately_one():
    rng = np.random.default_rng(1)
    values = rng.normal(size=2000)
    grid, density = _base.kde(values, points=512)
    area = np.trapz(density, grid)
    assert 0.9 < area < 1.1, area


def test_kde_single_value_is_a_spike_not_a_crash():
    grid, density = _base.kde([5.0, 5.0, 5.0], points=32)
    assert density.sum() == 1.0
    # The spike lands on the nearest of `points` discrete grid samples, not
    # necessarily exactly on 5.0 (32 evenly spaced samples over [4.5, 5.5]
    # don't have to include 5.0 itself).
    assert abs(grid[int(np.argmax(density))] - 5.0) < (grid[1] - grid[0])


def test_kde_empty_input_does_not_raise():
    grid, density = _base.kde([], points=16)
    assert len(grid) == 16 and np.all(density == 0.0)
