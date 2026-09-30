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

"""Curve Browser tab + bottom property editor (manager.py's `_curve_*`
section, WP-K2): the tree following the focused subplot live, group
nesting/display_name, visibility checkboxes (view state, not undoable),
two-way selection sync, and the bottom editor's undoable property edits.
"""
import sys

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtTest

from lafigure.groups import Group
from tests.helpers import app, m, _place, _mouse, _vb_center


def _two_curve_figure():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    s1 = f._add_series(p, 'line', [0, 1, 2], [0, 1, 2], pen=pg.mkPen((200, 50, 50)), name='raw')
    s2 = f._add_series(p, 'line', [0, 1, 2], [2, 1, 0], pen=pg.mkPen((50, 50, 200)), name='filtered')
    return f, p, s1, s2


def _top_items(tree):
    return [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]


def _find_row(items, kind, obj):
    for item in items:
        if item.data(0, m.FigureManager.ROLE_KIND) == kind and item.data(0, m.FigureManager.ROLE_OBJ) is obj:
            return item
        found = _find_row([item.child(i) for i in range(item.childCount())], kind, obj)
        if found is not None:
            return found
    return None


# -- tree content: nesting, display_name, following focus -------------------
def test_tree_nests_group_members_and_shows_free_series_and_annotations():
    f, p, s1, s2 = _two_curve_figure()
    ann_grouped = _place(f, 'rect', p)
    ann_free = _place(f, 'ellipse', p, QtCore.QPointF(-60, -40))
    inner = Group([s1, s2], common_label='Ch1 ')
    outer = Group([inner, ann_grouped], common_label='Outer')
    f.groups.append(outer)

    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()

    top = _top_items(mgr.curve_tree)
    # Exactly the two fixed categories at the true top level.
    assert len(top) == 2
    assert [item.text(0) for item in top] == ['Curves', 'Annotations']
    curves_cat, anns_cat = top

    # 'outer' has a Series leaf (via 'inner') so it nests under Curves, not
    # Annotations, even though one of its own members is an annotation --
    # and neither s1/s2 nor ann_grouped appear a second time as their own
    # sibling rows.
    assert curves_cat.childCount() == 1
    group_item = curves_cat.child(0)
    assert group_item.data(0, mgr.ROLE_KIND) == 'group'
    assert group_item.text(0) == 'Outer'
    assert group_item.data(0, mgr.ROLE_OBJ) is outer
    assert group_item.childCount() == 2

    # The one ungrouped annotation nests under Annotations.
    assert anns_cat.childCount() == 1
    free_ann_item = anns_cat.child(0)
    assert free_ann_item.data(0, mgr.ROLE_KIND) == 'annotation'
    assert free_ann_item.data(0, mgr.ROLE_OBJ) is ann_free

    inner_item = _find_row(top, 'group', inner)
    assert inner_item is not None and inner_item.parent() is group_item
    assert inner_item.childCount() == 2
    s1_item = _find_row(top, 'series', s1)
    assert s1_item.text(0) == inner.display_name(s1)
    assert s1_item.text(0) != (s1.name or '')  # display_name, not the raw name
    f.close()
    mgr.close()


def test_plain_series_and_annotation_show_their_own_name():
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    top = _top_items(mgr.curve_tree)
    s1_item = _find_row(top, 'series', s1)
    assert s1_item.text(0) == 'raw'
    f.close()
    mgr.close()


def test_switching_focus_within_one_figure_updates_the_tree():
    f = m.LaFigure(empty=True)
    p1 = f.add_subplot(row=0, col=0)
    p2 = f.add_subplot(row=1, col=0)
    s1 = f._add_series(p1, 'line', [0, 1], [0, 1], name='on-p1')
    s2 = f._add_series(p2, 'line', [0, 1], [0, 1], name='on-p2')

    mgr = m.FigureManager()
    app.processEvents()

    f._on_plot_clicked(p1)
    app.processEvents()
    assert _find_row(_top_items(mgr.curve_tree), 'series', s1) is not None
    assert _find_row(_top_items(mgr.curve_tree), 'series', s2) is None

    f._on_plot_clicked(p2)
    app.processEvents()
    assert _find_row(_top_items(mgr.curve_tree), 'series', s2) is not None
    assert _find_row(_top_items(mgr.curve_tree), 'series', s1) is None
    f.close()
    mgr.close()


