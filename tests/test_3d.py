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

"""WP-O: 3D cells (axes_type='3d'), the scatter3d/line3d/surface kinds, and
brushing through the camera projection (view3d.py, kinds/*3d.py, layout.py).

What these tests can and cannot see. The suite runs under
QT_QPA_PLATFORM=offscreen, which has no OpenGL at all on Windows (CLAUDE.md
bug #10), so every 3D cell here renders through the QPainter fallback --
the same projection, drawn by the CPU. Covered headlessly: the camera math
(against the WP-G spike's validated numpy camera and Qt's own QMatrix4x4
recipe), the brush projection, the kinds, the layout/selection/undo
integration with real mouse events, and the fallback's pixels. The GL path
itself is only exercised by test_gl_render_matches_the_projection_on_a_real_context,
which runs a child process on the native platform and reports SKIPPED
(passing) when that has no GL context either.
"""
import importlib.util
import os
import subprocess
import sys
import time

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from lafigure import DataSource, SERIES_KINDS
from lafigure.view3d import Camera, View3DBox, Series3DItem, project_to_screen, rows_in_screen_rect
from tests.helpers import app, m, _mouse, has_border

L = QtCore.Qt.LeftButton
R = QtCore.Qt.RightButton
MID = QtCore.Qt.MiddleButton
NO = QtCore.Qt.NoButton
ALT = QtCore.Qt.AltModifier
CTRL = QtCore.Qt.ControlModifier
PRESS = QtCore.QEvent.MouseButtonPress
MOVE = QtCore.QEvent.MouseMove
RELEASE = QtCore.QEvent.MouseButtonRelease

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _spike():
    """The WP-G spike module, imported from its file (spikes/ is no package)."""
    path = os.path.join(ROOT, 'spikes', 'gl_offscreen_readback.py')
    spec = importlib.util.spec_from_file_location('gl_spike', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _drag(f, a, b, button=L, mods=QtCore.Qt.NoModifier):
    """A real drag. Paced: pyqtgraph's scene drops mouse moves closer than
    1/mouseRateLimit s (10 ms) to the previous one, so a second unpaced
    drag right after another one never becomes a drag event at all."""
    _mouse(f, PRESS, a, button, button=button, mods=mods)
    for t in (0.25, 0.5, 1.0):
        time.sleep(0.012)
        _mouse(f, MOVE, a + (b - a) * t, button, button=NO, mods=mods)
    _mouse(f, RELEASE, b, NO, button=button, mods=mods)


def _brush(f, plot_item, a, b):
    """A real brush drag on plot_item between view points a and b (QPointF)."""
    vb = plot_item.getViewBox()
    _drag(f, vb.mapViewToScene(a), vb.mapViewToScene(b))


def _rect(p):
    return QtCore.QRectF(p.sceneBoundingRect())


def _figure_3d_and_2d():
    """Empty figure: a 3D cell at (0, 0) and a 2D subplot at (0, 1). Both
    show one DataSource: scatter3d of (a, b, c) and a 2D scatter of (a, b)."""
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    rng = np.random.default_rng(1)
    n = 200
    src = DataSource({'a': rng.normal(size=n), 'b': rng.normal(size=n), 'c': rng.normal(size=n)})
    ax3 = f.subplot(0, 0, axes_type='3d', title="3D")
    s3 = ax3.scatter3d(src, x='a', y='b', z='c', name="abc")
    ax2 = f.subplot(0, 1, title="2D")
    s2 = ax2.scatter(src, x='a', y='b', name="ab")
    f._deselect_all()
    app.processEvents()
    return f, ax3.plot_item, ax2.plot_item, s3, s2, src


def _vb(p):
    return p.getViewBox()


def _settle():
    for _ in range(3):
        app.processEvents()


# -- pure numpy: camera, projection, brush -----------------------------------

def test_camera_matches_the_spikes_validated_camera_and_qt():
    """view3d.Camera is the WP-G spike's camera (validated there against
    real rendered pixels), unchanged: same MVP after the same orbit/pan/
    wheel moves, and both match Qt's QMatrix4x4 recipe."""
    spike = _spike()
    ours = Camera(center=(1.0, -2.0, 0.5), distance=17.0, elevation=12.0, azimuth=-33.0)
    theirs = spike.Camera(center=(1.0, -2.0, 0.5), distance=17.0, elevation=12.0, azimuth=-33.0)
    for _ in range(5):
        for cam in (ours, theirs):
            cam.drag(37.0, -11.0, 'left', 800)
            cam.drag(15.0, 9.0, 'middle', 800)
            cam.wheel(120)
    assert np.allclose(ours.mvp(800, 600), theirs.mvp(800, 600), rtol=0, atol=1e-12)
    assert np.abs(ours.mvp(800, 600) - theirs.qt_mvp(800, 600)).max() < 1e-4


def test_projection_of_hand_computed_points():
    """Camera straight above the origin (elevation 90, azimuth -90: the view
    matrix is a plain translation by -10 along z), 60 deg fov, 200x200 px.
    Then a point (x, y, z) lands at 100 + 100 * sqrt(3) * (x, -y) / (10 - z)."""
    cam = Camera(center=(0, 0, 0), distance=10.0, elevation=90.0, azimuth=-90.0, fov=60.0)
    pts = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 0, 5), (0, 0, 20)], float)
    sx, sy, front = project_to_screen(cam.mvp(200, 200), pts[:, 0], pts[:, 1], pts[:, 2], 200, 200)
    k = 100 * np.sqrt(3)
    assert np.allclose(sx[:4], [100, 100 + k / 10, 100, 100 + k / 5])
    assert np.allclose(sy[:4], [100, 100, 100 - k / 10, 100])
    assert list(front) == [True, True, True, True, False], "z=20 is behind the camera"


