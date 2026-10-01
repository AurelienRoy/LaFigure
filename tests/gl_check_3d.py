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

"""Real-GL check of a 3D cell, run in a child process by test_3d.py's
test_gl_render_matches_the_projection_on_a_real_context (not collected by
run_tests.py itself: no test_ prefix).

Must run on the NATIVE Qt platform -- QT_QPA_PLATFORM=offscreen has no GL
on Windows (CLAUDE.md bug #10). Nothing is shown on screen
(WA_DontShowOnScreen). Uses the shipped configuration (useOpenGL=True, so
the viewport is a QOpenGLWidget with its own context, switched against the
3D renderer's on every render -- the spike's condition 2).

Checks, like the WP-G spike's check_projection but through LaFigure: a
4x4x4 lattice of black points on a 3D cell renders through GL ('gl'
backend), every point's numpy projection lands on a dark pixel of the
rendered image, still after a real mouse orbit (QMouseEvents to the
viewport) -- and the points are really composited into the window (grab).

Exit 0 + "GL-OK" on success, 1 on a mismatch, 2 + "NO-GL" when no GL
context can be created here.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop('QT_QPA_PLATFORM', None)

import numpy as np  # noqa: E402
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])

import lafigure as m  # noqa: E402  (sets useOpenGL=True, as shipped)
from lafigure import view3d  # noqa: E402


def dark_hits(img, sx, sy, scale):
    img = img.convertToFormat(QtGui.QImage.Format_RGB32)
    hits = 0
    for x, y in zip(sx, sy):
        ix, iy = int(x * scale), int(y * scale)
        dark = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if 0 <= ix + dx < img.width() and 0 <= iy + dy < img.height():
                    dark |= QtGui.QColor(img.pixel(ix + dx, iy + dy)).lightness() < 128
        hits += dark
    return hits


def mouse(f, etype, scene_pt, buttons, button=QtCore.Qt.LeftButton):
    view = f.layout_widget
    local = QtCore.QPointF(view.mapFromScene(scene_pt))
    global_pos = QtCore.QPointF(view.viewport().mapToGlobal(local.toPoint()))
    ev = QtGui.QMouseEvent(etype, local, local, global_pos, button, buttons, QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(view.viewport(), ev)
    app.processEvents()


def check(f, vb, item, label):
    vb.render_now()
    app.processEvents()
    if vb.last_backend != 'gl':
        print(f"FAIL {label}: rendered by {vb.last_backend!r}, not GL "
              f"({view3d._gl['error']})")
        return False
    img = vb.image_item.pixmap().toImage()
    scale = img.width() / vb.width()
    sx, sy, front = vb.projected(item)
    inside = front & (sx >= 1) & (sx < vb.width() - 1) & (sy >= 1) & (sy < vb.height() - 1)
    hits = dark_hits(img, sx[inside], sy[inside], scale)
    # Composited into the window: sample the grabbed window at the points.
    shot = f.layout_widget.grab().toImage()
    dpr = shot.devicePixelRatio()
    view = f.layout_widget
    scene_pts = [vb.mapViewToScene(QtCore.QPointF(x, y)) for x, y in zip(sx[inside], sy[inside])]
    wx = [view.mapFromScene(p).x() for p in scene_pts]
    wy = [view.mapFromScene(p).y() for p in scene_pts]
    shot_hits = dark_hits(shot, wx, wy, dpr)
    n = int(inside.sum())
    print(f"{label}: {hits}/{n} projected points on dark image pixels, "
          f"{shot_hits}/{n} in the grabbed window")
    return n > 0 and hits == n and shot_hits == n


def main():
    if not QtGui.QOpenGLContext().create():
        print(f"NO-GL: QOpenGLContext.create() failed on platform {app.platformName()!r}")
        return 2
    f = m.LaFigure(empty=True)
    f.setAttribute(QtCore.Qt.WA_DontShowOnScreen)
    f.resize(900, 700)
    f.show()
    app.processEvents()
    ax = f.subplot(0, 0, axes_type='3d')
    g = np.arange(-3.0, 3.1, 2.0)
    pts = np.array(np.meshgrid(g, g, g, indexing='ij')).reshape(3, -1).T
    s = ax.scatter3d(pts[:, 0], pts[:, 1], z=pts[:, 2], pen=(0, 0, 0), size=5)
    vb = ax.plot_item.getViewBox()
    app.processEvents()
    ok = check(f, vb, s.item, "initial")
    renderer = view3d.get_gl_renderer()
    print("GL:", renderer.info if renderer is not None else None)
    f.set_interaction_mode('hand')
    az = vb.camera.azimuth
    c = vb.sceneBoundingRect().center()
    L, NO = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
    mouse(f, QtCore.QEvent.MouseButtonPress, c, L)
    for t in (0.25, 0.5, 0.75, 1.0):
        mouse(f, QtCore.QEvent.MouseMove, c + QtCore.QPointF(120 * t, -40 * t), L, button=NO)
    mouse(f, QtCore.QEvent.MouseButtonRelease, c + QtCore.QPointF(120, -40), NO)
    if vb.camera.azimuth == az:
        print("FAIL: the real mouse drag did not orbit the camera")
        ok = False
    ok = check(f, vb, s.item, "after a real left-drag orbit") and ok
    f.close()
    if ok:
        print("GL-OK")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
