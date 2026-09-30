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

"""Figure-wide brushing (brushing.py)."""
import numpy as np
from pyqtgraph.Qt import QtCore

from lafigure.datasource import DataSource
from tests.helpers import (
    app, m, _mouse, _brush_drag, _key,
)


# -- shared fixtures for the tests below -------------------------------------
def _figure(n_plots=1):
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    axes = [f.subplot(i, 0) for i in range(n_plots)]
    return f, axes


def _linear_source(n=100):
    """An evenly-spaced dataset: brushing half of the current view range
    always catches a predictable, non-empty subset, whatever exact range
    a subplot's autoRange settles on."""
    t = np.linspace(0, 99, n)
    return DataSource({'t': t, 'z': np.zeros(n)})


def test_new_subplot_adopts_brushing():
    f = m.LaFigure()
    f.brush_action.trigger()
    f.add_new_subplot()
    new = f.plots[-1]
    assert f._brushers[new].brushing_enabled, "a subplot added while Brush is on must brush"
    f.close()


def test_brushing_works_in_a_figure_without_the_demo_scatters():
    """A "New Figure" has no linked-scatter SelectionModel: a real brush
    drag (which unbrushes the rest of the figure first) and turning Brush
    off both used to raise AttributeError on self.selection_model."""
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    p = f.add_subplot(row=0, col=0)
    x = np.linspace(0, 100, 1001)
    curve = p.plot(x, x)
    p.getViewBox().setRange(xRange=(0, 100), yRange=(0, 100), padding=0)
    app.processEvents()
    f.brush_action.trigger()
    vb = p.getViewBox()
    a = vb.mapViewToScene(QtCore.QPointF(20, 80))
    b = vb.mapViewToScene(QtCore.QPointF(40, 10))
    L = QtCore.Qt.LeftButton
    _mouse(f, QtCore.QEvent.MouseButtonPress, a, L)
    for t in (0.1, 0.5, 1.0):
        _mouse(f, QtCore.QEvent.MouseMove, a + (b - a) * t, L, button=QtCore.Qt.NoButton)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, b, QtCore.Qt.NoButton)
    items = f._figure_brush_items()
    assert len(items) == 1 and items[0][0] is curve, "control: the real drag brushed the curve"
    brushed_x = curve.xData[items[0][1]]
    assert brushed_x.min() >= 20 - 0.2 and brushed_x.max() <= 40 + 0.2, (brushed_x.min(), brushed_x.max())
    f.select_action.trigger()  # Brush off (Select replaces it)
    f.close()


# -- post-hide brushing: PLAN.md's "reproduce first" bug -----------------
# Investigated extensively (real, correctly-paced drags -- CLAUDE.md bug
# #17 -- across a single subplot, two subplots linked by a shared
# DataSource, and an unrelated third subplot; with the exact
# hide_brushed_points() code path; with and without pyqtgraph's own
# ViewBox autoRange left on). Could NOT reproduce a "no other point can be
# brushed afterward" lockup in this environment: every real drag, using
# the CURRENT view range at the moment of the drag (exactly what a real
# mouse gesture is driven by), correctly selected the new region.
#
# One artifact WAS found and is worth recording: a test (or any other
# caller) that memoizes a subplot's `viewRange()` *before* a Hide and
# reuses those stale bounds to build a later rectangle can compute a
# scene position far outside the widget once pyqtgraph's own autoRange
# has zoomed into the much smaller remaining data -- that "selects
# nothing" too, but it is a stale-coordinate bug in the *caller*, not in
# brushing.py/selection.py: a real user's mouse is always driven by the
# CURRENT screen, never a memoized one. Both tests below re-read
# `viewRange()` fresh right before building the second rectangle, exactly
# like a real drag would, and are kept as regression coverage for the
# reported sequence either way.
def test_brush_after_hide_selects_a_different_still_visible_region():
    f, (ax,) = _figure()
    src = _linear_source()
    s = ax.scatter(src, x='t', y='z', size=6)
    vb = ax.plot_item.getViewBox()
    vb.setRange(xRange=(0, 100), yRange=(-1, 1), padding=0)
    app.processEvents()
    f.brush_action.trigger()

    xr, yr = vb.viewRange()
    mid = (xr[0] + xr[1]) / 2
    _brush_drag(f, ax.plot_item, (xr[0], yr[0]), (mid, yr[1]))
    items = f._figure_brush_items()
    assert len(items) == 1 and items[0][1].any(), "control: region A brushed something"

    f.hide_brushed_points()
    assert f.has_hidden_points()

    # Re-read the view range NOW (autoRange may have moved it) and brush
    # the other half of what's CURRENTLY visible -- a different region,
    # still showing real (unhidden) points.
    xr2, yr2 = vb.viewRange()
    mid2 = (xr2[0] + xr2[1]) / 2
    _brush_drag(f, ax.plot_item, (mid2, yr2[0]), (xr2[1], yr2[1]))
    items = f._figure_brush_items()
    assert len(items) == 1, "must select something in the new region, not stay stuck empty"
    mask = items[0][1]
    assert mask.any(), "brushing after Hide must not be permanently stuck with nothing selected"
    assert s.x[mask].min() >= mid2 - 1e-6, "the newly selected points are the ones in region B"
    f.close()


