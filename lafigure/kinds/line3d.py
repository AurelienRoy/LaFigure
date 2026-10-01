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

"""ax.line3d(x, y, z=z, width=1, pen=color) -- a polyline through 3D
points (a trajectory), or ax.line3d(source, x='a', y='b', z='c'). Its
vertices are its rows: brushing selects vertices, like a 2D line's samples.
Hidden/filtered rows are left out and their neighbors joined, as a 2D
line of the same rows draws them. Only on an axes_type='3d' subplot."""
import numpy as np

from ..series import register_series_kind
from ..view3d import Kind3D, Primitive, Series3DItem

DEFAULT_WIDTH = 1.5


class Line3DItem(Series3DItem):
    def _build_primitives(self, xyz):
        return [Primitive('line_strip', xyz, self.color(), self.size)]


class Line3DKind(Kind3D):
    name = 'line3d'

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None,
               z=None, width=DEFAULT_WIDTH):
        self._check_plot(plot_item)
        x = self._column(x, None, None, None, 'x')
        y = self._column(y, None, None, len(x), 'y')
        z = self._column(z, source, rows, len(x), 'z')
        item = Line3DItem(np.column_stack([x, y, z]), pen=pen, name=name, size=width,
                          source=source)
        plot_item.addItem(item, ignoreBounds=True)
        return item

    def to_dict(self, item):
        xyz = np.array(item.positions(), copy=True)
        return {'x': xyz[:, 0], 'y': xyz[:, 1], 'pen': item.opts['pen'], 'name': item.name(),
                'style': {'z': xyz[:, 2], 'width': item.size}}


register_series_kind(Line3DKind())
