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

"""R4-3D: a 5th interaction mode "Rotate + Zoom" (view_ops.py) holding
today's 3D camera behavior, enabled only while a 3D subplot is focused;
Zoom Rect mode becomes a real drag-a-rectangle zoom on a 3D cell
(view3d.py); a 3D subplot's right-click menu gains 4 camera-view presets
(shown only in Rotate + Zoom mode) and a Projection submenu, and loses FFT
(menus.py); a 2D subplot's menu gains a Scale (X/Y linear/log) submenu,
hidden for 3D.

toolbar.py is coordinator-owned (see PLAN.md); the Rotate + Zoom button
itself is a reported diff, not built here. _add_rotate_action below stands
in for it -- a checkable QAction wired exactly like the toolbar's own
mode buttons (action()'s pattern in toolbar.py) and added to the real
Select/Hand/Zoom/Brush QActionGroup, so exclusivity is genuinely tested,
not assumed.
"""
import logging
import time

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from lafigure.view3d import Camera, View3DBox, project_to_screen
from tests.helpers import app, m, _mouse

L = QtCore.Qt.LeftButton
NO = QtCore.Qt.NoButton
PRESS = QtCore.QEvent.MouseButtonPress
MOVE = QtCore.QEvent.MouseMove
RELEASE = QtCore.QEvent.MouseButtonRelease


class _ListLogHandler(logging.Handler):
    """Same small caplog-equivalent CLAUDE.md's round-3 packages built
    (this project has no pytest) -- a fresh instance per test, attached/
    detached around the assertion."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _drag(f, a, b, button=L, mods=QtCore.Qt.NoModifier):
    """A real, paced drag (CLAUDE.md bug #17: pyqtgraph's GraphicsScene
    drops a move closer than 10ms to the previous one) -- same recipe as
    tests/test_3d.py's own _drag and tests/helpers._band_drag."""
    _mouse(f, PRESS, a, button, button=button, mods=mods)
    for t in (0.25, 0.5, 1.0):
        time.sleep(0.012)
        _mouse(f, MOVE, a + (b - a) * t, button, button=NO, mods=mods)
    _mouse(f, RELEASE, b, NO, button=button, mods=mods)


def _add_rotate_action(f):
    """Stand-in for toolbar.py's reported diff: a checkable QAction in the
    same exclusive mode group as Select/Hand/Zoom/Brush."""
    act = QtGui.QAction("Rotate + Zoom", f)
    act.setCheckable(True)
    act.triggered.connect(lambda checked: f.set_interaction_mode('rotate'))
    group = f.zoom_action.actionGroup()
    if group is not None:
        group.addAction(act)
    f.rotate_action = act
    f._update_rotate_action_enabled()
    return act


def _figure_2d_and_3d():
    """An empty figure: a 2D line subplot at (0, 0), a 3D scatter cell at
    (0, 1). Shown, so geometry is real."""
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    p2 = f.add_subplot(row=0, col=0, title="2D")
    p2.plot([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0])
    ax3 = f.subplot(0, 1, axes_type='3d', title="3D")
    xyz = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [-1.0, 0.5, 2.0], [2.0, -1.0, 0.5]])
    ax3.scatter3d(xyz[:, 0], xyz[:, 1], z=xyz[:, 2])
    f._deselect_all()
    app.processEvents()
    return f, p2, ax3.plot_item


def _vb(p):
    return p.getViewBox()


def _menu_actions(f, plot_item):
    """Right-click the center of plot_item's data area with real mouse
    events, and return its (already-shown) vb.menu -- mirrors
    test_view_ops.py's test_toggle_legend_via_the_real_subplot_menu_...,
    which found ViewBox.raiseContextMenu uses menu.popup() (non-blocking),
    so nothing needs stubbing."""
    vb = _vb(plot_item)
    pt = vb.sceneBoundingRect().center()
    R = QtCore.Qt.RightButton
    _mouse(f, PRESS, pt, R, button=R)
    _mouse(f, RELEASE, pt, NO, button=R)
    menu = vb.menu
    menu.close()
    return menu


def _close_menus():
    for w in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(w, QtWidgets.QMenu):
            w.close()


# -- 1/2: the mode itself, and its enabled state following focus -------------

def test_rotate_action_enabled_only_for_a_3d_focused_subplot():
    f, p2, p3 = _figure_2d_and_3d()
    act = _add_rotate_action(f)
    f.focused_plot = p2
    assert not act.isEnabled()
    f.focused_plot = p3
    assert act.isEnabled()
    f.focused_plot = p2
    assert not act.isEnabled()
    f.close()


