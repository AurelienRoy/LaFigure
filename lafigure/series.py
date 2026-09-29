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
"""
import numpy as np
import pyqtgraph as pg

from .datasource import DataSource

# Attribute holding an item's Series. On the item itself, so the Series
# lives and dies with it and needs no bookkeeping on removal.
_SERIES_ATTR = '_lafigure_series'


def _read_only(arr):
    if arr is None:
        return None
    view = np.asarray(arr).view()
    view.flags.writeable = False
    return view


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
        self.kind_obj.set_xy(self.item, x, y)
        self._source, self._rows = source, rows

    def set_data(self, x, y):
        """Replace the data, undoably. A series from an explicit source stays
        linked to it if the length is unchanged (the same rows, new values);
        otherwise it detaches to a private source."""
        x, y = np.array(x, copy=True), np.array(y, copy=True)
        if len(x) != len(y):
            raise ValueError(f"set_data: x has {len(x)} points, y has {len(y)}")
        old = (*self.kind_obj.get_xy(self.item), self._source, self._rows)
        keep = self._rows is not None and len(self._rows) == len(x)
        new = (x, y, self._source if keep else None, self._rows if keep else None)
        self._apply(*new)
        self.figure._push_history(lambda: self._apply(*old), lambda: self._apply(*new))

    def to_dict(self):
        """The kind's to_dict plus 'kind' and the source linkage -- the
        clipboard/undo format. The DataSource is kept by reference: the
        clipboard is process-wide, so a pasted series stays linked."""
        d = self.kind_obj.to_dict(self.item)
        d['kind'] = self.kind
        d['source'] = self._source
        d['rows'] = None if self._rows is None else self._rows.copy()
        d['columns'] = self.columns
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
        return series

    def _add_series_from_dict(self, plot_item, d):
        """Inverse of Series.to_dict (paste, undo of a delete, FFT redo)."""
        return self._add_series(plot_item, d['kind'], d['x'], d['y'], pen=d['pen'], name=d['name'],
                                source=d.get('source'), rows=d.get('rows'),
                                columns=d.get('columns'), **d.get('style', {}))

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
