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

"""Annotations (annotation_ops.py + annotations.py).

IMPORTANT for anyone extending this file: every undo_fn/redo_fn created by
_create_annotation/delete_annotation/paste_subplot closes over a
*specific* AnnotationItem instance and, on the "recreate" side, builds a
brand-new instance via AnnotationItem.from_dict (same pattern as
delete_curve). A Python variable capturing "the annotation" goes stale
across any undo/redo that recreates it: re-fetch it from win.annotations
afterward rather than reusing the old reference. It also means you can't
safely undo() twice in a row past a create/delete pair that itself already
replaced the object once -- pair every undo with its matching redo (or a
fresh delete_annotation call on whatever is *currently* live).
"""
import logging
import math
import time

from pyqtgraph.Qt import QtCore, QtGui, QtWidgets, QtTest

from tests.helpers import (
    app, m, SHIFT, FakeClickEvent, FakeSceneEvent, FakePressEvent, shown_figure,
    first_curve, _click_annotation, _place, _two_annotation_figure,
    _scene_pos, _vb_center, _dblclick, _editor, _type, _click_away, _drive_font_dialog,
    _press_escape,
)


class _ListHandler(logging.Handler):
    """Appends each record's rendered message to a list. This project has
    no pytest (no caplog fixture), so this small handler stands in for it
    -- see PLAN.md's Round 3 preamble, which explicitly allows every
    debug-logging package to build its own tiny copy of this rather than
    share a file neither owns (tests/test_brushing.py has an identical
    one of its own)."""

    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _attached_handler():
    logger = logging.getLogger('lafigure')
    handler = _ListHandler()
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return handler, logger, old_level


