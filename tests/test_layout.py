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

"""The free layout on a fractional grid (layout.py, grid.py, handles.py).

Every drag here is a real QMouseEvent sequence sent to the viewport
(_mouse), since what a drag does depends on Qt's item grabbing and on the
scene event filter (rubber band) seeing the same events. Geometry checks
compare the neighbors' real sceneBoundingRect() before and after, not just
the boxes bookkeeping (CLAUDE.md bug #6).
"""
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from lafigure import grid
from lafigure.handles import GutterHandle
from tests.helpers import (
    app, m, shown_figure, _click_subplot,
)

L = QtCore.Qt.LeftButton
R = QtCore.Qt.RightButton
NO = QtCore.Qt.NoButton
ALT = QtCore.Qt.AltModifier
CTRL = QtCore.Qt.ControlModifier
PRESS = QtCore.QEvent.MouseButtonPress
MOVE = QtCore.QEvent.MouseMove
RELEASE = QtCore.QEvent.MouseButtonRelease


def _mouse(f, etype, scene_pt, buttons, button=L, mods=QtCore.Qt.NoModifier):
    """Like helpers._mouse, but with a real global position. The short
    QMouseEvent constructor sets globalPos to QCursor.pos(), and
    QGraphicsScene picks the *item* under the mouse from the global
    position (mapped back through the viewport) -- so helpers._mouse
    reaches the scene event filter (which reads scenePos) at the right
    point but hands presses to whatever item sits under the real cursor.
    Dragging a handle or a gutter needs the item to get the press."""
    view = f.layout_widget
    local = QtCore.QPointF(view.mapFromScene(scene_pt))
    global_pos = QtCore.QPointF(view.viewport().mapToGlobal(local.toPoint()))
    ev = QtGui.QMouseEvent(etype, local, local, global_pos, button, buttons, mods)
    QtWidgets.QApplication.sendEvent(view.viewport(), ev)
    app.processEvents()


def _drag(f, a, b, mods=QtCore.Qt.NoModifier):
    _mouse(f, PRESS, a, L, mods=mods)
    for t in (0.25, 0.5, 1.0):
        _mouse(f, MOVE, a + (b - a) * t, L, button=NO, mods=mods)
    _mouse(f, RELEASE, b, NO, mods=mods)


def _rect(p):
    return QtCore.QRectF(p.sceneBoundingRect())


def _close(a, b, tol=1e-6):
    return abs(a - b) <= tol


def _rects_close(a, b, tol=0.01):
    return all(abs(u - v) <= tol for u, v in zip(a.getRect(), b.getRect()))


def _handle_center(f, role):
    h = f.move_handle if role == 'move' else f.resize_handles[role]
    assert h.isVisible(), f"control: the {role} handle must be showing"
    return h.sceneBoundingRect().center()


def _gutter_point(f, axis, index, along):
    """A scene point on interior grid line `index`, at grid coordinate
    `along` on the other axis."""
    if axis == 'col':
        return QtCore.QPointF(f._gx_to_px(index), f._gy_to_px(along))
    return QtCore.QPointF(f._gx_to_px(along), f._gy_to_px(index))


def _three_columns():
    """Empty figure with a | b | c in one row and an inset d inside b's
    cell (grid box 1.25..1.75 x 0.25..0.75). Nothing selected."""
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    a = f.add_subplot(0, 0, title="a")
    b = f.add_subplot(0, 1, title="b")
    c = f.add_subplot(0, 2, title="c")
    d = f.add_subplot(0, 1, title="d")
    f.set_subplot_box(d, (1.25, 0.25, 1.75, 0.75))
    f._deselect_all()
    app.processEvents()
    return f, a, b, c, d


# -- pure grid math ----------------------------------------------------------

