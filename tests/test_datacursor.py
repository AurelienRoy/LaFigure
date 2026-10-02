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

"""The data-cursor overhaul (2026-09-29): an oriented selection outline, the
end-handle pulled off the label, live point tracking pinned by a stable
point_ref (row id for a DataSource-backed series, array index for a private
one -- see annotation_ops.py's own docstring on the class of helpers), Z in
a 3D cursor's text, camera-follow on a 3D cell, and removing a cursor whose
own point is brushed-deleted (2D and 3D) as one undo entry with the delete.

point_ref's own resolution -- annotation_ops.py's _plot_data_items_for_ref/
_cursor_ref_item/_cursor_ref_array_index/_row_id, and AnnotationItem.
refresh_point (annotations.py) -- has no public, non-interactive
constructor either, like every other annotation kind (see CLAUDE.md's
examples-scripts note): these tests build one directly via
LaFigure._create_annotation, same as test_annotation_ops.py does.
"""
import numpy as np
from pyqtgraph.Qt import QtCore

from lafigure import DataSource
from lafigure.annotations import ORIENTED_OUTLINE_KINDS
from lafigure.console import datatip_text
from tests.helpers import app, m, FakeClickEvent


def _figure(n_plots=1):
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    axes = [f.subplot(i, 0) for i in range(n_plots)]
    return f, axes


def _brush_rows(f, series, rows, additive=False):
    """Brush exact row ids, as a finished drag on series' subplot would."""
    plot = next(p for p in f.plots if series.item in p.listDataItems())
    f._on_rect_brush_finished(plot, {series.item: np.asarray(rows)}, additive)


def _ramp_source(n=50):
    t = np.arange(n, dtype=float)
    return DataSource({'t': t, 'a': t * 2.0})


class _FakeEv:
    """Minimal stand-in for a QGraphicsSceneMouseEvent, covering only what
    AnnotationItem._cursor_mouse_press/_cursor_mouse_move/_cursor_mouse_release
    read -- same level of directness the data-cursor overhaul's own
    anchor-handle tests used before this feature replaced the handle
    object with these three methods (ann._on_anchor_press(None), etc.)."""
    def __init__(self, scene_pos=None, local_pos=None, modifiers=QtCore.Qt.NoModifier,
                 button=QtCore.Qt.LeftButton):
        self._scene_pos = scene_pos
        self._local_pos = local_pos if local_pos is not None else QtCore.QPointF(0, 0)
        self._modifiers = modifiers
        self._button = button

    def button(self):
        return self._button

    def modifiers(self):
        return self._modifiers

    def scenePos(self):
        return self._scene_pos

    def pos(self):
        return self._local_pos

    def accept(self):
        pass

    def ignore(self):
        pass


def _figure_3d(n=30, seed=0):
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    rng = np.random.default_rng(seed)
    src = DataSource({'a': rng.normal(size=n), 'b': rng.normal(size=n), 'c': rng.normal(size=n)})
    ax = f.subplot(0, 0, axes_type='3d')
    s = ax.scatter3d(src, x='a', y='b', z='c', name="abc")
    f._deselect_all()
    app.processEvents()
    return f, ax.plot_item, s, src


# -- oriented outline / end-handle pullback ---------------------------------

def test_cursor_is_an_oriented_outline_kind_and_not_warped_off_square():
    """Same pattern as lafigure-axes-geometry's own worked example: a
    non-1:1 data scale must not turn the outline's right angles into some
    other angle on screen."""
    assert 'cursor' in ORIENTED_OUTLINE_KINDS
    f, (ax,) = _figure()
    ax.plot_item.getViewBox().setRange(xRange=(0, 1000), yRange=(0, 1), padding=0)
    app.processEvents()
    ann = f._create_annotation('cursor', 'axes', ax.plot_item, QtCore.QPointF(500, 0.5), None, text="x")
    poly = ann._selection_outline_polygon()
    pts = [ann.mapToScene(poly[i]) for i in range(4)]
    v1, v2 = pts[1] - pts[0], pts[2] - pts[1]
    assert abs(v1.x() * v2.x() + v1.y() * v2.y()) < 1e-6, "adjacent edges must stay perpendicular on screen"
    f.close()