def test_rotate_mode_switches_to_zoom_when_focus_leaves_every_3d_subplot():
    f, p2, p3 = _figure_2d_and_3d()
    _add_rotate_action(f)
    f.focused_plot = p3
    f.set_interaction_mode('rotate')
    assert f.interaction_mode == 'rotate'
    f.focused_plot = p2
    assert f.interaction_mode == 'zoom', "the user's explicit rule"
    assert f.zoom_action.isChecked()
    f.close()


def test_rotate_mode_keeps_pan_enabled_and_is_exclusive_with_the_other_modes():
    f, p2, p3 = _figure_2d_and_3d()
    act = _add_rotate_action(f)
    f.focused_plot = p3
    act.trigger()
    assert f.interaction_mode == 'rotate'
    assert not f.zoom_action.isChecked() and not f.select_action.isChecked()
    assert all(p.getViewBox().state['mouseEnabled'] == [True, True] for p in f.plots)
    f.select_action.trigger()
    assert f.interaction_mode == 'select' and not act.isChecked()
    f.close()


def test_rotate_mode_has_a_distinct_drawn_cursor():
    f, p2, p3 = _figure_2d_and_3d()
    _add_rotate_action(f)
    f.focused_plot = p3
    f.set_interaction_mode('rotate')
    cursor = _vb(p3).cursor()
    assert cursor.shape() == QtCore.Qt.BitmapCursor
    assert not cursor.pixmap().isNull() and cursor.pixmap().width() > 0
    f.close()


def test_rotate_mode_change_is_logged_like_every_other_mode():
    f, p2, p3 = _figure_2d_and_3d()
    _add_rotate_action(f)
    f.focused_plot = p3
    logger = logging.getLogger('lafigure')
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    handler = _ListLogHandler()
    logger.addHandler(handler)
    try:
        f.set_interaction_mode('rotate')
        assert any('rotate' in msg for msg in handler.messages), handler.messages
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    f.close()


# -- 3/4: a real drag on a 3D cell in rotate vs. zoom mode, and undo ---------

def test_rotate_mode_drag_orbits_and_zoom_mode_drag_rect_zooms_with_undo():
    f, p2, p3 = _figure_2d_and_3d()
    _add_rotate_action(f)
    f.focused_plot = p3
    vb = _vb(p3)
    cam = vb.camera
    c = vb.sceneBoundingRect().center()

    f.set_interaction_mode('rotate')
    az0, el0 = cam.azimuth, cam.elevation
    n0 = len(f.undo_stack)
    _drag(f, c, c + QtCore.QPointF(50, 20))
    assert cam.azimuth != az0 and cam.elevation != el0, "rotate mode orbits"
    assert len(f.undo_stack) == n0 + 1, "one undo entry, through the view-history mechanism"

    f.set_interaction_mode('zoom')
    pre_zoom = vb.camera_state()
    az1 = cam.azimuth
    n1 = len(f.undo_stack)
    w, h = vb.width(), vb.height()
    a = vb.mapViewToScene(QtCore.QPointF(0.2 * w, 0.2 * h))
    b = vb.mapViewToScene(QtCore.QPointF(0.5 * w, 0.4 * h))
    assert vb.rbScaleBox.isVisible() is False  # control: not shown before the drag
    _drag(f, a, b)
    assert cam.azimuth == az1, "zoom mode never orbits a 3D cell"
    assert cam.distance < pre_zoom['distance'], "the rect is smaller than the view: zoom in"
    assert not np.allclose(cam.center, pre_zoom['center']), "the camera re-centers on the rect"
    assert len(f.undo_stack) == n1 + 1

    f.undo()
    assert vb.camera_state() == pre_zoom
    f.close()


def test_zoom_rect_box_is_gray_during_a_real_drag_on_a_3d_cell():
    """The same CLAUDE.md bug #8 styling the 2D Zoom Rect box gets
    (ViewOpsMixin._apply_view_mouse_mode), reused for free by a 3D cell's
    own rbScaleBox (view3d.py's _zoom_rect_drag)."""
    f, p2, p3 = _figure_2d_and_3d()
    f.set_interaction_mode('zoom')
    vb = _vb(p3)
    start = vb.sceneBoundingRect().center()
    _mouse(f, PRESS, start, L)
    for d in (5, 20, 40):
        _mouse(f, MOVE, start + QtCore.QPointF(d, d), L, button=NO)
    assert vb.rbScaleBox.isVisible(), "control: the drag really is drawing the zoom box"
    pen, brush = vb.rbScaleBox.pen().color(), vb.rbScaleBox.brush().color()
    assert pen.red() == pen.green() == pen.blue(), "gray, not pyqtgraph's yellow"
    assert brush.red() == brush.green() == brush.blue()
    _mouse(f, RELEASE, start + QtCore.QPointF(40, 40), NO)
    assert not vb.rbScaleBox.isVisible()
    f.close()


