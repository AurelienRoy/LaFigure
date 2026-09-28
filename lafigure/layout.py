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

"""The subplot grid: construction (add_subplot -- the only addPlot() call
site), plain single-cell add/delete, FFT's whole-row insert/delete, and
the resize/move/swap/float machinery with its handles.

Resize, move, swap and float are kept together in this one module on
purpose: they share one piece of state (self.floating, the detached
plot -> placeholder map) and the same grid bookkeeping, and splitting
them would put that state in two mixins. See CLAUDE.md bugs #1-#6.
"""
import sys
from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg

from .selection import RectBrush
from .handles import ResizeHandle, MoveHandle
from .editable_text import wire_plot_labels_editable
from .annotations import AnnotationItem
from .selection_ui import selection_op


AXES_TYPES = ('cartesian',)


class LayoutMixin:
    def add_subplot(self, row, col, rowspan=1, colspan=1, title='', axes_type='cartesian'):
        """The only subplot construction site (guarded by
        test_add_subplot_is_the_only_subplot_construction_site): every new
        subplot adopts the figure-wide toggles here.

        rowspan/colspan are passed through to the grid. axes_type is part
        of the frozen interface for later work packages; only 'cartesian'
        exists so far, and it is recorded on the PlotItem as
        `plot_item.axes_type`."""
        if axes_type not in AXES_TYPES:
            raise NotImplementedError(f"axes_type={axes_type!r} is not implemented yet "
                                      f"(available: {', '.join(AXES_TYPES)})")
        plot_item = self.layout_widget.addPlot(row=row, col=col, rowspan=rowspan,
                                               colspan=colspan, title=title)
        plot_item.axes_type = axes_type
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
        self._apply_view_mouse_mode(vb)
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

    @selection_op
    def _forget_removed_plot(self, plot_item):
        """Shared focused-plot/active-curve bookkeeping after a plot leaves
        self.plots, regardless of which removal path was used."""
        self._brushers.pop(plot_item, None)
        if plot_item in self.selected_plots:
            self.selected_plots.remove(plot_item)
        if self.focused_plot is plot_item:
            self.focused_plot = self.plots[0] if self.plots else None
            if self.focused_plot is not None:
                self._mark_active(self.focused_plot, keep_selection=True)
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
        self.focused_plot = new_plot
        self._mark_active(new_plot)

        holder = {'plot': new_plot}

        def undo_fn():
            p = holder.get('plot')
            if p is not None:
                self._remove_subplot(p)

        def redo_fn():
            p = self._insert_subplot_at(row, col, title, '', '', [])
            holder['plot'] = p
            self.focused_plot = p
            self._mark_active(p)

        self._push_history(undo_fn, redo_fn)

    # -- subplot resize (drag a border/corner of the focused subplot) -----
    def toggle_overlap_resize(self, checked):
        self.overlap_resize = checked
        if not checked:
            # Turning overlap off is "rearrange now": snap every floating
            # subplot back into the grid, sizing its row/col from where it
            # currently sits so the reflow roughly matches what was on screen.
            # Checked before the loop, which empties self.floating (checking
            # after it meant the new stretch factors were never applied).
            had_floating = bool(self.floating)
            for plot_item in list(self.floating.keys()):
                rect = QtCore.QRectF(plot_item.pos(), plot_item.size())
                _, row, col, _ = self.floating[plot_item]
                self._reattach_floating(plot_item)
                self._set_stretch_for_size(self.col_stretch, col, rect.width(), self.layout_widget.width())
                self._set_stretch_for_size(self.row_stretch, row, rect.height(), self.layout_widget.height())
            if had_floating:
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
        active = self.focused_plot
        # focused_plot outlives its selection (e.g. a curve click deselects
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
        p = self.focused_plot
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
            p = self.focused_plot
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
        p = self.focused_plot
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
        p = self.focused_plot
        delta = scene_pos - st['origin']
        p.setPos(st['start_pos'] + delta)
        self._position_handles()

    def _end_move(self, scene_pos):
        st = self._move_state
        if st is None:
            return
        self._move_state = None
        p = self.focused_plot
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
            self.focused_plot = new_plot
            self._mark_active(new_plot)

        def redo_fn():
            p = holder.get('plot')
            if p is not None:
                self._remove_subplot(p)

        self._push_history(undo_fn, redo_fn)
