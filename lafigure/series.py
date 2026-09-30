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

"""Series kinds and the Series wrapper -- what replaced the old
`(x, y, pen, name)` curve tuples.

- A **SeriesKind** knows how to build one kind of plotted data (`create`),
  serialize it (`to_dict`, the clipboard/undo format), and which actions
  apply to it (`capabilities`). Kinds live in `SERIES_KINDS`, filled by
  `register_series_kind`; only 'line' exists so far (later packages add
  their own kinds the same way).
- A **Series** is a thin wrapper around the real pyqtgraph item a kind
  created. The item itself stays a genuine `pg.PlotDataItem` living in
  `plot_item.listDataItems()`, so selection, menus and brushing keep
  working on it directly; the Series only adds kind, source and rows. It is
  reachable from its item (`figure._series_of(item)`), never kept in a
  separate list that could go stale.
- `SeriesMixin._add_series` is the only series construction site, guarded
  by test_add_series_is_the_only_series_construction_site.

Source linkage: a series built from plain arrays gets a private
DataSource ('x'/'y' columns) lazily, on first access to `.source` -- free
until someone asks. A series built from an explicit DataSource keeps that
object and the row indices it shows (`rows`), so several series from one
source are linked by construction; brushing across them is a later
package's job.

Display transform (WP-P7, transform.py): a Series carries `transform`
(dx, dy, sx, sy) and its item draws raw * scale + offset. The item's data
-- hence `x`/`y`, get_xy, and everything reading them (brush hit-test,
Stats, Fit, CSV/HTML export, data cursors) -- is the TRANSFORMED data;
every write through get_xy/set_xy/_apply stays in that drawn space, so
brushing's snapshots and row views need no change. The raw data is what
the DataSource / caller's arrays hold, never written: `raw_xy()` recovers
it exactly (a cached copy while the drawn data is still what the
transform produced, else by inverting the transform). Code that re-derives
drawn data from raw source columns must pass it through `transform_xy`.
"""
import numpy as np
import pyqtgraph as pg

from .datasource import DataSource
from .transform import IDENTITY, Transform, TransformDialog, transform_applies

# Attribute holding an item's Series. On the item itself, so the Series
# lives and dies with it and needs no bookkeeping on removal.
_SERIES_ATTR = '_lafigure_series'


def _read_only(arr):
    if arr is None:
        return None
    view = np.asarray(arr).view()
    view.flags.writeable = False
    return view


def _same_data(a, b):
    if a is b:
        return True
    if a is None or b is None:
        return False
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and np.array_equal(a, b)


class SeriesKind:
    """One kind of plotted data. Subclasses set `name`/`capabilities` and
    implement `create`/`to_dict`; register an instance with
    register_series_kind."""
    name = None
    # Which actions apply: e.g. 'brush', 'fft', 'remove_average', 'fit', 'copy'.
    capabilities = frozenset()

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None, **style):
        """Build the pyqtgraph item on plot_item and return it. source/rows
        are the Series' business; a kind may ignore them. x/y's meaning is
        the kind's own to define (e.g. a histogram kind treats x as the raw
        samples to bin, y as unused) -- Axes._plot_kind only routes them."""
        raise NotImplementedError

    def to_dict(self, item):
        """Everything create() needs to rebuild `item`: 'x', 'y', 'pen',
        'name', 'style' (keyword arguments for create). Arrays are copies."""
        raise NotImplementedError

    def get_xy(self, item):
        """The item's current (x, y) data, for Series.x/.y -- override for
        an item that isn't a plain pg.PlotDataItem (e.g. ScatterPlotItem,
        ImageItem): return whatever numpy arrays best represent it."""
        return item.xData, item.yData

    def set_xy(self, item, x, y):
        """Apply new (x, y) data to the item, for Series.set_data -- override
        alongside get_xy for a non-PlotDataItem item."""
        item.setData(x, y)


