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

"""R4-STYLE: the annotation menu's Line Style/Line Width/Color.../Fill.../
Arrow Style... entries (replacing the old single "Properties..." dialog
chain), arrow_style.ArrowStyleDialog, and the curve menu's area-kind
Surface Color/Surface Opacity entries -- see PLAN.md round 4.

Menu-content/gating tests call the menu-building methods directly
(_curve_context_menu, AnnotationItem.contextMenuEvent with QMenu.exec_
stubbed) -- the same convention tests/test_menus.py already uses for
curve-menu gating, since what's being tested is the menu's CONTENT, not
Qt's own click-dispatch routing (already covered elsewhere, e.g. bug #21's
regression tests)."""
import os
import tempfile

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

import lafigure as m
import lafigure.annotation_ops as annotation_ops
from lafigure.arrow_style import ArrowStyleDialog, default_head_style
from tests.helpers import app, _two_annotation_figure, _place, _click_annotation, SHIFT


# -- local helpers (small, deliberate duplication of tests/test_menus.py's
# own -- see CLAUDE.md's DBG3 lesson: independent test files each keeping
# a tiny helper beats a shared file neither package owns) ------------------
def _texts(menu):
    return [a.text() for a in menu.actions()]


def _submenu_titles(menu):
    return [a.menu().title() for a in menu.actions() if a.menu() is not None]


def _submenu(menu, title):
    return next(a.menu() for a in menu.actions() if a.menu() is not None and a.menu().title() == title)


class _FakeCtxEvent:
    def __init__(self, pos=QtCore.QPoint(0, 0)):
        self._pos = pos

    def screenPos(self):
        return self._pos

    def accept(self):
        pass


def _annotation_menu(ann):
    """Build (not show) ann's right-click menu -- QMenu.exec_ stubbed so
    nothing blocks, same technique tests/helpers._right_click_menu uses
    for a real click; here called directly since menu CONTENT doesn't
    depend on Qt's click-dispatch routing."""
    shown = []
    real_exec = QtWidgets.QMenu.exec_
    QtWidgets.QMenu.exec_ = lambda self, *a, **k: shown.append(self)
    try:
        ann.contextMenuEvent(_FakeCtxEvent())
    finally:
        QtWidgets.QMenu.exec_ = real_exec
    return shown[-1]


def _ini_settings(directory):
    """A QSettings backed by a private file, so these tests never touch
    the real user registry/config file -- same pattern test_export.py's
    own _ini_settings uses."""
    return QtCore.QSettings(os.path.join(directory, 'settings.ini'), QtCore.QSettings.IniFormat)


def _curve_figure(kind='line', **kwargs):
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0, title="T")
    x = np.arange(10.0)
    y = np.arange(10.0) ** 2
    plot_fn = ax.plot if kind == 'line' else getattr(ax, kind)
    s = plot_fn(x, y, **kwargs)
    return f, ax.plot_item, s.item


# -- annotation menu: Properties... replaced by individual entries ---------
def test_annotation_menu_has_no_properties_and_lists_the_new_entries():
    f, curve, rect, ellipse = _two_annotation_figure()
    menu = _annotation_menu(rect)
    texts = _texts(menu)
    assert "Properties..." not in texts
    assert "Color..." in texts and "Fill..." in texts
    assert _submenu_titles(menu)[:2] == ["Line Style", "Line Width"]
    assert "Arrow Style..." not in texts, "rect has no arrowhead"
    f.close()


def test_arrow_family_gets_arrow_style_non_arrow_kinds_do_not():
    f, curve, rect, ellipse = _two_annotation_figure()
    arrow = _place(f, 'arrow', f.plots[0])
    assert "Arrow Style..." in _texts(_annotation_menu(arrow))
    assert "Arrow Style..." not in _texts(_annotation_menu(rect))
    assert "Arrow Style..." not in _texts(_annotation_menu(ellipse))
    f.close()


def test_fill_entry_present_only_for_rect_and_ellipse():
    f, curve, rect, ellipse = _two_annotation_figure()
    line = _place(f, 'line', f.plots[1], QtCore.QPointF(60, 60))
    assert "Fill..." in _texts(_annotation_menu(rect))
    assert "Fill..." in _texts(_annotation_menu(ellipse))
    assert "Fill..." not in _texts(_annotation_menu(line))
    f.close()


def test_text_kind_has_line_style_and_width_disabled_color_stays_enabled():
    f, curve, rect, ellipse = _two_annotation_figure()
    text_ann = f._create_annotation('text', 'figure', None, QtCore.QPointF(80, 80), None, text="hi")
    menu = _annotation_menu(text_ann)
    assert not _submenu(menu, "Line Style").isEnabled()
    assert not _submenu(menu, "Line Width").isEnabled()
    color_action = next(a for a in menu.actions() if a.text() == "Color...")
    assert color_action.isEnabled()
    f.close()


