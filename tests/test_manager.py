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

"""FigureManager + registry: the tree tracks open figures/subplots, "New
Figure" makes a truly empty one, and the shared Clipboard carries a whole
subplot from one figure window to a separate one (all pre-existing
coverage, kept). New in this pass (Phase 2b, "figure browser" half): the
two-tab structure, editable figure/subplot nodes, live blue selection
coloring, the three curve/annotation/controls checkboxes, and the node
right-click actions.

Right-click *menus* are modal when exec'd (see test_menus.py's own note),
so -- like that file -- these drive the underlying dispatch methods
(_node_copy/_node_paste/_node_delete) directly rather than actually
popping up and clicking a QMenu.
"""
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from tests.helpers import (
    app, m, shown_figure, _place,
)


def test_figure_manager_tracks_figures_and_cross_window_paste():
    """Tree tracks figures; an empty figure has no subplot floor; a subplot
    pastes into a separate window; closing unregisters."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

    mgr = m.FigureManager()
    app.processEvents()
    assert win in mgr._figure_items
    win_item = mgr._figure_items[win]
    assert win_item.childCount() == len(win.plots)

    empty_win = mgr.new_figure()
    app.processEvents()
    assert empty_win.empty is True
    assert empty_win.plots == []
    assert empty_win in mgr._figure_items
    assert mgr._figure_items[empty_win].childCount() == 0

    # An empty figure has no floor on subplot count -- adding then deleting its
    # only subplot must be able to leave it at zero again (unlike `win`, whose
    # floor of 1 is exercised implicitly by every delete_subplot() call above).
    empty_win.add_new_subplot()
    app.processEvents()
    assert len(empty_win.plots) == 1
    assert mgr._figure_items[empty_win].childCount() == 1
    empty_win.delete_subplot(empty_win.plots[0])
    assert len(empty_win.plots) == 0

    # Copy a subplot out of `win` and paste it into the separate `empty_win`
    # window via the process-wide clipboard -- this is the cross-window path
    # that a single-window app couldn't support.
    win._on_plot_clicked(p1)
    n_curves_p1 = len([c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)])
    win.copy_subplot()
    assert win.clipboard.subplot is not None
    assert win.clipboard is empty_win.clipboard  # same process-wide singleton

    empty_win.paste_subplot()
    app.processEvents()
    assert len(empty_win.plots) == 1
    pasted = empty_win.plots[0]
    assert pasted.titleLabel.text == p1.titleLabel.text
    pasted_curves = [c for c in pasted.listDataItems() if isinstance(c, pg.PlotDataItem)]
    assert len(pasted_curves) == n_curves_p1

    empty_win.undo()
    assert len(empty_win.plots) == 0
    empty_win.redo()
    assert len(empty_win.plots) == 1

    # Closing a figure unregisters it from both the registry and the manager's
    # tree.
    empty_win.close()
    app.processEvents()
    assert empty_win not in mgr._figure_items
    win.close()
    mgr.close()


def test_central_widget_is_a_three_tab_widget():
    mgr = m.FigureManager()
    app.processEvents()
    assert isinstance(mgr.centralWidget(), QtWidgets.QTabWidget)
    assert mgr.tabs is mgr.centralWidget()
    assert mgr.tabs.count() == 3
    assert mgr.tabs.tabText(0) == "Figure Browser"
    assert mgr.tabs.tabText(1) == "Curve Browser"
    assert mgr.tabs.tabText(2) == "Variable Browser"
    # The Curve Browser tab is a structural placeholder a later package
    # (K2) can find and populate -- just assert the widgets exist.
    assert isinstance(mgr.curve_tree, QtWidgets.QTreeWidget)
    assert isinstance(mgr.curve_browser_label, QtWidgets.QLabel)
    assert isinstance(mgr.var_table, QtWidgets.QTableWidget)
    mgr.close()


def test_renaming_a_subplot_row_is_undoable_in_that_figure():
    win = shown_figure()
    mgr = m.FigureManager()
    app.processEvents()
    p1 = win.plots[0]
    row = mgr._fig_plot_rows[win][p1]
    old_name = win.subplot_name(p1)

    # Simulate the in-place edit committing -- this is exactly the code
    # path Qt's own item delegate takes (setData through EditRole), so it
    # drives the same itemChanged signal a real double-click/F2 edit would.
    row.setText(0, "Renamed Subplot")
    app.processEvents()

    assert win.subplot_name(p1) == "Renamed Subplot"
    assert p1.titleLabel.text == "Renamed Subplot"
    win.undo()
    assert win.subplot_name(p1) == old_name
    win.redo()
    assert win.subplot_name(p1) == "Renamed Subplot"
    win.close()
    mgr.close()


def test_renaming_a_figure_row_updates_the_window_title():
    win = shown_figure()
    mgr = m.FigureManager()
    app.processEvents()
    item = mgr._figure_items[win]
    old_title = win.windowTitle()

    item.setText(0, "My Renamed Figure")
    app.processEvents()

    assert win.windowTitle() == "My Renamed Figure"
    assert item.text(0) == "My Renamed Figure"
    win.undo()
    assert win.windowTitle() == old_title
    win.close()
    mgr.close()


def test_editing_a_subplot_row_does_not_get_torn_down_mid_edit():
    """Regression guard: rename_subplot's own undoable apply() fires
    subplotsChanged synchronously, which rebuilds the tree from inside
    this very itemChanged handler -- the row object must survive that
    (reused, not recreated) so nothing crashes and the dict stays coherent."""
    win = shown_figure()
    mgr = m.FigureManager()
    app.processEvents()
    p1 = win.plots[0]
    row_before = mgr._fig_plot_rows[win][p1]
    row_before.setText(0, "Still Here")
    app.processEvents()
    row_after = mgr._fig_plot_rows[win][p1]
    assert row_after is row_before
    assert row_after.text(0) == "Still Here"
    win.close()
    mgr.close()


def test_selected_subplot_rows_turn_blue_and_clear():
    win = shown_figure()
    mgr = m.FigureManager()
    app.processEvents()
    p1 = win.plots[0]
    row = mgr._fig_plot_rows[win][p1]
    # The demo figure pre-selects p1 on construction (see figure.py's
    # _build_demo_subplots) -- start from a clean slate.
    win._deselect_all()
    app.processEvents()
    assert row.background(0).style() == QtCore.Qt.NoBrush

    win._on_plot_clicked(p1)  # the real selection path (selection_ui.py)
    app.processEvents()
    assert p1 in win.selected_plots
    assert row.background(0).color() == mgr.SELECTED_BG

    win._deselect_all()
    app.processEvents()
    assert row.background(0).style() == QtCore.Qt.NoBrush
    win.close()
    mgr.close()


def test_checkboxes_toggle_curve_and_annotation_sublevels():
    win = shown_figure()
    mgr = m.FigureManager()
    app.processEvents()
    p1 = win.plots[0]
    row = mgr._fig_plot_rows[win][p1]
    assert row.childCount() == 0  # unchecked by default

    n_curves = len([c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)])
    mgr.show_curves_check.setChecked(True)
    app.processEvents()
    assert row.childCount() == n_curves
    assert all(row.child(i).data(0, mgr.ROLE_KIND) == 'curve' for i in range(row.childCount()))

    mgr.show_curves_check.setChecked(False)
    app.processEvents()
    assert row.childCount() == 0

    ann = _place(win, 'rect', p1)
    mgr.show_annotations_check.setChecked(True)
    app.processEvents()
    assert row.childCount() == 1
    assert row.child(0).data(0, mgr.ROLE_KIND) == 'annotation'
    assert row.child(0).data(0, mgr.ROLE_OBJ) is ann

    mgr.show_annotations_check.setChecked(False)
    app.processEvents()
    assert row.childCount() == 0

    # "Show GUI controls": nothing to add yet (Phase 5) -- must not crash.
    mgr.show_controls_check.setChecked(True)
    app.processEvents()
    assert row.childCount() == 0
    mgr.show_controls_check.setChecked(False)
    app.processEvents()

    win.close()
    mgr.close()


def test_curve_sublevel_updates_live_on_add_delete_rename():
    """Before the fix, adding/deleting/renaming a curve on an existing
    subplot never rebuilt this tree -- only add_subplot/delete_subplot
    fired the registry signal it rebuilds from."""
    win = shown_figure()
    mgr = m.FigureManager()
    app.processEvents()
    p1 = win.plots[0]
    row = mgr._fig_plot_rows[win][p1]
    mgr.show_curves_check.setChecked(True)
    app.processEvents()
    n_before = row.childCount()

    new_curve = win._add_series(p1, 'line', [0, 1, 2], [0, 1, 2], name='extra').item
    app.processEvents()
    assert row.childCount() == n_before + 1
    assert any(row.child(i).data(0, mgr.ROLE_OBJ) is new_curve for i in range(row.childCount()))

    win._apply_curve_rename(p1, new_curve, 'renamed')
    app.processEvents()
    renamed_row = next(row.child(i) for i in range(row.childCount())
                        if row.child(i).data(0, mgr.ROLE_OBJ) is new_curve)
    assert renamed_row.text(0) == 'renamed'

    win.delete_curve(new_curve)
    app.processEvents()
    assert row.childCount() == n_before
    win.close()
    mgr.close()


def test_node_delete_removes_a_subplot_and_is_undoable():
    win = shown_figure()
    mgr = m.FigureManager()
    app.processEvents()
    p2 = win.plots[1]
    n_before = len(win.plots)

    mgr._node_delete(win, 'plot', p2)
    app.processEvents()
    assert len(win.plots) == n_before - 1
    assert p2 not in win.plots

    win.undo()
    assert len(win.plots) == n_before
    win.close()
    mgr.close()


def test_node_copy_and_paste_a_single_subplot_targets_only_that_node():
    """Right-click Copy/Paste on one subplot row must target exactly that
    subplot regardless of what is selected inside the figure's own window
    (PLAN.md's package note) -- select a *different* plot first."""
    win = shown_figure()
    other_win = m.LaFigure(empty=True)
    other_win.show()
    app.processEvents()
    mgr = m.FigureManager()
    app.processEvents()

    p0, p1 = win.plots[0], win.plots[1]
    win._on_plot_clicked(p0)  # select a different subplot than the one we copy
    assert win.selected_plots == [p0]

    mgr._node_copy(win, 'plot', p1)
    assert win.clipboard.last_copied == 'subplot'
    assert len(win.clipboard.subplot) == 1
    assert win.clipboard.subplot[0]['title'] == p1.titleLabel.text

    mgr._node_paste(other_win, 'plot', None)
    app.processEvents()
    assert len(other_win.plots) == 1
    assert other_win.plots[0].titleLabel.text == p1.titleLabel.text

    win.close()
    other_win.close()
    mgr.close()


def test_node_delete_on_a_figure_row_closes_that_figure():
    win = shown_figure()
    mgr = m.FigureManager()
    app.processEvents()
    assert win in mgr._figure_items

    mgr._node_delete(win, 'figure', None)
    app.processEvents()
    assert win not in mgr._figure_items
    mgr.close()


def test_node_delete_curve_and_annotation():
    win = shown_figure()
    mgr = m.FigureManager()
    app.processEvents()
    p1 = win.plots[0]
    curve = [c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)][0]

    mgr._node_delete(win, 'curve', curve)
    app.processEvents()
    assert curve not in p1.listDataItems()
    win.undo()
    assert any(c.name() == curve.name() for c in p1.listDataItems()
               if isinstance(c, pg.PlotDataItem))

    ann = _place(win, 'rect', p1)
    mgr._node_delete(win, 'annotation', ann)
    app.processEvents()
    assert ann not in win.annotations
    win.undo()
    assert any(a.kind == 'rect' for a in win.annotations)

    win.close()
    mgr.close()
