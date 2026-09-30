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

"""Names and labels: figure name, subplot names, axis labels, curve
names. Every rename is undoable.
"""
from pyqtgraph.Qt import QtWidgets

from .editable_text import (
    wire_legend_editable, edit_in_place, AxisLabelTarget, LegendEntryTarget,
)


class NamingMixin:
    # -- figure and subplot names (the Figure Manager's editable nodes) ------
    def rename_figure(self, name):
        """Rename this figure: its window title, which is also its name in
        the Figure Manager. Undoable; every change, undo/redo included,
        emits the registry's figureRenamed."""
        old_name = self.windowTitle()
        if name == old_name:
            return

        def apply(n):
            self.setWindowTitle(n)
            self.registry.notify_figure_renamed(self)

        apply(name)
        self._push_history(undo_fn=lambda: apply(old_name), redo_fn=lambda: apply(name))

    def subplot_name(self, plot_item):
        """The name set by rename_subplot, else the subplot's current
        title text (which may be empty)."""
        name = getattr(plot_item, 'lafigure_name', None)
        return name if name is not None else (plot_item.titleLabel.text or '')

    def rename_subplot(self, plot_item, name):
        """Rename a subplot: records `name` as its name and shows it as its
        title. Undoable (restores both the old title and the old name,
        explicit or not); emits the registry's subplotsChanged so the
        Figure Manager's tree relabels it."""
        old_title = plot_item.titleLabel.text
        old_name = getattr(plot_item, 'lafigure_name', None)

        def apply(title, explicit_name):
            plot_item.setTitle(title)
            plot_item.lafigure_name = explicit_name
            self.registry.notify_subplots_changed(self)

        apply(name, name)
        self._push_history(undo_fn=lambda: apply(old_title, old_name),
                           redo_fn=lambda: apply(name, name))

    # -- curve names and axis labels -----------------------------------------
    def _apply_curve_rename(self, plot_item, curve, new_name):
        """The one rename path (curve menu, legend in-place edit, Curve
        browser): `new_name` is a source string (richtext.py markup), kept
        as is in curve.opts['name']; only the legend renders it. The legend
        is rebuilt through _refresh_legend_order, so a "_"-prefixed name
        drops out of it (and back in) and the z-order is kept."""
        old_name = curve.name() or ""
        curve.opts['name'] = new_name
        legend = plot_item.legend
        if legend is not None:
            if hasattr(self, '_refresh_legend_order'):
                self._refresh_legend_order(plot_item)
            else:
                legend.removeItem(old_name)
                legend.addItem(curve, new_name)
            wire_legend_editable(self, plot_item, legend)
        self.registry.notify_subplots_changed(self)

    def _rename_curve(self, plot_item, curve):
        """Renames every selected curve to the same new name if `curve`
        (the one picked from the right-click submenu) is part of the
        current multi-select (Shift+click to select more than one), else
        just `curve` alone. In place, over the curve's legend entry, when
        it has one on screen; otherwise there is no text to edit in place,
        so a small dialog asks."""
        targets = self.selected_curves if curve in self.selected_curves else [curve]
        entry = LegendEntryTarget(self, plot_item, curve)
        if entry.text_item() is not None:
            others = tuple(LegendEntryTarget(self, p, c) for c in targets if c is not curve
                           for p in [self._curve_plot(c)] if p is not None)
            edit_in_place(entry, also=others)
            return
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

    def set_axis_label(self, axis_name):
        """Toolbar 'X Label' / 'Y Label': same effect as double-clicking the
        axis label, just discoverable without knowing that gesture -- handy
        right after Add Subplot, whose axes start unlabeled. Applies the
        same text to every selected subplot (Shift+click to select more
        than one)."""
        targets = self.selected_plots if self.selected_plots else (
            [self.focused_plot] if self.focused_plot is not None else []
        )
        if not targets:
            return
        p = self.focused_plot if self.focused_plot in targets else targets[0]
        # In place over p's label (or where it would be, if still empty);
        # the committed text goes to every target, one undo entry.
        edit_in_place(AxisLabelTarget(self, p, axis_name),
                      also=tuple(AxisLabelTarget(self, t, axis_name) for t in targets if t is not p))
