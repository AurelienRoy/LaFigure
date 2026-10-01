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

"""Selection: the central scene click dispatcher, subplot/curve/annotation
selection (exclusive across kinds unless Shift is held), the focused
subplot, rubber-band selection, arrow-key nudge and Tab cycling.

Also the emission sites for the registry's focusChanged (the
focused_plot property setter -- the only writer) and selectionChanged
(_notify_selection_changed) signals.
"""
import functools
import logging
import time

from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg

from .handles import ResizeHandle, MoveHandle
from .annotations import AnnotationItem, TWO_CLICK_KINDS

# Debug mode (lafigure.debug.enable_debug_mode, WP-DBG1): plain
# hierarchical stdlib logging -- this child logger needs no wiring of its
# own, whatever handlers/level enable_debug_mode() attaches to the root
# 'lafigure' logger apply here for free.
logger = logging.getLogger('lafigure.selection_ui')

CLICK_CYCLE_TOLERANCE_PX = 4
CLICK_CYCLE_TIMEOUT_S = 1.0
# A real click landing this many screen pixels off a curve's own drawn
# line/marker still selects it -- MATLAB/LibreOffice style, not a
# razor-thin hit region. Applied on top of whatever the curve/marker
# already draws (a line's own width, a marker's own radius), never
# instead of it.
CLICK_HIT_TOLERANCE_PX = 4


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
    def _click_gesture_desc(self, ev, additive):
        """Short gesture label for the debug log: some combination of
        plain/shift/right-click/double-click (a single click is 'plain')."""
        parts = []
        if ev.button() == QtCore.Qt.RightButton:
            parts.append('right-click')
        if additive:
            parts.append('shift')
        if ev.double():
            parts.append('double-click')
        return '+'.join(parts) if parts else 'plain'

    def _click_hit_desc(self, hit_plot, pos):
        """Short description of what a click at scene position `pos`
        actually hit -- an annotation, a curve, a subplot, or empty space --
        for the debug log. Reuses the same per-kind hit-tests ordinary
        dispatch itself uses (_annotation_at, _curves_at), so the
        description matches what was actually eligible to be selected."""
        ann = self._annotation_at(pos)
        if ann is not None:
            return ("annotation '%s' (%s)" % (ann.text, ann.kind) if ann.text
                     else "annotation (%s)" % ann.kind)
        if hit_plot is not None:
            curves = self._curves_at(hit_plot, pos)
            if curves:
                return "curve '%s'" % (curves[0].opts.get('name') or '<unnamed>')
            return "subplot '%s'" % self.subplot_name(hit_plot)
        return "empty space"

    def _click_selection_desc(self):
        """Short summary of the resulting selection, for the debug log."""
        focused = self.subplot_name(self.focused_plot) if self.focused_plot is not None else None
        active = self.active_curve.opts.get('name') if self.active_curve is not None else None
        return ("plots=%d curves=%d annotations=%d focused_plot=%r active_curve=%r"
                 % (len(self.selected_plots), len(self.selected_curves),
                    len(self.selected_annotations), focused, active))

    def _log_click_dispatch(self, ev, additive, hit_plot, pos, outcome):
        """One DEBUG line per dispatched click: the gesture, what was
        actually hit, and the resulting selection outcome -- for the
        copy-pasteable debug log (CLAUDE.md's debug-mode roadmap item,
        Round 3/DBG3). _on_scene_clicked is the one central dispatcher
        (CLAUDE.md's "What worked well: one central click dispatcher"), so
        this is the one place a click's final outcome is logged."""
        logger.debug("click: gesture=%s hit=%s -> %s (%s)",
                     self._click_gesture_desc(ev, additive), self._click_hit_desc(hit_plot, pos),
                     outcome, self._click_selection_desc())

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
            kind = self._placing_kind
            if not ev.double() and self._placing_kind not in TWO_CLICK_KINDS:
                self._handle_placement_click(pos)
            self._log_click_dispatch(ev, additive, None, pos, "placing annotation '%s'" % kind)
            return

        if self._relink_source is not None:
            if not ev.double():
                self._handle_relink_click(pos)
            self._log_click_dispatch(ev, additive, None, pos, "relink")
            return

        hit_plot = None
        for p in self._plots_by_z():
            if p.getViewBox().sceneBoundingRect().contains(pos):
                hit_plot = p
                break

        if (self.interaction_mode == 'zoom' and hit_plot is not None
                and ev.button() == QtCore.Qt.LeftButton
                and getattr(hit_plot, 'axes_type', 'cartesian') != '3d'):
            # Zoom Rect mode's plain-click behavior: a drag still draws a
            # zoom rectangle (pyqtgraph's own RectMode), but a click with
            # no drag was otherwise a no-op -- now single click zooms in,
            # double click zooms out (see _click_zoom).
            self._on_plot_clicked(hit_plot, additive=False)
            self._click_zoom(hit_plot, pos, out=ev.double())
            self._log_click_dispatch(ev, additive, hit_plot, pos,
                                      "zoom %s" % ('out' if ev.double() else 'in'))
            return

        if (self.interaction_mode == 'cursor' and hit_plot is not None
                and ev.button() == QtCore.Qt.LeftButton):
            # Data Cursor mode: a click on empty data area moves (or, with
            # Shift, adds) that subplot's datacursor -- see
            # _handle_cursor_mode_click. A click that actually lands on an
            # existing datacursor's own marker/text/line never reaches
            # here at all: AnnotationItem's native mousePressEvent (kind
            # == 'cursor') consumes it first, same as every other
            # annotation drag (see CLAUDE.md's note on native-vs-pyqtgraph
            # click dispatch).
            self._handle_cursor_mode_click(hit_plot, pos, additive=additive)
            self._log_click_dispatch(ev, additive, hit_plot, pos, "cursor mode click")
            return

        if (hit_plot is None and ev.button() == QtCore.Qt.RightButton
                and not ev.double() and not ev.isAccepted()
                and self._annotation_at(pos) is None):
            # A right-click inside some subplot's ViewBox already gets its
            # own context menu from pyqtgraph (see _wire_context_menu) --
            # this covers right-clicking truly empty space instead, which
            # otherwise did nothing but deselect everything. A right-click
            # on a figure/border-anchored annotation (outside every
            # subplot) is excluded too: its own contextMenuEvent (a
            # separate native Qt event) already handles that click.
            self._show_empty_space_menu()
            self._log_click_dispatch(ev, additive, hit_plot, pos, "opened empty-space menu")
            return

        if ev.double():
            self._deselect_all()
            self._log_click_dispatch(ev, additive, hit_plot, pos, "deselected all (double-click)")
            return

        if hit_plot is not None:
            # Accepted = a curve (or legend sample) already handled this
            # click; selecting the subplot too would undo its exclusivity.
            if not ev.isAccepted():
                self._on_plot_clicked(hit_plot, additive=additive)
                outcome = "toggled subplot in selection" if additive else "selected subplot"
            else:
                outcome = "curve/legend already handled the click"
        elif not ev.isAccepted() and not additive:
            # Shift+click on empty space does nothing (LibreOffice/MATLAB).
            # Single click landed outside every subplot, and nothing
            # clickable (e.g. a figure/border-anchored annotation) consumed
            # it -- that's genuinely empty space.
            self._deselect_all()
            outcome = "deselected all (empty space)"
        else:
            outcome = "no-op"

        if not additive and ev.button() == QtCore.Qt.LeftButton:
            # Left-click-only: a right-click on an already-selected curve
            # lands at the same spot as the left click that selected it,
            # so treating it as a click-cycling step too would silently
            # advance to the NEXT stacked target (typically the subplot)
            # right after its own context menu already popped up (menus.py
            # raises it earlier in the same dispatch, via ViewBox's own
            # mouseClickEvent -- see raise_context_menu), flipping the
            # selection out from under the just-opened menu. Right-clicks
            # have their own "keep the existing selection" rule already
            # (_curve_menu_targets/_on_plot_context) and must never read or
            # write the click-cycle state.
            self._apply_click_cycle(pos)

        self._log_click_dispatch(ev, additive, hit_plot, pos, outcome)

    # -- click-cycling: repeated clicks at (about) the same spot step
    # through whatever's stacked there (curves, annotations, subplots) --
    def _stacked_click_targets(self, scene_pos):
        """Every subplot/curve/annotation whose clickable area contains
        scene_pos, topmost first, LibreOffice/MATLAB Alt+click style --
        built from the same per-kind hit-tests normal click dispatch
        already uses (_annotation_at-style, _curves_at, a subplot's own
        ViewBox), not Qt's own raw item stack, so every target cycling can
        reach is guaranteed reachable by a normal, non-cycling click too.

        Ordering approximates real render z-order, not a perfect replica
        of Qt's own hit-testing: annotations render above every subplot
        (zValue=800, any anchor -- see annotations.py) so they come first,
        in the app's own annotation z-order (matching _annotation_at);
        then subplots by their own z-order (_plots_by_z()), each
        contributing its own curves (topmost first) then its own body,
        before moving to the next (lower) subplot -- covering the
        "overlapping subplots" case too, not just one grid cell."""
        targets = []
        for a in sorted(self.annotations, key=lambda a: a.zValue(), reverse=True):
            if a.contains(a.mapFromScene(scene_pos)):
                targets.append(('annotation', a, a.parent_plot))
        for p in self._plots_by_z():
            if not p.getViewBox().sceneBoundingRect().contains(scene_pos):
                continue
            for c in self._curves_at(p, scene_pos):
                targets.append(('curve', c, p))
            targets.append(('subplot', p, p))
        return targets

    def _apply_click_target(self, target):
        kind, obj, plot_item = target
        if kind == 'annotation':
            self._select_annotation(obj)
        elif kind == 'curve':
            self._select_curve(obj)
            self._mark_active(plot_item, keep_selection=True)
        elif kind == 'subplot':
            self._on_plot_clicked(plot_item)

    def _apply_click_cycle(self, pos):
        """Called after ordinary click dispatch already ran (whatever it
        selected stands as index 0 of _stacked_click_targets -- both use
        the same per-kind hit-tests/priority, so they agree). If this
        click landed within CLICK_CYCLE_TOLERANCE_PX of the previous
        plain click, within CLICK_CYCLE_TIMEOUT_S of it, select the NEXT
        target in the stack instead, wrapping around. Only ever chooses
        between outcomes ordinary dispatch could itself have produced
        (_apply_click_target reuses the same single-target selection
        setters) -- it doesn't reimplement selection, just which target."""
        if self.interaction_mode != 'select':
            self._click_cycle = None
            return
        targets = self._stacked_click_targets(pos)
        if not targets:
            self._click_cycle = None
            return
        now = time.monotonic()
        prev = self._click_cycle
        same_spot = (
            prev is not None
            and (pos - prev['pos']).manhattanLength() <= CLICK_CYCLE_TOLERANCE_PX
            and now - prev['time'] <= CLICK_CYCLE_TIMEOUT_S
        )
        index = (prev['index'] + 1) % len(targets) if same_spot else 0
        self._click_cycle = {'pos': QtCore.QPointF(pos), 'index': index, 'time': now}
        if same_spot:
            self._apply_click_target(targets[index])

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

    def _select_annotations(self, anns):
        """Exclusively select `anns` (e.g. just-pasted annotations)."""
        self._clear_selection()
        self._mark_active(self.focused_plot, keep_selection=True)
        for a in anns:
            self.selected_annotations.append(a)
            a.set_selected(True)
        self.active_annotation = anns[-1] if anns else None

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
        self._deselect_legend()
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
    @staticmethod
    def _padded_points_at(scatter_item, orig_points_at, pos):
        """ScatterPlotItem.pointsAt (and the _maskAt it delegates to) only
        hit-tests a marker's own drawn radius, with no click tolerance at
        all -- unlike PlotCurveItem, which already gets one via
        setClickable's own `width`. Padding it CLICK_HIT_TOLERANCE_PX
        screen pixels wider (converted to this item's local/data units via
        its own pixelVectors, the same conversion _maskAt itself already
        does for a pxMode symbol) makes a near-miss click still land a
        small/thin marker, not just a dead-center one. `pos` may already be
        a QRectF (e.g. menus.py's own _curves_at, or a caller that wants an
        unpadded region test) -- passed through as-is."""
        if isinstance(pos, QtCore.QRectF):
            return orig_points_at(pos)
        px, py = scatter_item.pixelVectors()
        dx = (px.length() if px is not None else 0) * CLICK_HIT_TOLERANCE_PX
        dy = (py.length() if py is not None else 0) * CLICK_HIT_TOLERANCE_PX
        if dx <= 0 and dy <= 0:
            return orig_points_at(pos)
        rect = QtCore.QRectF(pos.x() - dx, pos.y() - dy, 2 * dx, 2 * dy)
        return orig_points_at(rect)

    def _wire_curve_clickable(self, plot_item, curve):
        """Make a curve's line AND its markers (if any) clickable; clicking
        either selects it (visual highlight) and makes it the target for
        Copy / FFT, instead of those actions always guessing the subplot's
        first curve.

        Before this fix, only curve.curve.sigClicked (the invisible-or-not
        connecting line) was wired -- a scatter's own ScatterPlotItem
        (curve.scatter) already handles and *accepts* a click landing
        exactly on one of its markers (pyqtgraph's own
        ScatterPlotItem.mouseClickEvent), but with nothing connected to
        curve.scatter.sigClicked, that accepted click silently selected
        nothing: a dead-center click on an isolated marker (one the
        invisible connecting line's own mouseShape stroke doesn't happen
        to cover) never reached this handler at all. Both signals carry
        (..., ev) as their last argument, so the same handler works
        unmodified for either."""
        curve.curve.setClickable(True, width=8 + 2 * CLICK_HIT_TOLERANCE_PX)
        orig_points_at = curve.scatter.pointsAt
        curve.scatter.pointsAt = (
            lambda pos, _s=curve.scatter, _orig=orig_points_at: self._padded_points_at(_s, _orig, pos))
        # _padded_points_at alone isn't enough: pyqtgraph's GraphicsScene
        # first narrows candidates to items near the click via its OWN
        # click radius (items(point) plus a small search rect,
        # GraphicsScene._clickRadius, default 2px) using each item's
        # shape()/boundingRect() -- unaffected by the pointsAt override
        # above -- BEFORE ever calling an item's mouseClickEvent at all. A
        # tight, isolated marker's own boundingRect can be smaller than
        # that default radius, so a near-miss click on it never even
        # reaches ScatterPlotItem.mouseClickEvent to test (verified live:
        # pointsAt was never called at all for such a click before this).
        # Widen the whole scene's radius to match -- safe: it only affects
        # which items are OFFERED a click to test, never how any of them
        # decide to handle it.
        scene = plot_item.getViewBox().scene()
        if scene is not None and scene._clickRadius < CLICK_HIT_TOLERANCE_PX:
            scene.setClickRadius(CLICK_HIT_TOLERANCE_PX)

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
        curve.scatter.sigClicked.connect(handler)

    def _highlight_curve_pen(self, curve):
        """Selection highlight. The un-highlighted style is parked in
        opts['_orig_pen'] / opts['_orig_symbol_pen'], present exactly while
        the curve is highlighted (_unhighlight_curve_pen pops them) -- so a
        style edited while unselected is never overwritten by a stale copy
        on the next deselect, and "the curve's real style" is always
        opts.get('_orig_pen', opts['pen']) (curve_style.py relies on it)."""
        orig_pen = curve.opts.get('pen')
        # "No line": none, NoPen, or fully transparent -- the scatter kind's
        # pen (kinds/scatter.py), which must stay non-None for hit-testing.
        no_line = (orig_pen is None or pg.mkPen(orig_pen).style() == QtCore.Qt.NoPen
                   or pg.mkPen(orig_pen).color().alpha() == 0)
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
        # Pop, not get: the parked style must not outlive the highlight
        # (see _highlight_curve_pen).
        orig_pen = curve.opts.pop('_orig_pen', None)
        if orig_pen is not None:
            curve.setPen(orig_pen)
        if '_orig_symbol_pen' in curve.opts:
            curve.setSymbolPen(curve.opts.pop('_orig_symbol_pen'))

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
