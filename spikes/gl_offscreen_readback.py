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

"""Spike (WP-G): can a 3D grid cell render offscreen + read back fast enough?

Roadmap Phase 6, "Option A": a 3D cell is a normal grid item that renders
an offscreen GL view to an image each frame and forwards mouse input to
its camera. This script measures the per-frame cost of exactly that
round trip -- draw into a framebuffer object, read it back as a QImage,
convert to the QPixmap a QGraphicsPixmapItem would display -- for 3D
scatter clouds and a surface, at two cell sizes. Standalone: nothing in
the lafigure package is imported or touched.

Why raw Qt GL and not pyqtgraph.opengl.GLViewWidget: pyqtgraph.opengl
needs PyOpenGL, which the session that wrote this could not install (no
PyPI access). PyQt5 ships its own GL bindings (QOpenGLContext,
QOffscreenSurface, QOpenGLFramebufferObject, QOpenGLShaderProgram,
QOpenGLBuffer, versionFunctions()), so the renderer below reproduces what
GLScatterPlotItem.paint() does -- VBOs uploaded once, one
glDrawArrays(GL_POINTS) per frame -- and what GLViewWidget.grabFramebuffer()
does -- FBO -> glReadPixels -> QImage. The Camera class reproduces
GLViewWidget's viewMatrix()/projectionMatrix()/orbit()/pan()/wheelEvent()
math in numpy, checked against Qt's own QMatrix4x4 calls at startup.

Run:  python spikes/gl_offscreen_readback.py        (see spikes/README.md)
"""

import argparse
import os
import statistics
import sys
import time
from math import cos, radians, sin, tan

import numpy as np

# GL enums used below (no PyOpenGL, so no GL.GL_* names).
GL_POINTS = 0x0000
GL_TRIANGLES = 0x0004
GL_FLOAT = 0x1406
GL_DEPTH_TEST = 0x0B71
GL_DEPTH_BUFFER_BIT = 0x0100
GL_COLOR_BUFFER_BIT = 0x4000
GL_PROGRAM_POINT_SIZE = 0x8642
GL_TEXTURE_2D = 0x0DE1
GL_RGBA8 = 0x8058
GL_VENDOR, GL_RENDERER, GL_VERSION = 0x1F00, 0x1F01, 0x1F02

VERTEX_SHADER = """
#version 120
attribute vec3 a_pos;
attribute vec4 a_color;
uniform mat4 u_mvp;
uniform float u_point_size;
varying vec4 v_color;
void main() {
    gl_Position = u_mvp * vec4(a_pos, 1.0);
    gl_PointSize = u_point_size;
    v_color = a_color;
}
"""

FRAGMENT_SHADER = """
#version 120
varying vec4 v_color;
void main() {
    gl_FragColor = v_color;
}
"""


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--points", type=int, nargs="+",
                   default=[10_000, 100_000, 1_000_000],
                   help="scatter point counts to benchmark")
    p.add_argument("--surface", type=int, default=500,
                   help="surface grid side N (N x N vertices); 0 to skip")
    p.add_argument("--sizes", nargs="+", default=["800x600", "1600x1000"],
                   help="offscreen framebuffer sizes, WxH")
    p.add_argument("--frames", type=int, default=60,
                   help="timed frames per (scene, size)")
    p.add_argument("--point-size", type=float, default=4.0,
                   help="scatter point size in pixels")
    p.add_argument("--software", action="store_true",
                   help="force Qt's bundled Mesa llvmpipe (QT_OPENGL=software)")
    p.add_argument("--platform", default=None,
                   help="set QT_QPA_PLATFORM before creating the app")
    p.add_argument("--brush-points", type=int, default=1_000_000,
                   help="point count for the numpy projection timing")
    p.add_argument("--save-png", metavar="DIR", default=None,
                   help="save each scene's last frame as a PNG in DIR, to "
                        "check by eye that something real was rendered")
    p.add_argument("--in-scene", type=int, nargs="*", default=[1, 4],
                   metavar="K",
                   help="also time K 3D cells inside a real pyqtgraph "
                        "GraphicsLayoutWidget (useOpenGL=True); pass the "
                        "flag with no value to skip")
    p.add_argument("--in-scene-points", type=int, default=1_000_000,
                   help="scatter points per 3D cell for --in-scene")
    return p.parse_args()


