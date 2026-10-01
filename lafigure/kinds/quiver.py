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

"""the 'quiver' SeriesKind -- a field of arrows.

    ax.quiver(x, y, u=u_array, v=v_array, scale=None, fraction=0.15,
              arrow_px=9)

One arrow per sample `i`, tail at `(x[i], y[i])`, pointing along
`(u[i], v[i])` scaled by a single scalar `scale`. A `_base.CompositeSeriesItem`
(this is exactly the "visual isn't one existing item's shape" case that
class exists for), since an arrow field is several primitives (shaft +
triangular head) per sample, not one `PlotDataItem`.

**Autoscale ("a fraction of the data range")**: when `scale` isn't given
explicitly, `_autoscale` picks it so the LONGEST arrow's length, in data
units after scaling, equals `fraction` (default 0.15) times the Euclidean
diagonal of the samples' own `(x, y)` bounding box -- a single scalar
factor applied identically to `u` and `v`, never a per-axis stretch (that
would change each arrow's on-screen DIRECTION, not just its length -- see
the `lafigure-axes-geometry` skill's own distinction between a direction
and a plain data-space extent). Degenerates gracefully to a single fixed
fallback when there's only one sample or every vector is zero-length --
see `_autoscale`'s own docstring.

**Arrowhead built in SCENE (screen-pixel) space, not local (data) space**
-- read `.claude/skills/lafigure-axes-geometry/SKILL.md` first. The shaft
itself (tail -> head) is a genuine data-space vector and is drawn directly
in local coordinates -- that's its real, intended extent, not a bug (the
skill's own "does NOT apply" carve-out). Only the head's two back corners,
which have an inherent on-screen DIRECTION (pointing along the shaft as it
actually looks on screen), are computed from an angle measured in scene
space and mapped back -- otherwise the triangle warps into a lopsided
shape on any subplot whose X/Y data-per-pixel ratio isn't 1:1. This mirrors
`annotations.AnnotationItem._draw_arrowhead` almost exactly; duplicated
here (not imported) since this package doesn't own annotations.py.

**Known gaps, stated plainly rather than worked around:**
- Not click-selectable (`CompositeSeriesItem` has no `.curve` -- see its
  own docstring); `capabilities` is just `{'copy'}` -- no brush/fft/
  remove_average/fit, since a directional vector field isn't a set of
  independently selectable points in the way those actions assume.
- No `to_plotly` converter for HTML export -- `html_export.py`'s generic
  `Scattergl` fallback would draw only the tail points, not the arrows;
  a real converter is future work, reported rather than attempted here
  (this package doesn't own `html_export.py`).
"""
import math

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui

from ._base import CompositeSeriesItem
from ..series import SeriesKind, register_series_kind

DEFAULT_FRACTION = 0.15   # of the samples' own (x, y) bounding-box diagonal
DEFAULT_ARROW_PX = 9
ARROWHEAD_SPREAD = math.pi / 7   # same half-angle annotations.py's arrowhead uses
DEFAULT_COLOR = 'b'


def _autoscale(tail_x, tail_y, u, v, fraction):
    """The scalar `scale` such that the longest `(u, v)` vector, scaled,
    has length `fraction` times the (tail_x, tail_y) samples' own bounding
    -box diagonal. Falls back to `fraction` itself (i.e. scale == fraction)
    when that diagonal is zero (one sample, or every sample at the same
    point) -- the vectors are then scaled by a plain fraction of their own
    magnitude, which is still well-defined and deterministic. Falls back to
    1.0 (no scaling) when every vector is zero-length, since there is then
    nothing to scale relative to."""
    mag = np.hypot(u, v)
    finite_mag = mag[np.isfinite(mag)]
    max_mag = float(finite_mag.max()) if finite_mag.size else 0.0
    if max_mag <= 0:
        return 1.0
    if len(tail_x) > 1:
        xr = float(np.max(tail_x) - np.min(tail_x))
        yr = float(np.max(tail_y) - np.min(tail_y))
        data_range = math.hypot(xr, yr)
    else:
        data_range = 0.0
    if data_range <= 0:
        data_range = max_mag
    return fraction * data_range / max_mag