def test_grid_math_maps_piecewise_linearly_and_round_trips():
    lines = [0.0, 0.2, 1.0]
    assert _close(grid.to_frac(lines, 0.5), 0.1)
    assert _close(grid.to_frac(lines, 1.5), 0.6)
    assert _close(grid.to_frac(lines, 2.0), 1.0)
    for g in (0.0, 0.3, 1.0, 1.25, 2.0):
        assert _close(grid.from_frac(lines, grid.to_frac(lines, g)), g)
    inserted = grid.insert_track(grid.equal_lines(2), 1)
    assert all(_close(u, v) for u, v in zip(inserted, grid.equal_lines(3))), "equal tracks stay equal"
    uneven = [0.0, 0.3, 1.0]
    back = grid.delete_track(grid.insert_track(uneven, 2), 2)
    assert all(_close(u, v) for u, v in zip(back, uneven)), "delete_track undoes insert_track"
    # Insert at line 1: a span starting on it moves, one crossing it grows,
    # one ending on it stays -- and delete is the exact inverse.
    for span, shifted in (((1, 2), (2, 3)), ((0.5, 1.5), (0.5, 2.5)), ((0, 1), (0, 1))):
        assert grid.shift_span_for_insert(*span, 1) == shifted
        assert grid.shift_span_for_delete(*shifted, 1) == span
    assert grid.gutter_segments([(0, 0, 2, 1), (0, 1, 1, 2)], 'col', 1, 2) == [(1.0, 2.0)], \
        "a line under a spanning subplot is no gutter there"


# -- resize (bugs #2, #3, #6) --------------------------------------------------

def test_resizing_a_border_never_moves_a_sibling():
    """Drag p1's right handle 80 px (Alt: no snapping). Only p1 changes;
    p2, which it now overlaps, keeps its exact geometry -- as do p3/p4."""
    f = shown_figure()
    p1, p2, p3, p4 = f.plots
    _click_subplot(f, p1)
    before = {p: _rect(p) for p in (p1, p2, p3, p4)}
    n_undo = len(f.undo_stack)
    start = _handle_center(f, 'right')
    _drag(f, start, start + QtCore.QPointF(80, 0), mods=ALT)
    assert abs(_rect(p1).width() - (before[p1].width() + 80)) < 0.5
    assert _rect(p1).left() == before[p1].left() and _rect(p1).height() == before[p1].height()
    for p in (p2, p3, p4):
        assert _rect(p) == before[p], "a sibling's real geometry changed"
    assert len(f.undo_stack) == n_undo + 1, "one drag = one undo entry"
    f.undo()
    assert _rect(p1) == before[p1]
    f.redo()
    assert abs(_rect(p1).width() - (before[p1].width() + 80)) < 0.5
    f.close()


def test_two_consecutive_drags_and_the_subplot_stays_live():
    """Bug #2: a second drag on the same subplot used to KeyError. Bug #3:
    a detached subplot went invisible. Both drags must work, and the plot
    must stay a visible scene item that still takes clicks."""
    f = shown_figure()
    p1 = f.plots[0]
    _click_subplot(f, p1)
    w0 = _rect(p1).width()
    start = _handle_center(f, 'right')
    _drag(f, start, start + QtCore.QPointF(-60, 0), mods=ALT)
    assert abs(_rect(p1).width() - (w0 - 60)) < 0.5
    start = _handle_center(f, 'bottom-right')
    h0 = _rect(p1).height()
    _drag(f, start, start + QtCore.QPointF(30, -40), mods=ALT)
    assert abs(_rect(p1).width() - (w0 - 30)) < 0.5 and abs(_rect(p1).height() - (h0 - 40)) < 0.5
    assert p1.scene() is f.layout_widget.scene() and p1.isVisible()
    f._deselect_all()
    _click_subplot(f, p1)
    assert f.selected_plots == [p1], "still clickable after two drags"
    assert len(f.undo_stack) >= 2
    f.close()


# -- delete leaves a hole (bug #1) --------------------------------------------

