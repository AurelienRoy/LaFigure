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
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import lafigure as m
# figure.py sets useOpenGL=True as a module-level side effect on import
# (correct for the shipped app), which stomps the line above. Offscreen
# QPA has no real GL context, so re-assert False now that the import is done.
pg.setConfigOptions(useOpenGL=False)


class FakeClickEvent:
    """Duck-types pyqtgraph's MouseClickEvent enough to drive
    _on_scene_clicked() directly, without going through real Qt mouse-event
    dispatch (unreliable to simulate headlessly -- see CLAUDE.md, "Headless testing by
    calling methods directly")."""

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
# which this harness can't simulate reliably (see CLAUDE.md, "Headless
# testing by calling methods directly"). Verify that
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


# Figure-wide toggles vs. subplots created later. Actions are driven with
# .trigger() -- what a real click does. setChecked() alone never emits
# `triggered`, so a test using it would pass without running the handler.

def _is_x_linked(plot_item):
    return plot_item.getViewBox().linkedView(pg.ViewBox.XAxis) is not None


def test_new_subplot_adopts_link_x():
    f = m.LaFigure()
    f.link_x_action.trigger()
    f.add_new_subplot()
    new = f.plots[-1]
    assert _is_x_linked(new), "a subplot added while Link X is on must be X-linked"
    f.link_x_action.trigger()
    assert not any(_is_x_linked(p) for p in f.plots)
    f.close()


def test_link_x_survives_deleting_the_reference_subplot():
    f = m.LaFigure()
    f.link_x_action.trigger()
    old_reference = f.plots[0]
    f.delete_subplot(old_reference)
    reference = f.plots[0]
    assert not _is_x_linked(reference)
    for p in f.plots[1:]:
        assert p.getViewBox().linkedView(pg.ViewBox.XAxis) is reference.getViewBox(), \
            "followers must re-link to the new plots[0], not the deleted one"
    f.close()


def test_new_subplot_adopts_brushing():
    f = m.LaFigure()
    f.brush_action.trigger()
    f.add_new_subplot()
    new = f.plots[-1]
    assert f._brushers[new].brushing_enabled, "a subplot added while Brush is on must brush"
    f.close()


def test_brush_off_does_not_reenable_pan_in_select_mode():
    f = m.LaFigure()
    f.hand_action.trigger()
    f.brush_action.trigger()
    assert all(p.getViewBox().state['mouseEnabled'] == [False, False] for p in f.plots), \
        "brushing must disable pan even in Hand mode"
    f.select_action.trigger()
    f.brush_action.trigger()
    assert all(p.getViewBox().state['mouseEnabled'] == [False, False] for p in f.plots), \
        "Brush off must not re-enable pan while Select mode forbids it"
    f.hand_action.trigger()
    assert all(p.getViewBox().state['mouseEnabled'] == [True, True] for p in f.plots)
    f.close()


def test_add_subplot_is_the_only_subplot_construction_site():
    """add_subplot is where new subplots adopt the figure-wide toggles; a
    second addPlot() call would silently bypass that."""
    import inspect
    import lafigure.figure
    src = inspect.getsource(lafigure.figure)
    assert src.count('.addPlot(') == 1, "a new addPlot() call site bypasses add_subplot"
    assert 'def add_subplot' in src  # control: the scan is reading the right file


def test_undoing_fft_drops_its_brusher():
    f = m.LaFigure()
    f._on_plot_clicked(f.plots[0])
    f.fft_below()
    fft_plot = f.plots[-1]
    assert fft_plot in f._brushers  # control: the FFT subplot really got a brusher
    f.undo()
    assert fft_plot not in f.plots
    assert set(f._brushers) <= set(f.plots), "a removed subplot's RectBrush must not linger"
    f.close()


# Selection exclusivity: a click selects one thing and deselects every other
# kind (subplot / curve / annotation) unless Shift is held. Clicks are driven
# through the real handlers in Qt's order: a curve's sigClicked fires first
# and accepts the event, then the scene handler runs.

SHIFT = QtCore.Qt.ShiftModifier


class FakePressEvent:
    """Duck-types the QGraphicsSceneMouseEvent AnnotationItem.mousePressEvent reads."""

    def __init__(self, pos, modifiers=QtCore.Qt.NoModifier):
        self._pos = pos
        self._modifiers = modifiers

    def button(self):
        return QtCore.Qt.LeftButton

    def modifiers(self):
        return self._modifiers

    def scenePos(self):
        return self._pos

    def accept(self):
        pass


