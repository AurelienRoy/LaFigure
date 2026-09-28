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

"""Selection: the central scene click dispatcher, subplot/curve/annotation
selection (exclusive across kinds unless Shift is held), the focused
subplot, rubber-band selection, arrow-key nudge and Tab cycling.

Also the emission sites for the registry's focusChanged (the
focused_plot property setter -- the only writer) and selectionChanged
(_notify_selection_changed) signals.
"""
import functools

from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg

from .handles import ResizeHandle, MoveHandle
from .annotations import AnnotationItem, TWO_CLICK_KINDS


def selection_op(fn):
    """Mark a method that may change the selection lists. Nested calls are
    batched: only the outermost one reports, once, through
    _notify_selection_changed -- so one click emits selectionChanged at
    most once, never for the intermediate "cleared" state a plain click
    passes through. Use it on any new method that edits selected_plots/
    selected_curves/selected_annotations."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        self._selection_depth += 1
        try:
            return fn(self, *args, **kwargs)
        finally:
            self._selection_depth -= 1
            if self._selection_depth == 0:
                self._notify_selection_changed()
    return wrapper


class SelectionUIMixin:
    NUDGE_PX = 1        # arrow key: move selected annotations 1 screen pixel
    NUDGE_BIG_PX = 10   # Shift+arrow
    BAND_MIN_DRAG_PX = 3  # below this a press+release on empty space is a click

    # -- focus and change notification -------------------------------------
    @property
    def focused_plot(self):
        """The focused subplot (CLAUDE.md glossary): the selected subplot,
        or else the one that received the last action -- the target of
        toolbar actions (FFT, Remove Average, Paste Curve, ...). It
        outlives its selection: clicking a curve deselects the curve's
        subplot but keeps it focused. Distinct from _hover_plot, which
        only Home/Fit use."""
        return self._focused_plot

    @focused_plot.setter
    def focused_plot(self, plot_item):
        # The only writer of focus: every assignment in the package goes
        # through here, so this is the one emission site of focusChanged.
        if plot_item is self._focused_plot:
            return
        self._focused_plot = plot_item
        self.registry.notify_focus_changed(self, plot_item)

    def _notify_selection_changed(self):
        """Emit the registry's selectionChanged if the selection differs
        from what it last reported. Called by selection_op on the way out
        of the outermost selection-changing call; safe to call anywhere."""
        current = (tuple(self.selected_plots), tuple(self.selected_curves),
                   tuple(self.selected_annotations))
        if current == self._last_selection:
            return
        self._last_selection = current
        self.registry.notify_selection_changed(self)

    # -- click dispatch and subplot selection --------------------------------
    @selection_op
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
        if self._suppress_click:
            self._suppress_click = False
            return
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
        for p in self._plots_by_z():
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

    @selection_op
    def _on_plot_clicked(self, plot_item, additive=False):
        """additive = Shift: toggle this subplot in/out of the selection,
        as in LibreOffice Draw and MATLAB. focused_plot keeps tracking the
        clicked subplot either way -- it is the toolbar target."""
        self.focused_plot = plot_item
        if additive:
            if plot_item in self.selected_plots:
                self.selected_plots.remove(plot_item)
            else:
                self.selected_plots.append(plot_item)
            self._mark_active(plot_item, keep_selection=True)
        else:
            self._mark_active(plot_item)

    @selection_op
    def _on_plot_context(self, plot_item):
        """Right-click: keep a selection that already involves this subplot
        (so menu actions see the whole Shift-built set), else select the
        subplot like a plain click."""
        involved = plot_item in self.selected_plots or any(
            self._curve_plot(c) is plot_item for c in self.selected_curves)
        if involved:
            self.focused_plot = plot_item
            self._mark_active(plot_item, keep_selection=True)
        else:
            self._on_plot_clicked(plot_item)

    @selection_op
    def _select_plots(self, plots):
        """Exclusively select `plots` (e.g. just-pasted subplots)."""
        self._clear_selection()
        self.focused_plot = plots[-1]
        self.selected_plots = list(plots)
        self._mark_active(self.focused_plot, keep_selection=True)

    def _on_scene_hovered(self, pos):
        """sigMouseMoved gives scene coords directly (unlike sigMouseClicked's
        event object) -- pos is already what the hit-test loop below needs."""
        for p in self._plots_by_z():
            if p.getViewBox().sceneBoundingRect().contains(pos):
                self._hover_plot = p
                break

    @selection_op
    def _deselect_all(self):
        """Double-click a subplot, or a single click that lands outside
        every subplot: clear every selection AND the focused subplot."""
        self._clear_selection()
        self.focused_plot = None
        for p in self.plots:
            p.getViewBox().setBorder(None)
        self._hide_handles()

    @selection_op
    def _clear_selection(self):
        """Deselect every kind -- subplots, curves, annotation. Any selection
        without Shift starts here: selections are exclusive across kinds.
        focused_plot is left alone; it is the toolbar target, not a selection."""
        self._deselect_curve()
        self._deselect_annotation()
        self.selected_plots = []

    @selection_op
    def _mark_active(self, active, keep_selection=False):
        # The red border / move+resize handles only ever show in Select
        # mode -- Hand and Zoom Rect are explicitly "no selection" modes,
        # even though self.focused_plot itself keeps tracking the last
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
            self.focused_plot = plot_item
            self._mark_active(plot_item, keep_selection=True)

        curve.curve.sigClicked.connect(handler)

    def _highlight_curve_pen(self, curve):
        orig_pen = curve.opts.get('pen')
        no_line = orig_pen is None or pg.mkPen(orig_pen).style() == QtCore.Qt.NoPen
        if no_line and curve.opts.get('symbol') is not None:
            # Dots without a line (e.g. the demo's scatters): outline the
            # dots -- giving them a pen would draw a line through every point.
            curve.opts.setdefault('_orig_symbol_pen', curve.opts.get('symbolPen'))
            curve.setSymbolPen(pg.mkPen('k', width=1.5))
            return
        curve.opts.setdefault('_orig_pen', orig_pen)
        base = pg.mkPen(orig_pen) if orig_pen is not None else pg.mkPen('k')
        curve.setPen(pg.mkPen(color=base.color(), width=base.width() + 3))

    @selection_op
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
        if '_orig_symbol_pen' in curve.opts:
            curve.setSymbolPen(curve.opts['_orig_symbol_pen'])

    @selection_op
    def _deselect_curve(self):
        for c in self.selected_curves:
            self._unhighlight_curve_pen(c)
        self.selected_curves = []
        self.active_curve = None

    @selection_op
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

    # -- rubber-band selection (LibreOffice Draw / MATLAB) ------------------
    def _can_start_band_at(self, scene_pos):
        """Nothing selectable under the cursor, as in LibreOffice: not on an
        annotation or its handles, a subplot resize/move handle, a curve or
        a legend (pyqtgraph would hand those the release as a click). Then
        either outside every subplot, or inside a subplot's data area --
        which Select mode otherwise leaves idle (the gutters between
        subplots are only a few pixels wide) -- unless brushing claims that
        drag. Axes and titles never start one."""
        in_plot = [p for p in self.plots if p.sceneBoundingRect().contains(scene_pos)]
        if in_plot and (self.brushing or not any(
                p.getViewBox().sceneBoundingRect().contains(scene_pos) for p in in_plot)):
            return False
        for p in in_plot:
            for c in p.listDataItems():
                if (isinstance(c, pg.PlotDataItem) and getattr(c.curve, 'clickable', False)
                        and c.curve.mouseShape().contains(c.curve.mapFromScene(scene_pos))):
                    return False
        for item in self.layout_widget.scene().items(scene_pos):
            if isinstance(item, (ResizeHandle, MoveHandle)) and item.isVisible():
                return False
            while item is not None:
                if isinstance(item, (AnnotationItem, pg.LegendItem)):
                    return False
                item = item.parentItem()
        return True

    def _band_event(self, event):
        """A left press where _can_start_band_at arms the band; it only appears once the
        drag passes BAND_MIN_DRAG_PX, so a plain click still deselects.
        Press and release are never consumed (pyqtgraph must still see
        them); the moves are, once the band is showing."""
        etype = event.type()
        if etype == QtCore.QEvent.GraphicsSceneMousePress:
            self._band = None
            self._suppress_click = False
            if (event.button() == QtCore.Qt.LeftButton and self.interaction_mode == 'select'
                    and self._placing_kind is None and self._relink_source is None
                    and self._can_start_band_at(event.scenePos())):
                self._band = {
                    'origin': QtCore.QPointF(event.scenePos()),
                    'additive': bool(event.modifiers() & QtCore.Qt.ShiftModifier),
                    'item': None,
                }
            return False
        if self._band is None:
            return False
        if etype == QtCore.QEvent.GraphicsSceneMouseMove:
            rect = QtCore.QRectF(self._band['origin'], event.scenePos()).normalized()
            if self._band['item'] is None:
                if max(rect.width(), rect.height()) < self.BAND_MIN_DRAG_PX:
                    return False
                item = QtWidgets.QGraphicsRectItem()
                pen = pg.mkPen((40, 90, 200), width=1, style=QtCore.Qt.DashLine)
                pen.setCosmetic(True)
                item.setPen(pen)
                item.setBrush(pg.mkBrush(40, 90, 200, 30))
                item.setZValue(1e6)
                self.layout_widget.scene().addItem(item)
                self._band['item'] = item
            self._band['item'].setRect(rect)
            return True
        if etype == QtCore.QEvent.GraphicsSceneMouseRelease:
            band, self._band = self._band, None
            if band['item'] is not None:
                rect = QtCore.QRectF(band['origin'], event.scenePos()).normalized()
                self.layout_widget.scene().removeItem(band['item'])
                self._select_in_rect(rect, band['additive'])
                self._suppress_click = True
            return False
        return False

    @selection_op
    def _select_in_rect(self, rect, additive=False):
        """Select every subplot (its data area) and annotation (its shape,
        without handle padding) lying fully inside the scene rect `rect`.
        Shift adds to the selection; otherwise the band replaces it."""
        plots = [p for p in self.plots if rect.contains(p.getViewBox().sceneBoundingRect())]
        anns = [a for a in self.annotations if rect.contains(a.shape_scene_rect())]
        if not additive:
            self._clear_selection()
        for p in plots:
            if p not in self.selected_plots:
                self.selected_plots.append(p)
        if plots:
            self.focused_plot = plots[-1]
        for a in anns:
            if a not in self.selected_annotations:
                self._select_annotation(a, additive=True)
        self._mark_active(self.focused_plot, keep_selection=True)

    # -- keyboard: arrow-key nudge, Tab cycling ------------------------------
    def nudge_selection(self, dx_px, dy_px):
        """Move every selected annotation by (dx_px, dy_px) screen pixels,
        as one undo entry. Subplots are grid cells and curves are data, so
        neither moves."""
        if self.interaction_mode != 'select' or not self.selected_annotations:
            return
        delta = QtCore.QPointF(dx_px, dy_px)
        with self.undo_group():
            for a in self.selected_annotations:
                parent = a.parentItem()
                origin = a.pos()
                if parent is None:
                    target = origin + delta
                else:
                    target = parent.mapFromScene(parent.mapToScene(origin) + delta)
                a.setPos(target)
                a._push_move_history(origin, target)

    def _tab_order(self):
        """Every selectable item in reading order: subplots top-to-bottom,
        left-to-right, each followed by its clickable curves and its own
        annotations; free-floating (figure) annotations last."""
        def reading_key(rect):
            return (round(rect.top()), round(rect.left()))

        order = []
        for p in sorted(self.plots, key=lambda p: reading_key(p.sceneBoundingRect())):
            order.append(p)
            order.extend(c for c in p.listDataItems()
                         if isinstance(c, pg.PlotDataItem) and getattr(c.curve, 'clickable', False))
            order.extend(sorted((a for a in self.annotations if a.parent_plot is p),
                                key=lambda a: reading_key(a.shape_scene_rect())))
        order.extend(sorted((a for a in self.annotations if a.parent_plot is None),
                            key=lambda a: reading_key(a.shape_scene_rect())))
        return order

    @selection_op
    def cycle_selection(self, step):
        """Tab / Shift+Tab: select the next / previous item of _tab_order,
        exclusively. Starts from the one selected item, or from either end
        when zero or several items are selected."""
        if self.interaction_mode != 'select':
            return
        order = self._tab_order()
        if not order:
            return
        selected = self.selected_plots + self.selected_curves + self.selected_annotations
        if len(selected) == 1 and selected[0] in order:
            idx = (order.index(selected[0]) + step) % len(order)
        else:
            idx = 0 if step > 0 else len(order) - 1
        target = order[idx]
        if isinstance(target, AnnotationItem):
            self._select_annotation(target)
        elif isinstance(target, pg.PlotDataItem):
            self._select_curve(target)
            self.focused_plot = self._curve_plot(target)
            self._mark_active(self.focused_plot, keep_selection=True)
        else:
            self._on_plot_clicked(target)

    # -- annotation selection ------------------------------------------------
    @selection_op
    def _select_annotation(self, ann, additive=False):
        """additive = Shift: toggle `ann` in/out of the selection, keeping
        everything else selected. Otherwise select only `ann`."""
        if not additive:
            self._clear_selection()
            self._mark_active(self.focused_plot, keep_selection=True)
        elif ann in self.selected_annotations:
            ann.set_selected(False)
            self._forget_annotation_selection(ann)
            return
        self.selected_annotations.append(ann)
        self.active_annotation = ann
        ann.set_selected(True)

    @selection_op
    def _deselect_annotation(self):
        for a in self.selected_annotations:
            a.set_selected(False)
        self.selected_annotations = []
        self.active_annotation = None

    @selection_op
    def _forget_annotation_selection(self, ann):
        if ann in self.selected_annotations:
            self.selected_annotations.remove(ann)
        if ann is self.active_annotation:
            self.active_annotation = self.selected_annotations[-1] if self.selected_annotations else None
