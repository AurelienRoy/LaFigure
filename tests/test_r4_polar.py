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

"""Tests for PLAN.md's R4-POLAR: lafigure/kinds/_polar_base.py + the
polar / polarhistogram / piechart kinds."""
import math

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui

import lafigure as m
from lafigure.axes import Axes
from lafigure.kinds import _polar_base as pb
from tests.helpers import has_border  # noqa: F401 (kept importable-parity with other test files)


def _figure_with_plot():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    return f, p


def _ax():
    f, p = _figure_with_plot()
    return f, p, Axes(f, p)


def _paint(item):
    img = QtGui.QImage(64, 64, QtGui.QImage.Format_ARGB32)
    painter = QtGui.QPainter(img)
    try:
        item.paint(painter)
    finally:
        painter.end()


# -- polar_to_xy ----------------------------------------------------------------
def test_polar_to_xy_basic_angles():
    theta = np.array([0.0, math.pi / 2, math.pi, 3 * math.pi / 2])
    r = np.array([1.0, 2.0, 3.0, 4.0])
    x, y = pb.polar_to_xy(theta, r)
    np.testing.assert_allclose(x, [1.0, 0.0, -3.0, 0.0], atol=1e-9)
    np.testing.assert_allclose(y, [0.0, 2.0, 0.0, -4.0], atol=1e-9)


def test_polar_to_xy_negative_r_lands_on_the_opposite_side():
    x, y = pb.polar_to_xy(np.array([0.0]), np.array([-1.0]))
    np.testing.assert_allclose(x, [-1.0], atol=1e-9)
    np.testing.assert_allclose(y, [0.0], atol=1e-9)


# -- setup_polar_axes / draw_polar_grid / grow_polar_grid -----------------------
def test_setup_polar_axes_hides_axes_and_locks_aspect():
    f, p = _figure_with_plot()
    pb.setup_polar_axes(p)
    for axis in ('left', 'bottom', 'top', 'right'):
        assert not p.getAxis(axis).isVisible()
    assert p.getViewBox().state['aspectLocked']
    f.close()


def test_draw_polar_grid_adds_items_and_sets_range():
    f, p = _figure_with_plot()
    items = pb.draw_polar_grid(p, rmax=5.0)
    assert len(items) > 0
    for it in items:
        assert it.scene() is not None
    vb = p.getViewBox()
    (x0, x1), (y0, y1) = vb.viewRange()
    assert x1 > 5.0 and y1 > 5.0
    f.close()


def test_draw_polar_grid_called_twice_replaces_not_stacks():
    f, p = _figure_with_plot()
    first = pb.draw_polar_grid(p, rmax=2.0)
    second = pb.draw_polar_grid(p, rmax=2.0)
    assert len(first) == len(second)
    # the first batch must have been removed from the scene
    for it in first:
        assert it.scene() is None
    f.close()


def test_grow_polar_grid_grows_but_never_shrinks():
    f, p = _figure_with_plot()
    pb.grow_polar_grid(p, 2.0)
    assert getattr(p, pb._GRID_RMAX_ATTR) == 2.0
    pb.grow_polar_grid(p, 1.0)
    assert getattr(p, pb._GRID_RMAX_ATTR) == 2.0, "must not shrink back down"
    pb.grow_polar_grid(p, 5.0)
    assert getattr(p, pb._GRID_RMAX_ATTR) == 5.0
    f.close()


def test_clear_polar_grid_removes_everything():
    f, p = _figure_with_plot()
    items = pb.draw_polar_grid(p, rmax=3.0)
    pb.clear_polar_grid(p)
    for it in items:
        assert it.scene() is None
    assert getattr(p, pb._GRID_ATTR) == []
    f.close()


# -- polar ------------------------------------------------------------------------
def test_polar_series_appears_with_right_kind_and_drawn_cartesian_xy():
    f, p, ax = _ax()
    theta = np.array([0.0, math.pi / 2])
    r = np.array([1.0, 2.0])
    s = ax.polar(theta, r, name='trace')
    assert s.kind == 'polar'
    assert s in ax.series
    np.testing.assert_allclose(list(s.x), [1.0, 0.0], atol=1e-9)
    np.testing.assert_allclose(list(s.y), [0.0, 2.0], atol=1e-9)
    assert isinstance(s.item, pg.PlotDataItem), "polar delegates to 'line' -- a real PlotDataItem"
    f.close()