def _vb_center(plot_item):
    return plot_item.getViewBox().sceneBoundingRect().center()


def _click_subplot(f, plot_item, modifiers=QtCore.Qt.NoModifier):
    f._on_scene_clicked(FakeClickEvent(_vb_center(plot_item), modifiers=modifiers))


def _click_curve(f, plot_item, curve, modifiers=QtCore.Qt.NoModifier):
    curve.curve.sigClicked.emit(curve.curve, FakeClickEvent(_vb_center(plot_item), modifiers=modifiers))
    f._on_scene_clicked(FakeClickEvent(_vb_center(plot_item), accepted=True, modifiers=modifiers))


def _click_annotation(f, ann, modifiers=QtCore.Qt.NoModifier):
    ann.mousePressEvent(FakePressEvent(ann.scenePos(), modifiers=modifiers))


def _selection_figure():
    """A fresh figure in Select mode with one rect annotation on plots[1],
    and nothing selected."""
    f = m.LaFigure()
    f.show()
    app.processEvents()
    plot = f.plots[1]
    f.start_placing_annotation('rect')
    scene = f.layout_widget.scene()
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMousePress, _vb_center(plot)))
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMouseRelease,
                                        _vb_center(plot) + QtCore.QPointF(40, 30)))
    f._deselect_all()
    ann = f.annotations[-1]
    curve = f.plots[0].listDataItems()[0]
    return f, curve, ann


def _selected(f):
    return list(f.selected_plots), list(f.selected_curves), f.active_annotation


def test_curve_click_deselects_the_selected_subplot():
    f, curve, ann = _selection_figure()
    p0, p1 = f.plots[0], f.plots[1]
    _click_subplot(f, p1)
    assert _selected(f) == ([p1], [], None)
    _click_curve(f, p0, curve)
    assert _selected(f) == ([], [curve], None), _selected(f)
    assert not has_border(p1) and not has_border(p0), "no subplot is selected, so no border"
    assert not f.move_handle.isVisible(), "handles belong to a selected subplot"
    assert f.active_plot is p0, "the curve's subplot stays the toolbar target"
    f.close()


def test_subplot_click_deselects_curve_and_annotation():
    f, curve, ann = _selection_figure()
    _click_curve(f, f.plots[0], curve)
    _click_subplot(f, f.plots[1])
    assert _selected(f) == ([f.plots[1]], [], None)
    _click_annotation(f, ann)
    _click_subplot(f, f.plots[0])
    assert _selected(f) == ([f.plots[0]], [], None), "a subplot click must deselect the annotation"
    f.close()


def test_annotation_click_deselects_curve_and_subplot():
    f, curve, ann = _selection_figure()
    _click_subplot(f, f.plots[1])
    _click_curve(f, f.plots[0], curve, modifiers=SHIFT)
    _click_annotation(f, ann)
    assert _selected(f) == ([], [], ann), _selected(f)
    assert not any(has_border(p) for p in f.plots)
    f.close()


def test_curve_click_deselects_the_annotation():
    f, curve, ann = _selection_figure()
    _click_annotation(f, ann)
    _click_curve(f, f.plots[0], curve)
    assert _selected(f) == ([], [curve], None), _selected(f)
    f.close()


def test_shift_click_keeps_every_kind_selected():
    f, curve, ann = _selection_figure()
    p0, p1 = f.plots[0], f.plots[1]
    _click_subplot(f, p1)
    _click_curve(f, p0, curve, modifiers=SHIFT)
    _click_annotation(f, ann, modifiers=SHIFT)
    _click_subplot(f, p0, modifiers=SHIFT)
    assert _selected(f) == ([p1, p0], [curve], ann), _selected(f)
    f.close()


def test_right_click_inside_the_selection_keeps_it():
    f, curve, ann = _selection_figure()
    p0, p1 = f.plots[0], f.plots[1]
    _click_subplot(f, p0)
    _click_subplot(f, p1, modifiers=SHIFT)
    f._on_plot_context(p0)
    assert _selected(f) == ([p0, p1], [], None), "right-click must not collapse a multi-select"
    f._on_plot_context(f.plots[2])
    assert _selected(f) == ([f.plots[2]], [], None), "right-click outside the selection selects"
    f.close()


