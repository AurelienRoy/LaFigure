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

"""View state and per-subplot data actions: interaction mode
(Select/Hand/Zoom Rect/Rotate + Zoom/Brush), Home / Fit Vertical / Fit
Horizontal, legend (show/hide, select, move), view history (every zoom/pan
gesture is one undo entry), Link X, Remove Average, FFT -> subplot below,
axis Scale (X/Y linear/log), and the 3D-only camera actions (view presets,
projection) a 3D subplot's right-click menu (menus.py) calls into.
"""
import logging
import math

import numpy as np
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .datasource import DataSource
from .editable_text import wire_legend_editable
from .selection_ui import selection_op
from .transform import Transform, transform_applies
from .view3d import View3DBox

logger = logging.getLogger('lafigure.view_ops')

# Qt has no built-in "magnifying glass" cursor shape, so Zoom Rect gets a
# drawn one (same technique as toolbar.py's _fit_icon): a lens with a "+"
# inside, a handle, cached once since it never changes.
_ZOOM_CURSOR = None


def _zoom_cursor():
    global _ZOOM_CURSOR
    if _ZOOM_CURSOR is None:
        size = 24
        pix = QtGui.QPixmap(size, size)
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(40, 40, 40), 1.6)
        painter.setPen(pen)
        # Lens: circle centered at (9, 9), radius 6.
        cx, cy, r = 9, 9, 6
        painter.drawEllipse(QtCore.QPointF(cx, cy), r, r)
        # "+" inside the lens.
        painter.drawLine(QtCore.QPointF(cx - 3, cy), QtCore.QPointF(cx + 3, cy))
        painter.drawLine(QtCore.QPointF(cx, cy - 3), QtCore.QPointF(cx, cy + 3))
        # Handle, from the lens's lower-right edge out to the corner.
        painter.setPen(QtGui.QPen(QtGui.QColor(40, 40, 40), 2.2))
        hx, hy = cx + r * 0.7, cy + r * 0.7
        painter.drawLine(QtCore.QPointF(hx, hy), QtCore.QPointF(size - 2, size - 2))
        painter.end()
        # Hotspot at the lens center: that's the point actually being
        # zoomed into, same convention as a real magnifier cursor.
        _ZOOM_CURSOR = QtGui.QCursor(pix, cx, cy)
    return _ZOOM_CURSOR


_ROTATE_CURSOR = None


def _rotate_cursor():
    """Rotate + Zoom mode's cursor: a circular orbit arrow, same drawn-
    cursor technique as _zoom_cursor (Qt has no built-in shape for this
    either), cached once."""
    global _ROTATE_CURSOR
    if _ROTATE_CURSOR is None:
        size = 24
        pix = QtGui.QPixmap(size, size)
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor(40, 40, 40), 1.8))
        cx, cy, r = 12, 12, 8
        rect = QtCore.QRectF(cx - r, cy - r, 2 * r, 2 * r)
        # A near-full circle (Qt angles: 1/16th of a degree, counterclockwise
        # from 3 o'clock), leaving a gap where the arrowhead sits.
        start_deg = 20.0
        painter.drawArc(rect, int(start_deg * 16), int(290 * 16))
        # Arrowhead at the arc's start point, pointing along the tangent
        # there (the direction the arc continues in, i.e. of travel).
        a = math.radians(start_deg)
        tip = QtCore.QPointF(cx + r * math.cos(a), cy - r * math.sin(a))
        tangent = a + math.pi / 2
        for da in (0.5, -0.5):
            wing = tip - QtCore.QPointF(6 * math.cos(tangent + da), -6 * math.sin(tangent + da))
            painter.drawLine(tip, wing)
        painter.end()
        _ROTATE_CURSOR = QtGui.QCursor(pix, cx, cy)
    return _ROTATE_CURSOR


_ZOOM_DRAG_CURSOR = None