def test_polar_axes_are_hidden_and_aspect_locked():
    f, p, ax = _ax()
    ax.polar(np.array([0.0, 1.0]), np.array([1.0, 2.0]))
    assert not p.getAxis('bottom').isVisible()
    assert p.getViewBox().state['aspectLocked']
    f.close()


def test_polar_draws_a_grid_sized_to_the_data():
    f, p, ax = _ax()
    ax.polar(np.array([0.0]), np.array([7.0]))
    assert getattr(p, pb._GRID_RMAX_ATTR) == 7.0
    f.close()


def test_polar_capabilities_are_narrowed_honestly():
    from lafigure.series import SERIES_KINDS
    assert SERIES_KINDS['polar'].capabilities == frozenset({'brush', 'copy'})


def test_polar_to_dict_round_trips_theta_r_not_cartesian_xy():
    f, p, ax = _ax()
    theta = np.array([0.0, math.pi / 3, math.pi])
    r = np.array([1.0, 2.0, 3.0])
    s = ax.polar(theta, r, name='abc')
    d = s.to_dict()
    assert d['kind'] == 'polar'
    np.testing.assert_allclose(d['x'], theta)
    np.testing.assert_allclose(d['y'], r)
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'polar'
    np.testing.assert_allclose(list(s2.x), list(s.x), atol=1e-9)
    np.testing.assert_allclose(list(s2.y), list(s.y), atol=1e-9)
    assert s2.item.name() == 'abc'
    f.close()


def test_polar_copy_paste_round_trip_through_the_clipboard():
    f, p, ax = _ax()
    s = ax.polar(np.array([0.0, math.pi / 2]), np.array([1.0, 3.0]), name='p1')
    f._select_curve(s.item)
    f.copy_curve()
    q = f.add_subplot(row=1, col=0)
    f.focused_plot = q
    f.paste_curve()
    (pasted,) = f._series_on(q)
    assert pasted.kind == 'polar'
    np.testing.assert_allclose(list(pasted.x), list(s.x), atol=1e-9)
    f.close()


# -- polarhistogram -----------------------------------------------------------------
def test_polarhistogram_bins_samples_into_the_right_wedges():
    f, p, ax = _ax()
    theta = np.array([0.0, 0.1, 0.05, 0.2, 0.15,       # 5 samples near angle 0
                      math.pi / 2, math.pi / 2 + 0.1, math.pi / 2 + 0.2])  # 3 near pi/2
    s = ax.polarhistogram(theta, bins=4, name='h')
    assert s.kind == 'polarhistogram'
    assert s in ax.series
    counts = s.item._counts
    assert counts[0] == 5
    assert counts[1] == 3
    assert counts[2] == 0 and counts[3] == 0
    f.close()


def test_polarhistogram_density_normalizes_to_one():
    f, p, ax = _ax()
    theta = np.zeros(10)
    s = ax.polarhistogram(theta, bins=4, density=True)
    assert math.isclose(float(s.item._counts.sum()), 1.0)
    f.close()


def test_polarhistogram_not_click_selectable():
    f, p, ax = _ax()
    s = ax.polarhistogram(np.array([0.0, 1.0, 2.0]), bins=6)
    assert not hasattr(s.item, 'curve')
    f.close()


def test_polarhistogram_paints_without_raising():
    f, p, ax = _ax()
    f.show()
    s = ax.polarhistogram(np.array([0.0, 0.5, 1.0, 1.5]), bins=8)
    _paint(s.item)
    f.close()


def test_polarhistogram_draws_a_grid_sized_to_the_tallest_bin():
    f, p, ax = _ax()
    theta = np.concatenate([np.zeros(9), np.full(1, math.pi)])
    s = ax.polarhistogram(theta, bins=4)
    assert getattr(p, pb._GRID_RMAX_ATTR) == s.item.rmax() == 9.0
    f.close()


def test_polarhistogram_to_dict_stores_raw_samples_and_round_trips():
    f, p, ax = _ax()
    theta = np.array([0.0, 0.2, math.pi, math.pi + 0.1, math.pi + 0.2])
    s = ax.polarhistogram(theta, bins=6, density=False, name='raw')
    d = s.to_dict()
    assert d['kind'] == 'polarhistogram'
    np.testing.assert_allclose(np.sort(d['x']), np.sort(theta))
    assert d['style']['bins'] == 6
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'polarhistogram'
    np.testing.assert_array_equal(s2.item._counts, s.item._counts)
    f.close()


