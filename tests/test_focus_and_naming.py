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

"""The interfaces WP-01 froze for later work packages: focused_plot and
the registry's focusChanged / selectionChanged / figureRenamed signals,
subplot_name / rename_subplot / rename_figure (undoable), and
add_subplot's rowspan / colspan / axes_type parameters.

The registry is process-wide, so every test filters signals down to its
own figure and disconnects its slot when done.
"""
import contextlib

from pyqtgraph.Qt import QtCore

from tests.helpers import (
    app, m, SHIFT, shown_figure, first_curve, _click_subplot, _click_curve,
    _click_annotation, _selection_figure, _press_escape, _key, _band_drag,
)


@contextlib.contextmanager
def _recording(signal, fig):
    """Collect the arguments of every emission of a registry `signal`
    whose first argument is `fig`."""
    log = []

    def slot(*args):
        if args[0] is fig:
            log.append(args[1:] if len(args) > 1 else args[0])

    signal.connect(slot)
    try:
        yield log
    finally:
        signal.disconnect(slot)


# -- naming ----------------------------------------------------------------

def test_subplot_name_falls_back_to_the_current_title():
    f = shown_figure()
    p = f.plots[1]
    assert f.subplot_name(p) == "Signal B"
    p.setTitle("Edited by double-click")  # what editable_text does
    assert f.subplot_name(p) == "Edited by double-click", "never renamed: follows the title"
    f.close()


def test_rename_subplot_round_trips_through_undo_redo():
    f = shown_figure()
    p = f.plots[1]
    mgr = m.FigureManager()
    app.processEvents()
    n_undo = len(f.undo_stack)
    with _recording(f.registry.subplotsChanged, f) as changed:
        f.rename_subplot(p, "Pressure")
        assert f.subplot_name(p) == "Pressure" and p.titleLabel.text == "Pressure"
        assert len(f.undo_stack) == n_undo + 1
        assert changed, "subplotsChanged lets the Figure Manager relabel the subplot"
        assert mgr._figure_items[f].child(1).text(0) == "Pressure"
        f.undo()
        assert p.titleLabel.text == "Signal B" and f.subplot_name(p) == "Signal B"
        assert getattr(p, 'lafigure_name', None) is None, "undo restores 'never renamed'"
        assert mgr._figure_items[f].child(1).text(0) == "Signal B"
        f.redo()
        assert f.subplot_name(p) == "Pressure" and p.titleLabel.text == "Pressure"
        f.rename_subplot(p, "Temperature")
        f.undo()
        assert f.subplot_name(p) == "Pressure", "undo goes back to the previous explicit name"
    f.close()


def test_rename_figure_round_trips_and_emits_figure_renamed():
    f = shown_figure()
    old = f.windowTitle()
    n_undo = len(f.undo_stack)
    with _recording(f.registry.figureRenamed, f) as renamed:
        f.rename_figure("Test rig 3")
        assert f.windowTitle() == "Test rig 3" and renamed == [f]
        assert len(f.undo_stack) == n_undo + 1
        f.undo()
        assert f.windowTitle() == old and renamed == [f, f]
        f.redo()
        assert f.windowTitle() == "Test rig 3" and len(renamed) == 3
        f.rename_figure("Test rig 3")
        assert len(renamed) == 3 and len(f.undo_stack) == n_undo + 1, "same name: no-op"
    f.close()


# -- focusChanged ----------------------------------------------------------

def test_focus_changed_fires_when_the_focused_subplot_changes():
    f = shown_figure()
    p0, p1 = f.plots[0], f.plots[1]
    assert f.focused_plot is p0, "control: the demo focuses its first subplot"
    with _recording(f.registry.focusChanged, f) as focus:
        _click_subplot(f, p1)
        assert focus == [(p1,)]
        _click_subplot(f, p1)
        assert focus == [(p1,)], "no emission without a change"
        _click_curve(f, p0, first_curve(p0))
        assert focus[-1] == (p0,), "a curve click focuses the curve's subplot"
        _press_escape(f)
        assert focus[-1] == (None,), "deselecting everything clears focus"
        f.add_new_subplot()
        new = f.plots[-1]
        assert focus[-1] == (new,), "a new subplot takes focus"
        f.undo()
        assert new not in f.plots and focus[-1] == (f.plots[0],), \
            "removing the focused subplot moves focus to plots[0]"
    f.close()


