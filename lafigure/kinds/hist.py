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

"""ax.hist(data, bins=30, **style) -- a histogram of raw samples.

Per Axes._plot_kind's calling convention, `ax.hist(data, bins=30)` routes
through `_add_series(plot_item, 'hist', data, None, bins=30)`, so
HistKind.create receives x=the raw samples (NOT already binned) and
y=None, exactly like every other kind here -- create() itself does the
binning (np.histogram) and builds the same 'center'-stepMode
pg.PlotDataItem stairs.py uses (edges, counts).

to_dict/undo/copy-paste storage choice: store the ORIGINAL raw samples
(+ `bins`), not the computed edges/counts. A histogram is conceptually a
view over raw samples, not a fixed pair of arrays -- storing the raw data
means undo/copy-paste re-bins from scratch and stays correct even if
np.histogram's own binning algorithm or the sample data were to change
later, at the cost of re-running np.histogram on every rebuild (cheap next
to the millions-of-points curves this app already handles). The raw
samples aren't retrievable from the built item's own xData/yData (those
are bin edges/counts, already lossy), so they're kept on the item itself,
the same pattern series.py's own _SERIES_ATTR uses for the Series
wrapper."""
import numpy as np

from ..series import SeriesKind, register_series_kind

DEFAULT_BINS = 30
_RAW_ATTR = '_lafigure_hist_raw'
_BINS_ATTR = '_lafigure_hist_bins'


class HistKind(SeriesKind):
    name = 'hist'
    # NOT 'brush': same length mismatch as stairs (stepMode='center'
    # edges vs. counts) -- see stairs.py's comment, identical reasoning.
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               bins=DEFAULT_BINS, **style):
        data = np.asarray(x, dtype=float)
        counts, edges = np.histogram(data, bins=bins)
        kwargs = {'name': name, 'stepMode': 'center'}
        if pen is not None:
            kwargs['pen'] = pen
        item = plot_item.plot(edges, counts.astype(float), **kwargs)
        setattr(item, _RAW_ATTR, data.copy())
        setattr(item, _BINS_ATTR, bins)
        return item

    def to_dict(self, item):
        return {
            'x': np.array(getattr(item, _RAW_ATTR, item.xData), copy=True),
            'y': None,
            'pen': item.opts.get('_orig_pen', item.opts.get('pen')),
            'name': item.name(),
            'style': {'bins': getattr(item, _BINS_ATTR, DEFAULT_BINS)},
        }


register_series_kind(HistKind())
