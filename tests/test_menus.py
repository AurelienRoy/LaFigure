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

"""Right-click menus (menus.py). The menus are modal when exec'd, so these
inspect the subplot menu pyqtgraph owns and emit its aboutToShow, which is
where the menu selects the subplot and rebuilds its curve submenus."""
import csv
import os
import tempfile

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

import lafigure as m
from tests.helpers import app, shown_figure, first_curve, _click_subplot, SHIFT


def _texts(menu):
    return [a.text() for a in menu.actions()]


def _submenu_titles(menu):
    return [a.menu().title() for a in menu.actions() if a.menu() is not None]


BRUSH_ACTION_LABELS = (
    "Delete Selected Points", "Transform Selected Points...",
    "Selection Stats...", "Fit Selected Points",
)


def test_subplot_menu_has_the_app_actions():
    f = shown_figure()
    texts = _texts(f.plots[0].getViewBox().menu)
    for label in ("Copy Subplot", "Paste Subplot", "Paste Curve", "Toggle Legend",
                  "Bring Subplot to Front", "Send Subplot to Back", "Reorder Curves...",
                  "Remove Average", "FFT -> Subplot Below", "Delete Selected Points",
                  "Transform Selected Points...", "Selection Stats...",
                  "Fit Selected Points", "Delete Curve", "Rename Curve"):
        assert label in texts, (label, texts)
    for label in ("Copy Curve", "Bring to Front", "Send to Back"):
        assert label not in texts, ("curve-only action in the subplot menu", label)
    f.close()


def test_subplot_menu_paste_curve_is_enabled_only_with_a_copied_curve_and_pastes_there():
    f = m.LaFigure(empty=True)
    src = f.add_subplot(row=0, col=0)
    f._add_series(src, 'line', np.arange(5.0), np.arange(5.0), name="ramp")
    empty = f.add_subplot(row=1, col=0)
    f.clipboard.curve = []
    menu = empty.getViewBox().menu
    paste = next(a for a in menu.actions() if a.text() == "Paste Curve")
    menu.aboutToShow.emit()
    assert not paste.isEnabled(), "nothing copied: Paste Curve is disabled"
    f.focused_plot = src
    f.copy_curve()
    menu.aboutToShow.emit()
    assert paste.isEnabled(), "a curve copied: Paste Curve is enabled"
    paste.trigger()
    assert [c.name() for c in empty.listDataItems()] == ["ramp"], "pasted onto the menu's subplot"
    f.undo()
    assert empty.listDataItems() == [], "one undo step"
    f.close()


def test_opening_the_menu_lists_curves_and_keeps_a_selection_involving_it():
    f = shown_figure()
    p0, p1 = f.plots[0], f.plots[1]
    menu = p0.getViewBox().menu
    submenus = {a.text(): a.menu() for a in menu.actions() if a.menu() is not None}
    _click_subplot(f, p1)
    menu.aboutToShow.emit()
    assert f.selected_plots == [p0] and f.focused_plot is p0, "right-click outside the selection selects"
    assert _texts(submenus["Delete Curve"]) == [first_curve(p0).name()]
    assert _texts(submenus["Rename Curve"]) == [first_curve(p0).name()]
    _click_subplot(f, p1, modifiers=SHIFT)
    menu.aboutToShow.emit()
    assert f.selected_plots == [p0, p1], "right-click inside the selection keeps it whole"
    f.close()


def test_pyqtgraph_export_and_axis_menus_are_removed():
    f = shown_figure()
    menu = f.plots[0].getViewBox().menu
    texts = _texts(menu)
    assert "Export..." not in texts, texts
    titles = _submenu_titles(menu)
    assert "X axis" not in titles, titles
    assert "Y axis" not in titles, titles
    assert "Mouse Mode" not in titles, titles
    # pyqtgraph's own "View All" and this app's own entries stay.
    assert "View All" in texts, texts
    assert "Export to CSV..." in texts, texts
    for label in ("Copy Subplot", "Paste Subplot", "Toggle Legend"):
        assert label in texts, (label, texts)
    f.close()


