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

import logging

from tests.helpers import (
    m, shown_figure,
)


class _ListLogHandler(logging.Handler):
    """Appends record.getMessage() to a plain list -- this project has no
    pytest/caplog, so debug-mode logging tests build this small handler
    themselves (per PLAN.md's Round 3 brief) instead."""
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _attach_log_handler(logger_name='lafigure'):
    """Attach a fresh _ListLogHandler to logging.getLogger(logger_name),
    forcing its level to DEBUG for the duration of the test. Returns
    (logger, handler, old_level) -- caller must remove/restore in a
    finally block so no state leaks into other tests."""
    logger = logging.getLogger(logger_name)
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    handler = _ListLogHandler()
    logger.addHandler(handler)
    return logger, handler, old_level


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


def test_push_history_logs_once_when_an_entry_lands_on_the_stack():
    """A plain (non-grouped) _push_history call logs exactly one record on
    'lafigure.history' -- the point the entry actually lands on
    undo_stack."""
    f = m.LaFigure()
    logger, handler, old_level = _attach_log_handler()
    try:
        f._push_history(lambda: None, lambda: None)
        push_records = [msg for msg in handler.messages if 'push' in msg]
        assert len(push_records) == 1, handler.messages
        assert str(len(f.undo_stack)) in push_records[0]
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    f.close()


def test_push_history_inside_a_group_logs_once_per_entry_not_per_inner_call():
    """Steps folded into an open undo_group() must NOT each log a 'landed
    on the stack' record -- only the group's own close (which pushes
    exactly one combined entry) does."""
    f = m.LaFigure()
    logger, handler, old_level = _attach_log_handler()
    try:
        with f.undo_group():
            f._push_history(lambda: None, lambda: None)
            f._push_history(lambda: None, lambda: None)
            f._push_history(lambda: None, lambda: None)
            assert not any('push' in msg for msg in handler.messages), (
                "no entry may log as landed while the group is still open")
        push_records = [msg for msg in handler.messages if 'push' in msg]
        assert len(push_records) == 1, handler.messages
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    f.close()


def test_undo_and_redo_log_when_they_run_an_entry():
    """undo()/redo() each log a record identifying which one ran, with the
    resulting stack depths."""
    f = m.LaFigure()
    f._push_history(lambda: None, lambda: None)
    logger, handler, old_level = _attach_log_handler()
    try:
        f.undo()
        undo_records = [msg for msg in handler.messages if msg.startswith('undo:')]
        assert len(undo_records) == 1, handler.messages
        assert 'ran entry' in undo_records[0]

        f.redo()
        redo_records = [msg for msg in handler.messages if msg.startswith('redo:')]
        assert len(redo_records) == 1, handler.messages
        assert 'ran entry' in redo_records[0]
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    f.close()


def test_undo_and_redo_log_when_the_stack_is_empty():
    """undo()/redo() must also be distinguishable in the log when there was
    nothing to do, so a bug report can tell 'ran' from 'no-op' apart."""
    f = m.LaFigure()
    f.undo_stack.clear()
    f.redo_stack.clear()
    logger, handler, old_level = _attach_log_handler()
    try:
        f.undo()
        assert any(msg.startswith('undo:') and 'empty' in msg for msg in handler.messages), handler.messages
        f.redo()
        assert any(msg.startswith('redo:') and 'empty' in msg for msg in handler.messages), handler.messages
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    f.close()
