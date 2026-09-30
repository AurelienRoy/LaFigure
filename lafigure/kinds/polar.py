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

"""ax.polar(theta, r, **style) -- a line traced in polar coordinates
(theta in RADIANS, standard math orientation -- see kinds/_polar_base.py),
drawn on an ordinary cartesian PlotItem with hidden axes and a locked 1:1
aspect (round 4's confirmed decision: no new axes_type for the polar
family). Delegates the actual drawing to the 'line' kind, via
_base.DerivedKind -- the round's "re-use the same base function"
requirement -- so a polar curve is a genuine pg.PlotDataItem: click-
selection, brushing and the millions-of-points settings ('line''s own
clip_to_view/downsample) all keep working on it exactly as they do on a
plain ax.plot curve, just fed already-converted (x, y).

The shared polar grid (radial rings, angular spokes, degree labels) is
drawn/grown under the subplot by _polar_base.grow_polar_grid every time
a polar series is added to it, sized to the largest r any polar-family
series on that subplot has shown so far.

**Round-trips through theta/r, not the drawn x/y.** `to_dict()`/`create()`
's own (x, y) pair IS (theta, r) -- what `ax.polar(theta, r)` was
actually called with -- so copy/paste and undo/redo (which both rebuild
through create()) reconstruct a polar series exactly, grid included.
`Series.x`/`.y` (via get_xy, delegated to 'line') stay the drawn
CARTESIAN coordinates instead, matching every other kind and this
project's Transform convention (series.py's module docstring: "'x'/'y'
stay drawn data") -- so `set_data`/brushing/Stats/Fit/CSV export all see
and write the CARTESIAN projection, not theta/r. A caller wanting to
change the underlying angle/radius data has to convert with
`polar_to_xy` first and call `set_data` with the result, exactly like
any other kind's set_data always writes what's actually drawn.

**Capabilities, honestly narrowed.** 'line' also claims 'fft' and
'remove_average' -- neither is verified (or really meaningful) against a
polar trace's CARTESIAN projection (an FFT of x(t) mixed with a
periodicity artifact from wrapping theta, an "average" that isn't an
average of anything the user thinks in radius/angle terms), so this kind
narrows capabilities to `{'brush', 'copy'}` rather than inheriting
DerivedKind's default (the base kind's capabilities) -- 'fit' is left
out too, for the same reason (a linear/polynomial fit through a
CARTESIAN polar projection isn't a meaningful "fit" of the polar data).
Brushing a rectangle still works exactly as on any 'line' curve -- it
selects points by their drawn (x, y) position, which is the CARTESIAN
plane the trace is actually shown in; a user thinking of the brush
rectangle in (theta, r) terms may find the selected region reads
differently on a polar plot than on a cartesian one -- a UI/UX note, not
a bug in the row selection itself, and out of this package's scope.
"""
import numpy as np

from ._base import DerivedKind
from ._polar_base import grow_polar_grid, polar_to_xy
from ..series import register_series_kind

_THETA_R_ATTR = '_lafigure_polar_theta_r'


class PolarKind(DerivedKind):
    name = 'polar'
    base = 'line'
    capabilities = frozenset({'brush', 'copy'})  # see module docstring

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None, **style):
        theta = np.zeros(0) if x is None else np.asarray(x, dtype=float)
        r = np.zeros(0) if y is None else np.asarray(y, dtype=float)
        gx, gy = polar_to_xy(theta, r)
        item = self.base_kind.create(plot_item, gx, gy, pen=pen, name=name,
                                     source=source, rows=rows, **style)
        setattr(item, _THETA_R_ATTR, (theta, r))
        self.setup(plot_item, item, **style)
        return item

    def setup(self, plot_item, item, **kwargs):
        theta, r = getattr(item, _THETA_R_ATTR, (np.zeros(0), np.zeros(0)))
        rmax = float(np.max(np.abs(r))) if r.size else 1.0
        grow_polar_grid(plot_item, rmax)

    def to_dict(self, item):
        theta, r = getattr(item, _THETA_R_ATTR, (np.zeros(0), np.zeros(0)))
        d = self.base_kind.to_dict(item)
        d['x'] = np.array(theta, copy=True)
        d['y'] = np.array(r, copy=True)
        return d


register_series_kind(PolarKind())
