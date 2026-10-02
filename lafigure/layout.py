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

"""The free subplot layout on a fractional grid: construction (add_subplot
-- the only PlotItem construction site), add/delete, FFT's row insertion,
and the Select-mode layout gestures (resize, move/swap, grid-line drag,
snapping) with their handles, gutters and undo.

No QGraphicsGridLayout is involved any more. The figure owns a grid --
column and row line positions as figure fractions (self.grid_cols,
self.grid_rows) -- and every subplot a box (self.boxes[plot] = (left, top,
right, bottom)) in fractional grid coordinates; see grid.py for the math.
_apply_layout maps every box to pixels and setGeometry()s its subplot, on
every change and on every viewport resize. A subplot is a top-level scene
item from creation to removal: nothing ever detaches or reparents it, so
the float/placeholder/reattach machinery -- and bugs #2, #3, #5 and #6,
which all lived in it -- are gone rather than guarded. Overlap is just two
intersecting boxes; self.z_order says which one is on top.

The whole layout is a few numbers (lines, boxes, z-order), so every layout
gesture pushes one undo entry holding a before/after snapshot of it.
"""
import math
import sys
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from . import grid
from .grid import EPS
from .selection import RectBrush
from .handles import ResizeHandle, MoveHandle, GutterHandle, XLinkBadge, GUIDES_Z
from .editable_text import wire_plot_labels_editable
from .annotations import AnnotationItem
from .selection_ui import selection_op
from .view3d import View3DBox


# 'cartesian': a 2D pg.PlotItem. '3d': the same PlotItem with a View3DBox as
# its ViewBox (view3d.py) -- to this module, just another subplot with a box.
AXES_TYPES = ('cartesian', '3d')


class _ViewportWatcher(QtCore.QObject):
    """Re-lays the figure out whenever the view's viewport changes size.
    Watching the viewport (rather than overriding the main window's
    resizeEvent) sees the final size synchronously, including the
    pending resize a window only delivers when it is first shown."""

    def __init__(self, figure):
        super().__init__(figure)
        self._figure = figure

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.Resize:
            self._figure._apply_layout()
        return False


class SnapGuides(QtWidgets.QGraphicsItem):
    """The magnetic sub-grid, shown only while a layout drag is running:
    the grid lines, their snap subdivisions (dotted), and -- highlighted --
    whichever line/edge the drag is currently snapped to (the alignment
    guides). Paint-only: an empty shape() keeps it out of hit-testing."""

    def __init__(self):
        super().__init__()
        self.setZValue(GUIDES_Z)
        self.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        self._rect = QtCore.QRectF()
        self._lines = []      # (x0, y0, x1, y1, kind) with kind 'line' or 'sub'
        self._guides = []     # (x0, y0, x1, y1): the active snaps
        self.hide()

    def set_content(self, rect, lines, guides):
        self.prepareGeometryChange()
        self._rect = QtCore.QRectF(rect)
        self._lines = lines
        self._guides = guides
        self.update()

    def boundingRect(self):
        return self._rect.adjusted(-2, -2, 2, 2)

    def shape(self):
        return QtGui.QPainterPath()

    def paint(self, painter, option, widget=None):
        line_pen = pg.mkPen((150, 150, 150), width=1)
        sub_pen = pg.mkPen((180, 180, 180), width=1, style=QtCore.Qt.DotLine)
        guide_pen = pg.mkPen((230, 0, 150), width=1)
        for pen in (line_pen, sub_pen, guide_pen):
            pen.setCosmetic(True)
        for x0, y0, x1, y1, kind in self._lines:
            painter.setPen(line_pen if kind == 'line' else sub_pen)
            painter.drawLine(QtCore.QLineF(x0, y0, x1, y1))
        painter.setPen(guide_pen)
        for x0, y0, x1, y1 in self._guides:
            painter.drawLine(QtCore.QLineF(x0, y0, x1, y1))


