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

"""3D cells (roadmap Phase 6, "Option A"): a 3D subplot renders its scene
offscreen to an image and shows that image like any other item, so the
layout, selection, menus, undo and brushing keep treating it as a subplot.

**A 3D cell is a pg.PlotItem whose ViewBox is a View3DBox.** add_subplot
(layout.py) still makes exactly one PlotItem; for axes_type='3d' it only
passes a View3DBox as its viewBox and hides the 2D axes. Everything keyed on a
PlotItem -- boxes, z_order, handles, click selection, the right-click menu,
the RectBrush -- therefore works unchanged. The View3DBox pins its view
range to its own pixels, (0, 0)-(width, height) with y down, so "view
coordinates" inside a 3D cell are screen pixels of the rendered image: a
brush rectangle arrives there in the same units the camera projects to.

**The math is the WP-G spike's** (spikes/gl_offscreen_readback.py), moved
here unchanged: Camera is GLViewWidget's euler camera in numpy (checked
there against Qt's QMatrix4x4 recipe and against real rendered pixels),
project_to_screen its brush projection. The renderer is the spike's
OffscreenRenderer (QOpenGLContext + QOffscreenSurface + FBO, PyQt5's own
GL bindings, no PyOpenGL), generalized to several primitives per scene.

**The spike's five conditions**, and where each lives:
1. Render on demand: View3DBox.request_render coalesces requests (camera,
   data, visibility, size) into one render on the next event-loop turn;
   an idle cell just keeps its pixmap.
2. One offscreen context shared by every 3D cell -- one per process, not
   per figure (a stricter sharing than the spike asked for: VBOs are then
   valid in every figure). made current before every render.
3. Brushing projects once per camera state: View3DBox.projected caches the
   screen coordinates per (camera version, size, data version), so a brush
   rect test costs only the comparisons. Points hidden behind others are
   selected too (no depth test), as the spike noted.
4. HiDPI: the image is rendered at size x devicePixelRatio.
5. No GL context (QT_QPA_PLATFORM=offscreen on Windows, CLAUDE.md bug #10;
   or LAFIGURE_3D_BACKEND=painter): paint_fallback draws the same
   projection with QPainter -- slower, approximate (per-primitive color,
   no depth buffer, surfaces over 20k triangles as vertices only), but the
   cell is never blank and the headless tests can check its pixels.

**Series on a 3D cell** (kinds/scatter3d.py, line3d.py, surface.py) are
Series3DItem data holders added to the PlotItem, so they are in
listDataItems() and have a Series like every other kind; they draw
nothing themselves -- the cell renders them all into one image, with one
depth buffer. Kind3D.get_xy returns (positions (N, 3), None), the same
"(data, None)" stretch imshow uses. They apply their DataSource's hidden
rows and filter themselves at draw time (listening to its on_change), so
Hide Brushed Points and src.filter reach 3D views without the point-view
machinery of brushing.py, which only handles x/y point clouds.
"""
import os
import sys
import weakref
from math import cos, radians, sin, tan

import numpy as np
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import pyqtgraph as pg
import pyqtgraph.functions as fn

from .series import SeriesKind, _SERIES_ATTR

# GL enums (no PyOpenGL, so no GL.GL_* names).
GL_POINTS = 0x0000
GL_LINES = 0x0001
GL_LINE_STRIP = 0x0003
GL_TRIANGLES = 0x0004
GL_FLOAT = 0x1406
GL_DEPTH_TEST = 0x0B71
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
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

# Environment switch: LAFIGURE_3D_BACKEND=painter never tries OpenGL.
BACKEND_ENV = 'LAFIGURE_3D_BACKEND'
# The QPainter fallback fills at most this many triangles (a Python loop);
# a larger surface is drawn as its vertices.
FALLBACK_MAX_TRIANGLES = 20_000


