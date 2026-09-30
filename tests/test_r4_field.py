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

"""R4-FIELD: quiver, feather, contour."""
import math

import numpy as np
import pyqtgraph as pg

from lafigure.axes import Axes
from lafigure.kinds import contour as contour_mod
from lafigure.kinds.quiver import QuiverItem, _autoscale
from lafigure.kinds.feather import FeatherItem
from tests.helpers import app, m


def _figure_with_plot():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    return f, Axes(f, p)


# -- quiver ---------------------------------------------------------------
def test_quiver_appears_in_ax_series_with_the_right_kind():
    f, ax = _figure_with_plot()
    x, y = np.array([0.0, 1.0]), np.array([0.0, 0.0])
    u, v = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    s = ax.quiver(x, y, u=u, v=v)
    assert s.kind == 'quiver'
    assert s.item in [x.item for x in ax.series]
    assert isinstance(s.item, QuiverItem)
    assert not hasattr(s.item, 'curve'), "control: not click-selectable"
    f.close()


def test_quiver_autoscale_matches_hand_computed_value():
    x, y = np.array([0.0, 1.0, 2.0]), np.array([0.0, 0.0, 0.0])
    u, v = np.array([1.0, 0.0, 1.0]), np.array([0.0, 1.0, 1.0])
    # data_range = hypot(2, 0) = 2; max |vector| = hypot(1,1) = sqrt(2);
    # fraction=0.15 -> scale = 0.15 * 2 / sqrt(2)
    expected = 0.15 * 2.0 / math.sqrt(2.0)
    got = _autoscale(x, y, u, v, 0.15)
    assert math.isclose(got, expected, rel_tol=1e-12)


def test_quiver_explicit_scale_overrides_autoscale():
    f, ax = _figure_with_plot()
    s = ax.quiver(np.array([0.0]), np.array([0.0]), u=np.array([1.0]), v=np.array([0.0]), scale=5.0)
    assert s.item.scale == 5.0
    # head is exactly tail + (u, v) * scale
    r = s.item.boundingRect()
    assert math.isclose(r.right(), 5.0)
    f.close()


def test_quiver_head_position_is_tail_plus_scaled_vector():
    f, ax = _figure_with_plot()
    x, y = np.array([2.0]), np.array([3.0])
    u, v = np.array([1.0]), np.array([1.0])
    s = ax.quiver(x, y, u=u, v=v, scale=2.0)
    hx, hy = s.item._head_xy()
    assert (float(hx[0]), float(hy[0])) == (4.0, 5.0)
    f.close()


def test_quiver_arrowhead_paints_without_raising_on_a_non_square_data_scale():
    """A regression guard for the scene-space arrowhead requirement: a
    subplot whose X and Y data-per-pixel ratio is deliberately not 1:1
    (the lafigure-axes-geometry skill's own check) must still paint a
    real, finite-sized filled triangle -- not raise, and not degenerate
    to zero-area. We can't easily assert an exact scene-pixel angle
    without a shown window's real geometry, so this exercises the actual
    paint() path (via a real QImage/QPainter, mirroring test_r4_base.py's
    own pattern) and confirms it doesn't crash and draws something."""
    f, ax = _figure_with_plot()
    f.plots[0].getViewBox().setRange(xRange=(0, 1000), yRange=(0, 1), padding=0)
    f.show()
    app.processEvents()
    s = ax.quiver(np.array([0.0, 500.0]), np.array([0.5, 0.5]),
                  u=np.array([1.0, -1.0]), v=np.array([0.3, 0.3]))
    img = pg.QtGui.QImage(200, 200, pg.QtGui.QImage.Format_ARGB32)
    painter = pg.QtGui.QPainter(img)
    try:
        s.item.paint(painter)
    finally:
        painter.end()
    f.close()


def test_quiver_to_dict_round_trips_through_create():
    f, ax = _figure_with_plot()
    x, y = np.array([0.0, 1.0]), np.array([2.0, 3.0])
    u, v = np.array([1.0, 2.0]), np.array([3.0, -1.0])
    s = ax.quiver(x, y, u=u, v=v, name='wind')
    d = s.to_dict()
    assert d['kind'] == 'quiver'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'quiver'
    np.testing.assert_array_equal(s2.x, x)
    np.testing.assert_array_equal(s2.y, y)
    np.testing.assert_array_equal(s2.item._u, u)
    np.testing.assert_array_equal(s2.item._v, v)
    assert s2.item.scale == s.item.scale
    assert s2.item.name() == 'wind'
    f.close()


def test_quiver_copy_paste_subplot_round_trip():
    f, ax = _figure_with_plot()
    ax.quiver(np.array([0.0, 1.0]), np.array([0.0, 0.0]), u=np.array([1.0, 1.0]), v=np.array([1.0, 0.0]))
    f._on_plot_clicked(ax.plot_item)
    f.copy_subplot()
    f.paste_subplot()
    kinds = [s.kind for s in f._series_on(f.plots[-1])]
    assert 'quiver' in kinds
    f.close()