def test_annotation_lifecycle():
    """Place (drag gesture and point kinds), anchor zones, data cursor,
    cancel, relink, delete priority, subplot delete/undo carrying its
    annotation, and cross-window subplot paste with its annotation.
    Extent kinds go through eventFilter (FakeSceneEvent), not
    _on_scene_clicked: a real click-and-drag never fires sigMouseClicked."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots
    c1 = first_curve(p1)
    mgr = m.FigureManager()

    win.set_interaction_mode('select')
    win._on_plot_clicked(p1)

    # Extent shape (rect), axes-anchored: a press-drag-release gesture inside
    # p1's data area (see FakeSceneEvent/place_two_click_shape docstrings for
    # why this goes through eventFilter, not _on_scene_clicked).
    scene = win.layout_widget.scene()
    vb1_center = p1.getViewBox().sceneBoundingRect().center()
    win.start_placing_annotation('rect')
    assert win._placing_kind == 'rect'
    win.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMousePress, vb1_center))
    assert win._placing_state is not None
    win.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMouseRelease, vb1_center + QtCore.QPointF(80, 60)))
    assert win._placing_kind is None, "placement state must clear once the shape is finalized"
    assert len(win.annotations) == 1
    rect_ann = win.annotations[0]
    assert rect_ann.kind == 'rect' and rect_ann.anchor == 'axes' and rect_ann.parent_plot is p1
    assert win.active_annotation is rect_ann, "creating an annotation should select it"

    win.undo()
    assert len(win.annotations) == 0
    win.redo()
    assert len(win.annotations) == 1
    rect_ann = win.annotations[0]  # re-fetch: redo recreated a new instance, see note above
    assert rect_ann.kind == 'rect' and rect_ann.anchor == 'axes' and rect_ann.parent_plot is p1

    # Border-anchored zone detection: a click on p1's title-bar area (inside
    # its full scene rect, outside its ViewBox) should resolve to 'border'.
    title_pos = p1.titleLabel.mapToScene(p1.titleLabel.boundingRect().center())
    assert not p1.getViewBox().sceneBoundingRect().contains(title_pos), \
        "test assumes the title sits outside the ViewBox's data area"
    anchor, parent = win._annotation_zone(title_pos)
    assert anchor == 'border' and parent is p1

    # Figure-anchored: a click outside every subplot resolves to ('figure', None).
    far_scene_pos = QtCore.QPointF(-500, -500)
    anchor, parent = win._annotation_zone(far_scene_pos)
    assert anchor == 'figure' and parent is None
    free_ann = win._create_annotation('rect', 'figure', None, far_scene_pos, QtCore.QPointF(30, 20))
    assert free_ann.anchor == 'figure' and free_ann.parent_plot is None
    assert free_ann.scene() is win.layout_widget.scene()
    win.undo()  # remove free_ann again; its own create/undo pair, doesn't touch rect_ann
    assert free_ann not in win.annotations
    assert rect_ann in win.annotations

    # Data cursor: axes-only, snaps to the nearest sample on the active curve.
    win._on_plot_clicked(p1)
    win._select_curve(c1)
    sample_scene_pos = p1.getViewBox().mapViewToScene(QtCore.QPointF(float(c1.xData[100]), float(c1.yData[100])))
    win.start_placing_annotation('cursor')
    win._on_scene_clicked(FakeClickEvent(sample_scene_pos))
    assert win._placing_kind is None
    cursor_ann = win.active_annotation
    assert cursor_ann.kind == 'cursor' and cursor_ann.anchor == 'axes'
    assert abs(cursor_ann.pos().x() - c1.xData[100]) < 1e-6
    win.delete_annotation(cursor_ann)
    assert cursor_ann not in win.annotations
    win.undo()
    cursor_ann = win.annotations[-1]  # re-fetch: undoing the delete recreated a new instance
    assert cursor_ann.kind == 'cursor'
    win.delete_annotation(cursor_ann)  # a fresh, correctly-paired delete -- see note above on why
    assert cursor_ann not in win.annotations
    assert rect_ann in win.annotations and len(win.annotations) == 1

    # Cancelling placement mid-shape (Escape) must not leave a dangling
    # half-created annotation or a stuck override cursor.
    n_before = len(win.annotations)
    win.start_placing_annotation('line')
    win.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMousePress, vb1_center))
    assert win._placing_state is not None
    win._cancel_placing()
    assert win._placing_kind is None and win._placing_state is None
    assert len(win.annotations) == n_before

    # Reparenting ("Link to..."): move rect_ann from p1 (axes) to p2 (border,
    # via a click on p2's title area) and back. Unlike creation, reparenting
    # mutates the SAME AnnotationItem in place (see _reparent_annotation), so
    # rect_ann stays valid across this undo -- no re-fetch needed here.
    win._deselect_curve()
    assert rect_ann.anchor == 'axes' and rect_ann.parent_plot is p1
    win._start_relink(rect_ann)
    assert win._relink_source is rect_ann
    p2_title_pos = p2.titleLabel.mapToScene(p2.titleLabel.boundingRect().center())
    win._on_scene_clicked(FakeClickEvent(p2_title_pos))
    assert win._relink_source is None
    assert rect_ann.anchor == 'border' and rect_ann.parent_plot is p2
    win.undo()
    assert rect_ann.anchor == 'axes' and rect_ann.parent_plot is p1
    assert win.active_annotation is rect_ann  # reparenting (and its undo) re-selects the annotation

    # delete_selection() priority: annotation > curve > subplot.
    win.delete_selection()
    assert rect_ann not in win.annotations
    win.undo()
    rect_ann = win.annotations[-1]  # re-fetch: undoing delete_annotation recreated a new instance
    assert rect_ann.kind == 'rect' and rect_ann.anchor == 'axes' and rect_ann.parent_plot is p1

    win._deselect_annotation()
    win._on_plot_clicked(p1)
    win._select_curve(c1)
    n_curves_before = len(p1.listDataItems())
    win.delete_selection()  # only the curve is selected, so only the curve goes
    assert len(p1.listDataItems()) == n_curves_before - 1
    win.undo()
    assert len(p1.listDataItems()) == n_curves_before
    assert rect_ann in win.annotations  # curve delete/undo must not disturb the annotation

    # Deleting a subplot must take its (still-attached) annotations with it,
    # and undo must bring them back re-parented to the recreated PlotItem.
    win.active_curve = None
    win._deselect_annotation()
    win._on_plot_clicked(p1)
    n_plots_before = len(win.plots)
    win.delete_selection()  # no curve/annotation selected -> deletes the subplot itself
    assert len(win.plots) == n_plots_before - 1
    assert not any(a.parent_plot is p1 for a in win.annotations), \
        "deleting a subplot must purge its annotations too"
    win.undo()
    assert len(win.plots) == n_plots_before
    assert len(win.annotations) == 1 and win.annotations[0].kind == 'rect'
    # _insert_subplot_at appends to the end of self.plots (see add_subplot),
    # so the recreated PlotItem is not necessarily win.plots[0] -- find it via
    # the annotation that was just restored onto it, not by list position.
    restored_p1 = win.annotations[0].parent_plot
    assert restored_p1 in win.plots

    # Copy/paste a subplot (with its annotation) across two separate figure
    # windows via the shared Clipboard, same cross-window path exercised above
    # for curves.
    win._on_plot_clicked(restored_p1)
    win.copy_subplot()
    assert len(win.clipboard.subplot[0]['annotations']) == 1
    other = mgr.new_figure()
    app.processEvents()
    other.paste_subplot()
    app.processEvents()
    assert len(other.plots) == 1
    pasted_plot = other.plots[0]
    assert len(other.annotations) == 1
    pasted_ann = other.annotations[0]
    assert pasted_ann.kind == 'rect' and pasted_ann.parent_plot is pasted_plot
    other.close()
    app.processEvents()
    win.close()


def test_plain_click_on_a_grouped_annotation_collapses_to_it():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    press = FakePressEvent(rect.scenePos())
    rect.mousePressEvent(press)
    assert f.selected_annotations == [rect, ellipse], "the press keeps the group (drag-ready)"
    rect.mouseReleaseEvent(press)
    assert f.selected_annotations == [rect] and not ellipse._selected
    f.close()


def test_dragging_a_selected_annotation_moves_the_whole_group():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    rect_before, ellipse_before = _scene_pos(rect), _scene_pos(ellipse)
    start = rect.scenePos()
    delta = QtCore.QPointF(30, 20)
    rect.mousePressEvent(FakePressEvent(start))
    rect.mouseMoveEvent(FakePressEvent(start + delta))
    rect.mouseReleaseEvent(FakePressEvent(start + delta))
    for name, before, ann in (('rect', rect_before, rect), ('ellipse', ellipse_before, ellipse)):
        moved = _scene_pos(ann) - before
        assert abs(moved.x() - 30) < 0.5 and abs(moved.y() - 20) < 0.5, (name, moved)
    assert f.selected_annotations == [rect, ellipse], "a real drag keeps the group selected"
    f.undo()  # one gesture, one Undo
    assert (_scene_pos(rect) - rect_before).manhattanLength() < 0.5
    assert (_scene_pos(ellipse) - ellipse_before).manhattanLength() < 0.5
    f.close()


def test_style_menu_applies_to_every_selected_annotation():
    f, curve, rect, ellipse = _two_annotation_figure()
    line = _place(f, 'line', f.plots[2])
    old_line_brush = line.brush
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    _click_annotation(f, line, modifiers=SHIFT)
    targets = [rect, ellipse, line]
    f.set_annotation_color(targets, (255, 0, 0))
    f.set_annotation_line_width(targets, 4.0)
    f.set_annotation_fill(targets, QtGui.QBrush(QtGui.QColor(0, 0, 255, 60)))
    for a in targets:
        assert a.pen.color() == QtGui.QColor(255, 0, 0) and a.pen.widthF() == 4.0, a.kind
    assert rect.brush.color() == QtGui.QColor(0, 0, 255, 60)
    assert ellipse.brush.color() == QtGui.QColor(0, 0, 255, 60)
    assert line.brush is old_line_brush, "fill only applies to rect/ellipse"
    f.close()


def test_multi_style_edit_is_one_undo_entry():
    f, curve, rect, ellipse = _two_annotation_figure()
    old = {a: (a.pen.color(), a.pen.widthF()) for a in (rect, ellipse)}
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    n_undo = len(f.undo_stack)
    f.set_annotation_color([rect, ellipse], (255, 0, 0))
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert {a: (a.pen.color(), a.pen.widthF()) for a in (rect, ellipse)} == old
    f.close()


# -- Shift constraints (LibreOffice Draw style): move / resize / rotate /
# placement all snap the same way while Shift is held. Every check below
# compares SCENE (screen-pixel) vectors, not local/data ones -- see
# constrain_extent_vector's own docstring for why that's the deliberate
# choice (it reads the same on screen for any anchor/data scale).

def test_shift_move_snaps_to_45_degrees():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_annotation(f, rect)
    start = rect.scenePos()
    rect.mousePressEvent(FakePressEvent(start))
    rect.mouseMoveEvent(FakePressEvent(start + QtCore.QPointF(50, 6), modifiers=SHIFT))
    moved = rect.scenePos() - start
    assert abs(moved.y()) < 0.5 and moved.x() > 0, moved
    rect.mouseReleaseEvent(FakePressEvent(start + QtCore.QPointF(50, 6), modifiers=SHIFT))
    f.close()


def test_plain_move_is_not_constrained():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_annotation(f, rect)
    start = rect.scenePos()
    rect.mousePressEvent(FakePressEvent(start))
    rect.mouseMoveEvent(FakePressEvent(start + QtCore.QPointF(50, 6)))
    moved = rect.scenePos() - start
    assert abs(moved.x() - 50) < 0.5 and abs(moved.y() - 6) < 0.5, moved
    rect.mouseReleaseEvent(FakePressEvent(start + QtCore.QPointF(50, 6)))
    f.close()


def test_shift_resize_rect_is_screen_square():
    f, curve, rect, ellipse = _two_annotation_figure()
    origin_scene = rect.mapToScene(QtCore.QPointF(0, 0))
    rect._on_endpoint_drag(origin_scene + QtCore.QPointF(80, 20), modifiers=SHIFT)
    vec = rect.mapToScene(rect.p1_local) - origin_scene
    assert abs(abs(vec.x()) - abs(vec.y())) < 1.0, vec
    assert abs(vec.x() - 80) < 1.0, vec  # the larger magnitude wins, sign preserved
    f.close()


def test_plain_resize_rect_is_not_constrained():
    f, curve, rect, ellipse = _two_annotation_figure()
    origin_scene = rect.mapToScene(QtCore.QPointF(0, 0))
    rect._on_endpoint_drag(origin_scene + QtCore.QPointF(80, 20))
    vec = rect.mapToScene(rect.p1_local) - origin_scene
    assert abs(vec.x() - 80) < 1.0 and abs(vec.y() - 20) < 1.0, vec


def test_shift_resize_line_snaps_angle():
    f, curve, rect, ellipse = _two_annotation_figure()
    line = _place(f, 'line', f.plots[2])
    origin_scene = line.mapToScene(QtCore.QPointF(0, 0))
    line._on_endpoint_drag(origin_scene + QtCore.QPointF(100, 12), modifiers=SHIFT)
    vec = line.mapToScene(line.p1_local) - origin_scene
    assert abs(vec.y()) < 1.0 and vec.x() > 90, vec
    f.close()


def test_shift_start_handle_resize_is_screen_square():
    """The p0 (start) handle drags the *other* end while p1 stays fixed --
    same constraint, opposite end."""
    f, curve, rect, ellipse = _two_annotation_figure()
    p1_scene = rect.mapToScene(rect.p1_local)
    rect._on_start_press(None)
    rect._on_start_drag(p1_scene + QtCore.QPointF(-70, -18), modifiers=SHIFT)
    vec = rect.mapToScene(QtCore.QPointF(0, 0)) - p1_scene
    assert abs(abs(vec.x()) - abs(vec.y())) < 1.0, vec
    assert rect.mapToScene(rect.p1_local) == p1_scene, "p1 must stay exactly fixed"
    f.close()


def test_shift_rotate_snaps_to_45_degrees():
    f, curve, rect, ellipse = _two_annotation_figure()
    center = rect.mapToScene(rect._shape_center_local())
    rect._on_rotate_drag(center + QtCore.QPointF(60, -55), modifiers=SHIFT)
    ratio = rect.screen_rotation() / 45.0
    assert abs(ratio - round(ratio)) < 1e-6, rect.screen_rotation()
    f.close()


def test_plain_rotate_is_not_constrained():
    f, curve, rect, ellipse = _two_annotation_figure()
    center = rect.mapToScene(rect._shape_center_local())
    rect._on_rotate_drag(center + QtCore.QPointF(60, -55))
    ratio = rect.screen_rotation() / 45.0
    assert abs(ratio - round(ratio)) > 1e-3, "control: this angle should NOT land on a 45-degree step"
    f.close()


def test_shift_placement_drag_constrains_the_new_shape():
    f = m.LaFigure()
    f.show()
    app.processEvents()
    plot = f.plots[0]
    scene = f.layout_widget.scene()
    start = _vb_center(plot)
    f.start_placing_annotation('rect')
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMousePress, start))
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMouseRelease,
                                        start + QtCore.QPointF(90, 15), modifiers=SHIFT))
    ann = f.annotations[-1]
    vec = ann.mapToScene(ann.p1_local) - ann.mapToScene(QtCore.QPointF(0, 0))
    assert abs(abs(vec.x()) - abs(vec.y())) < 1.0, vec
    f.close()


# -- Selection outline / arrowhead geometry (pure math, no QPainter needed) --

def test_oriented_outline_for_a_diagonal_arrow_is_tight_in_scene_space():
    f, curve, rect, ellipse = _two_annotation_figure()
    arrow = _place(f, 'arrow', f.plots[2])
    arrow.p1_local = QtCore.QPointF(60, 40)  # diagonal, not horizontal/vertical
    poly = arrow._selection_outline_polygon()
    assert len(poly) == 4
    scene_poly = [arrow.mapToScene(p) for p in poly]
    p0_scene = arrow.mapToScene(QtCore.QPointF(0, 0))
    p1_scene = arrow.mapToScene(arrow.p1_local)
    length = math.hypot(p1_scene.x() - p0_scene.x(), p1_scene.y() - p0_scene.y())

    def dist(a, b):
        return math.hypot(a.x() - b.x(), a.y() - b.y())

    # A tight, oriented rectangle around the segment in SCENE space: two
    # opposite edges ~= the segment length + 2*END_PAD, the other two
    # ~= 2*PERP_PAD -- tighter than the old axis-aligned box of the two
    # endpoints (60 x 40), and not the axis-aligned box at all.
    edges = sorted(dist(scene_poly[i], scene_poly[(i + 1) % 4]) for i in range(4))
    expected_short, expected_long = 2 * arrow.OUTLINE_PERP_PAD_PX, length + 2 * arrow.OUTLINE_END_PAD_PX
    assert abs(edges[0] - expected_short) < 0.5 and abs(edges[1] - expected_short) < 0.5, edges
    assert abs(edges[2] - expected_long) < 0.5 and abs(edges[3] - expected_long) < 0.5, edges
    f.close()


def test_rect_selection_outline_hugs_the_rect_in_screen_pixels():
    """Was: the outline equals boundingRect() inset by 4 local units (a
    ~16px margin, per-axis data units on an 'axes' anchor). WP-P1: it
    hugs the drawn rect by OUTLINE_PAD_PX screen pixels on every side."""
    f, curve, rect, ellipse = _two_annotation_figure()
    poly = [rect.mapToScene(pt) for pt in rect._selection_outline_polygon()]
    assert len(poly) == 4
    drawn = QtGui.QPolygonF(_scene_corners(rect)).boundingRect()
    outline = QtGui.QPolygonF(poly).boundingRect()
    pad = rect.OUTLINE_PAD_PX
    for got, want in ((outline.left(), drawn.left() - pad), (outline.right(), drawn.right() + pad),
                      (outline.top(), drawn.top() - pad), (outline.bottom(), drawn.bottom() + pad)):
        assert abs(got - want) < 0.5, (outline, drawn)
    f.close()


def test_oriented_outline_is_not_warped_by_a_non_square_data_scale():
    """A subplot whose X range spans 1000x its Y range: a rotation/box
    computed in DATA space (not scene space) would come out visibly
    skewed on screen. The outline polygon, mapped to scene space, must
    still be a true rectangle (adjacent edges perpendicular)."""
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    f._add_series(p, 'line', [0, 1000], [0, 1], name='flat')
    f.show()
    app.processEvents()
    p.getViewBox().setRange(xRange=(0, 1000), yRange=(0, 1), padding=0)
    app.processEvents()
    start_scene = p.getViewBox().mapViewToScene(QtCore.QPointF(500, 0.5))
    arrow = f._create_annotation(
        'arrow', 'axes', p, p.getViewBox().mapSceneToView(start_scene), QtCore.QPointF(200, 0.3))
    poly = arrow._selection_outline_polygon()
    scene_poly = [arrow.mapToScene(pt) for pt in poly]

    def vec(a, b):
        return (b.x() - a.x(), b.y() - a.y())

    e0, e1 = vec(scene_poly[0], scene_poly[1]), vec(scene_poly[1], scene_poly[2])
    dot = e0[0] * e1[0] + e0[1] * e1[1]
    assert abs(dot) < 0.5, ("adjacent edges must be perpendicular on screen", dot)
    f.close()


def test_arrowhead_is_a_real_triangle_pointing_at_the_tip():
    """The tip corner must stay exactly at the line's endpoint; the other
    two corners come back from a scene-space round trip (see
    _draw_arrowhead's docstring for why), so check them via their
    scene-space triangle instead of exact local values."""
    f, curve, rect, ellipse = _two_annotation_figure()
    arrow = _place(f, 'arrow', f.plots[2])
    arrow.p1_local = QtCore.QPointF(50, 0)
    captured = []
    real_draw_polygon = QtGui.QPainter.drawPolygon

    class _Recorder:
        def drawPolygon(self, poly):
            captured.append(QtGui.QPolygonF(poly))

    arrow._draw_arrowhead(_Recorder(), arrow.p1_local, QtCore.QPointF(0, 0))
    assert len(captured) == 1
    poly = captured[0]
    assert len(poly) == 3
    assert poly[0] == arrow.p1_local, "the tip corner is exact, no scene round-trip"
    tip_scene = arrow.mapToScene(poly[0])
    p1_scene = arrow.mapToScene(poly[1])
    p2_scene = arrow.mapToScene(poly[2])
    back_scene = QtCore.QPointF((p1_scene.x() + p2_scene.x()) / 2, (p1_scene.y() + p2_scene.y()) / 2)

    def dist(a, b):
        return math.hypot(a.x() - b.x(), a.y() - b.y())

    expected = math.hypot(arrow.head_length, arrow.head_width / 2)
    assert abs(dist(tip_scene, p1_scene) - expected) < 0.5
    assert abs(dist(tip_scene, p2_scene) - expected) < 0.5
    assert abs(dist(tip_scene, back_scene) - arrow.head_length) < 0.5
    f.close()


# -- "Link to subplot <name>" menu shortcuts (item 5) -----------------------

def test_subplots_under_annotation_and_link_shortcut():
    f = m.LaFigure(empty=True)
    p0 = f.add_subplot(row=0, col=0)
    p1 = f.add_subplot(row=0, col=1)
    f.show()
    app.processEvents()
    r0, r1 = p0.sceneBoundingRect(), p1.sceneBoundingRect()
    mid_x = (r0.right() + r1.left()) / 2
    start = QtCore.QPointF(mid_x - 20, r0.top() + 10)
    ann = f._create_annotation('rect', 'figure', None, start, QtCore.QPointF(40, 20))
    covered = f._subplots_under_annotation(ann)
    assert p0 in covered and p1 in covered, (covered, r0, r1)

    f._link_annotation_to_subplot(ann, p1)
    assert ann.anchor == 'border' and ann.parent_plot is p1
    assert ann in f.annotations
    f.close()


class _FakeMenuEvent:
    """Duck-types the QGraphicsSceneContextMenuEvent AnnotationItem.
    contextMenuEvent reads: screenPos() (only passed through to
    QMenu.exec_, which is monkeypatched below to avoid a blocking modal
    popup) and accept()."""

    def __init__(self, pos):
        self._pos = pos

    def screenPos(self):
        return self._pos.toPoint()

    def accept(self):
        pass


def test_link_to_subplot_actions_only_offered_for_an_unlinked_annotation():
    f = m.LaFigure(empty=True)
    p0 = f.add_subplot(row=0, col=0)
    p1 = f.add_subplot(row=0, col=1)
    f.show()
    app.processEvents()
    r0, r1 = p0.sceneBoundingRect(), p1.sceneBoundingRect()
    mid_x = (r0.right() + r1.left()) / 2
    start = QtCore.QPointF(mid_x - 20, r0.top() + 10)
    free_ann = f._create_annotation('rect', 'figure', None, start, QtCore.QPointF(40, 20))
    linked_ann = f._create_annotation('rect', 'axes', p0, QtCore.QPointF(10, 10), QtCore.QPointF(10, 10))

    captured = []
    real_exec = QtWidgets.QMenu.exec_
    QtWidgets.QMenu.exec_ = lambda self, *a, **k: captured.append(self)
    try:
        free_ann.contextMenuEvent(_FakeMenuEvent(free_ann.scenePos()))
        free_texts = [a.text() for a in captured[-1].actions()]
        linked_ann.contextMenuEvent(_FakeMenuEvent(linked_ann.mapToScene(QtCore.QPointF(0, 0))))
        linked_texts = [a.text() for a in captured[-1].actions()]
    finally:
        QtWidgets.QMenu.exec_ = real_exec

    assert any(t.startswith("Link to subplot") for t in free_texts), free_texts
    assert not any(t.startswith("Link to subplot") for t in linked_texts), linked_texts
    f.close()


# -- WP-P1: tight hit-test shape(), scene-space rotation, textarrow label ----
# Every check below measures SCENE (screen-pixel) geometry -- see the
# lafigure-axes-geometry skill: on a subplot whose X/Y data-per-pixel isn't
# 1:1, local (data) numbers say nothing about what the user sees.

def _dist(a, b):
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def _angle_deg(vec):
    return math.degrees(math.atan2(vec.y(), vec.x()))


def _hits(ann, scene_pt):
    """Qt's own hit-test: QGraphicsItem.contains() reads shape()."""
    return ann.contains(ann.mapFromScene(scene_pt))


def _one_subplot_figure(x_range=None, y_range=None):
    """One subplot, shown; optionally with a fixed (non-1:1) view."""
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    f._add_series(p, 'line', [0, 1], [0, 1], name='_bg')
    f.show()
    app.processEvents()
    if x_range is not None:
        p.getViewBox().setRange(xRange=x_range, yRange=y_range, padding=0)
        app.processEvents()
    return f, p


def _skewed_axes_rect(kind='rect'):
    """An 'axes'-anchored `kind` on a subplot spanning 1000 data units in X
    but 1 in Y -- about as far from 1:1 as a real plot gets. Its screen box
    is 120 x 60 px, starting at the view's center."""
    f, p = _one_subplot_figure(x_range=(0, 1000), y_range=(0, 1))
    vb = p.getViewBox()
    start_scene = vb.sceneBoundingRect().center()
    p0 = vb.mapSceneToView(start_scene)
    p1 = vb.mapSceneToView(start_scene + QtCore.QPointF(120, -60)) - p0
    ann = f._create_annotation(kind, 'axes', p, p0, p1)
    f._deselect_all()
    return f, p, ann


def _scene_corners(ann):
    p1 = ann.p1_local
    return [ann.mapToScene(QtCore.QPointF(x, y))
            for x, y in ((0, 0), (p1.x(), 0), (p1.x(), p1.y()), (0, p1.y()))]


def _assert_screen_rectangle(ann, width, height, angle):
    """The shape's four corners form, ON SCREEN, a width x height rectangle
    whose local-x edge points at `angle` degrees -- i.e. a true rotation,
    not a skewed parallelogram."""
    c0, c1, c2, c3 = _scene_corners(ann)
    e0, e1 = c1 - c0, c3 - c0
    dot = e0.x() * e1.x() + e0.y() * e1.y()
    assert abs(dot) < 1.0, ("edges must be perpendicular on screen", dot, e0, e1)
    assert abs(math.hypot(e0.x(), e0.y()) - width) < 0.5, (e0, width)
    assert abs(math.hypot(e1.x(), e1.y()) - height) < 0.5, (e1, height)
    diff = (_angle_deg(e0) - angle + 180) % 360 - 180
    assert abs(diff) < 0.5, ("on-screen angle", _angle_deg(e0), angle)


def test_rect_shape_hugs_the_rect_in_screen_pixels():
    """shape() is the dashed outline (a few screen px around the rect), not
    boundingRect()'s 20px-padded box: 3px past an edge still hits, 12px
    past no longer does (the old padded box did)."""
    f, p = _one_subplot_figure()
    start = p.getViewBox().sceneBoundingRect().center() - QtCore.QPointF(40, 30)
    rect = f._create_annotation('rect', 'figure', None, start, QtCore.QPointF(80, 50))
    right_mid = start + QtCore.QPointF(80, 25)
    top_mid = start + QtCore.QPointF(40, 0)
    assert _hits(rect, right_mid + QtCore.QPointF(3, 0))
    assert _hits(rect, top_mid + QtCore.QPointF(0, -3))
    far = right_mid + QtCore.QPointF(12, 0)
    assert rect.boundingRect().contains(rect.mapFromScene(far)), "control: the old padded box reached it"
    assert not _hits(rect, far)
    assert not _hits(rect, top_mid + QtCore.QPointF(0, -12))
    f.close()


def test_ellipse_shape_is_a_bounding_ellipse():
    """A click in the bounding box's corner, a few px past the ellipse's
    own edge, no longer hits it; just past the edge on an axis still does."""
    f, p = _one_subplot_figure()
    center = p.getViewBox().sceneBoundingRect().center()
    a, b = 40, 25
    ell = f._create_annotation('ellipse', 'figure', None, center - QtCore.QPointF(a, b),
                               QtCore.QPointF(2 * a, 2 * b))
    corner = center + QtCore.QPointF(a - 3, -(b - 3))  # inside the box, outside the ellipse
    assert ell.boundingRect().contains(ell.mapFromScene(corner)), "control: the old box reached it"
    assert not _hits(ell, corner)
    assert _hits(ell, center + QtCore.QPointF(a + 2, 0))
    assert _hits(ell, center + QtCore.QPointF(0, b + 2))
    assert _hits(ell, center)
    # The drawn outline is the same bounding ellipse, not a box.
    poly = ell._selection_outline_polygon()
    assert len(poly) > 8, "an ellipse outline, not a 4-corner box"
    for pt in poly:
        s = ell.mapToScene(pt) - center
        assert (s.x() / a) ** 2 + (s.y() / b) ** 2 > 1.0, "outline sits outside the drawn ellipse"
        assert abs(s.x()) <= a + 8 and abs(s.y()) <= b + 8, "only a few px outside it"
    f.close()


def test_shape_padding_is_screen_pixels_on_a_non_square_axes_subplot():
    """Same few-px margin on X and Y, even though one data unit is ~0.4px
    in X and ~300px in Y: built in scene space, never per-axis local pad."""
    f, p, rect = _skewed_axes_rect()
    c0, c1, c2, c3 = _scene_corners(rect)
    right_mid = (c1 + c2) / 2
    top_mid = (c2 + c3) / 2  # p1.y is "up" on screen here (negative scene dy)
    scene = f.layout_widget.scene()
    for edge_mid, out in ((right_mid, QtCore.QPointF(1, 0)), (top_mid, QtCore.QPointF(0, -1))):
        assert _hits(rect, edge_mid + out * 3), edge_mid
        assert not _hits(rect, edge_mid + out * 12), edge_mid
        # Qt's own item picking agrees: an item under a clipping ancestor
        # (the ViewBox) is picked by clipPath(), not shape(), unless
        # contains() is overridden -- see AnnotationItem.contains.
        assert rect in scene.items(edge_mid + out * 3)
        assert rect not in scene.items(edge_mid + out * 12)
    f.close()


def test_oriented_kinds_shape_hugs_the_segment():
    f, p = _one_subplot_figure()
    start = p.getViewBox().sceneBoundingRect().center() - QtCore.QPointF(50, 0)
    arrow = f._create_annotation('arrow', 'figure', None, start, QtCore.QPointF(100, 60))
    mid = start + QtCore.QPointF(50, 30)
    n_unit = QtCore.QPointF(-60, 100) * (1 / math.hypot(60, 100))
    assert _hits(arrow, mid)
    assert _hits(arrow, mid + n_unit * 4)
    # 15px perpendicular to the segment: inside the old axis-aligned box.
    assert arrow.boundingRect().contains(arrow.mapFromScene(mid + n_unit * 15)), "control"
    assert not _hits(arrow, mid + n_unit * 15)
    f.close()


def test_textarrow_shape_includes_its_text_label():
    f, p = _one_subplot_figure()
    start = p.getViewBox().sceneBoundingRect().center() - QtCore.QPointF(60, 0)
    ta = f._create_annotation('textarrow', 'figure', None, start, QtCore.QPointF(100, 0), text='hello')
    label_center = ta._text_scene_rect().center()
    assert _hits(ta, label_center)
    assert _hits(ta, start + QtCore.QPointF(50, 0))
    f.close()


def test_real_click_selects_near_the_rect_edge_but_not_in_the_ellipse_corner():
    """Through Qt's own item picking (a real QMouseEvent to the viewport),
    not just contains(): what the user actually clicks."""
    from tests.helpers import _mouse
    f, p = _one_subplot_figure()
    f.set_interaction_mode('select')
    center = p.getViewBox().sceneBoundingRect().center()
    rect = f._create_annotation('rect', 'figure', None, center + QtCore.QPointF(20, -40),
                                QtCore.QPointF(80, 60))
    ell = f._create_annotation('ellipse', 'figure', None, center - QtCore.QPointF(120, 40),
                               QtCore.QPointF(80, 60))
    f._deselect_all()
    L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
    press, release = QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease

    corner = center - QtCore.QPointF(120, 40) + QtCore.QPointF(3, 3)
    _mouse(f, press, corner, L)
    _mouse(f, release, corner, N)
    assert ell not in f.selected_annotations, "the ellipse's box corner is no longer the ellipse"

    f._deselect_all()
    time.sleep(1.1)  # past the click-cycle timeout, so this is a fresh click
    near_edge = center + QtCore.QPointF(20 + 80 + 3, -10)
    _mouse(f, press, near_edge, L)
    _mouse(f, release, near_edge, N)
    assert rect in f.selected_annotations, "3px past the rect's edge still grabs it"
    f.close()


def test_real_click_just_above_an_axes_rect_on_a_skewed_subplot_misses_it():
    """The 'axes' case through real events: the old padded box reached
    thousands of px in Y here (a 20px pad converted with the X/Y-averaged
    data-per-pixel), and Qt's clip-based contains() kept using it."""
    from tests.helpers import _mouse
    f, p, rect = _skewed_axes_rect()
    f.set_interaction_mode('select')
    c0, c1, c2, c3 = _scene_corners(rect)
    L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
    above = (c2 + c3) / 2 + QtCore.QPointF(0, -12)
    _mouse(f, QtCore.QEvent.MouseButtonPress, above, L)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, above, N)
    assert rect not in f.selected_annotations
    time.sleep(1.1)  # past the click-cycle timeout
    inside_edge = (c2 + c3) / 2 + QtCore.QPointF(0, -3)
    _mouse(f, QtCore.QEvent.MouseButtonPress, inside_edge, L)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, inside_edge, N)
    assert rect in f.selected_annotations
    f.close()


