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

"""Headless smoke test. Run with:
    QT_QPA_PLATFORM=offscreen python3 smoke_test.py
"""
import numpy as np
import pyqtgraph as pg
pg.setConfigOptions(useOpenGL=False)  # test-only; the shipped app keeps useOpenGL=True
from pyqtgraph.Qt import QtCore, QtWidgets
import lafigure as m
# figure.py sets useOpenGL=True as a module-level side effect on import
# (correct for the shipped app), which stomps the line above. Offscreen
# QPA has no real GL context, so re-assert False now that the import is done.
pg.setConfigOptions(useOpenGL=False)


class FakeClickEvent:
    """Duck-types pyqtgraph's MouseClickEvent enough to drive
    _on_scene_clicked() directly, without going through real Qt mouse-event
    dispatch (unreliable to simulate headlessly -- see HANDOFF.md)."""

    def __init__(self, pos, double=False, accepted=False, button=QtCore.Qt.LeftButton,
                 modifiers=QtCore.Qt.NoModifier):
        self._pos = pos
        self._double = double
        self._accepted = accepted
        self._button = button
        self._modifiers = modifiers

    def scenePos(self):
        return self._pos

    def double(self):
        return self._double

    def isAccepted(self):
        return self._accepted

    def button(self):
        return self._button

    def modifiers(self):
        return self._modifiers


def has_border(plot_item):
    """pyqtgraph's ViewBox.setBorder(None) stores fn.mkPen(None) -- a QPen
    styled NoPen, never the Python singleton None -- so `.border is None`
    can never be true. Check pen style instead."""
    return plot_item.getViewBox().border.style() != QtCore.Qt.NoPen


class FakeSceneEvent:
    """Duck-types a raw QGraphicsScene mouse event enough to drive
    LaFigure.eventFilter() directly. TWO_CLICK_KINDS (rect/ellipse/line/
    arrow/doublearrow/textarrow) are placed via a press-drag-release gesture
    intercepted by eventFilter, NOT via sigMouseClicked/_on_scene_clicked
    (see eventFilter's own docstring: a real click-and-drag never fires
    sigMouseClicked at all) -- so exercising that placement path means
    feeding eventFilter raw press/release events like this, not
    FakeClickEvent."""

    def __init__(self, etype, pos, button=QtCore.Qt.LeftButton):
        self._type = etype
        self._pos = pos
        self._button = button

    def type(self):
        return self._type

    def scenePos(self):
        return self._pos

    def button(self):
        return self._button


app = QtWidgets.QApplication([])
win = m.LaFigure()
win.show()
app.processEvents()

p1, p2, p3, p4 = win.plots
assert win.active_plot is p1

# Focus/active-subplot tracking must follow the click target, not connection order.
win._on_plot_clicked(p2)
assert win.active_plot is p2
win._on_plot_clicked(p4)
assert win.active_plot is p4
assert has_border(p4)
assert not has_border(p2)

# Curve selection: clicking a curve highlights it and restores the previous one.
c1 = [c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)][0]
win._select_curve(c1)
assert win.active_curve is c1
w1 = c1.opts['pen'].width()

c2 = [c for c in p2.listDataItems() if isinstance(c, pg.PlotDataItem)][0]
win._select_curve(c2)
assert c1.opts['pen'].width() == w1 - 3
assert win.active_curve is c2

# Double-clicking a subplot deselects everything: the active subplot AND
# the selected curve (this is _on_scene_clicked's ev.double() branch).
win._on_plot_clicked(p1)
win._select_curve(c1)
assert win.active_plot is p1 and win.active_curve is c1
win._on_scene_clicked(FakeClickEvent(p1.sceneBoundingRect().center(), double=True))
assert win.active_plot is None
assert win.active_curve is None
assert not has_border(p1)
assert not win.move_handle.isVisible()

# A single click landing outside every subplot also deselects everything.
win._on_plot_clicked(p2)
assert win.active_plot is p2
far_away = QtCore.QPointF(-999999, -999999)
win._on_scene_clicked(FakeClickEvent(far_away, double=False, accepted=False))
assert win.active_plot is None

win._on_plot_clicked(p1)  # restore a sane active plot for what follows

# Copy/paste should act on the selected curve.
win._on_plot_clicked(p2)
win.copy_curve()
win._on_plot_clicked(p1)
before = len(p1.listDataItems())
win.paste_curve()
assert len(p1.listDataItems()) == before + 1

# FFT should act on the selected curve.
win._on_plot_clicked(p2)
win._select_curve(c2)
n_before = len(win.plots)
win.fft_below()
assert len(win.plots) == n_before + 1