def test_cursor_has_no_grab_handles_unlike_every_other_kind():
    """A datacursor has none of the yellow grab-handle objects every other
    annotation kind gets -- its round marker and label text are grabbed
    directly via native hit-testing (_cursor_region_at/_cursor_mouse_press)
    instead, per the Data Cursor mode feature's own design."""
    f, (ax,) = _figure()
    cursor = f._create_annotation('cursor', 'axes', ax.plot_item, QtCore.QPointF(0, 0), None, text="x")
    assert cursor._end_handle is None
    assert cursor._anchor_handle is None
    assert cursor._start_handle is None
    assert cursor._rotate_handle is None
    line = f._create_annotation('line', 'axes', ax.plot_item, QtCore.QPointF(0, 0), QtCore.QPointF(1, 1))
    assert line._end_handle is not None, "every other kind keeps its handles"
    f.close()


# -- 2D point tracking -------------------------------------------------------

def test_cursor_point_ref_tracks_value_edits_automatically_via_the_undo_hook():
    """Any undoable action funnels through history.py's _push_history/
    undo/redo, which is where the blanket, best-effort resync lives -- so a
    cursor stays on its point without anything having to call
    refresh_point() by hand."""
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    row = 10
    x0, y0 = float(s.item.xData[row]), float(s.item.yData[row])
    items = f._plot_data_items_for_ref(ax.plot_item, False)
    point_ref = {'is_3d': False, 'curve_index': items.index(s.item), 'row': f._row_id(s, row)}
    ann = f._create_annotation('cursor', 'axes', ax.plot_item, QtCore.QPointF(x0, y0), None,
                                text=f"{x0:.4g}, {y0:.4g}", point_ref=point_ref)
    assert abs(ann.pos().y() - y0) < 1e-9

    s.set_data(s.item.xData, s.item.yData + 1000.0)
    assert abs(ann.pos().y() - (y0 + 1000.0)) < 1e-6, "set_data's own _push_history must have re-synced it"

    f.undo()
    assert abs(ann.pos().y() - y0) < 1e-6, "undo must resync it back too"
    f.close()


def test_deleting_the_cursors_own_row_removes_it_with_the_delete_as_one_undo():
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    row = 5
    x0, y0 = float(s.item.xData[row]), float(s.item.yData[row])
    items = f._plot_data_items_for_ref(ax.plot_item, False)
    point_ref = {'is_3d': False, 'curve_index': items.index(s.item), 'row': f._row_id(s, row)}
    ann = f._create_annotation('cursor', 'axes', ax.plot_item, QtCore.QPointF(x0, y0), None,
                                text="", point_ref=point_ref)
    assert ann in f.annotations
    n_before = len(s.item.xData)

    f.brush_action.trigger()
    _brush_rows(f, s, [row])
    f.delete_brushed_points()
    assert ann not in f.annotations, "the cursor's own point was just removed from this curve"
    assert len(s.item.xData) == n_before - 1

    f.undo()
    assert len(s.item.xData) == n_before
    ann = f.annotations[-1]  # re-fetch: undo of delete_annotation recreated a new instance
    assert ann.kind == 'cursor' and ann.point_ref == point_ref

    f.redo()
    assert ann not in f.annotations and len(s.item.xData) == n_before - 1
    f.close()


def test_marker_drag_repicks_the_row_on_the_same_curve_and_is_undoable():
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    row0 = 5
    x0, y0 = float(s.item.xData[row0]), float(s.item.yData[row0])
    items = f._plot_data_items_for_ref(ax.plot_item, False)
    point_ref = {'is_3d': False, 'curve_index': items.index(s.item), 'row': f._row_id(s, row0)}
    ann = f._create_annotation('cursor', 'axes', ax.plot_item, QtCore.QPointF(x0, y0), None,
                                text="", point_ref=point_ref)

    row1 = 20
    target_scene = ax.plot_item.getViewBox().mapViewToScene(
        QtCore.QPointF(float(s.item.xData[row1]), float(s.item.yData[row1])))
    ann._cursor_mouse_press(_FakeEv(scene_pos=ann.mapToScene(QtCore.QPointF(0, 0))))
    assert ann._cursor_drag is not None and ann._cursor_drag['region'] == 'marker'
    ann._cursor_mouse_move(_FakeEv(scene_pos=target_scene))
    assert ann.point_ref['row'] == f._row_id(s, row1)
    assert abs(ann.pos().x() - s.item.xData[row1]) < 1e-6
    ann._cursor_mouse_release(_FakeEv(scene_pos=target_scene))

    f.undo()
    assert ann.point_ref['row'] == f._row_id(s, row0)
    assert abs(ann.pos().x() - x0) < 1e-6
    f.redo()
    assert ann.point_ref['row'] == f._row_id(s, row1)
    f.close()


