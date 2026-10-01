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

"""Brushing on every series kind: the rows_in_rect / show_rows protocol and
RectBrush, the per-subplot brush (drag capture + highlight overlays).

**Rows are the currency.** A brush selects *rows*: row indices into the
series' DataSource for a series built from one (`series.rows` maps each
drawn point to its row), or point positions for a series built from plain
arrays (its private source's rows are its positions). Two series sharing a
DataSource are therefore linked by construction: the figure (brushing.py)
keeps one sorted row array per source and shows it on every series of that
source. Nothing else -- no SelectionModel, no id column -- is needed.

The protocol, all module-level functions taking a Series:

- `rows_in_rect(series, rect)`: sorted int array of the rows whose data
  lies in `rect` (a QRectF in data coordinates). Always hit-tests the full
  data from `SeriesKind.get_xy`, never pyqtgraph's downsampled/clipped
  display.
- `show_rows(series, rows, highlight)`: build or update the overlay item
  highlighting `rows` (reusing `highlight`, the previous overlay, when it
  can); None when there is nothing to show.
- `positions_of_rows(series, rows)`: boolean mask over the drawn points,
  for the point actions (Delete/Transform/Stats/Fit); None if the kind
  isn't point-like.

A kind gets them for free if it's an x/y point cloud -- `get_xy` returns
two equal-length 1-D arrays, one per row (line, scatter, stairs, area,
errorbar, ...). A kind may override either one by defining a method of the
same name, `kind.rows_in_rect(item, series, rect)` /
`kind.show_rows(item, series, rows, highlight)`. A histogram-like kind
instead defines `kind.brush_bins(item, series) -> (values, edges[,
heights])`: one value per row and the bin edges (plus the drawn bar
heights, if not raw counts). Its bars then link to rows through a per-row
bin index -- np.digitize, run once per item while Brush is on and cached
by RectBrush (keyed on the identity of `values`/`edges`, so return the same
arrays while the data is unchanged). Brushing a bar selects its rows;
brushed rows show as partial bars, np.bincount of their bins. Anything
else (a kind whose get_xy isn't point-like, e.g. an image) brushes nothing,
without error; a kind without 'brush' in `capabilities` is never asked.

This replaces the earlier SelectionModel/LinkedScatter mechanism (a
bespoke point-id-based shared selection, wired onto two hardcoded demo
scatter subplots): the demo's two scatter subplots are now two ordinary
series of one shared DataSource, linked by construction like any other
pair of series sharing a source. Removed 2026-09-28 (WP-J) once nothing
referenced either class any more.
"""
import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg

from .series import Series, _SERIES_ATTR


# -- the brushing protocol (see the module docstring) ------------------------
_NO_ROWS = np.zeros(0, dtype=np.intp)


def item_series(item):
    """The Series of a plot data item, or None. A PlotDataItem made outside
    _add_series reads as a plain-array line (SeriesMixin._series_of adopts
    it the same way, and keeps the result; this one is read-only)."""
    series = getattr(item, _SERIES_ATTR, None)
    if series is None and isinstance(item, pg.PlotDataItem):
        series = Series(None, item, 'line')
    return series


def is_brushable(series):
    return (series is not None and 'brush' in series.capabilities
            and series.item.isVisible())


def _sorted_rows(rows):
    rows = np.asarray(rows, dtype=np.intp).ravel()
    if rows.size > 1 and not np.all(rows[1:] > rows[:-1]):
        rows = np.unique(rows)
    return rows


def _row_ids(series, n):
    """The rows of a series' n data entries: series.rows for a series of an
    explicit DataSource, positions 0..n-1 for plain arrays; None if the
    two don't line up (the entries aren't one per row)."""
    rows = series.rows
    if rows is None:
        return np.arange(n)
    return rows if len(rows) == n else None


