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

"""Toolbar buttons and keyboard shortcuts (toolbar.py). Keys are real
QTest key clicks: shortcut routing is Qt's, which a direct call skips."""
from pyqtgraph.Qt import QtCore

from tests.helpers import shown_figure, _click_subplot, _key


def test_undo_redo_buttons_follow_the_stacks():
    f = shown_figure()
    assert not f.undo_action.isEnabled() and not f.redo_action.isEnabled(), "both start disabled"
    f.add_new_subplot()
    assert f.undo_action.isEnabled() and not f.redo_action.isEnabled()
    f.undo_action.trigger()
    assert not f.undo_action.isEnabled() and f.redo_action.isEnabled()
    f.redo_action.trigger()
    assert f.undo_action.isEnabled() and not f.redo_action.isEnabled()
    f.close()


def test_ctrl_z_ctrl_y_and_del_keys():
    f = shown_figure()
    n = len(f.plots)
    _click_subplot(f, f.plots[1])
    _key(f, QtCore.Qt.Key_Delete)
    assert len(f.plots) == n - 1, "Del deletes the selected subplot"
    _key(f, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
    assert len(f.plots) == n, "Ctrl+Z undoes it"
    _key(f, QtCore.Qt.Key_Y, QtCore.Qt.ControlModifier)
    assert len(f.plots) == n - 1, "Ctrl+Y redoes it"
    f.close()
