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

"""Undo/redo (history.py): round trips, the bounded stack, undo_group."""

from tests.helpers import (
    m, shown_figure,
)


def test_axis_label_history_round_trip():
    """Exercises the same undo/redo push set_axis_label makes internally
    (kept as a direct push rather than driving the real in-place editor
    WP-P8 added, so this test stays independent of that editor's own
    coverage in tests/test_richtext.py)."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

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
    win.close()


def test_history_is_bounded():
    """Pushing more than max_history entries drops the oldest."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

    win.undo_stack.clear()
    win.redo_stack.clear()
    for i in range(win.max_history + 5):
        win._push_history(undo_fn=lambda: None, redo_fn=lambda: None)
    assert len(win.undo_stack) == win.max_history
    win.close()


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
