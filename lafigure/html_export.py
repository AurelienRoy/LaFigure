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

"""WP-M: HTML export via plotly (CLAUDE.md roadmap Phase 4, "HTML via
plotly" + "Too-large HTML").

`plotly` is an OPTIONAL dependency -- nothing at module import time here
requires it (see `_require_plotly`, called only from the functions that
actually need it), so `import lafigure` / `import lafigure.html_export`
never fails just because plotly isn't installed. Only calling
`export_html`/`build_plotly_figure` without it raises a clear `ImportError`.

**Kept genuinely decoupled from export.py's PNG/JPG/SVG/PDF dialog code**
(see PLAN.md's note for this package): this module knows nothing about
`QPixmap`/`QPainter`; its only two `export.py` touch points are (1) being
registered under `EXPORTERS['html']` and (2) `export.py`'s `_do_export`
calling it with the figure + path instead of a pixmap (its own documented
"free to special-case 'html'" escape hatch).

**One plotly Figure per LaFigure window:**
  - Each subplot is placed by an absolute plotly `domain` (0..1 of the
    whole exported figure), computed from `figure.boxes[plot_item]`
    (fractional grid coordinates, see layout.py/grid.py) mapped through
    `figure.grid_cols`/`grid_rows` with the exact same piecewise-linear
    `grid.to_frac` layout.py itself uses -- so free/overlapping layouts
    (Phase 1) export exactly, not through a generic rectangular
    `make_subplots` grid.
  - Each series becomes a trace via `KIND_CONVERTERS[kind_name]` -- a
    small, focused `{kind_name: converter}` dict (not a `SeriesKind`
    method; `series.py` isn't an owned file here and has no `to_plotly`
    hook), with `_generic_fallback_trace` for any kind without a
    specific entry. A later kind package can add its own entry the same
    way without needing to understand plotly's whole API: a converter is
    `(series, x, y, extra_trace_kwargs) -> a go.Trace or a list of them`.
  - Annotations become plotly shapes (rect/ellipse/line) or annotations
    (arrow/doublearrow/textarrow/text/cursor), in the coordinate system
    matching their anchor (`'axes'` -> the subplot's own data axes,
    `'border'`/`'figure'` -> `paper` fractions derived the same way box
    domains are). A kind this module can't map exactly (an unmapped
    future annotation kind) degrades to a plain text annotation at its
    position rather than being silently dropped.
  - Hidden rows (`DataSource.hide_rows`) are excluded: a source-backed
    series' displayed points are always recomputed from
    `source.visible_rows` at export time (`_visible_xy_rows`), regardless
    of whether `console.watch_source` happened to be armed for it.
  - `ax.datatip` (console.py): a format-string spec is translated
    directly into a plotly `hovertemplate` (`_translate_hovertemplate`);
    a callable spec can't run in the browser, so it falls back to a
    generic x/y + every source column hover via `customdata` (noted, not
    silently wrong).
  - **Too-large HTML**: above `MAX_POINTS_PER_SERIES` points in some
    series, `export_html` shows `TooLargeHtmlDialog` (Keep all / Decimate
    1:N / peak-preserving) before writing; decimation is applied only to
    the over-threshold series, and only to kinds in `DECIMATABLE_KINDS`
    (parallel, same-length x/y arrays -- 'stairs'/'hist' have an
    edges-vs-values length mismatch, per their own kind modules, so
    decimating them safely needs different logic, out of this package's
    scope; 'imshow' is a 2D image, not a point cloud, and is excluded
    from the point count entirely).
"""
import math
import string

import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets

from . import grid
from .richtext import to_plotly

# -- threshold / decimation --------------------------------------------

# Named per PLAN.md's own suggestion ("e.g. 200,000 points per series").
# Checked per series, not as a figure-wide total: one huge series should
# trigger the popup even if every other subplot is tiny.
MAX_POINTS_PER_SERIES = 200_000
DEFAULT_DECIMATE_N = 10