def _point_xy(series):
    """(x, y, rows) if the series is an x/y point cloud, one point per row
    -- the full data from get_xy, not the display -- else None. A 3D
    kind's get_xy is (positions (N, 3), None) -- one row per point same as
    any other point cloud, so it counts too (using only the x/y columns:
    this is for row *membership*, e.g. positions_of_rows below, which
    never reads the actual coordinates back)."""
    x, y = series.kind_obj.get_xy(series.item)
    if x is None:
        return None
    x = np.asarray(x)
    if y is None:
        if x.ndim != 2 or x.shape[1] != 3:
            return None
        rows = _row_ids(series, x.shape[0])
        return None if rows is None else (x[:, 0], x[:, 1], rows)
    y = np.asarray(y)
    if x.ndim != 1 or x.shape != y.shape:
        return None
    rows = _row_ids(series, len(x))
    return None if rows is None else (x, y, rows)


def _binned(series, cache):
    """(bin index per row, rows, edges, raw counts, drawn heights) for a
    kind defining brush_bins, else None. The bin index is np.digitize'd
    once per item and kept in `cache` (RectBrush._bins) while the kind
    keeps returning the same value/edge arrays."""
    hook = getattr(series.kind_obj, 'brush_bins', None)
    if hook is None:
        return None
    got = hook(series.item, series)
    values, edges = got[0], got[1]
    entry = cache.get(series.item) if cache is not None else None
    if entry is None or entry[0] is not values or entry[1] is not edges:
        v, e = np.asarray(values, dtype=float), np.asarray(edges, dtype=float)
        n_bins = len(e) - 1
        index = np.digitize(v, e) - 1
        index[v == e[-1]] = n_bins - 1  # np.histogram's last bin is closed
        index[(index < 0) | (index >= n_bins) | ~np.isfinite(v)] = -1
        entry = (values, edges, index)
        if cache is not None:
            cache[series.item] = entry
    index = entry[2]
    rows = _row_ids(series, len(index))
    if rows is None:
        return None
    edges = np.asarray(edges, dtype=float)
    counts = np.bincount(index[index >= 0], minlength=len(edges) - 1)
    heights = counts if len(got) < 3 or got[2] is None else np.asarray(got[2], dtype=float)
    return index, rows, edges, counts, heights


def rows_in_rect(series, rect, cache=None):
    """Sorted rows of `series` whose data lies in `rect` (QRectF, data
    coordinates). See the module docstring for the kind hooks."""
    own = getattr(series.kind_obj, 'rows_in_rect', None)
    if own is not None:
        return _sorted_rows(own(series.item, series, rect))
    xlo, xhi, ylo, yhi = rect.left(), rect.right(), rect.top(), rect.bottom()
    binned = _binned(series, cache)
    if binned is not None:
        index, rows, edges, _counts, heights = binned
        hit = ((edges[1:] >= xlo) & (edges[:-1] <= xhi)
               & (np.maximum(heights, 0) >= ylo) & (np.minimum(heights, 0) <= yhi))
        return _sorted_rows(rows[np.isin(index, np.nonzero(hit)[0])])
    points = _point_xy(series)
    if points is None:
        return _NO_ROWS
    x, y, rows = points
    try:
        inside = (x >= xlo) & (x <= xhi) & (y >= ylo) & (y <= yhi)
    except TypeError:  # non-numeric data: nothing to hit
        return _NO_ROWS
    return _sorted_rows(rows[inside])


def positions_of_rows(series, rows):
    """Boolean mask over the series' data entries whose row is in `rows`,
    for the point actions; None if the series isn't point-like."""
    if getattr(series.kind_obj, 'brush_bins', None) is not None:
        return None
    points = _point_xy(series)
    if points is None:
        return None
    rows = np.asarray(rows, dtype=np.intp)
    if series.rows is None:
        mask = np.zeros(len(points[2]), dtype=bool)
        mask[rows[(rows >= 0) & (rows < mask.size)]] = True
        return mask
    return np.isin(points[2], rows)


