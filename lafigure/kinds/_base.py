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

"""Round 4's shared kind base (PLAN.md "R4-BASE") -- what every new plot
kind in `lafigure/kinds/` builds on, per the round's explicit requirement
to "re-use in the background the same base function, base plots" rather
than hand-roll a fresh pyqtgraph item per kind.

This is a **private support module, not a SeriesKind itself** -- nothing
here calls `register_series_kind`, so it is deliberately NOT imported by
`kinds/__init__.py` (which exists purely to make every *registered* kind
reachable as `ax.<name>(...)` on a plain `import lafigure` -- see its own
docstring). A kind package imports straight from here
(`from ._base import CompositeSeriesItem, categories, ...`) the same way
it already imports from `..series`.

Two families of helpers:

- **`CompositeSeriesItem`** / **`DerivedKind`**: the two ways a new kind
  avoids building its own from-scratch pyqtgraph item. `DerivedKind`
  wraps an *existing* registered kind (loglog on 'line', barh on 'bar',
  heatmap on 'imshow', spy on 'scatter', plot3 on 'line3d', ...) --
  nothing new is drawn, only the arguments/setup differ. `CompositeSeriesItem`
  is for a kind whose visual genuinely isn't a single existing item's shape
  (a box-and-whisker, a violin outline, a quiver field, a contour's
  polylines, pie wedges...) -- it still participates in `listDataItems()`
  like a real series, it just draws several primitives together.
- **Plain-numpy helpers** (`categories`, `apply_category_ticks`/
  `clear_category_ticks`, `jitter`, `value_colors`, `size_scale`, `bin2d`,
  `quantiles`, `kde`): the small, kind-agnostic numeric building blocks
  several of round 4's kinds independently need (a categorical axis, a
  numeric-to-color mapping, a numeric-to-marker-size mapping, a 2-D
  histogram, box-plot quantiles, a kernel density estimate). Each is pure
  numpy (+ pyqtgraph's own QColor/QBrush/ColorMap helpers where a kind
  needs an actual paintable object back) -- no Qt state, no scipy.

**Frozen API -- read before changing anything here.** Multiple wave-2
kind packages are written against the exact names/signatures below in
parallel; if something here turns out wrong or impossible, implement the
closest thing that still works and report it loudly rather than silently
reshaping the interface.
"""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

from ..series import SERIES_KINDS, SeriesKind

__all__ = [
    'CompositeSeriesItem', 'DerivedKind',
    'categories', 'apply_category_ticks', 'clear_category_ticks',
    'jitter', 'value_colors', 'size_scale', 'bin2d', 'quantiles', 'kde',
]