# -- camera (the spike's, unchanged) ------------------------------------------
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
    """GLViewWidget's default ('euler') camera, in numpy -- the WP-G spike's
    Camera, with a `version` counter (bumped by every move, so projections
    can be cached per camera state) and state()/set_state()/fit()."""

    # The 4 named camera-view presets (R4-3D): (elevation, azimuth) that
    # look straight down the one axis not named -- 'xy' looks down Z (so
    # the X-Y plane fills the view), 'xz' down Y, 'yz' down X, 'sideway'
    # is today's isometric default. Checked against camera_position():
    # elevation=90 puts the camera on +Z; elevation=0/azimuth=0 on +X;
    # elevation=0/azimuth=90 on +Y (see the worker's own report).
    VIEW_PRESETS = {
        'xy': (90.0, 0.0),
        'xz': (0.0, 90.0),
        'yz': (0.0, 0.0),
        'sideway': (30.0, 45.0),
    }

    def __init__(self, center=(0.0, 0.0, 0.0), distance=10.0,
                 elevation=30.0, azimuth=45.0, fov=60.0, projection='perspective'):
        self.center = np.array(center, float)
        self.distance = float(distance)
        self.elevation = float(elevation)
        self.azimuth = float(azimuth)
        self.fov = float(fov)
        self.projection = projection    # 'perspective' (default) or 'orthographic'
        self.version = 0

    # --- the camera-update API the cell's mouse handlers call
    def orbit(self, azim, elev):
        self.azimuth += azim
        self.elevation = float(np.clip(self.elevation + elev, -90.0, 90.0))
        self.version += 1

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
        self.version += 1

    def wheel(self, delta):
        """GLViewWidget.wheelEvent without Ctrl: dolly in/out."""
        self.distance *= 0.999 ** delta
        self.version += 1

    def dolly_scale(self, factor):
        """Scale distance by `factor` directly (Zoom Rect mode's drag-a-
        rectangle zoom on a 3D cell, View3DBox._apply_rect_zoom): factor
        < 1 zooms in, > 1 zooms out. Unlike wheel(), a plain linear scale
        -- the caller already derived `factor` from screen-pixel ratios."""
        self.distance *= float(factor)
        self.version += 1

    def look_along(self, preset):
        """Set elevation/azimuth to one of VIEW_PRESETS ('xy'/'xz'/'yz'/
        'sideway' -- the subplot menu's 4 camera-view entries, R4-3D).
        center/distance/fov/projection are untouched."""
        try:
            elevation, azimuth = self.VIEW_PRESETS[preset]
        except KeyError:
            raise ValueError(f"unknown view preset {preset!r}; expected one "
                             f"of {sorted(self.VIEW_PRESETS)}")
        self.elevation, self.azimuth = elevation, azimuth
        self.version += 1

    def drag(self, dx, dy, button, width):
        """GLViewWidget.mouseMoveEvent's mapping of a mouse delta (px)."""
        if button == "left":
            self.orbit(-dx, dy)
        elif button == "middle":
            self.pan(dx, dy, 0, width)

    # --- state
    def state(self):
        """Plain floats/str, comparable with ==: for undo and copy/paste."""
        return {'center': tuple(float(v) for v in self.center), 'distance': self.distance,
                'elevation': self.elevation, 'azimuth': self.azimuth, 'fov': self.fov,
                'projection': self.projection}

    def set_state(self, state):
        self.center = np.array(state['center'], float)
        self.distance = float(state['distance'])
        self.elevation = float(state['elevation'])
        self.azimuth = float(state['azimuth'])
        self.fov = float(state.get('fov', self.fov))
        # .get: a state captured before R4-3D added projection still restores.
        self.projection = state.get('projection', self.projection)
        self.version += 1

    def fit(self, lo, hi, elevation=30.0, azimuth=45.0):
        """Look at the box lo..hi (3-vectors) from the default direction,
        far enough that its bounding sphere fills the view."""
        lo, hi = np.asarray(lo, float), np.asarray(hi, float)
        radius = 0.5 * float(np.linalg.norm(hi - lo))
        if not np.isfinite(radius) or radius <= 0:
            radius = 1.0
        self.center = 0.5 * (lo + hi)
        self.distance = 1.15 * radius / sin(0.5 * radians(self.fov))
        self.elevation, self.azimuth = float(elevation), float(azimuth)
        self.version += 1

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
        if self.projection == 'orthographic':
            # Sized from distance and fov, not near/fov like the perspective
            # frustum below, so switching projection doesn't jump the
            # apparent scale of whatever sits at the camera's own focal
            # distance: half_w is exactly the world half-width the
            # perspective frustum shows at depth=distance (by similar
            # triangles from its near-plane r), so a point there projects
            # to the same screen position either way -- checked directly
            # against the perspective matrix in the worker's own tests.
            half_w = max(self.distance * tan(0.5 * radians(self.fov)), 1e-9)
            half_h = half_w * h / w
            m = np.zeros((4, 4))
            m[0, 0] = 1.0 / half_w
            m[1, 1] = 1.0 / half_h
            m[2, 2] = -2.0 / (far - near)
            m[2, 3] = -(far + near) / (far - near)
            m[3, 3] = 1.0
            return m
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


def project_to_screen(mvp, x, y, z, w, h):
    """Numpy projection of 3D points to pixel coords (top-left origin), the
    spike's. Returns (sx, sy, in_front). Only the x, y, w rows of the MVP
    are needed -- depth isn't, for a rectangle brush."""
    m = mvp
    cx = m[0, 0] * x + m[0, 1] * y + m[0, 2] * z + m[0, 3]
    cy = m[1, 0] * x + m[1, 1] * y + m[1, 2] * z + m[1, 3]
    cw = m[3, 0] * x + m[3, 1] * y + m[3, 2] * z + m[3, 3]
    with np.errstate(divide='ignore', invalid='ignore'):
        sx = (cx / cw + 1.0) * (0.5 * w)
        sy = (1.0 - cy / cw) * (0.5 * h)
    return sx, sy, cw > 0


def rows_in_screen_rect(sx, sy, front, rect):
    """Positions of the projected points inside `rect` (a QRectF in the
    same pixels, edges included, like selection.rows_in_rect's 2D test)."""
    return np.flatnonzero(front & (sx >= rect.left()) & (sx <= rect.right())
                          & (sy >= rect.top()) & (sy <= rect.bottom()))


