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

"""`LaColorBar`, an interactive colorbar that fixes the two user
complaints pyqtgraph's own `pg.ColorBarItem` has:

1. There was no visual indication of where the actual plotted data's
   min/max sit relative to the current levels.
2. Dragging one level handle rescaled the WHOLE bar from the *previous*
   level pair (`ColorBarItem._regionChanging`'s quadratic-sensitivity
   arithmetic on a `LinearRegionItem` reset to (63, 191) after every
   change) -- so one drag perturbed both levels, never just the one
   being dragged.

**The model (confirmed with the user, PLAN.md's Round 4 "Colorbar
model")**: the bar's own axis spans a *display range* `(dlo, dhi)` = the
union of the plotted data's min/max and both current levels, padded a few
percent (`DISPLAY_PAD_FRACTION`). Two independently movable `InfiniteLine`
limit handles sit at their own level values inside that display range;
dragging one changes ONLY that level -- the other's value is passed
through unchanged (same float, not merely equal by value) -- growing the
display range (and hence moving line pixel positions, the untouched
value's included) only if the new value falls outside it. Two more
`InfiniteLine`s, non-interactive and dashed, mark the plotted data's own
min/max, refreshed live. The gradient pixmap is redrawn so the colormap
spans only the LEVEL sub-range and clamps to the colormap's own end colors
outside it -- exactly what the attached item actually shows for
out-of-level values, so the bar reads honestly next to the plot.

**Why subclass `pg.ColorBarItem` instead of building from scratch**: its
gradient pixmap item (`self.bar`), frame axes and `PlotItem` scaffolding
(a ViewBox pinned to 0..256 or 0..1x0..256 depending on orientation, its
main axis `unlinkFromView()`d and ranged manually) are unrelated to the
two complaints above and worth keeping. `self.region` (the inherited
`LinearRegionItem`) is never built in the first place -- passing
`interactive=False` through to `pg.ColorBarItem.__init__` is enough;
nothing here fights it or monkeypatches it away (see CLAUDE.md's own note
on state parked "while X is on" -- the cleanest way to not have a feature
enabled is to never turn it on).

**Serving more than an image** (`attach(item, values_fn, plot_item,
source=None)`): the user explicitly asked for this to work for "scatter,
image, ..." -- so nothing here assumes `item` is a `pg.ImageItem`.
`values_fn()` is called on demand (never cached across calls) and must
return the current 1-D or 2-D array whose min/max should drive the two
dashed lines; that is the ONLY thing this module needs from `item` to
track live data changes for the dashed lines. Live refresh is wired at
three levels:
  1. `item.sigImageChanged`, if the item has one (an `ImageItem`'s own
     data-changed signal).
  2. `source.on_change(...)`, if an explicit `DataSource` is passed --
     for a colored scatter whose color column can change independently
     of the item's own signals (e.g. `src.filter(...)`, a reactive
     `table`/control edit).
  3. A figure-wide, best-effort resync: `HistoryMixin._resync_colorbars`
     (history.py), called from `_push_history`/`undo`/`redo` right next
     to the existing `_resync_cursor_points()` call, following that
     method's own "best effort, never raise" stance exactly.

**Frozen interface for R4-SCAT (and any future kind package) to code
against, verbatim, per this package's own brief:**

    bar = LaColorBar(colorMap=..., label=...)          # a pg.ColorBarItem
    bar.setImageItem(image_item, insert_in=plot_item)  # inherited, unchanged;
                                                        # only for an ImageItem
    bar.attach(item, values_fn, plot_item, source=None)
    bar.set_levels(lo, hi)      # -> also used internally by undo/redo
    bar.levels()                # inherited: -> (lo, hi)
    bar.data_range()            # -> (data_min, data_max) or (None, None)
    bar.sigLevelsChanged        # inherited pg.ColorBarItem Qt signal,
    bar.sigLevelsChangeFinished # emitted (self) on every live/completed
                                 # change -- connect to recolor points

`attach()`'s 3rd positional argument, `plot_item`, is REQUIRED (not
optional): it is how a completed drag finds "its" `LaFigure` to push one
undo entry through (`_push_history`) -- resolved once, at `attach()` time,
by scanning `registry.get_registry().figures` for one whose `.plots`
contains `plot_item` (there is no item->figure backref anywhere else in
the codebase to reuse). If no open figure's `.plots` contains it (e.g. a
bar built directly in a standalone script/test), dragging still updates
levels live -- it just isn't undoable, logged once at DEBUG.
"""
import logging