# Kinds whose get_xy() returns two parallel, same-length, point-indexed
# arrays -- the only kinds it's safe to decimate with the generic index
# picking below. 'stairs'/'hist' (edges len == values len + 1) and
# 'imshow' (a 2D matrix, not points) are deliberately excluded.
DECIMATABLE_KINDS = frozenset({'line', 'scatter', 'area', 'bar', 'errorbar'})


class ExportCancelled(Exception):
    """Raised by export_html when the user cancels TooLargeHtmlDialog."""


def stride_indices(n, step):
    """Indices kept by 1:`step` decimation -- exactly ceil(n / step) of
    them."""
    return np.arange(0, n, step)


def bucket_edges(n, n_buckets):
    """n_buckets + 1 integer boundaries splitting range(n) into
    n_buckets contiguous chunks (the last chunk absorbs any remainder,
    via linspace + rounding) -- shared by peak_indices and its own tests
    so a test can recompute the exact same buckets independently."""
    n_buckets = max(1, min(int(n_buckets), n))
    return np.linspace(0, n, n_buckets + 1).astype(int)


def peak_indices(y, n_buckets):
    """Indices kept by peak-preserving decimation: for each of
    `n_buckets` contiguous buckets along y's own index, keep the index of
    its min AND its max (in index order, de-duplicated) -- the same idea
    pyqtgraph's own setDownsampling(method='peak') uses for the live
    display, computed here in plain numpy since plotly has no built-in
    equivalent. Every bucket with at least one point contributes at
    least one index (its min==max point if the bucket has one element)."""
    y = np.asarray(y)
    n = len(y)
    if n == 0:
        return np.array([], dtype=int)
    edges = bucket_edges(n, n_buckets)
    idxs = set()
    for lo, hi in zip(edges[:-1], edges[1:]):
        if hi <= lo:
            continue
        seg = y[lo:hi]
        idxs.add(lo + int(np.argmin(seg)))
        idxs.add(lo + int(np.argmax(seg)))
    return np.array(sorted(idxs))


def decimate_stride(x, y, n):
    """1:N decimation of parallel arrays x/y -- exactly ceil(len(y)/n)
    points."""
    idx = stride_indices(len(y), n)
    return np.asarray(x)[idx], np.asarray(y)[idx]


def decimate_peak(x, y, n_buckets):
    """Peak-preserving decimation of parallel arrays x/y into n_buckets
    buckets (see peak_indices)."""
    idx = peak_indices(y, n_buckets)
    return np.asarray(x)[idx], np.asarray(y)[idx]


def _decimate_with_rows(x, y, rows, choice, n):
    """Like decimate_stride/decimate_peak, but also keeps a third
    parallel array (row indices, for hover customdata) aligned with
    whatever subset of x/y decimation keeps. choice: 'all' | 'stride' |
    'peak'."""
    if choice == 'all' or y is None or len(y) <= 1:
        return x, y, rows
    if choice == 'stride':
        idx = stride_indices(len(y), n)
    elif choice == 'peak':
        n_buckets = max(1, math.ceil(len(y) / n))
        idx = peak_indices(y, n_buckets)
    else:
        raise ValueError(f"unknown decimation choice {choice!r}")
    new_rows = rows[idx] if rows is not None else None
    return x[idx], y[idx], new_rows


# -- the too-large-HTML popup --------------------------------------------