# --------------------------------------------------------------- camera

def _rotation(angle_deg, x, y, z):
    """4x4 rotation matching QMatrix4x4.rotate(angle, x, y, z)."""
    a = radians(angle_deg)
    n = np.array([x, y, z], float)
    x, y, z = n / np.linalg.norm(n)
    c, s = cos(a), sin(a)
    C = 1 - c
    m = np.eye(4)
    m[:3, :3] = [[x * x * C + c, x * y * C - z * s, x * z * C + y * s],
                 [y * x * C + z * s, y * y * C + c, y * z * C - x * s],
                 [z * x * C - y * s, z * y * C + x * s, z * z * C + c]]
    return m


def _translation(x, y, z):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


class Camera:
    """GLViewWidget's default ('euler') camera, in numpy.

    Same opts and the same formulas as pyqtgraph 0.14's GLViewWidget:
    viewMatrix(), projectionMatrix() for the full viewport, orbit(),
    pan(relative='view-upright'), wheelEvent() and mouseMoveEvent()'s
    button mapping. Plain numpy so the brush projection below uses the
    very matrices the renderer uploads.
    """

    def __init__(self, center=(0.0, 0.0, 0.0), distance=10.0,
                 elevation=30.0, azimuth=45.0, fov=60.0):
        self.center = np.array(center, float)
        self.distance = distance
        self.elevation = elevation
        self.azimuth = azimuth
        self.fov = fov

    # --- the camera-update API a mouse-forwarding cell would call
    def orbit(self, azim, elev):
        self.azimuth += azim
        self.elevation = float(np.clip(self.elevation + elev, -90.0, 90.0))

    def pan(self, dx, dy, dz, width):
        """GLViewWidget.pan(..., relative='view-upright')."""
        c_vec = self.center - self.camera_position()
        dist = np.linalg.norm(c_vec)
        x_scale = dist * 2.0 * tan(0.5 * radians(self.fov)) / width
        z_vec = np.array([0.0, 0.0, 1.0])
        x_vec = np.cross(z_vec, c_vec)
        x_vec /= np.linalg.norm(x_vec)
        y_vec = np.cross(x_vec, z_vec)
        y_vec /= np.linalg.norm(y_vec)
        self.center = self.center + (x_vec * dx + y_vec * dy
                                     + z_vec * dz) * x_scale

    def wheel(self, delta):
        """GLViewWidget.wheelEvent without Ctrl: dolly in/out."""
        self.distance *= 0.999 ** delta

    def drag(self, dx, dy, button, width):
        """GLViewWidget.mouseMoveEvent's mapping of a mouse delta (px)."""
        if button == "left":
            self.orbit(-dx, dy)
        elif button == "middle":
            self.pan(dx, dy, 0, width)

    # --- matrices
    def camera_position(self):
        return np.linalg.inv(self.view_matrix())[:3, 3]

    def view_matrix(self):
        return (_translation(0.0, 0.0, -self.distance)
                @ _rotation(self.elevation - 90, 1, 0, 0)
                @ _rotation(self.azimuth + 90, 0, 0, -1)
                @ _translation(*(-self.center)))

    def projection_matrix(self, w, h):
        near, far = self.distance * 0.001, self.distance * 1000.0
        r = near * tan(0.5 * radians(self.fov))
        t = r * h / w
        left, right, bottom, top = -r, r, -t, t
        m = np.zeros((4, 4))
        m[0, 0] = 2 * near / (right - left)
        m[0, 2] = (right + left) / (right - left)
        m[1, 1] = 2 * near / (top - bottom)
        m[1, 2] = (top + bottom) / (top - bottom)
        m[2, 2] = -(far + near) / (far - near)
        m[2, 3] = -2 * far * near / (far - near)
        m[3, 2] = -1.0
        return m

    def mvp(self, w, h):
        return self.projection_matrix(w, h) @ self.view_matrix()

    def qt_mvp(self, w, h):
        """Same MVP built with GLViewWidget's literal QMatrix4x4 calls."""
        from PyQt5 import QtGui
        view = QtGui.QMatrix4x4()
        view.translate(0.0, 0.0, -self.distance)
        view.rotate(self.elevation - 90, 1, 0, 0)
        view.rotate(self.azimuth + 90, 0, 0, -1)
        view.translate(*(-self.center))
        near, far = self.distance * 0.001, self.distance * 1000.0
        r = near * tan(0.5 * radians(self.fov))
        t = r * h / w
        proj = QtGui.QMatrix4x4()
        proj.frustum(-r, r, -t, t, near, far)
        m = proj * view
        return np.array(m.data()).reshape(4, 4).T   # column-major -> rows