def test_a_negligible_zoom_rect_drag_changes_nothing():
    f, p2, p3 = _figure_2d_and_3d()
    f.set_interaction_mode('zoom')
    vb = _vb(p3)
    before = vb.camera_state()
    c = vb.sceneBoundingRect().center()
    _drag(f, c, c + QtCore.QPointF(1, 1))
    assert vb.camera_state() == before
    f.close()


# -- 5: the 4 camera-view presets --------------------------------------------

def test_view_presets_set_the_expected_elevation_and_azimuth_and_undo():
    f, p2, p3 = _figure_2d_and_3d()
    vb = _vb(p3)
    cam = vb.camera
    order = [('xy', 90.0, 0.0), ('xz', 0.0, 90.0), ('yz', 0.0, 0.0), ('sideway', 30.0, 45.0)]
    n0 = len(f.undo_stack)
    for preset, elev, azim in order:
        f._set_3d_view_preset(p3, preset)
        assert (cam.elevation, cam.azimuth) == (elev, azim), preset
    assert len(f.undo_stack) == n0 + len(order)
    initial = (30.0, 45.0)  # Camera()'s own default, and 'sideway'
    for _ in order:
        f.undo()
    assert (cam.elevation, cam.azimuth) == initial
    f.close()


def test_view_presets_match_camera_position_along_the_named_axis():
    """Cross-check Camera.VIEW_PRESETS against camera_position(), the way
    the worker derived them: 'xy' looks down Z (from +Z), 'xz' down Y,
    'yz' down X."""
    for preset, axis in (('xy', 2), ('xz', 1), ('yz', 0)):
        cam = Camera(center=(0.0, 0.0, 0.0), distance=10.0)
        cam.look_along(preset)
        pos = cam.camera_position()
        other_axes = [i for i in range(3) if i != axis]
        assert abs(pos[axis] - 10.0) < 1e-6, (preset, pos)
        for i in other_axes:
            assert abs(pos[i]) < 1e-6, (preset, pos)


def test_view_preset_menu_entries_are_shown_only_in_rotate_mode():
    f, p2, p3 = _figure_2d_and_3d()
    f.focused_plot = p3
    f.set_interaction_mode('zoom')
    menu = _menu_actions(f, p3)
    view_action = next(a for a in menu.actions() if a.text() == "Camera View")
    assert not view_action.isVisible()
    _close_menus()

    # set_interaction_mode('rotate') works with no rotate_action attached
    # at all (_sync_mode_actions's getattr default) -- the toolbar button
    # itself is a reported diff (toolbar.py, coordinator-owned).
    f.set_interaction_mode('rotate')
    menu = _menu_actions(f, p3)
    view_action = next(a for a in menu.actions() if a.text() == "Camera View")
    assert view_action.isVisible()
    _close_menus()
    f.close()


# -- 6: the Projection submenu ------------------------------------------------

def test_projection_submenu_switches_perspective_and_orthographic_and_undoes():
    f, p2, p3 = _figure_2d_and_3d()
    vb = _vb(p3)
    assert vb.camera.projection == 'perspective'
    n = len(f.undo_stack)
    menu = _menu_actions(f, p3)
    proj_menu = next(a for a in menu.actions() if a.text() == "Projection").menu()
    ortho = next(a for a in proj_menu.actions() if a.text() == "Orthographic")
    persp = next(a for a in proj_menu.actions() if a.text() == "Perspective")
    assert persp.isChecked() and not ortho.isChecked()
    ortho.trigger()
    assert vb.camera.projection == 'orthographic'
    assert len(f.undo_stack) == n + 1
    _close_menus()
    menu = _menu_actions(f, p3)
    proj_menu = next(a for a in menu.actions() if a.text() == "Projection").menu()
    assert next(a for a in proj_menu.actions() if a.text() == "Orthographic").isChecked()
    _close_menus()
    f.undo()
    assert vb.camera.projection == 'perspective'
    f.close()


