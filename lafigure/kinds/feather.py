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

"""the 'feather' SeriesKind -- a feather (wind-rose-style) plot.

    ax.feather(x, u=u_array, v=v_array, scale=None, fraction=0.15, arrow_px=9)

Exactly `quiver.QuiverItem`/`QuiverKind`, EXCEPT every arrow's tail sits on
the X axis (y=0) at `x[i]`, regardless of any `y` the caller passes -- the
classic MATLAB `feather()` convention (a row of vectors along one axis,
typically time, e.g. successive wind/current readings). `y` is accepted for
call-signature symmetry with `quiver` (and so a caller migrating from one to
the other doesn't have to drop it) but is IGNORED for tail placement -- see
`FeatherItem._tail_xy`. Reuses `quiver.py`'s autoscale/arrowhead machinery
by subclassing rather than duplicating it (this package owns both files);
see quiver.py's own module docstring for the autoscale and scene-space
arrowhead rationale, both unchanged here.

Same known gaps as quiver: not click-selectable, `capabilities` is just
`{'copy'}`, no `to_plotly` converter (html_export.py's generic Scattergl
fallback would only show the tail points, all pinned to y=0)."""
import numpy as np
import pyqtgraph as pg

from .quiver import QuiverItem, QuiverKind, DEFAULT_FRACTION, DEFAULT_ARROW_PX, DEFAULT_COLOR
from ..series import register_series_kind


class FeatherItem(QuiverItem):
    """Same as QuiverItem, except every tail is pinned to (x[i], 0)."""

    def _tail_xy(self):
        return self._x, np.zeros_like(self._x)


class FeatherKind(QuiverKind):
    name = 'feather'

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               u=None, v=None, scale=None, fraction=DEFAULT_FRACTION,
               arrow_px=DEFAULT_ARROW_PX, **style):
        if u is None or v is None:
            raise TypeError("feather(x, u=..., v=...): u and v are required")
        x = np.asarray(x, dtype=float)
        # y is accepted (call-signature symmetry with quiver) but ignored
        # for tail placement -- every tail is pinned to the X axis, see the
        # module docstring. FeatherItem still needs SOME y array of the
        # right length (it stores self._y even though _tail_xy never reads
        # it) -- reuse the caller's if given, else zeros.
        y_stored = np.asarray(y, dtype=float) if y is not None else np.zeros_like(x)
        color = pg.mkPen(pen).color() if pen is not None else pg.mkColor(DEFAULT_COLOR)
        item = FeatherItem(x, y_stored, u, v, pen=pg.mkPen(color), name=name, scale=scale,
                           fraction=fraction, arrow_px=arrow_px)
        plot_item.addItem(item)
        return item


register_series_kind(FeatherKind())