def test_brush_rows_in_a_screen_rect_for_hand_constructed_points():
    cam = Camera(center=(0, 0, 0), distance=10.0, elevation=90.0, azimuth=-90.0, fov=60.0)
    pts = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 0, 5), (0, 0, 20)], float)
    proj = project_to_screen(cam.mvp(200, 200), pts[:, 0], pts[:, 1], pts[:, 2], 200, 200)
    # x in [110, 140], y in [90, 110]: (1,0,0) at 117.3 and (1,0,5) at 134.6.
    rows = rows_in_screen_rect(*proj, QtCore.QRectF(QtCore.QPointF(110, 90), QtCore.QPointF(140, 110)))
    assert list(rows) == [1, 3]
    everything = rows_in_screen_rect(*proj, QtCore.QRectF(-1e6, -1e6, 2e6, 2e6))
    assert list(everything) == [0, 1, 2, 3], "a point behind the camera is never brushed"


def test_the_3d_kinds_are_registered_with_their_capabilities():
    for name in ('scatter3d', 'line3d', 'surface'):
        assert name in SERIES_KINDS, name
    assert 'brush' in SERIES_KINDS['scatter3d'].capabilities
    assert 'brush' in SERIES_KINDS['line3d'].capabilities
    assert 'brush' not in SERIES_KINDS['surface'].capabilities, "a surface's vertices aren't rows"
    for name in ('scatter3d', 'line3d', 'surface'):
        assert not {'fft', 'remove_average', 'fit'} & SERIES_KINDS[name].capabilities


# -- the 3D cell in the layout ---------------------------------------------------

def test_add_subplot_3d_is_a_cell_with_a_box_and_a_rendered_image():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    try:
        f.add_subplot(0, 0, axes_type='polar')
    except NotImplementedError:
        pass
    else:
        raise AssertionError("an unknown axes_type must still raise NotImplementedError")
    p = f.add_subplot(0, 0, axes_type='3d', title="cloud")
    q = f.add_subplot(0, 1)
    assert p.axes_type == '3d' and q.axes_type == 'cartesian'
    vb = _vb(p)
    assert isinstance(vb, View3DBox) and not isinstance(_vb(q), View3DBox)
    assert f.boxes[p] == (0, 0, 1, 1) and p in f.z_order and p in f.plots
    assert p in f._brushers, "the 3D cell gets its RectBrush like any subplot"
    assert not p.getAxis('left').isVisible() and not p.getAxis('bottom').isVisible()
    vb.render_now()
    # No GL under offscreen (bug #10): the QPainter fallback draws instead.
    assert vb.last_backend in ('gl', 'painter')
    pix = vb.image_item.pixmap()
    assert not pix.isNull()
    w, h = vb.width(), vb.height()
    assert abs(vb.image_item.sceneBoundingRect().width() - vb.sceneBoundingRect().width()) < 1
    (x0, x1), (y0, y1) = vb.viewRange()
    assert (x0, y0) == (0, 0) and abs(x1 - w) < 1e-6 and abs(y1 - h) < 1e-6, \
        "view coordinates are the cell's own pixels"
    f.close()


