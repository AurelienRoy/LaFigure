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

"""Selection (selection_ui.py): focus follows clicks, curve highlight,
deselection, exclusivity across kinds unless Shift is held, Esc, the
rubber band, Tab cycling and arrow-key nudge. The band and key tests use
REAL Qt mouse/key events (QMouseEvent to the viewport, QTest.keyClick),
not direct method calls: the band relies on pyqtgraph emitting exactly
one click after a drag whose moves it never saw, and the keys on Qt's
shortcut routing -- only the real event path can show either works.
"""
import logging
import math
import time

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

from tests.helpers import (
    app, m, SHIFT, FakeClickEvent, has_border, shown_figure, first_curve, _vb_center,
    _click_subplot, _click_curve, _click_annotation, _selection_figure, _selected,
    _two_annotation_figure, _empty_scene_point, _press_escape, _scene_pos, _mouse,
    _band_drag, _key, _band_start_up_left_of,
)


def test_focus_follows_the_clicked_subplot():
    """Focus tracking must follow the click target, not connection order."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

    assert win.focused_plot is p1

    # Focus/active-subplot tracking must follow the click target, not connection order.
    win._on_plot_clicked(p2)
    assert win.focused_plot is p2
    win._on_plot_clicked(p4)
    assert win.focused_plot is p4
    assert has_border(p4)
    assert not has_border(p2)
    win.close()


def test_selecting_a_curve_highlights_it_and_restores_the_previous_one():
    """Clicking a curve highlights it and restores the previous one."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots
    c1, c2 = first_curve(p1), first_curve(p2)

    c1 = [c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)][0]
    win._select_curve(c1)
    assert win.active_curve is c1
    w1 = c1.opts['pen'].width()

    c2 = [c for c in p2.listDataItems() if isinstance(c, pg.PlotDataItem)][0]
    win._select_curve(c2)
    assert c1.opts['pen'].width() == w1 - 3
    assert win.active_curve is c2
    win.close()


def test_double_click_deselects_subplot_and_curve():
    """Double-clicking a subplot deselects everything: the focused subplot AND
    the selected curve (this is _on_scene_clicked's ev.double() branch)."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots
    c1 = first_curve(p1)

    win._on_plot_clicked(p1)
    win._select_curve(c1)
    assert win.focused_plot is p1 and win.active_curve is c1
    win._on_scene_clicked(FakeClickEvent(p1.sceneBoundingRect().center(), double=True))
    assert win.focused_plot is None
    assert win.active_curve is None
    assert not has_border(p1)
    assert not win.move_handle.isVisible()
    win.close()


def test_click_outside_every_subplot_deselects():
    """A single click landing outside every subplot also deselects everything."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots
    far_away = QtCore.QPointF(-999999, -999999)

    win._on_plot_clicked(p2)
    assert win.focused_plot is p2
    far_away = QtCore.QPointF(-999999, -999999)
    win._on_scene_clicked(FakeClickEvent(far_away, double=False, accepted=False))
    assert win.focused_plot is None
    win.close()