def test_focused_plot_has_no_other_writer():
    """Every assignment goes through the property (its setter is the one
    emission site of focusChanged): no module writes the backing field
    except __init__'s initial None."""
    import glob
    import os
    package_dir = os.path.dirname(m.__file__)
    writers = {}
    for path in glob.glob(os.path.join(package_dir, '*.py')):
        with open(path, encoding='utf-8') as fh:
            n = fh.read().count('self._focused_plot = ')
        if n:
            writers[os.path.basename(path)] = n
    assert writers == {'figure.py': 1, 'selection_ui.py': 1}, writers


# -- selectionChanged ------------------------------------------------------

def test_selection_changed_fires_once_per_real_change():
    f, curve, ann = _selection_figure()
    p0, p1 = f.plots[0], f.plots[1]
    with _recording(f.registry.selectionChanged, f) as sel:
        _click_subplot(f, p1)
        assert len(sel) == 1 and sel[0] is f
        _click_subplot(f, p1)
        assert len(sel) == 1, "re-selecting the same subplot is no change"
        _click_curve(f, p0, curve)
        assert len(sel) == 2, "one emission per click, not one per intermediate state"
        _click_annotation(f, ann, modifiers=SHIFT)
        assert len(sel) == 3
        _press_escape(f)
        assert len(sel) == 4 and f.selected_curves == [] and f.selected_annotations == []
        _press_escape(f)
        assert len(sel) == 4, "nothing left to deselect"
        _key(f, QtCore.Qt.Key_Tab)
        assert f.selected_plots == [p0] and len(sel) == 5, "Tab (real key) selects the first item"
        _key(f, QtCore.Qt.Key_Tab)
        assert f.selected_curves == [curve] and len(sel) == 6, "then p0's curve"
        _band_drag(f, QtCore.QPointF(2, 2),
                   p0.getViewBox().sceneBoundingRect().bottomRight() + QtCore.QPointF(3, 3))
        assert f.selected_plots == [p0] and f.selected_curves == [] and len(sel) == 7, \
            "a real band drag emits once"
        _band_drag(f, QtCore.QPointF(2, 2),
                   p0.getViewBox().sceneBoundingRect().bottomRight() + QtCore.QPointF(3, 3))
        assert len(sel) == 7, "the same band again changes nothing"
        _click_annotation(f, ann)
        f.delete_selection()
        assert ann not in f.annotations and len(sel) == 9, "select, then delete"
    f.close()


def test_selection_changed_fires_when_a_selected_item_is_removed():
    f = shown_figure()
    p0 = f.plots[0]
    curve = first_curve(p0)
    _click_curve(f, p0, curve)
    with _recording(f.registry.selectionChanged, f) as sel:
        f.delete_curve(curve)
        assert f.selected_curves == [] and len(sel) == 1
        f.set_interaction_mode('hand')
        assert len(sel) == 1, "nothing selected: switching mode is no selection change"
    f.close()


# -- add_subplot's frozen parameters -----------------------------------------

def test_add_subplot_accepts_spans_and_axes_type():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    wide = f.add_subplot(row=0, col=0, rowspan=1, colspan=2, title="wide", axes_type='cartesian')
    left = f.add_subplot(1, 0)
    right = f.add_subplot(1, 1, title="right")
    app.processEvents()
    assert f.plots == [wide, left, right]
    assert wide.axes_type == left.axes_type == 'cartesian'
    assert wide.titleLabel.text == "wide" and right.titleLabel.text == "right"
    assert f._grid_position(left) == (1, 0) and f._grid_position(right) == (1, 1)
    assert wide.sceneBoundingRect().width() > 1.5 * left.sceneBoundingRect().width(), \
        "colspan is passed through to the grid"
    try:
        f.add_subplot(2, 0, axes_type='polar')  # '3d' exists since WP-O
    except NotImplementedError:
        pass
    else:
        raise AssertionError("an unimplemented axes_type must raise")
    assert len(f.plots) == 3, "a refused axes_type adds nothing"
    f.add_new_subplot()
    assert len(f.plots) == 4, "the grid still works after a spanning subplot"
    f.close()
