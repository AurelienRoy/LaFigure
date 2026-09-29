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

"""View state and per-subplot data actions (view_ops.py): interaction
modes, Home/Fit, Zoom Rect box color, Link X, Remove Average, FFT.
Figure-wide toggles are driven with action.trigger() -- what a real click
does; setChecked() alone never emits `triggered`.
"""
import time

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from tests.helpers import (
    app, m, has_border, shown_figure, first_curve, _mouse, _ramp_figure, _is_x_linked,
    _band_drag, _press_escape,
)


def test_fft_adds_a_subplot():
    """FFT acts on the selected curve and adds a subplot."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots
    c2 = first_curve(p2)

    win._on_plot_clicked(p2)
    win._select_curve(c2)
    n_before = len(win.plots)
    win.fft_below()
    assert len(win.plots) == n_before + 1
    win.close()


def test_interaction_modes_toggle_selection_ui():
    """Zoom Rect / Hand set the ViewBox mouse mode and hide selection;
    Select restores it."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

    win.set_interaction_mode('zoom')
    assert p1.getViewBox().state['mouseMode'] == pg.ViewBox.RectMode
    assert not win.move_handle.isVisible(), "handles must be hidden outside Select mode"
    win.set_interaction_mode('hand')
    assert p1.getViewBox().state['mouseMode'] == pg.ViewBox.PanMode
    assert not win.move_handle.isVisible()
    # Clicking a plot in Hand mode still tracks focused_plot (for toolbar
    # actions) but must NOT show the selection border.
    win._on_plot_clicked(p2)
    assert win.focused_plot is p2
    assert not has_border(p2), "Hand mode must not show a selection border"
    win.set_interaction_mode('select')
    assert p1.getViewBox().state['mouseMode'] == pg.ViewBox.PanMode
    win._on_plot_clicked(p1)
    assert has_border(p1)
    assert win.move_handle.isVisible()

    win.reset_view()
    win.close()


def test_zoom_mode_uses_a_drawn_magnifying_glass_cursor():
    """Zoom Rect has no built-in Qt cursor shape to reuse (unlike Hand's
    OpenHandCursor), so it gets a drawn one -- a real QCursor backed by a
    non-empty pixmap, not a bare Qt.CursorShape, and every subplot's
    ViewBox actually has it set. A subplot added while already in Zoom
    Rect mode must get it too (add_subplot's own cursor-adoption call)."""
    win = shown_figure()
    win.set_interaction_mode('zoom')
    for p in win.plots:
        cursor = p.getViewBox().cursor()
        assert cursor.shape() == QtCore.Qt.BitmapCursor, "a real drawn cursor, not a stock shape"
        assert not cursor.pixmap().isNull() and cursor.pixmap().width() > 0

    new_plot = win.add_subplot(row=2, col=0)
    assert new_plot.getViewBox().cursor().shape() == QtCore.Qt.BitmapCursor

    win.set_interaction_mode('hand')
    assert win.plots[0].getViewBox().cursor().shape() == QtCore.Qt.OpenHandCursor
    win.close()


