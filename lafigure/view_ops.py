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

"""View state and per-subplot data actions: interaction mode
(Select/Hand/Zoom Rect), Home / Fit Vertical / Fit Horizontal, legend,
Link X, Remove Average, FFT -> subplot below.
"""
import numpy as np
from pyqtgraph.Qt import QtCore
import pyqtgraph as pg

from .datasource import DataSource
from .editable_text import wire_legend_editable
from .selection_ui import selection_op


class ViewOpsMixin:
    # -- interaction mode ------------------------------------------------
    @staticmethod
    def _cursor_for_mode(mode):
        return QtCore.Qt.OpenHandCursor if mode == 'hand' else QtCore.Qt.ArrowCursor

    def _apply_view_mouse_mode(self, vb):
        """Set a ViewBox's pan/rect mouse mode from self.interaction_mode,
        and style Zoom Rect's drag rectangle light gray instead of
        pyqtgraph's yellow.

        The styling must follow every setMouseMode: pyqtgraph's
        setMouseMode(PanMode) drops its rbScaleBox, and the next access
        lazily builds a fresh, yellow one -- so a box styled once at
        subplot creation (the first version of this) never survived to the
        first zoom drag. Styled only in RectMode: touching rbScaleBox in
        PanMode would just build a box that the next setMouseMode drops."""
        if self.interaction_mode == 'zoom':
            vb.setMouseMode(pg.ViewBox.RectMode)
            vb.rbScaleBox.setPen(pg.mkPen((140, 140, 140), width=1))
            vb.rbScaleBox.setBrush(pg.mkBrush(200, 200, 200, 90))
        else:
            vb.setMouseMode(pg.ViewBox.PanMode)

    @selection_op
    def set_interaction_mode(self, mode):
        """'select': click-to-select + move/resize handles, dragging inside
        a subplot does nothing (freed up for the handles).
        'hand': plain pan, no selection. 'zoom': drag-to-zoom, no selection."""
        self.interaction_mode = mode
        cursor = self._cursor_for_mode(mode)
        for p in self.plots:
            vb = p.getViewBox()
            self._apply_view_mouse_mode(vb)
            self._apply_mouse_enabled(vb)
            vb.setCursor(cursor)
        if mode != 'select':
            self._deselect_curve()
        if self.focused_plot is not None:
            self._mark_active(self.focused_plot, keep_selection=True)
        else:
            self._hide_handles()

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
        p.getViewBox().autoRange()

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
            vb.setYRange(lo, hi)
        else:
            vb.setXRange(lo, hi)

    def toggle_legend(self):
        """Toggles independently on every selected subplot (Shift+click to
        select more than one) -- each subplot's legend flips its own
        current on/off state rather than being forced to match the others."""
        targets = self.selected_plots if self.selected_plots else (
            [self.focused_plot] if self.focused_plot is not None else []
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
        """Subtract the mean of what's drawn. A series whose y is a column
        of a DataSource gets a new derived column instead of an edit (see
        brushing.py, "Derived columns")."""
        p = self.focused_plot
        if p is None:
            return
        # One gesture, one undo entry, however many series it changes.
        with self.undo_group():
            for s in self._series_on(p):
                y = s.y
                if 'remove_average' not in s.capabilities or y is None or y.size == 0:
                    continue
                mean = np.mean(y)
                source = self._column_backed(s)
                if source is not None:
                    self._derive_y_column(s, "- mean", np.asarray(source[s.columns[1]], dtype=float) - mean)
                else:
                    s.set_data(s.x, y - mean)
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
        """The only writer of a ViewBox's mouse-enabled state: Select mode
        and brushing both disable pan, so neither may re-enable it alone."""
        enabled = self.interaction_mode != 'select' and not self.brushing
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
