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

"""FigureManager: a small persistent window listing every open LaFigure
and its subplots, plus a button to create a new, empty figure window --
this is what makes whole-subplot copy/paste between *separate* figure
windows something you can actually set up and test (see LaFigure.
copy_subplot/paste_subplot and clipboard.py).

Deliberately its own top-level window, not a dock inside a LaFigure --
it must outlive any single figure and list them all.

As of Phase 2b (CLAUDE.md), the central widget is a QTabWidget with two
tabs:
  - "Figure Browser" (self.tree): every open figure and its subplots, as
    before, plus -- new in this pass:
      * every figure/subplot node is text-editable (double-click / F2),
        renaming the figure (window title) or the subplot (its title),
        undoably, via LaFigure.rename_figure/rename_subplot.
      * rows of a figure's currently-selected subplots are colored blue,
        synced live from registry.selectionChanged.
      * a right-click menu on every node: Copy / Paste / Delete, reusing
        the figure's own clip_ops methods (same actions/undo as inside
        the figure itself -- see the module-level note below on what
        "Copy"/"Paste" mean for a whole-figure node, which has no
        existing single-shot equivalent).
      * three checkboxes (show curves / show annotations / show GUI
        controls) that add/remove read-only sub-levels under each
        subplot row. "Show GUI controls" has nothing to add yet (no
        controls exist before Phase 5) but must not crash.
  - "Curve Browser" (self.curve_tree / self.curve_browser_label): a
    structural placeholder only. It tracks registry.focusChanged just
    enough to show which subplot is focused; WP-K2 (Phase 2b) fills in
    the actual per-subplot series/annotation tree and bottom property
    editor once groups (WP-K1) exist.

Only the figure and subplot rows are made editable here -- a curve or
annotation row's own rename already has a dedicated, richer UI inside the
figure itself (right-click "Rename Curve"; annotations have no rename at
all yet), so this pass doesn't duplicate that in the tree.
"""
from contextlib import contextmanager

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from .figure import LaFigure
from .registry import get_registry


@contextmanager
def _no_item_signals(tree):
    """Guard against QTreeWidget.itemChanged firing for a programmatic
    setText/setData/setBackground -- only a real, user-driven in-place
    edit should be treated as a rename request (see _on_item_changed)."""
    tree.blockSignals(True)
    try:
        yield
    finally:
        tree.blockSignals(False)