class TooLargeHtmlDialog(QtWidgets.QDialog):
    """Shown by export_html when some series exceeds MAX_POINTS_PER_SERIES.
    Exactly three choices, per the roadmap: keep everything, decimate 1:N
    (N editable, default 10), or a peak-preserving (min/max per bucket,
    same N) decimation."""

    def __init__(self, series_counts, threshold, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Large HTML export")
        total = sum(n for _, n in series_counts)
        over = [n for _, n in series_counts if n > threshold]

        layout = QtWidgets.QVBoxLayout(self)
        msg = (f"This figure has {total:,} plotted points "
               f"({len(over)} series over {threshold:,} points each). "
               "A large HTML file can be slow to open in a browser.")
        label = QtWidgets.QLabel(msg)
        label.setWordWrap(True)
        layout.addWidget(label)

        self.keep_radio = QtWidgets.QRadioButton("Keep all points")
        self.stride_radio = QtWidgets.QRadioButton("Decimate 1:N")
        self.peak_radio = QtWidgets.QRadioButton(
            "Peak-preserving decimation (keeps each bucket's min/max)")
        self.stride_radio.setChecked(True)
        for rb in (self.keep_radio, self.stride_radio, self.peak_radio):
            layout.addWidget(rb)

        n_row = QtWidgets.QHBoxLayout()
        n_row.addWidget(QtWidgets.QLabel("N:"))
        self.n_spin = QtWidgets.QSpinBox()
        self.n_spin.setRange(2, 1_000_000)
        self.n_spin.setValue(DEFAULT_DECIMATE_N)
        n_row.addWidget(self.n_spin)
        n_row.addStretch(1)
        layout.addLayout(n_row)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def choice(self):
        if self.keep_radio.isChecked():
            return 'all'
        if self.peak_radio.isChecked():
            return 'peak'
        return 'stride'

    @property
    def n(self):
        return self.n_spin.value()


# -- plotly, imported lazily ---------------------------------------------

_plotly_go = None


def _require_plotly():
    """The plotly.graph_objects module, imported on first use. Raises a
    clear ImportError (never at `import lafigure` time) if plotly isn't
    installed."""
    global _plotly_go
    if _plotly_go is None:
        try:
            import plotly.graph_objects as go
        except ImportError as e:
            raise ImportError(
                "HTML export requires the optional 'plotly' package -- "
                "install it with `pip install plotly` and try again."
            ) from e
        _plotly_go = go
    return _plotly_go


# -- color helpers --------------------------------------------------------

def _pen_color(pen):
    if pen is None:
        return None
    c = pen.color()
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha() / 255:.3f})"


def _brush_color(brush):
    if brush is None:
        return None
    c = brush.color()
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha() / 255:.3f})"


# -- hidden-row exclusion -------------------------------------------------

def _visible_xy_rows(series):
    """(x, y, rows) for `series` with hidden/filtered rows excluded, if
    it's linked to an explicit DataSource with known (x[, y]) columns;
    (x, y, None) otherwise -- mirrors console.py's _refresh_series, but
    computed independently at export time (never relies on
    console.watch_source having been armed for this series)."""
    x, y = series.kind_obj.get_xy(series.item)
    x = None if x is None else np.asarray(x)
    y = None if y is None else np.asarray(y)
    source = series._source
    rows = series._rows
    if source is None or rows is None or series.columns is None:
        return x, y, None
    hidden = source.hidden_mask
    fmask = source.filter_mask
    visible_mask = (~hidden) if fmask is None else (fmask & ~hidden)
    keep = visible_mask[rows]
    kept_rows = rows[keep]
    xcol = series.columns[0]
    ycol = series.columns[1] if len(series.columns) > 1 else None
    new_x = np.asarray(source[xcol][kept_rows])
    new_y = np.asarray(source[ycol][kept_rows]) if ycol else None
    # Raw source columns -> what the series actually draws, through its
    # display transform (WP-P7's dx/dy/sx/sy; display-only, never written
    # back to the source).
    new_x, new_y = series.transform_xy(new_x, new_y)
    return new_x, (new_y if ycol else y), kept_rows


def _series_point_counts(figure):
    """[(series, point count)] for every series across every subplot,
    after hidden-row exclusion -- 'imshow' series are excluded (a 2D
    image isn't a point cloud)."""
    counts = []
    for plot_item in figure.plots:
        for series in figure._series_on(plot_item):
            if series.kind == 'imshow':
                continue
            _, y, _ = _visible_xy_rows(series)
            counts.append((series, 0 if y is None else len(y)))
    return counts