def test_programmatic_selection_is_exclusive_too():
    f, curve, ann = _selection_figure()
    _click_curve(f, f.plots[0], curve)
    f.add_new_subplot()
    assert _selected(f) == ([f.plots[-1]], [], None), "a new subplot's selection is exclusive"
    _click_curve(f, f.plots[0], curve)
    f.copy_subplot()  # nothing but a curve selected -> copies its subplot
    f.paste_subplot()
    assert _selected(f)[1:] == ([], None), "pasted subplots' selection is exclusive"
    f.close()


# LibreOffice Draw / MATLAB conventions: Shift+click toggles any item,
# Shift+click on empty space is a no-op, Esc deselects everything, a group
# of annotations drags together, and Del removes everything selected.

def _place(f, kind, plot_item, offset=QtCore.QPointF(0, 0)):
    scene = f.layout_widget.scene()
    start = _vb_center(plot_item) + offset
    f.start_placing_annotation(kind)
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMousePress, start))
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMouseRelease,
                                        start + QtCore.QPointF(40, 30)))
    return f.annotations[-1]


def _two_annotation_figure():
    """rect on plots[1], ellipse on plots[0] -- two subplots, so two
    different data-unit coordinate systems. Nothing selected."""
    f, curve, rect = _selection_figure()
    ellipse = _place(f, 'ellipse', f.plots[0], QtCore.QPointF(-60, -40))
    f._deselect_all()
    app.processEvents()  # let the ViewBoxes' lazy auto-range settle before positions are read
    return f, curve, rect, ellipse


def _empty_scene_point(f):
    pt = QtCore.QPointF(2, 2)
    assert not any(p.getViewBox().sceneBoundingRect().contains(pt) for p in f.plots), \
        "control: the 'empty' point must really be outside every subplot"
    return pt


def _press_escape(f):
    esc = [s for s in f.findChildren(QtGui.QShortcut)
           if s.key() == QtGui.QKeySequence(QtCore.Qt.Key_Escape)]
    assert len(esc) == 1, "control: exactly one Esc shortcut is bound"
    esc[0].activated.emit()


def _scene_pos(ann):
    return ann.parentItem().mapToScene(ann.pos()) if ann.parentItem() else ann.pos()


def test_shift_click_on_empty_space_changes_nothing():
    f, curve, ann = _selection_figure()
    _click_subplot(f, f.plots[1])
    _click_curve(f, f.plots[0], curve, modifiers=SHIFT)
    _click_annotation(f, ann, modifiers=SHIFT)
    before = _selected(f)
    f._on_scene_clicked(FakeClickEvent(_empty_scene_point(f), modifiers=SHIFT))
    assert _selected(f) == before, "Shift+click on empty space must do nothing"
    f._on_scene_clicked(FakeClickEvent(_empty_scene_point(f)))
    assert _selected(f) == ([], [], None), "a plain click on empty space still deselects all"
    f.close()


def test_escape_deselects_everything():
    f, curve, ann = _selection_figure()
    _click_subplot(f, f.plots[1])
    _click_curve(f, f.plots[0], curve, modifiers=SHIFT)
    _click_annotation(f, ann, modifiers=SHIFT)
    _press_escape(f)
    assert _selected(f) == ([], [], None) and f.selected_annotations == []
    assert not any(has_border(p) for p in f.plots) and not f.move_handle.isVisible()
    f.close()


def test_escape_cancels_relink_and_deselects_in_one_press():
    # Re-link, not placement: starting a placement already deselects all.
    f, curve, ann = _selection_figure()
    _click_annotation(f, ann)
    f._start_relink(ann)
    assert f.selected_annotations == [ann], "control: re-linking keeps the selection"
    _press_escape(f)
    assert f._relink_source is None
    assert _selected(f) == ([], [], None)
    f.close()


