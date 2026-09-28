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

"""Figure-wide data brushing: the Brush toggle, the RectBrush /
LinkedScatter coordination, and the four brushed-point actions (Delete,
Transform, Stats, Fit).
"""
import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg


class BrushingMixin:
    def toggle_brush(self, checked):
        self.brushing = checked
        for scatter in (getattr(self, 'scatter1', None), getattr(self, 'scatter2', None)):
            if scatter is not None:
                scatter.set_brushing(checked)
        for brusher in self._brushers.values():
            brusher.set_brushing(checked)
        for p in self.plots:
            self._apply_mouse_enabled(p.getViewBox())
        if not checked and self.selection_model is not None:
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
        if self.selection_model is not None:  # None in a figure without the demo pair
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
            curve = self._add_series(plot_item, 'line', xs_sorted, ys_fit, pen=fit_pen, name=label).item
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
