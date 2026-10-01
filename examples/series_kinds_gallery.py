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

"""One figure, six subplots, six different SeriesKinds -- everything
beyond a plain line that ships in lafigure/kinds/. Each `ax.<kind>(...)`
call is the ordinary public entry point (lafigure/axes.py's
Axes.__getattr__ routes any registered kind name to it); nothing here
reaches into a kind module directly.

Run (from anywhere -- this file adds the repo root to sys.path itself,
since lafigure isn't pip-installed):
    python examples/series_kinds_gallery.py
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
    rng = np.random.default_rng(1)

    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- series kinds gallery")

    # -- bar: weekly counts, string categories -> tick labels ------------
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    counts = [12, 19, 8, 24, 15]
    ax_bar = fig.subplot(0, 0, title="Bar")
    ax_bar.bar(days, counts, pen=(40, 90, 160), width=0.6)
    peak_i = int(np.argmax(counts))
    tail = QtCore.QPointF(peak_i - 1.1, counts[peak_i] + 5)
    tip = QtCore.QPointF(peak_i, counts[peak_i])
    fig._create_annotation('textarrow', 'axes', ax_bar.plot_item, tail, tip - tail,
                            text="busiest day")

    # -- errorbar: a measurement with per-point uncertainty ---------------
    x = np.linspace(0, 10, 12)
    y = 3.0 + 0.4 * x + rng.normal(scale=0.6, size=x.size)
    yerr = 0.3 + 0.1 * rng.random(x.size)
    ax_err = fig.subplot(0, 1, title="Errorbar")
    ax_err.errorbar(x, y, yerr=yerr, pen=(180, 70, 70), symbol='o')

    # -- area: a filled curve, baseline at y2 ------------------------------
    t = np.linspace(0, 4 * np.pi, 400)
    ax_area = fig.subplot(0, 2, title="Area")
    ax_area.area(t, 2 + np.sin(t) + 0.15 * t, y2=0, pen=(60, 140, 90))

    # -- stairs: a step function from bin edges + values -------------------
    edges = np.linspace(0, 10, 11)
    steps = np.array([1, 3, 2, 5, 4, 4, 6, 3, 2, 1], dtype=float)
    ax_stairs = fig.subplot(1, 0, title="Stairs")
    ax_stairs.stairs(edges, steps, pen=(150, 100, 200))

    # -- hist: a histogram of raw samples, binned internally ---------------
    samples = rng.normal(loc=5.0, scale=1.5, size=20_000)
    ax_hist = fig.subplot(1, 1, title="Histogram")
    ax_hist.hist(samples, bins=40, pen=(200, 130, 40))
    counts_h, edges_h = np.histogram(samples, bins=40)
    mean_label = QtCore.QPointF(float(samples.mean()), float(counts_h.max()) * 0.92)
    fig._create_annotation('cursor', 'axes', ax_hist.plot_item, mean_label,
                            QtCore.QPointF(2.0, 40.0), text=f"mean={samples.mean():.2f}")

    # -- imshow: a 2-D heatmap with a colorbar ------------------------------
    xs = np.linspace(-3, 3, 120)
    ys = np.linspace(-3, 3, 90)
    X, Y = np.meshgrid(xs, ys)
    Z = np.exp(-((X - 1) ** 2 + (Y + 0.5) ** 2)) + 0.6 * np.exp(-((X + 1.2) ** 2 + (Y - 1) ** 2) / 0.5)
    ax_img = fig.subplot(1, 2, title="Imshow")
    ax_img.imshow(Z, cmap='viridis')
    hot_row, hot_col = np.unravel_index(np.argmax(Z), Z.shape)
    fig._create_annotation('ellipse', 'axes', ax_img.plot_item,
                            QtCore.QPointF(hot_col - 8, hot_row - 8),
                            QtCore.QPointF(16, 16))

    fig.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
