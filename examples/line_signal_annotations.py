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

"""A single-subplot line example: a damped oscillation with its envelope,
a legend, and three annotations dropped onto it from code.

Shows the plain `fig.subplot(...).plot(...)` API (lafigure/axes.py) plus
`ax.plot_item`, which is a real pyqtgraph PlotItem -- so ordinary
pyqtgraph calls like `setLabel`/`addLegend` work on it directly, no
LaFigure-specific wrapper needed.

Annotations are normally placed interactively (pick a shape from the
toolbar's "Annotate" dropdown, then click or drag it into place -- see
CLAUDE.md's "Annotations" feature entry). A script that wants to drop one
in without a mouse can call the same `LaFigure._create_annotation(kind,
anchor, parent_plot, p0, p1_local, text=...)` the toolbar gesture itself
ends up calling; it's underscore-prefixed because there is not yet a
dedicated public constructor for non-interactive placement, but it is the
one real, undoable annotation-creation path in the app, used exactly this
way by this project's own test suite. `anchor='axes'` positions p0/p1 in
the subplot's DATA coordinates (so the annotation pans/zooms with the
curve); `anchor='figure'` positions them in scene pixels, independent of
any subplot.

Run (from anywhere -- this file adds the repo root to sys.path itself,
since lafigure isn't pip-installed):
    python examples/line_signal_annotations.py
"""
import os
import sys

import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lafigure


def main():
    app = QtWidgets.QApplication(sys.argv)

    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- damped oscillation")

    t = np.linspace(0, 20, 4000)
    envelope = np.exp(-0.15 * t)
    y = envelope * np.sin(2 * np.pi * 0.8 * t)

    ax = fig.subplot(0, 0, title="Damped oscillation")
    ax.plot(t, envelope, pen=(180, 180, 180), name="envelope")
    ax.plot(t, -envelope, pen=(180, 180, 180), name="_nolegend_")
    ax.plot(t, y, pen=(50, 90, 200), name="signal")
    ax.plot_item.setLabel('bottom', "time", units='s')
    ax.plot_item.setLabel('left', "amplitude")
    ax.plot_item.addLegend()

    # -- a textarrow pointing at the first peak --------------------------
    # In _create_annotation, p0 is the arrow's TAIL (where the text sits)
    # and p0 + p1_local is its TIP -- so the tip is placed exactly on the
    # peak by working backwards from it.
    peak_idx = int(np.argmax(y[t < 2]))
    peak = QtCore.QPointF(float(t[peak_idx]), float(y[peak_idx]))
    tail = QtCore.QPointF(peak.x() + 2.7, peak.y() + 0.35)
    fig._create_annotation('textarrow', 'axes', ax.plot_item, tail, peak - tail,
                            text="first peak")

    # -- a data-cursor readout further along the curve -------------------
    cursor_idx = int(np.argmin(np.abs(t - 9.0)))
    cursor_pt = QtCore.QPointF(float(t[cursor_idx]), float(y[cursor_idx]))
    fig._create_annotation('cursor', 'axes', ax.plot_item, cursor_pt,
                            QtCore.QPointF(1.5, 0.25),
                            text=f"t={cursor_pt.x():.2f}s, y={cursor_pt.y():.3f}")

    # -- a rect highlighting the settled tail of the signal ---------------
    settle_lo, settle_hi = 15.0, 20.0
    fig._create_annotation('rect', 'axes', ax.plot_item,
                            QtCore.QPointF(settle_lo, -0.08),
                            QtCore.QPointF(settle_hi - settle_lo, 0.16))

    fig.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