def test_brush_after_hide_selects_a_different_region_on_a_linked_subplot():
    """Same sequence as above, but the second brush lands on a DIFFERENT
    subplot sharing the first one's DataSource (like the demo's two
    linked scatters) -- the exact "brush elsewhere" wording in the bug
    report."""
    f, (ax1, ax2) = _figure(2)
    src = _linear_source()
    s1 = ax1.scatter(src, x='t', y='z', size=6)
    s2 = ax2.scatter(src, x='t', y='z', size=6)
    vb1, vb2 = ax1.plot_item.getViewBox(), ax2.plot_item.getViewBox()
    vb1.setRange(xRange=(0, 100), yRange=(-1, 1), padding=0)
    vb2.setRange(xRange=(0, 100), yRange=(-1, 1), padding=0)
    app.processEvents()
    f.brush_action.trigger()

    xr, yr = vb1.viewRange()
    mid = (xr[0] + xr[1]) / 2
    _brush_drag(f, ax1.plot_item, (xr[0], yr[0]), (mid, yr[1]))
    assert f._figure_brush_items(), "control: first brush selected something"

    f.hide_brushed_points()
    assert f.has_hidden_points()

    xr2, yr2 = vb2.viewRange()
    mid2 = (xr2[0] + xr2[1]) / 2
    _brush_drag(f, ax2.plot_item, (mid2, yr2[0]), (xr2[1], yr2[1]))
    items = f._figure_brush_items()
    assert items, "must select something on the OTHER subplot, not stay stuck"
    for item, mask in items:
        assert mask.any()
    f.close()


# -- Show All Points' enabled state (has_hidden_points) ----------------------
def test_has_hidden_points_toggles_with_hide_and_show_all():
    f, (ax,) = _figure()
    src = _linear_source()
    s = ax.scatter(src, x='t', y='z', size=6)
    vb = ax.plot_item.getViewBox()
    vb.setRange(xRange=(0, 100), yRange=(-1, 1), padding=0)
    app.processEvents()
    f.brush_action.trigger()

    assert not f.has_hidden_points(), "control: nothing hidden yet"
    xr, yr = vb.viewRange()
    _brush_drag(f, ax.plot_item, (xr[0], yr[0]), (xr[0] + (xr[1] - xr[0]) * 0.2, yr[1]))
    assert f._figure_brush_items(), "control: something got brushed"

    f.hide_brushed_points()
    assert f.has_hidden_points(), "Hide must make has_hidden_points() true"
    f.undo()
    assert not f.has_hidden_points(), "undoing the hide clears it again"
    f.redo()
    assert f.has_hidden_points()

    f.show_all_hidden_points()
    assert not f.has_hidden_points(), "Show All must make has_hidden_points() false again"
    f.undo()
    assert f.has_hidden_points(), "undoing Show All brings the hidden rows back"
    f.close()


# -- delete_brushed_points must notify the source, without shrinking it -----
def test_delete_brushed_points_notifies_source_on_change():
    f, (ax,) = _figure()
    src = _linear_source()
    s = ax.scatter(src, x='t', y='z', size=6)
    vb = ax.plot_item.getViewBox()
    vb.setRange(xRange=(0, 100), yRange=(-1, 1), padding=0)
    app.processEvents()
    f.brush_action.trigger()

    calls = []
    src.on_change(lambda: calls.append(1))

    xr, yr = vb.viewRange()
    _brush_drag(f, ax.plot_item, (xr[0], yr[0]), (xr[0] + (xr[1] - xr[0]) * 0.2, yr[1]))
    assert f._figure_brush_items(), "control: something got brushed"
    n_before = len(s.x)

    _key(f, QtCore.Qt.Key_Delete)  # Del in Brush mode -> delete_brushed_points
    assert len(s.x) < n_before, "control: the points were actually removed from the series"
    assert len(src) == 100, "the DataSource itself must never shrink"
    assert not src.hidden_mask.any(), "delete is not hide -- no mask is touched either"
    assert len(calls) == 1, "delete must fire on_change so depends_on=[source] re-runs"

    f.undo()
    assert len(s.x) == n_before
    assert len(calls) == 2, "undoing the delete must notify too"

    f.redo()
    assert len(s.x) < n_before
    assert len(calls) == 3, "redoing the delete must notify too"
    f.close()


def test_delete_brushed_points_on_plain_array_series_does_not_notify_any_source():
    """A plain-array series has no explicit DataSource for anyone to
    depends_on=[...]; deleting from it must not crash trying to notify one."""
    f, (ax,) = _figure()
    s = ax.plot(np.arange(10.0), np.arange(10.0))
    f.brush_action.trigger()
    f._on_rect_brush_finished(ax.plot_item, {s.item: np.array([0, 1])}, False)
    assert f._figure_brush_items()
    f.delete_brushed_points()  # must not raise
    assert list(s.x) == list(range(2, 10))
    f.close()