def test_export_to_csv_writes_padded_named_columns():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    p.plot(np.array([1.0, 2.0, 3.0]), np.array([10.0, 20.0, 30.0]), name="A")
    p.plot(np.array([1.0, 2.0]), np.array([5.0, 6.0]), name="B")

    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        f._export_subplot_csv(p, path)
        with open(path, newline="") as fh:
            rows = list(csv.reader(fh))
    finally:
        os.remove(path)
        f.close()

    assert rows[0] == ["A x", "A y", "B x", "B y"], rows[0]
    assert rows[1] == ["1.0", "10.0", "1.0", "5.0"], rows[1]
    assert rows[2] == ["2.0", "20.0", "2.0", "6.0"], rows[2]
    assert rows[3] == ["3.0", "30.0", "", ""], rows[3]  # B is shorter: padded with empty cells


def test_export_to_csv_falls_back_to_curve_n_when_unnamed():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    p.plot(np.array([1.0]), np.array([2.0]))

    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        f._export_subplot_csv(p, path)
        with open(path, newline="") as fh:
            rows = list(csv.reader(fh))
    finally:
        os.remove(path)
        f.close()

    assert rows[0] == ["curve 1 x", "curve 1 y"], rows[0]


def _labelled(menu):
    """Same as _brush_action_visibility's key set, but including the
    submenu's own action (its .text() is empty; its .menu().title() is
    "Fit Selected Points")."""
    out = {}
    for a in menu.actions():
        label = a.menu().title() if a.menu() is not None else a.text()
        if label in BRUSH_ACTION_LABELS:
            out[label] = (a.isVisible(), a.isEnabled())
    return out


def test_brushed_point_actions_hidden_when_brush_mode_is_off():
    f = shown_figure()
    assert not f.brushing, "control: Brush mode starts off"
    menu = f.plots[0].getViewBox().menu
    menu.aboutToShow.emit()
    vis = _labelled(menu)
    assert len(vis) == len(BRUSH_ACTION_LABELS), vis
    assert all(not visible for visible, _ in vis.values()), vis
    f.close()


def test_brushed_point_actions_visible_but_disabled_with_nothing_brushed():
    f = shown_figure()
    f.brush_action.trigger()
    assert f.brushing
    menu = f.plots[0].getViewBox().menu
    menu.aboutToShow.emit()
    vis = _labelled(menu)
    assert all(visible for visible, _ in vis.values()), vis
    assert all(not enabled for _, enabled in vis.values()), vis
    f.close()


def test_brushed_point_actions_visible_and_enabled_with_a_real_selection():
    f = shown_figure()
    f.brush_action.trigger()
    p0 = f.plots[0]
    curve = first_curve(p0)
    mask = np.zeros(len(curve.xData), dtype=bool)
    mask[:3] = True
    f._brushers[p0].set_selection({curve: mask})
    menu = p0.getViewBox().menu
    menu.aboutToShow.emit()
    vis = _labelled(menu)
    assert all(visible for visible, _ in vis.values()), vis
    assert all(enabled for _, enabled in vis.values()), vis
    f.close()


# -- headers, curve menu, Reorder Curves... ---------------------------------
class _FakeContextEvent:
    acceptedItem = None

    def __init__(self, scene_pos):
        self._pos = scene_pos

    def scenePos(self):
        return self._pos

    def screenPos(self):
        return QtCore.QPointF(10, 10)


def _curve_figure():
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0, title="Ramp")
    s = ax.plot(np.linspace(0, 100, 1001), np.linspace(0, 100, 1001), name="ramp")
    f.show()
    app.processEvents()
    vb = ax.plot_item.getViewBox()
    vb.setRange(xRange=(0, 100), yRange=(0, 100), padding=0)
    app.processEvents()
    return f, ax.plot_item, s.item


def test_subplot_menu_starts_with_a_header_naming_the_subplot():
    f, p, c = _curve_figure()
    menu = p.getViewBox().menu
    menu.aboutToShow.emit()
    first = menu.actions()[0]
    assert first.text() == "Subplot: Ramp" and not first.isEnabled()
    f.close()


