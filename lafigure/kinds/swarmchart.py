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

"""the 'swarmchart' SeriesKind -- one point per sample, placed at
its category's integer X position, spread apart (jittered) horizontally so
overlapping points at the same value stay individually visible -- MATLAB's
own `swarmchart`.

    ax.swarmchart(categories, values)                 # categories: any
                                                        # hashable-per-element
                                                        # sequence (strings or
                                                        # numbers), via
                                                        # _base.categories
    ax.swarmchart(source, x='group', y='measurement')  # a DataSource column

**Re-uses the same base function**: delegates the actual point-drawing to
the registered 'scatter' kind's `create()` -- the only new work here is
turning `x` (raw category values) into integer category codes
(`_base.categories`) and then a jittered X position (`_base.jitter`), and
putting the resulting labels on the subplot's bottom axis
(`_base.apply_category_ticks`).

**Round-trip**: `to_dict()` returns the RAW category values (not the
jittered positions) as `'x'`, plus `width`/`seed` in `style`, so `create()`
re-derives the exact same jitter deterministically on copy/paste or
undo/redo (`_base.jitter`'s own docstring: same input -> same output, seeded
via `np.random.default_rng`, independent of anything else that may have
drawn from numpy's global RNG state first).

**Known gaps**: brushing/deleting a point acts on its JITTERED (drawn)
position, same as any other scatter-derived kind -- there is no notion of
"delete this category's whole group" here, only individual points; the
category axis ticks are left on the subplot after every swarmchart create
(no attempt is made to merge ticks from two swarmcharts on the same
subplot, or to restore the axis's normal numeric ticks if the swarmchart is
later deleted -- `_base.clear_category_ticks` exists for a future package to
wire that up). `to_plotly`/HTML export has no dedicated converter (falls
back to the generic Scattergl one, which won't reproduce the categorical
tick labels).
"""
import numpy as np

from ..series import SERIES_KINDS, SeriesKind, register_series_kind
from ._base import apply_category_ticks, categories, jitter

DEFAULT_WIDTH = 0.3
DEFAULT_SEED = 0
DEFAULT_SYMBOL = 'o'
DEFAULT_SIZE = 8


class SwarmChartKind(SeriesKind):
    """One point per sample on a categorical X axis, jittered apart -- see
    module docstring. `get_xy`/`set_xy` are the inherited SeriesKind
    defaults (a real pg.PlotDataItem from the 'scatter' kind)."""
    name = 'swarmchart'
    capabilities = frozenset({'brush', 'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               width=DEFAULT_WIDTH, seed=DEFAULT_SEED, size=DEFAULT_SIZE,
               symbol=DEFAULT_SYMBOL, **style):
        cat_values = np.asarray(x) if x is not None else np.zeros(0)
        values = np.zeros(0) if y is None else np.asarray(y, dtype=float)
        codes, labels = categories(cat_values)
        xs = jitter(codes, width=width, seed=seed)

        item = SERIES_KINDS['scatter'].create(
            plot_item, xs, values, pen=pen, name=name, source=source, rows=rows,
            size=size, symbol=symbol, **style)

        apply_category_ticks(plot_item, 'bottom', labels)
        item._lafigure_swarm_categories = cat_values
        item._lafigure_swarm_labels = labels
        item._lafigure_swarm_width = width
        item._lafigure_swarm_seed = seed
        return item

    def to_dict(self, item):
        scatter_dict = SERIES_KINDS['scatter'].to_dict(item)
        cats = getattr(item, '_lafigure_swarm_categories', None)
        style = dict(scatter_dict['style'])
        style['width'] = getattr(item, '_lafigure_swarm_width', DEFAULT_WIDTH)
        style['seed'] = getattr(item, '_lafigure_swarm_seed', DEFAULT_SEED)
        return {
            # 'x' is the RAW categories (not the jittered positions actually
            # drawn), so create() re-derives the identical jitter on a
            # round trip -- see module docstring.
            'x': np.array(cats, copy=True) if cats is not None else scatter_dict['x'],
            'y': scatter_dict['y'],
            'pen': scatter_dict['pen'],
            'name': scatter_dict['name'],
            'style': style,
        }


register_series_kind(SwarmChartKind())
