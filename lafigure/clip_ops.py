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

"""Edit operations on curves and subplots: copy/paste (via the
process-wide Clipboard, so they work across figure windows) and delete
(Del key: everything selected, whatever its kind).

Series go through _series_full_dict/_add_series_restoring (brushing.py),
not bare to_dict/_add_series_from_dict: a copy or an undone delete keeps
the rows a series isn't drawing right now, and hides them again. A copied
series keeps its DataSource by reference, so a paste -- in any window --
stays linked to it (brushing, hidden rows).
"""
from pyqtgraph.Qt import QtCore

from .annotations import AnnotationItem
from .selection_ui import selection_op
from .groups import groups_from_dict


class ClipOpsMixin:
    # -- delete (curve or subplot) ---------------------------------------
    @selection_op
    def delete_selection(self):
        """Del key / toolbar Delete: remove everything selected, whatever
        its kind, as one undo entry.

        In Brush mode, Del instead removes the brushed points (the
        figure-wide brushed selection, not selected_plots/curves/
        annotations -- see brushing.py; Brush mode disables normal
        subplot/curve/annotation selection anyway, so this Del would
        otherwise do nothing useful).

        Curves and subplot-owned annotations on a subplot that is itself
        being deleted are skipped: the subplot's own undo restores them,
        while their separate undo steps would target the dead PlotItem."""
        if self.brushing:
            self.delete_brushed_points()
            return
        doomed_plots = list(self.selected_plots)
        if self.selected_legend is not None and self.selected_legend.legend is not None:
            # View state, like Toggle Legend -- not an undo entry.
            self._hide_legend(self.selected_legend)
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
        data = self._series_full_dict(self._series_of(curve))
        plot_item.removeItem(curve)
        self._forget_curve_selection(curve)
        brusher = self._brushers.get(plot_item)
        if brusher is not None:
            brusher.forget_curve(curve)
        # See series.py's _add_series for why: the Curve/Figure Browser
        # trees rebuild from this signal, and undo's re-add already
        # triggers it via _add_series_restoring -> _add_series, but this
        # removal and redo's (below) don't go through _add_series at all.
        self.registry.notify_subplots_changed(self)

        holder = {}

        def undo_fn():
            holder['curve'] = self._add_series_restoring(plot_item, data).item

        def redo_fn():
            c = holder.get('curve')
            if c is not None:
                plot_item.removeItem(c)
                self._forget_curve_selection(c)
                self.registry.notify_subplots_changed(self)

        self._push_history(undo_fn, redo_fn)

    # -- Ctrl+C / Ctrl+V: dispatch to curve, subplot or annotation copy/paste
    def copy_selection(self):
        """Ctrl+C: copy the selected curve(s) if any curve is selected
        (Shift+click to select more than one), else the selected
        annotation(s) if any are selected and no subplot is (selection is
        exclusive across kinds unless Shift is held, so this only matters
        for a mixed Shift-selection -- see CLAUDE.md), else the selected
        subplot(s) -- without the first check, Ctrl+C always copied a
        curve even when only a subplot had ever been selected, silently
        duplicating a curve on paste instead of the subplot. The subplot
        branch keeps its original fallback (copy_subplot() itself falls
        back to focused_plot when nothing is explicitly selected) so a
        plain click into a subplot with nothing selected still copies it,
        exactly as before annotations became copyable."""
        if self.selected_curves:
            self.copy_curve()
        elif self.selected_annotations and not self.selected_plots:
            self.copy_annotation()
        elif self.focused_plot is not None:
            self.copy_subplot()

    def paste_selection(self):
        """Ctrl+V: mirrors copy_selection -- pastes whichever kind was
        most recently copied, via Ctrl+C, Ctrl+Shift+C, or their menu
        equivalents (see Clipboard.last_copied)."""
        if self.clipboard.last_copied == 'subplot':
            self.paste_subplot()
        elif self.clipboard.last_copied == 'annotation':
            self.paste_annotation()
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
            p = self.focused_plot
            c = self._active_curve_on(p) if p is not None else None
            targets = [c] if c is not None else []
        if not targets:
            return
        self.clipboard.curve = [self._series_full_dict(self._series_of(c)) for c in targets]
        self.clipboard.last_copied = 'curve'

    def paste_curve(self):
        p = self.focused_plot
        if p is None or not self.clipboard.curve:
            return
        series_data = self.clipboard.curve

        def build():
            return [self._add_series_restoring(p, d).item for d in series_data]

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
            [self.focused_plot] if self.focused_plot is not None else []
        )
        if not targets:
            return
        self.clipboard.subplot = [
            {
                'title': p.titleLabel.text,
                'xlabel': p.getAxis('bottom').labelText,
                'ylabel': p.getAxis('left').labelText,
                'series': [self._series_full_dict(s) for s in self._series_on(p)],
                'annotations': [a.to_dict() for a in self._annotations_on(p)],
                'groups': [g.to_dict() for g in self.groups if g.subplot is p],
                'axes_type': getattr(p, 'axes_type', 'cartesian'),
                'view_state': self._subplot_view_state(p),
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
            new_groups = []
            for i, data in enumerate(data_list):
                new_plot = self._insert_subplot_at(
                    start_row + i, col, data['title'], data['xlabel'], data['ylabel'], [],
                    axes_type=data.get('axes_type', 'cartesian'), view_state=data.get('view_state'),
                )
                for d in data['series']:
                    self._add_series_restoring(new_plot, d)
                for d in data.get('annotations', []):
                    AnnotationItem.from_dict(self, new_plot, d)
                new_groups.extend(groups_from_dict(self, new_plot, data.get('groups', [])))
                new_plots.append(new_plot)
            self.groups.extend(new_groups)
            return new_plots, new_groups

        holder = {}
        holder['plots'], holder['groups'] = build()
        self._select_plots(holder['plots'])

        def undo_fn():
            for g in holder.get('groups', []):
                if g in self.groups:
                    self.groups.remove(g)
            for p in holder.get('plots', []):
                self._remove_subplot(p)
            holder['plots'] = []
            holder['groups'] = []

        def redo_fn():
            holder['plots'], holder['groups'] = build()
            self._select_plots(holder['plots'])

        self._push_history(undo_fn, redo_fn)

    # -- copy / paste annotations, including across separate figure
    # windows (via the process-wide Clipboard) ---------------------------
    ANNOTATION_PASTE_OFFSET_PX = 20

    def copy_annotation(self):
        """Copies every selected annotation (Shift+click to select more
        than one)."""
        if not self.selected_annotations:
            return
        self.clipboard.annotation = [a.to_dict() for a in self.selected_annotations]
        self.clipboard.last_copied = 'annotation'

    def paste_annotation(self):
        """Pastes every copied annotation, offset a few screen pixels from
        where it was copied (_offset_pasted_annotation) so a same-window
        paste doesn't land exactly on top of the original. An 'axes'/
        'border'-anchored one lands on the FOCUSED subplot -- same target
        convention paste_curve already uses, not necessarily the subplot
        it was copied from -- and is skipped if nothing is focused; a
        'figure'-anchored one just needs this window."""
        data_list = self.clipboard.annotation
        if not data_list:
            return
        target_plot = self.focused_plot

        def build():
            new_anns = []
            for data in data_list:
                if data['anchor'] != 'figure' and target_plot is None:
                    continue
                parent_plot = target_plot if data['anchor'] != 'figure' else None
                ann = AnnotationItem.from_dict(self, parent_plot, data)
                self._offset_pasted_annotation(ann)
                new_anns.append(ann)
            return new_anns

        holder = {'anns': build()}
        if not holder['anns']:
            return
        self._select_annotations(holder['anns'])

        def undo_fn():
            for a in holder.get('anns', []):
                self._purge_annotation(a)
            holder['anns'] = []

        def redo_fn():
            holder['anns'] = build()
            self._select_annotations(holder['anns'])

        self._push_history(undo_fn, redo_fn)

    def _offset_pasted_annotation(self, ann):
        """Nudges a just-pasted annotation ANNOTATION_PASTE_OFFSET_PX
        screen pixels right/down from wherever from_dict placed it --
        computed in scene (screen-pixel) space and converted into `ann`'s
        own parent frame (data units for 'axes', scene pixels for
        'figure'/'border'), same approach the Shift move-constraint uses
        (annotations.py). For 'border', anchor_offset (a box-relative
        fraction, the actual source of truth for its position -- see
        _place_border_annotation) is refreshed too, mirroring
        AnnotationItem._push_move_history's own pattern for a real drag."""
        delta = QtCore.QPointF(self.ANNOTATION_PASTE_OFFSET_PX, self.ANNOTATION_PASTE_OFFSET_PX)
        new_pos = ann._parent_point(ann.scenePos() + delta)
        ann.setPos(new_pos)
        if ann.anchor == 'border' and ann.parent_plot in self.plots:
            ann.anchor_offset = self._box_fraction(ann.parent_plot, new_pos)