# Interaction modes: Zoom Rect / Hand set ViewBox mouse mode and hide
# selection; Select restores it and re-enables curve/subplot selection.
win.set_interaction_mode('zoom')
assert p1.getViewBox().state['mouseMode'] == pg.ViewBox.RectMode
assert not win.move_handle.isVisible(), "handles must be hidden outside Select mode"
win.set_interaction_mode('hand')
assert p1.getViewBox().state['mouseMode'] == pg.ViewBox.PanMode
assert not win.move_handle.isVisible()
# Clicking a plot in Hand mode still tracks active_plot (for toolbar
# actions) but must NOT show the selection border.
win._on_plot_clicked(p2)
assert win.active_plot is p2
assert not has_border(p2), "Hand mode must not show a selection border"
win.set_interaction_mode('select')
assert p1.getViewBox().state['mouseMode'] == pg.ViewBox.PanMode
win._on_plot_clicked(p1)
assert has_border(p1)
assert win.move_handle.isVisible()

win.reset_view()

# Deselecting a curve restores its original pen.
win._select_curve(c2)
assert win.active_curve is c2
w2_selected = c2.opts['pen'].width()
win._deselect_curve()
assert win.active_curve is None
assert c2.opts['pen'].width() == w2_selected - 3
# NOTE: _deselect_curve() is called directly here. The real trigger --
# _on_scene_clicked() reading ev.isAccepted() to tell "clicked a curve" from
# "clicked empty space" -- goes through pyqtgraph's live mouse-event dispatch,
# which this harness can't simulate reliably (see HANDOFF.md). Verify that
# path interactively: click a curve to select it, then click empty canvas
# and confirm the highlight goes away.

# Undo/redo: remove_average.
p1_curve = [c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)][0]
y_before = p1_curve.yData.copy()
win._on_plot_clicked(p1)
win.remove_average()
assert not np.array_equal(p1_curve.yData, y_before)
win.undo()
assert np.allclose(p1_curve.yData, y_before)
win.redo()
assert not np.array_equal(p1_curve.yData, y_before)
win.undo()  # leave state clean for what follows

# Undo/redo: delete + recreate a curve.
n_curves_before = len(p1.listDataItems())
target = [c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)][0]
win.delete_curve(target)
assert len(p1.listDataItems()) == n_curves_before - 1
win.undo()
assert len(p1.listDataItems()) == n_curves_before
win.redo()
assert len(p1.listDataItems()) == n_curves_before - 1
win.undo()
# delete_curve's undo_fn recreates a brand-new PlotDataItem (see its own
# undo_fn/redo_fn closures) rather than reusing `target`/`c1` -- both are
# now stale, detached objects no longer in p1.listDataItems(). Re-fetch so
# every later use of c1 (curve selection later in this file, the
# annotations section's data-cursor and delete_selection-fallback tests)
# operates on the currently-live curve instead of silently no-op'ing on a
# dangling reference (this is exactly the staleness this file's own
# annotations-section comment warns about, just for a curve, not an
# annotation).
c1 = [c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)][0]

# Undo/redo: delete + recreate a subplot that shares its row with a
# surviving sibling (p3 and p4 are both in row 1 of the default 2x2 grid).
# This exact scenario used to crash with a Qt "cell already taken" error
# (or a KeyError from pyqtgraph's own bookkeeping on undo) because the old
# delete/undo logic shifted whole rows unconditionally, walking p4 into a
# cell p2 still occupied. p4 must never move or disappear throughout.
n_plots_before = len(win.plots)
p4_pos_before = win._grid_position(p4)
win._on_plot_clicked(p3)
win.active_curve = None  # force subplot deletion, not curve deletion
win.delete_selection()
assert len(win.plots) == n_plots_before - 1
assert p4 in win.plots and win._grid_position(p4) == p4_pos_before
win.undo()  # this is the line that used to raise KeyError
assert len(win.plots) == n_plots_before
assert p4 in win.plots and win._grid_position(p4) == p4_pos_before
win.redo()
assert len(win.plots) == n_plots_before - 1
assert p4 in win.plots and win._grid_position(p4) == p4_pos_before
win.undo()

# Resize: reflow mode should redistribute stretch, and the underlying grid
# layout attribute must actually exist (else resize silently does nothing --
# _grid_layout() prints a WARNING to stderr in that case, watch for it).
layout = win._grid_layout()
assert layout is not None, "pyqtgraph's GraphicsLayout.layout attribute is missing; see stderr warning"

