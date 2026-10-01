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

"""One window, one subplot per SeriesKind added in round 4 (wave 2) --
the "what's new" visual demo at a glance: `loglog`/`semilogx`/`semilogy`
(R4-LOG), `boxchart`/`violinplot` (R4-DIST), `polar` (R4-POLAR),
`bubblechart`/`swarmchart`/`binscatter`/`spy` (R4-SCAT), `quiver`/
`feather`/`contour` (R4-FIELD), `barh`/`stem`/`heatmap`/`errorband`
(R4-MISC), `plot3`/`bubblechart3d` (R4-K3D) -- 19 kinds. `series_kinds_
gallery.py` already covers everything from before round 4 (bar, errorbar,
area, stairs, hist, imshow); this file is its round-4 sequel, kept
separate so neither grows unreadably long.

Every call below is the ordinary public entry point
(`ax.<kind>(...)`, routed by `Axes.__getattr__`/`_plot_kind` --
lafigure/axes.py -- to whichever SeriesKind registered that name); nothing
here reaches into a `lafigure.kinds.*` module directly. Synthetic data
only, sized to stay fast under the offscreen test platform (CLAUDE.md's
own "millions of points" claim is about the 'line'/'scatter' family --
this gallery isn't a performance test).

Run (from anywhere -- this file adds the repo root to sys.path itself,
since lafigure isn't pip-installed):
    python examples/expanded_series_kinds_gallery.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lafigure
_debug_log = lafigure.enable_debug_mode()
print(f"Debug log: {_debug_log}")
from pyqtgraph.Qt import QtWidgets


def main():
    app = QtWidgets.QApplication(sys.argv)
    rng = np.random.default_rng(42)

    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- round 4 series kinds gallery")

    # -- loglog / semilogx / semilogy: the subplot's axes go log, not the
    #    data -- a power law y = x^2 is a straight line on a log-log plot,
    #    an exponential decay is a straight line on a semilogy plot. -------
    x_pos = np.linspace(1, 100, 200)
    ax_loglog = fig.subplot(0, 0, title="loglog: y = x^2")
    ax_loglog.loglog(x_pos, x_pos ** 2, pen=(60, 120, 200))

    ax_semilogx = fig.subplot(0, 1, title="semilogx: y = log(x) (linear)")
    ax_semilogx.semilogx(x_pos, np.log(x_pos), pen=(200, 100, 60))

    t_decay = np.linspace(0, 10, 200)
    ax_semilogy = fig.subplot(0, 2, title="semilogy: exponential decay")
    ax_semilogy.semilogy(t_decay, 1000 * np.exp(-0.7 * t_decay) + 1e-3, pen=(90, 160, 90))

    # -- boxchart: quantiles/whiskers/outliers, computed automatically ----
    cats = np.repeat(['A', 'B', 'C'], 80)
    vals = np.concatenate([rng.normal(0, 1, 80), rng.normal(3, 0.5, 80),
                           rng.normal(-1, 2, 80)])
    vals[5] += 15  # one deliberate outlier, shown as a small circle
    ax_box = fig.subplot(1, 0, title="boxchart: quantiles + outlier")
    ax_box.boxchart(cats, vals)

    # -- violinplot: per-category density (KDE) shape ----------------------
    cats_v = np.repeat(['narrow', 'bimodal'], 200)
    narrow = rng.normal(0, 0.6, 200)
    bimodal = np.concatenate([rng.normal(-2, 0.4, 100), rng.normal(2, 0.4, 100)])
    ax_violin = fig.subplot(1, 1, title="violinplot: unimodal vs. bimodal")
    ax_violin.violinplot(cats_v, np.concatenate([narrow, bimodal]))

    # -- polar: a rose curve, with the shared radial grid grown under it --
    theta = np.linspace(0, 2 * np.pi, 400)
    ax_polar = fig.subplot(1, 2, title="polar: rose curve r = cos(3*theta)")
    ax_polar.polar(theta, np.abs(np.cos(3 * theta)), pen=(150, 60, 160))

    # -- bubblechart: size AND color encode two extra numeric columns,
    #    with a live colorbar since color= is given. ------------------------
    n_bub = 60
    bx = rng.uniform(0, 10, n_bub)
    by = rng.uniform(0, 10, n_bub)
    mass = rng.uniform(5, 40, n_bub)
    temp = rng.uniform(0, 100, n_bub)
    ax_bubble = fig.subplot(2, 0, title="bubblechart: size + color + colorbar")
    ax_bubble.bubblechart(bx, by, size=mass, color=temp, cmap='plasma')

    # -- swarmchart: jittered points per category, none overlapping -------
    cats_s = np.repeat(['Mon', 'Tue', 'Wed'], 50)
    vals_s = np.concatenate([rng.normal(5, 1, 50), rng.normal(6, 0.5, 50),
                             rng.normal(4, 1.5, 50)])
    ax_swarm = fig.subplot(2, 1, title="swarmchart: jittered per category")
    ax_swarm.swarmchart(cats_s, vals_s)

    # -- binscatter: a large cloud binned into colored density points -----
    n_bin = 20_000
    binx = rng.normal(0, 2, n_bin)
    biny = binx * 0.5 + rng.normal(0, 1, n_bin)
    ax_bin = fig.subplot(2, 2, title="binscatter: 20k points, binned density")
    ax_bin.binscatter(binx, biny, bins=40)

    # -- spy: the sparsity pattern of a matrix ------------------------------
    size_spy = 50
    mat_spy = np.zeros((size_spy, size_spy))
    np.fill_diagonal(mat_spy, 1)
    idx = rng.integers(0, size_spy, (80, 2))
    mat_spy[idx[:, 0], idx[:, 1]] = 1
    ax_spy = fig.subplot(3, 0, title="spy: nonzero entries of a matrix")
    ax_spy.spy(mat_spy)

    # -- plot3 / bubblechart3d: 3D kinds, axes_type='3d' --------------------
    t3 = np.linspace(0, 6 * np.pi, 400)
    ax_plot3 = fig.subplot(3, 1, axes_type='3d', title="plot3: a 3D trajectory")
    ax_plot3.plot3(np.cos(t3), np.sin(t3), z=t3 / 5, pen=(200, 90, 90), width=2)

    n_b3 = 400
    b3x = rng.normal(0, 1, n_b3)
    b3y = rng.normal(0, 1, n_b3)
    b3z = rng.normal(0, 1, n_b3)
    b3size = rng.uniform(1, 10, n_b3)
    ax_bubble3d = fig.subplot(3, 2, axes_type='3d', title="bubblechart3d: size-bucketed")
    ax_bubble3d.bubblechart3d(b3x, b3y, z=b3z, size=b3size, pen=(70, 150, 220))

    # -- barh: horizontal bars, category axis on Y --------------------------
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    counts = [12, 19, 8, 24, 15]
    ax_barh = fig.subplot(4, 0, title="barh: horizontal bars")
    ax_barh.barh(days, counts, pen=(40, 110, 160))

    # -- stem: a discrete sampled signal -------------------------------------
    n_stem = 24
    stem_x = np.arange(n_stem)
    stem_y = np.sin(stem_x / 3.0) * np.exp(-stem_x / 30.0)
    ax_stem = fig.subplot(4, 1, title="stem: a discrete signal")
    ax_stem.stem(stem_x, stem_y)

    # -- heatmap: an imshow-style image placed over REAL axis coordinates -
    xs_h = np.linspace(-3, 3, 60)
    ys_h = np.linspace(0, 10, 45)
    Xh, Yh = np.meshgrid(xs_h, ys_h)
    Zh = np.exp(-(Xh ** 2) / 2) * np.sin(Yh)
    ax_heat = fig.subplot(4, 2, title="heatmap: placed on real x/y coordinates")
    ax_heat.heatmap(Zh, x_coords=xs_h, y_coords=ys_h, cmap='viridis')

    # -- errorband: a center line with a shaded uncertainty band -----------
    x_eb = np.linspace(0, 10, 60)
    y_eb = np.sin(x_eb) + 0.1 * x_eb
    yerr_eb = 0.15 + 0.05 * x_eb
    ax_errband = fig.subplot(5, 0, title="errorband: shaded uncertainty")
    ax_errband.errorband(x_eb, y_eb, yerr=yerr_eb, pen=(50, 120, 200))

    # -- quiver: a vector field, autoscaled arrows --------------------------
    gx, gy = np.meshgrid(np.linspace(-2, 2, 10), np.linspace(-2, 2, 10))
    gx, gy = gx.ravel(), gy.ravel()
    gu, gv = -gy, gx  # a simple rotational field
    ax_quiver = fig.subplot(5, 1, title="quiver: a rotational vector field")
    ax_quiver.quiver(gx, gy, u=gu, v=gv)

    # -- feather: successive vectors along one axis (classic wind/current) -
    n_feather = 16
    fx = np.arange(n_feather)
    fu = np.cos(fx / 2.0) * 3
    fv = np.sin(fx / 2.0) * 3 + 1
    ax_feather = fig.subplot(5, 2, title="feather: successive readings")
    ax_feather.feather(fx, u=fu, v=fv)

    # -- contour: marching-squares contour lines of a 2D field -------------
    xs_c = np.linspace(-3, 3, 80)
    ys_c = np.linspace(-3, 3, 80)
    Xc, Yc = np.meshgrid(xs_c, ys_c)
    Zc = (1 - Xc / 2 + Xc ** 5 + Yc ** 3) * np.exp(-Xc ** 2 - Yc ** 2)
    ax_contour = fig.subplot(6, 0, title="contour: marching squares")
    ax_contour.contour(Zc, levels=6, cmap='viridis')

    fig.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