def test_deselecting_a_curve_restores_its_pen():
    """Deselecting a curve restores its original pen."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots
    c2 = first_curve(p2)

    win._select_curve(c2)
    assert win.active_curve is c2
    w2_selected = c2.opts['pen'].width()
    win._deselect_curve()
    assert win.active_curve is None
    assert c2.opts['pen'].width() == w2_selected - 3
    # NOTE: _deselect_curve() is called directly here. The real trigger --
    # _on_scene_clicked() reading ev.isAccepted() to tell "clicked a curve" from
    # "clicked empty space" -- goes through pyqtgraph's live mouse-event dispatch,
    # which this harness can't simulate reliably (see CLAUDE.md, "Headless
    # testing by calling methods directly"). Verify that
    # path interactively: click a curve to select it, then click empty canvas
    # and confirm the highlight goes away.
    win.close()


def test_curve_click_deselects_the_selected_subplot():
    f, curve, ann = _selection_figure()
    p0, p1 = f.plots[0], f.plots[1]
    _click_subplot(f, p1)
    assert _selected(f) == ([p1], [], None)
    _click_curve(f, p0, curve)
    assert _selected(f) == ([], [curve], None), _selected(f)
    assert not has_border(p1) and not has_border(p0), "no subplot is selected, so no border"
    assert not f.move_handle.isVisible(), "handles belong to a selected subplot"
    assert f.focused_plot is p0, "the curve's subplot stays the toolbar target"
    f.close()


def test_subplot_click_deselects_curve_and_annotation():
    f, curve, ann = _selection_figure()
    _click_curve(f, f.plots[0], curve)
    _click_subplot(f, f.plots[1])
    assert _selected(f) == ([f.plots[1]], [], None)
    _click_annotation(f, ann)
    _click_subplot(f, f.plots[0])
    assert _selected(f) == ([f.plots[0]], [], None), "a subplot click must deselect the annotation"
    f.close()


def test_annotation_click_deselects_curve_and_subplot():
    f, curve, ann = _selection_figure()
    _click_subplot(f, f.plots[1])
    _click_curve(f, f.plots[0], curve, modifiers=SHIFT)
    _click_annotation(f, ann)
    assert _selected(f) == ([], [], ann), _selected(f)
    assert not any(has_border(p) for p in f.plots)
    f.close()


def test_curve_click_deselects_the_annotation():
    f, curve, ann = _selection_figure()
    _click_annotation(f, ann)
    _click_curve(f, f.plots[0], curve)
    assert _selected(f) == ([], [curve], None), _selected(f)
    f.close()


def test_shift_click_keeps_every_kind_selected():
    f, curve, ann = _selection_figure()
    p0, p1 = f.plots[0], f.plots[1]
    _click_subplot(f, p1)
    _click_curve(f, p0, curve, modifiers=SHIFT)
    _click_annotation(f, ann, modifiers=SHIFT)
    _click_subplot(f, p0, modifiers=SHIFT)
    assert _selected(f) == ([p1, p0], [curve], ann), _selected(f)
    f.close()


def test_right_click_inside_the_selection_keeps_it():
    f, curve, ann = _selection_figure()
    p0, p1 = f.plots[0], f.plots[1]
    _click_subplot(f, p0)
    _click_subplot(f, p1, modifiers=SHIFT)
    f._on_plot_context(p0)
    assert _selected(f) == ([p0, p1], [], None), "right-click must not collapse a multi-select"
    f._on_plot_context(f.plots[2])
    assert _selected(f) == ([f.plots[2]], [], None), "right-click outside the selection selects"
    f.close()


def test_programmatic_selection_is_exclusive_too():
    f, curve, ann = _selection_figure()
    _click_curve(f, f.plots[0], curve)
    f.add_new_subplot()
    assert _selected(f) == ([f.plots[-1]], [], None), "a new subplot's selection is exclusive"
    _click_curve(f, f.plots[0], curve)
    f.copy_subplot()  # nothing but a curve selected -> copies its subplot
    f.paste_subplot()
    assert _selected(f)[1:] == ([], None), "pasted subplots' selection is exclusive"
    f.close()


def test_shift_click_on_empty_space_changes_nothing():
    f, curve, ann = _selection_figure()
    _click_subplot(f, f.plots[1])
    _click_curve(f, f.plots[0], curve, modifiers=SHIFT)
    _click_annotation(f, ann, modifiers=SHIFT)
    before = _selected(f)
    f._on_scene_clicked(FakeClickEvent(_empty_scene_point(f), modifiers=SHIFT))
    assert _selected(f) == before, "Shift+click on empty space must do nothing"
    f._on_scene_clicked(FakeClickEvent(_empty_scene_point(f)))
    assert _selected(f) == ([], [], None), "a plain click on empty space still deselects all"
    f.close()


def test_right_click_on_a_figure_annotation_does_not_open_the_empty_space_menu():
    """A figure/border-anchored annotation sits outside every subplot's
    ViewBox, so a right-click on it used to fall into the 'truly empty
    space' branch and open Paste Subplot instead of the annotation's own
    menu (a separate, native contextMenuEvent -- see annotations.py)."""
    f, curve, ann = _selection_figure()
    pt = _empty_scene_point(f)
    free_ann = f._create_annotation('rect', 'figure', None, pt, QtCore.QPointF(20, 20))
    shown = []
    f._show_empty_space_menu = lambda: shown.append(True)
    f._on_scene_clicked(FakeClickEvent(pt + QtCore.QPointF(5, 5), button=QtCore.Qt.RightButton))
    assert shown == [], "the annotation's own contextMenuEvent handles this, not the empty-space menu"
    f.close()


def test_escape_deselects_everything():
    f, curve, ann = _selection_figure()
    _click_subplot(f, f.plots[1])
    _click_curve(f, f.plots[0], curve, modifiers=SHIFT)
    _click_annotation(f, ann, modifiers=SHIFT)
    _press_escape(f)
    assert _selected(f) == ([], [], None) and f.selected_annotations == []
    assert not any(has_border(p) for p in f.plots) and not f.move_handle.isVisible()
    f.close()


def test_escape_cancels_relink_and_deselects_in_one_press():
    # Re-link, not placement: starting a placement already deselects all.
    f, curve, ann = _selection_figure()
    _click_annotation(f, ann)
    f._start_relink(ann)
    assert f.selected_annotations == [ann], "control: re-linking keeps the selection"
    _press_escape(f)
    assert f._relink_source is None
    assert _selected(f) == ([], [], None)
    f.close()


def test_shift_click_toggles_every_kind():
    f, curve, rect, ellipse = _two_annotation_figure()
    p0, p1 = f.plots[0], f.plots[1]
    unselected_width = curve.opts['pen'].width()
    _click_subplot(f, p1)
    _click_subplot(f, p0, modifiers=SHIFT)
    _click_curve(f, p0, curve, modifiers=SHIFT)
    _click_annotation(f, rect, modifiers=SHIFT)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    assert f.selected_annotations == [rect, ellipse]
    assert rect._selected and ellipse._selected
    _click_subplot(f, p1, modifiers=SHIFT)
    _click_curve(f, p0, curve, modifiers=SHIFT)
    _click_annotation(f, rect, modifiers=SHIFT)
    assert f.selected_plots == [p0] and f.selected_curves == []
    assert f.selected_annotations == [ellipse] and not rect._selected
    assert f.active_annotation is ellipse
    assert curve.opts['pen'].width() == unselected_width, "Shift-toggling a curve off must restore its pen"
    f.close()


def test_band_from_the_margin_selects_enclosed_subplots_only():
    f, curve, ann = _selection_figure()
    p0 = f.plots[0]
    corner = QtCore.QPointF(2, 2)
    assert f._can_start_band_at(corner), "control: the figure margin starts a band"
    beyond = p0.getViewBox().sceneBoundingRect().bottomRight() + QtCore.QPointF(3, 3)
    _band_drag(f, corner, beyond)
    assert _selected(f) == ([p0], [], None), _selected(f)
    assert f._band is None and not f._suppress_click
    assert not any(isinstance(i, QtWidgets.QGraphicsRectItem) and i.zValue() == 1e6
                   for i in f.layout_widget.scene().items()), "the band rectangle must be removed"
    # p0 is now selected, so its resize handles show right at its box's
    # top-left corner -- which, on the free layout's small FIG_MARGIN, can
    # now coincide with `corner` (WP-A's fix to tests/helpers._mouse made
    # handles actually receive real clicks, unlike before). Use a point in
    # the opposite margin, away from any handle, for the plain click below.
    far_corner = QtCore.QPointF(f.layout_widget.width() - 2, f.layout_widget.height() - 2)
    assert f._can_start_band_at(far_corner), "control: the opposite margin also starts a band"
    _mouse(f, QtCore.QEvent.MouseButtonPress, far_corner, QtCore.Qt.LeftButton)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, far_corner, QtCore.Qt.NoButton)
    assert _selected(f) == ([], [], None), "the next plain click must not be swallowed"
    f.close()


def test_band_does_not_start_on_a_curve():
    f, curve, rect, ellipse = _two_annotation_figure()
    x, y = curve.xData[len(curve.xData) // 2], curve.yData[len(curve.yData) // 2]
    on_curve = f.plots[0].getViewBox().mapViewToScene(QtCore.QPointF(x, y))
    assert not f._can_start_band_at(on_curve), \
        "a press on a curve belongs to the curve (pyqtgraph clicks it on release)"
    f.close()


def test_band_inside_a_data_area_selects_enclosed_annotations():
    f, curve, rect, ellipse = _two_annotation_figure()
    r = rect.shape_scene_rect()
    start = _band_start_up_left_of(f, r.topLeft())
    _band_drag(f, start, r.bottomRight() + QtCore.QPointF(5, 5))
    assert f.selected_annotations == [rect] and f.selected_plots == [], _selected(f)
    f.close()


def test_shift_band_adds_to_the_selection():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_curve(f, f.plots[0], curve)
    r = rect.shape_scene_rect()
    _band_drag(f, _band_start_up_left_of(f, r.topLeft()), r.bottomRight() + QtCore.QPointF(5, 5),
               mods=SHIFT)
    assert f.selected_curves == [curve] and f.selected_annotations == [rect], _selected(f)
    f.close()


def test_band_never_starts_while_brushing_or_outside_select_mode():
    f, curve, rect, ellipse = _two_annotation_figure()
    inside = _vb_center(f.plots[2])
    f.brush_action.trigger()
    assert not f._can_start_band_at(inside), "brushing owns drags in the data area"
    f.select_action.trigger()
    f.hand_action.trigger()
    _band_drag(f, QtCore.QPointF(2, 2), f.plots[0].getViewBox().sceneBoundingRect().bottomRight()
               + QtCore.QPointF(3, 3))
    assert f.selected_plots == [], "no band in Hand mode"
    f.close()


def test_arrow_keys_nudge_selected_annotations_one_undo_per_press():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    before = {a: _scene_pos(a) for a in (rect, ellipse)}
    n_undo = len(f.undo_stack)
    _key(f, QtCore.Qt.Key_Right)
    _key(f, QtCore.Qt.Key_Down, QtCore.Qt.ShiftModifier)
    for a in (rect, ellipse):
        moved = _scene_pos(a) - before[a]
        assert abs(moved.x() - f.NUDGE_PX) < 0.5 and abs(moved.y() - f.NUDGE_BIG_PX) < 0.5, (a.kind, moved)
    assert len(f.undo_stack) == n_undo + 2, "one undo entry per key press"
    f.undo()
    f.undo()
    for a in (rect, ellipse):
        assert (_scene_pos(a) - before[a]).manhattanLength() < 0.5
    f.close()


def test_arrow_keys_do_nothing_without_selected_annotations():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_subplot(f, f.plots[0])
    pos, n_undo = _scene_pos(rect), len(f.undo_stack)
    _key(f, QtCore.Qt.Key_Left)
    assert _scene_pos(rect) == pos and len(f.undo_stack) == n_undo
    f.close()


def test_tab_cycles_every_item_in_reading_order_and_wraps():
    f, curve, rect, ellipse = _two_annotation_figure()
    order = f._tab_order()
    assert order[0] is f.plots[0] and order[1] is curve, "top-left subplot first, then its curves"
    assert ellipse in order and rect in order and order.index(rect) > order.index(f.plots[1])

    def current():
        sel = f.selected_plots + f.selected_curves + f.selected_annotations
        assert len(sel) == 1, sel
        return sel[0]

    for expected in order + [order[0]]:
        _key(f, QtCore.Qt.Key_Tab)
        assert current() is expected, (expected, current())
    _key(f, QtCore.Qt.Key_Backtab, QtCore.Qt.ShiftModifier)  # what a keyboard sends for Shift+Tab
    assert current() is order[-1]
    assert isinstance(QtWidgets.QApplication.focusWidget(), pg.GraphicsLayoutWidget), \
        "Tab must not move keyboard focus to the toolbar"
    f.close()


def _real_click(f, pt):
    _mouse(f, QtCore.QEvent.MouseButtonPress, pt, QtCore.Qt.LeftButton)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, pt, QtCore.Qt.NoButton)


def _click_selection(f):
    if f.selected_annotations:
        return ('annotation', f.selected_annotations[0])
    if f.selected_curves:
        return ('curve', f.selected_curves[0])
    if f.selected_plots:
        return ('subplot', f.selected_plots[0])
    return None


def _overlap_figure():
    """One subplot, a fixed (non-auto-ranging) view, a curve crossing the
    view's center, and a rect annotation straddling that same center --
    a deliberately robust fixture for click-cycling: an explicit range
    (not left auto-ranging, which can still be settling across the few
    real events these tests send) and a click point well inside each
    shape, not at a razor-thin edge where a tiny viewPixelSize fluctuation
    could flip containment."""
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    x = np.linspace(0, 100, 200)
    f._add_series(p, 'line', x, x, name='ramp')
    f.show()
    app.processEvents()
    vb = p.getViewBox()
    vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0)
    app.processEvents()
    center = vb.mapViewToScene(QtCore.QPointF(50, 50))
    ann = f._create_annotation('rect', 'axes', p, QtCore.QPointF(30, 30), QtCore.QPointF(40, 40))
    f._deselect_all()
    app.processEvents()
    return f, p, ann, center


def test_click_cycling_steps_through_overlapping_objects_and_wraps():
    """Select mode: repeated plain clicks at (about) the same spot step
    through whatever's stacked there -- built from real Qt mouse events
    (CLAUDE.md: this depends on real dispatch order between a curve's own
    clickable protocol, an annotation's native mousePressEvent, and the
    scene-level click signal, which a direct method call can't show)."""
    f, p, ann, pt = _overlap_figure()
    targets = f._stacked_click_targets(pt)
    assert len(targets) >= 2, "control: needs a real overlap here"

    seen = []
    for _ in range(len(targets) + 1):
        _real_click(f, pt)
        seen.append(_click_selection(f))
        time.sleep(0.6)  # comfortably above a real double-click interval, under CLICK_CYCLE_TIMEOUT_S
    assert all(s is not None for s in seen), seen
    assert len(set(seen)) == len(targets), (seen, [(k, type(o).__name__) for k, o, plt in targets])
    assert seen[0] == seen[len(targets)], "one full cycle must wrap back to the first selection"

    # A click clearly elsewhere is not "the same spot": no cycling, and it
    # breaks the cycle for a subsequent click back at pt too.
    other = _empty_scene_point(f)
    _real_click(f, other)
    assert _click_selection(f) is None
    time.sleep(0.6)
    _real_click(f, pt)
    assert _click_selection(f) == seen[0], "back at pt: cycling restarts at the top, not mid-cycle"
    f.close()


def test_click_cycling_only_applies_in_select_mode():
    f, p, ann, pt = _overlap_figure()
    assert len(f._stacked_click_targets(pt)) >= 2, "control: needs a real overlap here"
    f.set_interaction_mode('hand')
    _real_click(f, pt)
    first = _click_selection(f)
    time.sleep(0.6)
    _real_click(f, pt)
    assert _click_selection(f) == first, "Hand mode: no cycling, not a selection mode at all"
    f.close()


# -- click hit-tolerance and right-click stickiness (P2) --------------------
R = QtCore.Qt.RightButton
NO = QtCore.Qt.NoButton


def _perp_direction(vb, cx, cy):
    """Screen-space unit vector perpendicular to the data-space line
    through (cx-1, cy-1) -> (cx+1, cy+1) -- computed in SCENE (pixel)
    space, not assumed from the data-space slope, since a view's X/Y data-
    per-pixel scale isn't necessarily 1:1 (lafigure-axes-geometry)."""
    p1 = vb.mapViewToScene(QtCore.QPointF(cx - 1, cy - 1))
    p2 = vb.mapViewToScene(QtCore.QPointF(cx + 1, cy + 1))
    d = p2 - p1
    length = math.hypot(d.x(), d.y())
    return QtCore.QPointF(-d.y(), d.x()) / length


def _fixed_line_figure():
    """One subplot, a fixed (non-auto-ranging) view, a 45-degree ramp --
    same "robust for real mouse-event tests" pattern as _overlap_figure."""
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    x = np.linspace(0, 100, 200)
    c = f._add_series(p, 'line', x, x, name='ramp', pen=pg.mkPen('r', width=2)).item
    f.show()
    app.processEvents()
    app.processEvents()  # let the ViewBox's lazy auto-range settle first
    vb = p.getViewBox()
    vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0)
    app.processEvents()
    return f, p, c