win._on_plot_clicked(p1)
row, col = win._grid_position(p1)
stretch_before = dict(win.col_stretch)
win._begin_resize('right', QtCore.QPointF(0, 0))
win._update_resize(QtCore.QPointF(200, 0))  # drag right edge 200px right
assert win.col_stretch[col] != stretch_before[col]
win._end_resize()
assert win._resize_state is None
win._reset_grid_stretch()  # leave stretch clean for what follows

# Overlap mode: neighbors must NEVER change size, during the drag or after
# release -- that was the reported bug. p2's stretch/geometry must be
# untouched throughout, and p1 should end up detached (floating) at the
# dragged size instead.
win._on_plot_clicked(p1)
row_stretch_before = dict(win.row_stretch)
col_stretch_before = dict(win.col_stretch)
p2_rect_before = QtCore.QRectF(p2.sceneBoundingRect())
win.toggle_overlap_resize(True)
win._begin_resize('bottom-right', QtCore.QPointF(0, 0))
win._update_resize(QtCore.QPointF(150, 150))
assert win.row_stretch == row_stretch_before, "overlap mode must not reflow mid-drag"
assert win.col_stretch == col_stretch_before, "overlap mode must not reflow mid-drag"
assert p1 in win.floating
win._end_resize()
assert win.row_stretch == row_stretch_before, "overlap mode must not reflow on release either"
assert win.col_stretch == col_stretch_before, "overlap mode must not reflow on release either"
assert p2.sceneBoundingRect() == p2_rect_before, "a non-selected subplot changed size in overlap mode"
assert p1 in win.floating, "p1 should still be floating (overlapping) after release"

# A floated plot must stay a real, visible, painted scene item -- not just
# tracked at the right position (this is what the resize handles reflect
# regardless), which is what previously regressed to "only the yellow
# handles are visible, the subplot itself disappeared".
assert p1.scene() is win.layout_widget.scene()
assert p1.isVisible()
assert p1.zValue() > 0

# A second resize drag on an ALREADY-floating plot must not KeyError --
# this exact call previously crashed because _begin_resize fell through to
# _grid_position(p1), and a floating plot has no entry in
# layout_widget.ci.items any more.
win._begin_resize('right', QtCore.QPointF(0, 0))
win._update_resize(QtCore.QPointF(50, 0))
win._end_resize()
assert p1 in win.floating

# Turning Overlap Resize back off is "rearrange now": p1 reattaches to the
# grid and stretch factors update to roughly match its floated size.
win.toggle_overlap_resize(False)
assert p1 not in win.floating
assert win.row_stretch != row_stretch_before or win.col_stretch != col_stretch_before

# Undo/redo: add a new subplot.
n_plots_before = len(win.plots)
win.add_new_subplot()
assert len(win.plots) == n_plots_before + 1
win.undo()
assert len(win.plots) == n_plots_before
win.redo()
assert len(win.plots) == n_plots_before + 1
win.undo()

# Structural changes (add/remove subplot) reset manual sizing -- deliberate
# simplification, see _reset_grid_stretch docstring.
win._reset_grid_stretch()
assert all(v == 100 for v in win.row_stretch.values())
assert all(v == 100 for v in win.col_stretch.values())

# Move handle: dragging p1 onto p2 swaps their grid positions. _end_move
# uses whatever scene pos it's given to find the drop target, regardless of
# _update_move's own (purely cosmetic, for a live drag) positioning math.
win.set_interaction_mode('select')
win._on_plot_clicked(p1)
row1, col1 = win._grid_position(p1)
row2, col2 = win._grid_position(p2)
assert (row1, col1) != (row2, col2)
win._begin_move(QtCore.QPointF(0, 0))
assert p1 in win.floating
p2_center = p2.sceneBoundingRect().center()
win._update_move(p2_center)
win._end_move(p2_center)
assert p1 not in win.floating
assert win._grid_position(p1) == (row2, col2)
assert win._grid_position(p2) == (row1, col1)

# Dropping a moved plot on empty space (no subplot under the cursor) just
# reattaches it back where it started, rather than leaving it floating.
win._on_plot_clicked(p1)
row1, col1 = win._grid_position(p1)
win._begin_move(QtCore.QPointF(0, 0))
win._update_move(far_away)
win._end_move(far_away)
assert p1 not in win.floating
assert win._grid_position(p1) == (row1, col1)