def test_a_3d_cell_is_only_ever_built_by_add_subplot():
    """add_subplot's guard (test_layout.py) counts PlotItem( calls; a 3D
    cell is that same call with viewBox=View3DBox(). A View3DBox built
    anywhere else would be a 3D cell bypassing add_subplot."""
    import glob
    import re
    package_dir = os.path.dirname(m.__file__)
    sites = {}
    for path in glob.glob(os.path.join(package_dir, '**', '*.py'), recursive=True):
        with open(path, encoding='utf-8') as fh:
            n = len(re.findall(r'(?<!class )View3DBox\(\)', fh.read()))
        if n:
            sites[os.path.relpath(path, package_dir)] = n
    assert sites == {'layout.py': 1}, sites


def test_a_3d_cell_is_selected_resized_and_swapped_with_real_mouse_events():
    f, p3, p2, s3, s2, src = _figure_3d_and_2d()
    center = _vb(p3).sceneBoundingRect().center()
    _mouse(f, PRESS, center, L)
    _mouse(f, RELEASE, center, NO)
    assert f.selected_plots == [p3] and has_border(p3), "a real click selects the 3D cell"
    before2 = _rect(p2)
    w0 = _rect(p3).width()
    handle = f.resize_handles['right']
    assert handle.isVisible()
    start = handle.sceneBoundingRect().center()
    n_undo = len(f.undo_stack)
    _drag(f, start, start + QtCore.QPointF(-80, 0), mods=ALT)
    assert abs(_rect(p3).width() - (w0 - 80)) < 0.5
    assert _rect(p2) == before2, "the neighbor's real geometry is untouched (bug #6)"
    assert len(f.undo_stack) == n_undo + 1
    _settle()
    vb = _vb(p3)
    assert abs(vb.viewRange()[0][1] - vb.width()) < 1e-6, "the pixel range follows the new size"
    assert abs(vb.image_item.sceneBoundingRect().width() - vb.sceneBoundingRect().width()) < 1, \
        "re-rendered at the new size"
    f.undo()
    assert abs(_rect(p3).width() - w0) < 0.5
    b3, b2 = f.boxes[p3], f.boxes[p2]
    _mouse(f, PRESS, center, L)
    _mouse(f, RELEASE, center, NO)
    _drag(f, f.move_handle.sceneBoundingRect().center(), _vb(p2).sceneBoundingRect().center(), mods=CTRL)
    assert f.boxes[p3] == b2 and f.boxes[p2] == b3, "Ctrl+drop swaps a 3D cell with a 2D one"
    f.undo()
    assert f.boxes[p3] == b3 and f.boxes[p2] == b2
    f.send_to_back(p3)
    assert f.z_order[0] is p3
    f.close()


def test_orbit_pan_and_dolly_with_real_mouse_events_in_hand_mode_only():
    f, p3, p2, s3, s2, src = _figure_3d_and_2d()
    vb = _vb(p3)
    cam = vb.camera
    c = vb.sceneBoundingRect().center()
    az, el, dist, center = cam.azimuth, cam.elevation, cam.distance, cam.center.copy()
    # Select mode: a drag in the data area is a rubber band, never an orbit.
    _drag(f, c, c + QtCore.QPointF(60, 20))
    assert (cam.azimuth, cam.elevation) == (az, el)
    f.set_interaction_mode('hand')
    _drag(f, c, c + QtCore.QPointF(60, 20))
    assert cam.azimuth != az and cam.elevation != el, "left drag orbits"
    (x0, x1), (y0, y1) = vb.viewRange()
    assert (x0, y0) == (0, 0) and abs(x1 - vb.width()) < 1e-6, "and never pans the pixel range"
    _drag(f, c, c + QtCore.QPointF(40, 0), button=MID)
    assert not np.allclose(cam.center, center), "middle drag pans"
    _drag(f, c, c + QtCore.QPointF(0, -40), button=R)
    assert cam.distance < dist, "right drag up dollies in"
    d1 = cam.distance
    view = f.layout_widget
    local = QtCore.QPointF(view.mapFromScene(c))
    wheel = QtGui.QWheelEvent(local, QtCore.QPointF(view.viewport().mapToGlobal(local.toPoint())),
                              QtCore.QPoint(), QtCore.QPoint(0, 120), NO, QtCore.Qt.NoModifier,
                              QtCore.Qt.NoScrollPhase, False)
    QtWidgets.QApplication.sendEvent(view.viewport(), wheel)
    app.processEvents()
    assert cam.distance < d1, "the wheel dollies"
    f.close()


