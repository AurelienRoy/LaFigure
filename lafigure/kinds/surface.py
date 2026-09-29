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

"""ax.surface(x, y, z=Z, colormap='viridis') -- a height field z = f(x, y)
on a grid: x (nx,) and y (ny,) the grid lines (None = 0..n-1), Z (nx, ny).
Drawn as triangles (two per grid quad, like the WP-G spike's surface),
colored by height through a pyqtgraph colormap, or in one color if `pen`
is given. Only on an axes_type='3d' subplot.

Not brushable: a surface's vertices are grid samples, not rows of a
DataSource that another plot could share. get_xy is (vertices (nx*ny, 3),
None), grid order (x-major); set_xy with that shape keeps the grid."""
import numpy as np
import pyqtgraph as pg

from ..series import register_series_kind
from ..view3d import Kind3D, Primitive, Series3DItem

DEFAULT_COLORMAP = 'viridis'


class SurfaceItem(Series3DItem):
    def __init__(self, grid, pen=None, name=None, colormap=DEFAULT_COLORMAP):
        super().__init__(grid.reshape(-1, 3), pen=pen, name=name)
        self.grid_shape = grid.shape[:2]
        self.uniform = pen is not None
        self.colormap = colormap

    def grid(self):
        return self.positions().reshape(self.grid_shape + (3,))

    def _build_primitives(self, xyz):
        if len(xyz) != self.grid_shape[0] * self.grid_shape[1] or min(self.grid_shape) < 2:
            return [Primitive('points', xyz, self.color(), 2.0)]
        P = xyz.reshape(self.grid_shape + (3,))
        a, b, c, d = P[:-1, :-1], P[1:, :-1], P[1:, 1:], P[:-1, 1:]
        tri = np.stack([a, b, c, a, c, d], axis=2).reshape(-1, 3)
        if self.uniform:
            color = self.color()
        else:
            z = tri[:, 2]
            span = np.nanmax(z) - np.nanmin(z)
            t = (z - np.nanmin(z)) / span if span > 0 else np.zeros_like(z)
            color = pg.colormap.get(self.colormap).map(np.nan_to_num(t), mode='float')
        return [Primitive('triangles', tri, color)]


class SurfaceKind(Kind3D):
    name = 'surface'
    capabilities = frozenset({'copy'})

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               z=None, colormap=DEFAULT_COLORMAP):
        self._check_plot(plot_item)
        if z is None:
            raise TypeError("surface(x, y, z=Z): the height grid Z is required")
        Z = np.asarray(z, dtype=float)
        if Z.ndim != 2:
            raise ValueError(f"surface: Z must be 2-D (nx, ny), got shape {Z.shape}")
        nx, ny = Z.shape
        x = np.arange(nx, dtype=float) if x is None else np.asarray(x, dtype=float).ravel()
        y = np.arange(ny, dtype=float) if y is None else np.asarray(y, dtype=float).ravel()
        if len(x) != nx or len(y) != ny:
            raise ValueError(f"surface: x has {len(x)} and y {len(y)} values for a {Z.shape} Z")
        X, Y = np.meshgrid(x, y, indexing='ij')
        item = SurfaceItem(np.stack([X, Y, Z], axis=-1), pen=pen, name=name, colormap=colormap)
        plot_item.addItem(item, ignoreBounds=True)
        return item

    def set_xy(self, item, x, y):
        if y is None and len(np.asarray(x).reshape(-1, 3)) != len(item.positions()):
            raise ValueError("surface: new vertices must keep the grid's size")
        super().set_xy(item, x, y)

    def to_dict(self, item):
        grid = np.array(item.grid(), copy=True)
        return {'x': grid[:, 0, 0], 'y': grid[0, :, 1], 'pen': item.opts['pen'] if item.uniform else None,
                'name': item.name(), 'style': {'z': grid[:, :, 2], 'colormap': item.colormap}}


register_series_kind(SurfaceKind())