def test_rotation_is_applied_in_screen_space_on_a_non_square_axes_subplot():
    """setRotation() on an 'axes' annotation rotated in DATA space, which
    renders as a skewed parallelogram at some other angle. Now: the rotate
    handle asks for 30 degrees on screen, and the shape IS a 120x60px
    rectangle at 30 degrees on screen."""
    f, p, rect = _skewed_axes_rect()
    center = rect.mapToScene(rect._shape_center_local())
    # Handle rests straight above center; +30 deg turns it clockwise on screen.
    target = center + QtCore.QPointF(math.sin(math.radians(30)), -math.cos(math.radians(30))) * 80
    rect._on_rotate_drag(target)
    assert abs(rect.screen_rotation() - 30) < 1e-6, rect.screen_rotation()
    _assert_screen_rectangle(rect, 120, 60, 30)
    assert _dist(rect.mapToScene(rect._shape_center_local()), center) < 0.5, "pivot stays put"
    f.close()


def test_rotated_axes_annotation_stays_a_true_rotation_after_zoom():
    """The data->screen scale changes on every zoom, so the screen-space
    rotation has to be rebuilt then, or the shape skews again."""
    f, p, rect = _skewed_axes_rect()
    rect._apply_rotation(30)
    vb = p.getViewBox()
    vb.setRange(xRange=(0, 1000), yRange=(0, 3), padding=0)  # Y squeezed 3x on screen
    app.processEvents()
    c0, c1, c2, c3 = _scene_corners(rect)
    e0, e1 = c1 - c0, c3 - c0
    assert abs(e0.x() * e1.x() + e0.y() * e1.y()) < 1.0, (e0, e1)
    assert abs(_angle_deg(e0) - 30) < 0.5, _angle_deg(e0)
    f.close()