def test_marker_drag_never_jumps_to_a_different_curve_without_alt():
    f, (ax,) = _figure()
    src = _ramp_source()
    s1 = ax.plot(src, x='t', y='a')
    s2 = ax.plot(src, x='t', y='t')  # a second curve on the same subplot
    row0 = 5
    items = f._plot_data_items_for_ref(ax.plot_item, False)
    point_ref = {'is_3d': False, 'curve_index': items.index(s1.item), 'row': f._row_id(s1, row0)}
    ann = f._create_annotation(
        'cursor', 'axes', ax.plot_item,
        QtCore.QPointF(float(s1.item.xData[row0]), float(s1.item.yData[row0])),
        None, text="", point_ref=point_ref)

    # Drag toward a point that sits on s2, not s1, with no Alt held.
    target_scene = ax.plot_item.getViewBox().mapViewToScene(
        QtCore.QPointF(float(s2.item.xData[40]), float(s2.item.yData[40])))
    ann._cursor_mouse_press(_FakeEv(scene_pos=ann.mapToScene(QtCore.QPointF(0, 0))))
    ann._cursor_mouse_move(_FakeEv(scene_pos=target_scene))
    resolved_item = f._cursor_ref_item(ax.plot_item, ann.point_ref)
    assert resolved_item is s1.item, "must stay on the curve it started on without Alt"
    f.close()


def test_alt_held_marker_drag_switches_to_the_nearest_other_curve():
    f, (ax,) = _figure()
    src = _ramp_source()
    s1 = ax.plot(src, x='t', y='a')
    s2 = ax.plot(src, x='t', y='t')
    row0 = 5
    items = f._plot_data_items_for_ref(ax.plot_item, False)
    point_ref = {'is_3d': False, 'curve_index': items.index(s1.item), 'row': f._row_id(s1, row0)}
    ann = f._create_annotation(
        'cursor', 'axes', ax.plot_item,
        QtCore.QPointF(float(s1.item.xData[row0]), float(s1.item.yData[row0])),
        None, text="", point_ref=point_ref)

    target_scene = ax.plot_item.getViewBox().mapViewToScene(
        QtCore.QPointF(float(s2.item.xData[40]), float(s2.item.yData[40])))
    ann._cursor_mouse_press(_FakeEv(scene_pos=ann.mapToScene(QtCore.QPointF(0, 0))))
    ann._cursor_mouse_move(_FakeEv(scene_pos=target_scene, modifiers=QtCore.Qt.AltModifier))
    resolved_item = f._cursor_ref_item(ax.plot_item, ann.point_ref)
    assert resolved_item is s2.item, "Alt must switch to the nearest OTHER curve"
    f.close()


def test_hiding_the_cursors_row_does_not_delete_it_only_a_real_delete_does():
    """Hide Brushed Points narrows what a series draws exactly like Delete
    does, but it's reversible -- only brushing.delete_brushed_points'
    explicit hook removes a cursor; the generic resync never does, since it
    can't tell 'hidden' from 'deleted' (see brushing._cursors_targeting's
    own docstring on why this has to be precise, not generic)."""
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    row = 5
    items = f._plot_data_items_for_ref(ax.plot_item, False)
    point_ref = {'is_3d': False, 'curve_index': items.index(s.item), 'row': f._row_id(s, row)}
    ann = f._create_annotation('cursor', 'axes', ax.plot_item, QtCore.QPointF(0, 0), None,
                                text="", point_ref=point_ref)
    f.brush_action.trigger()
    _brush_rows(f, s, [row])
    f.hide_brushed_points()
    assert ann in f.annotations, "hide is reversible -- it must not remove the cursor"
    f.show_all_hidden_points()
    assert ann in f.annotations
    f.close()