def _fixed_scatter_figure():
    """One subplot, a single, isolated scatter point -- no neighboring
    point for the (otherwise invisible) connecting line to pass near, so
    a hit only ever comes from the marker's own (padded) hit-test."""
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0)
    s = ax.scatter(np.array([40.0]), np.array([40.0]), size=4)
    f.show()
    app.processEvents()
    app.processEvents()  # let the ViewBox's lazy auto-range settle first
    vb = ax.plot_item.getViewBox()
    vb.setRange(xRange=(-20, 100), yRange=(-20, 100), padding=0)
    app.processEvents()
    return f, ax.plot_item, s.item


def test_real_click_a_few_px_off_a_curves_path_still_selects_it():
    """A click perpendicular to the line's own screen-space path by a few
    pixels -- a clean miss under the old width=8 mouseWidth (half-width 4)
    -- must still select it once padded a few pixels wider
    (selection_ui._wire_curve_clickable)."""
    f, p, c = _fixed_line_figure()
    vb = p.getViewBox()
    center = vb.mapViewToScene(QtCore.QPointF(50, 50))
    off = center + _perp_direction(vb, 50, 50) * 6
    f._click_cycle = None
    _mouse(f, QtCore.QEvent.MouseButtonPress, off, QtCore.Qt.LeftButton)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, off, NO)
    assert f.selected_curves == [c], "a few px off the line's path still selects it"
    f.close()