# -- datatip -> plotly hovertemplate --------------------------------------

def _translate_hovertemplate(spec):
    """A str.format spec (e.g. "{speed:.2f} m/s @ t={t}") -> a plotly
    hovertemplate string with each referenced field replaced by
    '%{x}'/'%{y}' (for those two literal names) or '%{customdata[i]}'
    (any other name -- a DataSource column), plus the ordered list of
    column names customdata must be built from. Literal text in between
    fields is kept verbatim, so the hovertemplate reads like the original
    format string, just with plotly's own substitution tokens."""
    formatter = string.Formatter()
    custom_cols = []
    parts = []
    for literal_text, field_name, format_spec, _conversion in formatter.parse(spec):
        parts.append(literal_text)
        if field_name is None:
            continue
        fmt = f":{format_spec}" if format_spec else ""
        if field_name == 'x':
            parts.append(f"%{{x{fmt}}}")
        elif field_name == 'y':
            parts.append(f"%{{y{fmt}}}")
        else:
            if field_name not in custom_cols:
                custom_cols.append(field_name)
            idx = custom_cols.index(field_name)
            parts.append(f"%{{customdata[{idx}]{fmt}}}")
    return "".join(parts) + "<extra></extra>", custom_cols


def _hover_kwargs_for_series(plot_item, series, rows):
    """{'hovertemplate': ..., 'customdata': ...} for a source-backed,
    row-indexed series with a plot_item.datatip configured, else {}."""
    # Imported here, not at module level: console.py isn't in this
    # package's owned-files list, and this keeps the datatip feature
    # optional the same way plotly itself is -- if console.py were ever
    # unavailable, HTML export without a datatip configured still works.
    from .console import get_datatip

    if rows is None or series._source is None:
        return {}
    spec = get_datatip(plot_item)
    if spec is None:
        return {}
    source = series._source
    if callable(spec):
        # Can't run a Python callable in the exported, static HTML --
        # fall back to a generic hover with every source column instead
        # of silently dropping the customization (noted in this
        # package's report as a documented limitation, not a bug).
        cols = list(source.columns)
        parts = [f"{c}=%{{customdata[{i}]}}" for i, c in enumerate(cols)]
        hovertemplate = "x=%{x}<br>y=%{y}<br>" + "<br>".join(parts) + "<extra></extra>"
    else:
        hovertemplate, cols = _translate_hovertemplate(spec)
    if not cols:
        return {'hovertemplate': hovertemplate}
    customdata = np.column_stack([np.asarray(source[c][rows]) for c in cols])
    return {'hovertemplate': hovertemplate, 'customdata': customdata}


# -- kind -> plotly trace converters --------------------------------------
# Each converter: (series, x, y, extra_kwargs) -> a go.Trace, or a list of
# them (only 'area' needs a second, invisible baseline trace). extra_kwargs
# (hovertemplate/customdata, when present) is passed straight through to
# the trace constructor. A kind package that wants its own plotly mapping
# just adds an entry here -- see this module's own docstring.

def _line_trace(series, x, y, extra):
    go = _require_plotly()
    pen = series.item.opts.get('_orig_pen', series.item.opts.get('pen'))
    return go.Scattergl(x=x, y=y, mode='lines', name=to_plotly(series.name or ''),
                        line=dict(color=_pen_color(pen)), **extra)


def _scatter_trace(series, x, y, extra):
    go = _require_plotly()
    opts = series.item.opts
    color = _pen_color(opts.get('symbolPen')) or _brush_color(opts.get('symbolBrush'))
    size = opts.get('symbolSize', 8)
    return go.Scattergl(x=x, y=y, mode='markers', name=to_plotly(series.name or ''),
                        marker=dict(color=color, size=size), **extra)