def _zoom_drag_cursor():
    """Shown during a right-button drag in Zoom Rect mode -- pyqtgraph's
    dynamic zoom, which scales each axis by the drag (right/up = in,
    left/down = out). A lens with "±" inside, plus small horizontal and
    vertical double arrows for the two axes being scaled."""
    global _ZOOM_DRAG_CURSOR
    if _ZOOM_DRAG_CURSOR is None:
        size = 32
        pix = QtGui.QPixmap(size, size)
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        ink = QtGui.QColor(40, 40, 40)
        painter.setPen(QtGui.QPen(ink, 1.6))
        cx, cy, r = 11, 11, 7
        painter.drawEllipse(QtCore.QPointF(cx, cy), r, r)
        # "±": a plus above a minus.
        painter.drawLine(QtCore.QPointF(cx - 2.5, cy - 2), QtCore.QPointF(cx + 2.5, cy - 2))
        painter.drawLine(QtCore.QPointF(cx, cy - 4.5), QtCore.QPointF(cx, cy + 0.5))
        painter.drawLine(QtCore.QPointF(cx - 2.5, cy + 3), QtCore.QPointF(cx + 2.5, cy + 3))
        painter.setPen(QtGui.QPen(ink, 2.2))
        painter.drawLine(QtCore.QPointF(cx + 5, cy + 5), QtCore.QPointF(20, 20))
        painter.setPen(QtGui.QPen(ink, 1.3))

        def double_arrow(x0, y0, x1, y1):
            painter.drawLine(QtCore.QPointF(x0, y0), QtCore.QPointF(x1, y1))
            for (ax, ay), (bx, by) in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
                dx, dy = bx - ax, by - ay
                n = max((dx * dx + dy * dy) ** 0.5, 1e-9)
                ux, uy = dx / n, dy / n
                for sx, sy in ((uy, -ux), (-uy, ux)):
                    painter.drawLine(QtCore.QPointF(ax, ay),
                                     QtCore.QPointF(ax + 3 * ux + 2.5 * sx, ay + 3 * uy + 2.5 * sy))

        double_arrow(2, 28, 14, 28)     # horizontal, bottom-left
        double_arrow(28, 2, 28, 14)     # vertical, top-right
        painter.end()
        _ZOOM_DRAG_CURSOR = QtGui.QCursor(pix, cx, cy)
    return _ZOOM_DRAG_CURSOR


class _ViewHistoryFilter(QtCore.QObject):
    """Observe-only scene event filter for view history (never consumes).
    Installed after LaFigure's own scene filter, so Qt calls it first and
    it sees every press/move/release/wheel before anything can consume one."""

    def __init__(self, figure):
        super().__init__(figure)
        self.figure = figure

    def eventFilter(self, obj, ev):
        self.figure._view_history_event(ev)
        return False