class LayoutMixin:
    FIG_MARGIN = 4       # px between the view's edge and grid lines 0 / n
    CELL_PAD = 3         # px a subplot is drawn inside its box: 6 px gutters
    GUTTER_PX = 8        # hit width of a draggable grid line
    SNAP_PX = 8          # magnetic snapping threshold
    MIN_BOX_PX = 40      # smallest subplot a resize can make
    MIN_TRACK_PX = 30    # smallest row/column a grid-line drag can make
    PLOT_Z = 1           # z of the bottom subplot; self.z_order stacks up from it

    # -- state and pixel mapping ---------------------------------------------
    def _create_resize_handles(self):
        """Called once by LaFigure.__init__, before any subplot exists:
        creates the layout state, the handles, the snap guides, and the
        viewport watcher."""
        self.grid_cols = [0.0, 1.0]
        self.grid_rows = [0.0, 1.0]
        self.boxes = {}          # PlotItem -> (left, top, right, bottom), grid coordinates
        self.z_order = []        # PlotItems, bottom to top
        # Cell subdivisions the magnetic sub-grid snaps to: 2 = halves, 4 = quarters.
        self.snap_subdivisions = 2
        # Grid growth made by add_subplot, so undoing the addition shrinks
        # the grid back (see _record_growth / _undo_growth).
        self._grid_growth = []
        self._gutters = {}       # (axis, index, segment) -> GutterHandle
        self._resize_state = None
        self._move_state = None
        self._gutter_state = None

        scene = self.layout_widget.scene()
        roles = ('top', 'bottom', 'left', 'right',
                 'top-left', 'top-right', 'bottom-left', 'bottom-right')
        self.resize_handles = {role: ResizeHandle(self, role) for role in roles}
        for handle in self.resize_handles.values():
            scene.addItem(handle)
        self.move_handle = MoveHandle(self)
        scene.addItem(self.move_handle)
        self._snap_guides = SnapGuides()
        scene.addItem(self._snap_guides)
        self._viewport_watcher = _ViewportWatcher(self)
        self.layout_widget.viewport().installEventFilter(self._viewport_watcher)

    def _figure_rect(self):
        """The scene rect the grid spans: the viewport minus FIG_MARGIN.
        pyqtgraph's view maps scene coordinates 1:1 onto viewport pixels."""
        vp = self.layout_widget.viewport()
        m = self.FIG_MARGIN
        return QtCore.QRectF(m, m, max(vp.width() - 2 * m, 1), max(vp.height() - 2 * m, 1))

    def _gx_to_px(self, gx):
        r = self._figure_rect()
        return r.left() + grid.to_frac(self.grid_cols, gx) * r.width()

    def _gy_to_px(self, gy):
        r = self._figure_rect()
        return r.top() + grid.to_frac(self.grid_rows, gy) * r.height()

    def _px_to_gx(self, x):
        r = self._figure_rect()
        return grid.from_frac(self.grid_cols, (x - r.left()) / r.width())

    def _px_to_gy(self, y):
        r = self._figure_rect()
        return grid.from_frac(self.grid_rows, (y - r.top()) / r.height())

    def _g_to_px(self, axis, g):
        return self._gx_to_px(g) if axis == 'x' else self._gy_to_px(g)

    def _px_to_g(self, axis, px):
        return self._px_to_gx(px) if axis == 'x' else self._px_to_gy(px)

    def _n_tracks(self, axis):
        return len(self.grid_cols if axis in ('x', 'col') else self.grid_rows) - 1

    def _box_scene_rect(self, box):
        """A box's full extent in scene pixels (the subplot is drawn
        CELL_PAD inside it)."""
        left, top, right, bottom = box
        return QtCore.QRectF(QtCore.QPointF(self._gx_to_px(left), self._gy_to_px(top)),
                             QtCore.QPointF(self._gx_to_px(right), self._gy_to_px(bottom)))

    def _apply_layout(self):
        """Map every box to pixels and place its subplot there; restack by
        z_order; refresh backgrounds, gutters and handles. The one place a
        subplot's geometry is ever set."""
        pad = self.CELL_PAD
        for z, p in enumerate(self.z_order):
            p.setZValue(self.PLOT_Z + z)
        for p in self.plots:
            box = self.boxes.get(p)
            if box is None:
                continue
            rect = self._box_scene_rect(box).adjusted(pad, pad, -pad, -pad)
            p.setGeometry(rect)
        self._update_backgrounds()
        self._position_handles()
        self._update_x_link_badges()

    def _update_backgrounds(self):
        """A subplot drawn above another one it overlaps (an inset) gets an
        opaque background, the figure's color; the others stay transparent."""
        color = pg.mkColor(pg.getConfigOption('background'))
        for i, p in enumerate(self.z_order):
            box = self.boxes.get(p)
            covers = box is not None and any(
                grid.boxes_overlap(box, self.boxes[q]) for q in self.z_order[:i] if q in self.boxes)
            if covers:
                palette = p.palette()
                palette.setColor(QtGui.QPalette.Window, color)
                p.setPalette(palette)
            p.setAutoFillBackground(covers)

    # -- grid structure ----------------------------------------------------------
    def _insert_grid_track(self, axis, index):
        """Insert a new, empty column/row at line `index`; every edge at or
        past it shifts by one grid unit (grid.shift_span_for_insert)."""
        if axis == 'col':
            self.grid_cols = grid.insert_track(self.grid_cols, index)
        else:
            self.grid_rows = grid.insert_track(self.grid_rows, index)
        for p, (left, top, right, bottom) in list(self.boxes.items()):
            if axis == 'col':
                left, right = grid.shift_span_for_insert(left, right, index)
            else:
                top, bottom = grid.shift_span_for_insert(top, bottom, index)
            self.boxes[p] = (left, top, right, bottom)

    def _delete_grid_track(self, axis, index):
        """Inverse of _insert_grid_track: remove track `index`."""
        if self._n_tracks(axis) <= 1:
            return
        if axis == 'col':
            self.grid_cols = grid.delete_track(self.grid_cols, index)
        else:
            self.grid_rows = grid.delete_track(self.grid_rows, index)
        for p, (left, top, right, bottom) in list(self.boxes.items()):
            if axis == 'col':
                left, right = grid.shift_span_for_delete(left, right, index)
            else:
                top, bottom = grid.shift_span_for_delete(top, bottom, index)
            self.boxes[p] = (left, top, right, bottom)

    def _record_growth(self, plot_item, before):
        """add_subplot appended rows/columns to fit plot_item's box. Keep
        what the grid looked like before and after, so that removing
        plot_item as the undo of its own addition (paste, Add Subplot)
        shrinks the grid back -- see _undo_growth."""
        self._grid_growth.append({
            'plot': plot_item, 'before': before, 'retired': False,
            'after': (tuple(self.grid_cols), tuple(self.grid_rows)),
        })

    def _undo_growth(self, plot_item, restore):
        """plot_item was just removed. restore=False (a user Delete, which
        leaves a hole) forgets its growth record. restore=True (an undo)
        retires it, then pops every retired record off the top of the stack
        whose grid is still exactly what it produced and whose added
        tracks are empty now -- in stack order, so undoing a multi-subplot
        paste shrinks the grid back whatever order the subplots go in."""
        for rec in list(self._grid_growth):
            if rec['plot'] is plot_item:
                if restore:
                    rec['retired'] = True
                else:
                    self._grid_growth.remove(rec)
        while self._grid_growth and self._grid_growth[-1]['retired']:
            rec = self._grid_growth[-1]
            cols, rows = rec['before']
            if (tuple(self.grid_cols), tuple(self.grid_rows)) != rec['after']:
                break
            boxes = self.boxes.values()
            if not (all(grid.track_is_empty(boxes, 'col', c) for c in range(len(cols) - 1, self._n_tracks('col')))
                    and all(grid.track_is_empty(boxes, 'row', r) for r in range(len(rows) - 1, self._n_tracks('row')))):
                break
            self.grid_cols, self.grid_rows = list(cols), list(rows)
            self._grid_growth.pop()

    # -- adding/removing whole subplots ------------------------------------------
    # Plain add/delete only touches its own box -- it never shifts another
    # subplot (bug #1): a deleted subplot leaves a hole. FFT inserts a whole
    # grid row, which shifts edges by grid units -- safe for any layout with
    # fractional coordinates. _remove_subplot/_insert_subplot_at: plain.
    # insert_subplot_below / _insert_subplot_with_shift /
    # _remove_subplot_with_shift: FFT.

    def add_subplot(self, row, col, rowspan=1, colspan=1, title='', axes_type='cartesian'):
        """The only subplot construction site (guarded by
        test_add_subplot_is_the_only_subplot_construction_site): every new
        subplot adopts the figure-wide toggles here.

        The new subplot's box is the cells (row, col) .. (row + rowspan,
        col + colspan); the grid grows (new rows/columns appended) to fit
        it. axes_type ('cartesian' or '3d', see AXES_TYPES) is recorded on
        the PlotItem as `plot_item.axes_type`; a 3D cell is still this one
        PlotItem, with a View3DBox for ViewBox and no 2D axes."""
        if axes_type not in AXES_TYPES:
            raise NotImplementedError(f"axes_type={axes_type!r} is not implemented yet "
                                      f"(available: {', '.join(AXES_TYPES)})")
        is_3d = axes_type == '3d'
        plot_item = pg.PlotItem(title=title, viewBox=View3DBox() if is_3d else None)
        # Its geometry is ours (_apply_layout); its own size hints must not clamp it.
        plot_item.setMinimumSize(1, 1)
        self.layout_widget.scene().addItem(plot_item)
        box = (col, row, col + colspan, row + rowspan)
        before = (tuple(self.grid_cols), tuple(self.grid_rows))
        while self._n_tracks('col') < box[2]:
            self.grid_cols = grid.insert_track(self.grid_cols, self._n_tracks('col'))
        while self._n_tracks('row') < box[3]:
            self.grid_rows = grid.insert_track(self.grid_rows, self._n_tracks('row'))
        if (tuple(self.grid_cols), tuple(self.grid_rows)) != before:
            self._record_growth(plot_item, before)
        self.boxes[plot_item] = box
        self.z_order.append(plot_item)

        plot_item.axes_type = axes_type
        if is_3d:
            # The view's coordinates are the rendered image's pixels: no
            # 2D axis or grid means anything there.
            plot_item.hideAxis('left')
            plot_item.hideAxis('bottom')
        else:
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
        self._add_x_link_group_for(plot_item)
        self._apply_link_x()
        self._apply_layout()
        self.registry.notify_subplots_changed(self)
        return plot_item

    @staticmethod
    def _cell_of(box):
        return int(math.floor(box[1] + EPS)), int(math.floor(box[0] + EPS))

    def _grid_position(self, plot_item):
        """(row, col) of the cell holding the box's top-left corner -- where
        FFT/paste/delete-undo place things relative to this subplot."""
        return self._cell_of(self.boxes[plot_item])

    def _try_grid_position(self, plot_item):
        """Like _grid_position, but None for a plot this figure doesn't lay out."""
        box = self.boxes.get(plot_item)
        return self._cell_of(box) if box is not None else None

    def _detach_plot(self, plot_item):
        """Shared removal: annotations, scene, bookkeeping. Returns its box
        (None if this figure wasn't laying it out)."""
        for a in self._annotations_on(plot_item):
            self._purge_annotation(a)
        box = self.boxes.pop(plot_item, None)
        if plot_item in self.z_order:
            self.z_order.remove(plot_item)
        if plot_item.scene() is not None:
            plot_item.scene().removeItem(plot_item)
        self.plots.remove(plot_item)
        self._forget_removed_plot(plot_item)
        return box

    def _remove_subplot(self, plot_item, restore_grid=True):
        """Remove exactly this subplot. Leaves a hole -- no other subplot
        moves or resizes. restore_grid=True (the default, for undoing an
        addition: paste, Add Subplot) also shrinks back grid rows/columns
        that adding it created, if they are empty now; delete_subplot passes
        False, since a deleted subplot leaves its hole."""
        box = self._detach_plot(plot_item)
        if box is None:
            print(f"WARNING: _remove_subplot: {plot_item} had no layout box -- "
                  "removed it from bookkeeping only.", file=sys.stderr)
            row, col = None, None
        else:
            row, col = self._cell_of(box)
        self._undo_growth(plot_item, restore_grid)
        self._apply_layout()
        self.registry.notify_subplots_changed(self)
        return row, col

    def _insert_subplot_at(self, row, col, title, xlabel, ylabel, series_data, box=None,
                           axes_type='cartesian', view_state=None):
        """Place a new subplot in cell (row, col) -- or exactly at `box`,
        when restoring a deleted one -- without shifting anything. Inverse
        of _remove_subplot. series_data: BrushingMixin._series_full_dict
        outputs (Series.to_dict plus hidden/not-currently-drawn rows).
        axes_type/view_state: what _subplot_view_state captured (a 3D
        cell's camera), so a 3D subplot comes back as one."""
        new_plot = self.add_subplot(row=row, col=col, title=title, axes_type=axes_type)
        if box is not None:
            self.boxes[new_plot] = box
            self._apply_layout()
        if xlabel:
            new_plot.setLabel('bottom', xlabel)
        if ylabel:
            new_plot.setLabel('left', ylabel)
        for d in series_data:
            self._add_series_restoring(new_plot, d)
        self._apply_subplot_view_state(new_plot, view_state)
        return new_plot

    @staticmethod
    def _subplot_view_state(plot_item):
        """What a subplot's view needs beyond its series to come back the
        same (delete + undo, copy + paste): a 3D cell's camera; None for 2D,
        whose range is view state that isn't kept."""
        vb = plot_item.getViewBox()
        return {'camera': vb.camera_state()} if isinstance(vb, View3DBox) else None

    @staticmethod
    def _apply_subplot_view_state(plot_item, view_state):
        vb = plot_item.getViewBox()
        if view_state and isinstance(vb, View3DBox) and 'camera' in view_state:
            vb.set_camera_state(view_state['camera'])

    def insert_subplot_below(self, reference_plot, title=""):
        """FFT -> subplot below: insert a new grid row right under the
        reference's bottom edge and put a fresh subplot in it, in the
        reference's column. Only what lies below that line moves down (by
        one grid row); the result is an ordinary, freely movable subplot."""
        left, _, _, bottom = self.boxes[reference_plot]
        row = int(math.ceil(bottom - EPS))
        col = int(math.floor(left + EPS))
        self._insert_grid_track('row', row)
        return self.add_subplot(row=row, col=col, title=title)

    def _insert_subplot_with_shift(self, row, col, title, xlabel, ylabel, series_data):
        """Redo of an FFT insertion: insert grid row `row` again, then the
        subplot in cell (row, col) -- what insert_subplot_below did, without
        needing its (by now recreated) reference plot."""
        self._insert_grid_track('row', row)
        return self._insert_subplot_at(row, col, title, xlabel, ylabel, series_data)

    def _remove_subplot_with_shift(self, plot_item):
        """Undo of an FFT insertion: remove the subplot and the grid row it
        was inserted into, moving everything below back up one row."""
        box = self._detach_plot(plot_item)
        self._undo_growth(plot_item, restore=False)
        row, col = self._cell_of(box) if box is not None else (None, None)
        if row is not None:
            self._delete_grid_track('row', row)
        self._apply_layout()
        self.registry.notify_subplots_changed(self)
        return row, col

    @selection_op
    def _forget_removed_plot(self, plot_item):
        """Shared focused-plot/active-curve bookkeeping after a plot leaves
        self.plots, regardless of which removal path was used."""
        self._brushers.pop(plot_item, None)
        if plot_item in self.selected_plots:
            self.selected_plots.remove(plot_item)
        if self.selected_legend is plot_item:
            self.selected_legend = None
        if self.focused_plot is plot_item:
            self.focused_plot = self.plots[0] if self.plots else None
            if self.focused_plot is not None:
                self._mark_active(self.focused_plot, keep_selection=True)
        if self._hover_plot is plot_item:
            self._hover_plot = None
        for c in [c for c in self.selected_curves if self._curve_plot(c) is None]:
            self._forget_curve_selection(c)
        self._discard_x_link_badge(plot_item)
        self._x_link_groups.pop(plot_item, None)
        self._renumber_x_link_groups()
        self._relabel_x_link_badges()
        self._apply_link_x()

    def add_new_subplot(self):
        """Toolbar 'Add Subplot': fills the first empty grid cell (reading
        order), else appends a new row and uses its first cell."""
        cell = grid.first_empty_cell(list(self.boxes.values()),
                                     self._n_tracks('row'), self._n_tracks('col'))
        row, col = cell if cell is not None else (self._n_tracks('row'), 0)
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

    def delete_subplot(self, plot_item):
        min_subplots = 0 if self.empty else 1
        if len(self.plots) <= min_subplots:
            return  # keep at least one subplot (zero for a manager-created empty figure)
        title = plot_item.titleLabel.text
        xlabel = plot_item.getAxis('bottom').labelText
        ylabel = plot_item.getAxis('left').labelText
        series_data = [self._series_full_dict(s) for s in self._series_on(plot_item)]
        # Snapshot annotations first: _remove_subplot purges them unconditionally.
        annotations_data = [a.to_dict() for a in self._annotations_on(plot_item)]
        box = self.boxes.get(plot_item)
        z_index = self.z_order.index(plot_item) if plot_item in self.z_order else None
        axes_type = getattr(plot_item, 'axes_type', 'cartesian')
        view_state = self._subplot_view_state(plot_item)
        row, col = self._remove_subplot(plot_item, restore_grid=False)
        if row is None:
            # _remove_subplot's defensive fallback -- append a new row
            # rather than crashing undo with a None row/col.
            row, col, box = self._n_tracks('row'), 0, None

        holder = {}

        def undo_fn():
            new_plot = self._insert_subplot_at(row, col, title, xlabel, ylabel, series_data, box=box,
                                               axes_type=axes_type, view_state=view_state)
            if z_index is not None:
                self.z_order.remove(new_plot)
                self.z_order.insert(min(z_index, len(self.z_order)), new_plot)
                self._apply_layout()
            holder['plot'] = new_plot
            for d in annotations_data:
                AnnotationItem.from_dict(self, new_plot, d)
            self.focused_plot = new_plot
            self._mark_active(new_plot)

        def redo_fn():
            p = holder.get('plot')
            if p is not None:
                self._remove_subplot(p, restore_grid=False)

        self._push_history(undo_fn, redo_fn)

    # -- layout snapshots and undo -------------------------------------------------
    def _layout_snapshot(self):
        return {'cols': tuple(self.grid_cols), 'rows': tuple(self.grid_rows),
                'boxes': dict(self.boxes), 'z': tuple(self.z_order)}

    def _restore_layout(self, snap, structural=False):
        """Apply a snapshot to the subplots it knows that still exist. Like
        every closure on the undo stack, it holds PlotItem references: a
        subplot recreated since (delete + undo) is a new object it can't see.
        The grid lines are only restored if the track counts match, unless
        `structural` (undoing an insert/delete of a track itself)."""
        if structural or (len(snap['cols']) == len(self.grid_cols)
                          and len(snap['rows']) == len(self.grid_rows)):
            self.grid_cols, self.grid_rows = list(snap['cols']), list(snap['rows'])
        for p, box in snap['boxes'].items():
            if p in self.boxes:
                self.boxes[p] = box
        known = [p for p in snap['z'] if p in self.boxes]
        self.z_order = known + [p for p in self.z_order if p not in known]
        self._apply_layout()

    def _push_layout_change(self, before, structural=False):
        """One undo entry for whatever changed the layout since `before`
        (a _layout_snapshot()); nothing if it didn't change."""
        after = self._layout_snapshot()
        if after == before:
            return
        self._push_history(lambda: self._restore_layout(before, structural),
                           lambda: self._restore_layout(after, structural))

    def set_subplot_box(self, plot_item, box):
        """Place a subplot at an arbitrary box (left, top, right, bottom) in
        grid coordinates -- any fraction, e.g. an inset. Undoable."""
        before = self._layout_snapshot()
        left, top, right, bottom = box
        n_cols, n_rows = self._n_tracks('col'), self._n_tracks('row')
        left, right = max(0.0, min(left, n_cols)), max(0.0, min(right, n_cols))
        top, bottom = max(0.0, min(top, n_rows)), max(0.0, min(bottom, n_rows))
        if right - left <= EPS or bottom - top <= EPS:
            return
        self.boxes[plot_item] = (left, top, right, bottom)
        self._apply_layout()
        self._push_layout_change(before)

    def bring_to_front(self, plot_item):
        """Draw this subplot above every other one. Undoable."""
        self._restack(plot_item, top=True)

    def send_to_back(self, plot_item):
        """Draw this subplot below every other one. Undoable."""
        self._restack(plot_item, top=False)

    def _restack(self, plot_item, top):
        if plot_item not in self.z_order:
            return
        before = self._layout_snapshot()
        self.z_order.remove(plot_item)
        if top:
            self.z_order.append(plot_item)
        else:
            self.z_order.insert(0, plot_item)
        self._apply_layout()
        self._push_layout_change(before)

    def toggle_overlap_resize(self, checked):
        """Obsolete, kept only so the old "Grid Layout" toolbar button
        doesn't crash: there is no reflow-vs-overlap mode any more. Free
        positioning is the normal state, and two subplots overlap exactly
        when their boxes do."""
        pass

    def _reattach_all_floating(self):
        """Obsolete no-op, kept for clip_ops.paste_subplot's call site:
        nothing ever floats (is detached from a layout) any more."""
        pass

    # -- handles and gutters --------------------------------------------------------
    def _hide_handles(self):
        for handle in self.resize_handles.values():
            handle.hide()
        self.move_handle.hide()
        self._update_gutters()

    def _position_handles(self):
        self._reposition_annotations()
        active = self.focused_plot
        # focused_plot outlives its selection (e.g. a curve click deselects
        # its subplot but keeps it as toolbar target) -- no handles then.
        if active is None or active not in self.selected_plots or self.interaction_mode != 'select':
            self._hide_handles()
            return
        self._update_gutters()
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

    # -- X-link badges (view_ops.py owns grouping/cycling; this owns the scene item) --
    def _create_x_link_badge(self, plot_item):
        badge = XLinkBadge(self, plot_item)
        self.layout_widget.scene().addItem(badge)
        self._x_link_badges[plot_item] = badge

    def _discard_x_link_badge(self, plot_item):
        badge = self._x_link_badges.pop(plot_item, None)
        if badge is not None and badge.scene() is not None:
            badge.scene().removeItem(badge)

    def _update_x_link_badges(self):
        """Position every X-link badge at its subplot's current top-right
        corner, inset inward so it doesn't sit on the Select-mode resize
        handle anchored at that same corner point. Called from
        _apply_layout, the one place a subplot's geometry is set."""
        pad = 4
        for p, badge in self._x_link_badges.items():
            rect = p.sceneBoundingRect()
            badge.setPos(rect.right() - XLinkBadge.WIDTH - pad, rect.top() + pad)

    def _update_gutters(self):
        """One GutterHandle per stretch of an interior grid line that no
        subplot crosses, in Select mode only. Items are kept per (axis,
        line, stretch) key rather than rebuilt, so the gutter being dragged
        -- whose key can't change during its own drag -- keeps its grab."""
        wanted = {}
        if self.interaction_mode == 'select':
            boxes = list(self.boxes.values())
            for axis in ('col', 'row'):
                n, extent = self._n_tracks(axis), self._n_tracks('row' if axis == 'col' else 'col')
                for index in range(1, n):
                    for s, seg in enumerate(grid.gutter_segments(boxes, axis, index, extent)):
                        wanted[(axis, index, s)] = seg
        for key in [k for k in self._gutters if k not in wanted]:
            item = self._gutters.pop(key)
            if item.scene() is not None:
                item.scene().removeItem(item)
        half = self.GUTTER_PX / 2
        for key, (g0, g1) in wanted.items():
            item = self._gutters.get(key)
            if item is None:
                item = GutterHandle(self, key[0], key[1])
                self.layout_widget.scene().addItem(item)
                self._gutters[key] = item
            axis, index, _ = key
            if axis == 'col':
                x, y0, y1 = self._gx_to_px(index), self._gy_to_px(g0), self._gy_to_px(g1)
                item.setRect(x - half, y0, 2 * half, y1 - y0)
            else:
                y, x0, x1 = self._gy_to_px(index), self._gx_to_px(g0), self._gx_to_px(g1)
                item.setRect(x0, y - half, x1 - x0, 2 * half)
            item.show()

    def _gutter_under(self, scene_pos):
        """The GutterHandle a press at scene_pos would reach, if any."""
        for item in self.layout_widget.scene().items(scene_pos):
            if item.isVisible() and item.acceptedMouseButtons():
                return item if isinstance(item, GutterHandle) else None
        return None

    def eventFilter(self, obj, event):
        """A press on a gutter belongs to the gutter's own drag: the rubber
        band (selection_ui._band_event, reached through the scene filter
        chain) would arm on it -- a gutter is "nothing selectable" to it --
        and then consume the drag's moves. Let the chain run, then disarm
        the band for such a press."""
        consumed = super().eventFilter(obj, event)
        if (not consumed and obj is self.layout_widget.scene()
                and event.type() == QtCore.QEvent.GraphicsSceneMousePress
                and self._band is not None and self._gutter_under(event.scenePos()) is not None):
            self._band = None
        return consumed

    # -- magnetic snapping ------------------------------------------------------------
    def _snap_candidates(self, axis, exclude=()):
        """Grid coordinates a dragged edge on `axis` ('x' or 'y') may snap
        to: grid lines (0 and n being the figure margins), cell
        subdivisions, and the edges of every subplot not in `exclude`."""
        n = self._n_tracks(axis)
        subdiv = max(1, int(self.snap_subdivisions))
        cands = [(float(k), 'line') for k in range(n + 1)]
        cands += [(k + j / subdiv, 'sub') for k in range(n) for j in range(1, subdiv)]
        lo, hi = (0, 2) if axis == 'x' else (1, 3)
        for p, box in self.boxes.items():
            if p not in exclude:
                cands += [(box[lo], 'edge'), (box[hi], 'edge')]
        return cands

    def _nearest_snap(self, axis, px, cands):
        """(grid coordinate, pixel distance) of the candidate nearest `px`
        within SNAP_PX, or None."""
        best = None
        for g, _ in cands:
            d = abs(self._g_to_px(axis, g) - px)
            if d <= self.SNAP_PX and (best is None or d < best[1]):
                best = (g, d)
        return best

    def _show_snap_guides(self, guides=()):
        """Show the magnetic sub-grid; `guides` = [(axis, grid coord)] of
        the active snaps, drawn highlighted across the whole figure."""
        r = self._figure_rect()
        subdiv = max(1, int(self.snap_subdivisions))
        lines = []
        for axis in ('x', 'y'):
            n = self._n_tracks(axis)
            for k in range(n + 1):
                for j in range(subdiv if k < n else 1):
                    px = self._g_to_px(axis, k + j / subdiv)
                    kind = 'line' if j == 0 else 'sub'
                    lines.append((px, r.top(), px, r.bottom(), kind) if axis == 'x'
                                 else (r.left(), px, r.right(), px, kind))
        drawn = []
        for axis, g in guides:
            px = self._g_to_px(axis, g)
            drawn.append((px, r.top(), px, r.bottom()) if axis == 'x' else (r.left(), px, r.right(), px))
        self._snap_guides.set_content(r, lines, drawn)
        self._snap_guides.show()

    def _hide_snap_guides(self):
        self._snap_guides.hide()

    @staticmethod
    def _snapping(mods):
        return not (mods & QtCore.Qt.AltModifier)

    # -- resize one subplot (drag a border/corner handle) --------------------------
    def _begin_resize(self, role, scene_pos):
        p = self.focused_plot
        if p is None or p not in self.boxes:
            return
        self._resize_state = {
            'role': role, 'plot': p, 'origin': QtCore.QPointF(scene_pos),
            'start_box': self.boxes[p], 'before': self._layout_snapshot(),
        }
        self._show_snap_guides()

    def _update_resize(self, scene_pos, mods=QtCore.Qt.NoModifier):
        """Move the dragged edge(s) of the one subplot being resized, in
        pixels from where they started, snapped unless Alt is held. Only
        this subplot's box changes -- neighbors never move (bug #6)."""
        st = self._resize_state
        if st is None:
            return
        p, role = st['plot'], st['role']
        left, top, right, bottom = st['start_box']
        dx = scene_pos.x() - st['origin'].x()
        dy = scene_pos.y() - st['origin'].y()
        snap = self._snapping(mods)
        guides = []

        def drag_edge(axis, g, delta, fixed, sign):
            px = self._g_to_px(axis, g) + delta
            # Never closer than MIN_BOX_PX to the opposite, fixed edge.
            limit = self._g_to_px(axis, fixed) + sign * self.MIN_BOX_PX
            px = max(px, limit) if sign > 0 else min(px, limit)
            new = self._px_to_g(axis, px)
            if snap:
                hit = self._nearest_snap(axis, px, self._snap_candidates(axis, exclude=(p,)))
                if hit is not None and sign * (self._g_to_px(axis, hit[0]) - limit) >= 0:
                    new = hit[0]
                    guides.append((axis, new))
            return new

        if 'left' in role:
            left = drag_edge('x', left, dx, right, -1)
        elif 'right' in role:
            right = drag_edge('x', right, dx, left, +1)
        if 'top' in role:
            top = drag_edge('y', top, dy, bottom, -1)
        elif 'bottom' in role:
            bottom = drag_edge('y', bottom, dy, top, +1)
        self.boxes[p] = (left, top, right, bottom)
        self._apply_layout()
        self._show_snap_guides(guides)

    def _end_resize(self):
        st = self._resize_state
        if st is None:
            return
        self._resize_state = None
        self._hide_snap_guides()
        self._position_handles()
        self._push_layout_change(st['before'])

    # -- move / swap (drag the move handle, Select mode only) ----------------------
    def _begin_move(self, scene_pos):
        p = self.focused_plot
        if p is None or self.interaction_mode != 'select' or p not in self.boxes:
            return
        self._move_state = {
            'plot': p, 'start_box': self.boxes[p], 'before': self._layout_snapshot(),
            'origin': (self._px_to_gx(scene_pos.x()), self._px_to_gy(scene_pos.y())),
        }
        # Drawn on top while it moves; _apply_layout restores its z_order place.
        p.setZValue(self.PLOT_Z + len(self.z_order))
        self._show_snap_guides()

    def _update_move(self, scene_pos, mods=QtCore.Qt.NoModifier):
        """Translate the box by the mouse's motion in grid units -- so it
        keeps its grid size (a one-cell subplot stays one cell wide), and
        snap whichever of its edges is nearest a candidate."""
        st = self._move_state
        if st is None:
            return
        p = st['plot']
        left, top, right, bottom = st['start_box']
        gx0, gy0 = st['origin']
        guides = []
        new = {}
        for axis, lo0, hi0, g0, pos in (('x', left, right, gx0, scene_pos.x()),
                                        ('y', top, bottom, gy0, scene_pos.y())):
            size, n = hi0 - lo0, self._n_tracks(axis)
            lo = min(max(lo0 + self._px_to_g(axis, pos) - g0, 0.0), n - size)
            hi = lo + size
            if self._snapping(mods):
                cands = self._snap_candidates(axis, exclude=(p,))
                best = None   # (pixel distance, snapped edge is the high one, grid coord)
                for is_hi, edge in ((False, lo), (True, hi)):
                    hit = self._nearest_snap(axis, self._g_to_px(axis, edge), cands)
                    if hit is not None and (best is None or hit[1] < best[0]):
                        best = (hit[1], is_hi, hit[0])
                if best is not None:
                    _, is_hi, g = best
                    # The snapped edge takes the candidate's exact value.
                    snapped = (g - size, g) if is_hi else (g, g + size)
                    if snapped[0] >= -EPS and snapped[1] <= n + EPS:
                        lo, hi = snapped
                        guides.append((axis, g))
            new[axis] = (lo, hi)
        (left, right), (top, bottom) = new['x'], new['y']
        self.boxes[p] = (left, top, right, bottom)
        self._apply_layout()
        p.setZValue(self.PLOT_Z + len(self.z_order))
        self._show_snap_guides(guides)

    def _end_move(self, scene_pos, mods=QtCore.Qt.NoModifier):
        """Plain drop: the subplot stays where it was dragged. Ctrl+drop
        onto another subplot: the two swap boxes (the dragged one takes the
        target's, the target takes the dragged one's starting box)."""
        st = self._move_state
        if st is None:
            return
        self._move_state = None
        self._hide_snap_guides()
        p = st['plot']
        if mods & QtCore.Qt.ControlModifier:
            target = self._plot_at(scene_pos, exclude=p)
            if target is not None:
                self.boxes[p] = self.boxes[target]
                self.boxes[target] = st['start_box']
        self._apply_layout()
        self._push_layout_change(st['before'])

    def _plot_at(self, scene_pos, exclude=None):
        """The topmost subplot whose drawn box contains scene_pos."""
        for p in self._plots_by_z():
            if p is not exclude and p.sceneBoundingRect().contains(scene_pos):
                return p
        return None

    def _plots_by_z(self):
        """Every subplot, topmost first: the order a hit test must try them
        in once subplots can overlap (an inset above its host)."""
        return list(reversed(self.z_order))

    # -- 'border' annotations: offsets as a fraction of the subplot's box ----------
    def _box_fraction(self, plot_item, scene_pos):
        """scene_pos as a fraction of plot_item's drawn box: (0, 0) is its
        top-left corner, (1, 1) its bottom-right. Meant as a 'border'
        annotation's anchor_offset, so the annotation keeps its relative
        place when the subplot is resized (Annotations simplification #5)."""
        r = plot_item.sceneBoundingRect()
        return QtCore.QPointF((scene_pos.x() - r.left()) / max(r.width(), EPS),
                              (scene_pos.y() - r.top()) / max(r.height(), EPS))

    def _box_point(self, plot_item, fraction):
        """Inverse of _box_fraction: the scene point at `fraction` of the box."""
        r = plot_item.sceneBoundingRect()
        return QtCore.QPointF(r.left() + fraction.x() * r.width(),
                              r.top() + fraction.y() * r.height())

    # -- grid-line drag (drag a gutter) --------------------------------------------
    def _begin_gutter_drag(self, axis, index, scene_pos):
        if self.interaction_mode != 'select' or not 0 < index < self._n_tracks(axis):
            return
        lines = self.grid_cols if axis == 'col' else self.grid_rows
        self._gutter_state = {
            'axis': axis, 'index': index, 'origin': QtCore.QPointF(scene_pos),
            'start': lines[index], 'before': self._layout_snapshot(),
        }
        self._show_snap_guides()

    def _update_gutter_drag(self, scene_pos, mods=QtCore.Qt.NoModifier):
        """Move grid line `index`: every edge between its two neighbor
        lines rescales with it (grid coordinates never change); it can't
        squeeze a track below MIN_TRACK_PX. Snaps to where the two tracks
        would be equal, to where all tracks would be equal, and to the
        edges of subplots that don't move with it."""
        st = self._gutter_state
        if st is None:
            return
        axis, index = st['axis'], st['index']
        r = self._figure_rect()
        size = r.width() if axis == 'col' else r.height()
        d = (scene_pos.x() - st['origin'].x()) if axis == 'col' else (scene_pos.y() - st['origin'].y())
        lines = list(self.grid_cols if axis == 'col' else self.grid_rows)
        frac = st['start'] + d / size
        snapped = False
        if self._snapping(mods):
            n = len(lines) - 1
            cands = [(lines[index - 1] + lines[index + 1]) / 2, index / n]
            lo, hi = (0, 2) if axis == 'col' else (1, 3)
            for box in self.boxes.values():
                for e in (box[lo], box[hi]):
                    if e <= index - 1 + EPS or e >= index + 1 - EPS:
                        cands.append(grid.to_frac(lines, e))
            best = min(cands, key=lambda c: abs(c - frac))
            if abs(best - frac) * size <= self.SNAP_PX:
                frac, snapped = best, True
        margin = self.MIN_TRACK_PX / size
        low, high = lines[index - 1] + margin, lines[index + 1] - margin
        frac = min(max(frac, low), high) if low <= high else st['start']
        lines[index] = frac
        if axis == 'col':
            self.grid_cols = lines
        else:
            self.grid_rows = lines
        self._apply_layout()
        self._show_snap_guides([('x' if axis == 'col' else 'y', index)] if snapped else [])

    def _end_gutter_drag(self):
        st = self._gutter_state
        if st is None:
            return
        self._gutter_state = None
        self._hide_snap_guides()
        self._push_layout_change(st['before'])

    # -- gutter right-click menu ----------------------------------------------------
    def _build_gutter_menu(self, axis, index):
        """Insert a column/row at this line, delete the (empty) one on
        either side, or make every column/row the same size."""
        menu = QtWidgets.QMenu(self)
        word, before_word, after_word = (("Column", "Left", "Right") if axis == 'col'
                                         else ("Row", "Above", "Below"))
        menu.addAction(f"Insert {word} Here").triggered.connect(
            lambda: self.insert_grid_track(axis, index))
        boxes = list(self.boxes.values())
        for label, track in ((before_word, index - 1), (after_word, index)):
            act = menu.addAction(f"Delete {word} {label}")
            act.setEnabled(self._n_tracks(axis) > 1 and grid.track_is_empty(boxes, axis, track))
            act.triggered.connect(lambda checked=False, t=track: self.delete_grid_track(axis, t))
        menu.addSeparator()
        menu.addAction(f"Equalize {word}s").triggered.connect(lambda: self.equalize_grid(axis))
        return menu

    def _show_gutter_menu(self, axis, index, screen_pos):
        self._build_gutter_menu(axis, index).exec_(QtCore.QPointF(screen_pos).toPoint())

    def insert_grid_track(self, axis, index):
        """Insert an empty column ('col') or row ('row') at grid line
        `index`; whatever lies past it shifts by one track. Undoable."""
        before = self._layout_snapshot()
        self._insert_grid_track(axis, index)
        self._apply_layout()
        self._push_layout_change(before, structural=True)

    def delete_grid_track(self, axis, index):
        """Delete column/row `index`, only if no subplot covers any of it.
        Undoable."""
        if self._n_tracks(axis) <= 1 or not grid.track_is_empty(list(self.boxes.values()), axis, index):
            return
        before = self._layout_snapshot()
        self._delete_grid_track(axis, index)
        self._apply_layout()
        self._push_layout_change(before, structural=True)

    def equalize_grid(self, axis):
        """Make every column ('col') or row ('row') the same size. Undoable."""
        before = self._layout_snapshot()
        lines = grid.equal_lines(self._n_tracks(axis))
        if axis == 'col':
            self.grid_cols = lines
        else:
            self.grid_rows = lines
        self._apply_layout()
        self._push_layout_change(before)
