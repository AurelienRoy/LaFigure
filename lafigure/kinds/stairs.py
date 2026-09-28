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

"""ax.stairs(edges, values, **style) -- a standard step plot from bin
edges + per-bin values, backed by a genuine pg.PlotDataItem with
stepMode='center'.

pyqtgraph's PlotCurveItem.setData docs (this project's installed version,
0.14.0) say stepMode='center' draws each `x` value as a step BOUNDARY,
with `y` giving the value of the step between two consecutive boundaries
-- so it wants `len(x) == len(y) + 1` (edges), exactly the histogram/
stairs convention, unlike 'left'/'right' which want `len(x) == len(y)`
(each x itself is one edge of its own step). 'center' is therefore the
one that takes `edges` (n+1 points) and `values`/`counts` (n points) as
this kind's own call convention already promises -- confirmed by reading
PlotCurveItem.setData's source, not guessed (see this package's CLAUDE.md
lesson on not assuming pyqtgraph API behavior)."""
import numpy as np

from ..series import SeriesKind, register_series_kind


class StairsKind(SeriesKind):
    name = 'stairs'
    # NOT 'brush': RectBrush (brushing.py) zips curve.xData/yData as
    # same-length parallel arrays, but a 'center'-stepMode item's xData
    # (edges) is one element LONGER than its yData (values) -- brushing
    # this kind today would misalign or crash. Left for WP-J (generalizing
    # brushing per-kind) rather than worked around here.
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None, **style):
        edges = np.asarray(x, dtype=float)
        values = np.asarray(y, dtype=float)
        if len(edges) != len(values) + 1:
            raise ValueError(
                f"stairs(edges, values): edges must have exactly one more point than "
                f"values (got {len(edges)} edges, {len(values)} values)")
        kwargs = {'name': name, 'stepMode': 'center'}
        if pen is not None:
            kwargs['pen'] = pen
        return plot_item.plot(edges, values, **kwargs)

    def to_dict(self, item):
        return {
            'x': np.array(item.xData, copy=True),
            'y': np.array(item.yData, copy=True),
            'pen': item.opts.get('_orig_pen', item.opts.get('pen')),
            'name': item.name(),
            'style': {},
        }


register_series_kind(StairsKind())