def test_rotated_axes_annotation_survives_delete_and_undo():
    """from_dict applies the rotation before the item has its ViewBox
    parent; re-parenting must rebuild the screen-space transform."""
    f, p, rect = _skewed_axes_rect()
    rect._apply_rotation(30)
    f.delete_annotation(rect)
    f.undo()
    restored = f.annotations[-1]
    assert abs(restored.screen_rotation() - 30) < 1e-6
    _assert_screen_rectangle(restored, 120, 60, 30)
    f.close()


def test_shift_rotate_snaps_to_screen_45_on_a_non_square_axes_subplot():
    f, p, rect = _skewed_axes_rect()
    center = rect.mapToScene(rect._shape_center_local())
    rect._on_rotate_drag(center + QtCore.QPointF(60, -35), modifiers=SHIFT)
    assert abs(rect.screen_rotation() - 45) < 1e-6, rect.screen_rotation()
    _assert_screen_rectangle(rect, 120, 60, 45)
    f.close()


def test_real_shift_drag_of_the_rotate_handle_snaps_on_screen():
    """The rotate handle driven by real QMouseEvents (Qt picks the handle
    from the event's global position -- CLAUDE.md bug #11)."""
    from tests.helpers import _mouse
    f, p, rect = _skewed_axes_rect()
    f.set_interaction_mode('select')
    f._select_annotation(rect)
    app.processEvents()
    handle_scene = rect._rotate_handle.scenePos()
    center = rect.mapToScene(rect._shape_center_local())
    assert abs(_angle_deg(handle_scene - center) + 90) < 0.5, "control: handle rests straight above center"
    L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
    target = center + QtCore.QPointF(70, -20)  # ~74 deg from "up": snaps to 90
    _mouse(f, QtCore.QEvent.MouseButtonPress, handle_scene, L)
    time.sleep(0.012)
    _mouse(f, QtCore.QEvent.MouseMove, (handle_scene + target) / 2, L, button=N, mods=SHIFT)
    time.sleep(0.012)
    _mouse(f, QtCore.QEvent.MouseMove, target, L, button=N, mods=SHIFT)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, target, N, mods=SHIFT)
    assert abs(rect.screen_rotation() - 90) < 1e-6, rect.screen_rotation()
    _assert_screen_rectangle(rect, 120, 60, 90)
    f.close()


