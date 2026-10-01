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

"""R4-TREE: a plain left-click on a Figure Browser row (manager.py's
self.tree, NOT the Curve Browser's self.curve_tree, already covered by
test_curve_browser.py) sets the clicked row's figure/subplot as the
FOCUSED subplot -- PLAN.md's "Round 4" item 6 / CLAUDE.md's roadmap
"Figure-browser tree: clicking a row changes that figure's focused
subplot."

Every test that exercises the click itself drives a real QMouseEvent via
QtTest.QTest.mouseClick on the row's own visualItemRect -- CLAUDE.md bugs
#11/#19/#21/#22 are all cases where a direct slot call passed but a real
Qt-delivered click did not (or vice versa), so calling
mgr._on_tree_item_clicked(item, 0) directly would not actually prove this
works.
"""
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtTest

from tests.helpers import app, m, _place


def _two_plot_figure():
    """Two subplots, one curve each, in an otherwise-empty figure -- avoids
    the demo figure's own preselected/focused state so a test can assert
    an exact before/after value instead of "whatever the demo happened to
    pick".
    """
    f = m.LaFigure(empty=True)
    p1 = f.add_subplot(row=0, col=0, title="P1")
    p2 = f.add_subplot(row=0, col=1, title="P2")
    f._add_series(p1, 'line', [0, 1, 2], [0, 1, 2], name='c1')
    f._add_series(p2, 'line', [0, 1, 2], [2, 1, 0], name='c2')
    f.focused_plot = p1
    return f, p1, p2


def _click_row(tree, item):
    """A real left-click on `item`'s own row, centered so it lands clear of
    any disclosure triangle.

    scrollToItem first: other test modules run earlier in the same process
    (via run_tests.py -- this suite has no per-test process isolation)
    leave LaFigure windows open (several existing tests never call
    .close()), and every leaked one gets backfilled into a freshly
    constructed FigureManager's tree (see __init__). With enough of those
    ahead of it, `item`'s own row can end up below the tree's visible
    viewport -- visualItemRect() still reports its (correct) position in
    the tree's full virtual content, but QTest.mouseClick delivers to the
    viewport widget itself and a position beyond its actual rect is
    silently dropped (no itemClicked at all), not "delivered to the
    nearest visible row". Confirmed live: without this, the row is
    genuinely off-screen and the click reaches nothing.
    """
    tree.scrollToItem(item)
    app.processEvents()
    rect = tree.visualItemRect(item)
    pt = rect.center()
    QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.LeftButton, pos=pt)
    app.processEvents()


def test_clicking_a_subplot_row_focuses_that_subplot():
    f, p1, p2 = _two_plot_figure()
    mgr = m.FigureManager()
    mgr.show()
    app.processEvents()
    assert f.focused_plot is p1

    row2 = mgr._fig_plot_rows[f][p2]
    _click_row(mgr.tree, row2)

    assert f.focused_plot is p2
    f.close()
    mgr.close()


def test_clicking_a_subplot_row_fires_registry_focus_changed_once():
    f, p1, p2 = _two_plot_figure()
    mgr = m.FigureManager()
    mgr.show()
    app.processEvents()

    seen = []
    mgr.registry.focusChanged.connect(lambda fig, plot: seen.append((fig, plot)))

    row2 = mgr._fig_plot_rows[f][p2]
    _click_row(mgr.tree, row2)

    assert seen == [(f, p2)]

    # Clicking the ALREADY-focused subplot's own row again is a no-op for
    # the property (its setter's identity guard, selection_ui.py) -- no
    # second signal.
    seen.clear()
    _click_row(mgr.tree, row2)
    assert seen == []
    f.close()
    mgr.close()


