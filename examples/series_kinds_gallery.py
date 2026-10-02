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

"""Visual gallery of every SeriesKind that ships in lafigure/kinds/ --
the plain `line` kind (3 curves on one subplot) plus the 26 others
(the original 6 -- bar, errorbar, area, stairs, hist, imshow -- and the
20 from round 4: loglog/semilogx/semilogy, boxchart/violinplot, polar,
bubblechart/swarmchart/binscatter/spy, quiver/feather/contour,
barh/stem/heatmap/errorband, plot3/bubblechart3d/surface). Previously
two separate scripts (`series_kinds_gallery.py`,
`expanded_series_kinds_gallery.py`); merged into this one so there's a
single gallery to run.

Spread across three figure windows, at most 9 subplots each (a LaFigure
grid is meant to stay readable, not be a 27-cell wall of tiny plots) --
the second and third windows each include 3D kinds (`plot3`,
`bubblechart3d`, `surface`, all `axes_type='3d'`), so 3D is covered
without needing a fourth window.

Every call below is the ordinary public entry point (`ax.<kind>(...)`,
routed by `Axes.__getattr__`/`_plot_kind` -- lafigure/axes.py -- to
whichever SeriesKind registered that name); nothing here reaches into a
`lafigure.kinds.*` module directly. Synthetic data only, sized to stay
fast under the offscreen test platform (CLAUDE.md's own "millions of
points" claim is about the 'line'/'scatter' family -- this gallery isn't
a performance test).

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


def _build_figure_1(rng):
    """line (3 curves), bar, errorbar, area, stairs, hist, semilogy, loglog,
    semilogx."""
    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- series kinds gallery (1/3)")

    # -- line: the plain 'line' kind, 3 curves on one subplot --------------
    t_line = np.linspace(0, 4 * np.pi, 300)
    ax_line = fig.subplot(0, 0, title="Line: 3 curves")
    ax_line.plot(t_line, np.sin(t_line), pen=(60, 120, 200), name="sin(t)")
    ax_line.plot(t_line, 0.7 * np.sin(t_line + np.pi / 4), pen=(200, 100, 60),
                 name="0.7*sin(t+pi/4)")
    ax_line.plot(t_line, np.cos(t_line / 2), pen=(90, 160, 90), name="cos(t/2)")
    ax_line.plot_item.addLegend()

    # -- bar: weekly counts, string categories -> tick labels ------------
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    counts = [12, 19, 8, 24, 15]
    ax_bar = fig.subplot(0, 1, title="Bar")
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
    ax_err = fig.subplot(0, 2, title="Errorbar")
    ax_err.errorbar(x, y, yerr=yerr, pen=(180, 70, 70), symbol='o')

    # -- area: a filled curve, baseline at y2 ------------------------------
    t = np.linspace(0, 4 * np.pi, 400)
    ax_area = fig.subplot(1, 0, title="Area")
    ax_area.area(t, 2 + np.sin(t) + 0.15 * t, y2=0, pen=(60, 140, 90))

    # -- stairs: a step function from bin edges + values -------------------
    edges = np.linspace(0, 10, 11)
    steps = np.array([1, 3, 2, 5, 4, 4, 6, 3, 2, 1], dtype=float)
    ax_stairs = fig.subplot(1, 1, title="Stairs")
    ax_stairs.stairs(edges, steps, pen=(150, 100, 200))

    # -- hist: a histogram of raw samples, binned internally ---------------
    samples = rng.normal(loc=5.0, scale=1.5, size=20_000)
    ax_hist = fig.subplot(1, 2, title="Histogram")
    ax_hist.hist(samples, bins=40, pen=(200, 130, 40))
    counts_h, edges_h = np.histogram(samples, bins=40)
    mean_label = QtCore.QPointF(float(samples.mean()), float(counts_h.max()) * 0.92)
    fig._create_annotation('cursor', 'axes', ax_hist.plot_item, mean_label,
                            QtCore.QPointF(2.0, 40.0), text=f"mean={samples.mean():.2f}")

    # -- semilogy / loglog / semilogx: three views of the same lightly-
    #    damped mechanical 2nd-order system (mass-spring-damper), each one
    #    the classic textbook shape for that axis combination --------------
    wn = 5.0      # natural frequency, rad/s
    zeta = 0.07   # damping ratio (lightly damped -> a visible resonance peak)

    # The step/impulse response's decay envelope, exp(-zeta*wn*t) -- an
    # exponential decay is a straight line on a semilogy plot.
    t_decay = np.linspace(0, 8, 300)
    envelope = np.exp(-zeta * wn * t_decay)
    ax_semilogy = fig.subplot(2, 0, title="semilogy: decay envelope exp(-ζωₙt)")
    ax_semilogy.semilogy(t_decay, envelope, pen=(90, 160, 90))

    # Frequency response magnitude |H(jw)| = wn^2 / sqrt((wn^2-w^2)^2 + (2*zeta*wn*w)^2):
    # flat near 1 well below resonance, a peak at w ~ wn, then rolls off at
    # -40 dB/decade (slope -2) above it -- a straight line on log-log.
    w = np.logspace(-1, 2, 300)
    mag = wn ** 2 / np.sqrt((wn ** 2 - w ** 2) ** 2 + (2 * zeta * wn * w) ** 2)
    ax_loglog = fig.subplot(2, 1, title="loglog: 2nd-order system |H(jw)|")
    ax_loglog.loglog(w, mag, pen=(60, 120, 200))

    # The same frequency response as a Bode magnitude plot (dB vs log(freq)).
    mag_db = 20 * np.log10(mag)
    ax_semilogx = fig.subplot(2, 2, title="semilogx: Bode magnitude (dB)")
    ax_semilogx.semilogx(w, mag_db, pen=(200, 100, 60))

    return fig


def _build_figure_2(rng):
    """imshow, boxchart, violinplot, polar, bubblechart, swarmchart,
    binscatter, spy, plot3 (3D)."""
    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- series kinds gallery (2/3)")

    # -- imshow: a 2-D heatmap with a colorbar ------------------------------
    xs = np.linspace(-3, 3, 120)
    ys = np.linspace(-3, 3, 90)
    X, Y = np.meshgrid(xs, ys)
    Z = np.exp(-((X - 1) ** 2 + (Y + 0.5) ** 2)) + 0.6 * np.exp(-((X + 1.2) ** 2 + (Y - 1) ** 2) / 0.5)
    ax_img = fig.subplot(0, 0, title="Imshow")
    ax_img.imshow(Z, cmap='viridis')
    hot_row, hot_col = np.unravel_index(np.argmax(Z), Z.shape)
    fig._create_annotation('ellipse', 'axes', ax_img.plot_item,
                            QtCore.QPointF(hot_col - 8, hot_row - 8),
                            QtCore.QPointF(16, 16))

    # -- boxchart: quantiles/whiskers/outliers, computed automatically ----
    cats = np.repeat(['A', 'B', 'C'], 80)
    vals = np.concatenate([rng.normal(0, 1, 80), rng.normal(3, 0.5, 80),
                           rng.normal(-1, 2, 80)])
    vals[5] += 15  # one deliberate outlier, shown as a small circle
    ax_box = fig.subplot(0, 1, title="boxchart: quantiles + outlier")
    ax_box.boxchart(cats, vals)

    # -- violinplot: per-category density (KDE) shape ----------------------
    cats_v = np.repeat(['narrow', 'bimodal'], 200)
    narrow = rng.normal(0, 0.6, 200)
    bimodal = np.concatenate([rng.normal(-2, 0.4, 100), rng.normal(2, 0.4, 100)])
    ax_violin = fig.subplot(0, 2, title="violinplot: unimodal vs. bimodal")
    ax_violin.violinplot(cats_v, np.concatenate([narrow, bimodal]))

    # -- polar: a rose curve, with the shared radial grid grown under it --
    theta = np.linspace(0, 2 * np.pi, 400)
    ax_polar = fig.subplot(1, 0, title="polar: rose curve r = cos(3*theta)")
    ax_polar.polar(theta, np.abs(np.cos(3 * theta)), pen=(150, 60, 160))

    # -- bubblechart: size AND color encode two extra numeric columns,
    #    with a live colorbar since color= is given. ------------------------
    n_bub = 60
    bx = rng.uniform(0, 10, n_bub)
    by = rng.uniform(0, 10, n_bub)
    mass = rng.uniform(5, 40, n_bub)
    temp = rng.uniform(0, 100, n_bub)
    ax_bubble = fig.subplot(1, 1, title="bubblechart: size + color + colorbar")
    ax_bubble.bubblechart(bx, by, size=mass, color=temp, cmap='plasma')

    # -- swarmchart: jittered points per category, none overlapping -------
    cats_s = np.repeat(['Mon', 'Tue', 'Wed'], 50)
    vals_s = np.concatenate([rng.normal(5, 1, 50), rng.normal(6, 0.5, 50),
                             rng.normal(4, 1.5, 50)])
    ax_swarm = fig.subplot(1, 2, title="swarmchart: jittered per category")
    ax_swarm.swarmchart(cats_s, vals_s)

    # -- binscatter: a large cloud binned into colored density points -----
    n_bin = 20_000
    binx = rng.normal(0, 2, n_bin)
    biny = binx * 0.5 + rng.normal(0, 1, n_bin)
    ax_bin = fig.subplot(2, 0, title="binscatter: 20k points, binned density")
    ax_bin.binscatter(binx, biny, bins=40)

    # -- spy: the sparsity pattern of a matrix ------------------------------
    size_spy = 50
    mat_spy = np.zeros((size_spy, size_spy))
    np.fill_diagonal(mat_spy, 1)
    idx = rng.integers(0, size_spy, (80, 2))
    mat_spy[idx[:, 0], idx[:, 1]] = 1
    ax_spy = fig.subplot(2, 1, title="spy: nonzero entries of a matrix")
    ax_spy.spy(mat_spy)

    # -- plot3: a 3D kind, axes_type='3d' -----------------------------------
    t3 = np.linspace(0, 6 * np.pi, 400)
    ax_plot3 = fig.subplot(2, 2, axes_type='3d', title="plot3: a 3D trajectory")
    ax_plot3.plot3(np.cos(t3), np.sin(t3), z=t3 / 5, pen=(200, 90, 90), width=2)

    return fig


def _build_figure_3(rng):
    """bubblechart3d (3D), barh, stem, heatmap, errorband, quiver, feather,
    contour, surface (3D)."""
    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- series kinds gallery (3/3)")

    # -- bubblechart3d: a 3D kind, axes_type='3d', size-bucketed -----------
    n_b3 = 400
    b3x = rng.normal(0, 1, n_b3)
    b3y = rng.normal(0, 1, n_b3)
    b3z = rng.normal(0, 1, n_b3)
    b3size = rng.uniform(1, 10, n_b3)
    ax_bubble3d = fig.subplot(0, 0, axes_type='3d', title="bubblechart3d: size-bucketed")
    ax_bubble3d.bubblechart3d(b3x, b3y, z=b3z, size=b3size, pen=(70, 150, 220))

    # -- barh: horizontal bars, category axis on Y --------------------------
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    counts = [12, 19, 8, 24, 15]
    ax_barh = fig.subplot(0, 1, title="barh: horizontal bars")
    ax_barh.barh(days, counts, pen=(40, 110, 160))

    # -- stem: a discrete sampled signal -------------------------------------
    n_stem = 24
    stem_x = np.arange(n_stem)
    stem_y = np.sin(stem_x / 3.0) * np.exp(-stem_x / 30.0)
    ax_stem = fig.subplot(0, 2, title="stem: a discrete signal")
    ax_stem.stem(stem_x, stem_y)

    # -- heatmap: an imshow-style image placed over REAL axis coordinates -
    xs_h = np.linspace(-3, 3, 60)
    ys_h = np.linspace(0, 10, 45)
    Xh, Yh = np.meshgrid(xs_h, ys_h)
    Zh = np.exp(-(Xh ** 2) / 2) * np.sin(Yh)
    ax_heat = fig.subplot(1, 0, title="heatmap: placed on real x/y coordinates")
    ax_heat.heatmap(Zh, x_coords=xs_h, y_coords=ys_h, cmap='viridis')

    # -- errorband: a center line with a shaded uncertainty band -----------
    x_eb = np.linspace(0, 10, 60)
    y_eb = np.sin(x_eb) + 0.1 * x_eb
    yerr_eb = 0.15 + 0.05 * x_eb
    ax_errband = fig.subplot(1, 1, title="errorband: shaded uncertainty")
    ax_errband.errorband(x_eb, y_eb, yerr=yerr_eb, pen=(50, 120, 200))

    # -- quiver: a vector field, autoscaled arrows --------------------------
    gx, gy = np.meshgrid(np.linspace(-2, 2, 10), np.linspace(-2, 2, 10))
    gx, gy = gx.ravel(), gy.ravel()
    gu, gv = -gy, gx  # a simple rotational field
    ax_quiver = fig.subplot(1, 2, title="quiver: a rotational vector field")
    ax_quiver.quiver(gx, gy, u=gu, v=gv)

    # -- feather: successive vectors along one axis (classic wind/current) -
    n_feather = 16
    fx = np.arange(n_feather)
    fu = np.cos(fx / 2.0) * 3
    fv = np.sin(fx / 2.0) * 3 + 1
    ax_feather = fig.subplot(2, 0, title="feather: successive readings")
    ax_feather.feather(fx, u=fu, v=fv)

    # -- contour: marching-squares contour lines of a 2D field -------------
    xs_c = np.linspace(-3, 3, 80)
    ys_c = np.linspace(-3, 3, 80)
    Xc, Yc = np.meshgrid(xs_c, ys_c)
    Zc = (1 - Xc / 2 + Xc ** 5 + Yc ** 3) * np.exp(-Xc ** 2 - Yc ** 2)
    ax_contour = fig.subplot(2, 1, title="contour: marching squares")
    ax_contour.contour(Zc, levels=6, cmap='viridis')

    # -- surface: a 3D kind, axes_type='3d', a rippled height field -------
    xs_s = np.linspace(-5, 5, 40)
    ys_s = np.linspace(-5, 5, 40)
    Xs, Ys = np.meshgrid(xs_s, ys_s, indexing='ij')
    Zs = np.sin(np.sqrt(Xs ** 2 + Ys ** 2))
    ax_surface = fig.subplot(2, 2, axes_type='3d', title="surface: a rippled height field")
    ax_surface.surface(xs_s, ys_s, z=Zs, colormap='viridis')

    return fig


def main():
    app = QtWidgets.QApplication(sys.argv)
    rng = np.random.default_rng(1)

    fig1 = _build_figure_1(rng)
    fig2 = _build_figure_2(rng)
    fig3 = _build_figure_3(rng)

    fig1.show()
    fig2.show()
    fig3.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