import numpy as np
import pyqtgraph as pg
from pyqtgraph import functions as fn
from pyqtgraph.Qt import QtCore, QtGui

logger = logging.getLogger('lafigure.colorbar')


def _figure_for_plot_item(plot_item):
    """The open LaFigure whose `.plots` contains `plot_item`, or None.
    Local, on-demand lookup (never cached: a figure can close and another
    plot_item -> figure mapping exists nowhere else in the codebase) --
    imported inline to avoid giving colorbar.py a load-time dependency on
    registry.py's own import graph."""
    from .registry import get_registry
    for fig in get_registry().figures:
        if plot_item in fig.plots:
            return fig
    return None


class LaColorBar(pg.ColorBarItem):
    """See module docstring. A `pg.ColorBarItem` (still a real `PlotItem`,
    still usable with `setImageItem(item, insert_in=plot_item)`) whose
    interactive region is replaced by two independent limit lines plus two
    fixed data-extent lines, and whose gradient reflects only the level
    sub-range of a wider display range."""

    # The same fixed 0..256 (or 0..1 x 0..256, depending on orientation)
    # view-coordinate span pg.ColorBarItem's own inherited machinery uses
    # for its axis/gradient pixmap -- kept identical so `setColumnFixedWidth`/
    # `setRowFixedHeight` and the inherited axis/frame code need no change.
    BAR_SPAN = 256
    # How far the display range pads beyond the data-min/max-and-levels
    # union, as a fraction of that union's span (or of the single value's
    # own magnitude, floored to 1.0, if the union is degenerate/zero-width).
    DISPLAY_PAD_FRACTION = 0.05

    def __init__(self, values=None, width=25, colorMap=None, label=None,
                 limits=None, rounding=1, orientation='vertical',
                 pen='w', hoverPen='r', **kwargs):
        # Set before super().__init__(): pg.ColorBarItem.__init__ itself
        # may call our OVERRIDDEN _update_items (via setColorMap, if colorMap
        # is not None) before any of our own state below exists -- _ready
        # guards exactly that window. Plain attribute assignment on self is
        # safe before QObject.__init__ runs; only Qt machinery (signals,
        # items) would not be.
        self._ready = False
        self._data_min = None
        self._data_max = None
        self._display_range = (0.0, 1.0)
        self._attached_item = None
        self._attached_source = None
        self._values_fn = None
        self._plot_item = None
        self._figure = None
        self._pending_start_levels = None
        super().__init__(values=values, width=width, colorMap=colorMap, label=label,
                          interactive=False, limits=limits, rounding=rounding,
                          orientation=orientation, pen=pen, hoverPen=hoverPen, **kwargs)

        angle = 90 if self.horizontal else 0
        dash_pen = pg.mkPen('w', style=QtCore.Qt.DashLine)
        self._fixed_min_line = pg.InfiniteLine(angle=angle, movable=False, pen=dash_pen)
        self._fixed_max_line = pg.InfiniteLine(angle=angle, movable=False, pen=dash_pen)
        for line in (self._fixed_min_line, self._fixed_max_line):
            # Never grabbable/hit-testable -- "fixed, non-draggable" per the
            # roadmap item, not merely "movable=False" (which alone still
            # lets a click land on it and, for some pyqtgraph items, start
            # a context menu or hover state).
            line.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            line.setZValue(500)
            self.addItem(line)

        self._lo_line = pg.InfiniteLine(angle=angle, movable=True, pen=pen, hoverPen=hoverPen)
        self._hi_line = pg.InfiniteLine(angle=angle, movable=True, pen=pen, hoverPen=hoverPen)
        for line in (self._lo_line, self._hi_line):
            line.setZValue(1000)
            self.addItem(line)
        self._lo_line.sigPositionChanged.connect(lambda: self._on_line_moved(self._lo_line, True))
        self._hi_line.sigPositionChanged.connect(lambda: self._on_line_moved(self._hi_line, False))
        self._lo_line.sigPositionChangeFinished.connect(lambda: self._on_line_finished(True))
        self._hi_line.sigPositionChangeFinished.connect(lambda: self._on_line_finished(False))

        self._ready = True
        self._update_items()

    # -- attaching to a plotted item ------------------------------------
    def attach(self, item, values_fn, plot_item, source=None):
        """Wire this bar to `item` (an ImageItem, a ScatterPlotItem, or
        anything else whose value range the two dashed lines should
        track) living on `plot_item` -- see the module docstring for the
        exact, frozen signature and how live refresh is wired. Safe to
        call again (on the same or a different item): cleanly detaches
        the previous item's/source's subscriptions first."""
        if self._attached_item is not None and hasattr(self._attached_item, 'sigImageChanged'):
            try:
                self._attached_item.sigImageChanged.disconnect(self.refresh_limits)
            except (TypeError, RuntimeError):
                pass  # already disconnected, or the C++ object is gone
        if self._attached_source is not None:
            try:
                self._attached_source.off_change(self.refresh_limits)
            except ValueError:
                pass  # wasn't actually subscribed

        self._attached_item = item
        self._attached_source = source
        self._values_fn = values_fn
        self._plot_item = plot_item
        self._figure = _figure_for_plot_item(plot_item)
        # The marker HistoryMixin._resync_colorbars (history.py) looks for
        # on every item in every ViewBox -- set here so any kind that calls
        # attach() gets the figure-wide best-effort resync for free, even
        # if (like kinds/imshow.py) it also sets this itself right after.
        item._lafigure_colorbar = self
        if self._figure is None:
            logger.debug("attach: plot_item not found in any open figure's .plots -- "
                         "drag will update levels live but push no undo entry")
        if hasattr(item, 'sigImageChanged'):
            item.sigImageChanged.connect(self.refresh_limits)
        if source is not None:
            source.on_change(self.refresh_limits)
        self.refresh_limits()

    def refresh_limits(self):
        """Recompute the two fixed dashed lines (and, since the display
        range may need to grow/shrink around them, the axis range and
        gradient) from `values_fn()`'s CURRENT array. Best-effort: never
        raises -- an exception from a caller's values_fn, a None return,
        or a momentarily empty/all-NaN array just leaves the bar showing
        whatever it last showed, mirroring HistoryMixin.
        _resync_cursor_points's stance (history.py) exactly, since this is
        what that method calls on every colorbar it finds."""
        if self._values_fn is None:
            return
        try:
            arr = self._values_fn()
            if arr is None:
                return
            arr = np.asarray(arr, dtype=float).ravel()
            arr = arr[np.isfinite(arr)]
            if arr.size == 0:
                return
            data_min, data_max = float(arr.min()), float(arr.max())
        except Exception:
            logger.debug("refresh_limits: values_fn() failed, leaving the bar unchanged",
                         exc_info=True)
            return
        self._data_min, self._data_max = data_min, data_max
        self._update_items()

    def data_range(self):
        """(data_min, data_max) from the last successful values_fn() call
        -- (None, None) before attach()/refresh_limits() ever succeeded."""
        return (self._data_min, self._data_max)

    # -- levels -----------------------------------------------------------
    def set_levels(self, lo, hi):
        """Set BOTH levels directly and refresh everything. What undo/redo
        closures call; the drag handlers below call it too, always with
        only one side actually changed from self.values -- so the
        untouched side is always the exact same float the caller already
        had, never merely equal by value."""
        self.values = (lo, hi)
        self._update_items()
        self.sigLevelsChanged.emit(self)

    # -- the two movable limit lines ---------------------------------------
    def _on_line_moved(self, line, is_low):
        """Live, on every mouse-move of a drag (InfiniteLine.setPos emits
        sigPositionChanged synchronously from within itself -- see
        mouseDragEvent). Changes ONLY the dragged line's own value; the
        other side of self.values is passed straight through unchanged."""
        if self._pending_start_levels is None:
            self._pending_start_levels = self.values
        lo, hi = self.values
        raw_value = self._pos_to_value(line.value())
        if is_low:
            lo = min(raw_value, hi)  # never cross the other limit
        else:
            hi = max(raw_value, lo)
        self.set_levels(lo, hi)

    def _on_line_finished(self, is_low):
        """On release (InfiniteLine emits sigPositionChangeFinished once,
        after the drag's last setPos/sigPositionChanged already ran) --
        pushes exactly one undo entry for the whole gesture, if anything
        actually changed and an owning figure was found at attach() time."""
        start, self._pending_start_levels = self._pending_start_levels, None
        end = self.values
        if start is not None and start != end and self._figure is not None:
            old, new = start, end
            self._figure._push_history(lambda: self.set_levels(*old),
                                       lambda: self.set_levels(*new))
        self.sigLevelsChangeFinished.emit(self)

    def _pos_to_value(self, pos):
        dlo, dhi = self._display_range
        if dhi == dlo:
            return dlo
        return dlo + (pos / self.BAR_SPAN) * (dhi - dlo)

    def _value_to_pos(self, value):
        dlo, dhi = self._display_range
        if dhi == dlo:
            return self.BAR_SPAN / 2.0
        return ((value - dlo) / (dhi - dlo)) * self.BAR_SPAN

    def _reposition_lines(self):
        lo, hi = self.values
        for line, value in ((self._lo_line, lo), (self._hi_line, hi),
                             (self._fixed_min_line, self._data_min),
                             (self._fixed_max_line, self._data_max)):
            if value is None:
                line.setVisible(False)
                continue
            line.setVisible(True)
            line.blockSignals(True)  # never feed our own reposition back as a drag
            try:
                line.setPos(self._value_to_pos(value))
            finally:
                line.blockSignals(False)

    def _recompute_display_range(self):
        lo, hi = self.values
        candidates = [float(lo), float(hi)]
        if self._data_min is not None:
            candidates.append(self._data_min)
        if self._data_max is not None:
            candidates.append(self._data_max)
        dlo, dhi = min(candidates), max(candidates)
        span = dhi - dlo
        pad = span * self.DISPLAY_PAD_FRACTION if span > 0 else max(abs(dlo), 1.0) * self.DISPLAY_PAD_FRACTION
        self._display_range = (dlo - pad, dhi + pad)
        return self._display_range

    # -- gradient + inherited hook -------------------------------------
    def _update_items(self, update_cmap=False):
        """Overrides pg.ColorBarItem's own: ranges the axis to the DISPLAY
        range (not the levels), repositions all four lines, and always
        rebuilds the gradient pixmap (not only when update_cmap=True --
        the gradient now depends on levels/display range too, not just
        colormap identity, so any change that reaches this method must
        rebuild it)."""
        if not self._ready:
            # Reached from pg.ColorBarItem.__init__ itself (setColorMap /
            # setImageItem), before our own lines/display-range state
            # exists yet -- let super's own plain axis-range-to-levels
            # through; __init__ calls _update_items() again once ready.
            self.axis.setRange(self.values[0], self.values[1])
            return
        self._recompute_display_range()
        dlo, dhi = self._display_range
        self.axis.setRange(dlo, dhi)
        self._reposition_lines()
        if self._colorMap is not None:
            self._rebuild_gradient()
        for img_weakref in self.img_list:
            img = img_weakref()
            if img is None:
                continue
            img.setLevels(self.values)
            if self._colorMap is not None:
                img.setColorMap(self._colorMap)

    def _rebuild_gradient(self):
        """The bar's own pixmap: BAR_SPAN samples across the DISPLAY range,
        each colored by where its VALUE falls in the LEVEL sub-range
        (clamped to [0, 1] -- i.e. clamped to the colormap's own end
        colors outside the levels), so the bar visually matches what the
        attached item actually shows for an out-of-level value instead of
        implying (as the inherited full-span gradient would) that the
        whole displayed range is meaningfully colored."""
        dlo, dhi = self._display_range
        lo, hi = self.values
        n = self.BAR_SPAN
        # Same index-0-is-the-low-end ordering pg's own getLookupTable(nPts=256)
        # used (index 0 -> the colormap's low end) -- only what "low end" MEANS
        # changed (now the display range's low end, not the level's).
        sample_values = dlo + ((np.arange(n) + 0.5) / n) * (dhi - dlo)
        if hi > lo:
            frac_color = np.clip((sample_values - lo) / (hi - lo), 0.0, 1.0)
        else:
            frac_color = np.where(sample_values <= lo, 0.0, 1.0)
        lut = self._colorMap.map(frac_color, mode=pg.ColorMap.BYTE)
        lut = np.expand_dims(lut, axis=0 if self.horizontal else 1)
        qimg = fn.ndarray_to_qimage(lut, QtGui.QImage.Format.Format_RGBA8888)
        self.bar.setPixmap(QtGui.QPixmap.fromImage(qimg))
