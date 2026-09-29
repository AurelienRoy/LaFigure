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

"""Right-click menus: the per-subplot menu (extending pyqtgraph's own
ViewBox menu), the per-curve menu, and the minimal empty-space menu
(Paste Subplot).

A right-click on a curve reaches the ViewBox, not the curve
(PlotCurveItem.mouseClickEvent handles the left button only), so
_wire_context_menu wraps the ViewBox's raiseContextMenu: when the click
hit-tests onto a curve, that curve's own menu opens instead. Each menu
starts with a disabled header naming what it acts on. Subplot-level
actions (copy/paste subplot, FFT, CSV, z-order of the subplot) live only
in the subplot menu; curve-level ones (copy/paste curve, curve z-order,
display style) only in the curve menu.
"""
import csv

from pyqtgraph.Qt import QtGui, QtWidgets
import pyqtgraph as pg

from .curve_style import (LINE_STYLES, LINE_WIDTHS, MARKERS, MARKER_SIZES,
                          line_options_apply, marker_options_apply, pen_style_of)


def _menu_header(menu, text, before=None):
    """A disabled, bold first entry naming what the menu acts on."""
    header = QtGui.QAction(text, menu)
    header.setEnabled(False)
    font = header.font()
    font.setBold(True)
    header.setFont(font)
    if before is None:
        menu.addAction(header)
        menu.addSeparator()
    else:
        menu.insertAction(before, header)
        menu.insertSeparator(before)
    return header