def test_delete_in_a_shared_row_never_disturbs_the_sibling():
    f = shown_figure()
    p1, p2, p3, p4 = f.plots
    p4_rect, p4_box = _rect(p4), f.boxes[p4]
    lines = (list(f.grid_cols), list(f.grid_rows))
    p3_box = f.boxes[p3]
    _click_subplot(f, p3)
    f.delete_selection()
    assert p3 not in f.plots and f.boxes[p4] == p4_box and _rect(p4) == p4_rect
    assert (f.grid_cols, f.grid_rows) == lines, "delete leaves a hole, the grid is untouched"
    f.undo()
    p3b = f.plots[-1]
    assert f.boxes[p3b] == p3_box, "undo restores the exact box"
    assert f.boxes[p4] == p4_box and _rect(p4) == p4_rect
    f.redo()
    assert f.boxes[p4] == p4_box and _rect(p4) == p4_rect
    # The hole is the first empty cell: Add Subplot fills it, no new row.
    f.add_new_subplot()
    assert f.boxes[f.plots[-1]] == p3_box and f.grid_rows == lines[1]
    f.close()


def test_add_subplot_fills_the_first_empty_cell_else_appends_a_row():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    f.add_new_subplot()
    assert f.boxes[f.plots[0]] == (0, 0, 1, 1) and len(f.grid_rows) == 2, "empty figure: cell (0, 0)"
    f.add_new_subplot()
    assert f.boxes[f.plots[1]] == (0, 1, 1, 2) and len(f.grid_rows) == 3, "full grid: append a row"
    rect0 = _rect(f.plots[0])
    f.undo()
    assert len(f.grid_rows) == 2 and _rect(f.plots[0]) != rect0, "undo removes the appended row"
    f.redo()
    assert len(f.grid_rows) == 3 and _rect(f.plots[0]) == rect0
    f.close()


def test_undoing_a_paste_restores_the_grid_it_grew():
    f = shown_figure()
    lines = (list(f.grid_cols), list(f.grid_rows))
    rects = [_rect(p) for p in f.plots]
    _click_subplot(f, f.plots[0])
    _click_subplot(f, f.plots[1], modifiers=QtCore.Qt.ShiftModifier)
    f.copy_subplot()
    f.paste_subplot()
    assert len(f.grid_rows) == 5, "two pasted subplots, two new rows"
    f.undo()
    assert (f.grid_cols, f.grid_rows) == lines
    assert [_rect(p) for p in f.plots] == rects
    f.close()


# -- FFT row insertion ---------------------------------------------------------

def test_fft_inserts_a_row_under_the_source_and_round_trips():
    f = shown_figure()
    p1, p2, p3, p4 = f.plots
    boxes = {p: f.boxes[p] for p in f.plots}
    rects = {p: _rect(p) for p in f.plots}
    f.focused_plot = p1
    f.fft_below()
    fft = f.plots[-1]
    assert f.boxes[fft] == (0, 1, 1, 2) and f._grid_position(fft) == (1, 0)
    assert len(f.grid_rows) == 4
    assert f.boxes[p1] == boxes[p1] and f.boxes[p2] == boxes[p2], "the source row stays"
    assert f.boxes[p3] == (0, 2, 1, 3) and f.boxes[p4] == (1, 2, 2, 3), "rows below shift down"
    f.undo()
    assert fft not in f.plots and len(f.grid_rows) == 3
    for p in f.plots:
        assert f.boxes[p] == boxes[p] and _rects_close(_rect(p), rects[p])
    f.redo()
    fft = f.plots[-1]
    assert f.boxes[fft] == (0, 1, 1, 2) and f.boxes[p4] == (1, 2, 2, 3)
    f.undo()
    f.close()


def test_insert_subplot_below_a_spanning_subplot():
    """Fractional coordinates make the shift safe anywhere: a subplot
    crossing the new line grows instead of being walked into a sibling."""
    f, a, b, c, d = _three_columns()
    e = f.add_subplot(1, 0, rowspan=1, colspan=1, title="e")
    tall = f.add_subplot(0, 3, rowspan=2, title="tall")
    new = f.insert_subplot_below(a)
    assert f.boxes[new] == (0, 1, 1, 2)
    assert f.boxes[e] == (0, 2, 1, 3) and f.boxes[tall] == (3, 0, 4, 3)
    assert f.boxes[d] == (1.25, 0.25, 1.75, 0.75)
    f.close()