def test_shift_click_toggles_every_kind():
    f, curve, rect, ellipse = _two_annotation_figure()
    p0, p1 = f.plots[0], f.plots[1]
    unselected_width = curve.opts['pen'].width()
    _click_subplot(f, p1)
    _click_subplot(f, p0, modifiers=SHIFT)
    _click_curve(f, p0, curve, modifiers=SHIFT)
    _click_annotation(f, rect, modifiers=SHIFT)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    assert f.selected_annotations == [rect, ellipse]
    assert rect._selected and ellipse._selected
    _click_subplot(f, p1, modifiers=SHIFT)
    _click_curve(f, p0, curve, modifiers=SHIFT)
    _click_annotation(f, rect, modifiers=SHIFT)
    assert f.selected_plots == [p0] and f.selected_curves == []
    assert f.selected_annotations == [ellipse] and not rect._selected
    assert f.active_annotation is ellipse
    assert curve.opts['pen'].width() == unselected_width, "Shift-toggling a curve off must restore its pen"
    f.close()


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


def test_delete_removes_every_selected_kind():
    f, curve, rect, ellipse = _two_annotation_figure()
    p0, p2 = f.plots[0], f.plots[2]
    n_plots, n_curves, n_ann = len(f.plots), len(p0.listDataItems()), len(f.annotations)
    _click_annotation(f, rect)
    _click_curve(f, p0, curve, modifiers=SHIFT)
    _click_subplot(f, p2, modifiers=SHIFT)
    f.delete_selection()
    assert rect not in f.annotations and len(f.annotations) == n_ann - 1
    assert len(p0.listDataItems()) == n_curves - 1
    assert p2 not in f.plots and len(f.plots) == n_plots - 1
    f.close()


def test_delete_leaves_a_deleted_subplots_own_items_to_its_undo():
    f, curve, rect, ellipse = _two_annotation_figure()
    p0 = f.plots[0]
    n_curves, n_ann, n_undo = len(p0.listDataItems()), len(f.annotations), len(f.undo_stack)
    _click_subplot(f, p0)
    _click_curve(f, p0, curve, modifiers=SHIFT)
    _click_annotation(f, ellipse, modifiers=SHIFT)  # ellipse is on p0
    f.delete_selection()
    assert len(f.undo_stack) == n_undo + 1, "only the subplot's own undo entry"
    f.undo()
    restored = f.annotations[-1].parent_plot
    assert len(f.annotations) == n_ann
    assert len(restored.listDataItems()) == n_curves, "undo must bring back the subplot's curves"
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


# Grouped undo: one gesture on N selected items = one Undo entry.

def test_undo_group_nests_and_replays_in_order():
    f = m.LaFigure()
    log = []
    n_undo = len(f.undo_stack)
    with f.undo_group():
        f._push_history(lambda: log.append('undo a'), lambda: log.append('redo a'))
        with f.undo_group():
            f._push_history(lambda: log.append('undo b'), lambda: log.append('redo b'))
    assert len(f.undo_stack) == n_undo + 1, "a nested group folds into the outer one"
    f.undo()
    f.redo()
    assert log == ['undo b', 'undo a', 'redo a', 'redo b']
    single = (lambda: None, lambda: None)
    with f.undo_group():
        f._push_history(*single)
    assert f.undo_stack[-1] == single, "a one-step group is pushed as-is, not wrapped"
    f.close()


def test_multi_delete_is_one_undo_entry_and_round_trips():
    f, curve, rect, ellipse = _two_annotation_figure()
    p0, p2 = f.plots[0], f.plots[2]
    counts = lambda: (len(f.plots), len(f.plots[0].listDataItems()), len(f.annotations))
    before, n_undo = counts(), len(f.undo_stack)
    _click_annotation(f, rect)
    _click_curve(f, p0, curve, modifiers=SHIFT)
    _click_subplot(f, p2, modifiers=SHIFT)
    f.delete_selection()
    after = counts()
    assert after == (before[0] - 1, before[1] - 1, before[2] - 1), after
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert counts() == before
    f.redo()
    assert counts() == after
    f.undo()
    assert counts() == before, "a second undo must still work (holders refreshed by redo)"
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


# Rubber band, arrow nudge, Tab cycling. These use REAL Qt mouse/key events
# (QMouseEvent to the viewport, QTest.keyClick), not direct method calls:
# the band relies on pyqtgraph emitting exactly one click after a drag whose
# moves it never saw, and the keys on Qt's shortcut routing -- only the real
# event path can show either works.
from pyqtgraph.Qt import QtTest