def _stairs_trace(series, x, y, extra):
    """x = bin edges (n + 1), y = per-bin values (n) -- expand into
    explicit step coordinates (line_shape='hv') so the shape matches
    pyqtgraph's stepMode='center' rendering exactly."""
    go = _require_plotly()
    edges = np.asarray(x, dtype=float)
    values = np.asarray(y, dtype=float)
    y_ext = np.append(values, values[-1]) if len(values) else values
    pen = series.item.opts.get('_orig_pen', series.item.opts.get('pen'))
    return go.Scatter(x=edges, y=y_ext, mode='lines', line_shape='hv',
                      name=to_plotly(series.name or ''), line=dict(color=_pen_color(pen)), **extra)


def _area_trace(series, x, y, extra):
    go = _require_plotly()
    item = series.item
    pen = item.opts.get('_orig_pen', item.opts.get('pen'))
    y2 = item.opts.get('fillLevel') or 0
    traces = []
    if y2:
        baseline = np.full(len(y), float(y2))
        traces.append(go.Scatter(x=x, y=baseline, mode='lines', line=dict(width=0),
                                 showlegend=False, hoverinfo='skip'))
        fill = 'tonexty'
    else:
        fill = 'tozeroy'
    traces.append(go.Scatter(x=x, y=y, mode='lines', fill=fill, name=to_plotly(series.name or ''),
                             line=dict(color=_pen_color(pen)), **extra))
    return traces


def _hist_trace(series, x, y, extra):
    """Prefer the kind's own stashed raw samples (kinds/hist.py's
    _lafigure_hist_raw) so plotly can bin them itself (go.Histogram);
    falls back to the already-binned edges/counts as a bar chart if that
    attribute is ever absent (e.g. a future kind reusing 'hist' style
    differently)."""
    go = _require_plotly()
    item = series.item
    raw = getattr(item, '_lafigure_hist_raw', None)
    bins = getattr(item, '_lafigure_hist_bins', 30)
    if raw is not None:
        return go.Histogram(x=np.asarray(raw), nbinsx=bins, name=to_plotly(series.name or ''), **extra)
    edges = np.asarray(x, dtype=float)
    counts = np.asarray(y, dtype=float) if y is not None else np.array([])
    centers = (edges[:-1] + edges[1:]) / 2 if len(edges) > 1 else edges
    return go.Bar(x=centers, y=counts, name=to_plotly(series.name or ''), **extra)


def _bar_trace(series, x, y, extra):
    go = _require_plotly()
    return go.Bar(x=x, y=y, name=to_plotly(series.name or ''), **extra)


def _errorbar_trace(series, x, y, extra):
    go = _require_plotly()
    item = series.item
    eb = getattr(item, '_lafigure_errorbar', None)
    yerr = None
    if eb is not None:
        height = eb.opts.get('height')
        if height is not None:
            yerr = np.asarray(height, dtype=float) / 2.0
    pen = item.opts.get('_orig_pen', item.opts.get('pen'))
    kwargs = dict(x=x, y=y, mode='markers+lines', name=to_plotly(series.name or ''),
                 marker=dict(color=_pen_color(pen)))
    if yerr is not None:
        kwargs['error_y'] = dict(type='data', array=yerr, visible=True)
    kwargs.update(extra)
    return go.Scatter(**kwargs)


def _imshow_trace(series, x, y, extra):
    """x is the 2D matrix (ImshowKind.get_xy's own convention); y is
    unused. Not decimated (not in DECIMATABLE_KINDS)."""
    go = _require_plotly()
    item = series.item
    cmap = getattr(item, '_lafigure_cmap', 'viridis')
    cmap_name = cmap if isinstance(cmap, str) else 'viridis'
    colorscale = _PLOTLY_COLORSCALE.get(cmap_name.lower(), 'Viridis')
    kwargs = dict(z=x, colorscale=colorscale, name=to_plotly(series.name or ''))
    levels = item.getLevels()
    if levels is not None:
        kwargs['zmin'], kwargs['zmax'] = levels
    return go.Heatmap(**kwargs)