class LineKind(SeriesKind):
    """A plain line curve -- what every curve in the app was before kinds
    existed, FFT results included."""
    name = 'line'
    capabilities = frozenset({'brush', 'fft', 'remove_average', 'fit', 'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               clip_to_view=False, downsample=None, symbol=None, symbol_size=None,
               symbol_brush=None, symbol_pen=None):
        """clip_to_view/downsample ('peak', 'mean', 'subsample' or None) are
        the millions-of-points settings; clip_to_view assumes x increases.
        symbol*: an optional marker (curve_style.set_curve_marker)."""
        kwargs = {'name': name}
        if pen is not None:
            kwargs['pen'] = pen
        if symbol is not None:
            kwargs.update(symbol=symbol, symbolBrush=symbol_brush, symbolPen=symbol_pen)
            if symbol_size is not None:
                kwargs['symbolSize'] = symbol_size
        item = plot_item.plot(x, y, **kwargs)
        if clip_to_view:
            item.setClipToView(True)
        if downsample:
            item.setDownsampling(auto=True, method=downsample)
        return item

    def to_dict(self, item):
        style = {
            'clip_to_view': bool(item.opts.get('clipToView')),
            'downsample': item.opts.get('downsampleMethod') if item.opts.get('autoDownsample') else None,
        }
        if item.opts.get('symbol') is not None:
            # Only a line that has a marker records one, so a plain line's
            # dict keeps exactly its old shape.
            style.update(
                symbol=item.opts['symbol'], symbol_size=item.opts.get('symbolSize'),
                symbol_brush=item.opts.get('symbolBrush'),
                symbol_pen=item.opts.get('_orig_symbol_pen', item.opts.get('symbolPen')),
            )
        return {
            'x': np.array(item.xData, copy=True),
            'y': np.array(item.yData, copy=True),
            # The pen before any selection highlight (selection_ui keeps it there).
            'pen': item.opts.get('_orig_pen', item.opts.get('pen')),
            'name': item.name(),
            'style': style,
        }


SERIES_KINDS = {}


def register_series_kind(kind):
    """Make `kind` available to _add_series by its name (replaces a kind
    already registered under that name)."""
    if not kind.name:
        raise ValueError(f"series kind {kind!r} has no name")
    SERIES_KINDS[kind.name] = kind
    return kind


register_series_kind(LineKind())


class Series:
    """The facade over one plotted item. See the module docstring."""

    def __init__(self, figure, item, kind, source=None, rows=None, columns=None):
        self.figure = figure
        self.item = item
        self.kind = kind
        self._source = source
        self._rows = None if rows is None else np.asarray(rows, dtype=np.intp)
        self.columns = columns  # (x column, y column) in an explicit source
        self._private = None    # (x array, y array, DataSource), rebuilt when the data changes
        self._transform = IDENTITY
        # (drawn x, drawn y, raw x, raw y) as last written through the
        # transform: raw_xy's exact answer while the drawn data is unchanged.
        self._raw_cache = None
        self._transform_dialog = None   # its open TransformDialog, if any

    def __repr__(self):
        return f"<Series {self.kind} {self.name!r}>"

    @property
    def kind_obj(self):
        return SERIES_KINDS[self.kind]

    @property
    def capabilities(self):
        return self.kind_obj.capabilities

    @property
    def name(self):
        """The item's name, or None for a kind whose item has no .name()
        (e.g. imshow's pg.ImageItem) -- found by WP-I3."""
        get_name = getattr(self.item, 'name', None)
        return get_name() if get_name is not None else None

    @property
    def x(self):
        """The item's current x data, read-only (a view, not a copy). Goes
        through the kind's get_xy, so this works for non-PlotDataItem kinds
        too (see SeriesKind.get_xy)."""
        return _read_only(self.kind_obj.get_xy(self.item)[0])

    @property
    def y(self):
        return _read_only(self.kind_obj.get_xy(self.item)[1])

    @property
    def rows(self):
        """Row indices into `source` for an explicit source; None for a
        series built from plain arrays (its private source is all rows)."""
        return _read_only(self._rows)

    @property
    def source(self):
        """The explicit DataSource, or a private one built from the current
        data the first time it's asked for (and again after the data changes)."""
        if self._source is not None:
            return self._source
        x, y = self.kind_obj.get_xy(self.item)
        if self._private is None or self._private[0] is not x or self._private[1] is not y:
            empty = np.zeros(0)
            if y is None and np.ndim(x) == 2 and np.shape(x)[1] == 3:
                # A 3D kind's get_xy: (positions (N, 3), None) -- kinds/scatter3d.py etc.
                src = DataSource({'x': x[:, 0], 'y': x[:, 1], 'z': x[:, 2]})
            else:
                src = DataSource({'x': empty if x is None else x, 'y': empty if y is None else y})
            self._private = (x, y, src)
        return self._private[2]

    def _apply(self, x, y, source, rows):
        """x/y are DRAWN data (already transformed) -- brushing's
        snapshots and row views write through here."""
        self.kind_obj.set_xy(self.item, x, y)
        self._source, self._rows = source, rows

    # -- display transform (transform.py) ----------------------------------
    @property
    def transform(self):
        """The display Transform (dx, dy, sx, sy); IDENTITY by default."""
        return self._transform

    def transform_xy(self, x, y):
        """Raw arrays -> what this series draws for them."""
        return self._transform.apply(x, y)

    def raw_xy(self):
        """The untransformed data of what's drawn (never a copy the caller
        may write into -- treat as read-only)."""
        x, y = self.kind_obj.get_xy(self.item)
        t = self._transform
        if t.is_identity:
            return x, y
        cache = self._raw_cache
        if cache is not None and _same_data(cache[0], x) and _same_data(cache[1], y):
            return cache[2], cache[3]
        # Redrawn since (a brushing delete, hide/show...): the drawn data is
        # still transform(raw), so invert it.
        return t.invert(x, y)

    def _write_raw(self, x, y):
        """Draw raw arrays through the transform."""
        self.kind_obj.set_xy(self.item, *self._transform.apply(x, y))
        if self._transform.is_identity:
            self._raw_cache = None
        else:
            self._raw_cache = (*self.kind_obj.get_xy(self.item), x, y)

    def _set_transform(self, t):
        """Change the transform and redraw -- view only, no undo entry
        (SeriesMixin.set_series_transform is the undoable path). Entries a
        brushing row view keeps undrawn (hidden rows) are re-mapped too, so
        they come back through the new transform when shown."""
        if not isinstance(t, Transform):
            t = Transform(*t)
        old = self._transform
        if t == old:
            return
        raw_x, raw_y = self.raw_xy()
        synced = getattr(self.figure, '_synced_row_view', None)
        view = synced(self) if synced is not None else None
        self._transform = t
        self._write_raw(raw_x, raw_y)
        if view is not None:
            from .brushing import ROW_VIEW_ATTR
            vx, vy = t.apply(*old.invert(view.x, view.y))
            drawn_x, drawn_y = self.kind_obj.get_xy(self.item)
            vx, vy = np.array(vx, dtype=float), np.array(vy, dtype=float)
            vx[view.shown], vy[view.shown] = drawn_x, drawn_y   # the drawn ones exactly
            setattr(self.item, ROW_VIEW_ATTR, view.replace(x=vx, y=vy))

    def _apply_raw(self, x, y, source, rows):
        self._write_raw(x, y)
        self._source, self._rows = source, rows

    def set_data(self, x, y):
        """Replace the (raw) data, undoably; it's drawn through the current
        transform. A series from an explicit source stays linked to it if
        the length is unchanged (the same rows, new values); otherwise it
        detaches to a private source."""
        x, y = np.array(x, copy=True), np.array(y, copy=True)
        if len(x) != len(y):
            raise ValueError(f"set_data: x has {len(x)} points, y has {len(y)}")
        old = (*self.raw_xy(), self._source, self._rows)
        keep = self._rows is not None and len(self._rows) == len(x)
        new = (x, y, self._source if keep else None, self._rows if keep else None)
        self._apply_raw(*new)
        self.figure._push_history(lambda: self._apply_raw(*old), lambda: self._apply_raw(*new))

    def to_dict(self):
        """The kind's to_dict plus 'kind' and the source linkage -- the
        clipboard/undo format. The DataSource is kept by reference: the
        clipboard is process-wide, so a pasted series stays linked.
        'x'/'y' stay the drawn data; 'transform' is (dx, dy, sx, sy), and
        a transformed series also records 'raw' so a paste's Reset is exact."""
        d = self.kind_obj.to_dict(self.item)
        d['kind'] = self.kind
        d['source'] = self._source
        d['rows'] = None if self._rows is None else self._rows.copy()
        d['columns'] = self.columns
        d['transform'] = tuple(self._transform)
        if not self._transform.is_identity:
            d['raw'] = tuple(None if a is None else np.array(a, copy=True) for a in self.raw_xy())
        return d


class SeriesMixin:
    # -- the one series construction site ------------------------------
    def _add_series(self, plot_item, kind_name, x, y, pen=None, name=None,
                    source=None, rows=None, columns=None, **style):
        """Build a series of kind `kind_name` on plot_item, make it
        clickable (if its item supports the same protocol as a plain
        PlotDataItem's -- see the note below), and return its Series. With
        an explicit `source`, `rows` (default: every row) says which of its
        rows x/y show, and `columns` which (x, y) columns they came from."""
        kind = SERIES_KINDS[kind_name]
        if source is not None and rows is None:
            rows = np.arange(len(source))
        item = kind.create(plot_item, x, y, pen=pen, name=name, source=source, rows=rows, **style)
        series = Series(self, item, kind_name, source=source, rows=rows, columns=columns)
        setattr(item, _SERIES_ATTR, series)
        # _wire_curve_clickable (selection_ui.py) assumes item.curve, which
        # only a real pg.PlotDataItem has -- a kind whose item is genuinely
        # different (e.g. BarGraphItem, ImageItem) isn't click-selectable
        # yet; that's WP-J's job (generalizing selection/brushing across
        # kinds), not this construction site's. Guard rather than crash.
        if hasattr(item, 'curve'):
            self._wire_curve_clickable(plot_item, item)
        # The Curve Browser and the Figure Browser's "Show Curves" tree
        # both rebuild from this signal (manager.py's _on_subplots_changed)
        # -- without it, neither noticed a curve added to an existing
        # subplot, only whole-subplot add/remove.
        self.registry.notify_subplots_changed(self)
        return series

    def _add_series_from_dict(self, plot_item, d):
        """Inverse of Series.to_dict (paste, undo of a delete, FFT redo).
        d['x']/d['y'] are drawn data, so the item is built from them as-is
        and the transform is only recorded, never applied a second time."""
        series = self._add_series(plot_item, d['kind'], d['x'], d['y'], pen=d['pen'], name=d['name'],
                                  source=d.get('source'), rows=d.get('rows'),
                                  columns=d.get('columns'), **d.get('style', {}))
        t = Transform(*d.get('transform', IDENTITY))
        if not t.is_identity:
            series._transform = t
            raw = d.get('raw')
            if raw is not None:
                drawn = series.kind_obj.get_xy(series.item)
                if all(_same_data(a, b) for a, b in zip(t.apply(*raw), drawn)):
                    series._raw_cache = (*drawn, *raw)
        return series

    # -- display transform (transform.py) -----------------------------------
    def _apply_series_transform(self, series, t):
        """Redraw `series` through transform `t` -- view only, what the
        Transform popup does live on every edit. Brush highlights and data
        cursors pinned to its points follow."""
        series._set_transform(t)
        self._redraw_brush()
        self._resync_cursor_points()

    def set_series_transform(self, series, t, before=None):
        """Set `series`' display transform, as one undo entry going back to
        `before` (default: its current transform) -- the popup passes the
        values it opened with, so a whole live-edit session is one entry."""
        t = t if isinstance(t, Transform) else Transform(*t)
        before = series.transform if before is None else before
        self._apply_series_transform(series, t)
        if before == t:
            return
        self._push_history(lambda: self._apply_series_transform(series, before),
                           lambda: self._apply_series_transform(series, t))

    def open_transform_dialog(self, curve):
        """The curve menu's Transform...: the series' modeless popup (the
        already-open one, raised, if there is one). None for a kind a
        transform doesn't apply to (transform.TRANSFORM_KINDS)."""
        series = self._series_of(curve)
        if series is None or not transform_applies(series.kind):
            return None
        dlg = series._transform_dialog
        if dlg is None:
            dlg = TransformDialog(self, series, parent=self)
            series._transform_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    # -- item <-> Series ---------------------------------------------------
    def _series_of(self, item):
        """The Series wrapping `item`. A PlotDataItem made outside
        _add_series (none should be) is adopted as a 'line' on first ask."""
        series = getattr(item, _SERIES_ATTR, None)
        if series is None and isinstance(item, pg.PlotDataItem):
            series = Series(self, item, 'line')
            setattr(item, _SERIES_ATTR, series)
        return series

    def _series_on(self, plot_item):
        """Every Series on plot_item, in drawing order, derived live from
        its data items."""
        found = (self._series_of(item) for item in plot_item.listDataItems())
        return [s for s in found if s is not None]
