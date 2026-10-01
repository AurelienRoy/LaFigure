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

"""Three 3-D subplots (axes_type='3d', lafigure/view3d.py) side by side:
a point cloud (`ax.scatter3d`), a trajectory (`ax.line3d`), and a height
field (`ax.surface`) -- see CLAUDE.md's Phase 6 for how a 3-D cell is
just an ordinary grid subplot whose ViewBox renders through an offscreen
GL (or QPainter-fallback) camera, so move/resize/select/undo all keep
working on it like any other subplot.

Only one annotation here, and it's deliberately anchor='figure' (free-
floating over the whole window) rather than anchor='axes' on one of the
3-D cells: CLAUDE.md's Phase 6 notes that an axes-anchored annotation
doesn't yet follow a 3-D cell's camera as it orbits, so anchoring one
there would drift out of place the moment you drag to rotate the view.

Run (from anywhere -- this file adds the repo root to sys.path itself,
since lafigure isn't pip-installed):
    python examples/three_d_scene.py
"""
import os
import sys

import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lafigure
_debug_log = lafigure.enable_debug_mode()
print(f"Debug log: {_debug_log}")


def main():
    app = QtWidgets.QApplication(sys.argv)
    rng = np.random.default_rng(3)

    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- 3D")

    # -- scatter3d: a noisy point cloud around two centers -----------------
    n = 4000
    centers = rng.choice([0, 1], size=n)
    pts = rng.normal(scale=0.5, size=(n, 3))
    pts[centers == 1] += [2.5, 2.5, 1.0]
    ax_scatter = fig.subplot(0, 0, axes_type='3d', title="Point cloud")
    ax_scatter.scatter3d(pts[:, 0], pts[:, 1], z=pts[:, 2], pen=(70, 120, 220), size=3)

    # -- line3d: a helical trajectory ---------------------------------------
    t = np.linspace(0, 6 * np.pi, 600)
    ax_line = fig.subplot(0, 1, axes_type='3d', title="Trajectory")
    ax_line.line3d(np.cos(t), np.sin(t), z=t / 4, name="helix", pen=(200, 60, 60), width=2)

    # -- surface: a height field z = f(x, y) --------------------------------
    xs = np.linspace(-3, 3, 40)
    ys = np.linspace(-3, 3, 40)
    X, Y = np.meshgrid(xs, ys, indexing='ij')
    Z = np.sin(np.hypot(X, Y)) / (0.5 + np.hypot(X, Y))
    ax_surface = fig.subplot(0, 2, axes_type='3d', title="Surface")
    ax_surface.surface(xs, ys, z=Z, colormap='viridis')

    fig._create_annotation('text', 'figure', None, QtCore.QPointF(16, 16), None,
                            text="Drag to orbit, wheel to dolly, right-drag to pan")

    fig.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
