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
from tests.helpers import app, m


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


def test_end_handle_is_pulled_back_for_cursor_but_not_other_kinds():
    f, (ax,) = _figure()
    cursor = f._create_annotation('cursor', 'axes', ax.plot_item, QtCore.QPointF(0, 0), None, text="x")
    assert 0 < cursor.END_HANDLE_PULLBACK < 1
    assert cursor._end_handle_pos() == cursor.p1_local * cursor.END_HANDLE_PULLBACK
    assert cursor._end_handle_pos() != cursor.p1_local, \
        "the handle must clear the label bubble, which sits exactly at p1_local"
    line = f._create_annotation('line', 'axes', ax.plot_item, QtCore.QPointF(0, 0), QtCore.QPointF(1, 1))
    assert line._end_handle_pos() == line.p1_local, "only 'cursor' pulls its handle back"
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


def test_dragging_the_anchor_handle_repicks_the_row_on_the_same_curve_and_is_undoable():
    f, (ax,) = _figure()
    src = _ramp_source()
    s = ax.plot(src, x='t', y='a')
    row0 = 5
    x0, y0 = float(s.item.xData[row0]), float(s.item.yData[row0])
    items = f._plot_data_items_for_ref(ax.plot_item, False)
    point_ref = {'is_3d': False, 'curve_index': items.index(s.item), 'row': f._row_id(s, row0)}
    ann = f._create_annotation('cursor', 'axes', ax.plot_item, QtCore.QPointF(x0, y0), None,
                                text="", point_ref=point_ref)
    assert ann._anchor_handle is not None

    row1 = 20
    target_scene = ax.plot_item.getViewBox().mapViewToScene(
        QtCore.QPointF(float(s.item.xData[row1]), float(s.item.yData[row1])))
    ann._on_anchor_press(None)
    ann._on_anchor_drag(target_scene)
    assert ann.point_ref['row'] == f._row_id(s, row1)
    assert abs(ann.pos().x() - s.item.xData[row1]) < 1e-6
    ann._on_anchor_release(target_scene)

    f.undo()
    assert ann.point_ref['row'] == f._row_id(s, row0)
    assert abs(ann.pos().x() - x0) < 1e-6
    f.redo()
    assert ann.point_ref['row'] == f._row_id(s, row1)
    f.close()


def test_dragging_the_anchor_handle_never_jumps_to_a_different_curve():
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

    # Drag toward a point that sits on s2, not s1.
    target_scene = ax.plot_item.getViewBox().mapViewToScene(
        QtCore.QPointF(float(s2.item.xData[40]), float(s2.item.yData[40])))
    ann._on_anchor_press(None)
    ann._on_anchor_drag(target_scene)
    resolved_item = f._cursor_ref_item(ax.plot_item, ann.point_ref)
    assert resolved_item is s1.item, "must stay on the curve it started on, never switch curves"
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