def test_renders_on_demand_only():
    """Spike condition 1: re-render on a camera/data/size change, never per frame."""
    f, p3, p2, s3, s2, src = _figure_3d_and_2d()
    vb = _vb(p3)
    _settle()
    n = vb.render_count
    for _ in range(5):
        app.processEvents()
    assert vb.render_count == n, "nothing changed: no render"
    for _ in range(4):
        vb.camera.orbit(3, 0)
        vb.camera_changed()
    _settle()
    assert vb.render_count == n + 1, "several changes before the event loop runs: one render"
    f.close()


def test_the_fallback_draws_each_point_where_the_projection_says():
    """Offscreen: the QPainter fallback. A few isolated points must light
    the pixel their numpy projection names, and the background stays clear
    halfway between them."""
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    ax = f.subplot(0, 0, axes_type='3d')
    g = np.array([-2.0, 2.0])
    pts = np.array(np.meshgrid(g, g, g, indexing='ij')).reshape(3, -1).T
    s = ax.scatter3d(pts[:, 0], pts[:, 1], z=pts[:, 2], pen=(0, 0, 0), size=5)
    vb = _vb(ax.plot_item)
    vb.render_now()
    img = vb.image_item.pixmap().toImage()
    sx_scale = img.width() / vb.width()
    sx, sy, front = vb.projected(s.item)
    assert front.all()
    bg = QtGui.QColor(img.pixel(1, 1))
    for x, y in zip(sx, sy):
        c = QtGui.QColor(img.pixel(int(x * sx_scale), int(y * sx_scale)))
        assert c.lightness() < 100, f"no point drawn at its projection ({x:.0f}, {y:.0f})"
    assert bg.lightness() > 200
    f.close()


# -- series on a 3D cell ------------------------------------------------------------

def test_3d_series_data_model_and_to_dict_round_trip():
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0, axes_type='3d')
    t = np.linspace(0, 4 * np.pi, 50)
    s = ax.line3d(np.cos(t), np.sin(t), z=t, name="helix", pen=(200, 0, 0))
    assert s.kind == 'line3d' and s.x.shape == (50, 3) and s.y is None
    assert np.allclose(s.x[:, 2], t)
    assert isinstance(s.item, Series3DItem) and s.item in ax.plot_item.listDataItems()
    assert [x.item for x in ax.series] == [s.item]
    d = s.to_dict()
    s2 = f._add_series_from_dict(ax.plot_item, d)
    assert np.array_equal(s2.x, s.x) and s2.name == "helix"
    X, Y = np.linspace(-1, 1, 7), np.linspace(-2, 2, 5)
    Z = np.add.outer(X ** 2, Y)
    surf = ax.surface(X, Y, z=Z)
    assert surf.x.shape == (35, 3) and np.allclose(surf.x[:, 2], Z.ravel())
    surf2 = f._add_series_from_dict(ax.plot_item, surf.to_dict())
    assert np.array_equal(surf2.x, surf.x)
    ax2 = f.subplot(0, 1)
    try:
        ax2.scatter3d([1, 2], [3, 4], z=[5, 6])
    except ValueError:
        pass
    else:
        raise AssertionError("a 3D kind on a 2D subplot must refuse clearly")
    f.close()


def test_toggle_legend_and_group_recolor_work_on_a_3d_cell():
    f, p3, p2, s3, s2, src = _figure_3d_and_2d()
    f._on_plot_clicked(p3)
    f.toggle_legend()
    assert p3.legend is not None
    app.processEvents()
    s3.item.setPen(pg.mkPen((255, 0, 0)))
    assert pg.mkPen(s3.item.opts['pen']).color().red() == 255
    f.close()


# -- brushing: 3D <-> 2D through the shared DataSource ---------------------------------