_PLOTLY_COLORSCALE = {
    'viridis': 'Viridis', 'plasma': 'Plasma', 'inferno': 'Inferno',
    'magma': 'Magma', 'cividis': 'Cividis', 'jet': 'Jet',
    'gray': 'Greys', 'grey': 'Greys',
}


def _generic_fallback_trace(series, x, y, extra):
    """Any kind without its own entry in KIND_CONVERTERS -- a plain
    Scattergl line through whatever get_xy() returns."""
    go = _require_plotly()
    return go.Scattergl(x=x, y=y, mode='lines', name=to_plotly(series.name or ''), **extra)


KIND_CONVERTERS = {
    'line': _line_trace,
    'scatter': _scatter_trace,
    'stairs': _stairs_trace,
    'area': _area_trace,
    'hist': _hist_trace,
    'bar': _bar_trace,
    'errorbar': _errorbar_trace,
    'imshow': _imshow_trace,
}


def _build_traces_for_series(plot_item, series, decimate_choice, decimate_n):
    kind = series.kind
    if kind == 'imshow':
        x, y = series.kind_obj.get_xy(series.item)
        result = _imshow_trace(series, x, y, {})
        return [result]

    x, y, rows = _visible_xy_rows(series)
    if x is None or y is None:
        return []

    if kind in DECIMATABLE_KINDS and len(y) > MAX_POINTS_PER_SERIES:
        x, y, rows = _decimate_with_rows(x, y, rows, decimate_choice, decimate_n)

    extra = _hover_kwargs_for_series(plot_item, series, rows) if kind in DECIMATABLE_KINDS else {}
    converter = KIND_CONVERTERS.get(kind, _generic_fallback_trace)
    result = converter(series, x, y, extra)
    return list(result) if isinstance(result, (list, tuple)) else [result]


# -- subplot domain mapping (grid fractions -> plotly's 0..1 of figure) ---

def _subplot_domain(figure, plot_item):
    """((x0, x1), (y0, y1)) in plotly's paper-fraction convention (0 at
    left/bottom, 1 at right/top) for plot_item's box, mapped through the
    figure's own grid line positions with the same grid.to_frac
    piecewise-linear math layout.py uses for scene pixels -- see grid.py.
    Our own box/grid coordinates increase downward (top < bottom, like
    screen pixels); plotly's y increases upward, hence the 1 - ... flip."""
    left, top, right, bottom = figure.boxes[plot_item]
    x0 = grid.to_frac(figure.grid_cols, left)
    x1 = grid.to_frac(figure.grid_cols, right)
    top_f = grid.to_frac(figure.grid_rows, top)
    bottom_f = grid.to_frac(figure.grid_rows, bottom)
    y0, y1 = 1.0 - bottom_f, 1.0 - top_f
    return (x0, x1), (y0, y1)


def _plot_title(plot_item):
    try:
        return to_plotly(plot_item.titleLabel.text)
    except Exception:
        return ''


def _axis_label(plot_item, axis):
    try:
        return to_plotly(plot_item.getAxis(axis).labelText)
    except Exception:
        return ''


# -- annotations -----------------------------------------------------------

_SHAPE_ANN_KINDS = {'rect': 'rect', 'ellipse': 'circle'}


def _border_ann_paper_xy(figure, plot_item, pt, x_domain, y_domain):
    """A 'border'-anchored annotation's point (scene pixels) -> paper
    fraction, via the subplot's own box fraction (figure._box_fraction,
    layout.py) remapped into that subplot's plotly domain."""
    frac = figure._box_fraction(plot_item, pt)
    x0, x1 = x_domain
    y0, y1 = y_domain  # y1 = subplot's top edge, y0 = its bottom edge (see _subplot_domain)
    return x0 + frac.x() * (x1 - x0), y1 - frac.y() * (y1 - y0)