def test_remove_average_undo_redo():
    """Undo/redo: remove_average."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

    p1_curve = [c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)][0]
    y_before = p1_curve.yData.copy()
    win._on_plot_clicked(p1)
    win.remove_average()
    assert not np.array_equal(p1_curve.yData, y_before)
    win.undo()
    assert np.allclose(p1_curve.yData, y_before)
    win.redo()
    assert not np.array_equal(p1_curve.yData, y_before)
    win.undo()  # leave state clean for what follows
    win.close()


def test_new_subplot_adopts_link_x():
    f = m.LaFigure()
    f.link_x_action.trigger()
    f.add_new_subplot()
    new = f.plots[-1]
    assert _is_x_linked(new), "a subplot added while Link X is on must be X-linked"
    f.link_x_action.trigger()
    assert not any(_is_x_linked(p) for p in f.plots)
    f.close()


def test_link_x_survives_deleting_the_reference_subplot():
    f = m.LaFigure()
    f.link_x_action.trigger()
    old_reference = f.plots[0]
    f.delete_subplot(old_reference)
    reference = f.plots[0]
    assert not _is_x_linked(reference)
    for p in f.plots[1:]:
        assert p.getViewBox().linkedView(pg.ViewBox.XAxis) is reference.getViewBox(), \
            "followers must re-link to the new plots[0], not the deleted one"
    f.close()


def test_brush_is_a_mode_exclusive_with_select_hand_and_zoom():
    f = m.LaFigure()
    f.brush_action.trigger()
    assert f.interaction_mode == 'brush' and f.brushing
    assert not f.select_action.isChecked(), "picking Brush unchecks Select"
    assert all(p.getViewBox().state['mouseEnabled'] == [False, False] for p in f.plots),         "brushing owns left drags: no pan"
    f.select_action.trigger()
    assert f.interaction_mode == 'select' and not f.brushing
    assert not f.brush_action.isChecked(), "picking Select unchecks Brush"
    assert all(p.getViewBox().state['mouseEnabled'] == [False, False] for p in f.plots),         "Brush off must not re-enable pan while Select mode forbids it"
    f.brush_action.trigger()
    f.hand_action.trigger()
    assert not f.brushing and not f.brush_action.isChecked()
    assert all(p.getViewBox().state['mouseEnabled'] == [True, True] for p in f.plots)
    f.toggle_brush(True)
    assert f.brush_action.isChecked() and not f.hand_action.isChecked(), "the API syncs the toolbar"
    f.close()


def test_undoing_fft_drops_its_brusher():
    f = m.LaFigure()
    f._on_plot_clicked(f.plots[0])
    f.fft_below()
    fft_plot = f.plots[-1]
    assert fft_plot in f._brushers  # control: the FFT subplot really got a brusher
    f.undo()
    assert fft_plot not in f.plots
    assert set(f._brushers) <= set(f.plots), "a removed subplot's RectBrush must not linger"
    f.close()


def test_fit_vertical_uses_only_the_data_inside_the_x_range():
    f, vb = _ramp_figure()
    vb.setRange(xRange=(20, 40), yRange=(-500, 500), padding=0)
    f.fit_view_vertical()
    (x0, x1), (y0, y1) = vb.viewRange()
    assert abs(x0 - 20) < 1e-6 and abs(x1 - 40) < 1e-6, "X must not change"
    assert 15 < y0 <= 20 and 40 <= y1 < 45, (y0, y1)
    f.close()


def test_fit_horizontal_uses_only_the_data_inside_the_y_range():
    f, vb = _ramp_figure()
    vb.setRange(xRange=(-500, 500), yRange=(60, 70), padding=0)
    f.fit_view_horizontal()
    (x0, x1), (y0, y1) = vb.viewRange()
    assert abs(y0 - 60) < 1e-6 and abs(y1 - 70) < 1e-6, "Y must not change"
    assert 55 < x0 <= 60 and 70 <= x1 < 75, (x0, x1)
    f.close()


def test_fit_ignores_a_hidden_curve_and_an_empty_window():
    f, vb = _ramp_figure()
    p = f.plots[0]
    p.plot([30, 31], [1e6, -1e6]).setVisible(False)
    vb.setRange(xRange=(20, 40), yRange=(0, 1), padding=0)
    f.fit_view_vertical()
    assert vb.viewRange()[1][1] < 45, "a hidden curve must not stretch the view"
    vb.setRange(xRange=(500, 600), yRange=(0, 1), padding=0)
    f.fit_view_vertical()
    assert vb.viewRange()[1] == [0, 1], "no data in range leaves the view alone"
    f.close()


def _is_gray(vb):
    pen, brush = vb.rbScaleBox.pen().color(), vb.rbScaleBox.brush().color()
    return (pen.red() == pen.green() == pen.blue()
            and brush.red() == brush.green() == brush.blue())


def test_home_and_fit_buttons_follow_zoom_and_zoom_box_is_gray():
    """The box is checked in Zoom Rect mode, where it is drawn: pyqtgraph's
    setMouseMode(PanMode) drops its rbScaleBox and later builds a fresh,
    yellow one, so a box styled once at creation (the first version of
    this feature, and of this test, which read the box in Select mode)
    never reached the user. Also after a round trip through Select, and on
    a subplot created while already zooming."""
    f, vb = _ramp_figure()
    labels = [a.text() for a in f.findChild(QtWidgets.QToolBar).actions()]
    i = labels.index("Zoom Rect")
    assert labels[i + 1:i + 4] == ["Home", "Fit Vertical", "Fit Horizontal"], labels
    for _ in range(2):
        f.zoom_action.trigger()
        assert _is_gray(vb), "zoom rectangle must be gray, not yellow"
        f.select_action.trigger()
    f.zoom_action.trigger()
    late = f.add_subplot(row=1, col=0)
    assert _is_gray(late.getViewBox()), "a subplot added in Zoom Rect mode gets the gray box too"
    f.close()


def test_zoom_rect_box_is_gray_during_a_real_drag():
    """Real mouse events: the box pyqtgraph actually shows mid-drag."""
    f, vb = _ramp_figure()
    f.show()
    app.processEvents()
    f.zoom_action.trigger()
    L = QtCore.Qt.LeftButton
    start = vb.sceneBoundingRect().center()
    _mouse(f, QtCore.QEvent.MouseButtonPress, start, L)
    for d in (5, 20, 40):
        _mouse(f, QtCore.QEvent.MouseMove, start + QtCore.QPointF(d, d), L, button=QtCore.Qt.NoButton)
    assert vb.rbScaleBox.isVisible(), "control: the drag really is drawing the zoom box"
    assert _is_gray(vb), "the box shown during a real zoom drag must be gray"
    _mouse(f, QtCore.QEvent.MouseButtonRelease, start + QtCore.QPointF(40, 40), QtCore.Qt.NoButton)
    f.close()


def test_home_and_fit_toolbar_buttons_act_on_the_hovered_subplot():
    """Trigger the real toolbar actions, not just the methods behind them."""
    f, vb = _ramp_figure()
    actions = {a.text(): a for a in f.findChild(QtWidgets.QToolBar).actions()}
    vb.setRange(xRange=(20, 40), yRange=(-500, 500), padding=0)
    actions["Fit Vertical"].trigger()
    (x0, x1), (y0, y1) = vb.viewRange()
    assert 15 < y0 <= 20 and 40 <= y1 < 45, (y0, y1)
    vb.setRange(xRange=(-500, 500), yRange=(60, 70), padding=0)
    actions["Fit Horizontal"].trigger()
    (x0, x1), _ = vb.viewRange()
    assert 55 < x0 <= 60 and 70 <= x1 < 75, (x0, x1)
    vb.setRange(xRange=(40, 41), yRange=(40, 41), padding=0)
    actions["Home"].trigger()
    (x0, x1), (y0, y1) = vb.viewRange()
    assert x0 <= 0 and x1 >= 100 and y0 <= 0 and y1 >= 100, "Home autoranges to all the data"
    f.close()


# -- legend: visible, selectable, movable ------------------------------------
class _FakeLegendClick:
    def __init__(self):
        self.accepted = False

    def button(self):
        return QtCore.Qt.LeftButton

    def accept(self):
        self.accepted = True


def _legend_figure():
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0, title="L")
    ax.plot(np.arange(10.0), np.arange(10.0), name="one")
    ax.plot(np.arange(10.0), -np.arange(10.0), name="two")
    f.show()
    app.processEvents()
    f._on_plot_clicked(ax.plot_item)
    return f, ax.plot_item


def test_legend_toggled_on_over_existing_curves_lists_them():
    f, p = _legend_figure()
    f.toggle_legend()
    app.processEvents()
    assert p.legend is not None
    assert [label.text for _, label in p.legend.items] == ["one", "two"]
    assert not p.legend.boundingRect().isEmpty(), "a non-empty legend has a size"
    f.toggle_legend()
    assert p.legend is None
    f.close()


def test_legend_click_selects_it_and_escape_or_del_deselects():
    f, p = _legend_figure()
    f.toggle_legend()
    orig_pen = p.legend.opts['pen']
    ev = _FakeLegendClick()
    p.legend.mouseClickEvent(ev)
    assert ev.accepted and f.selected_legend is p
    assert f.selected_plots == [] and f.selected_curves == [], "exclusive, like any plain click"
    assert pg.mkPen(p.legend.opts['pen']).color().red() == 220
    _press_escape(f)
    assert f.selected_legend is None and p.legend.opts['pen'] is orig_pen, "original pen back"
    p.legend.mouseClickEvent(_FakeLegendClick())
    f.delete_selection()
    assert p.legend is None and f.selected_legend is None, "Del hides the selected legend"
    f.close()


def test_legend_drag_moves_it_as_one_undo_entry():
    f, p = _legend_figure()
    f.toggle_legend()
    app.processEvents()
    legend = p.legend
    start = QtCore.QPointF(legend.pos())
    a = legend.sceneBoundingRect().center()
    n = len(f.undo_stack)
    _band_drag(f, a, a + QtCore.QPointF(60, 40))
    app.processEvents()
    moved = QtCore.QPointF(legend.pos())
    assert (moved - start).manhattanLength() > 50, (start, moved)
    assert len(f.undo_stack) == n + 1, "the move only -- no view entry for the same gesture"
    f.undo()
    assert (QtCore.QPointF(legend.pos()) - start).manhattanLength() < 1
    f.redo()
    assert (QtCore.QPointF(legend.pos()) - moved).manhattanLength() < 1
    f.close()


# -- view history: zoom/pan are undoable -------------------------------------
def test_home_fit_and_view_all_are_undoable():
    f, vb = _ramp_figure()
    vb.setRange(xRange=(10, 20), yRange=(10, 20), padding=0)
    before = vb.viewRange()
    f.reset_view()
    assert vb.viewRange() != before
    f.undo()
    assert np.allclose(vb.viewRange(), before)
    f.redo()
    assert not np.allclose(vb.viewRange(), before)
    f.undo()
    f.fit_view_vertical()
    f.undo()
    assert np.allclose(vb.viewRange(), before)
    vb.menu.viewAll.trigger()
    assert not np.allclose(vb.viewRange(), before)
    f.undo()
    assert np.allclose(vb.viewRange(), before)
    f.close()


def test_zoom_rect_drag_is_one_undo_entry():
    f, vb = _ramp_figure()
    f.show()
    app.processEvents()
    vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0)
    f.zoom_action.trigger()
    before = vb.viewRange()
    n = len(f.undo_stack)
    _band_drag(f, vb.mapViewToScene(QtCore.QPointF(20, 80)), vb.mapViewToScene(QtCore.QPointF(60, 40)))
    app.processEvents()
    assert not np.allclose(vb.viewRange(), before), "control: the drag zoomed"
    assert len(f.undo_stack) == n + 1
    f.undo()
    assert np.allclose(vb.viewRange(), before)
    f.close()


def test_a_wheel_burst_is_one_undo_entry():
    f, vb = _ramp_figure()
    f.show()
    app.processEvents()
    vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0)
    f.hand_action.trigger()
    before = vb.viewRange()
    view = f.layout_widget
    local = QtCore.QPointF(view.mapFromScene(vb.sceneBoundingRect().center()))
    glob = QtCore.QPointF(view.viewport().mapToGlobal(local.toPoint()))
    n = len(f.undo_stack)
    for _ in range(3):
        ev = QtGui.QWheelEvent(local, glob, QtCore.QPoint(0, 0), QtCore.QPoint(0, 120),
                               QtCore.Qt.NoButton, QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(view.viewport(), ev)
        app.processEvents()
    assert not np.allclose(vb.viewRange(), before), "control: the wheel zoomed"
    f.undo()   # closes the still-open burst first, then undoes it whole
    assert len(f.undo_stack) == n
    assert np.allclose(vb.viewRange(), before)
    f.close()


def test_a_plain_click_pushes_no_view_entry():
    f, vb = _ramp_figure()
    f.show()
    app.processEvents()
    n = len(f.undo_stack)
    pt = vb.sceneBoundingRect().center()
    _mouse(f, QtCore.QEvent.MouseButtonPress, pt, QtCore.Qt.LeftButton)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, pt, QtCore.Qt.NoButton)
    app.processEvents()
    assert len(f.undo_stack) == n
    f.close()


def test_zoom_right_drag_shows_the_zoom_drag_cursor_only_during_the_drag():
    f, vb = _ramp_figure()
    f.show()
    app.processEvents()
    f.zoom_action.trigger()
    R = QtCore.Qt.RightButton
    a = vb.sceneBoundingRect().center()
    _mouse(f, QtCore.QEvent.MouseButtonPress, a, R, button=R)
    time.sleep(0.012)
    _mouse(f, QtCore.QEvent.MouseMove, a + QtCore.QPointF(30, -20), R, button=QtCore.Qt.NoButton)
    over = QtWidgets.QApplication.overrideCursor()
    assert over is not None and over.shape() == QtCore.Qt.BitmapCursor
    _mouse(f, QtCore.QEvent.MouseButtonRelease, a + QtCore.QPointF(30, -20), QtCore.Qt.NoButton, button=R)
    assert QtWidgets.QApplication.overrideCursor() is None
    for w in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(w, QtWidgets.QMenu):
            w.close()
    f.close()