def test_brushing_the_3d_view_selects_the_same_rows_on_the_2d_plot():
    f, p3, p2, s3, s2, src = _figure_3d_and_2d()
    f.toggle_brush(True)
    vb = _vb(p3)
    w, h = vb.width(), vb.height()
    rect = QtCore.QRectF(QtCore.QPointF(0.4 * w, 0.4 * h), QtCore.QPointF(0.6 * w, 0.6 * h))
    xyz = np.column_stack([src['a'], src['b'], src['c']])
    expected = rows_in_screen_rect(*project_to_screen(vb.camera.mvp(w, h), xyz[:, 0], xyz[:, 1],
                                                      xyz[:, 2], w, h), rect)
    assert 0 < expected.size < len(src), "control: the rect catches some rows, not all"
    _brush(f, p3, rect.topLeft(), rect.bottomRight())
    got3 = f._brushers[p3].selection.get(s3.item)
    assert got3 is not None and np.array_equal(got3, expected), "rows under the rect, by projection"
    got2 = f._brushers[p2].selection.get(s2.item)
    assert got2 is not None and np.array_equal(got2, expected), "the 2D plot shows the same rows"
    overlays = vb.overlays()
    assert len(overlays) == 1 and len(overlays[0].data) == expected.size
    f.close()


def test_brushing_the_2d_plot_highlights_the_rows_in_3d_and_follows_the_camera():
    f, p3, p2, s3, s2, src = _figure_3d_and_2d()
    f.toggle_brush(True)
    a, b = np.asarray(src['a']), np.asarray(src['b'])
    _brush(f, p2, QtCore.QPointF(0, 0), QtCore.QPointF(1.5, 1.5))
    # Control: the 2D brush itself (to within the pixel rounding of a real drag).
    expected = f._brushers[p2].selection[s2.item]
    assert expected.size and np.all((a[expected] > -0.05) & (a[expected] < 1.55)
                                    & (b[expected] > -0.05) & (b[expected] < 1.55))
    assert np.array_equal(f._brushers[p3].selection[s3.item], expected), "linked into the 3D view"
    vb = _vb(p3)
    overlay = vb.overlays()[0]
    sx, sy, _ = vb.projected(s3.item)
    assert np.allclose(overlay.data['x'], sx[expected]) and np.allclose(overlay.data['y'], sy[expected])
    vb.camera.orbit(40, -10)
    vb.camera_changed()
    _settle()
    sx, sy, _ = vb.projected(s3.item)
    assert np.allclose(overlay.data['x'], sx[expected]), "the highlight follows an orbit"
    f.close()


def test_hide_brushed_points_stops_drawing_them_in_3d_and_undoes():
    f, p3, p2, s3, s2, src = _figure_3d_and_2d()
    f.toggle_brush(True)
    _brush(f, p2, QtCore.QPointF(0, 0), QtCore.QPointF(1.5, 1.5))
    n_brushed = f._brushers[p2].selection[s2.item].size
    assert s3.item.drawn_count() == len(src)
    f.hide_brushed_points()
    assert s3.item.drawn_count() == len(src) - n_brushed
    assert len(s3.x) == len(src), "the 3D series keeps every row; hiding is only drawing"
    f.undo()
    assert s3.item.drawn_count() == len(src)
    src.filter("a > 0")
    assert s3.item.drawn_count() == int((np.asarray(src['a']) > 0).sum()), "src.filter reaches 3D too"
    src.filter(None)
    f.close()


# -- undo, Home, Link X ---------------------------------------------------------------

def test_deleting_and_undoing_a_3d_cell_keeps_its_kind_series_and_camera():
    f, p3, p2, s3, s2, src = _figure_3d_and_2d()
    vb = _vb(p3)
    vb.camera.orbit(25, 5)
    vb.camera_changed()
    state = vb.camera_state()
    box = f.boxes[p3]
    data = s3.x.copy()
    f.delete_subplot(p3)
    assert p3 not in f.plots
    f.undo()
    new = [p for p in f.plots if p is not p2][0]
    assert new.axes_type == '3d' and isinstance(_vb(new), View3DBox) and f.boxes[new] == box
    restored = f._series_on(new)
    assert [s.kind for s in restored] == ['scatter3d'] and np.array_equal(restored[0].x, data)
    assert restored[0].source is src, "still linked to its DataSource"
    assert _vb(new).camera_state() == state
    f.close()


def test_home_refits_the_camera_and_link_x_leaves_the_3d_range_alone():
    f, p3, p2, s3, s2, src = _figure_3d_and_2d()
    vb = _vb(p3)
    fitted = vb.camera_state()
    vb.camera.orbit(60, 20)
    vb.camera.wheel(500)
    vb.camera_changed()
    f._hover_plot = p3
    f.reset_view()
    assert vb.camera_state() == fitted, "Home = the fitted camera"
    f.toggle_link_x(True)   # p3 is plots[0]: the reference
    f._hover_plot = p2
    f.reset_view()
    (x0, x1), _ = vb.viewRange()
    assert x0 == 0 and abs(x1 - vb.width()) < 1e-6
    f.toggle_link_x(False)
    f.close()