def _label_checks(ta):
    """The label sits beside p1 (the arrowhead) -- off to the side of the
    segment, clear of it and of the tip, but close -- and nowhere near p0:
    the old fixed offset hung it off p0."""
    p0 = ta.mapToScene(QtCore.QPointF(0, 0))
    p1 = ta.mapToScene(ta.p1_local)
    box = ta._text_scene_rect()
    for t in (0.0, 0.1, 0.5, 0.9, 1.0):
        assert not box.contains(p0 + (p1 - p0) * t), ("the label covers the arrow", t, box)
    nearest = QtCore.QPointF(min(max(p1.x(), box.left()), box.right()),
                             min(max(p1.y(), box.top()), box.bottom()))
    assert _dist(nearest, p1) < ta.LABEL_GAP_PX + max(box.width(), box.height()) / 2, (box, p1)
    assert _dist(box.center(), p1) < _dist(box.center(), p0) - 30, (box, p0, p1)


def test_textarrow_label_sits_beside_p1_at_any_angle():
    f, p = _one_subplot_figure()
    start = p.getViewBox().sceneBoundingRect().center() - QtCore.QPointF(60, 0)
    ta = f._create_annotation('textarrow', 'figure', None, start, QtCore.QPointF(120, 0), text='label')
    for vec in ((120, 0), (0, -120), (-90, 90), (100, 70), (-120, 0)):
        ta.p1_local = QtCore.QPointF(*vec)
        _label_checks(ta)
    f.close()