def test_real_click_a_few_px_off_a_scatter_point_still_selects_it():
    """Same as above for a scatter marker: an offset a dead-center-only
    hit test (pyqtgraph's own ScatterPlotItem._maskAt, with no tolerance
    at all) would miss must still select it, via _padded_points_at."""
    f, p, c = _fixed_scatter_figure()
    vb = p.getViewBox()
    center = vb.mapViewToScene(QtCore.QPointF(40.0, 40.0))
    off = center + QtCore.QPointF(6, 0)
    f._click_cycle = None
    _mouse(f, QtCore.QEvent.MouseButtonPress, off, QtCore.Qt.LeftButton)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, off, NO)
    assert f.selected_curves == [c], "a few px off the marker still selects it"
    f.close()


def test_dead_center_scatter_click_selects_it_too():
    """Root-cause regression guard: before this fix, pyqtgraph's own
    ScatterPlotItem.mouseClickEvent already accepted a dead-center click on
    its own marker (hit-testing it correctly), but with nothing connected
    to curve.scatter.sigClicked the accepted click was silently swallowed
    -- nothing was ever selected, even exactly on the point (verified live
    before this fix; see this package's final report)."""
    f, p, c = _fixed_scatter_figure()
    vb = p.getViewBox()
    center = vb.mapViewToScene(QtCore.QPointF(40.0, 40.0))
    f._click_cycle = None
    _mouse(f, QtCore.QEvent.MouseButtonPress, center, QtCore.Qt.LeftButton)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, center, NO)
    assert f.selected_curves == [c]
    f.close()


