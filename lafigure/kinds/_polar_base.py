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

"""Shared support for the polar family of kinds (PLAN.md "R4-POLAR":
polar, polarhistogram, piechart).

**Confirmed round-4 decision: no new `axes_type`.** A polar kind is drawn
on an ordinary cartesian `PlotItem` -- it converts its own angle/radius
data to (x, y) itself and this module draws a decorative grid (radial
rings + angular spokes + degree labels) directly into that same
`PlotItem`'s `ViewBox`, hiding the normal cartesian axes and locking a
1:1 aspect so the grid (and the data plotted through `polar_to_xy`) reads
as round on screen regardless of the subplot's own box shape.

Because the aspect is locked 1:1 here, every polar kind's own geometry
(wedge edges, the arrow-free grid spokes) is safe to compute directly in
LOCAL (data) space with plain trig -- the data-per-pixel ratio this
module locks is exactly the case `.claude/skills/lafigure-axes-geometry
/SKILL.md` says makes local-space angle math correct (its warning is
about the *general*, non-1:1 case, not a blanket "always map through
scene space").

Angle convention throughout this package: **radians, standard math
orientation** -- 0 at the +X axis, increasing COUNTER-clockwise, exactly
MATLAB's `polarplot(theta, rho)` -- so `polar_to_xy` and every wedge/spoke
built from it (draw_polar_grid, polarhistogram's bins, piechart's slices)
agree with each other and with `ax.polar(theta, r)`'s own two inputs.

- `polar_to_xy` / `polar_grid_rmax` (via `_GRID_RMAX_ATTR`): the numeric
  core.
- `setup_polar_axes`: hide the cartesian axes, lock 1:1 aspect -- every
  polar kind calls this, even piechart, which doesn't call
  `draw_polar_grid` at all (a pie has no radial *scale* to show rings
  for; see piechart.py's own docstring).
- `draw_polar_grid` / `clear_polar_grid` / `grow_polar_grid`: the shared
  decoration. Calling `draw_polar_grid` again on the SAME `plot_item`
  replaces its previous grid rather than stacking a second one (kept in
  `plot_item._lafigure_polar_grid`) -- `grow_polar_grid` is what
  `polar.py`/`polarhistogram.py` actually call, so two polar-family
  series sharing one subplot end up with ONE grid, sized to the larger
  of the two (never shrinks back down on its own -- a known, documented
  simplification, not a bug: re-plotting a smaller series on the same
  subplot after a bigger one leaves the bigger grid showing).
"""
import math

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

__all__ = [
    'polar_to_xy', 'setup_polar_axes',
    'draw_polar_grid', 'clear_polar_grid', 'grow_polar_grid',
]

DEFAULT_RINGS = 4
DEFAULT_SPOKE_DEG = 30

_GRID_ATTR = '_lafigure_polar_grid'
_GRID_RMAX_ATTR = '_lafigure_polar_grid_rmax'


def polar_to_xy(theta, r):
    """(theta radians, r) -> (x, y) float arrays (same broadcast shape as
    theta/r): x = r*cos(theta), y = r*sin(theta) -- standard math
    orientation (0 rad = +X axis, increasing counter-clockwise), matching
    MATLAB's `polarplot(theta, rho)`. A negative r is plotted on the
    opposite side (as if theta were theta+pi) rather than clipped to 0 --
    `r*cos`/`r*sin` already do this for free, no special-casing needed."""
    theta = np.asarray(theta, dtype=float)
    r = np.asarray(r, dtype=float)
    return r * np.cos(theta), r * np.sin(theta)


def setup_polar_axes(plot_item):
    """Hide the ordinary cartesian axes/grid and lock a 1:1 aspect ratio
    on plot_item, so polar geometry drawn on it (this module's grid, and
    any polar kind's own converted x/y) reads as round on screen
    regardless of the subplot's box shape. Idempotent -- safe to call
    once per series added to the same subplot (every polar-family kind's
    create() does)."""
    for axis in ('left', 'bottom', 'top', 'right'):
        plot_item.hideAxis(axis)
    plot_item.showGrid(x=False, y=False)
    plot_item.getViewBox().setAspectLocked(True)


