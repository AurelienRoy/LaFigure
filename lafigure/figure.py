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

"""LaFigure: a MATLAB-Figure-like window -- multiple subplots in a
resizable grid, click to select, drag borders/corners to resize, drag a
center handle to move/swap, curve selection, undo/redo, copy/paste curves
and whole subplots (including across separate LaFigure windows via the
shared Clipboard), FFT-to-new-subplot, linked brushing, editable
title/axis/legend text.

See CLAUDE.md for the design lessons behind this file's structure -- in
particular, why "plain add/delete a subplot" and "FFT's whole-row
shift" are kept as two genuinely different code paths.
"""
import contextlib
import os
import sys
import numpy as np
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .selection import SelectionModel, LinkedScatter, RectBrush
from .handles import ResizeHandle, MoveHandle
from .editable_text import wire_plot_labels_editable, wire_legend_editable
from .registry import get_registry
from .clipboard import get_clipboard
from .annotations import AnnotationItem, SHAPE_KINDS, SHAPE_LABELS, TWO_CLICK_KINDS

pg.setConfigOptions(antialias=False, useOpenGL=True, background='w', foreground='k')

# icons/ lives next to this package's containing directory (lafigure_poc/),
# not inside the package itself.
ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'icons'
)


class LaFigure(QtWidgets.QMainWindow):
    def __init__(self, empty=False):
        super().__init__()
        self.setWindowTitle("MATLAB-like Figure")
        self.resize(1100, 750)

        # If True, delete_subplot's "keep at least one" floor is relaxed to zero.
        self.empty = empty

        self.layout_widget = pg.GraphicsLayoutWidget()
        self.setCentralWidget(self.layout_widget)

        self.plots = []          # list of PlotItem, in row order
        self.active_plot = None
        self.active_curve = None
        # Multi-select via Shift+click, a superset of {active_plot}/
        # {active_curve} respectively. Only Copy, Delete, axis labels,
        # curve rename, and Toggle Legend act on the whole set -- FFT,
        # Remove Average, and everything else still target only
        # active_plot/active_curve (see set_axis_label/toggle_legend/
        # _rename_curve/copy_curve/copy_subplot/delete_selection).
        self.selected_plots = []
        self.selected_curves = []
        # Last subplot the mouse moved over, tracked live (sigMouseMoved)
        # independently of click-selection -- lets "Reset View" act on
        # whichever subplot the user was just working in even in Hand/Zoom
        # mode, where panning/zooming never clicks (and so never touches
        # active_plot) and the user then moves the mouse away to the
        # toolbar before clicking the button. Never reset to None on its
        # own; only updated when the mouse is actually over a subplot.
        self._hover_plot = None
        self.linked_x = False
        self.brushing = False

        self.max_history = 20
        self.undo_stack = []     # list of (undo_fn, redo_fn)
        self.redo_stack = []
        self._undo_group = None  # list of steps while an undo_group() block is open

        # Row/col stretch factors; resizing a border adjusts them so the grid
        # layout reflows the rest of the grid for free.
        self.row_stretch = {}
        self.col_stretch = {}
        self.overlap_resize = False
        self._resize_state = None
        self._warned_no_grid_layout = False
        # plot_item -> placeholder holding its grid cell while detached/floating.
        self.floating = {}
        self._move_state = None

        # plot_item -> RectBrush, generic brush-select wired onto every
        # subplot by add_subplot (see selection.py's RectBrush docstring).
        # Absent for the two LinkedScatter demo subplots, which use their
        # own row-linked brushing instead.
        self._brushers = {}

        # -- annotations ---------------------------------------------
        self.annotations = []       # every AnnotationItem in this figure
        self.selected_annotations = []
        self.active_annotation = None   # most recently selected of selected_annotations
        # Set by "Annotate > <shape>": next scene click(s) place it instead of selecting.
        self._placing_kind = None
        self._placing_state = None  # {'anchor','parent_plot','p0'} between a two-click shape's clicks
        # Set by "Link to...": next click on a subplot/empty space reparents this annotation.
        self._relink_source = None

        # select: click to select, drag handles to resize/move. Default.
        # hand: plain pan/zoom, no selection UI.
        # zoom: like hand but drag zooms to a rectangle.
        self.interaction_mode = 'select'

        # Register before building subplots so FigureManager's tree/clipboard
        # already has an entry when the first subplotsChanged signal fires.
        self.registry = get_registry()
        self.clipboard = get_clipboard()
        self.registry.register(self)

        self._build_toolbar()
        self._create_resize_handles()
        if not empty:
            self._build_demo_subplots()
        self.set_interaction_mode('select')

        # One shared QGraphicsScene for all subplots -- connect once here, not per-subplot.
        self.layout_widget.scene().sigMouseClicked.connect(self._on_scene_clicked)
        self.layout_widget.scene().sigMouseMoved.connect(self._on_scene_hovered)
        # Raw press/move/release for drag-to-draw placement of extent-having
        # annotations -- see eventFilter's own docstring for why sigMouseClicked
        # alone (used above) can't do this.
        self.layout_widget.scene().installEventFilter(self)

    def closeEvent(self, ev):
        self.registry.unregister(self)
        super().closeEvent(ev)

    # -- layout -------------------------------------------------------
    def _build_toolbar(self):
        tb = QtWidgets.QToolBar("Tools")
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(tb)
        style = self.style()

        def action(label, slot, checkable=False, icon=None, tooltip=None):
            act = QtGui.QAction(label, self)
            if isinstance(icon, str):
                # Filename in icons/; missing file falls back to no icon.
                path = os.path.join(ICON_DIR, icon)
                if os.path.isfile(path):
                    act.setIcon(QtGui.QIcon(path))
                else:
                    print(f"WARNING: icon file not found: {path}", file=sys.stderr)
            elif icon is not None:
                act.setIcon(style.standardIcon(icon))
            act.setToolTip(tooltip or label)
            act.setCheckable(checkable)
            act.triggered.connect(slot)
            tb.addAction(act)
            return act

        def menu_button(icon, tooltip, entries):
            # entries: list of (label, slot)
            btn = QtWidgets.QToolButton()
            btn.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
            path = os.path.join(ICON_DIR, icon)
            if os.path.isfile(path):
                btn.setIcon(QtGui.QIcon(path))
            else:
                print(f"WARNING: icon file not found: {path}", file=sys.stderr)
            btn.setToolTip(tooltip)
            btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
            menu = QtWidgets.QMenu(btn)
            for entry_label, slot in entries:
                menu.addAction(entry_label).triggered.connect(slot)
            btn.setMenu(menu)
            tb.addWidget(btn)
            return btn

        SP = QtWidgets.QStyle

        action("Add Subplot", self.add_new_subplot, icon=SP.SP_FileDialogNewFolder,
               tooltip="Add Subplot: add a new empty subplot in a new row at the bottom")
        action("Delete", self.delete_selection, icon=SP.SP_TrashIcon,
               tooltip="Delete: remove the selected curve, or the active subplot if no curve is selected (Del)")
        self.undo_action = action("Undo", self.undo, icon=SP.SP_ArrowBack, tooltip="Undo last action (Ctrl+Z)")
        self.redo_action = action("Redo", self.redo, icon=SP.SP_ArrowForward, tooltip="Redo last undone action (Ctrl+Y)")
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)

        tb.addSeparator()
        self.overlap_resize_action = action(
            "Grid Layout", lambda checked: self.toggle_overlap_resize(not checked), checkable=True,
            icon=SP.SP_ToolBarVerticalExtensionButton,
            tooltip="Grid Layout: drag the active subplot's border/corner to resize it.\n"
                    "On (default): the grid reflows live as you drag, "
                    "resizing neighbors to fit -- no overlap.\n"
                    "Off: the subplot floats above its neighbors and keeps "
                    "overlapping them after you release; neighbors never "
                    "change size. Turning this back on snaps everything "
                    "back into the grid.",
        )
        self.overlap_resize_action.setChecked(True)

        menu_button('pencil.png', "Annotate: place a shape on the figure", [
            (SHAPE_LABELS[kind], lambda checked=False, kind=kind: self.start_placing_annotation(kind))
            for kind in SHAPE_KINDS if kind != 'cursor'
        ])
        action("Data Cursor", lambda: self.start_placing_annotation('cursor'),
               icon='tool_data_cursor.png', tooltip="Data Cursor: place a data-readout marker")

        action("Toggle Legend", self.toggle_legend, icon='tool_legend.png',
               tooltip="Toggle Legend")

        menu_button('tool_text_textbox.png', "Axis Labels", [
            ("X Label", lambda: self.set_axis_label('bottom')),
            ("Y Label", lambda: self.set_axis_label('left')),
        ])

        self.brush_action = action(
            "Brush", self.toggle_brush, checkable=True,
            icon='tool_data_brush.png',
            tooltip="Brush: rectangular data brushing on any subplot -- right-click a "
                     "selection to delete/transform/fit/stat it",
        )

        tb.addSeparator()
        mode_group = QtGui.QActionGroup(self)
        mode_group.setExclusive(True)
        self.select_action = action(
            "Select", lambda checked: self.set_interaction_mode('select'), checkable=True,
            icon='tool_pointer.png',
            tooltip="Select: click a subplot to select it, drag its border/corner "
                    "handles to resize, drag its center handle to move/swap it. "
                    "(default)",
        )
        action("Reset View", self.reset_view, icon=SP.SP_DirHomeIcon,
               tooltip="Reset View: reset the active subplot's view (autorange)")
        self.hand_action = action(
            "Hand", lambda checked: self.set_interaction_mode('hand'), checkable=True,
            icon='tool_hand.png',
            tooltip="Hand: pan/zoom/grab the subplot under the cursor. No selection.",
        )
        self.zoom_action = action(
            "Zoom Rect", lambda checked: self.set_interaction_mode('zoom'), checkable=True,
            icon='tool_zoom_in.png',
            tooltip="Zoom Rect: drag a rectangle to zoom into it. No selection.",
        )
        mode_group.addAction(self.select_action)
        mode_group.addAction(self.hand_action)
        mode_group.addAction(self.zoom_action)
        self.select_action.setChecked(True)

        tb.addSeparator()
        self.link_x_action = action(
            "Link X", self.toggle_link_x, checkable=True,
            icon='tool_plot_linked.png', tooltip="Link X: link the X axis across all subplots",
        )
        action("FFT -> subplot below", self.fft_below, icon='fft_icon6.png',
               tooltip="FFT: compute the FFT of the selected curve into a new subplot below")
        action("Remove Average", self.remove_average, icon='icon1b1.png',
               tooltip="Remove Average: subtract the mean from every curve on the active subplot")

        QtGui.QShortcut(QtGui.QKeySequence.Copy, self, activated=self.copy_selection)
        QtGui.QShortcut(QtGui.QKeySequence.Paste, self, activated=self.paste_selection)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+C"), self, activated=self.copy_subplot)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+V"), self, activated=self.paste_subplot)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), self, activated=self.delete_selection)
        QtGui.QShortcut(QtGui.QKeySequence.Undo, self, activated=self.undo)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Y"), self, activated=self.redo)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self,
                         activated=lambda: (self._cancel_placing(), self._cancel_relink(),
                                            self._deselect_all()))

    def _build_demo_subplots(self):
        t = np.linspace(0, 10, 200_000)
        y1 = np.sin(2 * np.pi * 1.0 * t) + 0.05 * np.random.randn(t.size) + 2.0
        y2 = np.sin(2 * np.pi * 2.5 * t) * np.exp(-0.1 * t)

        p1 = self.add_subplot(row=0, col=0, title="Signal A")
        c1 = p1.plot(t, y1, pen=pg.mkPen((80, 120, 220), width=1), name="signal A")
        c1.setClipToView(True)
        c1.setDownsampling(auto=True, method='peak')
        self._wire_curve_clickable(p1, c1)

        p2 = self.add_subplot(row=0, col=1, title="Signal B")
        c2 = p2.plot(t, y2, pen=pg.mkPen((220, 100, 80), width=1), name="signal B")
        c2.setClipToView(True)
        c2.setDownsampling(auto=True, method='peak')
        self._wire_curve_clickable(p2, c2)

        rng = np.random.default_rng(0)
        n = 20_000
        xs = rng.normal(size=n)
        ys = xs * 0.6 + rng.normal(scale=0.5, size=n)
        self.selection_model = SelectionModel(n)

        p3 = self.add_subplot(row=1, col=0, title="Scatter view 1 (brush me)")
        self.scatter1 = LinkedScatter(p3, xs, ys, self.selection_model, color=(80, 160, 90), figure=self)

        p4 = self.add_subplot(row=1, col=1, title="Scatter view 2 (same rows)")
        self.scatter2 = LinkedScatter(p4, ys, xs, self.selection_model, color=(160, 90, 160), figure=self)

        self.active_plot = p1
        self._mark_active(p1)

    def add_subplot(self, row, col, title=""):
        plot_item = self.layout_widget.addPlot(row=row, col=col, title=title)
        plot_item.showGrid(x=True, y=True, alpha=0.2)
        wire_plot_labels_editable(plot_item)
        self._wire_context_menu(plot_item)
        vb = plot_item.getViewBox()
        vb.sigRangeChanged.connect(
            lambda *_, p=plot_item: self._refresh_annotation_chrome(p)
        )
        # A new subplot must adopt every figure-wide toggle (mode, brush,
        # Link X) here: the toggles' own loops over self.plots never see a
        # plot created afterwards. Guarded by test_new_subplot_adopts_*.
        vb.setMouseMode(pg.ViewBox.RectMode if self.interaction_mode == 'zoom' else pg.ViewBox.PanMode)
        self._apply_mouse_enabled(vb)
        vb.setCursor(self._cursor_for_mode(self.interaction_mode))
        brusher = RectBrush(plot_item, on_finished=self._on_rect_brush_finished)
        brusher.set_brushing(self.brushing)
        self._brushers[plot_item] = brusher
        self.plots.append(plot_item)
        self._apply_link_x()
        self._reset_grid_stretch()
        self.registry.notify_subplots_changed(self)
        return plot_item

    def _refresh_annotation_chrome(self, plot_item):
        """An 'axes'-anchored annotation's constant-pixel chrome (handle
        size, arrowhead size, dashed outline, ...) is either a) Qt-flag-
        based (AnnotationHandle's ItemIgnoresTransformations) or b)
        recomputed live inside paint()/boundingRect() every repaint (see
        AnnotationItem._px_to_local) -- both self-correct automatically as
        the subplot is panned/zoomed, no wiring needed. The one exception
        is the rotate handle's offset above the shape's center: that's a
        *position*, baked into a one-off setPos() call by
        _position_rotate_handle, which only runs when the annotation's own
        geometry changes, not on a bare view pan/zoom. Without this, a
        'text' annotation's rotate handle (the only kind that still has
        one -- see TWO_ENDPOINT_KINDS) would drift the wrong constant-pixel
        distance from the text after zooming without touching it."""
        for a in self._annotations_on(plot_item):
            if a.anchor == 'axes' and a._rotate_handle is not None:
                a._position_rotate_handle()

    def _wire_context_menu(self, plot_item):
        """Extend PyQtGraph's built-in right-click menu (View All / Mouse Mode /
        Plot Options, all still present) with app-specific actions. Right-clicking
        also makes this the active subplot, same as a left click does."""
        menu = plot_item.getViewBox().menu
        menu.addSeparator()

        def bound(fn):
            return lambda: (self._on_plot_context(plot_item), fn())

        menu.addAction("Paste Curve").triggered.connect(bound(self.paste_curve))
        menu.addAction("Copy Subplot").triggered.connect(bound(self.copy_subplot))
        menu.addAction("Paste Subplot").triggered.connect(bound(self.paste_subplot))
        menu.addAction("Toggle Legend").triggered.connect(bound(self.toggle_legend))
        menu.addAction("Remove Average").triggered.connect(bound(self.remove_average))
        menu.addAction("FFT -> Subplot Below").triggered.connect(bound(self.fft_below))

        menu.addSeparator()
        menu.addAction("Delete Selected Points").triggered.connect(
            bound(self.delete_brushed_points)
        )
        menu.addAction("Transform Selected Points...").triggered.connect(
            bound(self.transform_brushed_points)
        )
        menu.addAction("Selection Stats...").triggered.connect(
            bound(self.show_selection_stats)
        )
        fit_menu = menu.addMenu("Fit Selected Points")
        fit_menu.addAction("Linear").triggered.connect(
            bound(lambda: self.fit_brushed_points(plot_item, degree=1))
        )
        fit_menu.addAction("Polynomial...").triggered.connect(
            bound(lambda: self.fit_brushed_points(plot_item, degree=None))
        )

        delete_menu = menu.addMenu("Delete Curve")
        rename_menu = menu.addMenu("Rename Curve")

        def rebuild_curve_menus():
            delete_menu.clear()
            rename_menu.clear()
            for curve in plot_item.listDataItems():
                if not isinstance(curve, pg.PlotDataItem):
                    continue
                label = curve.name() or "(unnamed curve)"
                delete_menu.addAction(label).triggered.connect(
                    lambda checked=False, c=curve: self.delete_curve(c)
                )
                rename_menu.addAction(label).triggered.connect(
                    lambda checked=False, c=curve: self._rename_curve(plot_item, c)
                )

        menu.aboutToShow.connect(lambda: (self._on_plot_context(plot_item), rebuild_curve_menus()))

    def _apply_curve_rename(self, plot_item, curve, new_name):
        old_name = curve.name() or ""
        curve.opts['name'] = new_name
        if plot_item.legend is not None:
            plot_item.legend.removeItem(old_name)
            plot_item.legend.addItem(curve, new_name)
            wire_legend_editable(plot_item.legend)

    def _rename_curve(self, plot_item, curve):
        """Renames every selected curve to the same new name if `curve`
        (the one picked from the right-click submenu) is part of the
        current multi-select (Shift+click to select more than one), else
        just `curve` alone."""
        targets = self.selected_curves if curve in self.selected_curves else [curve]
        old_names = {c: c.name() or "" for c in targets}
        new_name, ok = QtWidgets.QInputDialog.getText(
            None, "Rename curve", "New name:", QtWidgets.QLineEdit.Normal, old_names[curve]
        )
        if not ok or not new_name:
            return

        def apply_new():
            for c in targets:
                p = self._curve_plot(c)
                if p is not None:
                    self._apply_curve_rename(p, c, new_name)

        def undo_fn():
            for c, old_name in old_names.items():
                p = self._curve_plot(c)
                if p is not None:
                    self._apply_curve_rename(p, c, old_name)

        apply_new()
        self._push_history(undo_fn=undo_fn, redo_fn=apply_new)

    def _grid_position(self, plot_item):
        return self.layout_widget.ci.items[plot_item][0]

    def _try_grid_position(self, plot_item):
        """Like _grid_position, but returns None instead of KeyError-ing
        when plot_item isn't currently a key in the grid's own item map --
        used by _remove_subplot's defensive guard below."""
        entry = self.layout_widget.ci.items.get(plot_item)
        return entry[0] if entry else None

    # -- adding/removing whole subplots ----------------------------------
    # Plain add/delete only touches its own cell -- never shifts rows, since
    # a shift could walk into a still-occupied sibling cell. FFT always adds
    # its own dedicated row, so shifting whole rows is safe there only.
    # _remove_subplot/_insert_subplot_at: plain. insert_subplot_below /
    # _insert_subplot_with_shift / _remove_subplot_with_shift: FFT only.

    def _remove_subplot(self, plot_item):
        """Remove exactly this subplot's cell. Leaves the cell empty --
        does not shift or resize any other subplot."""
        if plot_item in self.floating:
            self._reattach_floating(plot_item)
        for a in self._annotations_on(plot_item):
            self._purge_annotation(a)
        position = self._try_grid_position(plot_item)
        if position is None:
            # Should be unreachable -- every plot_item is either grid-managed
            # or tracked in self.floating, and the branch above reattaches
            # the latter before we get here. If this fires, a bug upstream
            # (move/swap/resize bookkeeping) left plot_item in neither, which
            # would otherwise KeyError here and crash whatever undo/redo/
            # delete called us. Clean up what we still can instead of
            # losing the action entirely, and say so loudly so the exact
            # repro that triggered it can be tracked down.
            print(
                f"WARNING: _remove_subplot: {plot_item} was not found in the "
                "grid layout or self.floating -- removing it from bookkeeping "
                "only. This points to a bug in subplot move/swap/resize; "
                "please report the exact steps that led here.",
                file=sys.stderr,
            )
            row, col = None, None
            if plot_item.scene() is not None:
                plot_item.scene().removeItem(plot_item)
        else:
            row, col = position
            self.layout_widget.removeItem(plot_item)
        self.plots.remove(plot_item)
        self._forget_removed_plot(plot_item)
        self._reset_grid_stretch()
        self.registry.notify_subplots_changed(self)
        return row, col

    def _insert_subplot_at(self, row, col, title, xlabel, ylabel, curves_data):
        """Place a new subplot directly into a specific, already-empty grid
        cell -- no shifting. Inverse of _remove_subplot."""
        new_plot = self.add_subplot(row=row, col=col, title=title)
        if xlabel:
            new_plot.setLabel('bottom', xlabel)
        if ylabel:
            new_plot.setLabel('left', ylabel)
        for x, y, pen, name in curves_data:
            nc = new_plot.plot(x, y, pen=pen, name=name)
            self._wire_curve_clickable(new_plot, nc)
        return new_plot

    def insert_subplot_below(self, reference_plot, title=""):
        """Shift every subplot at/after the reference's row down one, then
        insert a fresh plot directly beneath it -- used by 'FFT -> subplot
        below', which always creates its own dedicated single-column row."""
        self._reattach_all_floating()
        ref_row, ref_col = self._grid_position(reference_plot)
        for p in self.plots:
            row, col = self._grid_position(p)
            if row > ref_row:
                self.layout_widget.removeItem(p)
                self.layout_widget.addItem(p, row=row + 1, col=col)
        new_plot = self.add_subplot(row=ref_row + 1, col=ref_col, title=title)
        return new_plot

    def _insert_subplot_with_shift(self, row, col, title, xlabel, ylabel, curves_data):
        """Mirrors insert_subplot_below's shifting, for redoing an FFT
        insertion (which insert_subplot_below itself can't do -- it needs a
        live reference PlotItem, which no longer exists after an undo)."""
        self._reattach_all_floating()
        for p in self.plots:
            r, c = self._grid_position(p)
            if r >= row:
                self.layout_widget.removeItem(p)
                self.layout_widget.addItem(p, row=r + 1, col=c)
        return self._insert_subplot_at(row, col, title, xlabel, ylabel, curves_data)

    def _remove_subplot_with_shift(self, plot_item):
        """Inverse of _insert_subplot_with_shift / insert_subplot_below:
        remove a subplot that owns its entire row and shift every row below
        it up by one to close the gap. Only safe for FFT's dedicated rows --
        never for a plain subplot that might share its row with a sibling."""
        self._reattach_all_floating()
        for a in self._annotations_on(plot_item):
            self._purge_annotation(a)
        row, col = self._grid_position(plot_item)
        self.layout_widget.removeItem(plot_item)
        self.plots.remove(plot_item)
        for p in self.plots:
            r, c = self._grid_position(p)
            if r > row:
                self.layout_widget.removeItem(p)
                self.layout_widget.addItem(p, row=r - 1, col=c)
        self._forget_removed_plot(plot_item)
        self._reset_grid_stretch()
        self.registry.notify_subplots_changed(self)
        return row, col

    def _forget_removed_plot(self, plot_item):
        """Shared active-plot/active-curve bookkeeping after a plot leaves
        self.plots, regardless of which removal path was used."""
        self._brushers.pop(plot_item, None)
        if plot_item in self.selected_plots:
            self.selected_plots.remove(plot_item)
        if self.active_plot is plot_item:
            self.active_plot = self.plots[0] if self.plots else None
            if self.active_plot is not None:
                self._mark_active(self.active_plot, keep_selection=True)
        if self._hover_plot is plot_item:
            self._hover_plot = None
        for c in [c for c in self.selected_curves if self._curve_plot(c) is None]:
            self._forget_curve_selection(c)
        self._apply_link_x()

    def add_new_subplot(self):
        """Toolbar 'Add Subplot': always creates a new, empty, dedicated
        row at the bottom -- so it never has to guess which existing cell
        is free, and stays consistent with FFT's row-shifting logic."""
        self._reattach_all_floating()
        row = max((self._grid_position(p)[0] for p in self.plots), default=-1) + 1
        col = 0
        title = f"Subplot {len(self.plots) + 1}"
        new_plot = self.add_subplot(row=row, col=col, title=title)
        self.active_plot = new_plot
        self._mark_active(new_plot)

        holder = {'plot': new_plot}

        def undo_fn():
            p = holder.get('plot')
            if p is not None:
                self._remove_subplot(p)

        def redo_fn():
            p = self._insert_subplot_at(row, col, title, '', '', [])
            holder['plot'] = p
            self.active_plot = p
            self._mark_active(p)

        self._push_history(undo_fn, redo_fn)

    # -- active-plot tracking ------------------------------------------
    def _on_scene_clicked(self, ev):
        """Single handler for the whole shared scene: figure out which
        subplot's ViewBox actually contains the click and make that one
        active. Do NOT connect this per-subplot -- see __init__ comment.

        pyqtgraph's GraphicsScene dispatches the click to clickable items
        (e.g. a curve, via _wire_curve_clickable) *before* emitting this
        signal, and the item accepts the event if it handled the click. So
        if nothing accepted it, the click landed on empty space / a
        non-clickable item -- that's what should clear curve selection.

        A double click -- on a subplot, on a curve, or landing nowhere --
        deselects everything instead of selecting. pyqtgraph's own
        MouseClickEvent already distinguishes double clicks via .double(),
        the same event object this signal carries."""
        pos = ev.scenePos()
        additive = bool(ev.modifiers() & QtCore.Qt.ShiftModifier)

        if self._placing_kind is not None:
            # TWO_CLICK_KINDS are placed via the raw press/move/release
            # event filter instead (see eventFilter) -- a real drag never
            # reaches sigMouseClicked at all, so this is normally a no-op
            # for them; the not-in check is just defensive belt-and-braces.
            if not ev.double() and self._placing_kind not in TWO_CLICK_KINDS:
                self._handle_placement_click(pos)
            return

        if self._relink_source is not None:
            if not ev.double():
                self._handle_relink_click(pos)
            return

        hit_plot = None
        for p in self.plots:
            if p.getViewBox().sceneBoundingRect().contains(pos):
                hit_plot = p
                break

        if (hit_plot is None and ev.button() == QtCore.Qt.RightButton
                and not ev.double() and not ev.isAccepted()):
            # A right-click inside some subplot's ViewBox already gets its
            # own context menu from pyqtgraph (see _wire_context_menu) --
            # this covers right-clicking truly empty space instead, which
            # otherwise did nothing but deselect everything.
            self._show_empty_space_menu()
            return

        if ev.double():
            self._deselect_all()
            return

        if hit_plot is not None:
            # Accepted = a curve (or legend sample) already handled this
            # click; selecting the subplot too would undo its exclusivity.
            if not ev.isAccepted():
                self._on_plot_clicked(hit_plot, additive=additive)
        elif not ev.isAccepted() and not additive:
            # Shift+click on empty space does nothing (LibreOffice/MATLAB).
            # Single click landed outside every subplot, and nothing
            # clickable (e.g. a figure/border-anchored annotation) consumed
            # it -- that's genuinely empty space.
            self._deselect_all()

    def _show_empty_space_menu(self):
        """Right-click landing outside every subplot: offer Paste Subplot,
        since that's otherwise only reachable via Ctrl+Shift+V or a
        subplot's own right-click menu -- neither is discoverable when
        there's no subplot to right-click yet (e.g. a freshly emptied
        figure)."""
        menu = QtWidgets.QMenu(self)
        paste_action = menu.addAction("Paste Subplot")
        paste_action.setEnabled(bool(self.clipboard.subplot))
        paste_action.triggered.connect(self.paste_subplot)
        menu.exec_(QtGui.QCursor.pos())

    def _on_plot_clicked(self, plot_item, additive=False):
        """additive = Shift: toggle this subplot in/out of the selection,
        as in LibreOffice Draw and MATLAB. active_plot keeps tracking the
        clicked subplot either way -- it is the toolbar target."""
        self.active_plot = plot_item
        if additive:
            if plot_item in self.selected_plots:
                self.selected_plots.remove(plot_item)
            else:
                self.selected_plots.append(plot_item)
            self._mark_active(plot_item, keep_selection=True)
        else:
            self._mark_active(plot_item)

    def _on_plot_context(self, plot_item):
        """Right-click: keep a selection that already involves this subplot
        (so menu actions see the whole Shift-built set), else select the
        subplot like a plain click."""
        involved = plot_item in self.selected_plots or any(
            self._curve_plot(c) is plot_item for c in self.selected_curves)
        if involved:
            self.active_plot = plot_item
            self._mark_active(plot_item, keep_selection=True)
        else:
            self._on_plot_clicked(plot_item)

    def _select_plots(self, plots):
        """Exclusively select `plots` (e.g. just-pasted subplots)."""
        self._clear_selection()
        self.active_plot = plots[-1]
        self.selected_plots = list(plots)
        self._mark_active(self.active_plot, keep_selection=True)

    def _on_scene_hovered(self, pos):
        """sigMouseMoved gives scene coords directly (unlike sigMouseClicked's
        event object) -- pos is already what the hit-test loop below needs."""
        for p in self.plots:
            if p.getViewBox().sceneBoundingRect().contains(pos):
                self._hover_plot = p
                break

    def _deselect_all(self):
        """Double-click a subplot, or a single click that lands outside
        every subplot: clear the selected curve AND the active subplot."""
        self._clear_selection()
        self.active_plot = None
        for p in self.plots:
            p.getViewBox().setBorder(None)
        self._hide_handles()

    def _clear_selection(self):
        """Deselect every kind -- subplots, curves, annotation. Any selection
        without Shift starts here: selections are exclusive across kinds.
        active_plot is left alone; it is the toolbar target, not a selection."""
        self._deselect_curve()
        self._deselect_annotation()
        self.selected_plots = []

    def _mark_active(self, active, keep_selection=False):
        # The red border / move+resize handles only ever show in Select
        # mode -- Hand and Zoom Rect are explicitly "no selection" modes,
        # even though self.active_plot itself keeps tracking the last
        # clicked subplot so toolbar actions (FFT, Remove Average, ...)
        # still have a sensible target regardless of which tool is active.
        # keep_selection=True preserves an existing Shift-built multi-select
        # (self.selected_plots) instead of collapsing it to just `active` --
        # used by additive clicks and by bookkeeping that re-renders after a
        # plot already known to be selected changes (see _on_plot_clicked,
        # _forget_removed_plot).
        if not keep_selection:
            self._clear_selection()
            self.selected_plots = [active] if active is not None else []
        show = self.interaction_mode == 'select'
        for p in self.plots:
            p.getViewBox().setBorder(pg.mkPen('r', width=2) if (show and p in self.selected_plots) else None)
        if show:
            self._position_handles()
        else:
            self._hide_handles()

    # -- subplot resize (drag a border/corner of the active subplot) -----
    def toggle_overlap_resize(self, checked):
        self.overlap_resize = checked
        if not checked:
            # Turning overlap off is "rearrange now": snap every floating
            # subplot back into the grid, sizing its row/col from where it
            # currently sits so the reflow roughly matches what was on screen.
            for plot_item in list(self.floating.keys()):
                rect = QtCore.QRectF(plot_item.pos(), plot_item.size())
                _, row, col, _ = self.floating[plot_item]
                self._reattach_floating(plot_item)
                self._set_stretch_for_size(self.col_stretch, col, rect.width(), self.layout_widget.width())
                self._set_stretch_for_size(self.row_stretch, row, rect.height(), self.layout_widget.height())
            if self.floating:
                self._apply_grid_stretch()
            self._position_handles()

    def _create_resize_handles(self):
        roles = ('top', 'bottom', 'left', 'right',
                 'top-left', 'top-right', 'bottom-left', 'bottom-right')
        self.resize_handles = {role: ResizeHandle(self, role) for role in roles}
        for handle in self.resize_handles.values():
            self.layout_widget.scene().addItem(handle)
        self.move_handle = MoveHandle(self)
        self.layout_widget.scene().addItem(self.move_handle)

    def _hide_handles(self):
        for handle in self.resize_handles.values():
            handle.hide()
        self.move_handle.hide()

    def _position_handles(self):
        self._reposition_annotations()
        active = self.active_plot
        # active_plot outlives its selection (e.g. a curve click deselects
        # its subplot but keeps it as toolbar target) -- no handles then.
        if active is None or active not in self.selected_plots or self.interaction_mode != 'select':
            self._hide_handles()
            return
        rect = active.sceneBoundingRect()
        s = ResizeHandle.SIZE
        anchors = {
            'top': (rect.center().x(), rect.top()),
            'bottom': (rect.center().x(), rect.bottom()),
            'left': (rect.left(), rect.center().y()),
            'right': (rect.right(), rect.center().y()),
            'top-left': (rect.left(), rect.top()),
            'top-right': (rect.right(), rect.top()),
            'bottom-left': (rect.left(), rect.bottom()),
            'bottom-right': (rect.right(), rect.bottom()),
        }
        for role, (x, y) in anchors.items():
            handle = self.resize_handles[role]
            handle.setPos(x - s / 2, y - s / 2)
            handle.show()
        ms = MoveHandle.SIZE
        center = rect.center()
        self.move_handle.setPos(center.x() - ms / 2, center.y() - ms / 2)
        self.move_handle.show()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QtCore.QTimer.singleShot(0, self._position_handles)

    def _grid_layout(self):
        """The QGraphicsGridLayout backing the subplot grid. Accessed via
        pyqtgraph's private `.layout` attribute on the GraphicsLayout central
        item -- not part of pyqtgraph's public API, so this is the one spot
        most likely to need fixing on a pyqtgraph version mismatch."""
        layout = getattr(self.layout_widget.ci, 'layout', None)
        if layout is None and not self._warned_no_grid_layout:
            print(
                "WARNING: LaFigure._grid_layout() could not find "
                "self.layout_widget.ci.layout (expected a QGraphicsGridLayout). "
                "Subplot border/corner resize will have no visible effect. "
                "This means pyqtgraph's internal GraphicsLayout attribute name "
                "changed; update _grid_layout() to match.",
                file=sys.stderr,
            )
            self._warned_no_grid_layout = True
        return layout

    def _reset_grid_stretch(self):
        """Re-derive row/col stretch factors from whatever is actually in
        the grid layout right now (plots AND any floating-plot
        placeholders) whenever subplots are added/removed/moved.
        Deliberately forgets any manual resizing across a structural change
        rather than trying to reindex it -- simpler and safer than tracking
        row/col renumbering precisely. Iterating the layout's own item map
        (rather than self.plots) also means this can't KeyError on a plot
        that's currently floating (and so briefly absent from the layout)."""
        self.row_stretch = {}
        self.col_stretch = {}
        for row, col in (positions[0] for positions in self.layout_widget.ci.items.values()):
            self.row_stretch.setdefault(row, 100)
            self.col_stretch.setdefault(col, 100)
        self._apply_grid_stretch()
        QtCore.QTimer.singleShot(0, self._position_handles)

    def _reattach_all_floating(self):
        for plot_item in list(self.floating.keys()):
            self._reattach_floating(plot_item)

    def _start_floating(self, plot_item, row, col):
        """Detach plot_item from the grid layout and let it float above the
        scene at its own manually-controlled geometry, so it can genuinely
        overlap neighboring subplots (a real QGraphicsGridLayout can't let
        two managed cells overlap -- that's the whole point of a layout).
        A same-sized invisible placeholder takes its place in the grid so
        every other row/col keeps exactly its current size while it floats.

        The placeholder's own item-level min/max/preferred size hints are
        NOT enough to pin the row/column on their own: QGraphicsGridLayout
        computes a row's height (and a column's width) from ALL items
        sharing it, so a sibling's own size hints (e.g. a neighboring
        PlotItem's small preferred size, expanded only by stretch-factor
        distribution) can still pull the row away from the placeholder's
        fixed size once redistribution runs -- this was observed live to
        shift/resize a non-selected neighbor by tens of pixels the instant
        a subplot floated, before any drag even happened. Pinning the row/
        column directly via the layout's own setRowFixedHeight/
        setColumnFixedWidth is authoritative regardless of what siblings
        report, and is what actually keeps neighbors byte-for-byte
        unchanged (verified live)."""
        rect = QtCore.QRectF(plot_item.sceneBoundingRect())
        placeholder = QtWidgets.QGraphicsWidget()
        placeholder.setPreferredSize(rect.size())
        placeholder.setMinimumSize(rect.size())
        placeholder.setMaximumSize(rect.size())
        self.layout_widget.removeItem(plot_item)
        self.layout_widget.addItem(placeholder, row=row, col=col)
        layout = self._grid_layout()
        prior_bounds = None
        if layout is not None:
            # Capture the row/col's own prior bounds so _reattach_floating can
            # restore them exactly, rather than guessing an "unbounded" sentinel.
            prior_bounds = (
                layout.rowMinimumHeight(row), layout.rowMaximumHeight(row), layout.rowPreferredHeight(row),
                layout.columnMinimumWidth(col), layout.columnMaximumWidth(col), layout.columnPreferredWidth(col),
            )
            layout.setRowFixedHeight(row, rect.height())
            layout.setColumnFixedWidth(col, rect.width())
            # addItem() above already ran one activate() pass using the
            # placeholder's item-level hints alone (which, per the note
            # above, isn't authoritative against siblings); force a second
            # pass now that the row/col are explicitly pinned so any
            # distortion from that first pass is corrected immediately
            # rather than lingering until something else calls activate().
            layout.activate()

        # removeItem() doesn't guarantee scene/parent/visibility -- force all three.
        if plot_item.scene() is None:
            self.layout_widget.scene().addItem(plot_item)
        plot_item.setParentItem(None)
        plot_item.setZValue(500)
        plot_item.show()
        plot_item.setPos(rect.topLeft())
        plot_item.resize(rect.width(), rect.height())

        # Store (row, col) here: once floating, plot_item is gone from
        # layout_widget.ci.items, so this is the only record of its origin cell.
        self.floating[plot_item] = (placeholder, row, col, prior_bounds)

    def _reattach_floating(self, plot_item):
        """Undo _start_floating: drop the placeholder and give plot_item
        back to the grid layout at the same cell, restoring normal
        layout-managed sizing (its floated size/position is discarded).
        Also releases the row/col fixed-size pin _start_floating applied,
        restoring the bounds captured there -- otherwise the row/column
        would stay rigidly locked at the floated size forever, even after
        the plot rejoins the grid."""
        entry = self.floating.pop(plot_item, None)
        if entry is None:
            return
        placeholder, row, col, prior_bounds = entry
        self.layout_widget.removeItem(placeholder)
        plot_item.setZValue(0)
        self.layout_widget.addItem(plot_item, row=row, col=col)
        layout = self._grid_layout()
        if layout is not None and prior_bounds is not None:
            row_min, row_max, row_pref, col_min, col_max, col_pref = prior_bounds
            layout.setRowMinimumHeight(row, row_min)
            layout.setRowMaximumHeight(row, row_max)
            layout.setRowPreferredHeight(row, row_pref)
            layout.setColumnMinimumWidth(col, col_min)
            layout.setColumnMaximumWidth(col, col_max)
            layout.setColumnPreferredWidth(col, col_pref)

    def _apply_grid_stretch(self):
        layout = self._grid_layout()
        if layout is None:
            return
        for row, stretch in self.row_stretch.items():
            layout.setRowStretchFactor(row, int(round(stretch)))
        for col, stretch in self.col_stretch.items():
            layout.setColumnStretchFactor(col, int(round(stretch)))
        layout.activate()

    def _begin_resize(self, role, scene_pos):
        p = self.active_plot
        if p is None:
            return
        if not self.overlap_resize and p in self.floating:
            # Switching to reflow mode: restore layout management first.
            self._reattach_floating(p)

        if p in self.floating:
            # Already floating: p isn't in layout_widget.ci.items, so use self.floating.
            _, row, col, _ = self.floating[p]
        else:
            row, col = self._grid_position(p)
        self._resize_state = {
            'role': role, 'row': row, 'col': col,
            'origin': scene_pos, 'start_rect': QtCore.QRectF(p.sceneBoundingRect()),
            'target_rect': QtCore.QRectF(p.sceneBoundingRect()),
        }
        if self.overlap_resize and p not in self.floating:
            self._start_floating(p, row, col)

    def _update_resize(self, scene_pos):
        st = self._resize_state
        if st is None:
            return
        dx = scene_pos.x() - st['origin'].x()
        dy = scene_pos.y() - st['origin'].y()
        role = st['role']
        start = st['start_rect']
        min_size = 40

        rect = QtCore.QRectF(start)
        if 'right' in role:
            rect.setWidth(max(min_size, start.width() + dx))
        elif 'left' in role:
            rect.setLeft(min(start.right() - min_size, start.left() + dx))
        if 'bottom' in role:
            rect.setHeight(max(min_size, start.height() + dy))
        elif 'top' in role:
            rect.setTop(min(start.bottom() - min_size, start.top() + dy))

        st['target_rect'] = rect

        if self.overlap_resize:
            # Detached, so this genuinely overlaps neighbors instead of resizing them.
            p = self.active_plot
            p.setPos(rect.topLeft())
            p.resize(rect.width(), rect.height())
        else:
            self._apply_resize_target(st)
            # Repositioning (not hiding) is safe mid-drag: setPos() keeps the mouse grab.
            self._position_handles()

    def _end_resize(self):
        st = self._resize_state
        if st is None:
            return
        # Nothing else to do: both modes already applied live during the drag.
        self._resize_state = None
        self._position_handles()

    def _apply_resize_target(self, st):
        """Translate the dragged rectangle's size into row/col stretch
        factors, holding every other row/col's factor fixed so the layout
        redistributes the remaining space among them (the 'reflow')."""
        role, row, col, rect = st['role'], st['row'], st['col'], st['target_rect']
        if 'left' in role or 'right' in role:
            self._set_stretch_for_size(self.col_stretch, col, rect.width(), self.layout_widget.width())
        if 'top' in role or 'bottom' in role:
            self._set_stretch_for_size(self.row_stretch, row, rect.height(), self.layout_widget.height())
        self._apply_grid_stretch()

    @staticmethod
    def _set_stretch_for_size(stretch_map, index, desired_size, total_size):
        total_size = max(total_size, 1)
        others = sum(v for i, v in stretch_map.items() if i != index)
        fraction = min(max(desired_size / total_size, 0.05), 0.9)
        stretch_map[index] = max(fraction * others / (1 - fraction), 5) if others > 0 else 100

    # -- subplot move (drag the center handle, Select mode only) ---------
    def _begin_move(self, scene_pos):
        p = self.active_plot
        if p is None or self.interaction_mode != 'select':
            return
        if p in self.floating:
            _, row, col, _ = self.floating[p]
        else:
            row, col = self._grid_position(p)
            self._start_floating(p, row, col)
        self._move_state = {'origin': scene_pos, 'start_pos': QtCore.QPointF(p.pos())}

    def _update_move(self, scene_pos):
        st = self._move_state
        if st is None:
            return
        p = self.active_plot
        delta = scene_pos - st['origin']
        p.setPos(st['start_pos'] + delta)
        self._position_handles()

    def _end_move(self, scene_pos):
        st = self._move_state
        if st is None:
            return
        self._move_state = None
        p = self.active_plot
        target = None
        for other in self.plots:
            if other is p or other in self.floating:
                continue
            if other.sceneBoundingRect().contains(scene_pos):
                target = other
                break
        if target is not None:
            self._swap_subplots(p, target)
        else:
            self._reattach_floating(p)
            self._position_handles()

    def _swap_subplots(self, a, b):
        """Drop 'a' (currently floating, mid-move) onto 'b': give each the
        other's original grid cell. Used by _end_move -- dragging a
        subplot's move handle onto another one swaps their positions."""
        placeholder, row_a, col_a, prior_bounds = self.floating.pop(a)
        row_b, col_b = self._grid_position(b)
        self.layout_widget.removeItem(placeholder)
        self.layout_widget.removeItem(b)
        self.layout_widget.addItem(b, row=row_a, col=col_a)
        self.layout_widget.addItem(a, row=row_b, col=col_b)
        a.setZValue(0)
        layout = self._grid_layout()
        if layout is not None and prior_bounds is not None:
            # Release the fixed-size pin _start_floating applied to (row_a,
            # col_a) -- _reset_grid_stretch below re-derives stretch factors
            # for every cell, but a leftover fixed min==max would still
            # override that, silently freezing this cell at its old size.
            row_min, row_max, row_pref, col_min, col_max, col_pref = prior_bounds
            layout.setRowMinimumHeight(row_a, row_min)
            layout.setRowMaximumHeight(row_a, row_max)
            layout.setRowPreferredHeight(row_a, row_pref)
            layout.setColumnMinimumWidth(col_a, col_min)
            layout.setColumnMaximumWidth(col_a, col_max)
            layout.setColumnPreferredWidth(col_a, col_pref)
        self._reset_grid_stretch()  # also repositions handles once layout settles

        # Diagnostic for a KeyError seen later in _remove_subplot (undoing a
        # paste/delete on a plot that had since been moved/swapped) whose
        # root cause wasn't reproducible from reading this method alone --
        # if addItem above silently didn't register one of these two, say so
        # now, at the moment it actually happens, instead of leaving it to
        # surface as a confusing crash somewhere unrelated much later.
        for item, label in ((a, 'a'), (b, 'b')):
            if item not in self.layout_widget.ci.items:
                print(
                    f"WARNING: _swap_subplots: {label}={item} did not register "
                    "in the grid layout after addItem -- please report this, "
                    "along with the exact drag/drop steps that led here.",
                    file=sys.stderr,
                )

    # -- curve selection -------------------------------------------------
    def _wire_curve_clickable(self, plot_item, curve):
        """Make a curve's line clickable; clicking it selects it (visual
        highlight) and makes it the target for Copy / FFT, instead of those
        actions always guessing the subplot's first curve."""
        curve.curve.setClickable(True, width=8)

        def handler(*args, plot_item=plot_item, curve=curve):
            # Guard: this fires before sigMouseClicked/_on_scene_clicked, which
            # handles placement/relink clicks -- don't also select/highlight.
            if self._placing_kind is not None or self._relink_source is not None:
                return
            ev = args[-1] if args else None
            additive = bool(ev.modifiers() & QtCore.Qt.ShiftModifier) if ev is not None else False
            if self.interaction_mode != 'select':
                self._on_plot_clicked(plot_item, additive=additive)
                return
            if (ev is not None and ev.button() == QtCore.Qt.RightButton
                    and curve in self.selected_curves):
                return  # right-click inside the selection keeps it
            self._select_curve(curve, additive=additive)
            self.active_plot = plot_item
            self._mark_active(plot_item, keep_selection=True)

        curve.curve.sigClicked.connect(handler)

    def _highlight_curve_pen(self, curve):
        orig_pen = curve.opts.get('pen')
        curve.opts.setdefault('_orig_pen', orig_pen)
        base = pg.mkPen(orig_pen) if orig_pen is not None else pg.mkPen('k')
        curve.setPen(pg.mkPen(color=base.color(), width=base.width() + 3))

    def _select_curve(self, curve, additive=False):
        """additive = Shift: toggle this curve in/out of the selection."""
        if additive:
            if curve in self.selected_curves:
                self._unhighlight_curve_pen(curve)
                self._forget_curve_selection(curve)
                return
            self._highlight_curve_pen(curve)
            self.selected_curves.append(curve)
            self.active_curve = curve
            return
        self._clear_selection()
        self._highlight_curve_pen(curve)
        self.selected_curves = [curve]
        self.active_curve = curve

    @staticmethod
    def _unhighlight_curve_pen(curve):
        orig_pen = curve.opts.get('_orig_pen')
        if orig_pen is not None:
            curve.setPen(orig_pen)

    def _deselect_curve(self):
        for c in self.selected_curves:
            self._unhighlight_curve_pen(c)
        self.selected_curves = []
        self.active_curve = None

    def _forget_curve_selection(self, curve):
        """Drop `curve` from the multi-select (and active_curve, falling
        back to whatever else is still selected) without touching its pen
        -- used when a curve has already been removed/replaced, unlike
        _deselect_curve which is a user-facing 'select nothing' action."""
        if curve in self.selected_curves:
            self.selected_curves.remove(curve)
        if curve is self.active_curve:
            self.active_curve = self.selected_curves[-1] if self.selected_curves else None

    def _active_curve_on(self, plot_item):
        """The curve to act on for Copy/FFT: the explicitly selected curve
        if it belongs to this subplot, else fall back to the first curve."""
        curves = [c for c in plot_item.listDataItems() if isinstance(c, pg.PlotDataItem)]
        if self.active_curve in curves:
            return self.active_curve
        return curves[0] if curves else None

    def _curve_plot(self, curve):
        for p in self.plots:
            if curve in p.listDataItems():
                return p
        return None

    # -- undo / redo -------------------------------------------------
    @contextlib.contextmanager
    def undo_group(self):
        """Fold every _push_history inside this block into one undo entry:
        one gesture = one Undo, as in LibreOffice Draw / MATLAB. Undo runs
        the steps in reverse and redo in order -- exactly what N separate
        presses did, so each step's own closures stay valid. Nests."""
        outer = self._undo_group is None
        if outer:
            self._undo_group = []
        try:
            yield
        finally:
            if outer:
                steps, self._undo_group = self._undo_group, None
                if len(steps) == 1:
                    self._push_history(*steps[0])
                elif steps:
                    self._push_history(
                        undo_fn=lambda: [u() for u, _ in reversed(steps)],
                        redo_fn=lambda: [r() for _, r in steps],
                    )

    def _push_history(self, undo_fn, redo_fn):
        if self._undo_group is not None:
            self._undo_group.append((undo_fn, redo_fn))
            return
        self.undo_stack.append((undo_fn, redo_fn))
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._update_undo_redo_actions()

    def _update_undo_redo_actions(self):
        self.undo_action.setEnabled(bool(self.undo_stack))
        self.redo_action.setEnabled(bool(self.redo_stack))

    def undo(self):
        if not self.undo_stack:
            return
        undo_fn, redo_fn = self.undo_stack.pop()
        undo_fn()
        self.redo_stack.append((undo_fn, redo_fn))
        self._update_undo_redo_actions()

    def redo(self):
        if not self.redo_stack:
            return
        undo_fn, redo_fn = self.redo_stack.pop()
        redo_fn()
        self.undo_stack.append((undo_fn, redo_fn))
        self._update_undo_redo_actions()

    # -- delete (curve or subplot) ---------------------------------------
    def delete_selection(self):
        """Del key / toolbar Delete: remove everything selected, whatever
        its kind, as one undo entry.

        Curves and subplot-owned annotations on a subplot that is itself
        being deleted are skipped: the subplot's own undo restores them,
        while their separate undo steps would target the dead PlotItem."""
        doomed_plots = list(self.selected_plots)
        with self.undo_group():
            for ann in list(self.selected_annotations):
                if ann.anchor == 'figure' or ann.parent_plot not in doomed_plots:
                    self.delete_annotation(ann)
            for curve in list(self.selected_curves):
                plot_item = self._curve_plot(curve)
                if plot_item is not None and plot_item not in doomed_plots:
                    self.delete_curve(curve)
            for plot_item in doomed_plots:
                self.delete_subplot(plot_item)

    def delete_curve(self, curve):
        plot_item = self._curve_plot(curve)
        if plot_item is None:
            return
        x, y = curve.xData.copy(), curve.yData.copy()
        pen = curve.opts.get('_orig_pen', curve.opts.get('pen'))
        name = curve.name()
        plot_item.removeItem(curve)
        self._forget_curve_selection(curve)
        brusher = self._brushers.get(plot_item)
        if brusher is not None:
            brusher.forget_curve(curve)

        holder = {}

        def undo_fn():
            new_curve = plot_item.plot(x, y, pen=pen, name=name)
            self._wire_curve_clickable(plot_item, new_curve)
            holder['curve'] = new_curve

        def redo_fn():
            c = holder.get('curve')
            if c is not None:
                plot_item.removeItem(c)
                self._forget_curve_selection(c)

        self._push_history(undo_fn, redo_fn)

    def delete_subplot(self, plot_item):
        min_subplots = 0 if self.empty else 1
        if len(self.plots) <= min_subplots:
            return  # keep at least one subplot (zero for a manager-created empty figure)
        title = plot_item.titleLabel.text
        xlabel = plot_item.getAxis('bottom').labelText
        ylabel = plot_item.getAxis('left').labelText
        curves_data = [
            (c.xData.copy(), c.yData.copy(), c.opts.get('_orig_pen', c.opts.get('pen')), c.name())
            for c in plot_item.listDataItems() if isinstance(c, pg.PlotDataItem)
        ]
        # Snapshot annotations first: _remove_subplot purges them unconditionally.
        annotations_data = [a.to_dict() for a in self._annotations_on(plot_item)]
        row, col = self._remove_subplot(plot_item)
        if row is None:
            # _remove_subplot's defensive fallback (plot_item was already
            # orphaned from the grid by some other bug) -- fall back to
            # appending a new row rather than crashing undo with a None row/col.
            row = max((self._grid_position(p)[0] for p in self.plots), default=-1) + 1
            col = 0

        holder = {}

        def undo_fn():
            new_plot = self._insert_subplot_at(row, col, title, xlabel, ylabel, curves_data)
            holder['plot'] = new_plot
            for d in annotations_data:
                AnnotationItem.from_dict(self, new_plot, d)
            self.active_plot = new_plot
            self._mark_active(new_plot)

        def redo_fn():
            p = holder.get('plot')
            if p is not None:
                self._remove_subplot(p)

        self._push_history(undo_fn, redo_fn)

    # -- toolbar actions -------------------------------------------------
    @staticmethod
    def _cursor_for_mode(mode):
        return QtCore.Qt.OpenHandCursor if mode == 'hand' else QtCore.Qt.ArrowCursor

    def set_interaction_mode(self, mode):
        """'select': click-to-select + move/resize handles, dragging inside
        a subplot does nothing (freed up for the handles).
        'hand': plain pan, no selection. 'zoom': drag-to-zoom, no selection."""
        self.interaction_mode = mode
        vb_mode = pg.ViewBox.RectMode if mode == 'zoom' else pg.ViewBox.PanMode
        cursor = self._cursor_for_mode(mode)
        for p in self.plots:
            vb = p.getViewBox()
            vb.setMouseMode(vb_mode)
            self._apply_mouse_enabled(vb)
            vb.setCursor(cursor)
        if mode != 'select':
            self._deselect_curve()
        if self.active_plot is not None:
            self._mark_active(self.active_plot, keep_selection=True)
        else:
            self._hide_handles()

    def reset_view(self):
        """Acts on whichever subplot the mouse was most recently over
        (self._hover_plot), not the click-selected self.active_plot --
        Hand/Zoom-mode panning never clicks a subplot, so active_plot can
        be stale while the user has clearly been working in a different
        one. Falls back to active_plot before any hover has been seen."""
        p = self._hover_plot or self.active_plot
        if p is None:
            return
        p.getViewBox().autoRange()

    def set_axis_label(self, axis_name):
        """Toolbar 'X Label' / 'Y Label': same effect as double-clicking the
        axis label, just discoverable without knowing that gesture -- handy
        right after Add Subplot, whose axes start unlabeled. Applies the
        same text to every selected subplot (Shift+click to select more
        than one)."""
        targets = self.selected_plots if self.selected_plots else (
            [self.active_plot] if self.active_plot is not None else []
        )
        if not targets:
            return
        p = self.active_plot if self.active_plot in targets else targets[0]
        prompt = "X-axis label:" if axis_name == 'bottom' else "Y-axis label:"
        text, ok = QtWidgets.QInputDialog.getText(
            None, "Edit label", prompt, QtWidgets.QLineEdit.Normal, p.getAxis(axis_name).labelText
        )
        if not ok:
            return
        old_texts = {t: t.getAxis(axis_name).labelText for t in targets}

        def apply_new():
            for t in targets:
                t.getAxis(axis_name).setLabel(text)

        def undo_fn():
            for t, old_text in old_texts.items():
                t.getAxis(axis_name).setLabel(old_text)

        apply_new()
        self._push_history(undo_fn=undo_fn, redo_fn=apply_new)

    def toggle_legend(self):
        """Toggles independently on every selected subplot (Shift+click to
        select more than one) -- each subplot's legend flips its own
        current on/off state rather than being forced to match the others."""
        targets = self.selected_plots if self.selected_plots else (
            [self.active_plot] if self.active_plot is not None else []
        )
        if not targets:
            return
        for p in targets:
            if p.legend is None:
                legend = p.addLegend()
                wire_legend_editable(legend)
            else:
                p.legend.scene().removeItem(p.legend)
                p.legend = None

    def remove_average(self):
        p = self.active_plot
        if p is None:
            return
        affected = []
        for curve in p.listDataItems():
            if not isinstance(curve, pg.PlotDataItem):
                continue
            y = curve.yData
            if y is None or y.size == 0:
                continue
            affected.append((curve, y.copy()))
            curve.setData(curve.xData, y - np.mean(y))
        if not affected:
            return

        def undo_fn():
            for curve, y in affected:
                curve.setData(curve.xData, y)

        def redo_fn():
            for curve, y in affected:
                curve.setData(curve.xData, y - np.mean(y))

        self._push_history(undo_fn, redo_fn)

    def fft_below(self):
        p = self.active_plot
        if p is None:
            return
        curve = self._active_curve_on(p)
        if curve is None:
            return
        x, y = curve.xData, curve.yData
        if x is None or x.size < 2:
            return
        dt = np.mean(np.diff(x))
        freqs = np.fft.rfftfreq(y.size, d=dt)
        mag = np.abs(np.fft.rfft(y)) / y.size
        title = f"FFT of {curve.name() or 'signal'}"
        fft_pen = pg.mkPen((60, 60, 60), width=1)

        fft_plot = self.insert_subplot_below(p, title=title)
        fft_curve = fft_plot.plot(freqs, mag, pen=fft_pen)
        self._wire_curve_clickable(fft_plot, fft_curve)
        fft_plot.setLabel('bottom', 'Frequency (Hz)')
        fft_plot.setLabel('left', 'Magnitude')

        row, col = self._grid_position(fft_plot)
        curves_data = [(freqs, mag, fft_pen, None)]
        holder = {'plot': fft_plot}

        def undo_fn():
            plot = holder.get('plot')
            if plot is not None:
                self._remove_subplot_with_shift(plot)

        def redo_fn():
            new_plot = self._insert_subplot_with_shift(row, col, title, 'Frequency (Hz)', 'Magnitude', curves_data)
            holder['plot'] = new_plot
            self.active_plot = new_plot
            self._mark_active(new_plot)

        self._push_history(undo_fn, redo_fn)

    def _apply_mouse_enabled(self, vb):
        """The only writer of a ViewBox's mouse-enabled state: Select mode
        and brushing both disable pan, so neither may re-enable it alone."""
        enabled = self.interaction_mode != 'select' and not self.brushing
        vb.setMouseEnabled(x=enabled, y=enabled)

    def _apply_link_x(self):
        """Link every subplot's X to plots[0], or unlink all. Re-run on any
        add/remove, since plots[0] -- the reference -- can change."""
        if not self.plots:
            return
        reference = self.plots[0]
        reference.setXLink(None)
        for p in self.plots[1:]:
            p.setXLink(reference if self.linked_x else None)

    def toggle_link_x(self, checked):
        self.linked_x = checked
        self._apply_link_x()

    def toggle_brush(self, checked):
        self.brushing = checked
        for scatter in (getattr(self, 'scatter1', None), getattr(self, 'scatter2', None)):
            if scatter is not None:
                scatter.set_brushing(checked)
        for brusher in self._brushers.values():
            brusher.set_brushing(checked)
        for p in self.plots:
            self._apply_mouse_enabled(p.getViewBox())
        if not checked:
            self.selection_model.clear()

    def _on_rect_brush_finished(self, plot_item, matches, additive):
        """RectBrush's on_finished callback (see selection.py) -- brushing
        is a figure-wide concept: a fresh, non-additive brush drag anywhere
        unbrushes every other subplot (and the linked-scatter pair) in this
        figure first; a Shift-held drag instead adds to whatever's already
        selected everywhere."""
        if not additive:
            self._clear_all_brush_selection(except_plot=plot_item)
            self._brushers[plot_item].set_selection(matches)
        else:
            self._brushers[plot_item].merge_selection(matches)

    def _clear_all_brush_selection(self, except_plot=None):
        for plot_item, brusher in self._brushers.items():
            if plot_item is not except_plot:
                brusher.clear_selection()
        self.selection_model.clear()

    def _figure_brush_items(self):
        """Every (curve, mask) with an active brush selection, figure-wide
        -- pooled across every subplot's RectBrush, since brushing is a
        figure-level concept (see _on_rect_brush_finished)."""
        items = []
        for brusher in self._brushers.values():
            for curve, mask in brusher.selection.items():
                if mask.any():
                    items.append((curve, mask))
        return items

    def _pooled_brush_xy(self, items):
        xs, ys = [], []
        for curve, mask in items:
            x, y = np.asarray(curve.xData), np.asarray(curve.yData)
            xs.append(x[mask])
            ys.append(y[mask])
        if not xs:
            return np.array([]), np.array([])
        return np.concatenate(xs), np.concatenate(ys)

    def _require_brush_selection(self):
        """Shared guard for the four brushed-selection actions below --
        returns the figure-wide list of (curve, mask) if there's a live
        selection anywhere, else tells the user what to do and returns None."""
        items = self._figure_brush_items()
        if not items:
            QtWidgets.QMessageBox.information(
                self, "No selection",
                "Brush-select some points first: toggle Brush mode, then drag "
                "a rectangle over the points (on any subplot; Shift+drag to "
                "add more, from any subplot).",
            )
            return None
        return items

    def delete_brushed_points(self):
        items = self._require_brush_selection()
        if items is None:
            return
        affected = [
            (curve, np.asarray(curve.xData).copy(), np.asarray(curve.yData).copy(), mask.copy())
            for curve, mask in items
        ]
        self._clear_all_brush_selection()

        def apply_delete():
            for curve, x, y, mask in affected:
                curve.setData(x=x[~mask], y=y[~mask])

        def undo_restore():
            for curve, x, y, mask in affected:
                curve.setData(x=x, y=y)

        apply_delete()
        self._push_history(undo_fn=undo_restore, redo_fn=apply_delete)

    def transform_brushed_points(self):
        items = self._require_brush_selection()
        if items is None:
            return
        expr, ok = QtWidgets.QInputDialog.getText(
            self, "Transform selected points",
            "Expression in terms of x, y (numpy available as np), applied to the\n"
            "selected points' y-values, e.g. \"y * 2\" or \"np.log(y)\":",
            QtWidgets.QLineEdit.Normal, "y",
        )
        if not ok or not expr:
            return

        affected = []
        for curve, mask in items:
            x_full, y_full = np.asarray(curve.xData), np.asarray(curve.yData)
            x_sel, y_sel = x_full[mask], y_full[mask]
            try:
                new_y_sel = np.asarray(
                    eval(expr, {'__builtins__': {}}, {'np': np, 'x': x_sel, 'y': y_sel}),
                    dtype=float,
                )
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Invalid expression", str(e))
                return
            if new_y_sel.shape != y_sel.shape:
                QtWidgets.QMessageBox.warning(
                    self, "Invalid expression",
                    "Result must have the same shape as the selected points.",
                )
                return
            affected.append((curve, x_full, y_full.copy(), mask.copy(), new_y_sel))

        def apply_transform():
            for curve, x_full, y_full, mask, new_y_sel in affected:
                new_y = y_full.copy()
                new_y[mask] = new_y_sel
                curve.setData(x=x_full, y=new_y)

        def undo_restore():
            for curve, x_full, y_full, mask, new_y_sel in affected:
                curve.setData(x=x_full, y=y_full)

        apply_transform()
        self._clear_all_brush_selection()
        self._push_history(undo_fn=undo_restore, redo_fn=apply_transform)

    def show_selection_stats(self):
        items = self._require_brush_selection()
        if items is None:
            return
        lines = []
        for curve, mask in items:
            x, y = np.asarray(curve.xData)[mask], np.asarray(curve.yData)[mask]
            label = curve.name() or "(unnamed curve)"
            lines.append(
                f"{label}: n={mask.sum()}  "
                f"x: mean={x.mean():.4g} std={x.std():.4g}  "
                f"y: mean={y.mean():.4g} std={y.std():.4g}"
            )
        if len(items) > 1:
            pooled_x, pooled_y = self._pooled_brush_xy(items)
            lines.append("")
            lines.append(
                f"All curves pooled: n={pooled_x.size}  "
                f"x: mean={pooled_x.mean():.4g} std={pooled_x.std():.4g}  "
                f"y: mean={pooled_y.mean():.4g} std={pooled_y.std():.4g}"
            )
        QtWidgets.QMessageBox.information(self, "Selection stats", "\n".join(lines))

    def fit_brushed_points(self, plot_item, degree):
        items = self._require_brush_selection()
        if items is None:
            return
        if degree is None:
            degree, ok = QtWidgets.QInputDialog.getInt(
                self, "Polynomial fit", "Degree:", 2, 1, 10
            )
            if not ok:
                return
        x, y = self._pooled_brush_xy(items)
        if x.size < degree + 1:
            QtWidgets.QMessageBox.warning(
                self, "Fit failed",
                f"Need at least {degree + 1} selected points for a degree-{degree} fit.",
            )
            return

        coeffs = np.polyfit(x, y, degree)
        y_hat = np.polyval(coeffs, x)
        ss_res = np.sum((y - y_hat) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
        label = "Linear fit" if degree == 1 else f"Polynomial fit (deg={degree})"
        terms = " + ".join(
            f"{c:.4g}*x^{degree - i}" if degree - i > 0 else f"{c:.4g}"
            for i, c in enumerate(coeffs)
        )
        text = f"{label}\ny = {terms}\nR² = {r2:.4g}"

        order = np.argsort(x)
        xs_sorted = x[order]
        ys_fit = np.polyval(coeffs, xs_sorted)

        def build():
            fit_pen = pg.mkPen((200, 30, 30), width=2, style=QtCore.Qt.DashLine)
            curve = plot_item.plot(xs_sorted, ys_fit, pen=fit_pen, name=label)
            self._wire_curve_clickable(plot_item, curve)
            text_item = pg.TextItem(text, color=(200, 30, 30), anchor=(0, 1))
            text_item.setPos(xs_sorted[-1], ys_fit[-1])
            plot_item.addItem(text_item)
            return curve, text_item

        holder = {}
        holder['curve'], holder['text'] = build()

        def undo_fn():
            c, t = holder.get('curve'), holder.get('text')
            if c is not None:
                plot_item.removeItem(c)
                self._forget_curve_selection(c)
            if t is not None:
                plot_item.removeItem(t)
            holder['curve'] = holder['text'] = None

        def redo_fn():
            holder['curve'], holder['text'] = build()

        self._push_history(undo_fn, redo_fn)

    # -- Ctrl+C / Ctrl+V: dispatch to curve or subplot copy/paste --------
    def copy_selection(self):
        """Ctrl+C: copy the selected curve(s) if any curve is selected
        (Shift+click to select more than one), else the selected
        subplot(s) -- without this, Ctrl+C always copied a curve even when
        only a subplot had ever been selected, silently duplicating a
        curve on paste instead of the subplot."""
        if self.selected_curves:
            self.copy_curve()
        elif self.active_plot is not None:
            self.copy_subplot()

    def paste_selection(self):
        """Ctrl+V: mirrors copy_selection -- pastes whichever kind was
        most recently copied, via Ctrl+C, Ctrl+Shift+C, or their menu
        equivalents (see Clipboard.last_copied)."""
        if self.clipboard.last_copied == 'subplot':
            self.paste_subplot()
        else:
            self.paste_curve()

    # -- copy / paste a curve between subplots ---------------------------
    def copy_curve(self):
        """Copies every selected curve (Shift+click to select more than
        one); with none explicitly selected, falls back to the active
        subplot's first curve, same as before multi-select existed."""
        if self.selected_curves:
            targets = list(self.selected_curves)
        else:
            p = self.active_plot
            c = self._active_curve_on(p) if p is not None else None
            targets = [c] if c is not None else []
        if not targets:
            return
        self.clipboard.curve = [
            (c.xData.copy(), c.yData.copy(), c.opts.get('_orig_pen', c.opts.get('pen')), c.name())
            for c in targets
        ]
        self.clipboard.last_copied = 'curve'

    def paste_curve(self):
        p = self.active_plot
        if p is None or not self.clipboard.curve:
            return
        curves_data = self.clipboard.curve

        def build():
            new_curves = []
            for x, y, pen, name in curves_data:
                nc = p.plot(x, y, pen=pen, name=name)
                self._wire_curve_clickable(p, nc)
                new_curves.append(nc)
            return new_curves

        holder = {'curves': build()}

        def undo_fn():
            for c in holder.get('curves', []):
                p.removeItem(c)
                self._forget_curve_selection(c)
            holder['curves'] = []

        def redo_fn():
            holder['curves'] = build()

        self._push_history(undo_fn, redo_fn)

    # -- copy / paste a whole subplot, including across separate figure
    # windows (via the process-wide Clipboard) ---------------------------
    def copy_subplot(self):
        """Copies every selected subplot (Shift+click to select more than
        one); with none explicitly selected, falls back to the active one."""
        targets = self.selected_plots if self.selected_plots else (
            [self.active_plot] if self.active_plot is not None else []
        )
        if not targets:
            return
        self.clipboard.subplot = [
            {
                'title': p.titleLabel.text,
                'xlabel': p.getAxis('bottom').labelText,
                'ylabel': p.getAxis('left').labelText,
                'curves': [
                    (c.xData.copy(), c.yData.copy(), c.opts.get('_orig_pen', c.opts.get('pen')), c.name())
                    for c in p.listDataItems() if isinstance(c, pg.PlotDataItem)
                ],
                'annotations': [a.to_dict() for a in self._annotations_on(p)],
            }
            for p in targets
        ]
        self.clipboard.last_copied = 'subplot'

    def paste_subplot(self):
        """Paste every copied subplot as new rows at the bottom of *this*
        window -- which may be a different LaFigure instance than the
        one it was copied from, since self.clipboard is shared
        process-wide (see clipboard.py)."""
        data_list = self.clipboard.subplot
        if not data_list:
            return
        self._reattach_all_floating()
        start_row = max((self._grid_position(p)[0] for p in self.plots), default=-1) + 1
        col = 0

        def build():
            new_plots = []
            for i, data in enumerate(data_list):
                new_plot = self._insert_subplot_at(
                    start_row + i, col, data['title'], data['xlabel'], data['ylabel'], data['curves']
                )
                for d in data.get('annotations', []):
                    AnnotationItem.from_dict(self, new_plot, d)
                new_plots.append(new_plot)
            return new_plots

        holder = {'plots': build()}
        self._select_plots(holder['plots'])

        def undo_fn():
            for p in holder.get('plots', []):
                self._remove_subplot(p)
            holder['plots'] = []

        def redo_fn():
            holder['plots'] = build()
            self._select_plots(holder['plots'])

        self._push_history(undo_fn, redo_fn)

    # -- annotations -------------------------------------------------
    # Placement arms self._placing_kind, then the next scene interaction
    # creates the annotation instead of selecting a subplot/curve. Point
    # kinds (text, cursor) place on a single click, handled by
    # _handle_placement_click via _on_scene_clicked's sigMouseClicked.
    # Extent kinds (TWO_CLICK_KINDS) place via a single press-drag-release
    # gesture instead: sigMouseClicked only fires for a genuine "click" (a
    # release near the press point within pyqtgraph's own click-vs-drag
    # threshold), so a real click-and-drag never reaches it at all -- hence
    # raw GraphicsSceneMousePress/Move/Release events are intercepted
    # directly via an event filter on the shared scene (see eventFilter
    # below and _placing_state).
    #
    # pos()/p1_local are in the anchor's coordinate space: scene pixels for
    # 'figure'/'border', data units for 'axes'. _add_annotation_to_scene /
    # _detach_/_reattach_annotation funnel all anchor-dependent bookkeeping
    # through one place.

    def _annotations_on(self, plot_item):
        return [a for a in self.annotations if a.parent_plot is plot_item and a.anchor in ('border', 'axes')]

    def _set_placing_cursor(self, on):
        """Push/pop the crosshair override cursor used while placing an
        annotation or relinking one. Checks Qt's own override-cursor stack
        (QApplication.overrideCursor()) rather than a hand-tracked flag, and
        pops in a loop when turning off -- self-healing against any missed
        push/pop pairing elsewhere (e.g. an exception, or a modal dialog
        popped up mid-placement) instead of silently leaving the crosshair
        stuck once the mismatch happens."""
        if on:
            if QtWidgets.QApplication.overrideCursor() is None:
                QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))
        else:
            while QtWidgets.QApplication.overrideCursor() is not None:
                QtWidgets.QApplication.restoreOverrideCursor()

    def start_placing_annotation(self, kind):
        self._cancel_relink()
        self._deselect_all()
        self._placing_kind = kind
        self._placing_state = None
        self._set_placing_cursor(True)

    def _cancel_placing(self):
        self._placing_kind = None
        self._placing_state = None
        self._set_placing_cursor(False)

    def _annotation_zone(self, scene_pos):
        """Which parent a click at `scene_pos` implies: a subplot's data
        area (axes-anchored), a subplot's chrome/margins (border-anchored),
        or nowhere in particular (figure-anchored, free-floating)."""
        for p in self.plots:
            if p.getViewBox().sceneBoundingRect().contains(scene_pos):
                return 'axes', p
        for p in self.plots:
            if p.sceneBoundingRect().contains(scene_pos):
                return 'border', p
        return 'figure', None

    def _handle_placement_click(self, scene_pos):
        """Single-click placement for point kinds (cursor, text). Extent
        kinds (TWO_CLICK_KINDS) are placed by a press-drag-release gesture
        instead -- see eventFilter -- so they never reach here; guarded by
        _on_scene_clicked, which only calls this for non-extent kinds."""
        kind = self._placing_kind
        anchor, parent_plot = self._annotation_zone(scene_pos)
        if kind == 'cursor':
            if anchor != 'axes':
                return  # a data cursor needs a subplot's data axes -- ignore clicks elsewhere
            data_pos = parent_plot.getViewBox().mapSceneToView(scene_pos)
            curve = self._active_curve_on(parent_plot)
            if curve is not None and curve.xData is not None and curve.xData.size:
                idx = int(np.argmin(np.abs(curve.xData - data_pos.x())))
                x, y = float(curve.xData[idx]), float(curve.yData[idx])
            else:
                x, y = data_pos.x(), data_pos.y()
            self._create_annotation('cursor', 'axes', parent_plot, QtCore.QPointF(x, y),
                                     None, text=f"{x:.4g}, {y:.4g}")
            self._cancel_placing()
            return

        p0 = (parent_plot.getViewBox().mapSceneToView(scene_pos) if anchor == 'axes'
              else QtCore.QPointF(scene_pos))
        text = ''
        if kind == 'text':
            text, ok = QtWidgets.QInputDialog.getText(
                None, "Add text", "Text:", QtWidgets.QLineEdit.Normal, "Text"
            )
            if not ok:
                self._cancel_placing()
                return
        self._create_annotation(kind, anchor, parent_plot, p0, None, text)
        self._cancel_placing()

    def eventFilter(self, obj, event):
        """Intercept raw press/move/release on the shared scene to place
        TWO_CLICK_KINDS (rect/ellipse/line/arrow/doublearrow/textarrow) via
        a single press-drag-release gesture, MATLAB-style, instead of two
        separate clicks. This can't be done through sigMouseClicked (used
        for every other click-driven interaction -- see _on_scene_clicked)
        because pyqtgraph's GraphicsScene only emits that signal for a
        genuine *click* (a release near the press point); a real
        click-and-drag never fires it at all. Returning True here consumes
        the event outright, so nothing else (a curve's own clickable
        handling, the ViewBox, subplot selection) reacts to it while a
        shape is being placed. A press+release with negligible movement
        (a plain click, no drag) falls back to the shape's default extent
        -- from AnnotationItem.__init__ -- so a single click still places
        something reasonable, matching the point-kind (text/cursor) gesture."""
        if obj is self.layout_widget.scene() and self._placing_kind in TWO_CLICK_KINDS:
            etype = event.type()
            if etype == QtCore.QEvent.GraphicsSceneMousePress:
                if event.button() != QtCore.Qt.LeftButton:
                    return True
                anchor, parent_plot = self._annotation_zone(event.scenePos())
                p0 = (parent_plot.getViewBox().mapSceneToView(event.scenePos()) if anchor == 'axes'
                      else QtCore.QPointF(event.scenePos()))
                self._placing_state = {
                    'anchor': anchor, 'parent_plot': parent_plot, 'p0': p0,
                    'press_scene_pos': QtCore.QPointF(event.scenePos()),
                }
                return True
            if etype == QtCore.QEvent.GraphicsSceneMouseMove and self._placing_state is not None:
                return True
            if etype == QtCore.QEvent.GraphicsSceneMouseRelease and self._placing_state is not None:
                state = self._placing_state
                anchor, parent_plot, p0 = state['anchor'], state['parent_plot'], state['p0']
                delta = event.scenePos() - state['press_scene_pos']
                if abs(delta.x()) < 3 and abs(delta.y()) < 3:
                    p1_local = None
                else:
                    p1 = (parent_plot.getViewBox().mapSceneToView(event.scenePos()) if anchor == 'axes'
                          else QtCore.QPointF(event.scenePos()))
                    p1_local = p1 - p0
                kind = self._placing_kind
                text = ''
                if kind == 'textarrow':
                    text, ok = QtWidgets.QInputDialog.getText(
                        None, "Add text", "Text:", QtWidgets.QLineEdit.Normal, "Text"
                    )
                    if not ok:
                        self._cancel_placing()
                        return True
                self._create_annotation(kind, anchor, parent_plot, p0, p1_local, text)
                self._cancel_placing()
                return True
        return super().eventFilter(obj, event)

    def _create_annotation(self, kind, anchor, parent_plot, p0, p1_local, text=''):
        pen = pg.mkPen('k', width=2)
        pen.setCosmetic(True)
        ann = AnnotationItem(self, kind, anchor, parent_plot, pen=pen, brush=None, text=text)
        if p1_local is not None:
            ann.p1_local = QtCore.QPointF(p1_local)
            if ann._end_handle is not None:
                ann._end_handle.setPos(ann.p1_local)
            if ann._rotate_handle is not None:
                ann._position_rotate_handle()
        if anchor == 'border' and parent_plot is not None:
            ann.anchor_offset = p0 - parent_plot.sceneBoundingRect().topLeft()
        self._add_annotation_to_scene(ann, p0)
        self._select_annotation(ann)

        snapshot = ann.to_dict()
        holder = {'ann': ann}

        def undo_fn():
            a = holder.get('ann')
            if a is not None:
                self._purge_annotation(a)

        def redo_fn():
            a = AnnotationItem.from_dict(self, parent_plot, snapshot)
            holder['ann'] = a
            self._select_annotation(a)

        self._push_history(undo_fn, redo_fn)
        return ann

    def _add_annotation_to_scene(self, ann, local_pos):
        """Place `ann` into its anchor's coordinate parent: the shared
        scene directly for 'figure'/'border' (scene-pixel coordinates), or
        the parent PlotItem's ViewBox for 'axes' (data coordinates, so it
        pans/zooms with the plot for free). `ann.anchor_offset` must
        already be correct for a 'border' annotation before calling this --
        it's the source of truth for where a border annotation sits, not
        `local_pos` (which _reposition_annotations can't reliably supply
        after a subplot has been resized/moved, or when landing in a
        differently-sized subplot via paste)."""
        if ann.anchor == 'axes':
            ann.parent_plot.addItem(ann)
            ann.setPos(local_pos)
        else:
            self.layout_widget.scene().addItem(ann)
            if ann.anchor == 'border' and ann.parent_plot is not None:
                self._place_border_annotation(ann)
            else:
                ann.setPos(local_pos)
        if ann not in self.annotations:
            self.annotations.append(ann)

    def _place_border_annotation(self, ann):
        if ann.parent_plot in self.plots:
            ann.setPos(ann.parent_plot.sceneBoundingRect().topLeft() + ann.anchor_offset)

    def _reposition_annotations(self):
        for a in self.annotations:
            if a.anchor == 'border':
                self._place_border_annotation(a)

    def _detach_annotation(self, ann):
        if ann.anchor == 'axes' and ann.parent_plot is not None:
            ann.parent_plot.removeItem(ann)
        elif ann.scene() is not None:
            ann.scene().removeItem(ann)

    def _purge_annotation(self, ann):
        """Remove `ann` for good without pushing its own undo entry --
        used when a whole subplot that owns it is itself being deleted/
        recreated as one undo step (see _remove_subplot)."""
        if ann in self.selected_annotations:
            ann.set_selected(False)
            self._forget_annotation_selection(ann)
        self._detach_annotation(ann)
        if ann in self.annotations:
            self.annotations.remove(ann)

    def delete_annotation(self, ann):
        """Right-click 'Delete' / Del key on a selected annotation."""
        snapshot = ann.to_dict()
        parent_plot = ann.parent_plot
        self._purge_annotation(ann)
        holder = {}

        def undo_fn():
            a = AnnotationItem.from_dict(self, parent_plot, snapshot)
            holder['ann'] = a
            self._select_annotation(a)

        def redo_fn():
            a = holder.get('ann')
            if a is not None:
                self._purge_annotation(a)

        self._push_history(undo_fn, redo_fn)

    def _select_annotation(self, ann, additive=False):
        """additive = Shift: toggle `ann` in/out of the selection, keeping
        everything else selected. Otherwise select only `ann`."""
        if not additive:
            self._clear_selection()
            self._mark_active(self.active_plot, keep_selection=True)
        elif ann in self.selected_annotations:
            ann.set_selected(False)
            self._forget_annotation_selection(ann)
            return
        self.selected_annotations.append(ann)
        self.active_annotation = ann
        ann.set_selected(True)

    def _deselect_annotation(self):
        for a in self.selected_annotations:
            a.set_selected(False)
        self.selected_annotations = []
        self.active_annotation = None

    def _forget_annotation_selection(self, ann):
        if ann in self.selected_annotations:
            self.selected_annotations.remove(ann)
        if ann is self.active_annotation:
            self.active_annotation = self.selected_annotations[-1] if self.selected_annotations else None

    def _edit_annotation_properties(self, ann):
        """Right-click 'Properties...': line color/width, and for
        rect/ellipse an optional fill color -- the CLAUDE.md-specified
        'right-click properties menu (line/fill/color)'. Applies to every
        selected annotation if `ann` is one of them; dialogs are seeded
        from `ann`, and the fill only touches rect/ellipse targets."""
        targets = list(self.selected_annotations) if ann in self.selected_annotations else [ann]
        color = QtWidgets.QColorDialog.getColor(ann.pen.color(), None, "Line color")
        if not color.isValid():
            return
        width, ok = QtWidgets.QInputDialog.getDouble(
            None, "Line width", "Width:", ann.pen.widthF(), 0.5, 20.0, 1
        )
        if not ok:
            return
        new_pen = pg.mkPen(color=color, width=width)
        new_pen.setCosmetic(True)
        new_fill = None
        if any(t.kind in ('rect', 'ellipse') for t in targets):
            answer = QtWidgets.QMessageBox.question(
                None, "Fill", "Set a fill color? (No keeps the current fill, if any)",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if answer == QtWidgets.QMessageBox.Yes:
                default = ann.brush.color() if ann.brush else QtGui.QColor(color.red(), color.green(), color.blue(), 60)
                fill_color = QtWidgets.QColorDialog.getColor(
                    default, None, "Fill color", QtWidgets.QColorDialog.ShowAlphaChannel
                )
                if fill_color.isValid():
                    new_fill = pg.mkBrush(fill_color)

        def apply(target, pen, brush):
            target.pen = pen
            target.brush = brush
            if target._text_item is not None:
                target._text_item.setDefaultTextColor(pen.color())
            target.update()

        with self.undo_group():
            for t in targets:
                old_pen, old_brush = t.pen, t.brush
                new_brush = new_fill if (new_fill is not None and t.kind in ('rect', 'ellipse')) else old_brush
                apply(t, new_pen, new_brush)
                self._push_history(
                    undo_fn=lambda t=t, p=old_pen, b=old_brush: apply(t, p, b),
                    redo_fn=lambda t=t, p=new_pen, b=new_brush: apply(t, p, b),
                )

    # -- reparenting ("filiation"): right-click an annotation -> Link to...
    # -> click its new parent (a subplot, or empty space for free-floating)
    def _start_relink(self, ann):
        self._cancel_placing()
        self._relink_source = ann
        self._set_placing_cursor(True)

    def _cancel_relink(self):
        self._relink_source = None
        self._set_placing_cursor(False)

    def _handle_relink_click(self, scene_pos):
        ann = self._relink_source
        self._relink_source = None
        self._set_placing_cursor(False)
        anchor, parent_plot = self._annotation_zone(scene_pos)
        if ann.kind == 'cursor' and anchor != 'axes':
            return  # a data cursor must stay tied to some subplot's data axes
        self._reparent_annotation(ann, anchor, parent_plot, scene_pos)

    def _reattach_annotation(self, ann, anchor, parent_plot, local_pos):
        """local_pos must already be in the coordinate space `anchor`
        implies -- scene pixels for figure/border, data units for axes."""
        ann.anchor = anchor
        ann.parent_plot = parent_plot
        if anchor == 'border' and parent_plot is not None:
            ann.anchor_offset = local_pos - parent_plot.sceneBoundingRect().topLeft()
        self._add_annotation_to_scene(ann, local_pos)

    def _reparent_annotation(self, ann, new_anchor, new_parent_plot, scene_pos):
        old_anchor, old_parent_plot, old_local_pos = ann.anchor, ann.parent_plot, ann.pos()
        new_local_pos = (new_parent_plot.getViewBox().mapSceneToView(scene_pos) if new_anchor == 'axes'
                          else QtCore.QPointF(scene_pos))

        def undo_fn():
            self._detach_annotation(ann)
            self._reattach_annotation(ann, old_anchor, old_parent_plot, old_local_pos)
            self._select_annotation(ann)

        def redo_fn():
            self._detach_annotation(ann)
            self._reattach_annotation(ann, new_anchor, new_parent_plot, new_local_pos)
            self._select_annotation(ann)

        redo_fn()
        self._push_history(undo_fn, redo_fn)