# -- grid-line (gutter) drag ---------------------------------------------------

def test_dragging_a_grid_line_rescales_attached_edges_only():
    f, a, b, c, d = _three_columns()
    before = {p: _rect(p) for p in (a, b, c, d)}
    n_undo = len(f.undo_stack)
    x1 = f._gx_to_px(1)
    pt = _gutter_point(f, 'col', 1, 0.5)
    _mouse(f, PRESS, pt, L, mods=ALT)
    _mouse(f, MOVE, pt + QtCore.QPointF(30, 0), L, button=NO, mods=ALT)
    assert f._band is None, "the rubber band must not claim a gutter drag"
    _mouse(f, MOVE, pt + QtCore.QPointF(60, 0), L, button=NO, mods=ALT)
    _mouse(f, RELEASE, pt + QtCore.QPointF(60, 0), NO, mods=ALT)
    assert abs(f._gx_to_px(1) - (x1 + 60)) < 0.5, "the line followed the mouse"
    assert abs(_rect(a).width() - (before[a].width() + 60)) < 0.5
    assert abs(_rect(b).left() - (before[b].left() + 60)) < 0.5
    assert _rect(b).right() == before[b].right()
    assert _rect(c) == before[c], "a subplot on the far side of the next line is untouched"
    # The inset keeps its place *proportionally* inside the resized cell.
    x1, x2 = f._gx_to_px(1), f._gx_to_px(2)
    pad = f.CELL_PAD
    assert abs(_rect(d).left() - (x1 + 0.25 * (x2 - x1) + pad)) < 0.01
    assert abs(_rect(d).right() - (x1 + 0.75 * (x2 - x1) - pad)) < 0.01
    assert f.boxes[d] == (1.25, 0.25, 1.75, 0.75), "grid coordinates never change on a line drag"
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    for p in (a, b, c, d):
        assert _rect(p) == before[p]
    f.close()


def test_gutter_cursor_and_hover():
    f, a, b, c, d = _three_columns()
    gutters = [g for g in f._gutters.values() if g.isVisible()]
    assert {(g.axis, g.index) for g in gutters} == {('col', 1), ('col', 2)}
    assert all(g.cursor().shape() == QtCore.Qt.SplitHCursor for g in gutters)
    _mouse(f, MOVE, _gutter_point(f, 'col', 2, 0.5), NO, button=NO)
    assert f.layout_widget.viewport().cursor().shape() == QtCore.Qt.SplitHCursor
    f.set_interaction_mode('hand')
    assert not any(g.isVisible() for g in f._gutters.values()), "gutters are a Select-mode tool"
    f.set_interaction_mode('select')
    p = f.plots[0]
    _click_subplot(f, p)
    assert f.resize_handles['right'].cursor().shape() == QtCore.Qt.SizeHorCursor
    assert f.resize_handles['top-left'].cursor().shape() == QtCore.Qt.SizeFDiagCursor
    assert f.move_handle.cursor().shape() == QtCore.Qt.SizeAllCursor
    f.close()