def test_quiver_requires_u_and_v():
    f, ax = _figure_with_plot()
    try:
        ax.quiver(np.array([0.0]), np.array([0.0]))
        raised = False
    except TypeError:
        raised = True
    assert raised
    f.close()


# -- feather ----------------------------------------------------------------
def test_feather_tails_are_pinned_to_the_x_axis_even_with_a_nonzero_y():
    f, ax = _figure_with_plot()
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([10.0, -5.0, 3.0])   # deliberately nonzero/varied -- must be ignored
    u, v = np.array([1.0, 1.0, 1.0]), np.array([0.0, 0.0, 0.0])
    s = ax.feather(x, u=u, v=v)
    assert isinstance(s.item, FeatherItem)
    tx, ty = s.item._tail_xy()
    np.testing.assert_array_equal(tx, x)
    np.testing.assert_array_equal(ty, np.zeros_like(x))
    f.close()


def test_feather_without_y_argument_works():
    f, ax = _figure_with_plot()
    s = ax.feather(np.array([0.0, 1.0]), u=np.array([1.0, 0.0]), v=np.array([0.0, 1.0]))
    assert s.kind == 'feather'
    tx, ty = s.item._tail_xy()
    assert list(ty) == [0.0, 0.0]
    f.close()


def test_feather_bounds_reflect_axis_pinned_tails():
    f, ax = _figure_with_plot()
    s = ax.feather(np.array([0.0, 1.0]), u=np.array([0.0, 0.0]), v=np.array([2.0, -2.0]), scale=1.0)
    r = s.item.boundingRect()
    # tails at y=0; heads at y=+2 and y=-2 -> bounding box spans y in [-2, 2]
    assert math.isclose(r.top(), -2.0) and math.isclose(r.bottom(), 2.0)
    f.close()


def test_feather_to_dict_round_trips_through_create():
    f, ax = _figure_with_plot()
    x = np.array([0.0, 1.0, 2.0])
    u, v = np.array([1.0, -1.0, 0.5]), np.array([0.5, 0.5, -1.0])
    s = ax.feather(x, u=u, v=v, name='wind-row')
    d = s.to_dict()
    assert d['kind'] == 'feather'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert isinstance(s2.item, FeatherItem)
    tx, ty = s2.item._tail_xy()
    np.testing.assert_array_equal(tx, x)
    np.testing.assert_array_equal(ty, np.zeros_like(x))
    np.testing.assert_array_equal(s2.item._u, u)
    assert s2.item.name() == 'wind-row'
    f.close()


# -- contour: marching_squares (hand-checked cases) --------------------------
def test_marching_squares_symmetric_peak_produces_a_diamond():
    """A 3x3 grid with a single peak of 4 at the center, 0 everywhere else.
    Hand-derived (see contour.py's module docstring for the method): the
    level=2 contour is a diamond around the peak with vertices at
    (1, 0.5), (1.5, 1), (1, 1.5), (0.5, 1)."""
    matrix = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 4.0, 0.0],
        [0.0, 0.0, 0.0],
    ])
    segs = contour_mod.marching_squares(matrix, 2.0)
    assert len(segs) == 4
    expected_points = {(1.0, 0.5), (1.5, 1.0), (1.0, 1.5), (0.5, 1.0)}
    seen_points = set()
    for (p0, p1) in segs:
        seen_points.add(p0)
        seen_points.add(p1)
    assert seen_points == expected_points
    # Each segment connects two ADJACENT diamond vertices (an edge of the
    # diamond), never the two opposite corners (a diagonal).
    diag_pairs = {frozenset({(1.0, 0.5), (1.0, 1.5)}), frozenset({(1.5, 1.0), (0.5, 1.0)})}
    for (p0, p1) in segs:
        assert frozenset({p0, p1}) not in diag_pairs


def test_marching_squares_no_crossing_returns_no_segments():
    matrix = np.array([[0.0, 0.0], [0.0, 0.0]])
    assert contour_mod.marching_squares(matrix, 5.0) == []


def test_marching_squares_saddle_case_resolved_by_mean_value():
    """A 2x2 checkerboard (10, 0 / 0, 10): all four corners alternate
    above/below level=5, the classic marching-squares ambiguous ("saddle")
    cell. Mean of the 4 corners is exactly 5 (>= level), so the documented
    convention pairs (top, left) and (right, bottom)."""
    matrix = np.array([[10.0, 0.0], [0.0, 10.0]])
    segs = contour_mod.marching_squares(matrix, 5.0)
    assert len(segs) == 2
    top, right, bottom, left = (0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)
    got = {frozenset(s) for s in segs}
    assert frozenset({top, left}) in got
    assert frozenset({right, bottom}) in got
    assert frozenset({top, right}) not in got


