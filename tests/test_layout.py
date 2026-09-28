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

"""The subplot grid (layout.py): single-cell delete never shifts a
sibling, reflow and overlap resize, add subplot, move/swap, and the
add_subplot single-construction-site guard. Geometry checks compare the
neighbors' real sceneBoundingRect(), not just stretch bookkeeping
(CLAUDE.md bug #6).
"""
from pyqtgraph.Qt import QtCore

from tests.helpers import (
    app, m, shown_figure,
)


def test_delete_subplot_sharing_a_row_undo_redo():
    """Undo/redo: delete + recreate a subplot that shares its row with a
    surviving sibling (p3 and p4 are both in row 1 of the default 2x2 grid)."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

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
    win.close()


def test_reflow_resize_changes_stretch():
    """Resize in reflow mode redistributes stretch factors."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

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
    win.close()


def test_overlap_resize_never_moves_neighbors():
    """Overlap mode: neighbors must NEVER change size, during the drag or after release."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

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
    win.close()


def test_add_new_subplot_undo_redo_and_stretch_reset():
    """Undo/redo: add a new subplot; structural changes reset manual sizing."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

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
    win.close()


def test_move_handle_swaps_and_drop_on_empty_reattaches():
    """Dragging the move handle onto another subplot swaps their grid cells;
    dropping on empty space puts the subplot back where it started."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots
    far_away = QtCore.QPointF(-999999, -999999)

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
    win.close()


def test_grid_layout_back_on_reflows_to_the_floated_size():
    """Turning Grid Layout back on is "rearrange now": the floated subplot's
    row/col take roughly its floated size -- in the real layout, not just in
    the row_stretch/col_stretch bookkeeping (the check that used to run
    after the loop that empties self.floating, so nothing was applied)."""
    win = shown_figure()
    p1, p2 = win.plots[0], win.plots[1]
    win._on_plot_clicked(p1)
    width_before = p1.sceneBoundingRect().width()
    win.toggle_overlap_resize(True)
    win._begin_resize('bottom-right', QtCore.QPointF(0, 0))
    win._update_resize(QtCore.QPointF(300, 150))
    win._end_resize()
    win.toggle_overlap_resize(False)
    app.processEvents()
    layout = win._grid_layout()
    row, col = win._grid_position(p1)
    assert layout.columnStretchFactor(col) == int(round(win.col_stretch[col])) != 100
    assert layout.rowStretchFactor(row) == int(round(win.row_stretch[row])) != 100
    # Roughly: the stretch factor maps to a size through the layout's own
    # min/preferred sizes, so it's ~+80 px here, not the full floated +300.
    assert p1.sceneBoundingRect().width() > width_before + 40, "p1 grows toward its floated width"
    assert p2.sceneBoundingRect().width() < width_before - 40, "its row neighbor shrinks to fit"
    win.close()


def test_add_subplot_is_the_only_subplot_construction_site():
    """add_subplot is where new subplots adopt the figure-wide toggles; a
    second addPlot() call would silently bypass that. Scans every module of
    the package, since LaFigure's code is spread over its mixins."""
    import glob
    import os
    package_dir = os.path.dirname(m.__file__)
    sites = {}
    for path in glob.glob(os.path.join(package_dir, '*.py')):
        with open(path, encoding='utf-8') as f:
            n = f.read().count('.addPlot(')
        if n:
            sites[os.path.basename(path)] = n
    assert sites == {'layout.py': 1}, f"a new addPlot() call site bypasses add_subplot: {sites}"
    with open(os.path.join(package_dir, 'layout.py'), encoding='utf-8') as f:
        assert 'def add_subplot' in f.read()  # control: the scan is reading the right file