def test_polarhistogram_capabilities_are_copy_only():
    from lafigure.series import SERIES_KINDS
    assert SERIES_KINDS['polarhistogram'].capabilities == frozenset({'copy'})


# -- piechart ------------------------------------------------------------------------
def test_piechart_fractions_sum_to_one_and_labels_align():
    f, p, ax = _ax()
    s = ax.piechart([10.0, 20.0, 70.0], labels=['a', 'b', 'c'])
    assert s.kind == 'piechart'
    assert s in ax.series
    np.testing.assert_allclose(float(s.item._fractions.sum()), 1.0)
    np.testing.assert_allclose(s.item._fractions, [0.1, 0.2, 0.7])
    assert s.item.slice_labels == ['a', 'b', 'c']
    f.close()


def test_piechart_default_labels_when_none_given():
    f, p, ax = _ax()
    s = ax.piechart([1.0, 1.0, 1.0])
    assert s.item.slice_labels == ['Slice 1', 'Slice 2', 'Slice 3']
    f.close()


def test_piechart_axes_hidden_and_aspect_locked_no_grid_drawn():
    f, p, ax = _ax()
    ax.piechart([1.0, 2.0, 3.0])
    assert not p.getAxis('left').isVisible()
    assert p.getViewBox().state['aspectLocked']
    # piechart deliberately does not call draw_polar_grid -- see its own
    # module docstring -- so no grid attribute should have been set.
    assert getattr(p, pb._GRID_ATTR, None) in (None, [])
    f.close()


def test_piechart_not_click_selectable():
    f, p, ax = _ax()
    s = ax.piechart([1.0, 2.0])
    assert not hasattr(s.item, 'curve')
    f.close()


def test_piechart_paints_without_raising():
    f, p, ax = _ax()
    f.show()
    s = ax.piechart([3.0, 1.0, 4.0, 1.0], labels=['w', 'x', 'y', 'z'])
    _paint(s.item)
    f.close()


def test_piechart_negative_values_are_clipped_not_dropped():
    f, p, ax = _ax()
    s = ax.piechart([-5.0, 10.0], labels=['neg', 'pos'])
    assert s.item._values[0] == 0.0
    assert s.item.slice_labels == ['neg', 'pos']
    np.testing.assert_allclose(s.item._fractions, [0.0, 1.0])
    f.close()


def test_piechart_custom_colors_are_used():
    f, p, ax = _ax()
    s = ax.piechart([1.0, 1.0], colors=[(255, 0, 0), (0, 255, 0)])
    assert s.item._colors[0].getRgb()[:3] == (255, 0, 0)
    assert s.item._colors[1].getRgb()[:3] == (0, 255, 0)
    f.close()


def test_piechart_to_dict_round_trips_values_labels_and_colors():
    f, p, ax = _ax()
    s = ax.piechart([2.0, 3.0, 5.0], labels=['p', 'q', 'r'],
                    colors=[(10, 20, 30), (40, 50, 60), (70, 80, 90)])
    d = s.to_dict()
    assert d['kind'] == 'piechart'
    np.testing.assert_allclose(d['x'], [2.0, 3.0, 5.0])
    assert d['style']['labels'] == ['p', 'q', 'r']
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'piechart'
    assert s2.item.slice_labels == ['p', 'q', 'r']
    np.testing.assert_allclose(s2.item._values, [2.0, 3.0, 5.0])
    assert s2.item._colors[0].getRgb()[:3] == (10, 20, 30)
    f.close()


def test_piechart_copy_paste_round_trip_through_the_clipboard():
    f, p, ax = _ax()
    s = ax.piechart([1.0, 2.0, 3.0], labels=['a', 'b', 'c'])
    f._select_curve(s.item)
    f.copy_curve()
    q = f.add_subplot(row=1, col=0)
    f.focused_plot = q
    f.paste_curve()
    (pasted,) = f._series_on(q)
    assert pasted.kind == 'piechart'
    assert pasted.item.slice_labels == ['a', 'b', 'c']
    f.close()


def test_piechart_capabilities_are_copy_only():
    from lafigure.series import SERIES_KINDS
    assert SERIES_KINDS['piechart'].capabilities == frozenset({'copy'})


def test_piechart_set_data_recomputes_fractions():
    f, p, ax = _ax()
    s = ax.piechart([1.0, 1.0])
    s.set_data([1.0, 1.0], [0.0, 0.0])  # set_data(x, y): y unused by this kind, still required
    np.testing.assert_allclose(s.item._fractions, [0.5, 0.5])
    f.close()