def test_textarrow_label_follows_p1_on_a_non_square_axes_subplot():
    f, p = _one_subplot_figure(x_range=(0, 1000), y_range=(0, 1))
    vb = p.getViewBox()
    start_scene = vb.sceneBoundingRect().center()
    p0 = vb.mapSceneToView(start_scene)
    p1 = vb.mapSceneToView(start_scene + QtCore.QPointF(100, -80)) - p0
    ta = f._create_annotation('textarrow', 'axes', p, p0, p1, text='label')
    _label_checks(ta)
    # Dragging the end handle moves the label along with the tip.
    ta._on_endpoint_press(None)
    ta._on_endpoint_drag(start_scene + QtCore.QPointF(-90, 60))
    ta._on_endpoint_release(None)
    _label_checks(ta)
    # So does a zoom (the tip moves on screen, the data doesn't).
    vb.setRange(xRange=(0, 2000), yRange=(0, 1), padding=0)
    app.processEvents()
    _label_checks(ta)
    f.close()


# -- annotation text: in-place editing, rich text, Font... (WP-P8) ------------
# Started by real double-clicks/right-clicks and typed with real keys (see
# tests/test_richtext.py's docstring for why).

def _text_center(ann):
    return ann._text_scene_rect().center()


def _text_annotation(anchor='axes', text=r"\alpha"):
    f, p = _one_subplot_figure()
    if anchor == 'axes':
        vb = p.getViewBox()
        ann = f._create_annotation('text', 'axes', p, vb.mapSceneToView(vb.sceneBoundingRect().center()),
                                   None, text=text)
    else:
        ann = f._create_annotation('text', 'figure', None, QtCore.QPointF(80, 80), None, text=text)
    f._deselect_all()
    app.processEvents()
    return f, p, ann