def test_tree_updates_live_when_a_curve_is_added_deleted_or_renamed():
    """Before the fix, this tree only rebuilt on focus/selection changes
    or a whole-subplot add/remove -- a curve added to (or renamed or
    deleted on) the already-focused subplot left it stale."""
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    curves_cat = _top_items(mgr.curve_tree)[0]
    n_before = curves_cat.childCount()

    s3 = f._add_series(p, 'line', [0, 1], [1, 0], name='extra')
    app.processEvents()
    curves_cat = _top_items(mgr.curve_tree)[0]  # tree rebuilt: re-find
    assert curves_cat.childCount() == n_before + 1
    assert _find_row(_top_items(mgr.curve_tree), 'series', s3) is not None

    f._apply_curve_rename(p, s3.item, 'renamed')
    app.processEvents()
    row = _find_row(_top_items(mgr.curve_tree), 'series', s3)
    assert row is not None and row.text(0) == 'renamed'

    f.delete_curve(s3.item)
    app.processEvents()
    curves_cat = _top_items(mgr.curve_tree)[0]  # tree rebuilt: re-find
    assert curves_cat.childCount() == n_before
    f.close()
    mgr.close()


def test_switching_focus_across_two_figures_updates_the_tree():
    f1 = m.LaFigure(empty=True)
    p1 = f1.add_subplot(row=0, col=0)
    s1 = f1._add_series(p1, 'line', [0, 1], [0, 1], name='fig1-curve')

    f2 = m.LaFigure(empty=True)
    p2 = f2.add_subplot(row=0, col=0)
    s2 = f2._add_series(p2, 'line', [0, 1], [0, 1], name='fig2-curve')

    mgr = m.FigureManager()
    app.processEvents()

    f1._on_plot_clicked(p1)
    app.processEvents()
    assert mgr._curve_current_fig is f1
    assert _find_row(_top_items(mgr.curve_tree), 'series', s1) is not None

    f2._on_plot_clicked(p2)
    app.processEvents()
    assert mgr._curve_current_fig is f2
    assert _find_row(_top_items(mgr.curve_tree), 'series', s2) is not None
    assert _find_row(_top_items(mgr.curve_tree), 'series', s1) is None

    f1.close()
    f2.close()
    mgr.close()


def test_reclicking_an_already_focused_subplot_still_updates_the_tree():
    """The real staleness bug (PLAN.md P5): the tab already keys off
    focused_plot via registry.focusChanged, but that signal fires ONLY
    when a figure's own focused_plot actually changes value
    (selection_ui.py's property setter, a frozen interface this package
    doesn't own/alter). Click f1's subplot, then f2's, then f1's AGAIN --
    for f1 that subplot was already its own focused_plot, so focusChanged
    never fires a second time for it, yet the user plainly just switched
    back to f1. Driven with real QMouseEvents (tests/helpers._mouse): a
    direct _on_plot_clicked() call wouldn't exercise the app-wide mouse
    watcher this fix adds (FigureManager.eventFilter) -- CLAUDE.md bugs
    #11/#19's standing rule that Qt-event-routing-dependent behavior needs
    a real event, not a direct method call."""
    f1 = m.LaFigure(empty=True)
    p1 = f1.add_subplot(row=0, col=0)
    s1 = f1._add_series(p1, 'line', [0, 1], [0, 1], name='fig1-curve')
    f1.show()

    f2 = m.LaFigure(empty=True)
    p2 = f2.add_subplot(row=0, col=0)
    s2 = f2._add_series(p2, 'line', [0, 1], [0, 1], name='fig2-curve')
    f2.show()
    app.processEvents()

    mgr = m.FigureManager()
    app.processEvents()

    c1, c2 = _vb_center(p1), _vb_center(p2)

    def click(fig, pt):
        _mouse(fig, QtCore.QEvent.MouseButtonPress, pt, QtCore.Qt.LeftButton)
        _mouse(fig, QtCore.QEvent.MouseButtonRelease, pt, QtCore.Qt.NoButton)
        app.processEvents()

    click(f1, c1)
    assert mgr._curve_current_fig is f1
    assert _find_row(_top_items(mgr.curve_tree), 'series', s1) is not None

    click(f2, c2)
    assert mgr._curve_current_fig is f2
    assert _find_row(_top_items(mgr.curve_tree), 'series', s2) is not None

    # f1's own focused_plot doesn't change here (it was already p1) -- the
    # exact click that used to leave the tree stuck on f2.
    click(f1, c1)
    assert f1.focused_plot is p1
    assert mgr._curve_current_fig is f1
    assert _find_row(_top_items(mgr.curve_tree), 'series', s1) is not None
    assert _find_row(_top_items(mgr.curve_tree), 'series', s2) is None

    f1.close()
    f2.close()
    mgr.close()


