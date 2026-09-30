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

"""Three subplots, three different views of the SAME rows, linked through
one shared `lafigure.DataSource` (lafigure/datasource.py) -- exactly how a
customer wires up cross-filtering: build one DataSource, then pass it as
the first argument to `ax.<kind>(source, x='col', y='col')` on as many
subplots as you like. Nothing about the subplots themselves needs to know
they're linked; brushing does, because it looks up rows on the shared
source rather than positions on one plot.

This script only *sets up* the link -- try it live once the window is
open: click the toolbar's Brush-mode button (or press the shortcut shown
under the "?" help dialog), then drag a rectangle over a handful of points
in either scatter. The same underlying rows highlight in both scatters
*and* in the histogram, because all three series were built from the one
`source` below.

Run (from anywhere -- this file adds the repo root to sys.path itself,
since lafigure isn't pip-installed):
    python examples/linked_brushing_scatter.py
"""
import os
import sys

import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lafigure
_debug_log = lafigure.enable_debug_mode()
print(f"Debug log: {_debug_log}")


def main():
    app = QtWidgets.QApplication(sys.argv)
    rng = np.random.default_rng(7)

    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- linked brushing")

    n = 8000
    a = rng.normal(size=n)
    b = 0.6 * a + rng.normal(scale=0.5, size=n)
    # A visible group of outliers so there's something worth circling.
    outliers = a > 2.2
    source = lafigure.DataSource({'a': a, 'b': b})

    ax1 = fig.subplot(0, 0, title="b vs a (brush me)")
    ax1.scatter(source, x='a', y='b', name="points", size=4,
                symbolBrush=pg.mkBrush(80, 140, 220, 140), symbolPen=None)

    ax2 = fig.subplot(0, 1, title="a vs b -- same rows")
    ax2.scatter(source, x='b', y='a', name="points", size=4,
                symbolBrush=pg.mkBrush(220, 120, 80, 140), symbolPen=None)

    ax3 = fig.subplot(1, 0, colspan=2, title="Distribution of a")
    ax3.hist(a, bins=50, pen=(90, 90, 90))

    # Circle the outlier cluster on the first scatter and point to it --
    # both anchor='axes', so the shapes pan/zoom together with the data.
    lo_x, hi_x = float(a[outliers].min()), float(a[outliers].max())
    lo_y, hi_y = float(b[outliers].min()), float(b[outliers].max())
    fig._create_annotation('ellipse', 'axes', ax1.plot_item,
                            QtCore.QPointF(lo_x - 0.1, lo_y - 0.1),
                            QtCore.QPointF((hi_x - lo_x) + 0.2, (hi_y - lo_y) + 0.2))
    label_pos = QtCore.QPointF(hi_x + 0.6, hi_y - 0.3)
    fig._create_annotation('textarrow', 'axes', ax1.plot_item, label_pos,
                            QtCore.QPointF(lo_x - 0.3, (lo_y + hi_y) / 2) - label_pos,
                            text=f"{int(outliers.sum())} outliers (a > 2.2)")

    fig.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