def _no_input_dialog(*a, **k):
    raise AssertionError("no QInputDialog popup")


def test_double_click_annotation_text_edits_in_place():
    f, p, ann = _text_annotation()
    assert ann._text_item.toPlainText() == "α", "rendered rich text"
    saved = QtWidgets.QInputDialog.getText
    QtWidgets.QInputDialog.getText = staticmethod(_no_input_dialog)
    try:
        rect = ann._text_scene_rect()
        _dblclick(f, _text_center(ann))
        ed = _editor(f)
        assert ed is not None, "a double-click on the text opens the in-place editor"
        assert ed.sceneBoundingRect().intersects(rect), "over the text"
        assert ed.text() == r"\alpha", "edits the source markup"
        n_undo = len(f.undo_stack)
        _type(f, r" = \beta^{2}")
        _click_away(f)
    finally:
        QtWidgets.QInputDialog.getText = saved
    assert _editor(f) is None
    assert ann.text == r"\alpha = \beta^{2}"
    assert ann._text_item.toPlainText() == "α = β2"
    assert "vertical-align:super" in ann._text_item.toHtml()
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert ann.text == r"\alpha" and ann._text_item.toPlainText() == "α"
    f.redo()
    assert ann.text == r"\alpha = \beta^{2}"
    f.close()


def test_annotation_text_shift_enter_makes_a_multi_line_label():
    f, p, ann = _text_annotation(anchor='figure', text="one")
    one_line = ann._text_scene_rect().height()
    _dblclick(f, _text_center(ann))
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Return, QtCore.Qt.ShiftModifier)
    _type(f, "two")
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Return)
    app.processEvents()
    assert ann.text == "one\ntwo"
    assert ann._text_scene_rect().height() > 1.6 * one_line, "renders as two lines"
    # The hit-test shape follows the taller label (P1's shape() reads the text box).
    bottom = ann._text_scene_rect().bottomLeft() + QtCore.QPointF(10, -4)
    assert ann.contains(ann.mapFromScene(bottom))
    f.close()


def _context_menu(f, scene_pt):
    """A real QContextMenuEvent through the view (what a right-click turns
    into), with QMenu.exec_ stubbed; returns the menu shown."""
    shown = []
    real_exec = QtWidgets.QMenu.exec_
    QtWidgets.QMenu.exec_ = lambda self, *a, **k: shown.append(self)
    try:
        view = f.layout_widget
        local = view.mapFromScene(scene_pt)
        ev = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, local,
                                     view.viewport().mapToGlobal(local))
        QtWidgets.QApplication.sendEvent(view.viewport(), ev)
        app.processEvents()
    finally:
        QtWidgets.QMenu.exec_ = real_exec
    return shown[-1] if shown else None


def test_annotation_font_applies_to_the_selected_text_annotations_undoably():
    f, p, a = _text_annotation(anchor='figure', text="first")
    b = f._create_annotation('text', 'figure', None, QtCore.QPointF(200, 120), None, text="second")
    rect = f._create_annotation('rect', 'figure', None, QtCore.QPointF(300, 150), QtCore.QPointF(30, 20))
    f._deselect_all()
    f._select_annotation(a)
    f._select_annotation(b, additive=True)
    f._select_annotation(rect, additive=True)
    app.processEvents()
    before = (a.font_spec(), b.font_spec())
    menu = _context_menu(f, _text_center(a))
    assert menu is not None
    texts = [x.text() for x in menu.actions()]
    assert "Font..." in texts and "Edit Text" in texts, texts
    chosen = {'family': QtGui.QFont().defaultFamily(), 'size': 20.0, 'bold': True,
              'italic': False, 'underline': True, 'strikeout': True, 'color': (10, 120, 30, 255)}
    n_undo = len(f.undo_stack)
    opened = _drive_font_dialog(chosen, [x for x in menu.actions() if x.text() == "Font..."][0].trigger)
    assert opened == [before[0]], "the dialog starts from the clicked annotation's font"
    for ann in (a, b):
        spec = ann.font_spec()
        assert spec['bold'] and not spec['italic'] and spec['size'] == 20.0, spec
        assert spec['underline'] and spec['strikeout'], spec
        assert spec['color'] == chosen['color']
        font = ann._text_item.document().firstBlock().begin().fragment().charFormat().font()
        assert font.underline() and font.strikeOut(), "rendered, not just recorded"
    assert len(f.undo_stack) == n_undo + 1, "one undo entry for the whole selection"
    # A shape without text offers no Font...
    rect_menu = _context_menu(f, rect.mapToScene(rect.p1_local / 2))
    assert rect_menu is not None and "Font..." not in [x.text() for x in rect_menu.actions()]
    f.undo()
    assert (a.font_spec(), b.font_spec()) == before
    f.redo()
    assert a.font_spec()['size'] == 20.0
    f.close()


def test_annotation_copy_paste_round_trips_the_source_and_font():
    f, p, ann = _text_annotation(anchor='axes', text=r"\textbf{Peak} at 3\pm0.1 \mu s")
    ann._apply_font({'family': ann.font_spec()['family'], 'size': 15.0, 'bold': False,
                     'italic': True, 'color': (0, 0, 200, 255)})
    f._select_annotation(ann)
    f.focused_plot = p
    f.copy_annotation()
    f.paste_annotation()
    pasted = f.annotations[-1]
    assert pasted is not ann
    assert pasted.text == r"\textbf{Peak} at 3\pm0.1 \mu s", "the SOURCE, not the rendered HTML"
    assert pasted._text_item.toPlainText() == "Peak at 3±0.1 μ s"
    spec = pasted.font_spec()
    assert spec['italic'] and spec['size'] == 15.0 and spec['color'] == (0, 0, 200, 255), spec
    # Editing the pasted one shows the original markup.
    f._deselect_all()
    app.processEvents()
    _dblclick(f, _text_center(pasted))
    assert _editor(f) is not None and _editor(f).text() == r"\textbf{Peak} at 3\pm0.1 \mu s"
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Escape)
    app.processEvents()
    assert _editor(f) is None and pasted.text == r"\textbf{Peak} at 3\pm0.1 \mu s"
    f.close()