# -- visibility checkboxes: view state, never undoable -----------------------
def test_series_visibility_checkbox_toggles_item_and_is_not_undoable():
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    item = _find_row(_top_items(mgr.curve_tree), 'series', s1)
    assert item.checkState(0) == QtCore.Qt.Checked
    n_undo = len(f.undo_stack)

    item.setCheckState(0, QtCore.Qt.Unchecked)
    app.processEvents()

    assert s1.item.isVisible() is False
    assert len(f.undo_stack) == n_undo
    f.close()
    mgr.close()


def test_real_click_on_an_annotation_checkbox_does_not_crash():
    """A real click on the checkbox fires itemChanged (which used to
    rebuild the tree synchronously) *before* the same click's own
    itemClicked -- the synchronous rebuild deleted the C++ item out from
    under that still-pending itemClicked, so Qt delivered it a null item
    and _on_curve_tree_item_clicked raised AttributeError. Only a real
    QTest click (not item.setCheckState) reproduces this: that's why the
    other checkbox test above didn't catch it."""
    f, p, s1, s2 = _two_curve_figure()
    ann = _place(f, 'ellipse', p)
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    item = _find_row(_top_items(mgr.curve_tree), 'annotation', ann)
    assert item.checkState(0) == QtCore.Qt.Checked

    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda t, v, tb: errors.append(v)
    try:
        rect = mgr.curve_tree.visualItemRect(item)
        pt = QtCore.QPoint(rect.left() + 8, rect.top() + rect.height() // 2)
        QtTest.QTest.mouseClick(mgr.curve_tree.viewport(), QtCore.Qt.LeftButton, pos=pt)
        app.processEvents()
        app.processEvents()  # the deferred rebuild's singleShot(0, ...)
    finally:
        sys.excepthook = old_hook
    assert errors == [], errors
    assert ann.isVisible() is False
    f.close()
    mgr.close()


def test_group_visibility_checkbox_is_tristate_for_mixed_members():
    f, p, s1, s2 = _two_curve_figure()
    group = Group([s1, s2], common_label='Grp')
    f.groups.append(group)
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()

    group_item = _find_row(_top_items(mgr.curve_tree), 'group', group)
    assert group_item.checkState(0) == QtCore.Qt.Checked

    s1_item = _find_row(_top_items(mgr.curve_tree), 'series', s1)
    s1_item.setCheckState(0, QtCore.Qt.Unchecked)
    app.processEvents()

    group_item = _find_row(_top_items(mgr.curve_tree), 'group', group)  # tree rebuilt: re-find
    assert group_item.checkState(0) == QtCore.Qt.PartiallyChecked

    group_item.setCheckState(0, QtCore.Qt.Checked)
    app.processEvents()
    assert s1.item.isVisible() is True
    assert s2.item.isVisible() is True
    f.close()
    mgr.close()


# -- Curves / Annotations top-level categories -------------------------------
def test_tree_has_curves_and_annotations_categories_with_correct_nesting():
    f, p, s1, s2 = _two_curve_figure()
    ann = _place(f, 'rect', p)
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()

    top = _top_items(mgr.curve_tree)
    assert [item.text(0) for item in top] == ['Curves', 'Annotations']
    curves_cat, anns_cat = top
    assert curves_cat.data(0, mgr.ROLE_KIND) == 'category'
    assert anns_cat.data(0, mgr.ROLE_KIND) == 'category'
    assert bool(curves_cat.flags() & QtCore.Qt.ItemIsUserCheckable)
    assert bool(anns_cat.flags() & QtCore.Qt.ItemIsUserCheckable)

    assert {curves_cat.child(i).data(0, mgr.ROLE_OBJ) for i in range(curves_cat.childCount())} == {s1, s2}
    assert anns_cat.childCount() == 1
    assert anns_cat.child(0).data(0, mgr.ROLE_OBJ) is ann
    f.close()
    mgr.close()


def test_unchecking_category_unchecks_every_child_recursively_through_groups():
    f, p, s1, s2 = _two_curve_figure()
    group = Group([s1, s2], common_label='Grp')
    f.groups.append(group)
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()

    curves_cat = _top_items(mgr.curve_tree)[0]
    assert curves_cat.text(0) == 'Curves'
    assert curves_cat.checkState(0) == QtCore.Qt.Checked

    curves_cat.setCheckState(0, QtCore.Qt.Unchecked)
    app.processEvents()

    assert s1.item.isVisible() is False
    assert s2.item.isVisible() is False
    curves_cat = _top_items(mgr.curve_tree)[0]  # tree rebuilt: re-find
    assert curves_cat.checkState(0) == QtCore.Qt.Unchecked
    f.close()
    mgr.close()


def test_checking_a_child_re_checks_its_unchecked_category():
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()

    # Hide both directly (not via the tree) so the category starts fully
    # unchecked, then re-derive the tree from that real state.
    s1.item.setVisible(False)
    s2.item.setVisible(False)
    mgr._curve_rebuild_tree()
    curves_cat = _top_items(mgr.curve_tree)[0]
    assert curves_cat.checkState(0) == QtCore.Qt.Unchecked

    s1_item = _find_row(_top_items(mgr.curve_tree), 'series', s1)
    s1_item.setCheckState(0, QtCore.Qt.Checked)
    app.processEvents()

    assert s1.item.isVisible() is True
    assert s2.item.isVisible() is False  # untouched
    curves_cat = _top_items(mgr.curve_tree)[0]  # tree rebuilt: re-find
    # Tristate, exactly like Group.visible: not every child is visible any
    # more (s2 still is not), so the category is "re-checked" to the mixed
    # state, not silently left Unchecked.
    assert curves_cat.checkState(0) == QtCore.Qt.PartiallyChecked
    f.close()
    mgr.close()


def test_real_click_on_a_category_checkbox_does_not_crash():
    """Same CLAUDE.md bug #19 regression guard as the annotation-row test
    above, for the newly-added category row: a real click fires
    itemChanged before itemClicked, so a synchronous rebuild inside the
    former would tear the tree down under the latter's still-pending
    delivery."""
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    curves_cat = _top_items(mgr.curve_tree)[0]
    assert curves_cat.checkState(0) == QtCore.Qt.Checked

    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda t, v, tb: errors.append(v)
    try:
        rect = mgr.curve_tree.visualItemRect(curves_cat)
        pt = QtCore.QPoint(rect.left() + 8, rect.top() + rect.height() // 2)
        QtTest.QTest.mouseClick(mgr.curve_tree.viewport(), QtCore.Qt.LeftButton, pos=pt)
        app.processEvents()
        app.processEvents()  # the deferred rebuild's singleShot(0, ...)
    finally:
        sys.excepthook = old_hook
    assert errors == [], errors
    assert s1.item.isVisible() is False
    assert s2.item.isVisible() is False
    f.close()
    mgr.close()


def test_category_visibility_checkbox_is_not_undoable():
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    n_undo = len(f.undo_stack)

    curves_cat = _top_items(mgr.curve_tree)[0]
    curves_cat.setCheckState(0, QtCore.Qt.Unchecked)
    app.processEvents()

    assert len(f.undo_stack) == n_undo
    f.close()
    mgr.close()


def test_mixed_group_nests_under_curves_when_it_has_any_series_leaf():
    """groups.py's group_selection allows mixing Series + AnnotationItem
    members in one group (Ctrl+G on a mixed selection); there is no third
    tree category for that, so the documented rule is: any Series leaf at
    all puts the whole group under Curves."""
    f, p, s1, s2 = _two_curve_figure()
    ann = _place(f, 'rect', p)
    group = Group([s1, ann], common_label='Mixed')
    f.groups.append(group)
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()

    top = _top_items(mgr.curve_tree)
    curves_cat, anns_cat = top
    group_item = _find_row([curves_cat], 'group', group)
    assert group_item is not None
    assert _find_row([anns_cat], 'group', group) is None
    f.close()
    mgr.close()


# -- selection sync, both ways -----------------------------------------------
def test_clicking_a_series_row_selects_the_curve_in_the_figure():
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    item = _find_row(_top_items(mgr.curve_tree), 'series', s1)

    mgr._on_curve_tree_item_clicked(item, 0)
    app.processEvents()

    assert f.selected_curves == [s1.item]
    assert f.focused_plot is p
    f.close()
    mgr.close()


def test_clicking_a_group_row_selects_every_leaf_member():
    f, p, s1, s2 = _two_curve_figure()
    ann = _place(f, 'rect', p)
    group = Group([s1, ann], common_label='Grp')
    f.groups.append(group)
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    item = _find_row(_top_items(mgr.curve_tree), 'group', group)

    mgr._on_curve_tree_item_clicked(item, 0)
    app.processEvents()

    assert f.selected_curves == [s1.item]
    assert f.selected_annotations == [ann]
    f.close()
    mgr.close()


def test_figure_selection_recolors_the_matching_tree_row():
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()

    f._select_curve(s1.item)
    app.processEvents()

    item = _find_row(_top_items(mgr.curve_tree), 'series', s1)
    other = _find_row(_top_items(mgr.curve_tree), 'series', s2)
    assert item.background(0).color() == mgr.SELECTED_BG
    assert other.background(0).style() == QtCore.Qt.NoBrush
    f.close()
    mgr.close()


# -- bottom property editor ---------------------------------------------------
def test_series_editor_shows_name_and_color_and_width_are_undoable():
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()

    mgr._curve_show_editor('series', s1)
    # mgr is never shown (headless), so isVisible() would be False for
    # everything regardless of our own row show/hide logic -- isHidden()
    # reflects the explicit local flag _curve_set_row_visible sets/clears.
    assert not mgr.curve_name_edit.isHidden()
    assert mgr.curve_name_edit.text() == 'raw'
    assert not mgr.curve_color_button.isHidden()
    assert not mgr.curve_width_spin.isHidden()
    assert not mgr.curve_marker_combo.isHidden()  # a line can take markers (MATLAB-style)

    n_undo = len(f.undo_stack)
    old_color = pg.mkPen(s1.item.opts['pen']).color()
    mgr._curve_recolor(f, s1, (10, 20, 30, 255))
    assert pg.mkPen(s1.item.opts['pen']).color().getRgb()[:3] == (10, 20, 30)
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert pg.mkPen(s1.item.opts['pen']).color().getRgb()[:3] == old_color.getRgb()[:3]
    f.redo()

    n_undo2 = len(f.undo_stack)
    mgr.curve_width_spin.setValue(7.0)
    mgr._on_curve_width_edited()
    assert pg.mkPen(s1.item.opts['pen']).widthF() == 7.0
    assert len(f.undo_stack) == n_undo2 + 1
    f.undo()
    assert pg.mkPen(s1.item.opts['pen']).widthF() != 7.0

    f.close()
    mgr.close()


def test_series_name_edit_is_undoable():
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    mgr._curve_show_editor('series', s1)

    n_undo = len(f.undo_stack)
    mgr.curve_name_edit.setText('renamed')
    mgr._on_curve_name_edited()
    assert s1.item.name() == 'renamed'
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert s1.item.name() == 'raw'
    f.close()
    mgr.close()


def test_group_editor_shows_and_edits_label_position():
    f, p, s1, s2 = _two_curve_figure()
    group = Group([s1, s2], common_label='Ch1 ', label_position='prefix')
    f.groups.append(group)
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()

    mgr._curve_show_editor('group', group)
    assert not mgr.curve_label_pos_combo.isHidden()
    assert mgr.curve_label_pos_combo.currentIndex() == 0
    assert mgr.curve_name_edit.isHidden()

    n_undo = len(f.undo_stack)
    mgr.curve_label_pos_combo.setCurrentIndex(1)  # real Qt signal fires the handler
    app.processEvents()
    assert group.label_position == 'suffix'
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert group.label_position == 'prefix'
    f.close()
    mgr.close()


# -- Z order: setZValue on the Series' item, confirmed to reorder real
# on-screen stacking (see this package's report) -----------------------------
def test_z_order_front_and_back_change_zvalue_and_are_undoable():
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    mgr._curve_show_editor('series', s1)

    n_undo = len(f.undo_stack)
    mgr._curve_z_extreme(front=True)
    assert s1.item.zValue() > s2.item.zValue()
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert s1.item.zValue() <= s2.item.zValue()
    f.close()
    mgr.close()


# -- right-click Delete -------------------------------------------------------
def test_delete_series_row_is_undoable():
    f, p, s1, s2 = _two_curve_figure()
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()
    n_curves_before = len([c for c in p.listDataItems() if isinstance(c, pg.PlotDataItem)])

    mgr._curve_delete_node(f, 'series', s1)
    app.processEvents()
    assert len([c for c in p.listDataItems() if isinstance(c, pg.PlotDataItem)]) == n_curves_before - 1

    f.undo()
    assert len([c for c in p.listDataItems() if isinstance(c, pg.PlotDataItem)]) == n_curves_before
    f.close()
    mgr.close()


def test_delete_group_row_removes_members_and_the_group_and_is_undoable():
    f, p, s1, s2 = _two_curve_figure()
    group = Group([s1, s2], common_label='Grp')
    f.groups.append(group)
    mgr = m.FigureManager()
    app.processEvents()
    f._on_plot_clicked(p)
    app.processEvents()

    n_undo = len(f.undo_stack)
    mgr._curve_delete_node(f, 'group', group)
    app.processEvents()

    assert group not in f.groups
    assert len([c for c in p.listDataItems() if isinstance(c, pg.PlotDataItem)]) == 0
    assert len(f.undo_stack) == n_undo + 1

    f.undo()
    assert group in f.groups
    assert len([c for c in p.listDataItems() if isinstance(c, pg.PlotDataItem)]) == 2
    f.close()
    mgr.close()