def project_to_screen(mvp, x, y, z, w, h):
    """Numpy projection of 3D points to pixel coords (top-left origin).

    Returns (sx, sy, in_front). Only the x, y, w rows of the MVP are
    needed -- depth isn't, for a rectangle brush.
    """
    m = mvp
    cx = m[0, 0] * x + m[0, 1] * y + m[0, 2] * z + m[0, 3]
    cy = m[1, 0] * x + m[1, 1] * y + m[1, 2] * z + m[1, 3]
    cw = m[3, 0] * x + m[3, 1] * y + m[3, 2] * z + m[3, 3]
    sx = (cx / cw + 1.0) * (0.5 * w)
    sy = (1.0 - cy / cw) * (0.5 * h)
    return sx, sy, cw > 0


def brush_rows(mvp, x, y, z, w, h, rect):
    """Rows whose projection falls inside a screen rect (x0, y0, x1, y1)."""
    sx, sy, front = project_to_screen(mvp, x, y, z, w, h)
    x0, y0, x1, y1 = rect
    return np.flatnonzero(front & (sx >= x0) & (sx < x1)
                          & (sy >= y0) & (sy < y1))


# ------------------------------------------------------------- renderer

class OffscreenRenderer:
    """QOpenGLContext + QOffscreenSurface + FBO; no window, no PyOpenGL."""

    def __init__(self, QtGui):
        self.QtGui = QtGui
        self.ctx = QtGui.QOpenGLContext()
        if not self.ctx.create():
            raise RuntimeError("QOpenGLContext.create() failed")
        self.surface = QtGui.QOffscreenSurface()
        self.surface.setFormat(self.ctx.format())
        self.surface.create()
        if not self.ctx.makeCurrent(self.surface):
            raise RuntimeError("QOpenGLContext.makeCurrent(QOffscreenSurface)"
                               " failed")
        profile = QtGui.QOpenGLVersionProfile()
        profile.setVersion(2, 1)
        self.gl = self.ctx.versionFunctions(profile)
        if self.gl is None:
            fmt = self.ctx.format()
            raise RuntimeError(
                "no OpenGL 2.1 function table for this context (got %d.%d, "
                "profile %d); PyQt5 only wraps compatibility-profile tables"
                % (fmt.majorVersion(), fmt.minorVersion(), fmt.profile()))
        self.gl.initializeOpenGLFunctions()
        self.info = "%s | %s | %s" % (self.gl.glGetString(GL_VENDOR),
                                      self.gl.glGetString(GL_RENDERER),
                                      self.gl.glGetString(GL_VERSION))
        self.program = QtGui.QOpenGLShaderProgram()
        self.program.addShaderFromSourceCode(QtGui.QOpenGLShader.Vertex,
                                             VERTEX_SHADER)
        self.program.addShaderFromSourceCode(QtGui.QOpenGLShader.Fragment,
                                             FRAGMENT_SHADER)
        self.program.bindAttributeLocation("a_pos", 0)
        self.program.bindAttributeLocation("a_color", 1)
        if not self.program.link():
            raise RuntimeError("shader link failed: " + self.program.log())
        self.u_mvp = self.program.uniformLocation("u_mvp")
        self.u_point_size = self.program.uniformLocation("u_point_size")
        self.vbo_pos = self.vbo_color = None
        self.fbo = None
        self.count, self.mode, self.point_size = 0, GL_POINTS, 1.0

    def make_current(self):
        """Needed whenever another context (a QOpenGLWidget) ran since."""
        self.ctx.makeCurrent(self.surface)

    def _upload(self, arr):
        buf = self.QtGui.QOpenGLBuffer(self.QtGui.QOpenGLBuffer.VertexBuffer)
        buf.create()
        buf.setUsagePattern(self.QtGui.QOpenGLBuffer.StaticDraw)
        buf.bind()
        buf.allocate(arr, arr.nbytes)
        buf.release()
        return buf

    def set_geometry(self, pos, color, mode, point_size=1.0):
        """Upload once (like GLScatterPlotItem.upload_vbo), draw many."""
        for buf in (self.vbo_pos, self.vbo_color):
            if buf is not None:
                buf.destroy()
        self.vbo_pos = self._upload(np.ascontiguousarray(pos, np.float32))
        self.vbo_color = self._upload(np.ascontiguousarray(color, np.float32))
        self.count, self.mode, self.point_size = len(pos), mode, point_size
        self.gl.glFinish()

    def resize(self, w, h):
        # Target and internal format must be explicit: PyQt5's defaults
        # for them yield an invalid FBO once a depth attachment is asked.
        self.fbo = self.QtGui.QOpenGLFramebufferObject(
            w, h, self.QtGui.QOpenGLFramebufferObject.CombinedDepthStencil,
            GL_TEXTURE_2D, GL_RGBA8)
        if not self.fbo.isValid():
            raise RuntimeError("framebuffer object %dx%d is invalid" % (w, h))
        self.w, self.h = w, h

    def render(self, mvp):
        gl, prog = self.gl, self.program
        self.fbo.bind()
        gl.glViewport(0, 0, self.w, self.h)
        gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_DEPTH_TEST)
        gl.glEnable(GL_PROGRAM_POINT_SIZE)
        prog.bind()
        prog.setUniformValue(self.u_mvp,
                             self.QtGui.QMatrix4x4(*mvp.astype(float).ravel()))
        gl.glUniform1f(self.u_point_size, self.point_size)
        self.vbo_pos.bind()
        prog.setAttributeBuffer(0, GL_FLOAT, 0, 3)
        prog.enableAttributeArray(0)
        self.vbo_color.bind()
        prog.setAttributeBuffer(1, GL_FLOAT, 0, 4)
        prog.enableAttributeArray(1)
        gl.glDrawArrays(self.mode, 0, self.count)
        prog.disableAttributeArray(0)
        prog.disableAttributeArray(1)
        self.vbo_color.release()
        prog.release()

    def finish(self):
        self.gl.glFinish()

    def read(self):
        """FBO -> QImage (glReadPixels + flip, as grabFramebuffer does)."""
        return self.fbo.toImage()