def show_rows(series, rows, highlight=None, cache=None):
    """The overlay highlighting `rows` of `series` -- `highlight` updated in
    place when it's the right type, else a new item -- or None if none of
    those rows is drawn. The caller adds/removes it from the ViewBox."""
    own = getattr(series.kind_obj, 'show_rows', None)
    if own is not None:
        return own(series.item, series, rows, highlight)
    rows = np.asarray(rows, dtype=np.intp)
    if rows.size == 0:
        return None
    binned = _binned(series, cache)
    if binned is not None:
        # Partial bars: the brushed rows' share of each bar, drawn over it.
        index, series_rows, edges, counts, heights = binned
        brushed = index[np.isin(series_rows, rows) & (index >= 0)]
        partial = np.bincount(brushed, minlength=len(counts))
        if not partial.any():
            return None
        scale = np.divide(heights, counts, out=np.zeros(len(counts)), where=counts > 0)
        opts = dict(x0=edges[:-1], width=np.diff(edges), height=partial * scale)
        if isinstance(highlight, pg.BarGraphItem):
            highlight.setOpts(**opts)
            return highlight
        hl = pg.BarGraphItem(pen=pg.mkPen('k', width=1), brush=pg.mkBrush(255, 60, 60, 200), **opts)
        hl.setZValue(10)
        return hl
    mask = positions_of_rows(series, rows)
    if mask is None or not mask.any():
        return None
    x, y = (np.asarray(a) for a in series.kind_obj.get_xy(series.item))
    if isinstance(highlight, pg.ScatterPlotItem):
        highlight.setData(x=x[mask], y=y[mask])
        return highlight
    hl = pg.ScatterPlotItem(x=x[mask], y=y[mask], size=8, pen=pg.mkPen('k', width=1),
                            brush=pg.mkBrush(255, 60, 60, 220))
    hl.setZValue(10)
    return hl