# -- 3D: placement, camera-follow, Z in the text, delete ---------------------

def test_3d_cursor_placement_picks_the_nearest_projected_point():
    f, p, s, src = _figure_3d()
    vb = p.getViewBox()
    vb.render_now()
    sx, sy, front = vb.projected(s.item)
    row = int(np.flatnonzero(front)[0])
    scene_pos = vb.mapViewToScene(QtCore.QPointF(float(sx[row]), float(sy[row])))
    hit = f._nearest_3d_point(p, scene_pos)
    assert hit is not None
    item, array_idx, xyz, local_pos = hit
    assert item is s.item and array_idx == row
    assert np.allclose(xyz, s.item.positions()[row])
    f.close()


def test_datatip_text_includes_z_only_when_given():
    assert datatip_text(None, None, None, None, 1.5, 2.5) == "1.5, 2.5"
    assert datatip_text(None, None, None, None, 1.5, 2.5, z=3.5) == "1.5, 2.5, 3.5"


def test_3d_cursor_follows_the_camera_on_orbit():
    f, p, s, src = _figure_3d()
    vb = p.getViewBox()
    vb.render_now()
    sx, sy, front = vb.projected(s.item)
    row = int(np.flatnonzero(front)[0])
    local_pos = QtCore.QPointF(float(sx[row]), float(sy[row]))
    xyz = s.item.positions()[row]
    point_ref = {'is_3d': True, 'curve_index': 0, 'row': f._row_id(s, row)}
    text = datatip_text(f, p, s.item, row, float(xyz[0]), float(xyz[1]), z=float(xyz[2]))
    assert text.count(',') == 2, "a 3D cursor's default text must include the Z component"
    ann = f._create_annotation('cursor', 'axes', p, local_pos, None, text=text, point_ref=point_ref)
    before = QtCore.QPointF(ann.pos())

    vb.camera.orbit(35, 10)
    vb.camera_changed()
    vb.render_now()  # tests call this directly rather than waiting on the coalescing timer

    sx2, sy2, front2 = vb.projected(s.item)
    assert bool(front2[row])
    expected = QtCore.QPointF(float(sx2[row]), float(sy2[row]))
    assert (ann.pos() - expected).manhattanLength() < 1e-6, "render_now must re-project it every render"
    assert (ann.pos() - before).manhattanLength() > 1.0, "the orbit must have actually moved it on screen"
    f.close()


def test_delete_brushed_points_on_a_3d_series_removes_the_row_and_its_cursor():
    """3D point deletion (positions (N, 3), no y) previously crashed
    delete_brushed_points -- np.asarray(None)[keep]. Also the reason a
    cursor's auto-delete-on-delete rule needed 3D support built at all."""
    f, p, s, src = _figure_3d()
    row = 3
    point_ref = {'is_3d': True, 'curve_index': 0, 'row': f._row_id(s, row)}
    ann = f._create_annotation('cursor', 'axes', p, QtCore.QPointF(0, 0), None,
                                text="pt", point_ref=point_ref)
    n_before = len(s.item.positions())

    f.brush_action.trigger()
    _brush_rows(f, s, [row])
    f.delete_brushed_points()

    assert len(s.item.positions()) == n_before - 1
    assert ann not in f.annotations

    f.undo()
    assert len(s.item.positions()) == n_before
    f.close()


# -- Data Cursor mode (toolbar): click-to-move/add, per-subplot tracking ----

def test_cursor_mode_is_exclusive_with_the_other_modes():
    f, (ax,) = _figure()
    f.cursor_action.trigger()
    assert f.interaction_mode == 'cursor'
    assert f.cursor_action.isChecked() and not f.select_action.isChecked()
    vb = ax.plot_item.getViewBox()
    assert not vb.mouseEnabled()[0], "Data Cursor mode must disable pan, like Select/Brush"
    f.select_action.trigger()
    assert f.interaction_mode == 'select' and not f.cursor_action.isChecked()
    f.close()


