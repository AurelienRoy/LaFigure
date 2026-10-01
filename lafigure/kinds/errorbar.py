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

"""The 'errorbar' SeriesKind -- reachable as
ax.errorbar(x, y, yerr=..., ...) once this module is imported (see
register_series_kind below).

Unlike 'bar', this kind's *primary* tracked item (Series.item, what
_add_series wires clickable) is a genuine pg.PlotDataItem -- a marker/line
built the ordinary way via plot_item.plot(...) -- so click-selection keeps
working "for free" through the existing hasattr(item, 'curve') guard in
_add_series. The error whiskers are a second, paired pg.ErrorBarItem, kept
in lockstep via a plain attribute on the primary item
(item._lafigure_errorbar) rather than any change to series.py/axes.py.

Known gap (see this package's final report): lafigure/clip_ops.py's
delete_curve only does `plot_item.removeItem(curve)` on the primary item;
it has no knowledge of `_lafigure_errorbar` and doesn't remove the paired
ErrorBarItem, so deleting an errorbar series currently leaves its whiskers
orphaned on the plot. Fixing that means editing clip_ops.py, which this
package doesn't own -- flagged rather than worked around.
"""
import numpy as np
import pyqtgraph as pg

from ..series import SeriesKind, register_series_kind

_EB_ATTR = '_lafigure_errorbar'


def _resized_height(old, n):
    """Fit an existing 'height' (whisker) array to a new point count n --
    needed because ErrorBarItem.drawPath broadcasts y +/- height/2
    elementwise and raises if the lengths differ, which a plain
    eb.setData(x=x, y=y) (leaving 'height' at its old length) would trigger
    the moment set_data changes the point count, not just the positions."""
    if old is None:
        return None
    old = np.asarray(old, dtype=float)
    if old.size == n:
        return old
    if old.size == 0:
        return np.zeros(n)
    if old.size > n:
        return old[:n].copy()
    return np.concatenate([old, np.full(n - old.size, old[-1])])


class ErrorbarKind(SeriesKind):
    name = 'errorbar'
    # See bar.py's comment on the same restriction: only 'copy' (to_dict/
    # create round trip) has been verified against this kind's item shape.
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               yerr=None, symbol='o', **style):
        x = np.zeros(0) if x is None else np.asarray(x, dtype=float)
        y = np.zeros(0) if y is None else np.asarray(y, dtype=float)
        kwargs = {'name': name, 'symbol': symbol}
        if pen is not None:
            kwargs['pen'] = pen
        item = plot_item.plot(x, y, **kwargs)

        if yerr is None:
            yerr_arr = np.zeros_like(y)
        else:
            yerr_arr = np.broadcast_to(np.asarray(yerr, dtype=float), y.shape).copy()
        eb_kwargs = {'x': x, 'y': y, 'height': 2.0 * yerr_arr}
        if pen is not None:
            eb_kwargs['pen'] = pen
        eb = pg.ErrorBarItem(**eb_kwargs)
        plot_item.addItem(eb)
        setattr(item, _EB_ATTR, eb)
        return item

    def to_dict(self, item):
        eb = getattr(item, _EB_ATTR, None)
        height = None if eb is None else eb.opts.get('height')
        yerr = None if height is None else np.asarray(height, dtype=float) / 2.0
        return {
            'x': np.array(item.xData, copy=True),
            'y': np.array(item.yData, copy=True),
            # The pen before any selection highlight (selection_ui keeps it
            # there), same convention as LineKind.to_dict.
            'pen': item.opts.get('_orig_pen', item.opts.get('pen')),
            'name': item.name(),
            'style': {
                'yerr': None if yerr is None else np.array(yerr, copy=True),
                'symbol': item.opts.get('symbol'),
            },
        }

    def set_xy(self, item, x, y):
        """Overridden (not just get_xy) because moving the primary item's
        data without also repositioning the paired ErrorBarItem would leave
        the whiskers drifted from the markers -- see the work package note
        on set_data needing to move both together."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        item.setData(x, y)
        eb = getattr(item, _EB_ATTR, None)
        if eb is not None:
            height = _resized_height(eb.opts.get('height'), len(x))
            eb.setData(x=x, y=y, height=height)


register_series_kind(ErrorbarKind())