# -- CompositeSeriesItem: a kind whose visual is more than one PlotDataItem ----
class CompositeSeriesItem(pg.GraphicsObject):
    """Base for a kind whose visual is *not* one `PlotDataItem` -- several
    primitives drawn together as one series (a box-and-whisker, a violin
    outline, a quiver field, a contour's polylines, pie wedges...).

    Modeled closely on `view3d.Series3DItem` (read that first) for the
    same reason it exists: `PlotItem.addItem` only files an item into
    `listDataItems()` -- which `figure._series_on`, the Curve Browser, CSV
    export etc. all read to enumerate a subplot's series -- when the item
    `implements('plotData')`. This class provides that plumbing
    (`implements`, `name`/`setName`, `setPen`, `boundingRect`, `paint`)
    once, so a kind's own item subclass only implements the two drawing
    hooks below.

    Subclasses implement:
      `_paint(painter)` -- draw the shape(s) in the item's own LOCAL (data)
        coordinates; `painter` is already positioned/clipped by Qt the way
        any `QGraphicsItem.paint` is. `self.pen`/`self.brush` (both real
        `QPen`/`QBrush`, set via the constructor or `setPen`/`setBrush`)
        are there to use, but nothing requires it -- a kind coloring each
        primitive differently (e.g. per-category) may ignore them.
      `_bounds()` -- `(xmin, xmax, ymin, ymax)` of what's currently drawn,
        in the same local (data) coordinates, or `None` if there is
        nothing to draw yet (an empty series). Backs `boundingRect()` and
        hence the ViewBox's autorange (Home / Fit / a plain add_subplot's
        initial view) -- get it right or the subplot won't frame the data.

    Call `invalidate()` whenever the drawn data changes (new points, a
    style change that affects extent, hidden rows...): it does
    `prepareGeometryChange()` (Qt requires this BEFORE a `boundingRect()`-
    affecting change becomes visible), `informViewBoundsChanged()` (so the
    ViewBox's autorange notices the new extent) and `update()` (repaint).
    `_bounds()` itself is cached (recomputed lazily, only after
    `invalidate()`), the same "cheap unless something changed" discipline
    `Series3DItem.bounds()` already uses, for the same reason (CLAUDE.md's
    own lesson from that class: a full rescan on every paint is the kind
    of cost that is invisible in a small test and very visible at scale).

    **Not click-selectable.** `SeriesMixin._add_series` only wires click
    selection for an item with a `.curve` attribute (a real
    `PlotDataItem`'s internal `PlotCurveItem`) -- a `CompositeSeriesItem`
    has none, so it is plotted but not yet selectable by a click, exactly
    like the existing `BarGraphItem`/`ImageItem` kinds (see CLAUDE.md's
    per-kind "known gaps" notes). This is accepted for round 4, not a
    bug -- say so again in each concrete subclass's own docstring rather
    than faking a `.curve` to silence it.
    """

    def __init__(self, name=None, pen=None, brush=None):
        super().__init__()
        self._name = name
        self.pen = pg.mkPen(pen) if pen is not None else pg.mkPen('k')
        self.brush = pg.mkBrush(brush) if brush is not None else pg.mkBrush(None)
        # What pyqtgraph's legend sample / groups.py read (mirrors
        # Series3DItem.opts -- both are "not a PlotDataItem, but still
        # look like one enough for the parts of the app that only read
        # opts['pen']/opts['symbol']").
        self.opts = {'pen': self.pen, 'symbol': None}
        self._bounds_cache = False   # False = not computed yet; None = empty

    # -- the plot-data-item protocol pyqtgraph and the app use (see the
    # class docstring; mirrors Series3DItem's own version of this block)
    def implements(self, interface=None):
        ints = ['plotData']
        return ints if interface is None else interface in ints

    def name(self):
        return self._name

    def setName(self, name):
        self._name = name

    def setPen(self, *args, **kwargs):
        self.pen = pg.mkPen(*args, **kwargs)
        self.opts['pen'] = self.pen
        self.update()

    def setBrush(self, *args, **kwargs):
        self.brush = pg.mkBrush(*args, **kwargs)
        self.update()

    def getData(self):
        """The two representative 1-D arrays the rest of the app reads
        (Fit Vertical/Horizontal...) -- empty by default (a composite
        shape has no single obvious x/y pair); override when the kind has
        one (e.g. a box's category codes / medians)."""
        return np.zeros(0), np.zeros(0)

    # -- geometry / painting, delegating to the subclass hooks
    def _cached_bounds(self):
        if self._bounds_cache is False:
            self._bounds_cache = self._bounds()
        return self._bounds_cache

    def boundingRect(self):
        b = self._cached_bounds()
        if b is None:
            return QtCore.QRectF()
        x0, x1, y0, y1 = b
        return QtCore.QRectF(QtCore.QPointF(x0, y0), QtCore.QPointF(x1, y1)).normalized()

    def _bounds(self):
        """(xmin, xmax, ymin, ymax) in local coordinates, or None. See the
        class docstring -- subclasses must implement this."""
        raise NotImplementedError

    def paint(self, painter, *args):
        self._paint(painter)

    def _paint(self, painter):
        """Draw in local (data) coordinates. See the class docstring --
        subclasses must implement this."""
        raise NotImplementedError

    def invalidate(self):
        """Call after the drawn data changes -- see the class docstring."""
        self.prepareGeometryChange()
        self._bounds_cache = False
        self.informViewBoundsChanged()
        self.update()


# -- DerivedKind: a kind that delegates to another registered kind ------------
class DerivedKind(SeriesKind):
    """A kind that delegates to another already-registered kind instead of
    building its own item -- this module's version of the round's "re-use
    the same base function, base plots" requirement. Subclasses set `name`
    (their own kind name) and `base` (the registered name of the kind to
    delegate to, e.g. `'line'`/`'scatter'`/`'bar'`/`'imshow'`/`'line3d'`);
    optionally `create_defaults`, a dict of keyword arguments merged UNDER
    the caller's own `**style` (the caller's own choice always wins, via
    plain dict update) before they reach the base kind's `create()`; and
    optionally override `setup(plot_item, item, **kwargs)`, run once right
    after the base kind's `create()` has built and returned `item` --
    e.g. to call `plot_item.setLogMode(...)` (loglog/semilogx/semilogy) or
    `item.setOpts(...)` for a detail the base kind's own `create()` doesn't
    take as a keyword. `kwargs` there is exactly the merged
    `create_defaults`/`style` dict `create()` built (not `x`/`y`/`pen`/
    `name`/`source`/`rows`, which `create()` already consumed positionally/
    by name to build `item` itself).

    `create()`/`to_dict()`/`get_xy()`/`set_xy()` all delegate to the base
    kind by default; `capabilities` defaults to the base kind's too (its
    actions -- brush/fft/remove_average/fit/copy -- generally still apply
    to a plain relabeling/rescaling of the same underlying item type).
    Override any of these on a subclass that needs to transform its own
    arguments before delegating (e.g. `spy` picking the nonzero entries of
    a matrix before handing plain (x, y) point arrays to `scatter`'s
    `create`), or that narrows/widens what applies.
    """
    base = None
    create_defaults = None

    @property
    def base_kind(self):
        return SERIES_KINDS[self.base]

    @property
    def capabilities(self):
        return self.base_kind.capabilities

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None, **style):
        kwargs = dict(self.create_defaults or {})
        kwargs.update(style)
        item = self.base_kind.create(plot_item, x, y, pen=pen, name=name,
                                     source=source, rows=rows, **kwargs)
        self.setup(plot_item, item, **kwargs)
        return item

    def setup(self, plot_item, item, **kwargs):
        """Run once, right after the base kind's create() built `item`.
        The default does nothing; override to apply whatever the base
        kind's own create() doesn't expose as a keyword."""
        pass

    def to_dict(self, item):
        return self.base_kind.to_dict(item)

    def get_xy(self, item):
        return self.base_kind.get_xy(item)

    def set_xy(self, item, x, y):
        self.base_kind.set_xy(item, x, y)


