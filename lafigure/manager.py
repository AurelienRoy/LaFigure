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
      * a plain left-click on any row sets its figure's FOCUS: a subplot
        row focuses itself, a curve/annotation row focuses its parent
        subplot, a figure row raises and tracks that figure (Round 4,
        R4-TREE -- see _on_tree_item_clicked). Focus only -- it never
        touches selected_plots/selected_curves/selected_annotations.
  - "Curve Browser" (self.curve_tree / self.curve_browser_label, plus
    self.curve_editor below the tree): filled in by WP-K2 (Phase 2b),
    restructured by WP-P5 (Round 2). Shows the focused subplot's
    Series/Group/AnnotationItem hierarchy of the most recently active
    LaFigure window (its own small "most recently used figure" tracker --
    self._curve_recent/_curve_focus -- reimplementing the same idea as
    axes.py's gcf()/_touch locally, since manager.py doesn't own axes.py;
    kept in sync not just by registry.focusChanged but also by an
    app-wide mouse-press watcher -- see eventFilter's own docstring for
    the real, reproducible staleness that alone fixes), under two fixed
    top-level rows, **"Curves"** and **"Annotations"** (a group nests
    under whichever one its members belong to -- see _curve_rebuild_tree).
    Every row, category rows included, has a tristate visibility checkbox
    (view state, not undoable): checking/unchecking a category sets every
    descendant; checking one child while its category is still unchecked
    re-checks the category, both directions falling out of the same
    "recompute from real state on every rebuild" rule Group.visible
    already used (see _curve_category_item). A right-click Delete /
    "Edit common label..." menu, two-way selection sync with the actual
    figure, and a bottom property editor (name, Z order, color, line
    width/style, marker, alpha, and -- for a Group row -- the common
    label's prefix/suffix position). Kept in its own clearly-prefixed
    (`_curve_*`) section below, deliberately independent of the Figure
    Browser tab's own code above it, per PLAN.md's package note for K2.

Only the figure and subplot rows are made editable here -- a curve or
annotation row's own rename already has a dedicated, richer UI inside the
figure itself (right-click "Rename Curve"; annotations have no rename at
all yet), so this pass doesn't duplicate that in the tree.
"""
import weakref
from contextlib import contextmanager

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from .figure import LaFigure
from .registry import get_registry
from .annotations import AnnotationItem, SHAPE_LABELS
from .series import Series
from .groups import Group, _ungroup_one
from .curve_style import (CurveStyleMixin, line_options_apply, marker_options_apply,
                          LINE_STYLES, MARKERS, pen_style_of)


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
        # One manager per process, reachable from any figure ("Reorder
        # Curves...", LaFigure.open_curve_browser).
        self.registry.manager = self
        # Keep our own open LaFigure instances alive -- nothing else
        # holds a strong reference to a figure created here once its local
        # variable goes out of scope.
        self._owned_figures = []

        tb = QtWidgets.QToolBar("Figures")
        self.addToolBar(tb)
        new_fig_action = QtGui.QAction("New Figure", self)
        new_fig_action.setToolTip("Open a new, empty figure window")
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
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        browser_layout.addWidget(self.tree)

        # -- Curve Browser tab (WP-K2) -------------------------------------
        curve_widget = QtWidgets.QWidget()
        curve_layout = QtWidgets.QVBoxLayout(curve_widget)
        curve_layout.setContentsMargins(4, 4, 4, 4)
        self.curve_browser_label = QtWidgets.QLabel("Select a subplot to see its curves")
        curve_layout.addWidget(self.curve_browser_label)
        self.curve_tree = QtWidgets.QTreeWidget()
        self.curve_tree.setHeaderLabels(["Curve / Annotation"])
        self.curve_tree.itemChanged.connect(self._on_curve_item_changed)
        self.curve_tree.itemClicked.connect(self._on_curve_tree_item_clicked)
        self.curve_tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.curve_tree.customContextMenuRequested.connect(self._on_curve_tree_context_menu)
        curve_layout.addWidget(self.curve_tree)
        curve_layout.addWidget(self._build_curve_editor())

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(browser_widget, "Figure Browser")
        self.tabs.addTab(curve_widget, "Curve Browser")
        self.setCentralWidget(self.tabs)

        self._figure_items = {}    # LaFigure -> top-level QTreeWidgetItem
        self._fig_plot_rows = {}   # LaFigure -> {PlotItem: QTreeWidgetItem}
        self._focused = (None, None)  # last (LaFigure, PlotItem) from focusChanged

        # -- Curve Browser tab's own "most recently active figure" tracker
        # (see module docstring): weak refs so a closed figure is never
        # kept alive just because it was once looked at.
        self._curve_recent = []      # [weakref(LaFigure)], most recent last
        self._curve_focus = {}       # LaFigure -> PlotItem or None
        self._curve_current_fig = None
        self._curve_current_plot = None
        self._curve_editor_target = (None, None)   # ('series'|'group'|'annotation', obj)
        self._curve_editor_updating = False         # guard while populating editor widgets

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
        self._curve_show_editor(None, None)

        # App-wide mouse watcher for the Curve Browser's recency tracker --
        # see eventFilter's own docstring for why registry.focusChanged
        # alone isn't enough. Installed last, once every attribute
        # eventFilter reads (self._figure_items) already exists.
        self._app = QtWidgets.QApplication.instance()
        if self._app is not None:
            self._app.installEventFilter(self)

    def closeEvent(self, event):
        if self._app is not None:
            self._app.removeEventFilter(self)
        super().closeEvent(event)

    def eventFilter(self, obj, event):
        """App-wide filter (installed on the QApplication itself, not on
        any one figure): catches a real mouse press landing anywhere
        inside a tracked LaFigure window, independent of whatever
        downstream state change -- or lack of one -- it causes.

        Bug this fixes: the Curve Browser tab's "most recently active
        figure" tracker (_curve_touch, called from _on_focus_changed) only
        ever ran off registry.focusChanged, which fires only when a
        figure's OWN focused_plot actually changes value (see
        selection_ui.py's property setter -- a frozen WP-01 interface,
        not this package's to alter). So: focus figure A's subplot, focus
        figure B's subplot (tracker now points at B), then click BACK on
        figure A's subplot again -- since that subplot was already A's own
        focused_plot, the setter's guard suppresses focusChanged entirely,
        and the tracker is never told A is relevant again, leaving the
        tree stuck showing B's curves while the user is back in A. A
        plain mouse press, by contrast, is unconditional: it happens
        whether or not anything the press causes downstream actually
        changes. Confirmed live (not assumed) that a real QMouseEvent sent
        the way tests/helpers._mouse sends one reaches here with the
        correct obj.window() -- see this package's test file.

        Never consumes the event (always returns False)."""
        if event.type() == QtCore.QEvent.MouseButtonPress and isinstance(obj, QtWidgets.QWidget):
            window = obj.window()
            if window in self._figure_items:
                self._curve_touch(window, window.focused_plot)
        return False

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
        # Curve Browser tab: drop it from the recency tracker too, and
        # re-target if it was the one currently shown.
        self._curve_focus.pop(fig, None)
        self._curve_recent[:] = [r for r in self._curve_recent if r() is not None and r() is not fig]
        if self._curve_current_fig is fig:
            self._curve_refresh_target()

    def _on_subplots_changed(self, fig):
        self._refresh_subplots(fig)
        if fig is self._curve_current_fig:
            self._curve_rebuild_tree()

    def _on_selection_changed(self, fig):
        self._apply_selection_colors(fig)
        if fig is self._curve_current_fig:
            self._curve_apply_selection_colors()

    def _on_figure_renamed(self, fig):
        item = self._figure_items.get(fig)
        if item is not None:
            with _no_item_signals(self.tree):
                item.setText(0, fig.windowTitle())
        if fig is self._curve_current_fig:
            self._curve_update_label()

    def _on_focus_changed(self, fig, plot_item):
        """Curve Browser tab: tracks the focused subplot of the most
        recently active figure (see module docstring) and rebuilds
        self.curve_tree from it."""
        self._focused = (fig, plot_item)
        self._curve_touch(fig, plot_item)

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

    def _on_tree_item_clicked(self, item, column):
        """A plain left-click on any Figure Browser row makes the clicked
        row's own subplot the FOCUS of its figure -- CLAUDE.md roadmap
        item "Figure-browser tree: clicking a row changes that figure's
        focused subplot." A subplot row focuses itself; a curve/annotation
        row focuses its parent subplot (via _curve_owner, the same helper
        _node_paste already uses to find a curve's own subplot -- no
        second lookup path); a figure row has no single subplot to focus,
        so it instead becomes the "tracked" figure -- raised the same way
        a double-click already raises any row's figure, plus fed through
        _curve_touch, the same call the app-wide mouse-press eventFilter
        makes for a real click inside a figure window (see that method's
        own docstring), so the Curve Browser tab's "most recently active
        figure" doesn't go stale just because this click didn't happen to
        land inside a LaFigure window itself.

        Deliberately does NOT touch selected_plots/selected_curves/
        selected_annotations -- CLAUDE.md is explicit that widening what
        the multi-select reaches is its own product decision, not an
        incidental one, and the roadmap item asked for focus only. Goes
        through the one frozen `focused_plot` property (its setter,
        selection_ui.py, is the sole place registry.focusChanged fires) --
        never a second, parallel focus-setting path."""
        fig = item.data(0, QtCore.Qt.UserRole)
        if fig is None:
            return
        kind = item.data(0, self.ROLE_KIND)
        obj = item.data(0, self.ROLE_OBJ)

        if kind == 'figure':
            fig.show()
            fig.raise_()
            fig.activateWindow()
            self._curve_touch(fig, fig.focused_plot)
            return

        if kind == 'plot':
            plot_item = obj
        elif kind == 'curve':
            plot_item = self._curve_owner(fig, obj)
        elif kind == 'annotation':
            plot_item = obj.parent_plot
        else:
            plot_item = None

        if plot_item is not None:
            fig.focused_plot = plot_item

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

    # =====================================================================
    # Curve Browser tab (WP-K2) -- kept deliberately separate from the
    # Figure Browser tab's code above (PLAN.md's package note): every
    # method/attribute here is prefixed `_curve_`/`curve_`, and none of the
    # Figure Browser tab's own methods are touched.
    #
    # Rows: 'series' (a Series), 'group' (a Group, recursing into its own
    # members) or 'annotation' (an AnnotationItem not already inside a
    # group) -- see _curve_rebuild_tree. Reuses the module-level
    # ROLE_KIND/ROLE_OBJ data roles (their numeric value only, not shared
    # state -- self.curve_tree's items are unrelated Qt objects from
    # self.tree's).
    # =====================================================================

    # -- "most recently active figure" tracking (see module docstring) ----
    def _curve_touch(self, fig, plot_item):
        if fig is not None:
            self._curve_focus[fig] = plot_item
            self._curve_recent[:] = [r for r in self._curve_recent
                                     if r() is not None and r() is not fig]
            self._curve_recent.append(weakref.ref(fig))
        self._curve_refresh_target()

    def _curve_refresh_target(self):
        fig = None
        for ref in reversed(self._curve_recent):
            f = ref()
            if f is not None and f in self.registry.figures:
                fig = f
                break
        plot_item = self._curve_focus.get(fig) if fig is not None else None
        if fig is None or plot_item not in fig.plots:
            plot_item = None
        self._curve_current_fig = fig
        self._curve_current_plot = plot_item
        self._curve_update_label()
        self._curve_rebuild_tree()

    def _curve_update_label(self):
        fig, plot_item = self._curve_current_fig, self._curve_current_plot
        if fig is None or plot_item is None:
            self.curve_browser_label.setText("Select a subplot to see its curves")
        else:
            name = fig.subplot_name(plot_item) or "(untitled subplot)"
            self.curve_browser_label.setText(f"{fig.windowTitle()} — {name}")

    # -- tree construction --------------------------------------------------
    def _curve_rebuild_tree(self):
        """Two fixed top-level rows, 'Curves' and 'Annotations' (each its
        own checkbox), always present once a subplot is focused -- even if
        one side is empty -- so the split is visible structure, not
        something that only shows up once there's content for it."""
        fig, plot_item = self._curve_current_fig, self._curve_current_plot
        with _no_item_signals(self.curve_tree):
            self.curve_tree.clear()
            if fig is not None and plot_item is not None and plot_item in fig.plots:
                top_groups = [g for g in fig.groups if g.subplot is plot_item]
                grouped = set()
                for g in top_groups:
                    grouped.update(g.leaf_members)

                curve_rows = []        # [(kind, obj, QTreeWidgetItem)]
                annotation_rows = []
                for s in fig._series_on(plot_item):
                    if s not in grouped:
                        curve_rows.append(('series', s, self._curve_series_row(s)))
                for g in top_groups:
                    row = self._curve_group_row(g)
                    # A group with at least one Series leaf goes under
                    # Curves, else under Annotations -- groups.py's
                    # group_selection allows mixing both kinds in one
                    # group (Ctrl+G on a curve+annotation selection), and
                    # there is no third category to split a mixed group
                    # across, so "has any curve" wins the tie.
                    bucket = (curve_rows if any(isinstance(m, Series) for m in g.leaf_members)
                              else annotation_rows)
                    bucket.append(('group', g, row))
                for a in fig._annotations_on(plot_item):
                    if a not in grouped:
                        annotation_rows.append(('annotation', a, self._curve_annotation_row(a)))

                self.curve_tree.addTopLevelItem(self._curve_category_item('Curves', curve_rows))
                self.curve_tree.addTopLevelItem(self._curve_category_item('Annotations', annotation_rows))
            self.curve_tree.expandAll()
        self._curve_apply_selection_colors()
        self._curve_validate_editor_target()

    def _curve_category_item(self, label, rows):
        """One of the two fixed top-level rows, holding `rows` (already-
        built (kind, obj, child_item) triples) as its children. Its own
        checkbox is a tristate aggregate of those children's REAL, current
        visibility -- recomputed fresh on every rebuild, never bookkept as
        a separate flag, the same "recompute from reality" approach
        Group.visible already uses (groups.py). That is what makes the
        two-way propagation this package adds fall out for free: every
        checkbox edit defers a full rebuild (see _on_curve_item_changed),
        and this method re-derives the category's own state from whatever
        the edit actually changed, whether that was one of its direct
        children or a leaf nested inside one of its groups."""
        item = QtWidgets.QTreeWidgetItem([label])
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setData(0, self.ROLE_KIND, 'category')
        item.setData(0, self.ROLE_OBJ, label)
        for kind, obj, child in rows:
            item.addChild(child)
        values = [self._curve_row_value(kind, obj) for kind, obj, _ in rows]
        item.setCheckState(0, self._tri_checkstate(self._curve_aggregate(values)))
        return item

    @staticmethod
    def _curve_row_value(kind, obj):
        """True/False/None (tristate) -- Group.visible's own convention --
        for whichever kind of row this is, used to fold a row into its
        category's aggregate checkbox state."""
        if kind == 'group':
            return obj.visible
        if kind == 'annotation':
            return obj.isVisible()
        if kind == 'series':
            return obj.item.isVisible()
        return True

    @staticmethod
    def _curve_aggregate(values):
        """True if every value is True, False if every value is False
        (including "no values"), else None (a mix -- which also covers any
        value that is itself None, i.e. an already-mixed nested group)."""
        if not values:
            return False
        if all(v is True for v in values):
            return True
        if all(v is False for v in values):
            return False
        return None

    @staticmethod
    def _tri_checkstate(value):
        if value is True:
            return QtCore.Qt.Checked
        if value is False:
            return QtCore.Qt.Unchecked
        return QtCore.Qt.PartiallyChecked

    def _curve_series_row(self, series, group=None):
        text = group.display_name(series) if group is not None else (series.name or "(curve)")
        item = QtWidgets.QTreeWidgetItem([text])
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(0, QtCore.Qt.Checked if series.item.isVisible() else QtCore.Qt.Unchecked)
        item.setData(0, self.ROLE_KIND, 'series')
        item.setData(0, self.ROLE_OBJ, series)
        return item

    def _curve_annotation_row(self, ann, group=None):
        own = ann.text or SHAPE_LABELS.get(ann.kind, ann.kind)
        text = group.display_name(ann) if group is not None else own
        item = QtWidgets.QTreeWidgetItem([text])
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(0, QtCore.Qt.Checked if ann.isVisible() else QtCore.Qt.Unchecked)
        item.setData(0, self.ROLE_KIND, 'annotation')
        item.setData(0, self.ROLE_OBJ, ann)
        return item

    def _curve_group_row(self, group):
        item = QtWidgets.QTreeWidgetItem([group.common_label or "(group)"])
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(0, self._curve_group_check_state(group))
        item.setData(0, self.ROLE_KIND, 'group')
        item.setData(0, self.ROLE_OBJ, group)
        for m in group.members:
            if isinstance(m, Group):
                child = self._curve_group_row(m)
            elif isinstance(m, AnnotationItem):
                child = self._curve_annotation_row(m, group=group)
            else:
                child = self._curve_series_row(m, group=group)
            item.addChild(child)
        return item

    @staticmethod
    def _curve_group_check_state(group):
        return FigureManager._tri_checkstate(group.visible)

    # -- visibility checkboxes: view state, never undoable -------------------
    def _on_curve_item_changed(self, item, column):
        kind = item.data(0, self.ROLE_KIND)
        obj = item.data(0, self.ROLE_OBJ)
        if kind is None or obj is None:
            return
        if kind == 'category':
            # Downward only -- the upward direction (a child re-checking
            # its still-unchecked category) needs no code of its own: the
            # deferred rebuild below recomputes the category's checkbox
            # from its children's real state regardless of which row was
            # actually edited (see _curve_category_item).
            value = item.checkState(0) == QtCore.Qt.Checked
            for i in range(item.childCount()):
                self._curve_set_child_visible(item.child(i), value)
        elif kind == 'group':
            obj.set_visible(item.checkState(0) == QtCore.Qt.Checked)
        elif kind == 'series':
            obj.item.setVisible(item.checkState(0) == QtCore.Qt.Checked)
        elif kind == 'annotation':
            obj.setVisible(item.checkState(0) == QtCore.Qt.Checked)
        # Deferred, not called directly: a real click on the checkbox fires
        # itemChanged (this handler) *before* the same click's own
        # itemClicked -- rebuilding the tree here, synchronously, deletes
        # `item` out from under that still-pending itemClicked delivery, so
        # Qt hands it a null item (AttributeError: 'NoneType' has no
        # attribute 'data' in _on_curve_tree_item_clicked). Rebuilding on
        # the next event-loop turn lets both signals for this click finish
        # first.
        QtCore.QTimer.singleShot(0, self._curve_rebuild_tree)

    def _curve_set_child_visible(self, item, value):
        """Apply `value` to one direct child of a category row -- used by
        the category checkbox's downward propagation. A 'group' child
        applies through Group.set_visible (which already reaches every one
        of its own leaves, nested or not) rather than recursing into its
        Qt children here too."""
        kind = item.data(0, self.ROLE_KIND)
        obj = item.data(0, self.ROLE_OBJ)
        if kind == 'group':
            obj.set_visible(value)
        elif kind == 'series':
            obj.item.setVisible(value)
        elif kind == 'annotation':
            obj.setVisible(value)

    # -- selection sync: tree click -> figure --------------------------------
    def _on_curve_tree_item_clicked(self, item, column):
        fig, plot_item = self._curve_current_fig, self._curve_current_plot
        if fig is None or plot_item is None or item is None:
            return
        kind = item.data(0, self.ROLE_KIND)
        obj = item.data(0, self.ROLE_OBJ)
        if kind == 'category':
            # Nothing to select for the two fixed category rows themselves
            # -- just drop whatever the editor was showing.
            self._curve_show_editor(None, None)
            return
        curves, anns = [], []
        if kind == 'series':
            curves = [obj.item]
        elif kind == 'annotation':
            anns = [obj]
        elif kind == 'group':
            for leaf in obj.leaf_members:
                (curves if isinstance(leaf, Series) else anns).append(
                    leaf.item if isinstance(leaf, Series) else leaf)
        targets = [('c', c) for c in curves] + [('a', a) for a in anns]
        if not targets:
            fig._clear_selection()
        else:
            first = True
            for t_kind, t_obj in targets:
                if t_kind == 'c':
                    fig._select_curve(t_obj, additive=not first)
                else:
                    fig._select_annotation(t_obj, additive=not first)
                first = False
        fig.focused_plot = plot_item
        fig._mark_active(plot_item, keep_selection=True)
        self._curve_show_editor(kind, obj)

    # -- selection sync: figure -> tree (background color, like WP-D's blue
    # rows -- NOT the tree's own native selection, so this never feeds back
    # into _on_curve_tree_item_clicked) -------------------------------------
    def _curve_apply_selection_colors(self):
        fig = self._curve_current_fig
        if fig is None:
            return
        selected_curves = set(getattr(fig, 'selected_curves', []))
        selected_anns = set(getattr(fig, 'selected_annotations', []))

        def hit(kind, obj):
            if kind == 'series':
                return obj.item in selected_curves
            if kind == 'annotation':
                return obj in selected_anns
            if kind == 'group':
                return any((isinstance(leaf, Series) and leaf.item in selected_curves)
                           or (not isinstance(leaf, Series) and leaf in selected_anns)
                           for leaf in obj.leaf_members)
            return False

        def paint(item):
            kind = item.data(0, self.ROLE_KIND)
            obj = item.data(0, self.ROLE_OBJ)
            brush = QtGui.QBrush(self.SELECTED_BG) if hit(kind, obj) else QtGui.QBrush()
            item.setBackground(0, brush)
            for i in range(item.childCount()):
                paint(item.child(i))

        with _no_item_signals(self.curve_tree):
            for i in range(self.curve_tree.topLevelItemCount()):
                paint(self.curve_tree.topLevelItem(i))

    # -- right-click menu: Delete / Edit common label... ---------------------
    def _on_curve_tree_context_menu(self, pos):
        item = self.curve_tree.itemAt(pos)
        fig = self._curve_current_fig
        if item is None or fig is None:
            return
        kind = item.data(0, self.ROLE_KIND)
        obj = item.data(0, self.ROLE_OBJ)
        if kind == 'category':
            return  # the two fixed rows have nothing to delete/label

        menu = QtWidgets.QMenu(self.curve_tree)
        delete_action = menu.addAction("Delete")
        label_action = menu.addAction("Edit common label...") if kind == 'group' else None

        chosen = menu.exec_(self.curve_tree.viewport().mapToGlobal(pos))
        if chosen is delete_action:
            self._curve_delete_node(fig, kind, obj)
        elif chosen is not None and chosen is label_action:
            self._curve_edit_common_label(fig, obj)

    def _curve_delete_node(self, fig, kind, obj):
        if kind == 'series':
            fig.delete_curve(obj.item)
        elif kind == 'annotation':
            fig.delete_annotation(obj)
        elif kind == 'group':
            self._curve_delete_group(fig, obj)
        self._curve_rebuild_tree()

    def _curve_delete_group(self, fig, group):
        """Delete a whole group: every leaf member (curve/annotation), plus
        the group entry itself, as one undo entry -- reuses groups.py's own
        _ungroup_one (the same helper Ctrl+Shift+G uses) for the bookkeeping
        half, targeting this specific group directly rather than whatever
        happens to be selected."""
        leaves = list(group.leaf_members)
        with fig.undo_group():
            for leaf in leaves:
                if isinstance(leaf, Series):
                    fig.delete_curve(leaf.item)
                else:
                    fig.delete_annotation(leaf)
            _ungroup_one(fig, group)

    def _curve_edit_common_label(self, fig, group):
        text, ok = QtWidgets.QInputDialog.getText(
            self, "Edit common label", "Label:", QtWidgets.QLineEdit.Normal, group.common_label)
        if not ok:
            return
        old = group.common_label

        def apply(label):
            group.common_label = label

        apply(text)
        fig._push_history(lambda: apply(old), lambda: apply(text))
        self._curve_rebuild_tree()

    # -- bottom property editor ----------------------------------------------
    def _build_curve_editor(self):
        """Controls for whatever is selected in self.curve_tree -- rebuilt
        (shown/hidden per row, not recreated) on every _curve_show_editor
        call. Kept as one QGroupBox so FigureManager.__init__ can just
        addWidget() it once."""
        box = QtWidgets.QGroupBox("Properties")
        form = QtWidgets.QFormLayout(box)

        self.curve_name_edit = QtWidgets.QLineEdit()
        self.curve_name_edit.editingFinished.connect(self._on_curve_name_edited)
        form.addRow("Name", self.curve_name_edit)

        self._curve_z_row = QtWidgets.QWidget()
        z_layout = QtWidgets.QHBoxLayout(self._curve_z_row)
        z_layout.setContentsMargins(0, 0, 0, 0)
        self.curve_z_up = QtWidgets.QToolButton(text="Up")
        self.curve_z_down = QtWidgets.QToolButton(text="Down")
        self.curve_z_front = QtWidgets.QToolButton(text="Front")
        self.curve_z_back = QtWidgets.QToolButton(text="Back")
        for b in (self.curve_z_up, self.curve_z_down, self.curve_z_front, self.curve_z_back):
            z_layout.addWidget(b)
        self.curve_z_up.clicked.connect(lambda: self._curve_move_z(+1))
        self.curve_z_down.clicked.connect(lambda: self._curve_move_z(-1))
        self.curve_z_front.clicked.connect(lambda: self._curve_z_extreme(True))
        self.curve_z_back.clicked.connect(lambda: self._curve_z_extreme(False))
        form.addRow("Z order", self._curve_z_row)

        self.curve_color_button = QtWidgets.QPushButton("Choose...")
        self.curve_color_button.clicked.connect(self._on_curve_color_clicked)
        form.addRow("Color", self.curve_color_button)

        self.curve_width_spin = QtWidgets.QDoubleSpinBox()
        self.curve_width_spin.setRange(0.5, 20.0)
        self.curve_width_spin.setSingleStep(0.5)
        self.curve_width_spin.editingFinished.connect(self._on_curve_width_edited)
        form.addRow("Line width", self.curve_width_spin)

        # Item data is the MATLAB code (curve_style.LINE_STYLES) -- the same
        # table the curve menu uses, so every style it can set (including
        # "None", missing from this combo until now) round-trips correctly.
        self.curve_style_combo = QtWidgets.QComboBox()
        for label, code, _ in LINE_STYLES:
            self.curve_style_combo.addItem(label, code)
        self.curve_style_combo.currentIndexChanged.connect(self._on_curve_style_edited)
        form.addRow("Line style", self.curve_style_combo)

        # Item data is the pyqtgraph symbol (curve_style.MARKERS' own 3rd
        # column; 'none' stands in for None, since QComboBox can't
        # distinguish "no data set" from "data is None"), so this offers
        # every marker the curve menu can set, not a hardcoded subset.
        self.curve_marker_combo = QtWidgets.QComboBox()
        for label, code, symbol in MARKERS:
            self.curve_marker_combo.addItem(label, symbol if symbol is not None else 'none')
        self.curve_marker_combo.currentIndexChanged.connect(self._on_curve_marker_edited)
        form.addRow("Marker", self.curve_marker_combo)

        self.curve_alpha_spin = QtWidgets.QSpinBox()
        self.curve_alpha_spin.setRange(0, 255)
        self.curve_alpha_spin.editingFinished.connect(self._on_curve_alpha_edited)
        form.addRow("Alpha", self.curve_alpha_spin)

        self.curve_label_pos_combo = QtWidgets.QComboBox()
        self.curve_label_pos_combo.addItems(["Beginning", "End"])
        self.curve_label_pos_combo.currentIndexChanged.connect(self._on_curve_label_pos_edited)
        form.addRow("Common label position", self.curve_label_pos_combo)

        self.curve_editor = box
        return box

    def _curve_editor_rows(self):
        return (self.curve_name_edit, self._curve_z_row, self.curve_color_button,
                self.curve_width_spin, self.curve_style_combo, self.curve_marker_combo,
                self.curve_alpha_spin, self.curve_label_pos_combo)

    def _curve_set_row_visible(self, widget, visible):
        label = self.curve_editor.layout().labelForField(widget)
        widget.setVisible(visible)
        if label is not None:
            label.setVisible(visible)

    def _curve_validate_editor_target(self):
        """After a rebuild (a delete, a focus change...), drop the editor's
        target if it no longer exists -- e.g. it was just deleted."""
        kind, obj = self._curve_editor_target
        if kind is None:
            return
        fig, plot_item = self._curve_current_fig, self._curve_current_plot
        valid = False
        if fig is not None and plot_item is not None:
            if kind == 'series':
                valid = obj in fig._series_on(plot_item)
            elif kind == 'annotation':
                valid = obj in fig.annotations
            elif kind == 'group':
                valid = obj in fig.groups or any(obj in g.leaf_members for g in fig.groups)
        if not valid:
            self._curve_show_editor(None, None)

    def _curve_show_editor(self, kind, obj):
        """Populate the bottom editor for `obj` (a Series/Group/
        AnnotationItem) of the given kind, hiding whatever control doesn't
        apply -- e.g. no marker control for a plain 'line' series, no line
        width for an annotation or a group."""
        self._curve_editor_target = (kind, obj)
        self._curve_editor_updating = True
        try:
            if kind is None:
                for w in self._curve_editor_rows():
                    self._curve_set_row_visible(w, False)
                return

            series = obj if kind == 'series' else None
            opts = None
            if series is not None and hasattr(series.item, 'opts'):
                # The real style, not the selection highlight (curve_style.py).
                opts = CurveStyleMixin._curve_style_state(series.item)

            self._curve_set_row_visible(self.curve_name_edit, kind == 'series')
            if kind == 'series':
                self.curve_name_edit.setText(series.name or '')

            self._curve_set_row_visible(self._curve_z_row, kind == 'series')

            has_color = kind == 'series' and opts is not None and (
                opts.get('pen') is not None or opts.get('symbolBrush') is not None
                or opts.get('symbolPen') is not None)
            self._curve_set_row_visible(self.curve_color_button, has_color)
            self._curve_set_row_visible(self.curve_alpha_spin, has_color)
            if has_color:
                self.curve_alpha_spin.setValue(self._curve_series_color(series).alpha())

            is_line = kind == 'series' and line_options_apply(series.kind) and opts is not None
            self._curve_set_row_visible(self.curve_width_spin, is_line)
            self._curve_set_row_visible(self.curve_style_combo, is_line)
            if is_line:
                pen = pg.mkPen(opts.get('pen')) if opts.get('pen') is not None else pg.mkPen('k')
                self.curve_width_spin.setValue(pen.widthF() or 1.0)
                # pen_style_of (curve_style.py) is the one place that already
                # knows NoPen/alpha-0 both mean 'none' -- reuse it instead of
                # a local QPen-style table that couldn't represent 'none' at
                # all (CLAUDE.md-class readback bug: a style the curve menu
                # can set that this combo couldn't show).
                code = pen_style_of(opts.get('pen'))
                idx = self.curve_style_combo.findData(code)
                self.curve_style_combo.setCurrentIndex(idx if idx >= 0 else 0)

            # PlotDataItem.opts always has a 'symbol' key (default None) even
            # for kinds that can't draw one -- gate on the kind itself, the
            # same rule as the curve right-click menu (curve_style.py).
            supports_marker = (kind == 'series' and opts is not None
                               and marker_options_apply(series.kind))
            self._curve_set_row_visible(self.curve_marker_combo, supports_marker)
            if supports_marker:
                sym = opts.get('symbol')
                idx = self.curve_marker_combo.findData(sym if sym is not None else 'none')
                self.curve_marker_combo.setCurrentIndex(idx if idx >= 0 else 0)

            self._curve_set_row_visible(self.curve_label_pos_combo, kind == 'group')
            if kind == 'group':
                self.curve_label_pos_combo.setCurrentIndex(0 if obj.label_position == 'prefix' else 1)
        finally:
            self._curve_editor_updating = False

    @staticmethod
    def _curve_series_color(series):
        """The series' own "real" color: its line pen if it actually draws
        one (a plain line), else its symbol brush/pen (a scatter's own line
        pen is fully transparent by construction -- see kinds/scatter.py)."""
        opts = CurveStyleMixin._curve_style_state(series.item)
        pen = opts.get('pen')
        if pen is not None:
            c = pg.mkPen(pen).color()
            if c.alpha() > 0:
                return c
        brush = opts.get('symbolBrush')
        if brush is not None:
            return pg.mkBrush(brush).color()
        symbol_pen = opts.get('symbolPen')
        if symbol_pen is not None:
            return pg.mkPen(symbol_pen).color()
        return QtGui.QColor('black')

    def _curve_recolor(self, fig, series, rgba):
        """Apply `rgba` to whatever the item draws (line and/or markers),
        undoably, through the figure's highlight-aware style path
        (curve_style.py). Shared by the color picker and the alpha spinbox."""
        fig.set_curve_color([series.item], rgba)

    def _on_curve_name_edited(self):
        if self._curve_editor_updating:
            return
        kind, obj = self._curve_editor_target
        if kind != 'series':
            return
        fig, plot_item = self._curve_current_fig, self._curve_current_plot
        new_name = self.curve_name_edit.text()
        old_name = obj.name or ''
        if new_name == old_name:
            return

        def apply(name):
            fig._apply_curve_rename(plot_item, obj.item, name)

        apply(new_name)
        fig._push_history(lambda: apply(old_name), lambda: apply(new_name))
        self._curve_rebuild_tree()

    def _on_curve_color_clicked(self):
        kind, obj = self._curve_editor_target
        if kind != 'series':
            return
        fig = self._curve_current_fig
        current = self._curve_series_color(obj)
        # ShowAlphaChannel alone isn't enough on Windows: QColorDialog
        # still prefers the OS-native picker, which has no alpha control at
        # all (COLORREF has no alpha channel) and silently discards it --
        # DontUseNativeDialog forces Qt's own cross-platform dialog, the
        # only one that actually honors ShowAlphaChannel.
        color = QtWidgets.QColorDialog.getColor(
            current, self, "Choose color",
            QtWidgets.QColorDialog.ShowAlphaChannel | QtWidgets.QColorDialog.DontUseNativeDialog)
        if not color.isValid():
            return
        self._curve_recolor(fig, obj, (color.red(), color.green(), color.blue(), color.alpha()))
        self._curve_show_editor('series', obj)

    def _on_curve_width_edited(self):
        if self._curve_editor_updating:
            return
        kind, obj = self._curve_editor_target
        if kind != 'series':
            return
        self._curve_current_fig.set_curve_line_width([obj.item], self.curve_width_spin.value())

    def _on_curve_style_edited(self, index):
        if self._curve_editor_updating:
            return
        kind, obj = self._curve_editor_target
        if kind != 'series':
            return
        code = self.curve_style_combo.itemData(index)
        self._curve_current_fig.set_curve_line_style([obj.item], code)

    def _on_curve_marker_edited(self, index):
        if self._curve_editor_updating:
            return
        kind, obj = self._curve_editor_target
        if kind != 'series':
            return
        symbol = self.curve_marker_combo.itemData(index)
        self._curve_current_fig.set_curve_marker([obj.item], None if symbol == 'none' else symbol)

    def _on_curve_alpha_edited(self):
        if self._curve_editor_updating:
            return
        kind, obj = self._curve_editor_target
        if kind != 'series':
            return
        fig = self._curve_current_fig
        current = self._curve_series_color(obj)
        new_alpha = self.curve_alpha_spin.value()
        if new_alpha == current.alpha():
            return
        self._curve_recolor(fig, obj, (current.red(), current.green(), current.blue(), new_alpha))

    def _on_curve_label_pos_edited(self, index):
        if self._curve_editor_updating:
            return
        kind, obj = self._curve_editor_target
        if kind != 'group':
            return
        fig = self._curve_current_fig
        old_pos = obj.label_position
        new_pos = 'prefix' if index == 0 else 'suffix'
        if old_pos == new_pos:
            return

        def apply(pos):
            obj.label_position = pos

        apply(new_pos)
        fig._push_history(lambda: apply(old_pos), lambda: apply(new_pos))
        self._curve_rebuild_tree()

    # -- Z order (setZValue on the Series' own item -- confirmed live to
    # reorder actual draw stacking, see this package's report) -------------
    def _curve_ordered_series(self, plot_item):
        fig = self._curve_current_fig
        series_list = fig._series_on(plot_item)
        return sorted(series_list, key=lambda s: (s.item.zValue(), series_list.index(s)))

    def _curve_set_z(self, fig, series, old_z, new_z):
        def apply(z):
            series.item.setZValue(z)

        apply(new_z)
        fig._push_history(lambda: apply(old_z), lambda: apply(new_z))

    def _curve_move_z(self, delta):
        kind, obj = self._curve_editor_target
        if kind != 'series':
            return
        fig, plot_item = self._curve_current_fig, self._curve_current_plot
        ordered = self._curve_ordered_series(plot_item)
        idx = ordered.index(obj)
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(ordered):
            return
        other = ordered[new_idx]
        z1, z2 = obj.item.zValue(), other.item.zValue()
        if z1 == z2:
            z2 = z1 + (1 if delta > 0 else -1)
        with fig.undo_group():
            self._curve_set_z(fig, obj, z1, z2)
            self._curve_set_z(fig, other, z2, z1)

    def _curve_z_extreme(self, front):
        kind, obj = self._curve_editor_target
        if kind != 'series':
            return
        self._curve_current_fig.curves_to_front([obj.item], front)

    # -- "Reorder Curves..." (a subplot's right-click menu) -----------------
    def show_curve_browser(self, fig, plot_item):
        """Raise this window on the Curve Browser tab, showing plot_item."""
        self.tabs.setCurrentIndex(1)
        self._curve_touch(fig, plot_item)
        self.show()
        self.raise_()
        self.activateWindow()

    def show_figure_browser(self):
        """Raise this window on the Figure Browser tab (the toolbar's
        Figure Manager button)."""
        self.tabs.setCurrentIndex(0)
        self.show()
        self.raise_()
        self.activateWindow()
