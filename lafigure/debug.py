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

"""Debug mode foundation (Round 3, WP-DBG1): one call, `enable_debug_mode()`,
that turns on crash-safe, verbose logging for the whole `lafigure` package so
a user can copy/paste `lafigure_debug.log` back into a bug report.

Frozen interface every sibling package (DBG2/DBG3/DBG4) codes against: use
ordinary hierarchical stdlib logging, `logging.getLogger('lafigure.<module
name>')`, in your own module -- nothing here needs to be imported by them.
This module only configures the root `'lafigure'` logger's handlers/level;
every child logger under it is affected for free, by stdlib logging's own
propagation rules.

What one `enable_debug_mode()` call wires up:
  - A `logging.FileHandler` (mode 'w' -- the log is one fixed file,
    overwritten every run, not timestamped-per-run, per the user's own
    confirmed choice) and a `logging.StreamHandler` (stderr), both on the
    `'lafigure'` logger, level DEBUG, format `LOG_FORMAT` below.
  - `faulthandler.enable(file=<that same log file>, all_threads=True)` --
    the one thing that can leave any trace of a native crash (an access
    violation, no Python traceback at all) in the log. Motivated directly
    by a real such crash found in round 2's follow-up (see CLAUDE.md).
  - `sys.excepthook` wrapped: every uncaught Python exception is logged at
    CRITICAL with its traceback, then the previously-installed hook (Python's
    own default, printing to stderr, unless something else already replaced
    it) still runs -- this never swallows the normal terminal behavior.
  - `QtCore.qInstallMessageHandler(...)`: every Qt-side (C++) warning/
    critical/fatal message is routed through `logging.getLogger('lafigure.qt')`
    instead of going straight to stderr unlogged.

Calling `enable_debug_mode()` more than once is idempotent: the second call
tears down exactly the handlers/hooks the first one installed before
reattaching fresh ones (truncating the log file again), so a subsequent
single log message appears exactly once, never duplicated.
"""
import faulthandler
import logging
import os
import sys

from pyqtgraph.Qt import QtCore

#: Exact log line format, shared by the file and stream handlers.
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

#: Default log file name, resolved against the CURRENT working directory
#: (not this package's own directory) -- that's where a user running an
#: example script actually looks.
DEFAULT_LOG_FILE = "lafigure_debug.log"

_root_logger = logging.getLogger("lafigure")

# Module-level state, so a second enable_debug_mode() call can cleanly undo
# what the first one installed instead of stacking handlers/hooks. Nothing
# here is part of the public API.
_state = {
    "handlers": [],              # our own FileHandler/StreamHandler instances
    "log_file": None,            # the open file object (faulthandler's target too)
    "previous_excepthook": None,  # whatever sys.excepthook was before WE first
                                   # wrapped it -- never overwritten by a later
                                   # call while our own wrapper is still installed
}

_QT_MSG_LEVELS = {
    QtCore.QtDebugMsg: logging.DEBUG,
    QtCore.QtInfoMsg: logging.INFO,
    QtCore.QtWarningMsg: logging.WARNING,
    QtCore.QtCriticalMsg: logging.CRITICAL,
    QtCore.QtFatalMsg: logging.CRITICAL,
}


def _qt_message_handler(msg_type, context, message):
    """Installed via QtCore.qInstallMessageHandler: bridges Qt's own C++-side
    diagnostics into the same 'lafigure' logger hierarchy."""
    level = _QT_MSG_LEVELS.get(msg_type, logging.WARNING)
    logging.getLogger("lafigure.qt").log(level, "%s", message)


def _excepthook(exc_type, exc_value, exc_tb):
    """Installed as sys.excepthook: logs the uncaught exception, then always
    still calls whatever hook was previously installed (Python's own default
    printer, unless something else had already replaced it) -- never
    swallows the normal terminal behavior."""
    logging.getLogger("lafigure").critical(
        "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
    previous = _state["previous_excepthook"]
    if previous is not None:
        previous(exc_type, exc_value, exc_tb)


def enable_debug_mode(log_path=None):
    """Turn on debug mode: verbose logging (file + stderr), faulthandler,
    an exception-hook logger, and a Qt message-handler bridge.

    log_path: where to write the log, default DEFAULT_LOG_FILE resolved
    against the current working directory. Opened in 'w' mode (truncated).

    Returns the absolute path actually written to, so a caller (e.g. an
    example script) can print/report it.

    Idempotent: calling this twice replaces the previously-installed
    handlers/hooks rather than stacking a second copy of each.
    """
    log_path = os.path.abspath(log_path) if log_path else os.path.abspath(DEFAULT_LOG_FILE)

    # Tear down whatever a previous call attached, so handlers never stack.
    for handler in _state["handlers"]:
        _root_logger.removeHandler(handler)
        handler.close()
    _state["handlers"] = []
    if _state["log_file"] is not None:
        try:
            _state["log_file"].close()
        except Exception:
            pass
        _state["log_file"] = None

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.DEBUG)

    _root_logger.setLevel(logging.DEBUG)
    _root_logger.propagate = False  # don't also hand records to Python's own
                                     # root logger, whatever it's configured to do
    _root_logger.addHandler(file_handler)
    _root_logger.addHandler(stream_handler)

    _state["handlers"] = [file_handler, stream_handler]
    _state["log_file"] = file_handler.stream

    # faulthandler: the one thing that can leave any trace of a native crash
    # (no Python traceback at all) in the log -- see this module's docstring.
    faulthandler.enable(file=file_handler.stream, all_threads=True)

    # Only capture "whatever was there before" the first time our own wrapper
    # goes in; a later call sees sys.excepthook is already _excepthook and
    # leaves the recorded previous hook alone, so chaining never points back
    # at ourselves.
    if sys.excepthook is not _excepthook:
        _state["previous_excepthook"] = sys.excepthook
        sys.excepthook = _excepthook

    # Qt only ever holds one C++-side message handler slot, so re-installing
    # ours is naturally idempotent -- no separate teardown needed.
    QtCore.qInstallMessageHandler(_qt_message_handler)

    _root_logger.debug("Debug mode enabled; log file: %s", log_path)
    return log_path