# -- plain-numpy helpers -------------------------------------------------------
def categories(values):
    """Map `values` (any sequence of hashable-per-element values -- strings,
    numbers, ...) to integer codes in 0..n_labels-1, one per element, in
    FIRST-SEEN order (not sorted -- swarmchart/boxchart/violinplot want the
    category order the caller's own data implies preserved, the same
    convention MATLAB's `categorical()` uses for an explicit category
    list). A numeric `values` array is bucketed by exact value, same as a
    string column, with each distinct value's own `str()` as its label.

    Returns `(codes int array shape (n,), labels list[str] length
    n_unique)`.
    """
    values = np.asarray(values)
    flat = values.ravel()
    keys = flat.tolist()  # numpy scalars -> native Python (hashable, comparable)
    seen = {}
    labels = []
    for k in keys:
        if k not in seen:
            seen[k] = len(labels)
            labels.append(str(k))
    codes = np.fromiter((seen[k] for k in keys), dtype=np.intp, count=len(keys))
    return codes, labels


def apply_category_ticks(plot_item, axis, labels):
    """Show `labels` (a list of str) at integer positions 0..len(labels)-1
    on `plot_item`'s `axis` (`'bottom'`/`'left'`/`'top'`/`'right'`, the
    same name `PlotItem.getAxis` takes), replacing whatever ticks were
    there -- the categorical-axis convention swarmchart/boxchart/
    violinplot share. `clear_category_ticks` is the inverse."""
    ax = plot_item.getAxis(axis)
    ax.setTicks([[(float(i), str(label)) for i, label in enumerate(labels)]])


def clear_category_ticks(plot_item, axis):
    """Undo `apply_category_ticks`: restore `axis`'s normal, automatic
    tick computation (`AxisItem.setTicks(None)`)."""
    plot_item.getAxis(axis).setTicks(None)


def jitter(codes, width=0.3, seed=0):
    """Deterministic horizontal jitter for a categorical axis (swarmchart/
    violinplot): `codes` (e.g. from `categories()`) each get a fixed
    pseudo-random offset in `[-width, width]`, seeded so the SAME input
    always produces the SAME jitter (`np.random.default_rng(seed)`, not
    the module-global numpy random state -- repeatable across a re-plot,
    undo/redo, or a test, and independent of anything else that may have
    drawn from numpy's global RNG first)."""
    codes = np.asarray(codes, dtype=float)
    rng = np.random.default_rng(seed)
    return codes + rng.uniform(-width, width, size=codes.shape)


def value_colors(values, cmap='viridis', levels=None):
    """The ONE place a numeric column becomes per-point colors: `values`
    mapped through `cmap` (a pyqtgraph colormap name, e.g. `'viridis'`, or
    an already-built `pg.ColorMap`) over `levels` (a `(lo, hi)` pair), or
    the data's own finite min/max when `levels` is None.

    Returns `(list[QBrush] length len(values), (lo, hi))` -- the second
    element is what was actually used (handy for a caller that also wants
    to attach a colorbar over the same range, e.g. via
    `colorbar.LaColorBar.attach`)."""
    values = np.asarray(values, dtype=float)
    color_map = cmap if isinstance(cmap, pg.ColorMap) else pg.colormap.get(cmap)
    if levels is None:
        finite = values[np.isfinite(values)]
        lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
    else:
        lo, hi = float(levels[0]), float(levels[1])
    span = hi - lo
    if span == 0:
        norm = np.zeros_like(values)
    else:
        norm = np.clip((values - lo) / span, 0.0, 1.0)
    norm = np.nan_to_num(norm, nan=0.0)
    colors = color_map.map(norm, mode='qcolor')
    return [pg.mkBrush(c) for c in colors], (lo, hi)