# X/Y label toolbar buttons (set_axis_label) open a modal QInputDialog,
# which would block this headless script waiting for input -- so this
# exercises the same undo/redo push it makes internally rather than calling
# set_axis_label() itself. Test the button interactively: select a
# subplot, click X Label / Y Label, confirm the dialog + resulting label.
win._on_plot_clicked(p1)
old_xlabel = p1.getAxis('bottom').labelText
win._push_history(
    undo_fn=lambda: p1.getAxis('bottom').setLabel(old_xlabel),
    redo_fn=lambda: p1.getAxis('bottom').setLabel('Time (s)'),
)
p1.getAxis('bottom').setLabel('Time (s)')
assert p1.getAxis('bottom').labelText == 'Time (s)'
win.undo()
assert p1.getAxis('bottom').labelText == old_xlabel
win.redo()
assert p1.getAxis('bottom').labelText == 'Time (s)'

# Bounded history: pushing more than max_history entries drops the oldest.
win.undo_stack.clear()
win.redo_stack.clear()
for i in range(win.max_history + 5):
    win._push_history(undo_fn=lambda: None, redo_fn=lambda: None)
assert len(win.undo_stack) == win.max_history

# -- FigureManager: tree tracks open figures/subplots, "New Figure" makes a
# truly empty one, and the shared Clipboard carries a whole subplot from one
# figure window to a separate one. ---------------------------------------
mgr = m.FigureManager()
app.processEvents()
assert win in mgr._figure_items
win_item = mgr._figure_items[win]
assert win_item.childCount() == len(win.plots)

empty_win = mgr.new_figure()
app.processEvents()
assert empty_win.empty is True
assert empty_win.plots == []
assert empty_win in mgr._figure_items
assert mgr._figure_items[empty_win].childCount() == 0

# An empty figure has no floor on subplot count -- adding then deleting its
# only subplot must be able to leave it at zero again (unlike `win`, whose
# floor of 1 is exercised implicitly by every delete_subplot() call above).
empty_win.add_new_subplot()
app.processEvents()
assert len(empty_win.plots) == 1
assert mgr._figure_items[empty_win].childCount() == 1
empty_win.delete_subplot(empty_win.plots[0])
assert len(empty_win.plots) == 0

# Copy a subplot out of `win` and paste it into the separate `empty_win`
# window via the process-wide clipboard -- this is the cross-window path
# that a single-window app couldn't support.
win._on_plot_clicked(p1)
n_curves_p1 = len([c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)])
win.copy_subplot()
assert win.clipboard.subplot is not None
assert win.clipboard is empty_win.clipboard  # same process-wide singleton

empty_win.paste_subplot()
app.processEvents()
assert len(empty_win.plots) == 1
pasted = empty_win.plots[0]
assert pasted.titleLabel.text == p1.titleLabel.text
pasted_curves = [c for c in pasted.listDataItems() if isinstance(c, pg.PlotDataItem)]
assert len(pasted_curves) == n_curves_p1

empty_win.undo()
assert len(empty_win.plots) == 0
empty_win.redo()
assert len(empty_win.plots) == 1

# Closing a figure unregisters it from both the registry and the manager's
# tree.
empty_win.close()
app.processEvents()
assert empty_win not in mgr._figure_items


# -- Annotations -----------------------------------------------------
# Placement is click-based (see figure.py's "-- annotations --" section
# docstring): _handle_placement_click() is what a real click ultimately
# calls, so exercising it directly is the same pattern this file already
# uses for _on_plot_clicked/_on_scene_clicked elsewhere -- no attempt to
# simulate a real Qt mouse drag. Kinds whose placement pops a modal
# QInputDialog ('text', 'textarrow') are exercised via _create_annotation()
# directly instead, same reasoning as set_axis_label's test note above.
#
# IMPORTANT for anyone extending this section: every undo_fn/redo_fn
# created by _create_annotation/delete_annotation/paste_subplot closes over
# a *specific* AnnotationItem instance and, on the "recreate" side, builds
# a brand-new instance via AnnotationItem.from_dict (same pattern as
# delete_curve elsewhere in this app -- see its own undo_fn). That means a
# Python variable capturing "the annotation" goes stale across any
# undo/redo that recreates it: re-fetch it from win.annotations afterward
# rather than reusing the old reference. It also means you can't safely
# undo() twice in a row past a create/delete pair that itself already
# replaced the object once -- pair every undo with its matching redo (or a
# fresh delete_annotation call on whatever is *currently* live) instead of
# assuming N creates can be undone with N blind undo() calls.
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
win.delete_selection()  # no active_annotation -> falls back to the selected curve
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

print("ALL OK")
