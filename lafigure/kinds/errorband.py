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

"""R4-MISC: the 'errorband' SeriesKind -- reachable as
ax.errorband(x, y, yerr=..., ...) (or `y_lower=`/`y_upper=` for an
asymmetric band) once this module is imported. The user's requested
"errorbar with shaded area": a shaded uncertainty band around a center
line, built from the same underlying mechanism `'area'`/`'line'` use --
NOT `pg.ErrorBarItem` (whiskers), which is what `'errorbar'`
(`kinds/errorbar.py`) already covers.

**Two real `pg.PlotDataItem`s, mirroring `errorbar.py`'s own primary/
companion split** (read that module's docstring first -- this kind
follows the identical pattern, including its documented gap):
  - the PRIMARY item (what `Series.item` is, what `_add_series` wires
    clickable) is the CENTER line, built exactly the way `'line'` builds
    one (`plot_item.plot(x, y, pen=...)`) -- so click-selection keeps
    working "for free" through the existing `hasattr(item, 'curve')`
    guard.
  - the BAND is a second `pg.PlotDataItem`, kept in lockstep via a plain
    attribute on the primary item (`item._lafigure_band`), built the same
    way `'area'` builds its own fill (a `PlotDataItem` with a `brush=`)
    -- except an error band's lower edge isn't a constant baseline the
    way area's `fillLevel=y2` is, so a single `fillLevel` can't express
    it. Instead the band item's OWN data traces the closed polygon
    outline directly: forward along the upper edge (`x`, `y + yerr`),
    then back along the lower edge (`x[::-1]`, `y - yerr`)`[::-1]`) --
    and `fillLevel='enclosed'` (confirmed against the installed
    pyqtgraph's `PlotCurveItem._getFillPath`/`_getClosingSegments`: this
    special value skips the normal "connect back to a constant baseline"
    step and fills exactly the path's own closed shape instead) fills
    that polygon with `brush=`, no baseline needed. The band's own pen is
    fully transparent (alpha 0, not `pen=None` -- see CLAUDE.md bug #15:
    `pen=None` reads as "use the kind's default pen" in some call paths,
    not "no pen"), so only the fill shows, never a visible outline
    stroke along the polygon boundary.

**Known gap, same as `errorbar.py`'s own documented one:**
`lafigure/clip_ops.py`'s `delete_curve` only does
`plot_item.removeItem(curve)` on the primary (center-line) item; it has
no knowledge of `_lafigure_band` and won't remove the paired band item,
so deleting an errorband series currently leaves its shaded region
orphaned on the plot. Flagged rather than worked around, per the same
precedent `errorbar.py` set (`clip_ops.py` isn't owned by this package).

**`capabilities` is `{'copy'}` only** -- same conservative choice as
`'bar'`/`'errorbar'`: brush/fft/remove_average/fit were never verified
against a series with a live companion item (a brush-driven `set_xy` on
just the primary line would desync the band unless routed through this
kind's own `set_xy`, which it is -- but Fit/FFT/Remove Average build a
BRAND NEW series rather than calling `set_xy`, so they'd never move the
band at all). A future package generalizing those actions across every
paired-item kind should re-examine this kind alongside `errorbar`'s.
"""
import numpy as np
import pyqtgraph as pg

from ..series import SeriesKind, register_series_kind

_BAND_ATTR = '_lafigure_band'
_ERR_LO_ATTR = '_lafigure_err_lo'
_ERR_HI_ATTR = '_lafigure_err_hi'
DEFAULT_ALPHA = 80


def _resize_to(arr, n):
    """Fit `arr` (or None) to length n -- pad by repeating its last value,
    or truncate -- the same tolerant reshape errorbar.py's own
    `_resized_height` applies, needed so set_xy (a point-count-changing
    set_data) doesn't crash trying to zip mismatched-length arrays."""
    if arr is None:
        return np.zeros(n)
    arr = np.asarray(arr, dtype=float)
    if arr.size == n:
        return arr
    if arr.size == 0:
        return np.zeros(n)
    if arr.size > n:
        return arr[:n].copy()
    return np.concatenate([arr, np.full(n - arr.size, arr[-1])])


def _band_xy(x, lower, upper):
    return np.concatenate([x, x[::-1]]), np.concatenate([upper, lower[::-1]])


class ErrorbandKind(SeriesKind):
    """`ax.errorband(x, y, yerr=..., ...)` -- see module docstring."""
    name = 'errorband'
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               yerr=None, y_lower=None, y_upper=None, band_brush=None,
               band_alpha=DEFAULT_ALPHA, **style):
        x = np.zeros(0) if x is None else np.asarray(x, dtype=float)
        y = np.zeros(0) if y is None else np.asarray(y, dtype=float)
        if y_lower is not None or y_upper is not None:
            lower = y.copy() if y_lower is None else np.broadcast_to(
                np.asarray(y_lower, dtype=float), y.shape).copy()
            upper = y.copy() if y_upper is None else np.broadcast_to(
                np.asarray(y_upper, dtype=float), y.shape).copy()
        else:
            err = np.zeros_like(y) if yerr is None else np.broadcast_to(
                np.asarray(yerr, dtype=float), y.shape).copy()
            lower, upper = y - err, y + err

        if pen is None:
            pen = pg.mkPen('b', width=1)
        else:
            pen = pg.mkPen(pen)

        if band_brush is None:
            color = pg.mkPen(pen).color()
            color.setAlpha(band_alpha)
            band_brush = pg.mkBrush(color)
        band_pen = pg.mkPen(color=(0, 0, 0, 0))  # fully transparent -- see module docstring
        xb, yb = _band_xy(x, lower, upper)
        band = plot_item.plot(xb, yb, pen=band_pen, fillLevel='enclosed', brush=band_brush)

        item = plot_item.plot(x, y, pen=pen, name=name)
        band.setZValue(item.zValue() - 1)  # band behind the center line
        setattr(item, _BAND_ATTR, band)
        setattr(item, _ERR_LO_ATTR, y - lower)
        setattr(item, _ERR_HI_ATTR, upper - y)
        return item

    def to_dict(self, item):
        y = np.asarray(item.yData, dtype=float)
        err_lo = getattr(item, _ERR_LO_ATTR, np.zeros_like(y))
        err_hi = getattr(item, _ERR_HI_ATTR, np.zeros_like(y))
        band = getattr(item, _BAND_ATTR, None)
        return {
            'x': np.array(item.xData, copy=True),
            'y': np.array(item.yData, copy=True),
            'pen': item.opts.get('_orig_pen', item.opts.get('pen')),
            'name': item.name(),
            'style': {
                'y_lower': np.array(y - err_lo, copy=True),
                'y_upper': np.array(y + err_hi, copy=True),
                'band_brush': None if band is None else band.opts.get('fillBrush'),
            },
        }

    def get_xy(self, item):
        return item.xData, item.yData

    def set_xy(self, item, x, y):
        """Overridden (not just get_xy) so the band moves with the center
        line -- same reasoning as errorbar.py's own set_xy override."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        item.setData(x, y)
        band = getattr(item, _BAND_ATTR, None)
        if band is None:
            return
        n = len(y)
        err_lo = _resize_to(getattr(item, _ERR_LO_ATTR, None), n)
        err_hi = _resize_to(getattr(item, _ERR_HI_ATTR, None), n)
        xb, yb = _band_xy(x, y - err_lo, y + err_hi)
        band.setData(xb, yb)
        setattr(item, _ERR_LO_ATTR, err_lo)
        setattr(item, _ERR_HI_ATTR, err_hi)


register_series_kind(ErrorbandKind())