# -- what a 3D scene is made of ------------------------------------------------
class Primitive:
    """One draw call: `mode` 'points', 'line_strip', 'lines' or 'triangles';
    `pos` float32 (N, 3); `color` float32 (N, 4) in 0..1; `size` the point
    size or line width in logical pixels. Never mutated once built -- new
    data builds a new Primitive -- so the GL renderer can keep its uploaded
    buffers for as long as the object lives."""
    __slots__ = ('mode', 'pos', 'color', 'size', '__weakref__')
    GL_MODES = {'points': GL_POINTS, 'line_strip': GL_LINE_STRIP,
                'lines': GL_LINES, 'triangles': GL_TRIANGLES}

    def __init__(self, mode, pos, color, size=1.0):
        self.mode = mode
        self.pos = np.ascontiguousarray(pos, np.float32).reshape(-1, 3)
        color = np.asarray(color, np.float32)
        if color.ndim == 1:
            color = np.broadcast_to(color, (len(self.pos), 4))
        self.color = np.ascontiguousarray(color, np.float32)
        self.size = float(size)


def rgba_f(color):
    """Anything pg.mkColor takes -> (r, g, b, a) floats in 0..1."""
    c = pg.mkColor(color)
    return (c.redF(), c.greenF(), c.blueF(), c.alphaF())


# -- the GL renderer (the spike's OffscreenRenderer) ---------------------------
class GLRenderer:
    """QOpenGLContext + QOffscreenSurface + one FBO resized per cell; no
    window, no PyOpenGL. Raises RuntimeError from __init__ when no usable
    context exists."""

    def __init__(self):
        self.ctx = QtGui.QOpenGLContext()
        if not self.ctx.create():
            raise RuntimeError("QOpenGLContext.create() failed")
        self.surface = QtGui.QOffscreenSurface()
        self.surface.setFormat(self.ctx.format())
        self.surface.create()
        if not self.ctx.makeCurrent(self.surface):
            raise RuntimeError("QOpenGLContext.makeCurrent(QOffscreenSurface) failed")
        profile = QtGui.QOpenGLVersionProfile()
        profile.setVersion(2, 1)
        self.gl = self.ctx.versionFunctions(profile)
        if self.gl is None:
            fmt = self.ctx.format()
            raise RuntimeError(
                "no OpenGL 2.1 function table for this context (got %d.%d, profile %d); "
                "PyQt5 only wraps compatibility-profile tables"
                % (fmt.majorVersion(), fmt.minorVersion(), fmt.profile()))
        self.gl.initializeOpenGLFunctions()
        self.info = "%s | %s | %s" % (self.gl.glGetString(GL_VENDOR),
                                      self.gl.glGetString(GL_RENDERER),
                                      self.gl.glGetString(GL_VERSION))
        self.program = QtGui.QOpenGLShaderProgram()
        self.program.addShaderFromSourceCode(QtGui.QOpenGLShader.Vertex, VERTEX_SHADER)
        self.program.addShaderFromSourceCode(QtGui.QOpenGLShader.Fragment, FRAGMENT_SHADER)
        self.program.bindAttributeLocation("a_pos", 0)
        self.program.bindAttributeLocation("a_color", 1)
        if not self.program.link():
            raise RuntimeError("shader link failed: " + self.program.log())
        self.u_mvp = self.program.uniformLocation("u_mvp")
        self.u_point_size = self.program.uniformLocation("u_point_size")
        self.fbo = None
        self.w = self.h = 0
        # id(Primitive) -> (weakref to it, position VBO, color VBO)
        self._buffers = {}
        self.ctx.doneCurrent()

    def _upload(self, arr):
        buf = QtGui.QOpenGLBuffer(QtGui.QOpenGLBuffer.VertexBuffer)
        buf.create()
        buf.setUsagePattern(QtGui.QOpenGLBuffer.StaticDraw)
        buf.bind()
        buf.allocate(arr, arr.nbytes)
        buf.release()
        return buf

    def _buffers_for(self, prim):
        """Upload once (like GLScatterPlotItem.upload_vbo), draw many."""
        entry = self._buffers.get(id(prim))
        if entry is None or entry[0]() is not prim:
            entry = (weakref.ref(prim), self._upload(prim.pos), self._upload(prim.color))
            self._buffers[id(prim)] = entry
        return entry[1], entry[2]

    def _purge(self):
        """Free the buffers of primitives that are gone (context current)."""
        for key in [k for k, e in self._buffers.items() if e[0]() is None]:
            _ref, pos_buf, color_buf = self._buffers.pop(key)
            pos_buf.destroy()
            color_buf.destroy()

    def _resize(self, w, h):
        # Target and internal format must be explicit: PyQt5's defaults
        # for them yield an invalid FBO once a depth attachment is asked.
        self.fbo = QtGui.QOpenGLFramebufferObject(
            w, h, QtGui.QOpenGLFramebufferObject.CombinedDepthStencil, GL_TEXTURE_2D, GL_RGBA8)
        if not self.fbo.isValid():
            raise RuntimeError("framebuffer object %dx%d is invalid" % (w, h))
        self.w, self.h = w, h

    def render(self, prims, mvp, pw, ph, dpr, background):
        """Draw `prims` with `mvp` into a pw x ph (device pixel) image."""
        # Another context (the useOpenGL=True viewport's) is current after
        # every repaint: always make ours current first (spike condition 2).
        if not self.ctx.makeCurrent(self.surface):
            raise RuntimeError("QOpenGLContext.makeCurrent(QOffscreenSurface) failed")
        try:
            self._purge()
            if self.fbo is None or (self.w, self.h) != (pw, ph):
                self._resize(pw, ph)
            gl, prog = self.gl, self.program
            self.fbo.bind()
            gl.glViewport(0, 0, pw, ph)
            gl.glClearColor(*rgba_f(background))
            gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            gl.glEnable(GL_DEPTH_TEST)
            gl.glEnable(GL_PROGRAM_POINT_SIZE)
            gl.glEnable(GL_BLEND)
            gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            prog.bind()
            prog.setUniformValue(self.u_mvp, QtGui.QMatrix4x4(*np.asarray(mvp, float).ravel()))
            for prim in prims:
                if not len(prim.pos):
                    continue
                pos_buf, color_buf = self._buffers_for(prim)
                gl.glUniform1f(self.u_point_size, prim.size * dpr)
                if prim.mode in ('lines', 'line_strip'):
                    gl.glLineWidth(max(1.0, prim.size * dpr))
                pos_buf.bind()
                prog.setAttributeBuffer(0, GL_FLOAT, 0, 3)
                prog.enableAttributeArray(0)
                color_buf.bind()
                prog.setAttributeBuffer(1, GL_FLOAT, 0, 4)
                prog.enableAttributeArray(1)
                gl.glDrawArrays(Primitive.GL_MODES[prim.mode], 0, len(prim.pos))
                prog.disableAttributeArray(0)
                prog.disableAttributeArray(1)
                color_buf.release()
            prog.release()
            self.fbo.release()
            # FBO -> QImage (glReadPixels + flip, as grabFramebuffer does).
            return self.fbo.toImage()
        finally:
            self.ctx.doneCurrent()