def test_gutter_right_click_menu_inserts_deletes_and_equalizes():
    f = shown_figure()
    p1, p2, p3, p4 = f.plots
    shown = []
    original_exec = QtWidgets.QMenu.exec_
    QtWidgets.QMenu.exec_ = lambda self, *a, **k: shown.append(self)
    try:
        pt = _gutter_point(f, 'col', 1, 0.5)
        _mouse(f, PRESS, pt, R, button=R)
        _mouse(f, RELEASE, pt, NO, button=R)
    finally:
        QtWidgets.QMenu.exec_ = original_exec
    assert len(shown) == 1, "a right-click on a gutter opens its menu"
    actions = {a.text(): a for a in shown[0].actions() if a.text()}
    assert set(actions) >= {"Insert Column Here", "Delete Column Left", "Delete Column Right",
                            "Equalize Columns"}
    assert not actions["Delete Column Left"].isEnabled(), "only an empty column can be deleted"
    p1_box = f.boxes[p1]
    actions["Insert Column Here"].trigger()
    assert len(f.grid_cols) == 4 and f.boxes[p1] == p1_box
    assert f.boxes[p2] == (2, 0, 3, 1) and f.boxes[p4] == (2, 1, 3, 2)
    menu = f._build_gutter_menu('col', 1)
    actions = {a.text(): a for a in menu.actions() if a.text()}
    assert actions["Delete Column Right"].isEnabled(), "the new column is empty"
    f.undo()
    assert len(f.grid_cols) == 3 and f.boxes[p2] == (1, 0, 2, 1)
    f.grid_cols = [0.0, 0.3, 1.0]
    f._apply_layout()
    f._build_gutter_menu('row', 1)  # control: row gutters build too
    actions = {a.text(): a for a in f._build_gutter_menu('col', 1).actions() if a.text()}
    actions["Equalize Columns"].trigger()
    assert all(_close(u, v) for u, v in zip(f.grid_cols, [0.0, 0.5, 1.0]))
    f.undo()
    assert all(_close(u, v) for u, v in zip(f.grid_cols, [0.0, 0.3, 1.0]))
    f.close()


# -- move / swap ---------------------------------------------------------------

def test_plain_drop_moves_and_ctrl_drop_swaps():
    f = shown_figure()
    p1, p2, p3, p4 = f.plots
    b1, b2, b4 = f.boxes[p1], f.boxes[p2], f.boxes[p4]
    p4_rect = _rect(p4)
    _click_subplot(f, p1)
    n_undo = len(f.undo_stack)
    _drag(f, _handle_center(f, 'move'), p4.sceneBoundingRect().center())
    assert f.boxes[p1] == b4, "plain drop: p1 moves onto p4's box (snapped)"
    assert f.boxes[p4] == b4 and _rect(p4) == p4_rect, "and p4 stays where it was"
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert f.boxes[p1] == b1
    _click_subplot(f, p1)
    _drag(f, _handle_center(f, 'move'), p2.sceneBoundingRect().center(), mods=CTRL)
    assert f.boxes[p1] == b2 and f.boxes[p2] == b1, "Ctrl+drop swaps"
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert f.boxes[p1] == b1 and f.boxes[p2] == b2
    f.redo()
    assert f.boxes[p1] == b2 and f.boxes[p2] == b1
    f.close()


# -- snapping ------------------------------------------------------------------

def test_resize_snaps_to_subdivisions_and_alt_disables_it():
    f = shown_figure()
    p1 = f.plots[0]
    _click_subplot(f, p1)
    target = f._gx_to_px(1.5) + 5  # 5 px off the half of column 1
    start = _handle_center(f, 'right')
    dx = target - f._gx_to_px(1)
    _mouse(f, PRESS, start, L)
    _mouse(f, MOVE, start + QtCore.QPointF(dx, 0), L, button=NO)
    assert f._snap_guides.isVisible(), "the magnetic sub-grid shows during the drag"
    _mouse(f, RELEASE, start + QtCore.QPointF(dx, 0), NO)
    assert not f._snap_guides.isVisible(), "and only during the drag"
    assert f.boxes[p1][2] == 1.5
    f.undo()
    _click_subplot(f, p1)
    start = _handle_center(f, 'right')
    _drag(f, start, start + QtCore.QPointF(dx, 0), mods=ALT)
    assert f.boxes[p1][2] != 1.5 and abs(f._gx_to_px(f.boxes[p1][2]) - target) < 0.5
    f.close()


def test_snaps_to_another_subplots_edge_and_to_the_figure_margin():
    f, a, b, c, d = _three_columns()
    f.set_subplot_box(d, (1.3, 0.25, 1.7, 0.75))
    _click_subplot(f, a)
    start = _handle_center(f, 'right')
    dx = f._gx_to_px(1.3) - 6 - f._gx_to_px(1)
    _drag(f, start, start + QtCore.QPointF(dx, 0))
    assert f.boxes[a][2] == 1.3, "alignment guide: snapped to d's left edge"
    # Move d so its right edge lands 5 px short of the figure's right margin.
    # (Selected directly: the scene click dispatcher hit-tests in self.plots
    # order, not z-order, so a click on an inset still selects its host.)
    f._on_plot_clicked(d)
    dx = (f._gx_to_px(3) - 5) - f._gx_to_px(1.7)
    start = _handle_center(f, 'move')
    _drag(f, start, start + QtCore.QPointF(dx, 0))
    assert f.boxes[d][2] == 3.0, "snapped to the figure margin"
    assert abs((f.boxes[d][2] - f.boxes[d][0]) - 0.4) < 1e-9, "a move keeps the box's grid size"
    f.close()


