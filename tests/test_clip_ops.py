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

"""Copy/paste and delete of curves and subplots (clip_ops.py)."""
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

import lafigure as m
from tests.helpers import (
    app, SHIFT, shown_figure, _click_subplot, _click_curve, _click_annotation,
    _two_annotation_figure, _scene_pos,
)


def test_copy_paste_curve_onto_the_focused_subplot():
    """Copy a curve from one subplot and paste it onto the focused one."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

    win._on_plot_clicked(p2)
    win.copy_curve()
    win._on_plot_clicked(p1)
    before = len(p1.listDataItems())
    win.paste_curve()
    assert len(p1.listDataItems()) == before + 1
    win.close()


def test_delete_curve_undo_redo():
    """Undo/redo: delete + recreate a curve."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

    n_curves_before = len(p1.listDataItems())
    target = [c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)][0]
    win.delete_curve(target)
    assert len(p1.listDataItems()) == n_curves_before - 1
    win.undo()
    assert len(p1.listDataItems()) == n_curves_before
    win.redo()
    assert len(p1.listDataItems()) == n_curves_before - 1
    win.undo()
    win.close()


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


# -- annotation copy/paste (item 3) ------------------------------------------

def test_copy_paste_annotation_offset_on_the_same_subplot():
    """Pasted back onto the subplot it was copied from, an annotation
    must land a few pixels off, not exactly on top of the original."""
    f, curve, rect, ellipse = _two_annotation_figure()  # rect on plots[1]
    before_pos = _scene_pos(rect)
    _click_annotation(f, rect)
    f.copy_annotation()
    assert f.clipboard.last_copied == 'annotation'
    f._on_plot_clicked(rect.parent_plot)
    n_before = len(f.annotations)
    f.paste_annotation()
    assert len(f.annotations) == n_before + 1
    pasted = f.annotations[-1]
    assert pasted is not rect and pasted.kind == 'rect'
    assert pasted.anchor == 'axes' and pasted.parent_plot is rect.parent_plot
    offset = _scene_pos(pasted) - before_pos
    assert offset.x() > 0 and offset.y() > 0, "pasted a few pixels down/right, not on top of the original"
    assert f.selected_annotations == [pasted], "paste selects the new annotation"

    f.undo()
    assert len(f.annotations) == n_before
    f.redo()
    assert len(f.annotations) == n_before + 1
    f.undo()
    f.close()


def test_paste_annotation_lands_on_the_focused_subplot_not_the_original():
    f, curve, rect, ellipse = _two_annotation_figure()  # rect on plots[1]
    other = f.plots[2]
    _click_annotation(f, rect)
    f.copy_annotation()
    f._on_plot_clicked(other)
    n_before = len(f.annotations)
    f.paste_annotation()
    assert len(f.annotations) == n_before + 1
    pasted = f.annotations[-1]
    assert pasted.anchor == 'axes' and pasted.parent_plot is other
    f.close()


def test_copy_paste_figure_annotation_across_windows():
    """A 'figure'-anchored (free-floating) annotation copies/pastes across
    separate LaFigure windows via the shared process-wide Clipboard, same
    as curves and subplots already do."""
    f = m.LaFigure(empty=True)
    f.add_subplot(row=0, col=0)
    f.show()
    app.processEvents()
    ann = f._create_annotation('text', 'figure', None, QtCore.QPointF(30, 30), None, text="hi")
    f._select_annotation(ann)
    f.copy_annotation()

    other = m.LaFigure(empty=True)
    other.show()
    app.processEvents()
    other.paste_annotation()
    assert len(other.annotations) == 1
    pasted = other.annotations[0]
    assert pasted.anchor == 'figure' and pasted.kind == 'text' and pasted.text == "hi"
    other.close()
    f.close()


def test_copy_selection_dispatches_to_annotation_when_only_one_is_selected():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_annotation(f, rect)
    f.copy_selection()
    assert f.clipboard.last_copied == 'annotation'
    assert len(f.clipboard.annotation) == 1
    f.close()


def test_multi_annotation_copy_paste_is_one_undo_entry():
    f, curve, rect, ellipse = _two_annotation_figure()
    _click_annotation(f, rect)
    _click_annotation(f, ellipse, modifiers=SHIFT)
    f.copy_annotation()
    assert len(f.clipboard.annotation) == 2
    f._on_plot_clicked(f.plots[2])
    n_before, n_undo = len(f.annotations), len(f.undo_stack)
    f.paste_annotation()
    assert len(f.annotations) == n_before + 2
    assert len(f.undo_stack) == n_undo + 1
    f.undo()
    assert len(f.annotations) == n_before
    f.close()