def test_marching_squares_saddle_case_other_branch():
    """The mirror checkerboard (0, 10 / 10, 0): mean is still 5 (>= level
    under our >= convention -- see _cell_segments), so REVERSING which
    corners are high still yields the SAME geometric pairing rule applied
    to the new corner layout: top/bottom are now the low corners, so the
    edges crossing are the same 4 points, paired as (top, right) &
    (left, bottom) this time (since >= means the tie still goes to the
    first branch, but the underlying a/b/c/d values differ)."""
    matrix = np.array([[0.0, 10.0], [10.0, 0.0]])
    segs = contour_mod.marching_squares(matrix, 5.0)
    assert len(segs) == 2
    for (p0, p1) in segs:
        for coord in (p0[0], p0[1], p1[0], p1[1]):
            assert math.isclose(coord, 0.5) or coord in (0.0, 1.0)


def test_resolve_levels_int_n_is_strictly_inside_the_min_max():
    matrix = np.array([[0.0, 10.0], [5.0, 3.0]])
    levels = contour_mod._resolve_levels(matrix, 3)
    assert len(levels) == 3
    assert levels[0] > 0.0 and levels[-1] < 10.0
    np.testing.assert_allclose(levels, np.linspace(0.0, 10.0, 5)[1:-1])


def test_resolve_levels_explicit_sequence_is_used_as_is():
    matrix = np.array([[0.0, 10.0], [5.0, 3.0]])
    levels = contour_mod._resolve_levels(matrix, [1.0, 2.5, 9.0])
    np.testing.assert_array_equal(levels, [1.0, 2.5, 9.0])


# -- contour: SeriesKind integration -----------------------------------------
def test_contour_appears_in_ax_series_with_the_right_kind():
    f, ax = _figure_with_plot()
    matrix = np.random.RandomState(0).rand(10, 10)
    s = ax.contour(matrix, levels=3)
    assert s.kind == 'contour'
    assert s.item in [x.item for x in ax.series]
    assert not hasattr(s.item, 'curve'), "control: not click-selectable"
    f.close()


def test_contour_bounds_match_matrix_grid_extent():
    f, ax = _figure_with_plot()
    matrix = np.zeros((7, 4))
    s = ax.contour(matrix, levels=2)
    r = s.item.boundingRect()
    assert (r.left(), r.right()) == (0.0, 3.0)
    assert (r.top(), r.bottom()) == (0.0, 6.0)
    f.close()


def test_contour_one_level_per_color_from_value_colors():
    f, ax = _figure_with_plot()
    matrix = np.array([[0.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 0.0]])
    s = ax.contour(matrix, levels=[1.0, 2.0, 3.0], cmap='viridis')
    assert len(s.item._level_colors) == 3
    from lafigure.kinds._base import value_colors
    brushes, _ = value_colors(np.array([1.0, 2.0, 3.0]), cmap='viridis')
    assert s.item._level_colors[0].getRgb() == brushes[0].color().getRgb()
    assert s.item._level_colors[-1].getRgb() == brushes[-1].color().getRgb()
    f.close()


def test_contour_paints_without_raising():
    f, ax = _figure_with_plot()
    f.show()
    app.processEvents()
    matrix = np.random.RandomState(1).rand(15, 15)
    s = ax.contour(matrix, levels=4)
    img = pg.QtGui.QImage(64, 64, pg.QtGui.QImage.Format_ARGB32)
    painter = pg.QtGui.QPainter(img)
    try:
        s.item.paint(painter)
    finally:
        painter.end()
    f.close()


def test_contour_to_dict_round_trips_through_create():
    f, ax = _figure_with_plot()
    matrix = np.random.RandomState(2).rand(12, 12)
    s = ax.contour(matrix, levels=5, cmap='plasma', line_width=2.0, name='iso')
    d = s.to_dict()
    assert d['kind'] == 'contour'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'contour'
    np.testing.assert_array_equal(s2.item._matrix, matrix)
    np.testing.assert_array_equal(s2.item._levels, s.item._levels)
    assert s2.item.line_width == 2.0
    assert s2.item._cmap == 'plasma'
    assert s2.item.name() == 'iso'
    f.close()


def test_contour_copy_paste_subplot_round_trip():
    f, ax = _figure_with_plot()
    ax.contour(np.random.RandomState(3).rand(8, 8), levels=3)
    f._on_plot_clicked(ax.plot_item)
    f.copy_subplot()
    f.paste_subplot()
    kinds = [s.kind for s in f._series_on(f.plots[-1])]
    assert 'contour' in kinds
    f.close()


def test_contour_requires_a_matrix():
    f, ax = _figure_with_plot()
    try:
        ax.contour(None)
        raised = False
    except TypeError:
        raised = True
    assert raised
    f.close()


def test_contour_rejects_1d_input():
    f, ax = _figure_with_plot()
    try:
        ax.contour(np.array([1.0, 2.0, 3.0]))
        raised = False
    except ValueError:
        raised = True
    assert raised
    f.close()