def test_projection_matrices_agree_in_apparent_scale_at_the_focal_distance():
    """Switching perspective<->orthographic must not jump the apparent
    scale of whatever sits at the camera's own focal distance (the
    brief's "sized from distance and fov" requirement) -- tested directly
    on the projection matrices in camera space, independent of pose."""
    cam = Camera(distance=12.0, fov=50.0)
    w, h = 400, 250
    x_edge = cam.distance * np.tan(np.radians(cam.fov / 2))
    z = -cam.distance   # camera space: at the focal distance, in front of the eye
    cam.projection = 'perspective'
    sx_p, sy_p, front_p = project_to_screen(cam.projection_matrix(w, h), x_edge, 0.0, z, w, h)
    cam.projection = 'orthographic'
    sx_o, sy_o, front_o = project_to_screen(cam.projection_matrix(w, h), x_edge, 0.0, z, w, h)
    assert bool(front_p) and bool(front_o)
    assert abs(float(sx_p) - w) < 1e-6, "perspective: this is exactly the frustum edge by construction"
    assert abs(float(sx_o) - float(sx_p)) < 1e-6, "orthographic must land at the same screen edge"
    # And the matrices really did change (m[3, 2] is the perspective divide).
    persp_m = cam.projection_matrix(w, h)
    cam.projection = 'perspective'
    assert cam.projection_matrix(w, h)[3, 2] == -1.0
    cam.projection = 'orthographic'
    assert persp_m[3, 2] == 0.0 and persp_m[3, 3] == 1.0


def test_camera_state_round_trips_projection():
    cam = Camera()
    cam.projection = 'orthographic'
    state = cam.state()
    assert state['projection'] == 'orthographic'
    cam2 = Camera()
    cam2.set_state(state)
    assert cam2.projection == 'orthographic'
    # A state captured before this field existed still restores (a plain
    # dict missing the key, e.g. an old copy/paste payload).
    del state['projection']
    cam3 = Camera()
    cam3.set_state(state)
    assert cam3.projection == 'perspective'


# -- 7: no FFT on a 3D subplot's menu -----------------------------------------

def test_fft_action_hidden_on_a_3d_subplot_menu_and_visible_on_a_2d_one():
    f, p2, p3 = _figure_2d_and_3d()
    menu2 = _menu_actions(f, p2)
    fft2 = next(a for a in menu2.actions() if a.text() == "FFT -> Subplot Below")
    assert fft2.isVisible()
    _close_menus()

    menu3 = _menu_actions(f, p3)
    fft3 = next(a for a in menu3.actions() if a.text() == "FFT -> Subplot Below")
    assert not fft3.isVisible()
    _close_menus()
    f.close()


# -- 6 (Scale submenu, confirmed addition): X/Y linear/log, hidden for 3D ----

def test_scale_submenu_switches_log_mode_and_undoes_and_is_absent_for_3d():
    f, p2, p3 = _figure_2d_and_3d()
    n = len(f.undo_stack)
    menu2 = _menu_actions(f, p2)
    scale_menu = next(a for a in menu2.actions() if a.text() == "Scale").menu()
    x_linear = next(a for a in scale_menu.actions() if a.text() == "X: Linear")
    x_log = next(a for a in scale_menu.actions() if a.text() == "X: Log")
    assert x_linear.isChecked() and not x_log.isChecked()
    assert not p2.ctrl.logXCheck.isChecked()
    x_log.trigger()
    assert p2.ctrl.logXCheck.isChecked()
    assert len(f.undo_stack) == n + 1
    _close_menus()

    menu2b = _menu_actions(f, p2)
    scale_menu = next(a for a in menu2b.actions() if a.text() == "Scale").menu()
    assert next(a for a in scale_menu.actions() if a.text() == "X: Log").isChecked()
    _close_menus()

    f.undo()
    assert not p2.ctrl.logXCheck.isChecked()

    menu3 = _menu_actions(f, p3)
    assert not any(a.text() == "Scale" for a in menu3.actions()), "no Scale submenu for a 3D subplot"
    _close_menus()
    f.close()


def test_scale_submenu_y_axis_also_switches_log_mode():
    f, p2, p3 = _figure_2d_and_3d()
    menu = _menu_actions(f, p2)
    scale_menu = next(a for a in menu.actions() if a.text() == "Scale").menu()
    y_log = next(a for a in scale_menu.actions() if a.text() == "Y: Log")
    assert not p2.ctrl.logYCheck.isChecked()
    y_log.trigger()
    assert p2.ctrl.logYCheck.isChecked()
    assert not p2.ctrl.logXCheck.isChecked(), "X untouched"
    _close_menus()
    f.close()