class ViewOpsMixin:
    WHEEL_SETTLE_MS = 400   # wheel ticks closer than this are one zoom gesture

    # -- interaction mode ------------------------------------------------
    @staticmethod
    def _cursor_for_mode(mode):
        if mode == 'hand':
            return QtCore.Qt.OpenHandCursor
        if mode == 'zoom':
            return _zoom_cursor()
        if mode == 'rotate':
            return _rotate_cursor()
        if mode == 'brush':
            return QtCore.Qt.CrossCursor
        return QtCore.Qt.ArrowCursor

    def _apply_view_mouse_mode(self, vb):
        """Set a ViewBox's pan/rect mouse mode from self.interaction_mode,
        and style Zoom Rect's drag rectangle light gray instead of
        pyqtgraph's yellow. Also the one place that tells a 3D cell
        (View3DBox) the figure's current mode (R4-3D) -- called on every
        mode change AND on that cell's own construction (add_subplot),
        exactly like _apply_mouse_enabled below, so a 3D cell created
        while already in Zoom Rect mode gets rect-zoom immediately too.

        The rbScaleBox styling must follow every setMouseMode: pyqtgraph's
        setMouseMode(PanMode) drops its rbScaleBox, and the next access
        lazily builds a fresh, yellow one -- so a box styled once at
        subplot creation (the first version of this) never survived to the
        first zoom drag. Styled only in RectMode: touching rbScaleBox in
        PanMode would just build a box that the next setMouseMode drops.
        A 3D cell's own View3DBox.mouseDragEvent draws through this same
        rbScaleBox in Zoom Rect mode (view3d.py), so it gets this styling
        for free -- setMouseMode itself is otherwise a no-op there (the
        cell never consults state['mouseMode'])."""
        if isinstance(vb, View3DBox):
            vb.interaction_mode = self.interaction_mode
        if self.interaction_mode == 'zoom':
            vb.setMouseMode(pg.ViewBox.RectMode)
            vb.rbScaleBox.setPen(pg.mkPen((140, 140, 140), width=1))
            vb.rbScaleBox.setBrush(pg.mkBrush(200, 200, 200, 90))
        else:
            vb.setMouseMode(pg.ViewBox.PanMode)

    @selection_op
    def set_interaction_mode(self, mode):
        """The five exclusive toolbar modes.
        'select': click-to-select + move/resize handles, dragging inside
        a subplot does nothing (freed up for the handles).
        'hand': plain pan, no selection. 'zoom': drag-to-zoom (a real
        rectangle zoom on a 3D cell too, R4-3D), no selection.
        'rotate': "Rotate + Zoom" (R4-3D) -- a 3D cell's own orbit/pan/
        dolly camera controls (today's default 3D behavior, moved under
        its own mode); a no-op on a 2D subplot, same as 'hand' there.
        Enabled only while a 3D subplot is focused (_update_rotate_action_
        enabled, below) and switches back to 'zoom' the moment focus
        leaves every 3D subplot.
        'brush': rectangular data brushing (brushing.py), no selection, no
        pan. Brush used to be a separate on/off toggle stacked on the other
        modes; it's exclusive since 2026-09-29 (user request) -- it already
        took over the left drag and disabled pan/wheel, so no combination
        was lost. self.brushing stays, derived from the mode."""
        old_mode = self.interaction_mode
        self.interaction_mode = mode
        if mode != old_mode:
            logger.debug("mode: %s -> %s", old_mode, mode)
        brushing = mode == 'brush'
        if brushing != self.brushing:
            self.brushing = brushing
            for brusher in self._brushers.values():
                brusher.set_brushing(brushing)
        cursor = self._cursor_for_mode(mode)
        for p in self.plots:
            vb = p.getViewBox()
            self._apply_view_mouse_mode(vb)
            self._apply_mouse_enabled(vb)
            vb.setCursor(cursor)
        self._sync_mode_actions()
        if mode != 'select':
            self._deselect_curve()
            self._deselect_legend()
        if self.focused_plot is not None:
            self._mark_active(self.focused_plot, keep_selection=True)
        else:
            self._hide_handles()

    def _sync_mode_actions(self):
        """Keep the toolbar's exclusive mode buttons in step with a mode set
        from code (toggle_brush, tests, the API), not just from a click.
        self.rotate_action doesn't exist unless toolbar.py's reported diff
        has been applied (or a test attaches one directly) -- getattr's
        default keeps this a no-op either way, same as every other action
        here would be if toolbar.py somehow hadn't built it."""
        action = getattr(self, {'select': 'select_action', 'hand': 'hand_action',
                                'zoom': 'zoom_action', 'brush': 'brush_action',
                                'rotate': 'rotate_action'}[self.interaction_mode], None)
        if action is not None and not action.isChecked():
            action.setChecked(True)

    def _update_rotate_action_enabled(self):
        """Rotate + Zoom is enabled only while a 3D subplot is focused
        (R4-3D). Connected to registry.focusChanged in _install_view_history
        below, since focused_plot's setter (selection_ui.py) is the one
        emission site -- and called once there too, so a figure whose
        first focus never actually changes (e.g. nothing focused yet)
        still starts with the correct (disabled) state.

        If leaving 'rotate' mode's only valid target (focus moves to a 2D
        subplot, or to nothing) the mode itself falls back to 'zoom' --
        the user's own explicit rule, not just disabling the button."""
        action = getattr(self, 'rotate_action', None)
        if action is None:
            return
        p = self.focused_plot
        is_3d = p is not None and getattr(p, 'axes_type', 'cartesian') == '3d'
        action.setEnabled(is_3d)
        if not is_3d and self.interaction_mode == 'rotate':
            self.set_interaction_mode('zoom')

    def _on_focus_changed_for_rotate_mode(self, fig, plot_item):
        if fig is self:
            self._update_rotate_action_enabled()

    # -- Home / Fit Vertical / Fit Horizontal ------------------------------
    def reset_view(self):
        """Acts on whichever subplot the mouse was most recently over
        (self._hover_plot), not the click-selected self.focused_plot --
        Hand/Zoom-mode panning never clicks a subplot, so focused_plot can
        be stale while the user has clearly been working in a different
        one. Falls back to focused_plot before any hover has been seen."""
        p = self._hover_plot or self.focused_plot
        if p is None:
            return
        self._undoable_view_change(p.getViewBox().autoRange)

    CLICK_ZOOM_FACTOR = 3.0  # a plain click in Zoom Rect mode zooms by this factor

    def _click_zoom(self, plot_item, scene_pos, out=False):
        """Zoom Rect mode's plain-click behavior (_on_scene_clicked):
        zoom in to 1/CLICK_ZOOM_FACTOR of the current view on a single
        click, or out to CLICK_ZOOM_FACTOR x it on a double-click --
        centered on the clicked DATA point, not the view's own center,
        matching a normal "click to zoom in here" gesture. One undo
        entry, same mechanism Home/Fit/View All use."""
        vb = plot_item.getViewBox()
        factor = self.CLICK_ZOOM_FACTOR if out else (1.0 / self.CLICK_ZOOM_FACTOR)
        center = vb.mapSceneToView(scene_pos)
        (x0, x1), (y0, y1) = vb.viewRange()

        def scaled(lo, hi, c):
            half = (hi - lo) / 2 * factor
            return c - half, c + half

        new_x, new_y = scaled(x0, x1, center.x()), scaled(y0, y1, center.y())
        self._undoable_view_change(lambda: vb.setRange(xRange=new_x, yRange=new_y, padding=0))

    def fit_view_vertical(self):
        """Stretch Y to the min/max of the data whose x lies in the current
        X range -- the curves as currently shown, not their full extent."""
        self._fit_view(axis=1)

    def fit_view_horizontal(self):
        """Stretch X to the min/max of the data whose y lies in the current
        Y range."""
        self._fit_view(axis=0)

    def _fit_view(self, axis):
        """Same target subplot as reset_view. Reads each item's full data
        (xData/yData), never the downsampled, clipped-to-view display."""
        p = self._hover_plot or self.focused_plot
        if p is None:
            return
        vb = p.getViewBox()
        (x0, x1), (y0, y1) = vb.viewRange()
        lo, hi = np.inf, -np.inf
        for item in p.listDataItems():
            if not item.isVisible():
                continue
            if isinstance(item, pg.PlotDataItem):
                x, y = item.xData, item.yData
            else:
                x, y = item.getData()
            if x is None or y is None or len(x) == 0:
                continue
            x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
            if axis == 1:
                values = y[(x >= x0) & (x <= x1)]
            else:
                values = x[(y >= y0) & (y <= y1)]
            values = values[np.isfinite(values)]
            if values.size:
                lo, hi = min(lo, values.min()), max(hi, values.max())
        if not np.isfinite(lo):
            return
        if axis == 1:
            self._undoable_view_change(lambda: vb.setYRange(lo, hi))
        else:
            self._undoable_view_change(lambda: vb.setXRange(lo, hi))

    # -- legend ----------------------------------------------------------
    def toggle_legend(self):
        """Toggles independently on every selected subplot (Shift+click to
        select more than one) -- each subplot's legend flips its own
        current on/off state rather than being forced to match the others.
        A selected legend's own subplot counts as selected. View state, not
        an undo entry (CLAUDE.md, "Not covered by undo")."""
        targets = self.selected_plots if self.selected_plots else (
            [self.focused_plot] if self.focused_plot is not None else []
        )
        if not targets:
            return
        for p in targets:
            if p.legend is None:
                self._show_legend(p)
            else:
                self._hide_legend(p)

    def _show_legend(self, p):
        legend = p.addLegend()
        # pyqtgraph enters an item in the legend only as PlotItem.addItem
        # adds it, and only if a legend already exists -- so a legend
        # toggled on over existing curves was empty: zero size, invisible.
        # _refresh_legend_order (below) both populates it (by the same rule
        # PlotItem.addItem uses: named plot-data items) and applies this
        # app's own two rules on top: skip a "_"-prefixed name (matplotlib's
        # "_nolegend_" convention) and order front-most (highest zValue)
        # first, ties by creation order.
        self._refresh_legend_order(p)
        wire_legend_editable(self, p, legend)
        self._wire_legend_interaction(p, legend)
        return legend

    def _refresh_legend_order(self, plot_item=None):
        """Rebuild the legend's entries (if it has one) so they are
        z-order descending -- front-most curve first, ties broken by
        creation order -- and never include a curve whose name starts
        with "_" (matplotlib's "_nolegend_" convention for "don't show
        this in the legend"). plot_item=None refreshes every subplot that
        currently has a legend.

        Call this whenever a legend is (re)built, or after anything that
        can change what it should show or in what order: a curve's
        z-order (curve_style.curves_to_front), a curve's name (a rename,
        in or out of a "_" prefix), or a curve being added/removed while
        a legend is already showing. LegendItem has no "reorder in place"
        API, so this clears and re-adds every entry rather than trying to
        patch it incrementally."""
        plots = [plot_item] if plot_item is not None else list(self.plots)
        for p in plots:
            legend = p.legend
            if legend is None:
                continue
            creation_order = {c: i for i, c in enumerate(p.listDataItems())}
            entries = []
            for item in p.listDataItems():
                implements = getattr(item, 'implements', None)
                name = item.name() if implements is not None and implements('plotData') else None
                if name and not name.startswith('_'):
                    entries.append(item)
            entries.sort(key=lambda c: (-c.zValue(), creation_order[c]))
            for sample, _label in list(legend.items):
                legend.removeItem(sample.item)
            for item in entries:
                legend.addItem(item, item.name())

    def _hide_legend(self, p):
        if self.selected_legend is p:
            self._deselect_legend()
        legend = p.legend
        if legend.scene() is not None:
            legend.scene().removeItem(legend)
        p.legend = None

    def _wire_legend_interaction(self, p, legend):
        """A click selects the legend (Select mode); a drag moves it -- that
        part is pyqtgraph's own LegendItem.mouseDragEvent -- and each move
        is one undo entry. Both are pyqtgraph's Python-level event
        protocol, so instance attributes override them (unlike a Qt
        virtual such as wheelEvent)."""
        native_drag = legend.mouseDragEvent

        def drag(ev, p=p, legend=legend):
            left = ev.button() == QtCore.Qt.LeftButton
            if left and ev.isStart():
                # isStart() comes with the first *move* (CLAUDE.md bug #14),
                # but pos() is only changed by native_drag, below.
                legend._lafigure_drag_from = QtCore.QPointF(legend.pos())
            native_drag(ev)
            if left and ev.isFinish():
                start = getattr(legend, '_lafigure_drag_from', None)
                end = QtCore.QPointF(legend.pos())
                legend._lafigure_drag_from = None
                if start is not None and start != end:
                    self._push_history(lambda: self._place_legend(p, legend, start),
                                       lambda: self._place_legend(p, legend, end))

        def click(ev, p=p):
            if ev.button() != QtCore.Qt.LeftButton or self.interaction_mode != 'select':
                return
            ev.accept()
            self._select_legend(p)

        legend.mouseDragEvent = drag
        legend.mouseClickEvent = click

    @staticmethod
    def _place_legend(p, legend, pos):
        if p.legend is legend:
            legend.autoAnchor(pos)

    @selection_op
    def _select_legend(self, p):
        """Exclusive, like any plain click: every other selection goes."""
        self._clear_selection()
        self.selected_legend = p
        legend = p.legend
        legend._lafigure_pen = legend.opts.get('pen')
        legend.setPen(pg.mkPen((220, 0, 0), width=1.5, style=QtCore.Qt.DashLine))
        self.focused_plot = p
        self._mark_active(p, keep_selection=True)

    def _deselect_legend(self):
        p, self.selected_legend = self.selected_legend, None
        if p is not None and p.legend is not None:
            # Straight into opts: setPen(None) would store a NoPen QPen, not
            # the legend's original None (same trap as CLAUDE.md bug #15).
            p.legend.opts['pen'] = getattr(p.legend, '_lafigure_pen', None)
            p.legend.update()

    # -- view history: every zoom/pan gesture is one undo entry ----------------
    # A view change is snapshot as {plot: range} (a 3D cell: its camera)
    # before and after a gesture; unchanged -> no entry. Gestures:
    #  * any mouse gesture on the scene, press to release (rect zoom,
    #    right-drag zoom, pan, axis drags, pyqtgraph's "A" button...) --
    #    unless another undo entry was pushed meanwhile (a subplot resize,
    #    an annotation drag, a legend move...), whose gesture it then was;
    #  * a burst of wheel ticks, closed WHEEL_SETTLE_MS after the last one;
    #  * Home / Fit / View All, wrapped explicitly (not scene events).
    # Scene-level, not per-ViewBox: wheelEvent is a Qt virtual, which PyQt
    # doesn't let an instance attribute override, unlike pyqtgraph's own
    # mouseDragEvent (that RectBrush wraps).
    def _install_view_history(self):
        self._view_gesture = None   # (before snapshot, undo top) while a mouse gesture is open
        self._wheel_gesture = None
        self._wheel_timer = QtCore.QTimer(self)
        self._wheel_timer.setSingleShot(True)
        self._wheel_timer.timeout.connect(self._close_wheel_gesture)
        self._right_drag = None     # Zoom Rect right-drag: {'pos', 'active'}
        self._view_history_filter = _ViewHistoryFilter(self)
        self.layout_widget.scene().installEventFilter(self._view_history_filter)
        # R4-3D: Rotate + Zoom's enabled state tracks focus. Connected here
        # (a per-instance setup method this mixin already owns, run once
        # from __init__) rather than in figure.py, which view_ops.py
        # doesn't own -- self.registry is a process-wide singleton, so the
        # handler filters to this figure itself, same pattern axes.py's
        # module-level gcf() tracker uses for a wider (all-figures) signal.
        self.registry.focusChanged.connect(self._on_focus_changed_for_rotate_mode)
        self._update_rotate_action_enabled()

    def _view_snapshot(self):
        snap = {}
        for p in self.plots:
            if getattr(p, 'axes_type', 'cartesian') == '3d':
                snap[p] = ('3d', self._subplot_view_state(p))
            else:
                vb = p.getViewBox()
                auto = tuple(bool(a) for a in vb.state['autoRange'])
                snap[p] = ('2d', (tuple(vb.viewRange()[0]), tuple(vb.viewRange()[1]), auto))
        return snap

    @staticmethod
    def _view_changed(before, after):
        """An axis still auto-ranging on both sides moved by itself (a
        resize, a selection border, new data) -- not a user zoom."""
        if before[0] != after[0] or before[0] == '3d':
            return before != after
        (bx, by, bauto), (ax, ay, aauto) = before[1], after[1]
        return any(not (bauto[i] and aauto[i]) and (b != a or bauto[i] != aauto[i])
                   for i, (b, a) in enumerate(((bx, ax), (by, ay))))

    def _restore_view_snapshot(self, snap):
        for p, (kind, state) in snap.items():
            if p not in self.plots:
                continue
            if kind == '3d':
                self._apply_subplot_view_state(p, state)
            else:
                x_range, y_range, auto = state
                vb = p.getViewBox()
                vb.setRange(xRange=x_range, yRange=y_range, padding=0)
                for axis, on in zip((vb.XAxis, vb.YAxis), auto):
                    if on:
                        vb.enableAutoRange(axis)

    def _push_view_change(self, before, after):
        changed = [p for p, v in after.items() if p in before and self._view_changed(before[p], v)]
        if not changed:
            return
        old = {p: before[p] for p in changed}
        new = {p: after[p] for p in changed}
        self._push_history(lambda: self._restore_view_snapshot(old),
                           lambda: self._restore_view_snapshot(new))

    def _undoable_view_change(self, fn):
        before = self._view_snapshot()
        fn()
        self._push_view_change(before, self._view_snapshot())

    def _undo_top(self):
        return self.undo_stack[-1] if self.undo_stack else None

    def _view_history_event(self, ev):
        t = ev.type()
        if t == QtCore.QEvent.GraphicsSceneMousePress:
            self._close_wheel_gesture()
            if self._view_gesture is None:
                self._view_gesture = (self._view_snapshot(), self._undo_top())
            if ev.button() == QtCore.Qt.RightButton and self.interaction_mode == 'zoom':
                self._right_drag = {'pos': QtCore.QPointF(ev.screenPos()), 'active': False}
        elif t == QtCore.QEvent.GraphicsSceneMouseMove:
            rd = self._right_drag
            if (rd is not None and not rd['active'] and ev.buttons() & QtCore.Qt.RightButton
                    and (QtCore.QPointF(ev.screenPos()) - rd['pos']).manhattanLength() > 3):
                rd['active'] = True
                QtWidgets.QApplication.setOverrideCursor(_zoom_drag_cursor())
        elif t == QtCore.QEvent.GraphicsSceneMouseRelease:
            if ev.button() == QtCore.Qt.RightButton and self._right_drag is not None:
                if self._right_drag['active']:
                    QtWidgets.QApplication.restoreOverrideCursor()
                self._right_drag = None
            if self._view_gesture is not None and not ev.buttons():
                # After, not now: this filter runs before pyqtgraph handles
                # the release, which is when e.g. a rect zoom is applied.
                QtCore.QTimer.singleShot(0, self._close_view_gesture)
        elif t == QtCore.QEvent.GraphicsSceneWheel:
            if self._wheel_gesture is None:
                self._wheel_gesture = (self._view_snapshot(), self._undo_top())
            self._wheel_timer.start(self.WHEEL_SETTLE_MS)

    def _close_view_gesture(self):
        gesture, self._view_gesture = self._view_gesture, None
        if gesture is not None and self._undo_top() is gesture[1]:
            self._push_view_change(gesture[0], self._view_snapshot())

    def _close_wheel_gesture(self):
        """Also called before undo/redo, so a still-open wheel burst becomes
        its own entry first (history.py)."""
        self._wheel_timer.stop()
        gesture, self._wheel_gesture = self._wheel_gesture, None
        if gesture is not None and self._undo_top() is gesture[1]:
            self._push_view_change(gesture[0], self._view_snapshot())

    def remove_average(self):
        """Subtract the mean of what's drawn (the transformed y, visible
        rows only) by folding it into each series' display transform:
        dy -= mean (WP-P7, transform.py). Nothing is written to a
        DataSource or array, and the Transform popup shows -- and its Reset
        undoes -- the offset."""
        p = self.focused_plot
        if p is None:
            return
        # One gesture, one undo entry, however many series it changes.
        with self.undo_group():
            for s in self._series_on(p):
                y = s.y
                if ('remove_average' not in s.capabilities or not transform_applies(s.kind)
                        or y is None or y.size == 0):
                    continue
                mean = float(np.nanmean(y))
                if not np.isfinite(mean):
                    continue
                t = s.transform
                self.set_series_transform(s, Transform(t.dx, t.dy - mean, t.sx, t.sy))
        self._redraw_brush()

    def fft_below(self):
        p = self.focused_plot
        if p is None:
            return
        curve = self._active_curve_on(p)
        if curve is None:
            return
        series = self._series_of(curve)
        x, y = series.x, series.y
        if x is None or x.size < 2:
            return
        dt = np.mean(np.diff(x))
        freqs = np.fft.rfftfreq(y.size, d=dt)
        mag = np.abs(np.fft.rfft(y)) / y.size
        title = f"FFT of {curve.name() or 'signal'}"
        fft_pen = pg.mkPen((60, 60, 60), width=1)

        fft_plot = self.insert_subplot_below(p, title=title)
        if series.rows is not None:
            # The spectrum's rows are frequencies, not the time series' rows:
            # a DataSource of its own, leaving the time series' one untouched.
            ycol = series.columns[1] if series.columns and len(series.columns) > 1 else 'y'
            columns = ('frequency', f"|FFT({ycol})|")
            source = DataSource(dict(zip(columns, (freqs, mag))))
            fft_series = self._add_series(fft_plot, 'line', freqs, mag, pen=fft_pen,
                                          source=source, columns=columns)
        else:
            fft_series = self._add_series(fft_plot, 'line', freqs, mag, pen=fft_pen)
        fft_plot.setLabel('bottom', 'Frequency (Hz)')
        fft_plot.setLabel('left', 'Magnitude')

        row, col = self._grid_position(fft_plot)
        series_data = [fft_series.to_dict()]
        holder = {'plot': fft_plot}

        def undo_fn():
            plot = holder.get('plot')
            if plot is not None:
                self._remove_subplot_with_shift(plot)

        def redo_fn():
            new_plot = self._insert_subplot_with_shift(row, col, title, 'Frequency (Hz)', 'Magnitude', [])
            for d in series_data:
                self._add_series_from_dict(new_plot, d)
            holder['plot'] = new_plot
            self.focused_plot = new_plot
            self._mark_active(new_plot)

        self._push_history(undo_fn, redo_fn)

    def _apply_mouse_enabled(self, vb):
        """The only writer of a ViewBox's mouse-enabled state: Select and
        Brush modes both disable pan (and the wheel). 'rotate' (R4-3D)
        needs no extra case here -- it behaves like 'hand'/'zoom' (mouse
        stays on) already, simply by not being 'select' or 'brush'."""
        enabled = self.interaction_mode not in ('select', 'brush')
        vb.setMouseEnabled(x=enabled, y=enabled)

    def _apply_link_x(self):
        """Link every subplot's X to plots[0], or unlink all. Re-run on any
        add/remove, since plots[0] -- the reference -- can change.
        A 3D cell's view range is its own pixels (view3d.py): never a
        reference, never linked."""
        plots = [p for p in self.plots if getattr(p, 'axes_type', 'cartesian') != '3d']
        if not plots:
            return
        reference = plots[0]
        reference.setXLink(None)
        for p in plots[1:]:
            p.setXLink(reference if self.linked_x else None)

    def toggle_link_x(self, checked):
        self.linked_x = checked
        self._apply_link_x()

    # -- axis Scale (X/Y linear/log), and the 3D-only camera menu actions --
    # (R4-3D; the subplot menu itself, incl. hiding these for a 2D/3D
    # subplot respectively, is menus.py's _wire_context_menu)
    def set_axis_scale(self, plot_item, axis, log):
        """Undoable X/Y linear<->log toggle (the subplot menu's "Scale"
        submenu; hidden for a 3D subplot there). A menu action, not a
        mouse gesture, so it goes through the plain undo stack
        (_push_history) like Remove Average/FFT -- not the view-history
        gesture mechanism above, which is press/move/release-driven."""
        ctrl = plot_item.ctrl
        check = ctrl.logXCheck if axis == 'x' else ctrl.logYCheck
        old = check.isChecked()
        if old == log:
            return

        def apply(value):
            if axis == 'x':
                plot_item.setLogMode(x=value)
            else:
                plot_item.setLogMode(y=value)

        apply(log)
        self._push_history(lambda: apply(old), lambda: apply(log))

    def _set_3d_view_preset(self, plot_item, preset):
        """One of the subplot menu's 4 camera-view entries (only shown
        while 'rotate' mode is active, menus.py). Undoable through the
        same view-history mechanism Home/Fit/View All use -- the camera
        state is already part of _view_snapshot for a 3D cell."""
        vb = plot_item.getViewBox()
        self._undoable_view_change(lambda: vb.set_view_preset(preset))

    def _set_3d_projection(self, plot_item, projection):
        """The subplot menu's Projection submenu (Perspective/
        Orthographic), always shown for a 3D subplot. Same undo mechanism
        as _set_3d_view_preset above."""
        vb = plot_item.getViewBox()
        self._undoable_view_change(lambda: vb.set_projection(projection))