# -- the new setters: undoable, apply to the whole selection ---------------
def test_annotation_line_style_width_color_apply_to_selection_as_one_undo():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    targets = [rect, ellipse]
    n = len(f.undo_stack)
    f.set_annotation_line_style(targets, '--')
    f.set_annotation_line_width(targets, 5.0)
    f.set_annotation_color(targets, (10, 20, 30))
    assert len(f.undo_stack) == n + 3
    for a in targets:
        assert a.pen.style() == QtCore.Qt.DashLine
        assert a.pen.widthF() == 5.0
        assert a.pen.color().getRgb()[:3] == (10, 20, 30)
    f.undo()
    f.undo()
    f.undo()
    assert rect.pen.color().getRgb()[:3] != (10, 20, 30)
    f.close()


def test_annotation_fill_only_touches_rect_and_ellipse_selected():
    f, curve, rect, ellipse = _two_annotation_figure()
    line = _place(f, 'line', f.plots[1], QtCore.QPointF(60, 60))
    old_line_brush = line.brush
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    _click_annotation(f, line, modifiers=SHIFT)
    targets = [rect, ellipse, line]
    brush = QtGui.QBrush(QtGui.QColor(0, 0, 255, 60))
    n = len(f.undo_stack)
    f.set_annotation_fill(targets, brush)
    assert len(f.undo_stack) == n + 1
    assert rect.brush.color() == QtGui.QColor(0, 0, 255, 60)
    assert ellipse.brush.color() == QtGui.QColor(0, 0, 255, 60)
    assert line.brush is old_line_brush
    f.undo()
    assert rect.brush is None and ellipse.brush is None
    f.close()


def test_annotation_line_style_none_then_back_stays_selectable_and_recolors():
    f, curve, rect, ellipse = _two_annotation_figure()
    f.set_annotation_line_style([rect], 'none')
    assert rect.pen.color().alpha() == 0
    f.set_annotation_line_style([rect], '-.')
    assert rect.pen.style() == QtCore.Qt.DashDotLine and rect.pen.color().alpha() == 255
    f.close()


# -- Arrow Style... dialog --------------------------------------------------
def test_arrow_style_dialog_live_update_then_commit_is_one_undo():
    f, curve, rect, ellipse = _two_annotation_figure()
    arrow = _place(f, 'arrow', f.plots[0])
    opened = (arrow.head_length, arrow.head_width, arrow.head_type)
    dlg = f.open_arrow_style_dialog(arrow)
    assert dlg is not None
    n = len(f.undo_stack)
    dlg.length_slider.setValue(25)
    dlg.width_slider.setValue(18)
    dlg.type_buttons['round'].setChecked(True)
    # Live-applied immediately, no undo entry yet (mirrors TransformDialog).
    assert (arrow.head_length, arrow.head_width, arrow.head_type) == (25, 18, 'round')
    assert len(f.undo_stack) == n
    dlg.accept()
    assert len(f.undo_stack) == n + 1
    f.undo()
    assert (arrow.head_length, arrow.head_width, arrow.head_type) == opened
    f.redo()
    assert (arrow.head_length, arrow.head_width, arrow.head_type) == (25, 18, 'round')
    f.close()


def test_arrow_style_dialog_cancel_restores_opened_with():
    f, curve, rect, ellipse = _two_annotation_figure()
    arrow = _place(f, 'arrow', f.plots[0])
    opened = (arrow.head_length, arrow.head_width, arrow.head_type)
    dlg = f.open_arrow_style_dialog(arrow)
    n = len(f.undo_stack)
    dlg.length_slider.setValue(30)
    dlg.type_buttons['diamond'].setChecked(True)
    assert (arrow.head_length, arrow.head_type) != (opened[0], opened[2])
    dlg.reject()
    assert (arrow.head_length, arrow.head_width, arrow.head_type) == opened
    assert len(f.undo_stack) == n, "Cancel pushes no undo entry"
    f.close()


def test_arrow_style_dialog_reset_goes_to_fixed_defaults():
    f, curve, rect, ellipse = _two_annotation_figure()
    arrow = _place(f, 'arrow', f.plots[0])
    dlg = f.open_arrow_style_dialog(arrow)
    dlg.length_slider.setValue(30)
    dlg.type_buttons['round'].setChecked(True)
    dlg.reset()
    assert arrow.head_type == 'arrow'
    assert abs(arrow.head_length - 10) < 1 and abs(arrow.head_width - 8.7) < 1
    dlg.accept()
    f.close()


def test_multi_target_arrow_style_is_one_undo_entry():
    f, curve, rect, ellipse = _two_annotation_figure()
    arrow = _place(f, 'arrow', f.plots[0])
    double = _place(f, 'doublearrow', f.plots[1], QtCore.QPointF(60, 60))
    _click_annotation(f, arrow)
    _click_annotation(f, double, modifiers=SHIFT)
    dlg = f.open_arrow_style_dialog(arrow)
    assert set(dlg.targets) == {arrow, double}
    n = len(f.undo_stack)
    dlg.length_slider.setValue(20)
    dlg.accept()
    assert len(f.undo_stack) == n + 1
    assert arrow.head_length == 20 and double.head_length == 20
    f.undo()
    assert arrow.head_length != 20 and double.head_length != 20
    f.close()


