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

"""ax.scatter3d(x, y, z=z, size=4, pen=color) -- points in a 3D cell, or
ax.scatter3d(source, x='a', y='b', z='c') for three columns of a DataSource
(then brushing links its rows with every other series of that source, 2D
or 3D). Only on a subplot made with axes_type='3d' (see view3d.py for how
the cell draws it and brushes it through the camera projection).

z is a keyword because Axes._plot_kind routes exactly two positional
coordinates (x, y) to every kind."""
import numpy as np

from ..series import register_series_kind
from ..view3d import Kind3D, Primitive, Series3DItem

DEFAULT_SIZE = 4


class Scatter3DItem(Series3DItem):
    def _build_primitives(self, xyz):
        return [Primitive('points', xyz, self.color(), self.size)]


class Scatter3DKind(Kind3D):
    name = 'scatter3d'

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               z=None, size=DEFAULT_SIZE):
        self._check_plot(plot_item)
        x = self._column(x, None, None, None, 'x')
        y = self._column(y, None, None, len(x), 'y')
        z = self._column(z, source, rows, len(x), 'z')
        item = Scatter3DItem(np.column_stack([x, y, z]), pen=pen, name=name, size=size,
                             source=source)
        plot_item.addItem(item, ignoreBounds=True)
        return item

    def to_dict(self, item):
        xyz = np.array(item.positions(), copy=True)
        return {'x': xyz[:, 0], 'y': xyz[:, 1], 'pen': item.opts['pen'], 'name': item.name(),
                'style': {'z': xyz[:, 2], 'size': item.size}}


register_series_kind(Scatter3DKind())
