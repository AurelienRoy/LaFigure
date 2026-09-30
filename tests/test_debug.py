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

"""Tests for lafigure.debug (WP-DBG1). Since enable_debug_mode() installs
GLOBAL, process-wide state (handlers on the 'lafigure' logger, sys.excepthook,
faulthandler, Qt's message handler), every test restores all of it in a
finally block -- this suite runs inside the same process as every other
tests/test_*.py file (run_tests.py), so leaking any of it would affect
unrelated tests that run afterward.
"""
import faulthandler
import logging
import os
import sys

from pyqtgraph.Qt import QtCore

import lafigure as m
from lafigure import debug


def _reset_debug_state():
    """Undo enable_debug_mode()'s global side effects completely, including
    ones its own idempotent-call handling doesn't need to touch (e.g. it
    never uninstalls the Qt handler or faulthandler -- there's no reason to,
    normally -- but a test suite needs the process left exactly as found)."""
    for handler in list(debug._state["handlers"]):
        debug._root_logger.removeHandler(handler)
        handler.close()
    debug._state["handlers"] = []
    if debug._state["log_file"] is not None:
        try:
            debug._state["log_file"].close()
        except Exception:
            pass
        debug._state["log_file"] = None
    debug._state["previous_excepthook"] = None
    sys.excepthook = sys.__excepthook__
    QtCore.qInstallMessageHandler(None)
    faulthandler.disable()
    debug._root_logger.setLevel(logging.WARNING)
    debug._root_logger.propagate = True


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_enable_creates_and_truncates_default_log_file(tmp_cwd=None):
    old_cwd = os.getcwd()
    workdir = os.path.join(old_cwd, "tests", "_debug_scratch")
    os.makedirs(workdir, exist_ok=True)
    os.chdir(workdir)
    try:
        expected = os.path.abspath("lafigure_debug.log")
        # Pre-populate the file with a sentinel, to prove enable_debug_mode
        # truncates rather than appends.
        with open(expected, "w") as f:
            f.write("stale content from a previous run\n")

        returned = m.enable_debug_mode()
        try:
            assert returned == expected
            assert os.path.isfile(expected)
            content = _read(expected)
            assert "stale content from a previous run" not in content
        finally:
            _reset_debug_state()
    finally:
        os.chdir(old_cwd)
        if os.path.isfile(os.path.join(workdir, "lafigure_debug.log")):
            os.remove(os.path.join(workdir, "lafigure_debug.log"))
        os.rmdir(workdir)


def test_child_logger_message_appears_in_file():
    path = m.enable_debug_mode(log_path=os.path.join(os.path.dirname(__file__), "_dbg1.log"))
    try:
        logging.getLogger("lafigure.somemodule").debug("hello from a child logger")
        # Handlers are unbuffered-enough by default (FileHandler flushes on
        # each emit), but flush explicitly to be sure before reading back.
        for h in debug._state["handlers"]:
            h.flush()
        content = _read(path)
        assert "hello from a child logger" in content
        assert "lafigure.somemodule" in content
        assert "DEBUG" in content
    finally:
        _reset_debug_state()
        if os.path.isfile(path):
            os.remove(path)


def test_faulthandler_enabled_and_writes_to_the_log_file():
    path = m.enable_debug_mode(log_path=os.path.join(os.path.dirname(__file__), "_dbg1.log"))
    try:
        assert faulthandler.is_enabled()
        # dump_traceback() is a safe, non-crashing diagnostic dump (unlike a
        # real fault) -- pass the exact file object faulthandler.enable() was
        # given, to confirm it's genuinely wired to the same log file rather
        # than just "enabled somewhere".
        faulthandler.dump_traceback(file=debug._state["log_file"], all_threads=True)
        debug._state["log_file"].flush()
        content = _read(path)
        assert "current thread" in content.lower()
    finally:
        _reset_debug_state()
        if os.path.isfile(path):
            os.remove(path)


def test_excepthook_logs_and_chains_to_previous_hook():
    calls = []

    def fake_previous(exc_type, exc_value, exc_tb):
        calls.append((exc_type, exc_value))

    sys.excepthook = fake_previous
    path = m.enable_debug_mode(log_path=os.path.join(os.path.dirname(__file__), "_dbg1.log"))
    try:
        assert sys.excepthook is debug._excepthook
        assert debug._state["previous_excepthook"] is fake_previous

        try:
            raise ValueError("synthetic uncaught exception")
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()

        # Call the installed hook directly -- never let a real uncaught
        # exception kill the test process.
        sys.excepthook(exc_type, exc_value, exc_tb)

        assert len(calls) == 1
        assert calls[0][0] is ValueError

        for h in debug._state["handlers"]:
            h.flush()
        content = _read(path)
        assert "synthetic uncaught exception" in content
        assert "CRITICAL" in content
    finally:
        _reset_debug_state()
        if os.path.isfile(path):
            os.remove(path)


def test_qt_warning_is_captured():
    path = m.enable_debug_mode(log_path=os.path.join(os.path.dirname(__file__), "_dbg1.log"))
    try:
        QtCore.qWarning("test message from qWarning")
        for h in debug._state["handlers"]:
            h.flush()
        content = _read(path)
        assert "test message from qWarning" in content
        assert "lafigure.qt" in content
    finally:
        _reset_debug_state()
        if os.path.isfile(path):
            os.remove(path)


def test_calling_twice_does_not_duplicate_handlers():
    path = os.path.join(os.path.dirname(__file__), "_dbg1.log")
    try:
        m.enable_debug_mode(log_path=path)
        m.enable_debug_mode(log_path=path)
        assert len(debug._state["handlers"]) == 2  # file + stream, not 4

        logging.getLogger("lafigure.somemodule").debug("only once please")
        for h in debug._state["handlers"]:
            h.flush()
        content = _read(path)
        assert content.count("only once please") == 1
    finally:
        _reset_debug_state()
        if os.path.isfile(path):
            os.remove(path)