# ---------------------------------------------------------------- scenes

def make_scatter(n, rng):
    pos = rng.standard_normal((n, 3)).astype(np.float32) * 2.0
    t = (pos[:, 2] - pos[:, 2].min()) / np.ptp(pos[:, 2])
    color = np.stack([t, 0.4 + 0.0 * t, 1.0 - t, np.ones_like(t)], axis=1)
    return pos, color.astype(np.float32)


def make_surface(n):
    """n x n height field as non-indexed triangles (6 vertices per quad)."""
    g = np.linspace(-10, 10, n, dtype=np.float32)
    X, Y = np.meshgrid(g, g, indexing="ij")
    R = np.hypot(X, Y) + 1e-6
    Z = 3.0 * np.sin(R) / R
    P = np.stack([X, Y, Z], axis=-1)
    a, b = P[:-1, :-1], P[1:, :-1]
    c, d = P[1:, 1:], P[:-1, 1:]
    tri = np.stack([a, b, c, a, c, d], axis=2).reshape(-1, 3)
    t = (tri[:, 2] - tri[:, 2].min()) / np.ptp(tri[:, 2])
    color = np.stack([t, 1.0 - 0.5 * t, 0.3 + 0.0 * t, np.ones_like(t)], 1)
    return tri.astype(np.float32), color.astype(np.float32)


# ------------------------------------------------------------ benchmarks