class RectBrush:
    """Rectangular brush-select on one subplot, for every brushable series
    on it, whatever its kind (through the protocol above).

    `LaFigure.add_subplot` makes one per subplot, but it costs nothing until
    Brush is on: the ViewBox drag handler is only wrapped while brushing,
    and the selection, overlays and bin caches only exist once something is
    brushed -- turning Brush off drops all of it again.

    `selection` maps a data item to the sorted rows brushed on it (see the
    module docstring); only non-empty entries are kept.
    """

    def __init__(self, plot_item, on_finished=None):
        self.plot_item = plot_item
        self.view_box = plot_item.getViewBox()
        self.brushing_enabled = False
        self.selection = {}    # data item -> sorted brushed rows
        self._highlights = {}  # data item -> its overlay (ScatterPlotItem, BarGraphItem, ...)
        self._bins = {}        # data item -> bin-index cache, see _binned
        # Called as on_finished(plot_item, matches, additive) when a drag
        # finishes, instead of applying the result locally -- lets
        # LaFigure coordinate brushing as a figure-wide concept (a new,
        # non-additive brush clears every other subplot's selection too; a
        # Shift-held one adds to whatever's already selected everywhere).
        # Falls back to purely local replace/merge if None (e.g. standalone use).
        self.on_finished = on_finished
        self._native_drag = None  # the ViewBox's own handler, while ours wraps it
        self._native_was_own = False
        self._origin = None
        self._rect_item = None

    # -- on/off --------------------------------------------------------------
    def set_brushing(self, enabled):
        # Pan-disabling is LaFigure._apply_mouse_enabled's job, not ours.
        self.brushing_enabled = enabled
        if enabled:
            self._install()
        else:
            self.uninstall()

    def _install(self):
        if self._native_drag is not None:
            return
        self._native_was_own = 'mouseDragEvent' in self.view_box.__dict__
        self._native_drag = self.view_box.mouseDragEvent
        self.view_box.mouseDragEvent = self._wrap_drag(self._native_drag)

    def uninstall(self):
        """Drop the selection, overlays and caches, and give the ViewBox its
        own drag handler back (a no-op if it was never wrapped)."""
        self.clear_selection()
        self._bins = {}
        if self._rect_item is not None:
            self.view_box.removeItem(self._rect_item)
            self._rect_item = self._origin = None
        if self._native_drag is None:
            return
        if self._native_was_own:
            self.view_box.mouseDragEvent = self._native_drag
        else:
            del self.view_box.mouseDragEvent
        self._native_drag = None

    # -- selection -------------------------------------------------------
    def brushable_series(self):
        for item in self.plot_item.listDataItems():
            series = item_series(item)
            if is_brushable(series):
                yield series

    def compute_matches(self, rect):
        """{item: sorted rows} of every brushable series with data in `rect`."""
        matches = {}
        for series in self.brushable_series():
            rows = rows_in_rect(series, rect, self._bins)
            if rows.size:
                matches[series.item] = rows
        return matches

    def _as_rows(self, item, rows):
        """Accepts sorted rows, or a boolean mask over the item's data."""
        rows = np.asarray(rows)
        if rows.dtype == bool:
            series = item_series(item)
            ids = _row_ids(series, len(rows)) if series is not None else None
            return _NO_ROWS if ids is None else _sorted_rows(ids[rows])
        return _sorted_rows(rows)

    def has_selection(self):
        return bool(self.selection)

    def set_selection(self, matches):
        """Replace this subplot's selection wholesale -- a non-additive brush.
        `matches` maps an item to rows (or a boolean mask over its data)."""
        self._show({item: self._as_rows(item, rows) for item, rows in matches.items()})

    def merge_selection(self, matches):
        """OR new matches into the existing selection -- a Shift-held brush."""
        merged = dict(self.selection)
        for item, rows in matches.items():
            rows = self._as_rows(item, rows)
            merged[item] = np.union1d(merged[item], rows) if item in merged else rows
        self._show(merged)

    def clear_selection(self):
        self._show({})

    def redraw(self):
        """Rebuild the overlays after the brushed series' data changed."""
        self._show(dict(self.selection))

    def forget_curve(self, curve):
        """Called when a curve is deleted out from under an active
        selection/highlight (e.g. via the 'Delete Curve' menu), so its
        orphaned highlight overlay doesn't linger on screen."""
        hl = self._highlights.pop(curve, None)
        if hl is not None:
            self.view_box.removeItem(hl)
        self.selection.pop(curve, None)
        self._bins.pop(curve, None)

    def _show(self, selection):
        old, self._highlights = self._highlights, {}
        self.selection = {}
        for item, rows in selection.items():
            if not rows.size:
                continue
            self.selection[item] = rows
            prev = old.pop(item, None)
            series = item_series(item)
            hl = show_rows(series, rows, prev, self._bins) if series is not None else None
            if prev is not None and hl is not prev:
                self.view_box.removeItem(prev)
            if hl is not None:
                if hl is not prev:
                    self.view_box.addItem(hl, ignoreBounds=True)
                self._highlights[item] = hl
        for prev in old.values():
            self.view_box.removeItem(prev)

    # -- the drag ----------------------------------------------------------
    def _wrap_drag(self, native_drag):
        def handler(ev, axis=None):
            if not self.brushing_enabled:
                return native_drag(ev, axis=axis)

            ev.accept()
            pos = self.view_box.mapToView(ev.pos())
            if ev.isStart():
                # Where the button went down, not ev.pos(): pyqtgraph only
                # starts a drag after the first move, already away from it.
                self._origin = self.view_box.mapToView(ev.buttonDownPos())
                self._rect_item = QtWidgets.QGraphicsRectItem()
                self._rect_item.setPen(pg.mkPen('k', style=QtCore.Qt.DashLine))
                self._rect_item.setBrush(pg.mkBrush(120, 120, 255, 40))
                self.view_box.addItem(self._rect_item, ignoreBounds=True)
            if self._origin is None:
                return
            rect = QtCore.QRectF(self._origin, pos).normalized()
            self._rect_item.setRect(rect)

            if ev.isFinish():
                matches = self.compute_matches(rect)
                # Checked at release time, not throughout the drag -- a
                # simplification matching how pyqtgraph's own ViewBox
                # reads modifiers for its Ctrl+drag box-zoom.
                additive = bool(ev.modifiers() & QtCore.Qt.ShiftModifier)
                self.view_box.removeItem(self._rect_item)
                self._rect_item = None
                self._origin = None
                if self.on_finished is not None:
                    self.on_finished(self.plot_item, matches, additive)
                elif additive:
                    self.merge_selection(matches)
                else:
                    self.set_selection(matches)
        return handler