# -- real GL, environment-dependent ---------------------------------------------------

def test_gl_render_matches_the_projection_on_a_real_context():
    """ENVIRONMENT-DEPENDENT. Runs tests/gl_check_3d.py in a child process
    on the native Qt platform (never shown on screen). There, if a real GL
    context exists, a 3D cell must render through GL and every projected
    point must land on a lit pixel, before and after a real mouse orbit.
    Prints SKIPPED and passes when the native platform has no GL either
    (e.g. a headless CI box) -- then only the fallback path was tested."""
    env = dict(os.environ)
    env.pop('QT_QPA_PLATFORM', None)
    env.pop('LAFIGURE_3D_BACKEND', None)
    proc = subprocess.run([sys.executable, os.path.join(ROOT, 'tests', 'gl_check_3d.py')],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    out = proc.stdout + proc.stderr
    if proc.returncode == 2 and 'NO-GL' in out:
        print("    SKIPPED (no GL context on the native platform):", out.strip().splitlines()[-1:])
        return
    assert proc.returncode == 0, out
    assert 'GL-OK' in out, out


# -- coordinator additions: the three cross-file diffs O reported, applied
# after this package merged (clip_ops.py, view_ops.py, series.py) --------

def test_copy_paste_a_3d_subplot_into_another_window_keeps_kind_and_camera():
    """The clip_ops.py diff: copy_subplot/paste_subplot now carry
    axes_type/view_state, so a pasted 3D cell stays 3D (not a plain 2D
    PlotItem) with its camera and DataSource link intact, even across
    separate LaFigure windows."""
    f, p3, p2, s3, s2, src = _figure_3d_and_2d()
    vb = _vb(p3)
    vb.camera.orbit(15, -10)
    vb.camera_changed()
    state = vb.camera_state()
    f._on_plot_clicked(p3)
    f.copy_subplot()

    f2 = m.LaFigure(empty=True)
    f2.paste_subplot()
    new = f2.plots[-1]
    assert new.axes_type == '3d' and isinstance(_vb(new), View3DBox)
    assert _vb(new).camera_state() == state
    (pasted,) = f2._series_on(new)
    assert pasted.kind == 'scatter3d' and pasted.source is src
    f.close()
    f2.close()


def test_link_x_skips_a_3d_cell_that_is_not_the_reference():
    """The view_ops.py diff filters 3D out of BOTH ends of _apply_link_x --
    this specifically covers the case the merged test suite didn't yet: a
    2D reference (plots[0]) linking a second 2D plot while a 3D cell sits
    elsewhere in the same figure. Before the fix, the follower loop would
    have called p.setXLink(reference) on the 3D cell too."""
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    p_ref = f.add_subplot(row=0, col=0)
    p_ref.plot([0, 10], [0, 1])
    p_2d = f.add_subplot(row=0, col=1)
    p_2d.plot([0, 10], [0, 1])
    ax3 = f.subplot(1, 0, axes_type='3d', title="3D")
    vb3 = _vb(ax3.plot_item)
    fitted = vb3.camera_state()

    f.toggle_link_x(True)
    assert p_2d.getViewBox().state['linkedViews'][0]() is p_ref.getViewBox()
    assert vb3.camera_state() == fitted, "the 3D cell must be untouched by linking"
    f.toggle_link_x(False)
    f.close()


def test_a_plain_array_3d_series_source_has_xyz_columns():
    """The optional series.py diff: Series.source's private-DataSource
    branch used to hand a (N, 3) array straight to DataSource as if it
    were a single 1-D column, which raised. A 3D kind's get_xy returns
    (positions, None) -- now split into x/y/z columns."""
    f = m.LaFigure(empty=True)
    ax3 = f.subplot(0, 0, axes_type='3d')
    xyz = np.array([[0.0, 1.0, 2.0], [3.0, 4.0, 5.0], [6.0, 7.0, 8.0]])
    s = ax3.scatter3d(xyz[:, 0], xyz[:, 1], z=xyz[:, 2])
    src = s.source
    assert set(src.columns) >= {'x', 'y', 'z'}
    assert np.array_equal(src['x'], xyz[:, 0])
    assert np.array_equal(src['y'], xyz[:, 1])
    assert np.array_equal(src['z'], xyz[:, 2])
    f.close()