def bench_scene(renderer, QtGui, pos, sizes, frames, save_as=None):
    """Per-frame timings (ms) for one uploaded scene at every size."""
    rows = []
    for (w, h) in sizes:
        renderer.resize(w, h)
        cam = Camera(distance=float(np.abs(pos).max()) * 2.5)
        # Warm-up: first frames include shader/driver lazy work.
        for _ in range(3):
            renderer.render(cam.mvp(w, h))
            renderer.read()
        t_render, t_read, t_pix, t_total = [], [], [], []
        for i in range(frames):
            # A mouse drag feeding the camera between frames: a full orbit
            # over the run, plus a small elevation wobble.
            cam.drag(-360.0 / frames, 2.0 * sin(i / 5.0), "left", w)
            t0 = time.perf_counter()
            renderer.render(cam.mvp(w, h))
            renderer.finish()
            t1 = time.perf_counter()
            img = renderer.read()
            t2 = time.perf_counter()
            pix = QtGui.QPixmap.fromImage(img)
            t3 = time.perf_counter()
            del img, pix          # "displayed", then discarded
            t_render.append((t1 - t0) * 1e3)
            t_read.append((t2 - t1) * 1e3)
            t_pix.append((t3 - t2) * 1e3)
            t_total.append((t3 - t0) * 1e3)
        if save_as:
            renderer.read().save("%s_%dx%d.png" % (save_as, w, h))
        rows.append({
            "size": "%dx%d" % (w, h),
            "render": statistics.median(t_render),
            "read": statistics.median(t_read),
            "pix": statistics.median(t_pix),
            "total": statistics.median(t_total),
            "p95": float(np.percentile(t_total, 95)),
        })
    return rows