_gl = {'renderer': None, 'tried': False, 'error': None}


def get_gl_renderer():
    """The process-wide GLRenderer, created on first use; None when no GL
    context can be created (tried once) or LAFIGURE_3D_BACKEND=painter."""
    if os.environ.get(BACKEND_ENV, '').lower() == 'painter':
        return None
    if not _gl['tried']:
        _gl['tried'] = True
        try:
            _gl['renderer'] = GLRenderer()
        except RuntimeError as e:
            _gl['error'] = str(e)
    return _gl['renderer']


def _disable_gl(error):
    print(f"WARNING: 3D OpenGL rendering failed ({error}); falling back to QPainter.",
          file=sys.stderr)
    _gl['renderer'], _gl['error'] = None, str(error)


# -- the QPainter fallback -------------------------------------------------------
def _qcolor(rgba):
    r, g, b, a = (float(v) for v in np.clip(rgba, 0, 1))
    return QtGui.QColor.fromRgbF(r, g, b, a)


def _polygon(x, y):
    poly = fn.create_qpolygonf(len(x))
    arr = fn.ndarray_from_qpolygonf(poly)
    arr[:, 0], arr[:, 1] = x, y
    return poly


def paint_fallback(prims, mvp, pw, ph, dpr, background):
    """The same scene, projected in numpy and drawn with QPainter -- for
    when there is no GL context. Approximate: one color per primitive
    (except filled triangles), no depth buffer (primitives are drawn in
    order; points of one primitive back to front)."""
    img = QtGui.QImage(pw, ph, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(pg.mkColor(background))
    w, h = pw / dpr, ph / dpr
    painter = QtGui.QPainter(img)
    try:
        painter.scale(dpr, dpr)
        for prim in prims:
            n = len(prim.pos)
            if not n:
                continue
            p = prim.pos.astype(float)
            sx, sy, front = project_to_screen(mvp, p[:, 0], p[:, 1], p[:, 2], w, h)
            color = _qcolor(prim.color.mean(axis=0))
            pen = QtGui.QPen(color, max(prim.size, 1.0))
            if prim.mode == 'points' or (prim.mode == 'triangles' and n // 3 > FALLBACK_MAX_TRIANGLES):
                pen.setCapStyle(QtCore.Qt.SquareCap)
                painter.setPen(pen)
                painter.drawPoints(_polygon(sx[front], sy[front]))
            elif prim.mode in ('line_strip', 'lines'):
                connect = np.zeros(n, dtype=bool)
                if prim.mode == 'line_strip':
                    connect[:-1] = front[:-1] & front[1:]
                else:
                    connect[0:n - 1:2] = front[0:n - 1:2] & front[1::2]
                painter.setPen(pen)
                painter.drawPath(pg.arrayToQPath(np.nan_to_num(sx), np.nan_to_num(sy),
                                                 connect=connect.astype(np.int32)))
            else:  # filled triangles, back to front (painter's algorithm)
                ntri = n // 3
                tx, ty = sx[:3 * ntri].reshape(ntri, 3), sy[:3 * ntri].reshape(ntri, 3)
                ok = front[:3 * ntri].reshape(ntri, 3).all(axis=1)
                eye = (np.c_[p[:3 * ntri], np.ones(3 * ntri)] @ mvp[3]).reshape(ntri, 3).mean(axis=1)
                colors = prim.color[:3 * ntri].reshape(ntri, 3, 4).mean(axis=1)
                painter.setPen(QtCore.Qt.NoPen)
                for i in np.argsort(-eye):
                    if ok[i]:
                        painter.setBrush(_qcolor(colors[i]))
                        painter.drawPolygon(_polygon(tx[i], ty[i]))
    finally:
        painter.end()
    return img


def render_image(prims, mvp, w, h, dpr, background):
    """(QImage, backend name): GL when a context exists, else the fallback."""
    pw, ph = max(int(round(w * dpr)), 1), max(int(round(h * dpr)), 1)
    renderer = get_gl_renderer()
    if renderer is not None:
        try:
            return renderer.render(prims, mvp, pw, ph, dpr, background), 'gl'
        except RuntimeError as e:
            _disable_gl(e)
    return paint_fallback(prims, mvp, pw, ph, dpr, background), 'painter'


# -- the data items a 3D kind adds to the cell ----------------------------------
class Series3DItem(pg.GraphicsObject):
    """The data of one 3D series, living in its cell's PlotItem like any
    plot data item (listDataItems, legend, Series) but drawing nothing
    itself: the cell's View3DBox asks every one of them for primitives()
    and renders the lot together. Subclasses implement _build_primitives.

    `positions()` is every entry, one per row -- the brushing unit. Rows
    hidden or filtered out in the series' DataSource aren't drawn (and
    can't be brushed); they stay in the data."""
    DEFAULT_COLOR = (31, 119, 180)

    def __init__(self, xyz, pen=None, name=None, size=1.0, source=None):
        super().__init__()
        self._xyz = np.array(xyz, dtype=float).reshape(-1, 3)
        self._name = name
        self.size = float(size)
        color = pg.mkPen(pen).color() if pen is not None else pg.mkColor(self.DEFAULT_COLOR)
        # What pyqtgraph's legend sample and groups.py read.
        self.opts = {'pen': pg.mkPen(color, width=self.size), 'symbol': None}
        self.data_version = 0
        self._prims = None
        self._bounds = False     # cached bounds(); False = not computed yet
        self._watch(source)

    # -- the plot-data-item protocol pyqtgraph and the app use
    def implements(self, interface=None):
        ints = ['plotData']
        return ints if interface is None else interface in ints

    def name(self):
        return self._name

    def setName(self, name):
        self._name = name

    def boundingRect(self):
        return QtCore.QRectF()

    def paint(self, *args):
        pass

    def getData(self):
        """No 2D data: Fit Vertical/Horizontal skip this item."""
        return None, None

    def setPen(self, *args, **kwargs):
        pen = pg.mkPen(*args, **kwargs)
        pen.setWidthF(self.size)
        self.opts['pen'] = pen
        self._invalidate()

    def color(self):
        return rgba_f(pg.mkPen(self.opts['pen']).color())

    # -- data
    def positions(self):
        view = self._xyz.view()
        view.flags.writeable = False
        return view

    def set_positions(self, xyz):
        xyz = np.array(xyz, dtype=float).reshape(-1, 3)
        self._xyz = xyz
        self.data_version += 1
        self._invalidate(refit=True)

    def visible_entries(self):
        """Bool mask over positions() of the drawn entries, or None for
        all: a series of a DataSource leaves out its hidden/filtered rows."""
        series = getattr(self, _SERIES_ATTR, None)
        if series is None or series.rows is None:
            return None
        src = series.source
        mask = ~src.hidden_mask
        if src.filter_mask is not None:
            mask = mask & src.filter_mask
        rows = series.rows
        if len(rows) != len(self._xyz):
            return None
        visible = mask[rows]
        return None if visible.all() else visible

    def drawn_count(self):
        visible = self.visible_entries()
        return len(self._xyz) if visible is None else int(visible.sum())

    def primitives(self):
        if self._prims is None:
            visible = self.visible_entries()
            xyz = self._xyz if visible is None else self._xyz[visible]
            self._prims = self._build_primitives(xyz)
        return self._prims

    def _build_primitives(self, xyz):
        raise NotImplementedError

    def bounds(self):
        """(lo, hi) of the drawn entries, or None. Cached until the data or
        its visibility changes: a full scan costs tens of ms at 1M points,
        which a render (the box, the fit) must not pay on every camera move."""
        if self._bounds is False:
            visible = self.visible_entries()
            xyz = self._xyz if visible is None else self._xyz[visible]
            xyz = xyz[np.isfinite(xyz).all(axis=1)]
            self._bounds = (xyz.min(axis=0), xyz.max(axis=0)) if len(xyz) else None
        return self._bounds

    # -- change propagation to the cell
    def view3d(self):
        vb = self.getViewBox()
        return vb if isinstance(vb, View3DBox) else None

    def _invalidate(self, refit=False):
        self._prims = None
        self._bounds = False
        vb = self.view3d()
        if vb is not None:
            vb.data_changed(refit=refit)

    def _watch(self, source):
        """Redraw when the source's hidden rows or filter change. The
        callback holds only a weak reference, and unsubscribes itself once
        the item is gone."""
        if source is None:
            return
        ref = weakref.ref(self)

        def on_change():
            item = ref()
            if item is None:
                source.off_change(on_change)
            else:
                item._invalidate()

        source.on_change(on_change)

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QtWidgets.QGraphicsItem.ItemVisibleHasChanged:
            vb = self.view3d()
            if vb is not None:
                vb.request_render()
        return result


class Brush3DOverlay(pg.ScatterPlotItem):
    """Highlight of brushed rows on a 3D cell: markers at the rows'
    projected pixels, re-projected whenever the camera moves (View3DBox.
    _refresh_overlays). Drawn on top of the image, occluded or not."""

    def __init__(self):
        super().__init__(size=8, pen=pg.mkPen('k', width=1), brush=pg.mkBrush(255, 60, 60, 220))
        self.setZValue(10)
        self.source_item = None
        self.entry_mask = None

    def refresh(self, vb):
        sx, sy, front = vb.projected(self.source_item)
        keep = self.entry_mask & front
        self.setData(x=sx[keep], y=sy[keep])


class Kind3D(SeriesKind):
    """What the three 3D kinds share: they only go on a 3D cell, their
    get_xy is (positions (N, 3), None), and they brush through the
    camera projection (the rows_in_rect/show_rows hooks selection.py asks
    a kind for, see its module docstring)."""
    capabilities = frozenset({'brush', 'copy'})

    def _check_plot(self, plot_item):
        if not isinstance(plot_item.getViewBox(), View3DBox):
            raise ValueError(f"{self.name} needs a 3D subplot: add_subplot(..., axes_type='3d')")

    @staticmethod
    def _column(value, source, rows, n, what):
        """A coordinate given as an array, or as a column name of `source`."""
        if isinstance(value, str):
            if source is None:
                raise TypeError(f"{what}={value!r} names a column, but there is no DataSource")
            value = source[value] if rows is None else source[value][rows]
        if value is None:
            raise TypeError(f"the {what} coordinates are required")
        value = np.asarray(value, dtype=float).ravel()
        if n is not None and len(value) != n:
            raise ValueError(f"{what} has {len(value)} values, expected {n}")
        return value

    def get_xy(self, item):
        return item.positions(), None

    def set_xy(self, item, x, y):
        """set_xy(item, positions (N, 3), None) replaces the data. A 1-D
        (x, y) pair -- console.py's filter refresh of a source-backed series
        sends one, for the visible rows only -- replaces the x and y of
        every entry when it has one value per entry, and is otherwise
        ignored: a 3D item applies its source's visibility itself."""
        if y is None:
            item.set_positions(x)
            return
        x, y = np.asarray(x, dtype=float).ravel(), np.asarray(y, dtype=float).ravel()
        xyz = np.array(item.positions(), copy=True)
        if len(x) == len(y) == len(xyz):
            xyz[:, 0], xyz[:, 1] = x, y
            item.set_positions(xyz)

    @staticmethod
    def _entry_rows(series, n):
        rows = series.rows
        return np.arange(n) if rows is None or len(rows) != n else np.asarray(rows)

    def rows_in_rect(self, item, series, rect):
        vb = item.view3d()
        if vb is None or not item.isVisible():
            return np.zeros(0, dtype=np.intp)
        sx, sy, front = vb.projected(item)
        inside = np.zeros(len(sx), dtype=bool)
        inside[rows_in_screen_rect(sx, sy, front, rect)] = True
        visible = item.visible_entries()
        if visible is not None:
            inside &= visible
        return self._entry_rows(series, len(sx))[inside]

    def show_rows(self, item, series, rows, highlight):
        vb = item.view3d()
        rows = np.asarray(rows, dtype=np.intp)
        if vb is None or rows.size == 0:
            return None
        n = len(item.positions())
        mask = np.isin(self._entry_rows(series, n), rows)
        visible = item.visible_entries()
        if visible is not None:
            mask &= visible
        if not mask.any():
            return None
        hl = highlight if isinstance(highlight, Brush3DOverlay) else Brush3DOverlay()
        hl.source_item, hl.entry_mask = item, mask
        hl.refresh(vb)
        return hl


# -- the cell ----------------------------------------------------------------------
class View3DBox(pg.ViewBox):
    """The ViewBox of a 3D cell: shows the rendered scene as a pixmap
    filling its view, keeps its view range pinned to its own pixels, and
    turns mouse drags into camera moves. See the module docstring."""
    BOX_COLOR = (0.62, 0.62, 0.62, 1.0)

    # A drag-a-rectangle zoom (Zoom Rect mode) this small never zooms --
    # treated as a near-click, same spirit as a 2D rect zoom's own
    # negligible-drag handling elsewhere in the app.
    MIN_ZOOM_RECT_PX = 4

    def __init__(self):
        self._pinned = False
        super().__init__(invertY=True, defaultPadding=0.0, enableMenu=True)
        self.camera = Camera()
        self._auto_fit = True       # refit to the data until the user moves the camera
        # The figure's current interaction mode ('select'/'hand'/'zoom'/
        # 'rotate'/'brush'), kept in sync by ViewOpsMixin._apply_view_mouse_mode
        # (called on every mode change AND on this cell's own construction,
        # via add_subplot) -- mouseDragEvent reads it to pick orbit vs. a
        # real rectangle zoom (R4-3D). Harmless default: _mouse_on() already
        # gates every drag on the mouse-enabled state, which Select/Brush
        # modes turn off regardless of this attribute.
        self.interaction_mode = 'select'
        self.render_count = 0
        self.last_backend = None
        self._proj_cache = weakref.WeakKeyDictionary()   # item -> (key, (sx, sy, front))
        # The Series3DItems shown here. Kept here, not read from addedItems:
        # ViewBox only lists items that count for its bounds, and ours don't.
        self._series_items = []
        self._box = (None, None)    # (bounds it was built for, its Primitive)
        self.image_item = QtWidgets.QGraphicsPixmapItem()
        self.image_item.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self.addItem(self.image_item, ignoreBounds=True)
        self.image_item.setZValue(-1)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.render_now)
        self.sigResized.connect(self._on_resized)
        self._pinned = True
        self.setRange()
        self.request_render()

    # -- the pinned pixel range: every range change lands on (0, 0)-(w, h)
    def _view_size(self):
        r = self.rect()
        return max(r.width(), 1.0), max(r.height(), 1.0)

    def setRange(self, rect=None, xRange=None, yRange=None, padding=None, update=True,
                 disableAutoRange=True):
        """Pinned: whatever asks (pan, zoom, auto-range, a linked view, Fit),
        the view stays this cell's own pixels. Camera moves replace pan/zoom."""
        if not self._pinned:
            return super().setRange(rect, xRange, yRange, padding, update, disableAutoRange)
        w, h = self._view_size()
        return super().setRange(xRange=(0, w), yRange=(0, h), padding=0, update=update,
                                disableAutoRange=True)

    def linkView(self, axis, view):
        """A 3D cell never follows another view's range (Link X)."""
        super().linkView(axis, None)

    def autoRange(self, *args, **kwargs):
        """Home / "View All": refit the camera to the data."""
        self.reset_camera()

    def _on_resized(self):
        self.setRange()
        self.request_render()

    # -- camera
    def camera_state(self):
        return self.camera.state()

    def set_camera_state(self, state):
        self.camera.set_state(state)
        self._auto_fit = False
        self.request_render()

    def reset_camera(self):
        self._auto_fit = True
        self._fit_camera()
        self.request_render()

    def camera_changed(self):
        """Call after moving self.camera directly (the mouse handlers do)."""
        self._auto_fit = False
        self.request_render()

    def set_view_preset(self, preset):
        """The subplot menu's 4 camera-view entries (R4-3D)."""
        self.camera.look_along(preset)
        self.camera_changed()

    def set_projection(self, projection):
        """The subplot menu's Projection submenu (R4-3D)."""
        if projection not in ('perspective', 'orthographic'):
            raise ValueError(f"unknown projection {projection!r}")
        self.camera.projection = projection
        self.camera.version += 1
        self.camera_changed()

    def _items3d(self, visible_only=True):
        return [it for it in self._series_items if it.isVisible() or not visible_only]

    def overlays(self):
        """The brush highlights RectBrush added to this cell."""
        return [it for it in self.childGroup.childItems() if isinstance(it, Brush3DOverlay)]

    def _data_bounds(self):
        found = [b for b in (it.bounds() for it in self._items3d()) if b is not None]
        if not found:
            return None
        return (np.min([lo for lo, _ in found], axis=0), np.max([hi for _, hi in found], axis=0))

    def _fit_camera(self):
        bounds = self._data_bounds()
        if bounds is not None:
            self.camera.fit(*bounds)

    def data_changed(self, refit=False):
        if refit and self._auto_fit:
            self._fit_camera()
        self.request_render()

    def addItem(self, item, *args, **kwargs):
        super().addItem(item, *args, **kwargs)
        if isinstance(item, Series3DItem) and item not in self._series_items:
            self._series_items.append(item)
            self.data_changed(refit=True)

    def removeItem(self, item):
        super().removeItem(item)
        if item in self._series_items:
            self._series_items.remove(item)
            self.request_render()

    # -- mouse: drags and the wheel move the camera (Hand/Zoom Rect modes;
    # Select mode and brushing disable the mouse, as they disable 2D pan)
    def _mouse_on(self):
        return any(self.state['mouseEnabled'])

    def mouseDragEvent(self, ev, axis=None):
        ev.accept()
        if not self._mouse_on():
            return
        # Zoom Rect mode (R4-3D): a left-drag draws a rectangle and zooms
        # into it on release, instead of orbiting -- every other mode
        # (Hand, Rotate + Zoom) keeps exactly the orbit/pan/dolly behavior
        # below, unchanged.
        if self.interaction_mode == 'zoom' and ev.button() == QtCore.Qt.LeftButton:
            self._zoom_rect_drag(ev)
            return
        d = ev.pos() - ev.lastPos()
        dx, dy = d.x(), d.y()
        button = ev.button()
        pan_mods = QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier
        if button == QtCore.Qt.LeftButton and not (ev.modifiers() & pan_mods):
            self.camera.orbit(-dx, dy)
        elif button in (QtCore.Qt.LeftButton, QtCore.Qt.MiddleButton):
            self.camera.pan(dx, dy, 0, self._view_size()[0])
        elif button == QtCore.Qt.RightButton:
            self.camera.wheel(-4.0 * dy)
        else:
            return
        self.camera_changed()

    def _zoom_rect_drag(self, ev):
        """Draw pyqtgraph's own rbScaleBox (styled light gray by
        ViewOpsMixin._apply_view_mouse_mode, same as the 2D Zoom Rect box --
        CLAUDE.md bug #8) while dragging; on release, zoom the camera into
        the rectangle. ev.pos()/ev.buttonDownPos() are already in this
        cell's own pinned pixel space (0, 0)-(w, h) -- the same frame
        mouseDragEvent's orbit/pan math above already uses directly."""
        p1, p2 = ev.buttonDownPos(QtCore.Qt.LeftButton), ev.pos()
        if ev.isFinish():
            self.rbScaleBox.hide()
            self._apply_rect_zoom(QtCore.QRectF(p1, p2).normalized())
        else:
            self.updateScaleBox(p1, p2)

    def _apply_rect_zoom(self, rect):
        """Pan the camera so the rect's center becomes the view center,
        then scale distance by the smaller of the two axis ratios (rect
        size / view size) so nothing inside the rect is cut off. A
        negligible drag (effectively a click) changes nothing."""
        w, h = self._view_size()
        if rect.width() < self.MIN_ZOOM_RECT_PX or rect.height() < self.MIN_ZOOM_RECT_PX:
            return
        center = rect.center()
        self.camera.pan(w / 2.0 - center.x(), h / 2.0 - center.y(), 0.0, w)
        ratio = min(rect.width() / w, rect.height() / h)
        self.camera.dolly_scale(ratio)
        self.camera_changed()

    def wheelEvent(self, ev, axis=None):
        if not self._mouse_on():
            ev.ignore()
            return
        self.camera.wheel(ev.delta())
        ev.accept()
        self.camera_changed()

    # -- projection (brushing), cached per camera state
    def projected(self, item):
        """(sx, sy, in_front) of every entry of `item`, in this cell's
        pixels -- projected once per camera state/size/data version."""
        w, h = self._view_size()
        key = (self.camera.version, w, h, item.data_version)
        cached = self._proj_cache.get(item)
        if cached is not None and cached[0] == key:
            return cached[1]
        xyz = item.positions()
        result = project_to_screen(self.camera.mvp(w, h), xyz[:, 0], xyz[:, 1], xyz[:, 2], w, h)
        self._proj_cache[item] = (key, result)
        return result

    def _refresh_overlays(self):
        for it in self.overlays():
            if it.source_item is not None:
                it.refresh(self)

    # -- rendering, on demand
    def request_render(self):
        """Coalesce: render once on the next event-loop turn."""
        if not self._timer.isActive():
            self._timer.start(0)

    def _device_pixel_ratio(self):
        scene = self.scene()
        views = scene.views() if scene is not None else []
        return float(views[0].devicePixelRatioF()) if views else 1.0

    def _box_primitive(self):
        """The data's bounding box, in gray: orientation for the eye."""
        bounds = self._data_bounds()
        if bounds is None:
            return None
        key = tuple(np.concatenate(bounds))
        if self._box[0] == key:
            return self._box[1]
        lo, hi = bounds
        corners = np.array([[(hi if (i >> k) & 1 else lo)[k] for k in range(3)] for i in range(8)])
        edges = [(i, i | (1 << k)) for i in range(8) for k in range(3) if not (i >> k) & 1]
        self._box = (key, Primitive('lines', corners[np.array(edges).ravel()], self.BOX_COLOR, 1.0))
        return self._box[1]

    def render_now(self):
        """Render the scene now and show it (tests call this directly)."""
        self._timer.stop()
        w, h = self._view_size()
        prims = []
        box = self._box_primitive()
        if box is not None:
            prims.append(box)
        for it in self._items3d():
            prims.extend(it.primitives())
        dpr = self._device_pixel_ratio()
        image, self.last_backend = render_image(
            prims, self.camera.mvp(w, h), w, h, dpr, pg.getConfigOption('background'))
        pix = QtGui.QPixmap.fromImage(image)
        self.image_item.setPixmap(pix)
        self.image_item.setTransform(QtGui.QTransform.fromScale(w / pix.width(), h / pix.height()))
        self.render_count += 1
        self._refresh_overlays()
        self._refresh_axes_cursors()

    def _refresh_axes_cursors(self):
        """Re-project every 'axes'-anchored data-cursor annotation living
        in this cell after every render (so after every camera orbit/pan/
        dolly, since that's what schedules one) -- see AnnotationItem.
        refresh_point's own docstring for why this is what makes a 3D
        cursor follow the camera: an 'axes' anchor here already lives in
        the rendered image's pixel space (this class's own docstring), so
        without this it would keep whatever pixel position it was placed
        at while the image underneath it changes around it. Walks
        childGroup.childItems(), not addedItems (CLAUDE.md's own lesson:
        the latter only lists items counted for autorange bounds)."""
        from .annotations import AnnotationItem
        for child in self.childGroup.childItems():
            if isinstance(child, AnnotationItem) and child.kind == 'cursor' and child.point_ref is not None:
                child.refresh_point()