def test_right_click_on_a_curve_opens_the_curve_menu_else_the_subplot_menu():
    f, p, c = _curve_figure()
    vb = p.getViewBox()
    shown = []
    real = f._curve_context_menu
    f._curve_context_menu = lambda plot_item, curve: shown.append(curve) or real(plot_item, curve)
    vb.raiseContextMenu(_FakeContextEvent(vb.mapViewToScene(QtCore.QPointF(50, 50))))
    assert shown == [c], "on the curve: the curve menu"
    assert f.selected_curves == [c], "right-click selects the curve (Select mode)"
    vb.raiseContextMenu(_FakeContextEvent(vb.mapViewToScene(QtCore.QPointF(20, 80))))
    assert shown == [c], "off the curve: pyqtgraph's subplot menu, not the curve menu"
    vb.menu.close()
    for w in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(w, QtWidgets.QMenu):
            w.close()
    f.close()


def test_curve_menu_has_curve_actions_only_and_a_header():
    f, p, c = _curve_figure()
    menu = f._curve_context_menu(p, c)
    texts = _texts(menu)
    assert texts[0] == "Curve: ramp" and not menu.actions()[0].isEnabled()
    for label in ("Copy Curve", "Paste Curve", "Bring to Front", "Send to Back",
                  "Rename Curve...", "Delete Curve"):
        assert label in texts, (label, texts)
    for label in ("Toggle Legend", "Copy Subplot", "Paste Subplot", "FFT -> Subplot Below",
                  "Export to CSV..."):
        assert label not in texts, (label, texts)
    titles = _submenu_titles(menu)
    assert titles == ["Line Style", "Line Width", "Marker", "Marker Size"], titles
    f.close()


def _curve_menu_style_entries(menu):
    """The submenu/action sequence among the six style controls, in the
    order they were added to the menu -- submenus and plain actions
    interleaved, unlike _submenu_titles/_texts which only see one kind."""
    names = []
    wanted_submenus = ("Line Style", "Line Width", "Marker", "Marker Size")
    wanted_actions = ("Line Color...", "Marker Color...")
    for a in menu.actions():
        if a.menu() is not None and a.menu().title() in wanted_submenus:
            names.append(a.menu().title())
        elif a.text() in wanted_actions:
            names.append(a.text())
    return names


def test_curve_menu_style_controls_are_in_the_required_order():
    f, p, c = _curve_figure()
    menu = f._curve_context_menu(p, c)
    assert _curve_menu_style_entries(menu) == [
        "Line Style", "Line Width", "Line Color...", "Marker", "Marker Size", "Marker Color...",
    ], _curve_menu_style_entries(menu)
    f.close()


def test_curve_menu_style_choice_applies_to_the_selection_as_one_undo():
    f, p, c = _curve_figure()
    c2 = f._add_series(p, 'line', np.arange(5.0), np.arange(5.0), name="b").item
    f._select_curve(c)
    f._select_curve(c2, additive=True)
    menu = f._curve_context_menu(p, c)
    assert _texts(menu)[0] == "Curve: ramp (+1 more)"
    widths = {a.menu().title(): a.menu() for a in menu.actions() if a.menu() is not None}["Line Width"]
    n = len(f.undo_stack)
    next(a for a in widths.actions() if a.text() == "4").trigger()
    f._deselect_curve()
    assert all(pg.mkPen(x.opts['pen']).widthF() == 4 for x in (c, c2))
    assert len(f.undo_stack) == n + 1
    f.close()


def test_curve_menu_line_and_marker_color_pick_independent_colors():
    f, p, c = _curve_figure()
    f.set_curve_marker([c], 'o')
    menu = f._curve_context_menu(p, c)
    line_color = next(a for a in menu.actions() if a.text() == "Line Color...")
    marker_color = next(a for a in menu.actions() if a.text() == "Marker Color...")
    assert line_color.isEnabled() and marker_color.isEnabled()

    real_get_color = QtWidgets.QColorDialog.getColor
    QtWidgets.QColorDialog.getColor = staticmethod(lambda *a, **k: QtGui.QColor(0, 255, 0))
    try:
        marker_color.trigger()
    finally:
        QtWidgets.QColorDialog.getColor = real_get_color
    assert pg.mkBrush(c.opts['symbolBrush']).color().getRgb()[:3] == (0, 255, 0)
    assert pg.mkPen(c.opts['pen']).color().getRgb()[:3] != (0, 255, 0), "line untouched by marker color"
    f.close()


