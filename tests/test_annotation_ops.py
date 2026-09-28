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
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from tests.helpers import (
    app, m, SHIFT, FakeClickEvent, FakeSceneEvent, FakePressEvent, shown_figure,
    first_curve, _click_annotation, _place, _two_annotation_figure,
    _scene_pos,
)


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


def test_properties_apply_to_every_selected_annotation():
    f, curve, rect, ellipse = _two_annotation_figure()
    line = _place(f, 'line', f.plots[2])
    old_line_brush = line.brush
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    _click_annotation(f, line, modifiers=SHIFT)
    red, fill = QtGui.QColor(255, 0, 0), QtGui.QColor(0, 0, 255, 60)
    colors = iter([red, fill])
    saved = (QtWidgets.QColorDialog.getColor, QtWidgets.QInputDialog.getDouble,
             QtWidgets.QMessageBox.question)
    QtWidgets.QColorDialog.getColor = staticmethod(lambda *a, **k: next(colors))
    QtWidgets.QInputDialog.getDouble = staticmethod(lambda *a, **k: (4.0, True))
    QtWidgets.QMessageBox.question = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Yes)
    try:
        f._edit_annotation_properties(rect)
    finally:
        (QtWidgets.QColorDialog.getColor, QtWidgets.QInputDialog.getDouble,
         QtWidgets.QMessageBox.question) = saved
    for a in (rect, ellipse, line):
        assert a.pen.color() == red and a.pen.widthF() == 4.0, a.kind
    assert rect.brush.color() == fill and ellipse.brush.color() == fill
    assert line.brush is old_line_brush, "fill only applies to rect/ellipse"
    f.close()


def test_multi_properties_is_one_undo_entry():
    f, curve, rect, ellipse = _two_annotation_figure()
    old = {a: (a.pen.color(), a.pen.widthF()) for a in (rect, ellipse)}
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    n_undo = len(f.undo_stack)
    saved = (QtWidgets.QColorDialog.getColor, QtWidgets.QInputDialog.getDouble,
             QtWidgets.QMessageBox.question)
    QtWidgets.QColorDialog.getColor = staticmethod(lambda *a, **k: QtGui.QColor(255, 0, 0))
    QtWidgets.QInputDialog.getDouble = staticmethod(lambda *a, **k: (4.0, True))
    QtWidgets.QMessageBox.question = staticmethod(lambda *a, **k: QtWidgets.QMessageBox.No)
    try:
        f._edit_annotation_properties(rect)
    finally:
        (QtWidgets.QColorDialog.getColor, QtWidgets.QInputDialog.getDouble,
         QtWidgets.QMessageBox.question) = saved
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert {a: (a.pen.color(), a.pen.widthF()) for a in (rect, ellipse)} == old
    f.close()