class MenusMixin:
    def _wire_context_menu(self, plot_item):
        """Extend PyQtGraph's built-in right-click menu with app-specific
        actions. Right-clicking also makes this the focused subplot, same
        as a left click does.

        pyqtgraph's own "View All" and "Plot Options" stay; "X axis",
        "Y axis" and "Mouse Mode" are removed below -- their range dialogs
        and mouse-mode switching are redundant with this app's own
        Select/Hand/Zoom-Rect toolbar modes. "Export..." is never actually
        present on `menu` at this point (pyqtgraph's GraphicsScene only
        splices it in live, on every real right-click, via
        ViewBox.raiseContextMenu -> Scene.addParentContextMenus, *before*
        popup() fires this menu's own aboutToShow) -- so it's pruned in the
        aboutToShow handler below, right alongside the trailing separator
        pyqtgraph adds with it every time (else that separator would
        accumulate, one more per right-click, forever)."""
        menu = plot_item.getViewBox().menu
        for title in ("X axis", "Y axis", "Mouse Mode"):
            stale = next(
                (a for a in menu.actions() if a.menu() is not None and a.menu().title() == title),
                None,
            )
            if stale is not None:
                menu.removeAction(stale)
        header = _menu_header(menu, "Subplot", before=menu.actions()[0])
        # pyqtgraph's View All is a zoom like Home: make it undoable too.
        vb = plot_item.getViewBox()
        menu.viewAll.triggered.disconnect()
        menu.viewAll.triggered.connect(lambda: self._undoable_view_change(vb.autoRange))
        menu.addSeparator()

        def bound(fn):
            return lambda: (self._on_plot_context(plot_item), fn())

        menu.addAction("Copy Subplot").triggered.connect(bound(self.copy_subplot))
        menu.addAction("Paste Subplot").triggered.connect(bound(self.paste_subplot))
        # Pastes onto this subplot -- the only menu path onto an empty one.
        paste_curve_action = menu.addAction("Paste Curve")
        paste_curve_action.triggered.connect(bound(self.paste_curve))
        menu.addAction("Bring Subplot to Front").triggered.connect(
            bound(lambda: self.bring_to_front(plot_item)))
        menu.addAction("Send Subplot to Back").triggered.connect(
            bound(lambda: self.send_to_back(plot_item)))
        menu.addAction("Toggle Legend").triggered.connect(bound(self.toggle_legend))
        menu.addAction("Reorder Curves...").triggered.connect(
            bound(lambda: self.open_curve_browser(plot_item)))
        menu.addAction("Remove Average").triggered.connect(bound(self.remove_average))
        menu.addAction("FFT -> Subplot Below").triggered.connect(bound(self.fft_below))
        menu.addAction("Export to CSV...").triggered.connect(
            bound(lambda: self._prompt_export_csv(plot_item))
        )

        menu.addSeparator()
        delete_pts_action = menu.addAction("Delete Selected Points")
        delete_pts_action.triggered.connect(bound(self.delete_brushed_points))
        transform_action = menu.addAction("Transform Selected Points...")
        transform_action.triggered.connect(bound(self.transform_brushed_points))
        stats_action = menu.addAction("Selection Stats...")
        stats_action.triggered.connect(bound(self.show_selection_stats))
        fit_menu = menu.addMenu("Fit Selected Points")
        fit_menu.addAction("Linear").triggered.connect(
            bound(lambda: self.fit_brushed_points(plot_item, degree=1))
        )
        fit_menu.addAction("Polynomial...").triggered.connect(
            bound(lambda: self.fit_brushed_points(plot_item, degree=None))
        )
        hide_pts_action = menu.addAction("Hide Brushed Points")
        hide_pts_action.triggered.connect(bound(self.hide_brushed_points))
        # These five act on the figure-wide brushed selection (see
        # brushing.py) -- shown only while Brush mode is on, and disabled
        # (not hidden) when nothing is currently brushed, since both can
        # change after this menu was built.
        brush_actions = [delete_pts_action, transform_action, stats_action, fit_menu.menuAction(),
                         hide_pts_action]
        # Always shown: hidden rows outlive Brush mode.
        show_all_action = menu.addAction("Show All Points")
        show_all_action.triggered.connect(bound(self.show_all_hidden_points))

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

        def update_brush_actions():
            has_selection = bool(self._figure_brush_items())
            for action in brush_actions:
                action.setVisible(self.brushing)
                action.setEnabled(self.brushing and has_selection)
            show_all_action.setEnabled(self.has_hidden_points())

        def prune_pyqtgraph_export():
            actions = menu.actions()
            while actions and actions[-1].text() == "Export...":
                menu.removeAction(actions[-1])
                actions = menu.actions()
            while actions and actions[-1].isSeparator():
                menu.removeAction(actions[-1])
                actions = menu.actions()

        def on_about_to_show():
            self._on_plot_context(plot_item)
            header.setText("Subplot: " + (self.subplot_name(plot_item) or "(untitled)"))
            paste_curve_action.setEnabled(bool(self.clipboard.curve))
            rebuild_curve_menus()
            update_brush_actions()
            prune_pyqtgraph_export()

        menu.aboutToShow.connect(on_about_to_show)

        native_raise = vb.raiseContextMenu

        def raise_context_menu(ev):
            # An annotation's own contextMenuEvent (a native Qt event,
            # independent of this ViewBox-level dispatch) already handles
            # a right-click on it -- without this check, both menus opened
            # at once. Checked in every mode, including Brush: the
            # annotation menu should still win there too.
            if self._annotation_at(ev.scenePos()) is not None:
                return
            # Brush mode keeps the subplot menu everywhere: its brushed-point
            # actions are what a right-click on brushed points is for.
            curve = None
            if self.interaction_mode != 'brush' and self._placing_kind is None:
                curve = self._curve_at(plot_item, ev.scenePos())
            if curve is None:
                native_raise(ev)
                return
            self._curve_context_menu(plot_item, curve).popup(ev.screenPos().toPoint())

        vb.raiseContextMenu = raise_context_menu

    # -- the curve menu ----------------------------------------------------
    def _curve_at(self, plot_item, scene_pos):
        """The topmost clickable curve under scene_pos, or None. Same hit
        area as a left click (the curve's mouseShape), plus a scatter's
        markers."""
        items = [c for c in plot_item.listDataItems()
                 if isinstance(c, pg.PlotDataItem) and c.isVisible()]
        order = {c: i for i, c in enumerate(items)}
        for c in sorted(items, key=lambda c: (c.zValue(), order[c]), reverse=True):
            if c.curve.mouseShape().contains(c.curve.mapFromScene(scene_pos)):
                return c
            if (c.opts.get('symbol') is not None
                    and len(c.scatter.pointsAt(c.scatter.mapFromScene(scene_pos)))):
                return c
        return None

    def _curve_menu_targets(self, plot_item, curve):
        """Right-click on a curve: keep a curve selection containing it (the
        menu acts on the whole set), else select just this curve (Select
        mode) -- same rule as right-clicking a subplot."""
        self.focused_plot = plot_item
        if curve in self.selected_curves:
            return list(self.selected_curves)
        if self.interaction_mode == 'select':
            self._select_curve(curve)
            self._mark_active(plot_item, keep_selection=True)
        return [curve]

    def _curve_context_menu(self, plot_item, curve):
        """Build (not show) the right-click menu of `curve`."""
        targets = self._curve_menu_targets(plot_item, curve)
        menu = QtWidgets.QMenu(self)
        label = curve.name() or "(unnamed curve)"
        if len(targets) > 1:
            label += f" (+{len(targets) - 1} more)"
        _menu_header(menu, "Curve: " + label)

        def paste():
            self.focused_plot = plot_item
            self.paste_curve()

        menu.addAction("Copy Curve").triggered.connect(lambda: self.copy_curve())
        paste_action = menu.addAction("Paste Curve")
        paste_action.setEnabled(bool(self.clipboard.curve))
        paste_action.triggered.connect(paste)
        menu.addAction("Bring to Front").triggered.connect(lambda: self.curves_to_front(targets, True))
        menu.addAction("Send to Back").triggered.connect(lambda: self.curves_to_front(targets, False))
        menu.addSeparator()

        state = self._curve_style_state(curve)
        kind = self._curve_kind(curve)
        has_line = line_options_apply(kind)
        has_marker = marker_options_apply(kind)
        pen = pg.mkPen(state['pen']) if state['pen'] is not None else None

        def choices(title, entries, current, setter, enabled=True):
            sub_menu = menu.addMenu(title)
            sub_menu.setEnabled(enabled)
            group = QtWidgets.QActionGroup(sub_menu)
            for text, value in entries:
                act = sub_menu.addAction(text)
                act.setCheckable(True)
                act.setChecked(value == current)
                group.addAction(act)
                act.triggered.connect(lambda checked=False, v=value: setter(targets, v))
            return sub_menu

        width = pen.widthF() if pen is not None else None
        choices("Line Width", [(f"{w:g}", w) for w in LINE_WIDTHS], width,
                self.set_curve_line_width, has_line)
        choices("Line Style", [(f"{text}  ({code})" if code != 'none' else text, code)
                               for text, code, _ in LINE_STYLES],
                pen_style_of(state['pen']), self.set_curve_line_style, has_line)
        choices("Marker", [(f"{text}  ({code})" if code != 'none' else text, symbol)
                           for text, code, symbol in MARKERS],
                state['symbol'], self.set_curve_marker, has_marker)
        choices("Marker Size", [(f"{s:g}", s) for s in MARKER_SIZES], state['symbolSize'],
                self.set_curve_marker_size, has_marker and state['symbol'] is not None)
        menu.addSeparator()

        menu.addAction("Rename Curve...").triggered.connect(
            lambda: self._rename_curve(plot_item, curve))

        def delete():
            with self.undo_group():
                for c in targets:
                    self.delete_curve(c)

        menu.addAction("Delete Curve" if len(targets) == 1 else "Delete Curves").triggered.connect(delete)
        return menu

    # -- Reorder Curves... -------------------------------------------------
    def open_curve_browser(self, plot_item=None):
        """Bring the Figure Manager forward on its Curve Browser tab, showing
        plot_item (default: the focused subplot) -- creating the manager if
        none is open."""
        from .manager import FigureManager   # manager imports figures' modules
        plot_item = plot_item if plot_item is not None else self.focused_plot
        if plot_item is not None:
            self.focused_plot = plot_item
        manager = getattr(self.registry, 'manager', None)
        if manager is None:
            manager = FigureManager()
        manager.show_curve_browser(self, plot_item)
        return manager

    def _export_subplot_csv(self, plot_item, path):
        """Write plot_item's curves to a CSV file: two columns per curve,
        "<name> x"/"<name> y" (or "curve N x"/"curve N y" if unnamed), from
        each curve's full xData/yData -- never the downsampled, clipped-to-
        view display data (same principle as view_ops._fit_view). Curves of
        different lengths are padded with empty cells to the longest one.
        Kept separate from the QFileDialog prompt so it's testable without
        driving the real dialog."""
        curves = [c for c in plot_item.listDataItems() if isinstance(c, pg.PlotDataItem)]
        columns = []
        for i, curve in enumerate(curves, start=1):
            name = curve.name() or f"curve {i}"
            x, y = curve.xData, curve.yData
            columns.append((f"{name} x", [] if x is None else list(x)))
            columns.append((f"{name} y", [] if y is None else list(y)))
        max_len = max((len(data) for _, data in columns), default=0)
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([header for header, _ in columns])
            for row_i in range(max_len):
                writer.writerow(
                    [data[row_i] if row_i < len(data) else "" for _, data in columns]
                )

    def _prompt_export_csv(self, plot_item):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export to CSV", "", "CSV Files (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        self._export_subplot_csv(plot_item, path)

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