class FigureManager(QtWidgets.QMainWindow):
    # Custom item-data roles on the Figure Browser tree, alongside the
    # existing Qt.UserRole (always the owning LaFigure, kept for
    # backward-compatible double-click raise/focus).
    ROLE_KIND = QtCore.Qt.UserRole + 1   # 'figure' | 'plot' | 'curve' | 'annotation'
    ROLE_OBJ = QtCore.Qt.UserRole + 2    # None | PlotItem | PlotDataItem | AnnotationItem

    SELECTED_BG = QtGui.QColor(200, 220, 255)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Figure Manager")
        self.resize(360, 520)

        self.registry = get_registry()
        # Keep our own open LaFigure instances alive -- nothing else
        # holds a strong reference to a figure created here once its local
        # variable goes out of scope.
        self._owned_figures = []

        tb = QtWidgets.QToolBar("Figures")
        self.addToolBar(tb)
        new_fig_action = QtGui.QAction("New Figure", self)
        new_fig_action.setToolTip("Create a new, empty figure window (no subplots) -- "
                                   "useful for testing copy/paste between figures.")
        new_fig_action.triggered.connect(self.new_figure)
        tb.addAction(new_fig_action)

        # -- Figure Browser tab -------------------------------------------
        browser_widget = QtWidgets.QWidget()
        browser_layout = QtWidgets.QVBoxLayout(browser_widget)
        browser_layout.setContentsMargins(4, 4, 4, 4)

        checks_row = QtWidgets.QHBoxLayout()
        self.show_curves_check = QtWidgets.QCheckBox("Show curves")
        self.show_annotations_check = QtWidgets.QCheckBox("Show annotations")
        self.show_controls_check = QtWidgets.QCheckBox("Show GUI controls")
        for cb in (self.show_curves_check, self.show_annotations_check, self.show_controls_check):
            cb.toggled.connect(self._refresh_all_children)
            checks_row.addWidget(cb)
        checks_row.addStretch(1)
        browser_layout.addLayout(checks_row)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Figure / Subplot"])
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        browser_layout.addWidget(self.tree)

        # -- Curve Browser tab (structural placeholder for WP-K2) ---------
        curve_widget = QtWidgets.QWidget()
        curve_layout = QtWidgets.QVBoxLayout(curve_widget)
        curve_layout.setContentsMargins(4, 4, 4, 4)
        self.curve_browser_label = QtWidgets.QLabel("Select a subplot to see its curves")
        curve_layout.addWidget(self.curve_browser_label)
        self.curve_tree = QtWidgets.QTreeWidget()
        self.curve_tree.setHeaderLabels(["Curve / Annotation"])
        curve_layout.addWidget(self.curve_tree)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(browser_widget, "Figure Browser")
        self.tabs.addTab(curve_widget, "Curve Browser")
        self.setCentralWidget(self.tabs)

        self._figure_items = {}    # LaFigure -> top-level QTreeWidgetItem
        self._fig_plot_rows = {}   # LaFigure -> {PlotItem: QTreeWidgetItem}
        self._focused = (None, None)  # last (LaFigure, PlotItem) from focusChanged

        self.registry.figureOpened.connect(self._on_figure_opened)
        self.registry.figureClosed.connect(self._on_figure_closed)
        self.registry.subplotsChanged.connect(self._on_subplots_changed)
        self.registry.selectionChanged.connect(self._on_selection_changed)
        self.registry.figureRenamed.connect(self._on_figure_renamed)
        self.registry.focusChanged.connect(self._on_focus_changed)

        # Any figures already open (e.g. the demo figure app.main() creates
        # before this manager) won't have fired figureOpened while we
        # weren't listening yet -- backfill them.
        for fig in list(self.registry.figures):
            self._add_figure_item(fig)

    def new_figure(self):
        fig = LaFigure(empty=True)
        fig.show()
        self._owned_figures.append(fig)
        return fig

    # -- tree maintenance -----------------------------------------------
    def _add_figure_item(self, fig):
        if fig in self._figure_items:
            return
        item = QtWidgets.QTreeWidgetItem()
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        item.setData(0, QtCore.Qt.UserRole, fig)
        item.setData(0, self.ROLE_KIND, 'figure')
        item.setData(0, self.ROLE_OBJ, None)
        item.setText(0, fig.windowTitle())  # not yet in the model: no itemChanged
        self.tree.addTopLevelItem(item)
        self._figure_items[fig] = item
        self._fig_plot_rows[fig] = {}
        self._refresh_subplots(fig)

    def _refresh_subplots(self, fig):
        """Rebuild `fig`'s subplot rows (and, transitively, their curve/
        annotation sub-levels) to match fig.plots, in place: existing rows
        are reused and only relabeled/reordered, so an in-progress edit of
        one row is never itself torn down by its own rename triggering
        this same refresh (see _on_item_changed)."""
        top_item = self._figure_items.get(fig)
        if top_item is None:
            return
        rows = self._fig_plot_rows.setdefault(fig, {})
        current_plots = list(fig.plots)
        with _no_item_signals(self.tree):
            top_item.setText(0, fig.windowTitle())
            for plot_item in list(rows):
                if plot_item not in current_plots:
                    row = rows.pop(plot_item)
                    idx = top_item.indexOfChild(row)
                    if idx >= 0:
                        top_item.takeChild(idx)
            for i, plot_item in enumerate(current_plots):
                row = rows.get(plot_item)
                if row is None:
                    row = QtWidgets.QTreeWidgetItem()
                    row.setFlags(row.flags() | QtCore.Qt.ItemIsEditable)
                    row.setData(0, QtCore.Qt.UserRole, fig)
                    row.setData(0, self.ROLE_KIND, 'plot')
                    row.setData(0, self.ROLE_OBJ, plot_item)
                    rows[plot_item] = row
                cur_idx = top_item.indexOfChild(row)
                if cur_idx != i:
                    if cur_idx >= 0:
                        top_item.takeChild(cur_idx)
                    top_item.insertChild(i, row)
                name = fig.subplot_name(plot_item) or "(untitled subplot)"
                if row.text(0) != name:
                    row.setText(0, name)
                self._refresh_plot_children(fig, plot_item, row)
            top_item.setExpanded(True)
        self._apply_selection_colors(fig)

    def _refresh_plot_children(self, fig, plot_item, row_item):
        """Read-only curve/annotation sub-levels under one subplot row,
        shown per the three header checkboxes. Rebuilt wholesale each time
        -- unlike the subplot rows above, these are never mid-edit, so
        there is no identity to preserve across a refresh."""
        row_item.takeChildren()
        if self.show_curves_check.isChecked():
            for c in plot_item.listDataItems():
                if isinstance(c, pg.PlotDataItem):
                    child = QtWidgets.QTreeWidgetItem([c.name() or "(curve)"])
                    child.setData(0, QtCore.Qt.UserRole, fig)
                    child.setData(0, self.ROLE_KIND, 'curve')
                    child.setData(0, self.ROLE_OBJ, c)
                    row_item.addChild(child)
        if self.show_annotations_check.isChecked():
            for a in fig.annotations:
                if a.parent_plot is plot_item:
                    child = QtWidgets.QTreeWidgetItem([a.kind])
                    child.setData(0, QtCore.Qt.UserRole, fig)
                    child.setData(0, self.ROLE_KIND, 'annotation')
                    child.setData(0, self.ROLE_OBJ, a)
                    row_item.addChild(child)
        # "Show GUI controls": no controls exist yet (Phase 5 / WP-N) --
        # nothing to add, but the checkbox must exist and toggle cleanly.
        if row_item.childCount():
            row_item.setExpanded(True)

    def _refresh_all_children(self, _checked=None):
        """A header checkbox toggled: rebuild every open figure's tree."""
        for fig in list(self._figure_items):
            self._refresh_subplots(fig)

    def _apply_selection_colors(self, fig):
        """Color a figure's selected-subplot rows blue, synced live from
        registry.selectionChanged; clear the rest."""
        rows = self._fig_plot_rows.get(fig, {})
        selected = set(getattr(fig, 'selected_plots', []))
        with _no_item_signals(self.tree):
            for plot_item, row in rows.items():
                brush = QtGui.QBrush(self.SELECTED_BG) if plot_item in selected else QtGui.QBrush()
                row.setBackground(0, brush)

    def _on_figure_opened(self, fig):
        self._add_figure_item(fig)

    def _on_figure_closed(self, fig):
        item = self._figure_items.pop(fig, None)
        self._fig_plot_rows.pop(fig, None)
        if item is not None:
            idx = self.tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self.tree.takeTopLevelItem(idx)
        if fig in self._owned_figures:
            self._owned_figures.remove(fig)

    def _on_subplots_changed(self, fig):
        self._refresh_subplots(fig)

    def _on_selection_changed(self, fig):
        self._apply_selection_colors(fig)

    def _on_figure_renamed(self, fig):
        item = self._figure_items.get(fig)
        if item is None:
            return
        with _no_item_signals(self.tree):
            item.setText(0, fig.windowTitle())

    def _on_focus_changed(self, fig, plot_item):
        """Curve Browser placeholder: tracks the focused subplot of the
        most recently active figure so WP-K2 can populate self.curve_tree
        from it later; no content logic yet, just a visible sign of life."""
        self._focused = (fig, plot_item)
        if plot_item is None:
            self.curve_browser_label.setText("Select a subplot to see its curves")
        else:
            name = fig.subplot_name(plot_item) if fig is not None else ''
            self.curve_browser_label.setText(f"Focused subplot: {name or '(untitled subplot)'}")

    def _on_item_double_clicked(self, item, column):
        """Double-clicking any row (the figure itself or one of its
        subplots/curves/annotations) raises and focuses that figure
        window. Editing is started separately, via F2 or a second,
        slower click on an already-selected item (Qt's own default
        edit trigger for an editable item) -- see setFlags above."""
        fig = item.data(0, QtCore.Qt.UserRole)
        if fig is None:
            return
        fig.show()
        fig.raise_()
        fig.activateWindow()

    def _on_item_changed(self, item, column):
        """A node's in-place edit committed (double-click / F2, then
        Enter or focus-out) -- Qt fires this once per commit, not per
        keystroke. Only figure and subplot rows are ever editable (see
        setFlags), so `kind`, not depth or parent(), decides what to
        rename; a name equal to the current one is a no-op (rename_figure/
        rename_subplot already guard that too, but checking here avoids
        pushing a redundant refresh)."""
        kind = item.data(0, self.ROLE_KIND)
        fig = item.data(0, QtCore.Qt.UserRole)
        if fig is None:
            return
        new_text = item.text(0)
        if kind == 'figure':
            if new_text != fig.windowTitle():
                fig.rename_figure(new_text)
        elif kind == 'plot':
            plot_item = item.data(0, self.ROLE_OBJ)
            if plot_item is not None and new_text != fig.subplot_name(plot_item):
                fig.rename_subplot(plot_item, new_text)

    # -- right-click menu: Copy / Paste / Delete -------------------------
    def _on_tree_context_menu(self, pos):
        """Same actions and undo as inside the figure itself, reusing its
        own clip_ops methods -- see _node_copy/_node_paste/_node_delete for
        exactly what each kind of node does, including the two cases with
        no pre-existing single-node equivalent (a whole-figure Copy/Paste)."""
        item = self.tree.itemAt(pos)
        if item is None:
            return
        fig = item.data(0, QtCore.Qt.UserRole)
        if fig is None:
            return
        kind = item.data(0, self.ROLE_KIND)
        obj = item.data(0, self.ROLE_OBJ)

        menu = QtWidgets.QMenu(self.tree)
        copy_action = menu.addAction("Copy")
        paste_action = menu.addAction("Paste")
        delete_action = menu.addAction("Delete")
        if kind == 'annotation':
            # No clipboard concept exists for a single annotation (only as
            # part of a whole subplot's copy/paste) -- don't offer actions
            # that would silently do nothing.
            copy_action.setEnabled(False)
            paste_action.setEnabled(False)

        chosen = menu.exec_(self.tree.viewport().mapToGlobal(pos))
        if chosen is copy_action:
            self._node_copy(fig, kind, obj)
        elif chosen is paste_action:
            self._node_paste(fig, kind, obj)
        elif chosen is delete_action:
            self._node_delete(fig, kind, obj)

    def _node_copy(self, fig, kind, obj):
        if kind == 'figure':
            # There is no "copy a whole figure" clipboard concept (Clipboard
            # only ever holds curves or subplots -- see clipboard.py); this
            # is deliberately mirrored as "copy every subplot in it" so
            # Paste elsewhere still does something useful. A no-op on an
            # empty figure (copy_subplot would otherwise IndexError on an
            # empty selected_plots list -- see _select_plots).
            if fig.plots:
                fig._select_plots(list(fig.plots))
                fig.copy_subplot()
        elif kind == 'plot':
            # Target exactly this subplot regardless of what's selected
            # inside the figure's own window (see PLAN.md's package note).
            fig._select_plots([obj])
            fig.copy_subplot()
        elif kind == 'curve':
            fig._select_curve(obj)
            fig.copy_curve()

    def _node_paste(self, fig, kind, obj):
        if kind in ('figure', 'plot'):
            # paste_subplot always appends new rows at the bottom of `fig`,
            # independent of any particular row clicked -- same as the
            # figure's own right-click "Paste Subplot".
            fig.paste_subplot()
        elif kind == 'curve':
            plot_item = self._curve_owner(fig, obj)
            if plot_item is not None:
                fig.focused_plot = plot_item
                fig.paste_curve()

    def _node_delete(self, fig, kind, obj):
        if kind == 'figure':
            # No "copied figure" concept exists to restore on undo, so this
            # is a plain window close, not an undoable figure-level action
            # (closing already ends that figure's own undo history too).
            fig.close()
        elif kind == 'plot':
            fig.delete_subplot(obj)
        elif kind == 'curve':
            fig.delete_curve(obj)
        elif kind == 'annotation':
            fig.delete_annotation(obj)

    @staticmethod
    def _curve_owner(fig, curve):
        for p in fig.plots:
            if curve in p.listDataItems():
                return p
        return None