def test_right_click_on_an_already_selected_curve_keeps_it_selected():
    """Reproduced with real QMouseEvents, not a direct method call
    (CLAUDE.md bugs #11/#19 both warn a direct call can hide exactly this
    class of bug): a right-click landing at the same spot as the left
    click that just selected the curve used to also feed click-cycling
    (_apply_click_cycle), which -- since the right click looked like a
    repeat click "at the same spot" -- silently advanced the selection to
    the NEXT stacked target (the subplot), right after the curve's own
    context menu had already opened (correctly) for that right-click."""
    f, p, c = _fixed_line_figure()
    vb = p.getViewBox()
    center = vb.mapViewToScene(QtCore.QPointF(50, 50))
    f._click_cycle = None
    _mouse(f, QtCore.QEvent.MouseButtonPress, center, QtCore.Qt.LeftButton)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, center, NO)
    assert f.selected_curves == [c], "control: the left click selected the curve"

    _mouse(f, QtCore.QEvent.MouseButtonPress, center, R, button=R)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, center, NO, button=R)
    assert f.selected_curves == [c], "the right-click must keep the curve selected"
    assert f.selected_plots == [], "must not flip the selection to the subplot"
    f.close()


# -- debug-mode click/selection-dispatch logging (Round 3 / WP-DBG3) --------
class _ListHandler(logging.Handler):
    """Appends every emitted record's rendered message to `messages`. Attach
    to logging.getLogger('lafigure') around an assertion, then remove --
    this project has no pytest/caplog, so this is the small per-package
    handler CLAUDE.md's Round-3 plan calls for (PLAN.md: "small duplication
    across independent packages beats a shared file neither owns")."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _debug_log(fn):
    """Run fn() with a _ListHandler attached to logging.getLogger('lafigure')
    at DEBUG level; returns the messages it captured. Enabling debug mode
    for real (lafigure.debug.enable_debug_mode, WP-DBG1) attaches handlers
    the same way, just to a file/stderr instead of a list -- this is the
    plain-stdlib equivalent for an assertion."""
    logger = logging.getLogger('lafigure')
    handler = _ListHandler()
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        fn()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    return handler.messages


def _dbg3_figure():
    """One subplot named 'Ramp', a fixed-view 45-degree line named 'ramp' --
    same "fixed view, real mouse events" pattern as _fixed_line_figure, kept
    as its own fixture (rather than reusing that one directly) so the
    subplot has an identifiable name for the log-message assertions below,
    without touching a helper other tests in this file already depend on."""
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0, title='Ramp')
    x = np.linspace(0, 100, 200)
    c = f._add_series(p, 'line', x, x, name='ramp', pen=pg.mkPen('r', width=2)).item
    f.show()
    app.processEvents()
    app.processEvents()  # let the ViewBox's lazy auto-range settle first
    vb = p.getViewBox()
    vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0)
    app.processEvents()
    return f, p, c


def test_click_dispatch_logs_a_plain_click_on_a_curve():
    """A real plain click landing on a curve produces a DEBUG record from
    _on_scene_clicked (the one central click dispatcher) naming that
    curve."""
    f, p, c = _dbg3_figure()
    vb = p.getViewBox()
    pt = vb.mapViewToScene(QtCore.QPointF(50, 50))  # on the 'ramp' line itself

    messages = _debug_log(lambda: _real_click(f, pt))

    dispatch = [msg for msg in messages if msg.startswith('click:')]
    assert dispatch, "no click-dispatch log record was produced by a real click"
    assert any("curve 'ramp'" in msg for msg in dispatch)
    assert any('gesture=plain' in msg for msg in dispatch)
    f.close()


def test_click_dispatch_logs_a_shift_click_adding_a_subplot():
    """A real Shift+click on empty subplot space (clear of the curve) both
    adds the subplot to the selection AND produces a DEBUG record naming
    that subplot."""
    f, p, c = _dbg3_figure()
    assert p not in f.selected_plots, "control: nothing selected yet"
    vb = p.getViewBox()
    pt = vb.mapViewToScene(QtCore.QPointF(10, 90))  # well off the y=x diagonal

    def do_click():
        _mouse(f, QtCore.QEvent.MouseButtonPress, pt, QtCore.Qt.LeftButton, mods=SHIFT)
        _mouse(f, QtCore.QEvent.MouseButtonRelease, pt, NO, mods=SHIFT)

    messages = _debug_log(do_click)

    assert p in f.selected_plots, "control: the shift-click must have added the subplot"
    dispatch = [msg for msg in messages if msg.startswith('click:')]
    assert dispatch
    assert any(f.subplot_name(p) in msg and 'subplot' in msg for msg in dispatch)
    assert any('shift' in msg for msg in dispatch)
    f.close()


def test_click_dispatch_logs_a_click_on_empty_space():
    """A real click landing outside every subplot produces a DEBUG record
    with an 'empty space' marker."""
    f, p, c = _dbg3_figure()
    pt = _empty_scene_point(f)

    messages = _debug_log(lambda: _real_click(f, pt))

    dispatch = [msg for msg in messages if msg.startswith('click:')]
    assert dispatch
    assert any('empty space' in msg for msg in dispatch)
    f.close()
