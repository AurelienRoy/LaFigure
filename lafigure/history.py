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

"""Undo/redo: a bounded stack of (undo_fn, redo_fn) closures, plus
undo_group() to fold one gesture's steps into a single entry.
"""
import contextlib


class HistoryMixin:
    # -- undo / redo -------------------------------------------------
    @contextlib.contextmanager
    def undo_group(self):
        """Fold every _push_history inside this block into one undo entry:
        one gesture = one Undo, as in LibreOffice Draw / MATLAB. Undo runs
        the steps in reverse and redo in order -- exactly what N separate
        presses did, so each step's own closures stay valid. Nests."""
        outer = self._undo_group is None
        if outer:
            self._undo_group = []
        try:
            yield
        finally:
            if outer:
                steps, self._undo_group = self._undo_group, None
                if len(steps) == 1:
                    self._push_history(*steps[0])
                elif steps:
                    self._push_history(
                        undo_fn=lambda: [u() for u, _ in reversed(steps)],
                        redo_fn=lambda: [r() for _, r in steps],
                    )

    def _push_history(self, undo_fn, redo_fn):
        if self._undo_group is not None:
            self._undo_group.append((undo_fn, redo_fn))
            return
        self.undo_stack.append((undo_fn, redo_fn))
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._update_undo_redo_actions()
        self._resync_cursor_points()

    def _update_undo_redo_actions(self):
        self.undo_action.setEnabled(bool(self.undo_stack))
        self.redo_action.setEnabled(bool(self.redo_stack))

    def _resync_cursor_points(self):
        """Best-effort: re-derive every data-cursor annotation's position/
        label from its point_ref against whatever the data is now. Cheap
        (annotation counts stay small) and idempotent, so it's safe to run
        after any undoable action and after undo/redo -- a cursor
        genuinely just tracks its point, it doesn't need its own separate
        undo entry for that (only for existing/not existing at all, which
        brushing.delete_brushed_points handles precisely, at the moment a
        point is actually removed from its curve)."""
        for ann in list(self.annotations):
            if ann.kind == 'cursor' and ann.point_ref is not None:
                ann.refresh_point()

    def undo(self):
        self._close_wheel_gesture()
        if not self.undo_stack:
            return
        undo_fn, redo_fn = self.undo_stack.pop()
        undo_fn()
        self.redo_stack.append((undo_fn, redo_fn))
        self._update_undo_redo_actions()
        self._resync_cursor_points()

    def redo(self):
        self._close_wheel_gesture()
        if not self.redo_stack:
            return
        undo_fn, redo_fn = self.redo_stack.pop()
        redo_fn()
        self.undo_stack.append((undo_fn, redo_fn))
        self._update_undo_redo_actions()
        self._resync_cursor_points()