def test_clicking_a_curve_row_focuses_its_parent_subplot():
    f, p1, p2 = _two_plot_figure()
    mgr = m.FigureManager()
    mgr.show()
    app.processEvents()
    mgr.show_curves_check.setChecked(True)
    app.processEvents()
    assert f.focused_plot is p1

    row2 = mgr._fig_plot_rows[f][p2]
    curve_row = next(row2.child(i) for i in range(row2.childCount())
                      if row2.child(i).data(0, mgr.ROLE_KIND) == 'curve')
    _click_row(mgr.tree, curve_row)

    assert f.focused_plot is p2
    f.close()
    mgr.close()


def test_clicking_an_annotation_row_focuses_its_parent_subplot():
    f, p1, p2 = _two_plot_figure()
    ann = _place(f, 'rect', p2)
    # Placing an annotation deselects everything, including focus, as a
    # side effect of the placement gesture's own click dispatch -- reset
    # to a known focus here so this test isolates the tree-click behavior
    # under test, not annotation placement's own unrelated side effects.
    f.focused_plot = p1
    mgr = m.FigureManager()
    mgr.show()
    app.processEvents()
    mgr.show_annotations_check.setChecked(True)
    app.processEvents()
    assert f.focused_plot is p1

    row2 = mgr._fig_plot_rows[f][p2]
    ann_row = next(row2.child(i) for i in range(row2.childCount())
                    if row2.child(i).data(0, mgr.ROLE_KIND) == 'annotation'
                    and row2.child(i).data(0, mgr.ROLE_OBJ) is ann)
    _click_row(mgr.tree, ann_row)

    assert f.focused_plot is p2
    f.close()
    mgr.close()


def test_clicking_a_figure_row_raises_and_tracks_that_figure():
    """A figure row has no single subplot to focus -- it makes that figure
    the "tracked/raised" one instead: raised the same way a double-click
    already raises any row's figure, and fed into the Curve Browser tab's
    own recency tracker (_curve_touch) so that tab doesn't stay stuck on
    whichever figure was clicked last (the same staleness class CLAUDE.md's
    Curve-browser bullet already documents for a plain mouse press inside a
    figure -- this is the tree-click equivalent)."""
    f1, p1a, p1b = _two_plot_figure()
    f2, p2a, p2b = _two_plot_figure()
    mgr = m.FigureManager()
    mgr.show()
    app.processEvents()
    # Establish f1 as the currently-tracked figure first.
    mgr._curve_touch(f1, f1.focused_plot)
    assert mgr._curve_current_fig is f1

    fig_row2 = mgr._figure_items[f2]
    _click_row(mgr.tree, fig_row2)

    assert mgr._curve_current_fig is f2
    assert f2.isVisible()
    f1.close()
    f2.close()
    mgr.close()


def test_clicking_a_row_does_not_touch_the_multi_select():
    """Focus only -- CLAUDE.md is explicit that widening what the
    multi-select reaches is a separate product decision; a tree click must
    not select the subplot/curve/annotation it focuses."""
    f, p1, p2 = _two_plot_figure()
    mgr = m.FigureManager()
    mgr.show()
    app.processEvents()
    f._deselect_all()
    app.processEvents()
    assert f.selected_plots == []

    row2 = mgr._fig_plot_rows[f][p2]
    _click_row(mgr.tree, row2)

    assert f.focused_plot is p2
    assert f.selected_plots == []
    assert f.selected_curves == []
    assert f.selected_annotations == []
    f.close()
    mgr.close()


def test_clicking_a_subplot_row_in_a_different_figure_only_focuses_that_figure():
    """Clicking a row belonging to figure B must not disturb figure A's own
    focused_plot."""
    f1, p1a, p1b = _two_plot_figure()
    f2, p2a, p2b = _two_plot_figure()
    mgr = m.FigureManager()
    mgr.show()
    app.processEvents()
    assert f1.focused_plot is p1a
    assert f2.focused_plot is p2a

    row = mgr._fig_plot_rows[f2][p2b]
    _click_row(mgr.tree, row)

    assert f2.focused_plot is p2b
    assert f1.focused_plot is p1a  # untouched
    f1.close()
    f2.close()
    mgr.close()