def _figure_ann_paper_xy(figure, pt):
    """A 'figure'-anchored (free-floating) annotation's point (scene
    pixels) -> paper fraction of the whole exported figure."""
    rect = figure._figure_rect()
    fx = (pt.x() - rect.left()) / rect.width()
    fy = (pt.y() - rect.top()) / rect.height()
    return fx, 1.0 - fy


def _add_annotation(fig, figure, ann, plot_item, xaxis_name, yaxis_name, x_domain, y_domain):
    """Add one AnnotationItem to the plotly figure as a shape (rect/
    ellipse/line) or an annotation (arrow-family/text/cursor), in the
    coordinate system its anchor implies -- see this module's docstring.
    A kind with no good plotly equivalent degrades to a plain text label
    at its position rather than being dropped."""
    if ann.anchor == 'axes':
        # AnnotationItem.pos()/p1_local are already DATA units for an
        # 'axes' anchor (added into the ViewBox's own child group -- see
        # annotations.py's module docstring), so no conversion is needed:
        # they drop straight into the subplot's own plotly axes.
        this_xref, this_yref = xaxis_name, yaxis_name

        def to_ref(pt):
            return pt.x(), pt.y()
    elif ann.anchor == 'border':
        this_xref, this_yref = 'paper', 'paper'

        def to_ref(pt):
            return _border_ann_paper_xy(figure, plot_item, pt, x_domain, y_domain)
    else:  # 'figure'
        this_xref, this_yref = 'paper', 'paper'

        def to_ref(pt):
            return _figure_ann_paper_xy(figure, pt)

    p0 = ann.pos()
    p1 = (QtCore.QPointF(p0.x() + ann.p1_local.x(), p0.y() + ann.p1_local.y())
          if ann.p1_local is not None else p0)
    x0, y0 = to_ref(p0)
    x1, y1 = to_ref(p1)
    color = _pen_color(ann.pen)
    width = ann.pen.widthF() or 1

    if ann.kind in _SHAPE_ANN_KINDS:
        fig.add_shape(type=_SHAPE_ANN_KINDS[ann.kind], xref=this_xref, yref=this_yref,
                     x0=min(x0, x1), x1=max(x0, x1), y0=min(y0, y1), y1=max(y0, y1),
                     line=dict(color=color, width=width), fillcolor=_brush_color(ann.brush))
        return
    if ann.kind == 'line':
        fig.add_shape(type='line', xref=this_xref, yref=this_yref,
                     x0=x0, y0=y0, x1=x1, y1=y1, line=dict(color=color, width=width))
        return
    if ann.kind == 'text':
        fig.add_annotation(x=x0, y=y0, xref=this_xref, yref=this_yref, text=to_plotly(ann.text),
                           showarrow=False, font=dict(color=color))
        return
    if ann.kind in ('arrow', 'textarrow'):
        fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref=this_xref, yref=this_yref,
                           axref=this_xref, ayref=this_yref, showarrow=True,
                           arrowcolor=color, text=to_plotly(ann.text) if ann.kind == 'textarrow' else '')
        return
    if ann.kind == 'doublearrow':
        fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref=this_xref, yref=this_yref,
                           axref=this_xref, ayref=this_yref, showarrow=True,
                           arrowcolor=color, text='')
        fig.add_annotation(x=x0, y=y0, ax=x1, ay=y1, xref=this_xref, yref=this_yref,
                           axref=this_xref, ayref=this_yref, showarrow=True,
                           arrowcolor=color, text='')
        return
    if ann.kind == 'cursor':
        label = f"({to_plotly(ann.text)})" if ann.text else ''
        fig.add_annotation(x=x0, y=y0, ax=x1, ay=y1, xref=this_xref, yref=this_yref,
                           axref=this_xref, ayref=this_yref, showarrow=True,
                           arrowcolor=color, text=label)
        return
    # Any future/unmapped shape kind: degrade to a plain text label
    # rather than dropping it silently.
    fig.add_annotation(x=x0, y=y0, xref=this_xref, yref=this_yref,
                       text=to_plotly(ann.text) or ann.kind, showarrow=False)