def size_scale(values, lo_px=4.0, hi_px=24.0):
    """Bubble marker sizes for `values` (e.g. bubblechart's `size=`
    column), linearly interpolated between `lo_px` and `hi_px` over the
    data's own finite min/max. **Area-proportional, not diameter-
    proportional**: the interpolation runs over `sqrt` of the normalized
    value, so doubling a value doubles the marker's apparent AREA (the
    reading a bubble chart's audience actually makes), matching MATLAB's
    own `bubblechart` convention, rather than doubling its diameter (which
    would quadruple the area and visually exaggerate the difference)."""
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.full(values.shape, lo_px)
    vmin, vmax = float(finite.min()), float(finite.max())
    if vmax == vmin:
        norm = np.zeros_like(values)
    else:
        norm = np.clip((values - vmin) / (vmax - vmin), 0.0, 1.0)
    norm = np.nan_to_num(norm, nan=0.0)
    return lo_px + (hi_px - lo_px) * np.sqrt(norm)


def bin2d(x, y, bins=50):
    """A 2-D histogram of `(x, y)` -- plain `np.histogram2d`, for
    binscatter / a heatmap-of-density. Returns `(counts 2-D array shape
    (nx, ny), x_edges, y_edges)`: `counts[i, j]` is the count in
    `x_edges[i]:x_edges[i+1]` by `y_edges[j]:y_edges[j+1]`, `np.histogram2d`'s
    own convention."""
    counts, x_edges, y_edges = np.histogram2d(
        np.asarray(x, dtype=float), np.asarray(y, dtype=float), bins=bins)
    return counts, x_edges, y_edges


def quantiles(values):
    """Tukey's boxplot summary of `values` (1.5*IQR whiskers), for
    boxchart (and reusable by violinplot for its own box overlay, if it
    wants one). Returns a dict: `q1`, `med`, `q3` (25th/50th/75th
    percentiles), `lo_whisker`/`hi_whisker` (the most extreme values still
    within `1.5 * IQR` of `q1`/`q3` -- NOT `q1 - 1.5*IQR` itself, matching
    the classic Tukey/MATLAB `boxplot` convention of whiskers that end on
    an actual data point), and `outliers` (every value beyond the
    whiskers, as a 1-D array). Non-finite values are dropped first; an
    empty/all-non-finite input returns NaN summary values and an empty
    `outliers` array rather than raising."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {'q1': np.nan, 'med': np.nan, 'q3': np.nan,
                'lo_whisker': np.nan, 'hi_whisker': np.nan,
                'outliers': np.zeros(0)}
    q1, med, q3 = (float(v) for v in np.percentile(values, [25, 50, 75]))
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = values[(values >= lo_fence) & (values <= hi_fence)]
    lo_whisker = float(inside.min()) if inside.size else q1
    hi_whisker = float(inside.max()) if inside.size else q3
    outliers = values[(values < lo_whisker) | (values > hi_whisker)]
    return {'q1': q1, 'med': med, 'q3': q3,
            'lo_whisker': lo_whisker, 'hi_whisker': hi_whisker,
            'outliers': outliers}


def kde(values, points=128):
    """A plain-numpy Gaussian kernel density estimate of `values`
    (Silverman's rule-of-thumb bandwidth -- no scipy dependency), for
    violinplot. Returns `(grid float array length `points`, density float
    array same length)`; `density` integrates to ~1 over `grid` (a proper
    density, not just a shape) so several violins drawn to the same scale
    stay comparable. Degenerates gracefully: a single distinct value (or
    fewer than 2 finite samples) returns a single spike at that value
    instead of dividing by a zero bandwidth; an empty input returns an
    all-zero density over an arbitrary `[0, 1]` grid rather than raising.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    n = values.size
    if n == 0:
        return np.linspace(0.0, 1.0, points), np.zeros(points)
    if n < 2 or values.std() == 0:
        lo, hi = float(values.min()) - 0.5, float(values.max()) + 0.5
        grid = np.linspace(lo, hi, points)
        density = np.zeros(points)
        density[int(np.argmin(np.abs(grid - values[0])))] = 1.0
        return grid, density
    std = float(values.std())
    q1, q3 = np.percentile(values, [25, 75])
    iqr = q3 - q1
    sigma = min(std, iqr / 1.34) if iqr > 0 else std
    bandwidth = 0.9 * sigma * n ** (-1.0 / 5.0)
    if bandwidth <= 0:
        bandwidth = std if std > 0 else 1.0
    lo, hi = values.min() - 3 * bandwidth, values.max() + 3 * bandwidth
    grid = np.linspace(lo, hi, points)
    diff = (grid[:, None] - values[None, :]) / bandwidth
    density = np.exp(-0.5 * diff ** 2).sum(axis=1) / (n * bandwidth * np.sqrt(2 * np.pi))
    return grid, density
