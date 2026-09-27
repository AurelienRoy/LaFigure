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

"""Shared selection model + linked scatter subplot.

Any number of plots can subscribe to a SelectionModel. When one plot
brushes a region, it updates the mask here, and every subscriber
re-renders its own highlight overlay -- this is what gives you "linked
brushing" / "link data across plots" across otherwise independent subplots.
"""
import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg


class SelectionModel(QtCore.QObject):
    selectionChanged = QtCore.Signal(object)  # emits a boolean numpy mask

    def __init__(self, n_points):
        super().__init__()
        self.mask = np.zeros(n_points, dtype=bool)

    def set_selection(self, mask):
        self.mask = mask
        self.selectionChanged.emit(self.mask)

    def clear(self):
        self.set_selection(np.zeros_like(self.mask))


class LinkedScatter:
    """A subplot that participates in linked selection: it owns (x, y) data
    plus a shared row-id space (so two subplots showing different
    projections of the *same* rows can highlight the same rows). Selecting
    via rectangular brush on this plot updates the shared SelectionModel;
    every LinkedScatter bound to that same model redraws its highlight
    overlay in response."""

    def __init__(self, plot_item, x, y, selection_model, color=(80, 120, 220), figure=None):
        self.plot_item = plot_item
        self.x = np.asarray(x)
        self.y = np.asarray(y)
        self.selection_model = selection_model

        self.base = pg.ScatterPlotItem(
            x=self.x, y=self.y, size=4, pen=None, brush=pg.mkBrush(*color, 160)
        )
        self.highlight = pg.ScatterPlotItem(
            x=[], y=[], size=7, pen=pg.mkPen('k', width=1), brush=pg.mkBrush(255, 60, 60, 220)
        )
        plot_item.addItem(self.base)
        plot_item.addItem(self.highlight)
        self.highlight.setZValue(10)

        selection_model.selectionChanged.connect(self._on_selection_changed)

        # add_subplot wires a generic RectBrush onto every new plot_item's
        # ViewBox by default (so brushing works on any subplot, not just
        # this row-linked pair). A LinkedScatter plot uses its own
        # row-linked brushing instead -- drop that default brusher first so
        # our own mouseDragEvent wrapper below isn't stacked on top of it.
        if figure is not None:
            brusher = figure._brushers.pop(plot_item, None)
            if brusher is not None:
                brusher.uninstall()
        self.figure = figure

        self.view_box = plot_item.getViewBox()
        self._brush_origin = None
        self._brush_rect_item = None
        self.brushing_enabled = False

        # Route mouse drags through our handler only while brushing mode is on.
        self.view_box.mouseDragEvent = self._wrap_drag(self.view_box.mouseDragEvent)

    def _on_selection_changed(self, mask):
        self.highlight.setData(x=self.x[mask], y=self.y[mask])

    def set_brushing(self, enabled):
        # Pan-disabling is LaFigure._apply_mouse_enabled's job, not ours.
        self.brushing_enabled = enabled

    def _wrap_drag(self, original_drag):
        def handler(ev, axis=None):
            if not self.brushing_enabled:
                return original_drag(ev, axis=axis)

            ev.accept()
            pos = self.view_box.mapToView(ev.pos())
            if ev.isStart():
                self._brush_origin = pos
                self._brush_rect_item = QtWidgets.QGraphicsRectItem()
                self._brush_rect_item.setPen(pg.mkPen('k', style=QtCore.Qt.DashLine))
                self._brush_rect_item.setBrush(pg.mkBrush(120, 120, 255, 40))
                self.view_box.addItem(self._brush_rect_item, ignoreBounds=True)

            if self._brush_origin is not None:
                x0, y0 = self._brush_origin.x(), self._brush_origin.y()
                x1, y1 = pos.x(), pos.y()
                rect = QtCore.QRectF(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
                self._brush_rect_item.setRect(rect)

            if ev.isFinish():
                x0, y0 = self._brush_origin.x(), self._brush_origin.y()
                x1, y1 = pos.x(), pos.y()
                xlo, xhi = sorted((x0, x1))
                ylo, yhi = sorted((y0, y1))
                mask = (self.x >= xlo) & (self.x <= xhi) & (self.y >= ylo) & (self.y <= yhi)
                additive = bool(ev.modifiers() & QtCore.Qt.ShiftModifier)
                if not additive:
                    # Brushing is a figure-wide concept (see RectBrush) --
                    # a fresh, non-additive brush anywhere unbrushes every
                    # other subplot in this figure first.
                    if self.figure is not None:
                        self.figure._clear_all_brush_selection(except_plot=self.plot_item)
                else:
                    mask = self.selection_model.mask | mask
                self.selection_model.set_selection(mask)
                self.view_box.removeItem(self._brush_rect_item)
                self._brush_rect_item = None
                self._brush_origin = None
        return handler


class RectBrush:
    """Generic rectangular brush-select wired onto a subplot's own curves.

    Unlike LinkedScatter (a shared row-space selection deliberately hardcoded
    to the two demo scatter subplots), this works on any subplot's ordinary
    PlotDataItem curves, whether or not that subplot participates in a
    shared SelectionModel -- it's what makes "Brush" mode select points on
    any graph, not only the two data-linked ones. `LaFigure.add_subplot`
    installs one of these on every new plot_item by default; a plot that's
    instead wired up as a LinkedScatter has its default RectBrush removed
    (see LinkedScatter.__init__) so the two don't stack on the same
    ViewBox.mouseDragEvent.
    """

    def __init__(self, plot_item, on_finished=None):
        self.plot_item = plot_item
        self.view_box = plot_item.getViewBox()
        self.brushing_enabled = False
        self._origin = None
        self._rect_item = None
        self.selection = {}    # PlotDataItem -> boolean mask, only entries with >=1 point
        self._highlights = {}  # PlotDataItem -> its highlight ScatterPlotItem overlay
        # Called as on_finished(plot_item, matches, additive) when a drag
        # finishes, instead of applying the result locally -- lets
        # LaFigure coordinate brushing as a figure-wide concept (a new,
        # non-additive brush clears every other subplot's selection too; a
        # Shift-held one adds to whatever's already selected everywhere).
        # Falls back to purely local replace/merge if None (e.g. standalone use).
        self.on_finished = on_finished
        self._native_drag = self.view_box.mouseDragEvent
        self.view_box.mouseDragEvent = self._wrap_drag(self._native_drag)

    def uninstall(self):
        """Restore the native (unwrapped) drag handler. Only used right
        after construction, before LinkedScatter installs its own wrapper
        in its place -- see LinkedScatter.__init__."""
        self.clear_selection()
        self.view_box.mouseDragEvent = self._native_drag

    def _curves(self):
        return [c for c in self.plot_item.listDataItems() if isinstance(c, pg.PlotDataItem)]

    def set_brushing(self, enabled):
        # Pan-disabling is LaFigure._apply_mouse_enabled's job, not ours.
        self.brushing_enabled = enabled
        if not enabled:
            self.clear_selection()

    def clear_selection(self):
        for item in self._highlights.values():
            self.view_box.removeItem(item)
        self._highlights = {}
        self.selection = {}

    def has_selection(self):
        return any(mask.any() for mask in self.selection.values())

    def set_selection(self, matches):
        """Replace this subplot's selection wholesale -- a non-additive brush."""
        self.clear_selection()
        self._draw_selection(matches)

    def merge_selection(self, matches):
        """OR new matches into the existing selection -- a Shift-held brush."""
        merged = {curve: mask.copy() for curve, mask in self.selection.items()}
        for curve, mask in matches.items():
            merged[curve] = (merged[curve] | mask) if curve in merged else mask
        self.clear_selection()
        self._draw_selection(merged)

    def _draw_selection(self, matches):
        self.selection = {}
        for curve, mask in matches.items():
            if not mask.any():
                continue
            self.selection[curve] = mask
            x, y = np.asarray(curve.xData), np.asarray(curve.yData)
            hl = pg.ScatterPlotItem(
                x=x[mask], y=y[mask], size=8, pen=pg.mkPen('k', width=1),
                brush=pg.mkBrush(255, 60, 60, 220),
            )
            hl.setZValue(10)
            self.view_box.addItem(hl, ignoreBounds=True)
            self._highlights[curve] = hl

    def forget_curve(self, curve):
        """Called when a curve is deleted out from under an active
        selection/highlight (e.g. via the 'Delete Curve' menu), so its
        orphaned highlight overlay doesn't linger on screen."""
        hl = self._highlights.pop(curve, None)
        if hl is not None:
            self.view_box.removeItem(hl)
        self.selection.pop(curve, None)

    def _wrap_drag(self, native_drag):
        def handler(ev, axis=None):
            if not self.brushing_enabled:
                return native_drag(ev, axis=axis)

            ev.accept()
            pos = self.view_box.mapToView(ev.pos())
            if ev.isStart():
                self._origin = pos
                self._rect_item = QtWidgets.QGraphicsRectItem()
                self._rect_item.setPen(pg.mkPen('k', style=QtCore.Qt.DashLine))
                self._rect_item.setBrush(pg.mkBrush(120, 120, 255, 40))
                self.view_box.addItem(self._rect_item, ignoreBounds=True)

            if self._origin is not None:
                x0, y0 = self._origin.x(), self._origin.y()
                x1, y1 = pos.x(), pos.y()
                rect = QtCore.QRectF(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
                self._rect_item.setRect(rect)

            if ev.isFinish():
                x0, y0 = self._origin.x(), self._origin.y()
                x1, y1 = pos.x(), pos.y()
                xlo, xhi = sorted((x0, x1))
                ylo, yhi = sorted((y0, y1))
                matches = self._compute_matches(xlo, xhi, ylo, yhi)
                # Checked at release time, not throughout the drag -- a
                # simplification (see RectBrush's own docstring), matching
                # how pyqtgraph's own ViewBox reads modifiers for its
                # Ctrl+drag box-zoom.
                additive = bool(ev.modifiers() & QtCore.Qt.ShiftModifier)
                if self.on_finished is not None:
                    self.on_finished(self.plot_item, matches, additive)
                elif additive:
                    self.merge_selection(matches)
                else:
                    self.set_selection(matches)
                self.view_box.removeItem(self._rect_item)
                self._rect_item = None
                self._origin = None
        return handler

    def _compute_matches(self, xlo, xhi, ylo, yhi):
        matches = {}
        for curve in self._curves():
            x, y = curve.xData, curve.yData
            if x is None or len(x) == 0:
                continue
            x, y = np.asarray(x), np.asarray(y)
            mask = (x >= xlo) & (x <= xhi) & (y >= ylo) & (y <= yhi)
            if mask.any():
                matches[curve] = mask
        return matches