def test_start_text_edit_select_all_lets_typing_replace_a_placeholder():
    """What a just-placed text annotation would use (see the report's
    annotation_ops.py diff): typing replaces the "Text" placeholder."""
    f, p, ann = _text_annotation(anchor='figure', text="Text")
    f.activateWindow()
    app.processEvents()
    ed = ann.start_text_edit(select_all=True)
    assert ed is _editor(f) and ed.textCursor().selectedText() == "Text"
    _type(f, "Hello")
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Return)
    app.processEvents()
    assert ann.text == "Hello"
    rect = f._create_annotation('rect', 'figure', None, QtCore.QPointF(300, 150), QtCore.QPointF(30, 20))
    assert rect.start_text_edit() is None, "a shape without text has nothing to edit"
    f.close()


def test_textarrow_label_edits_in_place_too():
    f, p = _one_subplot_figure()
    start = p.getViewBox().sceneBoundingRect().center() - QtCore.QPointF(60, 0)
    ta = f._create_annotation('textarrow', 'figure', None, start, QtCore.QPointF(120, 0), text='label')
    f._deselect_all()
    app.processEvents()
    _dblclick(f, _text_center(ta))
    assert _editor(f) is not None and _editor(f).text() == 'label'
    _type(f, "!")
    _click_away(f)
    assert ta.text == 'label!'
    _label_checks(ta)  # still laid out beside p1 (P1's geometry untouched)


# -- WP-DBG4: debug logging of annotation placement gestures -----------------
def test_rect_placement_gesture_logs_start_and_completion():
    """A real press-drag-release gesture (the same eventFilter path
    test_annotation_lifecycle drives) must log one "start" record (kind,
    anchor) and one "completed" record with the final geometry."""
    f = shown_figure()
    p1 = f.plots[0]
    scene = f.layout_widget.scene()
    vb1_center = _vb_center(p1)
    f.start_placing_annotation('rect')

    handler, logger, old_level = _attached_handler()
    try:
        f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMousePress, vb1_center))
        f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMouseRelease,
                                             vb1_center + QtCore.QPointF(80, 60)))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)

    assert len(f.annotations) == 1 and f.annotations[0].kind == 'rect', "control: really placed"
    starts = [msg for msg in handler.messages if msg.startswith("annotation placement start")]
    completions = [msg for msg in handler.messages if msg.startswith("annotation placement completed")]
    assert len(starts) == 1 and "kind=rect" in starts[0] and "anchor=axes" in starts[0], handler.messages
    assert len(completions) == 1 and "kind=rect" in completions[0] and "anchor=axes" in completions[0], \
        handler.messages
    f.close()


def test_negligible_drag_placement_is_completed_not_cancelled():
    """A press+release with no real movement still places the shape at its
    default extent (see eventFilter's own docstring) -- that's a
    completion, not a cancellation, and the log must say so."""
    f = shown_figure()
    p1 = f.plots[0]
    scene = f.layout_widget.scene()
    vb1_center = _vb_center(p1)
    f.start_placing_annotation('ellipse')

    handler, logger, old_level = _attached_handler()
    try:
        f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMousePress, vb1_center))
        f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMouseRelease, vb1_center))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)

    assert len(f.annotations) == 1 and f.annotations[0].kind == 'ellipse'
    completions = [msg for msg in handler.messages if msg.startswith("annotation placement completed")]
    cancels = [msg for msg in handler.messages if msg.startswith("annotation placement cancelled")]
    assert len(completions) == 1 and "default extent" in completions[0], handler.messages
    assert not cancels, handler.messages
    f.close()


def test_esc_mid_placement_logs_cancellation_not_completion():
    """Esc (the real toolbar shortcut, via _press_escape) mid-gesture must
    log a cancellation record, and must NOT be misread as a completion --
    _cancel_placing() is also called as plain cleanup right after every
    successful placement (see its own docstring), so this specifically
    guards against that cleanup call being mistaken for a cancel."""
    f = shown_figure()
    p1 = f.plots[0]
    scene = f.layout_widget.scene()
    f.start_placing_annotation('line')
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMousePress, _vb_center(p1)))
    assert f._placing_state is not None, "control: a placement really is in progress"
    n_before = len(f.annotations)

    handler, logger, old_level = _attached_handler()
    try:
        _press_escape(f)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)

    assert f._placing_kind is None and f._placing_state is None, "control: Esc cancelled it"
    assert len(f.annotations) == n_before, "control: nothing got created"
    cancels = [msg for msg in handler.messages if msg.startswith("annotation placement cancelled")]
    completions = [msg for msg in handler.messages if msg.startswith("annotation placement completed")]
    assert len(cancels) == 1 and "kind=line" in cancels[0], handler.messages
    assert not completions, handler.messages
    f.close()


def test_successful_placement_does_not_also_log_a_spurious_cancellation():
    """The inverse of the guard above: a completed placement's own
    cleanup call to _cancel_placing() must not ALSO emit a "cancelled"
    record alongside the "completed" one."""
    f = shown_figure()
    p1 = f.plots[0]
    scene = f.layout_widget.scene()
    f.start_placing_annotation('cursor')
    c1 = first_curve(p1)
    sample_pos = p1.getViewBox().mapViewToScene(QtCore.QPointF(float(c1.xData[50]), float(c1.yData[50])))

    handler, logger, old_level = _attached_handler()
    try:
        f._on_scene_clicked(FakeClickEvent(sample_pos))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)

    assert f._placing_kind is None, "control: the cursor was actually placed"
    completions = [msg for msg in handler.messages if msg.startswith("annotation placement completed")]
    cancels = [msg for msg in handler.messages if msg.startswith("annotation placement cancelled")]
    assert completions and "kind=cursor" in completions[0], handler.messages
    assert not cancels, handler.messages
    f.close()
    f.close()


def test_placing_an_axes_annotation_does_not_change_the_subplots_view_range():
    """An annotation is a view decoration, not data -- adding one must
    never nudge or jump the subplot's own auto-range (reported live: the
    first datacursor placed near a subplot's edge visibly changed its Y
    limits). Root cause: pyqtgraph's ViewBox.childrenBounds() folds a
    plain QGraphicsItem's (padded) boundingRect() into auto-range unless
    the item is added with ignoreBounds=True -- _add_annotation_to_scene
    now passes it for every 'axes'-anchored annotation, not just 'cursor'.
    Placed deliberately near a corner (where the datacursor's own label
    offset reaches furthest) since that's where the old bug was worst."""
    f = shown_figure()
    p1 = f.plots[0]
    vb = p1.getViewBox()
    for _ in range(5):
        app.processEvents()
    before = vb.viewRange()

    rect = vb.sceneBoundingRect()
    corner_scene = QtCore.QPointF(rect.right() - 5, rect.top() + 5)
    p0 = vb.mapSceneToView(corner_scene)
    f._create_annotation('cursor', 'axes', p1, p0, None, text='1.234567')
    for _ in range(3):
        app.processEvents()

    assert vb.viewRange() == before
    f.close()
