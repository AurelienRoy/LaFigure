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
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

from tests.helpers import (
    SHIFT, FakeClickEvent, has_border, shown_figure, first_curve, _vb_center,
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
    f.brush_action.trigger()
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