def test_plain_click_in_cursor_mode_creates_a_datacursor_at_the_nearest_point():
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    ax.plot_item.getViewBox().setRange(xRange=(0, 49), yRange=(0, 98), padding=0.1)
    f.cursor_action.trigger()
    assert not any(a.kind == 'cursor' for a in f.annotations)

    row = 12
    scene_pt = ax.plot_item.getViewBox().mapViewToScene(
        QtCore.QPointF(float(s.item.xData[row]), float(s.item.yData[row])))
    f._on_scene_clicked(FakeClickEvent(scene_pt))
    cursors = [a for a in f.annotations if a.kind == 'cursor']
    assert len(cursors) == 1
    assert cursors[0].point_ref['row'] == f._row_id(s, row)
    assert f._last_cursor_by_plot[ax.plot_item] is cursors[0]
    f.close()


def test_second_plain_click_moves_the_same_datacursor_instead_of_adding_one():
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    vb = ax.plot_item.getViewBox()
    vb.setRange(xRange=(0, 49), yRange=(0, 98), padding=0.1)
    f.cursor_action.trigger()

    row0 = 5
    f._on_scene_clicked(FakeClickEvent(vb.mapViewToScene(
        QtCore.QPointF(float(s.item.xData[row0]), float(s.item.yData[row0])))))
    cursors = [a for a in f.annotations if a.kind == 'cursor']
    assert len(cursors) == 1
    ann = cursors[0]

    row1 = 30
    f._on_scene_clicked(FakeClickEvent(vb.mapViewToScene(
        QtCore.QPointF(float(s.item.xData[row1]), float(s.item.yData[row1])))))
    cursors = [a for a in f.annotations if a.kind == 'cursor']
    assert cursors == [ann], "the SAME datacursor instance must have moved, not a new one"
    assert ann.point_ref['row'] == f._row_id(s, row1)

    f.undo()
    assert ann.point_ref['row'] == f._row_id(s, row0)
    f.close()


def test_shift_click_always_adds_a_new_datacursor():
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    vb = ax.plot_item.getViewBox()
    vb.setRange(xRange=(0, 49), yRange=(0, 98), padding=0.1)
    f.cursor_action.trigger()

    for row in (5, 30):
        f._on_scene_clicked(FakeClickEvent(
            vb.mapViewToScene(QtCore.QPointF(float(s.item.xData[row]), float(s.item.yData[row]))),
            modifiers=QtCore.Qt.ShiftModifier))
    cursors = [a for a in f.annotations if a.kind == 'cursor']
    assert len(cursors) == 2, "Shift+click must always add, never move an existing one"
    f.close()


def test_last_cursor_tracking_is_per_subplot():
    f, (ax0, ax1) = _figure(n_plots=2)
    src = _ramp_source()
    s0 = ax0.plot(src, x='t', y='a')
    s1 = ax1.plot(src, x='t', y='a')
    ax0.plot_item.getViewBox().setRange(xRange=(0, 49), yRange=(0, 98), padding=0.1)
    ax1.plot_item.getViewBox().setRange(xRange=(0, 49), yRange=(0, 98), padding=0.1)
    f.cursor_action.trigger()

    row = 7
    f._on_scene_clicked(FakeClickEvent(ax0.plot_item.getViewBox().mapViewToScene(
        QtCore.QPointF(float(s0.item.xData[row]), float(s0.item.yData[row])))))
    f._on_scene_clicked(FakeClickEvent(ax1.plot_item.getViewBox().mapViewToScene(
        QtCore.QPointF(float(s1.item.xData[row]), float(s1.item.yData[row])))))

    cursors = [a for a in f.annotations if a.kind == 'cursor']
    assert len(cursors) == 2, "clicking subplot 1 must not move subplot 0's datacursor"
    assert f._last_cursor_by_plot[ax0.plot_item] is not f._last_cursor_by_plot[ax1.plot_item]
    f.close()


