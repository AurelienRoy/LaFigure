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

"""ax.plot3(x, y, z=z, pen=color, width=1.5) -- MATLAB's name for a 3D
line plot (a polyline through 3D points / a trajectory), or
ax.plot3(source, x='a', y='b', z='c') for three columns of a DataSource.

A `_base.DerivedKind` on the already-registered `'line3d'` kind (round 4's
"re-use the same base function, base plots" rule) -- this module adds
nothing new: same item (kinds/line3d.py's Line3DItem), same create/to_dict/
get_xy/set_xy/capabilities, same brushing-by-vertex-row behavior, same
"only on an axes_type='3d' subplot" restriction (enforced by line3d's own
create() via Kind3D._check_plot). It exists purely so a MATLAB user finds
the familiar name `plot3` next to `scatter3d`/`line3d`/`surface`.

z is a keyword because Axes._plot_kind routes exactly two positional
coordinates (x, y) to every kind, same as scatter3d/line3d/bubblechart3d.
"""
from ..series import register_series_kind
from ._base import DerivedKind


class Plot3Kind(DerivedKind):
    name = 'plot3'
    base = 'line3d'


register_series_kind(Plot3Kind())