def bench_in_scene(renderer, QtCore, QtGui, n_cells, frames, n_points,
                   rng, save_as=None):
    """Option A for real: 3D cells as grid items in a GraphicsLayoutWidget.

    The window uses useOpenGL=True like LaFigure (its viewport is a
    QOpenGLWidget with its own GL context), so every frame switches
    between the offscreen context and the viewport's. Each 3D cell is a
    plain pg.GraphicsWidget in the grid that paints the read-back pixmap;
    two ordinary 2D PlotItems share the layout. Per frame: orbit each
    cell's camera, render + read back every 3D cell at its current
    on-screen size, then repaint the viewport synchronously.
    """
    import pyqtgraph as pg
    from PyQt5 import QtWidgets
    pg.setConfigOptions(useOpenGL=True, antialias=False)

    class GLCell(pg.GraphicsWidget):
        def __init__(self):
            super().__init__()
            self.pixmap = None
            self.cam = Camera(distance=15.0)
            # A bare GraphicsWidget has no size hint: without this the grid
            # squeezes it to a sliver next to the PlotItems.
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                               QtWidgets.QSizePolicy.Expanding)
            self.setPreferredSize(400, 300)

        def paint(self, p, *args):
            if self.pixmap is not None:
                p.drawPixmap(self.rect().toRect(), self.pixmap)

    win = pg.GraphicsLayoutWidget()
    win.setAttribute(QtCore.Qt.WA_DontShowOnScreen)
    win.resize(1600, 1000)
    t = np.linspace(0, 10, 100_000)
    for col in range(2):
        win.addPlot(row=0, col=col).plot(t, np.sin(t * (col + 1)))
    cells = []
    for i in range(n_cells):
        cell = GLCell()
        cell.cam.orbit(90.0 * i, 0.0)
        win.ci.addItem(cell, row=1 + i // 2, col=i % 2)
        cells.append(cell)
    for row in range(1 + (n_cells + 1) // 2):
        win.ci.layout.setRowStretchFactor(row, 1)
    win.show()
    QtGui.QGuiApplication.processEvents()
    pos, color = make_scatter(n_points, rng)
    renderer.make_current()
    renderer.set_geometry(pos, color, GL_POINTS, 3.0)

    def frame():
        for cell in cells:
            r = cell.sceneBoundingRect()
            w, h = max(int(r.width()), 1), max(int(r.height()), 1)
            renderer.make_current()
            if renderer.fbo is None or (renderer.w, renderer.h) != (w, h):
                renderer.resize(w, h)
            cell.cam.drag(-6.0, 0.0, "left", w)
            renderer.render(cell.cam.mvp(w, h))
            cell.pixmap = QtGui.QPixmap.fromImage(renderer.read())
            cell.update()
        win.viewport().repaint()

    for _ in range(3):
        frame()
    times = []
    for _ in range(frames):
        t0 = time.perf_counter()
        frame()
        times.append((time.perf_counter() - t0) * 1e3)
    # Did the 3D pixels really reach the composited view? The background
    # is black, so count bright pixels inside the first 3D cell.
    shot = win.grab().toImage().convertToFormat(QtGui.QImage.Format_RGB32)
    if save_as:
        shot.save(save_as)
    r = cells[0].mapRectToScene(cells[0].boundingRect())
    r = win.mapFromScene(r).boundingRect()
    dpr = shot.devicePixelRatio()
    lit = total = 0
    for y in range(r.top() + 2, r.bottom() - 2, 4):
        for x in range(r.left() + 2, r.right() - 2, 4):
            total += 1
            c = QtGui.QColor(shot.pixel(int(x * dpr), int(y * dpr)))
            lit += max(c.red(), c.green(), c.blue()) > 100
    size = "%dx%d" % (renderer.w, renderer.h)
    win.close()
    return (statistics.median(times), float(np.percentile(times, 95)),
            size, lit, total)


def check_matrices():
    """Numpy camera == GLViewWidget's QMatrix4x4 recipe, after moves."""
    cam = Camera(center=(1.0, -2.0, 0.5), distance=17.0, elevation=12.0,
                 azimuth=-33.0)
    worst = 0.0
    for step in range(5):
        cam.drag(37.0, -11.0, "left", 800)
        cam.drag(15.0, 9.0, "middle", 800)
        cam.wheel(120)
        worst = max(worst, float(np.abs(cam.mvp(800, 600)
                                        - cam.qt_mvp(800, 600)).max()))
    return worst


def check_projection(renderer):
    """Render isolated points, then check numpy says where they landed.

    Repeated after left-drag (orbit), wheel (dolly) and middle-drag (pan)
    camera moves: validates both "forward mouse input to the camera" and
    "brush via camera-matrix projection in numpy" against real pixels.
    """
    w, h = 800, 600
    renderer.resize(w, h)
    g = np.arange(-3.0, 3.1, 2.0)
    pos = np.array(np.meshgrid(g, g, g, indexing="ij"),
                   np.float32).reshape(3, -1).T          # 4x4x4 lattice
    color = np.ones((len(pos), 4), np.float32)
    renderer.set_geometry(pos, color, GL_POINTS, point_size=5.0)
    cam = Camera(distance=18.0)
    steps = [("initial", None),
             ("left-drag orbit (120, -40) px", ("left", 120.0, -40.0)),
             ("wheel +240 (dolly in)", ("wheel", 240.0, 0.0)),
             ("middle-drag pan (60, 25) px", ("middle", 60.0, 25.0))]
    results, prev = [], None
    for label, move in steps:
        if move is not None:
            kind, dx, dy = move
            if kind == "wheel":
                cam.wheel(dx)
            else:
                # Split into small increments, as real mouse moves arrive.
                for _ in range(10):
                    cam.drag(dx / 10, dy / 10, kind, w)
        renderer.render(cam.mvp(w, h))
        img = renderer.read().convertToFormat(
            renderer.QtGui.QImage.Format_RGB32)
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        arr = np.frombuffer(ptr, np.uint8).reshape(h, img.bytesPerLine())
        lum = arr[:, :4 * w].reshape(h, w, 4)[:, :, :3].max(axis=2)
        sx, sy, front = project_to_screen(cam.mvp(w, h), pos[:, 0].astype(float),
                                          pos[:, 1].astype(float),
                                          pos[:, 2].astype(float), w, h)
        inside = front & (sx >= 1) & (sx < w - 1) & (sy >= 1) & (sy < h - 1)
        hits = 0
        for x, y in zip(sx[inside], sy[inside]):
            ix, iy = int(x), int(y)
            if lum[iy - 1:iy + 2, ix - 1:ix + 2].max() > 128:
                hits += 1
        lit = int((lum > 128).sum())
        moved = None if prev is None else float(np.hypot(sx - prev[0],
                                                         sy - prev[1]).max())
        prev = (sx, sy)
        results.append((label, hits, int(inside.sum()), lit, moved))
    return results


def bench_brush(n, rng):
    """Numpy projection (+ rect -> rows) timing, DataSource-like columns."""
    x, y, z = (rng.standard_normal(n) * 2.0 for _ in range(3))  # float64
    cam = Camera(distance=12.0)
    w, h = 800, 600
    rect = (300, 200, 500, 400)
    t_proj, t_rows = [], []
    for _ in range(3):       # warm-up
        brush_rows(cam.mvp(w, h), x, y, z, w, h, rect)
    for i in range(20):
        cam.orbit(3.0, 0.0)  # a new camera per drag update
        m = cam.mvp(w, h)
        t0 = time.perf_counter()
        project_to_screen(m, x, y, z, w, h)
        t1 = time.perf_counter()
        rows = brush_rows(m, x, y, z, w, h, rect)
        t2 = time.perf_counter()
        t_proj.append((t1 - t0) * 1e3)
        t_rows.append((t2 - t1) * 1e3)
    # The camera doesn't move while the user drags a brush rectangle, so a
    # brush can project once at press and only re-test the rect per move.
    sx, sy, front = project_to_screen(cam.mvp(w, h), x, y, z, w, h)
    t_rect = []
    for i in range(20):
        x0, y0 = 300 + i, 200 + i
        t0 = time.perf_counter()
        np.flatnonzero(front & (sx >= x0) & (sx < x0 + 200)
                       & (sy >= y0) & (sy < y0 + 200))
        t_rect.append((time.perf_counter() - t0) * 1e3)
    # float32 packed (N, 3) variant, as GL-bound vertex data would be.
    pts = np.stack([x, y, z], 1).astype(np.float32)
    t_f32 = []
    for i in range(20):
        m = cam.mvp(w, h)
        t0 = time.perf_counter()
        mx = m[[0, 1, 3]].astype(np.float32)
        clip = pts @ mx[:, :3].T + mx[:, 3]
        sx = (clip[:, 0] / clip[:, 2] + 1.0) * (0.5 * w)
        sy = (1.0 - clip[:, 1] / clip[:, 2]) * (0.5 * h)
        t_f32.append((time.perf_counter() - t0) * 1e3)
    return (statistics.median(t_proj), statistics.median(t_rows),
            statistics.median(t_rect), statistics.median(t_f32), len(rows))


# ------------------------------------------------------------------ main

def main():
    args = parse_args()
    if args.platform:
        os.environ["QT_QPA_PLATFORM"] = args.platform
    if args.software:
        os.environ["QT_OPENGL"] = "software"
    from PyQt5 import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        sys.argv[:1])
    platform = app.platformName()
    print("Qt %s, PyQt5, QPA platform '%s', QT_OPENGL=%s" % (
        QtCore.QT_VERSION_STR, platform, os.environ.get("QT_OPENGL", "")))
    try:
        import pyqtgraph.opengl  # noqa: F401
        print("pyqtgraph.opengl importable (not used: this script measures "
              "the same GL path through raw Qt)")
    except Exception as e:  # noqa: BLE001 -- informational only
        print("pyqtgraph.opengl NOT importable: %s: %s" % (
            type(e).__name__, e))

    try:
        renderer = OffscreenRenderer(QtGui)
    except RuntimeError as e:
        print("\nERROR: no usable OpenGL context: %s" % e)
        if platform in ("offscreen", "minimal"):
            print("The '%s' QPA plugin provided no OpenGL context here (on "
                  "Windows with Qt 5.15 it never does, even with "
                  "QT_OPENGL=software; Linux is untested).\n"
                  "No window is ever shown by this script -- it renders to a"
                  " QOffscreenSurface -- so run it on the native platform:\n"
                  "  unset QT_QPA_PLATFORM, or pass --platform windows (or "
                  "xcb under Xvfb on Linux)." % platform)
        return 2
    print("GL: " + renderer.info)

    sizes = [tuple(int(v) for v in s.lower().split("x")) for s in args.sizes]
    rng = np.random.default_rng(0)

    # 1. Camera math and render/projection consistency.
    err = check_matrices()
    print("\nNumpy camera vs GLViewWidget QMatrix4x4 recipe: max |diff| = "
          "%.2e after orbit/pan/wheel moves" % err)
    print("\nRender vs numpy projection (64-point lattice, 800x600):")
    ok = True
    for label, hits, inside, lit, moved in check_projection(renderer):
        ok &= hits == inside and inside > 0
        print("  %-32s %2d/%2d projected points land on lit pixels"
              " (lit px %5d)%s" % (label, hits, inside, lit,
                                   "" if moved is None else
                                   ", max on-screen move %.1f px" % moved))
    print("  -> %s" % ("CONSISTENT" if ok else "MISMATCH"))

    # 2. Render + readback timing.
    scenes = [("scatter %s pts" % f"{n:,}", n) for n in args.points]
    if args.surface:
        scenes.append(("surface %dx%d (%s tri verts)" % (
            args.surface, args.surface, f"{6 * (args.surface - 1) ** 2:,}"),
            -args.surface))
    table = []
    for label, n in scenes:
        t0 = time.perf_counter()
        if n > 0:
            pos, color = make_scatter(n, rng)
            renderer.set_geometry(pos, color, GL_POINTS, args.point_size)
        else:
            pos, color = make_surface(-n)
            renderer.set_geometry(pos, color, GL_TRIANGLES)
        setup = (time.perf_counter() - t0) * 1e3
        print("\n%s: one-time data gen + upload %.0f ms" % (label, setup))
        save_as = None
        if args.save_png:
            os.makedirs(args.save_png, exist_ok=True)
            save_as = os.path.join(args.save_png, "%s_%d" % (
                "scatter" if n > 0 else "surface", abs(n)))
        for r in bench_scene(renderer, QtGui, pos, sizes, args.frames,
                             save_as):
            r["scene"] = label
            table.append(r)
            print("  %-10s total %.2f ms (render %.2f, readback %.2f, "
                  "toPixmap %.2f), p95 %.2f" % (r["size"], r["total"],
                                                r["render"], r["read"],
                                                r["pix"], r["p95"]))

    # 3. The same inside a real LaFigure-like window.
    in_scene = []
    for k in args.in_scene:
        med, p95, size, lit, total = bench_in_scene(
            renderer, QtCore, QtGui, k, args.frames, args.in_scene_points,
            rng, args.save_png and os.path.join(args.save_png,
                                                "in_scene_%d.png" % k))
        in_scene.append((k, med, p95, size, lit, total))
        print("\nin-scene, %d 3D cell(s) of %s pts at %s + 2 PlotItems: "
              "%.2f ms/frame (p95 %.2f); first 3D cell composited: %d/%d "
              "sampled px lit" % (k, f"{args.in_scene_points:,}", size, med,
                                  p95, lit, total))

    # 4. Brushing primitive.
    proj, rows, rect, f32, nsel = bench_brush(args.brush_points, rng)

    print("\n## Results (median of %d frames, ms)\n" % args.frames)
    print("GL: %s  \nQPA platform: %s\n" % (renderer.info, platform))
    print("| scene | size | render+glFinish | readback (toImage) "
          "| QPixmap.fromImage | **total** | total p95 | max fps |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in table:
        print("| %s | %s | %.2f | %.2f | %.2f | **%.2f** | %.2f | %.0f |" % (
            r["scene"], r["size"], r["render"], r["read"], r["pix"],
            r["total"], r["p95"], 1e3 / r["total"]))
    if in_scene:
        print("\nIn a 1600x1000 GraphicsLayoutWidget (useOpenGL=True) with 2 "
              "PlotItems of 100,000 pts, %s scatter pts per 3D cell; one "
              "frame = render+read every 3D cell + synchronous viewport "
              "repaint:\n" % f"{args.in_scene_points:,}")
        print("| 3D cells | cell size | **ms/frame** | p95 | max fps "
              "| 3D pixels composited |")
        print("|---:|---|---:|---:|---:|---|")
        for k, med, p95, size, lit, total in in_scene:
            print("| %d | %s | **%.2f** | %.2f | %.0f | %d/%d sampled px lit |"
                  % (k, size, med, p95, 1e3 / med, lit, total))
    print("\nNumpy brush projection, %s points (float64 columns x, y, z):"
          % f"{args.brush_points:,}")
    print("| step | median ms |\n|---|---:|")
    print("| project to screen (x, y, w rows of MVP) | %.2f |" % proj)
    print("| project + rect test -> row indices (%s rows hit) | %.2f |"
          % (f"{nsel:,}", rows))
    print("| rect test only, on screen coords cached at drag start | %.2f |"
          % rect)
    print("| project only, float32 packed (N,3) @ 3x4 | %.2f |" % f32)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