class QuiverItem(CompositeSeriesItem):
    """One arrow per `(x[i], y[i])`, pointing along `(u[i], v[i]) * scale`.
    See the module docstring for the autoscale/arrowhead conventions.
    `getData()` returns the sample positions `(x, y)` -- the field's own
    representative points, per `CompositeSeriesItem`'s own convention."""

    def __init__(self, x, y, u, v, pen=None, name=None, scale=None,
                 fraction=DEFAULT_FRACTION, arrow_px=DEFAULT_ARROW_PX):
        super().__init__(name=name, pen=pen)
        self.pen.setCosmetic(True)  # constant on-screen shaft width, not data-scaled
        self.arrow_px = float(arrow_px)
        self._set_data(x, y, u, v, scale, fraction)

    # -- data --------------------------------------------------------------
    def _set_data(self, x, y, u, v, scale, fraction):
        self._x = np.asarray(x, dtype=float)
        self._y = np.asarray(y, dtype=float)
        self._u = np.asarray(u, dtype=float)
        self._v = np.asarray(v, dtype=float)
        if len(self._x) != len(self._y) or len(self._x) != len(self._u) or len(self._x) != len(self._v):
            raise ValueError("quiver: x, y, u, v must all have the same length")
        self._fraction = float(fraction)
        tx, ty = self._tail_xy()
        self.scale = float(scale) if scale is not None else _autoscale(tx, ty, self._u, self._v, self._fraction)
        self.invalidate()

    def _tail_xy(self):
        """Where each arrow starts -- quiver: the sample point itself.
        `feather.FeatherItem` overrides this to pin every tail to the X
        axis instead."""
        return self._x, self._y

    def _head_xy(self):
        tx, ty = self._tail_xy()
        return tx + self._u * self.scale, ty + self._v * self.scale

    def getData(self):
        return self._x, self._y

    def set_xy(self, x, y):
        """Reposition the sample points, keeping (u, v) and the current
        scale -- used by Series.set_data. A length check mirrors
        _set_data's own."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if len(x) != len(self._u):
            raise ValueError("quiver.set_xy: length must match u/v")
        self._x, self._y = x, y
        self.invalidate()

    # -- geometry ------------------------------------------------------
    def _bounds(self):
        if len(self._x) == 0:
            return None
        tx, ty = self._tail_xy()
        hx, hy = self._head_xy()
        xs = np.concatenate([tx, hx])
        ys = np.concatenate([ty, hy])
        if xs.size == 0:
            return None
        return float(np.min(xs)), float(np.max(xs)), float(np.min(ys)), float(np.max(ys))

    def _paint(self, painter):
        painter.setPen(self.pen)
        painter.setBrush(QtGui.QBrush(self.pen.color()))
        tx, ty = self._tail_xy()
        hx, hy = self._head_xy()
        for i in range(len(tx)):
            tail = QtCore.QPointF(float(tx[i]), float(ty[i]))
            head = QtCore.QPointF(float(hx[i]), float(hy[i]))
            painter.drawLine(tail, head)
            if head != tail:
                self._draw_arrowhead(painter, head, tail)

    def _draw_arrowhead(self, painter, tip, tail):
        """A filled triangular arrowhead at `tip` (local/data coords),
        pointing away from `tail`. See the module docstring: built in SCENE
        space, mirroring annotations.AnnotationItem._draw_arrowhead. `tip`
        itself is never round-tripped through the scene mapping, so the
        head stays attached exactly at the shaft's real endpoint; only the
        two back corners (whose DIRECTION matters, not just their data-
        space position) go through mapToScene/mapFromScene."""
        tip_scene = self.mapToScene(tip)
        tail_scene = self.mapToScene(tail)
        angle = math.atan2(tip_scene.y() - tail_scene.y(), tip_scene.x() - tail_scene.x())
        size = self.arrow_px
        p1_scene = tip_scene - QtCore.QPointF(size * math.cos(angle - ARROWHEAD_SPREAD),
                                              size * math.sin(angle - ARROWHEAD_SPREAD))
        p2_scene = tip_scene - QtCore.QPointF(size * math.cos(angle + ARROWHEAD_SPREAD),
                                              size * math.sin(angle + ARROWHEAD_SPREAD))
        poly = QtGui.QPolygonF([tip, self.mapFromScene(p1_scene), self.mapFromScene(p2_scene)])
        painter.drawPolygon(poly)


class QuiverKind(SeriesKind):
    name = 'quiver'
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               u=None, v=None, scale=None, fraction=DEFAULT_FRACTION,
               arrow_px=DEFAULT_ARROW_PX, **style):
        if u is None or v is None:
            raise TypeError("quiver(x, y, u=..., v=...): u and v are required")
        if y is None:
            raise TypeError("quiver(x, y, u=..., v=...): y is required (see feather for tails on the X axis)")
        color = pg.mkPen(pen).color() if pen is not None else pg.mkColor(DEFAULT_COLOR)
        item = QuiverItem(x, y, u, v, pen=pg.mkPen(color), name=name, scale=scale,
                          fraction=fraction, arrow_px=arrow_px)
        plot_item.addItem(item)
        return item

    def to_dict(self, item):
        return {
            'x': np.array(item._x, copy=True),
            'y': np.array(item._y, copy=True),
            'pen': item.opts.get('pen'),
            'name': item.name(),
            'style': {
                'u': np.array(item._u, copy=True), 'v': np.array(item._v, copy=True),
                'scale': item.scale, 'fraction': item._fraction, 'arrow_px': item.arrow_px,
            },
        }

    def get_xy(self, item):
        return item.getData()

    def set_xy(self, item, x, y):
        item.set_xy(x, y)


register_series_kind(QuiverKind())