# -- building the whole plotly Figure -------------------------------------

def build_plotly_figure(figure, decimate_choice='all', decimate_n=DEFAULT_DECIMATE_N):
    """The whole LaFigure window as one plotly Figure -- every subplot
    placed by its own absolute domain, every series as a trace, every
    annotation as a shape/annotation. `decimate_choice`/`decimate_n`:
    applied only to series over MAX_POINTS_PER_SERIES (see
    _build_traces_for_series) -- 'all' keeps every point regardless."""
    go = _require_plotly()
    fig = go.Figure()
    layout_updates = {}

    for i, plot_item in enumerate(figure.plots, start=1):
        suffix = '' if i == 1 else str(i)
        xaxis_name, yaxis_name = 'x' + suffix, 'y' + suffix
        (x0, x1), (y0, y1) = _subplot_domain(figure, plot_item)
        series_here = figure._series_on(plot_item)
        yaxis_opts = dict(domain=[y0, y1], anchor=xaxis_name, title=_axis_label(plot_item, 'left'))
        if any(s.kind == 'imshow' for s in series_here):
            yaxis_opts['autorange'] = 'reversed'  # row 0 at the top, matching the live ImshowKind
        layout_updates[f'xaxis{suffix}'] = dict(domain=[x0, x1], anchor=yaxis_name,
                                                title=_axis_label(plot_item, 'bottom'))
        layout_updates[f'yaxis{suffix}'] = yaxis_opts

        title = _plot_title(plot_item)
        if title:
            fig.add_annotation(text=title, xref='paper', yref='paper',
                               x=(x0 + x1) / 2, y=y1 + 0.02, showarrow=False,
                               font=dict(size=14), xanchor='center', yanchor='bottom')

        for series in series_here:
            for trace in _build_traces_for_series(plot_item, series, decimate_choice, decimate_n):
                trace.update(xaxis=xaxis_name, yaxis=yaxis_name)
                fig.add_trace(trace)

        for ann in figure._annotations_on(plot_item):
            _add_annotation(fig, figure, ann, plot_item, xaxis_name, yaxis_name, (x0, x1), (y0, y1))

    for ann in figure.annotations:
        if ann.anchor == 'figure':
            _add_annotation(fig, figure, ann, None, None, None, None, None)

    fig.update_layout(**layout_updates)
    return fig


# -- the export entry point (registered as EXPORTERS['html']) -------------

def export_html(figure, path, parent=None, decimate_choice=None, decimate_n=None):
    """Write `figure` as a standalone HTML file at `path`. Signature
    deliberately differs from the (pixmap, path, header_text, header_pos)
    shape every raster/vector exporter uses (export.py's own docstring:
    HTML's input is a plotly figure, not a QPixmap) -- export.py's
    _do_export special-cases 'html' to call this instead.

    If decimate_choice/decimate_n are left None, this estimates the point
    counts first and, only if some series is over MAX_POINTS_PER_SERIES,
    shows TooLargeHtmlDialog (parented on `parent`, typically the Save
    dialog) to ask; canceling that dialog raises ExportCancelled rather
    than writing anything -- callers (export.py) should treat that as "the
    user changed their mind", not a format failure.
    """
    _require_plotly()
    if decimate_choice is None:
        counts = _series_point_counts(figure)
        if any(n > MAX_POINTS_PER_SERIES for _, n in counts):
            dlg = TooLargeHtmlDialog(counts, MAX_POINTS_PER_SERIES, parent)
            if dlg.exec_() != QtWidgets.QDialog.Accepted:
                raise ExportCancelled("HTML export cancelled by the user")
            decimate_choice, decimate_n = dlg.choice, dlg.n
        else:
            decimate_choice, decimate_n = 'all', DEFAULT_DECIMATE_N
    fig = build_plotly_figure(figure, decimate_choice, decimate_n or DEFAULT_DECIMATE_N)
    fig.write_html(path, include_plotlyjs='cdn')