def test_arrow_style_values_survive_copy_paste():
    f, curve, rect, ellipse = _two_annotation_figure()
    arrow = _place(f, 'arrow', f.plots[0])
    f.set_arrow_style([arrow], 24.0, 16.0, 'diamond', {arrow: (arrow.head_length, arrow.head_width, arrow.head_type)})
    f._select_annotation(arrow)
    f.copy_annotation()
    f.focused_plot = f.plots[0]
    f.paste_annotation()
    pasted = f.annotations[-1]
    assert pasted is not arrow
    assert (pasted.head_length, pasted.head_width, pasted.head_type) == (24.0, 16.0, 'diamond')
    f.close()


def test_arrow_style_persists_to_settings_and_is_read_back():
    with tempfile.TemporaryDirectory() as tmp:
        settings = _ini_settings(tmp)
        f, curve, rect, ellipse = _two_annotation_figure()
        arrow = _place(f, 'arrow', f.plots[0])
        dlg = ArrowStyleDialog(f, [arrow], settings=settings)
        dlg.length_slider.setValue(19)
        dlg.width_slider.setValue(13)
        dlg.type_buttons['round'].setChecked(True)
        dlg.accept()
        settings.sync()
        length, width, head_type = default_head_style(settings=_ini_settings(tmp))
        assert (length, width, head_type) == (19.0, 13.0, 'round')
        f.close()


def test_new_arrow_annotation_seeds_from_the_persisted_default():
    original = annotation_ops.default_head_style
    annotation_ops.default_head_style = lambda: (22.0, 14.0, 'diamond')
    try:
        f, curve, rect, ellipse = _two_annotation_figure()
        arrow = _place(f, 'arrow', f.plots[0])
        assert (arrow.head_length, arrow.head_width, arrow.head_type) == (22.0, 14.0, 'diamond')
        # An already-existing annotation's own style is untouched by the
        # preference -- it's per-instance state, not re-derived.
        assert (rect.head_length, rect.head_width, rect.head_type) == (
            rect.ARROWHEAD_PX, rect.DEFAULT_HEAD_WIDTH_PX, rect.DEFAULT_HEAD_TYPE)
        f.close()
    finally:
        annotation_ops.default_head_style = original


def test_arrowhead_polygon_points_none_type_is_empty_and_others_are_not():
    from lafigure.annotations import arrowhead_polygon_points
    tip, tail = QtCore.QPointF(100, 0), QtCore.QPointF(0, 0)
    assert arrowhead_polygon_points(tip, tail, 10, 8, 'none') == []
    for head_type in ('arrow', 'round', 'diamond'):
        pts = arrowhead_polygon_points(tip, tail, 10, 8, head_type)
        assert len(pts) >= 3, head_type
        # every point is at or behind the tip along the shaft direction
        assert all(p.x() <= tip.x() + 1e-6 for p in pts), head_type


# -- area-kind curve menu: Surface Color / Surface Opacity -----------------
def test_area_curve_menu_has_surface_entries_line_curve_does_not():
    f, p, area_item = _curve_figure('area')
    menu = f._curve_context_menu(p, area_item)
    assert "Surface Color..." in _texts(menu)
    assert "Surface Opacity" in _submenu_titles(menu)
    f.close()

    f2, p2, line_item = _curve_figure('line')
    menu2 = f2._curve_context_menu(p2, line_item)
    assert "Surface Color..." not in _texts(menu2)
    assert "Surface Opacity" not in _submenu_titles(menu2)
    f2.close()


def test_surface_color_and_opacity_apply_and_are_undoable():
    f, p, area_item = _curve_figure('area')
    n = len(f.undo_stack)
    f.set_curve_fill_color([area_item], (10, 20, 30))
    assert pg.mkBrush(area_item.opts['fillBrush']).color().getRgb()[:3] == (10, 20, 30)
    f.set_curve_fill_opacity([area_item], 50)
    assert abs(pg.mkBrush(area_item.opts['fillBrush']).color().alpha() - 127) <= 1
    assert len(f.undo_stack) == n + 2
    f.undo()
    f.undo()
    assert pg.mkBrush(area_item.opts['fillBrush']).color().getRgb()[:3] != (10, 20, 30)
    f.close()


def test_surface_opacity_survives_copy_paste():
    f, p, area_item = _curve_figure('area')
    f.set_curve_fill_opacity([area_item], 25)
    alpha_before = pg.mkBrush(area_item.opts['fillBrush']).color().alpha()
    f._select_curve(area_item)
    f.copy_curve()
    f.focused_plot = p
    f.paste_curve()
    pasted = p.listDataItems()[-1]
    assert pasted is not area_item
    assert pg.mkBrush(pasted.opts['fillBrush']).color().alpha() == alpha_before
    f.close()


def test_has_fill_is_gated_on_the_items_own_fillbrush_not_a_kind_list():
    from lafigure.curve_style import has_fill
    f, p, area_item = _curve_figure('area')
    f2, p2, line_item = _curve_figure('line')
    assert has_fill(area_item)
    assert not has_fill(line_item)
    f.close()
    f2.close()