def _mouse(f, etype, scene_pt, buttons, button=QtCore.Qt.LeftButton, mods=QtCore.Qt.NoModifier):
    view = f.layout_widget
    ev = QtGui.QMouseEvent(etype, QtCore.QPointF(view.mapFromScene(scene_pt)), button, buttons, mods)
    QtWidgets.QApplication.sendEvent(view.viewport(), ev)
    app.processEvents()


def _band_drag(f, a, b, mods=QtCore.Qt.NoModifier):
    L = QtCore.Qt.LeftButton
    _mouse(f, QtCore.QEvent.MouseButtonPress, a, L, mods=mods)
    for t in (0.1, 0.5, 1.0):
        _mouse(f, QtCore.QEvent.MouseMove, a + (b - a) * t, L, button=QtCore.Qt.NoButton, mods=mods)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, b, QtCore.Qt.NoButton, mods=mods)


def _key(f, key, mods=QtCore.Qt.NoModifier):
    f.activateWindow()
    app.processEvents()
    QtTest.QTest.keyClick(f, key, mods)
    app.processEvents()


def test_band_from_the_margin_selects_enclosed_subplots_only():
    f, curve, ann = _selection_figure()
    p0 = f.plots[0]
    corner = QtCore.QPointF(2, 2)
    assert f._can_start_band_at(corner), "control: the figure margin starts a band"
    beyond = p0.getViewBox().sceneBoundingRect().bottomRight() + QtCore.QPointF(3, 3)
    _band_drag(f, corner, beyond)
    assert _selected(f) == ([p0], [], None), _selected(f)
    assert f._band is None and not f._suppress_click
    assert not any(isinstance(i, QtWidgets.QGraphicsRectItem) and i.zValue() == 1e6
                   for i in f.layout_widget.scene().items()), "the band rectangle must be removed"
    _mouse(f, QtCore.QEvent.MouseButtonPress, corner, QtCore.Qt.LeftButton)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, corner, QtCore.Qt.NoButton)
    assert _selected(f) == ([], [], None), "the next plain click must not be swallowed"
    f.close()


def _band_start_up_left_of(f, pt):
    """A point up-left of `pt`, still inside the same data area, where a band
    can start -- i.e. clear of curves, legends and annotation padding."""
    for d in range(25, 120, 5):
        for dx, dy in ((d, d), (d, 25), (25, d)):
            cand = pt - QtCore.QPointF(dx, dy)
            if f._can_start_band_at(cand):
                return cand
    raise AssertionError("control: no free point to start a band near %r" % pt)