def clear_polar_grid(plot_item):
    """Remove whatever grid draw_polar_grid last drew on plot_item (a
    no-op if there is none yet)."""
    for item in getattr(plot_item, _GRID_ATTR, None) or []:
        try:
            plot_item.removeItem(item)
        except Exception:
            pass
    setattr(plot_item, _GRID_ATTR, [])
    setattr(plot_item, _GRID_RMAX_ATTR, 0.0)


def draw_polar_grid(plot_item, rmax, rings=DEFAULT_RINGS, spoke_deg=DEFAULT_SPOKE_DEG, pen=None):
    """(Re)draw radial rings + angular spokes + degree labels on
    plot_item, sized so the outermost ring sits at radius `rmax`.
    Replaces whatever grid this function (or grow_polar_grid) last drew
    on plot_item -- see the module docstring. Every item is added with
    `ignoreBounds=True` (the established pyqtgraph convention in this
    project -- see kinds/line3d.py, kinds/scatter3d.py, kinds/surface.py)
    so the grid itself never feeds the ViewBox's autorange; the view
    range is instead set explicitly here, to rmax plus a margin for the
    outer labels."""
    clear_polar_grid(plot_item)
    setup_polar_axes(plot_item)
    rmax = float(rmax) if rmax and rmax > 0 else 1.0
    grid_pen = pg.mkPen(pen) if pen is not None else pg.mkPen((120, 120, 120), width=1)
    no_fill = QtGui.QBrush(QtCore.Qt.NoBrush)
    label_color = (110, 110, 110)
    items = []

    for i in range(1, rings + 1):
        rr = rmax * i / rings
        ring = QtWidgets.QGraphicsEllipseItem(-rr, -rr, 2 * rr, 2 * rr)
        ring.setPen(grid_pen)
        ring.setBrush(no_fill)
        plot_item.addItem(ring, ignoreBounds=True)
        items.append(ring)
        label = pg.TextItem(f"{rr:.3g}", color=label_color, anchor=(0.5, 1.0))
        label.setPos(0.0, rr)
        plot_item.addItem(label, ignoreBounds=True)
        items.append(label)

    for deg in range(0, 360, spoke_deg):
        theta = math.radians(deg)
        x2, y2 = rmax * math.cos(theta), rmax * math.sin(theta)
        spoke = QtWidgets.QGraphicsLineItem(0.0, 0.0, x2, y2)
        spoke.setPen(grid_pen)
        plot_item.addItem(spoke, ignoreBounds=True)
        items.append(spoke)
        lx, ly = rmax * 1.12 * math.cos(theta), rmax * 1.12 * math.sin(theta)
        deg_label = pg.TextItem(f"{deg}°", color=label_color, anchor=(0.5, 0.5))
        deg_label.setPos(lx, ly)
        plot_item.addItem(deg_label, ignoreBounds=True)
        items.append(deg_label)

    setattr(plot_item, _GRID_ATTR, items)
    setattr(plot_item, _GRID_RMAX_ATTR, rmax)
    pad = rmax * 1.3
    plot_item.getViewBox().setRange(xRange=(-pad, pad), yRange=(-pad, pad), padding=0)
    return items


def grow_polar_grid(plot_item, rmax, **kwargs):
    """Draw/grow the shared polar grid on plot_item to cover `rmax` --
    what polar.py/polarhistogram.py's setup() actually calls, instead of
    draw_polar_grid directly, so a second polar-family series added to a
    subplot that already has a (smaller) grid grows it rather than
    replacing it with a smaller one. kwargs forwarded to draw_polar_grid
    (rings/spoke_deg/pen)."""
    current = getattr(plot_item, _GRID_RMAX_ATTR, 0.0)
    return draw_polar_grid(plot_item, max(float(rmax), current), **kwargs)