def test_cursor_context_menu_has_no_link_or_copy_paste_but_has_add_new():
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    row = 3
    items = f._plot_data_items_for_ref(ax.plot_item, False)
    point_ref = {'is_3d': False, 'curve_index': items.index(s.item), 'row': f._row_id(s, row)}
    ann = f._create_annotation('cursor', 'axes', ax.plot_item,
                                QtCore.QPointF(float(s.item.xData[row]), float(s.item.yData[row])),
                                None, text="", point_ref=point_ref)

    class _FakeCtxEv:
        def screenPos(self):
            return QtCore.QPoint(0, 0)

        def accept(self):
            pass

    # Patch QMenu.exec_ to capture action labels instead of blocking on a
    # real popup -- same trick a modal-dialog-avoidance test would use.
    from pyqtgraph.Qt import QtWidgets
    orig_menu_exec = QtWidgets.QMenu.exec_
    captured = {}

    def fake_exec(self, *a, **k):
        captured['labels'] = [act.text() for act in self.actions()]

    QtWidgets.QMenu.exec_ = fake_exec
    try:
        ann.contextMenuEvent(_FakeCtxEv())
    finally:
        QtWidgets.QMenu.exec_ = orig_menu_exec

    labels = captured['labels']
    assert "Add New Datacursor" in labels
    assert not any("Copy" in l or "Paste" in l or "Link" in l for l in labels)
    f.close()


def test_add_new_datacursor_menu_action_creates_a_second_one_offset_nearby():
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    row = 3
    items = f._plot_data_items_for_ref(ax.plot_item, False)
    point_ref = {'is_3d': False, 'curve_index': items.index(s.item), 'row': f._row_id(s, row)}
    ann = f._create_annotation('cursor', 'axes', ax.plot_item,
                                QtCore.QPointF(float(s.item.xData[row]), float(s.item.yData[row])),
                                None, text="", point_ref=point_ref)
    assert len([a for a in f.annotations if a.kind == 'cursor']) == 1

    f._add_datacursor_near(ann)
    cursors = [a for a in f.annotations if a.kind == 'cursor']
    assert len(cursors) == 2
    f.close()


# -- label kept inside the subplot on creation -------------------------------

def test_new_cursor_label_lands_inside_the_subplot_near_every_corner():
    """A datacursor placed near a subplot's edge used to always point its
    label up-and-right on screen (the kind's fixed __init__ default),
    which can land it outside the subplot -- invisible, since a ViewBox
    clips its 'axes'-anchored children (CLAUDE.md bug #21) -- for a point
    close enough to the top or right edge. fit_cursor_label_onscreen
    (wired into _create_annotation) should flip the offset toward
    whichever side has room instead, for every corner."""
    f, (ax,) = _figure()
    ax.plot_item.getViewBox().setRange(xRange=(0, 10), yRange=(-1, 1), padding=0)
    app.processEvents()
    vb = ax.plot_item.getViewBox()
    rect = vb.sceneBoundingRect()
    margin = 5
    corners = {
        'top-right': QtCore.QPointF(rect.right() - margin, rect.top() + margin),
        'top-left': QtCore.QPointF(rect.left() + margin, rect.top() + margin),
        'bottom-right': QtCore.QPointF(rect.right() - margin, rect.bottom() - margin),
        'bottom-left': QtCore.QPointF(rect.left() + margin, rect.bottom() - margin),
    }
    for name, scene_pt in corners.items():
        p0 = vb.mapSceneToView(scene_pt)
        ann = f._create_annotation('cursor', 'axes', ax.plot_item, p0, None, text="1.234")
        label_scene = ann.mapToScene(ann.p1_local)
        assert rect.adjusted(-2, -2, 2, 2).contains(label_scene), \
            f"{name}: label landed outside the subplot at {label_scene}"
    f.close()


def test_new_cursor_label_keeps_default_direction_when_there_is_room():
    """Away from any edge, the label still goes up-and-right exactly as
    before -- the fit only kicks in once the default would actually land
    outside the subplot."""
    f, (ax,) = _figure()
    ax.plot_item.getViewBox().setRange(xRange=(0, 10), yRange=(-1, 1), padding=0)
    app.processEvents()
    vb = ax.plot_item.getViewBox()
    p0 = vb.mapSceneToView(vb.sceneBoundingRect().center())
    ann = f._create_annotation('cursor', 'axes', ax.plot_item, p0, None, text="x")
    assert ann.p1_local.x() > 0
    assert ann.mapToScene(ann.p1_local).y() < ann.mapToScene(QtCore.QPointF(0, 0)).y()
    f.close()