def test_band_does_not_start_on_a_curve():
    f, curve, rect, ellipse = _two_annotation_figure()
    x, y = curve.xData[len(curve.xData) // 2], curve.yData[len(curve.yData) // 2]
    on_curve = f.plots[0].getViewBox().mapViewToScene(QtCore.QPointF(x, y))
    assert not f._can_start_band_at(on_curve), \
        "a press on a curve belongs to the curve (pyqtgraph clicks it on release)"
    f.close()


def test_band_inside_a_data_area_selects_enclosed_annotations():
    f, curve, rect, ellipse = _two_annotation_figure()
    r = rect.shape_scene_rect()
    start = _band_start_up_left_of(f, r.topLeft())
    _band_drag(f, start, r.bottomRight() + QtCore.QPointF(5, 5))
    assert f.selected_annotations == [rect] and f.selected_plots == [], _selected(f)
    f.close()


def test_shift_band_adds_to_the_selection():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_curve(f, f.plots[0], curve)
    r = rect.shape_scene_rect()
    _band_drag(f, _band_start_up_left_of(f, r.topLeft()), r.bottomRight() + QtCore.QPointF(5, 5),
               mods=SHIFT)
    assert f.selected_curves == [curve] and f.selected_annotations == [rect], _selected(f)
    f.close()


def test_band_never_starts_while_brushing_or_outside_select_mode():
    f, curve, rect, ellipse = _two_annotation_figure()
    inside = _vb_center(f.plots[2])
    f.brush_action.trigger()
    assert not f._can_start_band_at(inside), "brushing owns drags in the data area"
    f.brush_action.trigger()
    f.hand_action.trigger()
    _band_drag(f, QtCore.QPointF(2, 2), f.plots[0].getViewBox().sceneBoundingRect().bottomRight()
               + QtCore.QPointF(3, 3))
    assert f.selected_plots == [], "no band in Hand mode"
    f.close()


def test_arrow_keys_nudge_selected_annotations_one_undo_per_press():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    before = {a: _scene_pos(a) for a in (rect, ellipse)}
    n_undo = len(f.undo_stack)
    _key(f, QtCore.Qt.Key_Right)
    _key(f, QtCore.Qt.Key_Down, QtCore.Qt.ShiftModifier)
    for a in (rect, ellipse):
        moved = _scene_pos(a) - before[a]
        assert abs(moved.x() - f.NUDGE_PX) < 0.5 and abs(moved.y() - f.NUDGE_BIG_PX) < 0.5, (a.kind, moved)
    assert len(f.undo_stack) == n_undo + 2, "one undo entry per key press"
    f.undo()
    f.undo()
    for a in (rect, ellipse):
        assert (_scene_pos(a) - before[a]).manhattanLength() < 0.5
    f.close()


def test_arrow_keys_do_nothing_without_selected_annotations():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_subplot(f, f.plots[0])
    pos, n_undo = _scene_pos(rect), len(f.undo_stack)
    _key(f, QtCore.Qt.Key_Left)
    assert _scene_pos(rect) == pos and len(f.undo_stack) == n_undo
    f.close()


def test_tab_cycles_every_item_in_reading_order_and_wraps():
    f, curve, rect, ellipse = _two_annotation_figure()
    order = f._tab_order()
    assert order[0] is f.plots[0] and order[1] is curve, "top-left subplot first, then its curves"
    assert ellipse in order and rect in order and order.index(rect) > order.index(f.plots[1])

    def current():
        sel = f.selected_plots + f.selected_curves + f.selected_annotations
        assert len(sel) == 1, sel
        return sel[0]

    for expected in order + [order[0]]:
        _key(f, QtCore.Qt.Key_Tab)
        assert current() is expected, (expected, current())
    _key(f, QtCore.Qt.Key_Backtab, QtCore.Qt.ShiftModifier)  # what a keyboard sends for Shift+Tab
    assert current() is order[-1]
    assert isinstance(QtWidgets.QApplication.focusWidget(), pg.GraphicsLayoutWidget), \
        "Tab must not move keyboard focus to the toolbar"
    f.close()


for _test in (
    test_band_from_the_margin_selects_enclosed_subplots_only,
    test_band_does_not_start_on_a_curve,
    test_band_inside_a_data_area_selects_enclosed_annotations,
    test_shift_band_adds_to_the_selection,
    test_band_never_starts_while_brushing_or_outside_select_mode,
    test_arrow_keys_nudge_selected_annotations_one_undo_per_press,
    test_arrow_keys_do_nothing_without_selected_annotations,
    test_tab_cycles_every_item_in_reading_order_and_wraps,
    test_undo_group_nests_and_replays_in_order,
    test_multi_delete_is_one_undo_entry_and_round_trips,
    test_multi_properties_is_one_undo_entry,
    test_shift_click_on_empty_space_changes_nothing,
    test_escape_deselects_everything,
    test_escape_cancels_relink_and_deselects_in_one_press,
    test_shift_click_toggles_every_kind,
    test_plain_click_on_a_grouped_annotation_collapses_to_it,
    test_dragging_a_selected_annotation_moves_the_whole_group,
    test_delete_removes_every_selected_kind,
    test_delete_leaves_a_deleted_subplots_own_items_to_its_undo,
    test_properties_apply_to_every_selected_annotation,
    test_curve_click_deselects_the_selected_subplot,
    test_subplot_click_deselects_curve_and_annotation,
    test_annotation_click_deselects_curve_and_subplot,
    test_curve_click_deselects_the_annotation,
    test_shift_click_keeps_every_kind_selected,
    test_right_click_inside_the_selection_keeps_it,
    test_programmatic_selection_is_exclusive_too,
    test_undoing_fft_drops_its_brusher,
    test_new_subplot_adopts_link_x,
    test_link_x_survives_deleting_the_reference_subplot,
    test_new_subplot_adopts_brushing,
    test_brush_off_does_not_reenable_pan_in_select_mode,
    test_add_subplot_is_the_only_subplot_construction_site,
):
    _test()
    app.processEvents()

print("ALL OK")