# -- overlap and z-order -------------------------------------------------------

def test_overlap_gets_an_opaque_background_and_z_order_is_undoable():
    f, a, b, c, d = _three_columns()
    assert d.zValue() > b.zValue() and _rect(d).intersects(_rect(b)), "control: the inset overlaps b"
    assert d.autoFillBackground() and not b.autoFillBackground(), "the one on top is opaque"
    assert not a.autoFillBackground(), "no overlap, no background"
    n_undo = len(f.undo_stack)
    f.send_to_back(d)
    assert d.zValue() < b.zValue() and b.autoFillBackground() and not d.autoFillBackground()
    f.bring_to_front(d)
    assert d.zValue() > max(p.zValue() for p in (a, b, c)) and d.autoFillBackground()
    assert len(f.undo_stack) == n_undo + 2
    f.undo()
    assert d.zValue() < b.zValue()
    f.close()


def test_box_fraction_follows_a_resized_subplot():
    """_box_fraction/_box_point: the helpers a 'border' annotation's
    offset is meant to be stored with, so it scales with its subplot."""
    f = shown_figure()
    p1 = f.plots[0]
    pt = _rect(p1).topLeft() + QtCore.QPointF(50, 20)
    frac = f._box_fraction(p1, pt)
    assert (f._box_point(p1, frac) - pt).manhattanLength() < 1e-6
    f.set_subplot_box(p1, (0, 0, 2, 1))
    r = _rect(p1)
    moved = f._box_point(p1, frac)
    assert abs((moved.x() - r.left()) / r.width() - frac.x()) < 1e-9
    assert moved.x() - r.left() > 50 + 40, "the offset grew with the box"
    f.close()


# -- window resize, construction site, obsolete API ----------------------------

def test_window_resize_recomputes_every_box():
    f = shown_figure()
    p2 = f.plots[1]
    f.resize(700, 500)
    app.processEvents()
    vp = f.layout_widget.viewport()
    assert abs(_rect(p2).right() - (vp.width() - f.FIG_MARGIN - f.CELL_PAD)) < 0.01
    assert abs(_rect(p2).top() - (f.FIG_MARGIN + f.CELL_PAD)) < 0.01
    f.close()


def test_toggle_overlap_resize_is_a_harmless_no_op():
    f = shown_figure()
    rects = [_rect(p) for p in f.plots]
    f.toggle_overlap_resize(True)
    f.toggle_overlap_resize(False)
    f._reattach_all_floating()
    assert [_rect(p) for p in f.plots] == rects
    f.close()


def test_add_subplot_is_the_only_subplot_construction_site():
    """add_subplot is where new subplots adopt the figure-wide toggles; a
    second PlotItem construction (or a leftover addPlot()) would silently
    bypass that. Scans every module of the package."""
    import glob
    import os
    import re
    package_dir = os.path.dirname(m.__file__)
    sites = {}
    for path in glob.glob(os.path.join(package_dir, '*.py')):
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
        # (?<!\w): ScatterPlotItem( etc. are not subplots.
        n = text.count('.addPlot(') + len(re.findall(r'(?<!\w)PlotItem\(', text))
        if n:
            sites[os.path.basename(path)] = n
    assert sites == {'layout.py': 1}, f"a new subplot construction site bypasses add_subplot: {sites}"
    with open(os.path.join(package_dir, 'layout.py'), encoding='utf-8') as fh:
        assert 'def add_subplot' in fh.read()  # control: the scan is reading the right file
    assert GutterHandle is not None