def test_curve_menu_marker_color_disabled_without_a_marker():
    f, p, c = _curve_figure()
    menu = f._curve_context_menu(p, c)
    marker_color = next(a for a in menu.actions() if a.text() == "Marker Color...")
    assert not marker_color.isEnabled(), "no marker on this curve yet"
    f.close()


def _submenu_by_title(menu, title):
    return next(a.menu() for a in menu.actions() if a.menu() is not None and a.menu().title() == title)


def test_scatter_line_style_is_never_grayed_but_width_and_color_are_until_drawn():
    """The root bug this package fixes (see curve_style.py/menus.py): gating
    Line Style/Width/Color purely by kind string left them permanently
    grayed for 'scatter', even once it was visibly drawing a real line.
    New rule: Line Style is enabled for any line-capable kind regardless of
    whether a line is drawn right now (it's the one control that can turn
    one on); Line Width/Color stay grayed until a line actually exists."""
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0, title="Scatter")
    s = ax.scatter(np.arange(5.0), np.arange(5.0), size=6)
    c = s.item
    f.show()
    app.processEvents()

    menu = f._curve_context_menu(ax.plot_item, c)
    line_color = next(a for a in menu.actions() if a.text() == "Line Color...")
    assert _submenu_by_title(menu, "Line Style").isEnabled(), "capable of a line: never grayed"
    assert not _submenu_by_title(menu, "Line Width").isEnabled(), "no line drawn yet: grayed"
    assert not line_color.isEnabled(), "no line drawn yet: grayed"

    f.set_curve_line_style([c], '-')
    menu2 = f._curve_context_menu(ax.plot_item, c)
    line_color2 = next(a for a in menu2.actions() if a.text() == "Line Color...")
    assert _submenu_by_title(menu2, "Line Style").isEnabled()
    assert _submenu_by_title(menu2, "Line Width").isEnabled(), "a real line is now drawn: enabled"
    assert line_color2.isEnabled()
    f.close()


def test_reorder_curves_opens_the_manager_on_the_curve_tab():
    f, p, c = _curve_figure()
    mgr = f.open_curve_browser(p)
    assert mgr.tabs.currentIndex() == 1
    assert mgr._curve_current_fig is f and mgr._curve_current_plot is p
    assert f.open_curve_browser(p) is mgr, "one manager, reused"
    mgr.close()
    f.close()


def test_right_click_on_an_annotation_opens_neither_the_curve_nor_subplot_menu():
    """An AnnotationItem's own contextMenuEvent (annotations.py, a native
    Qt event) fires independently of this ViewBox-level dispatch -- before
    the fix, both it and whichever of these two also opened."""
    f, p, c = _curve_figure()
    vb = p.getViewBox()
    ann = f._create_annotation('rect', 'axes', p, QtCore.QPointF(10, 10), QtCore.QPointF(10, 10))
    ann_scene = ann.mapToScene(QtCore.QPointF(5, 5))
    shown = []
    real_curve_menu = f._curve_context_menu
    f._curve_context_menu = lambda plot_item, curve: shown.append(curve) or real_curve_menu(plot_item, curve)
    popped = []
    real_popup = vb.menu.popup
    vb.menu.popup = lambda *a, **k: popped.append(True)
    try:
        # Control: off the annotation, off the curve -- the plain subplot
        # menu still opens (proves the popup spy actually observes this).
        vb.raiseContextMenu(_FakeContextEvent(vb.mapViewToScene(QtCore.QPointF(90, 5))))
        assert popped == [True], "control: subplot menu should open here"
        popped.clear()
        # On the annotation: neither menu opens.
        vb.raiseContextMenu(_FakeContextEvent(ann_scene))
        assert shown == [], "no curve menu"
        assert popped == [], "no subplot menu -- the annotation's own contextMenuEvent handles it"
    finally:
        vb.menu.popup = real_popup
        f._curve_context_menu = real_curve_menu
    f.close()
