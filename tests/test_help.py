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

"""Help dialog tests (help.py)."""

import re
from pyqtgraph.Qt import QtWidgets

from tests.helpers import shown_figure
from lafigure.help import HelpMixin, __version__


def test_show_help_creates_dialog():
    """Calling show_help() on a LaFigure instance creates and displays a dialog."""
    f = shown_figure()

    # Capture the dialog without blocking on exec()
    captured_dialogs_before = set(f.findChildren(QtWidgets.QDialog))

    # Patch exec to not block
    original_exec = QtWidgets.QDialog.exec
    QtWidgets.QDialog.exec = lambda self: QtWidgets.QDialog.Rejected

    try:
        f.show_help()
    finally:
        QtWidgets.QDialog.exec = original_exec

    # Check that a dialog was created
    captured_dialogs_after = set(f.findChildren(QtWidgets.QDialog))
    new_dialogs = captured_dialogs_after - captured_dialogs_before
    assert len(new_dialogs) > 0, "show_help() should create a dialog"

    f.close()


def test_help_dialog_contains_required_keywords():
    """The help dialog's text contains mode names and version pattern."""
    f = shown_figure()

    # Patch exec to not block
    original_exec = QtWidgets.QDialog.exec
    captured_dialog = {}

    def capture_exec(self):
        captured_dialog['dialog'] = self
        return QtWidgets.QDialog.Rejected

    QtWidgets.QDialog.exec = capture_exec

    try:
        f.show_help()
    finally:
        QtWidgets.QDialog.exec = original_exec

    if 'dialog' in captured_dialog:
        dialog = captured_dialog['dialog']
        # Get the text from the QTextBrowser inside the dialog
        text_browser = None
        for child in dialog.findChildren(QtWidgets.QTextBrowser):
            text_browser = child
            break

        assert text_browser is not None, "dialog should contain a QTextBrowser"
        text = text_browser.toPlainText()

        # Check for required keywords
        assert "Select" in text, "help text should mention 'Select' mode"
        assert "Hand" in text, "help text should mention 'Hand' mode"
        assert "Zoom Rect" in text, "help text should mention 'Zoom Rect' mode"

        # Check for version pattern (e.g., "0.1.0")
        version_pattern = r"\d+\.\d+"
        assert re.search(
            version_pattern, text
        ), "help text should contain a version number matching pattern \\d+\\.\\d+"

    f.close()


def test_help_dialog_has_close_button():
    """The help dialog has a Close button that can be clicked."""
    f = shown_figure()

    # Patch exec to not block
    original_exec = QtWidgets.QDialog.exec
    captured_dialog = {}

    def capture_exec(self):
        captured_dialog['dialog'] = self
        return QtWidgets.QDialog.Rejected

    QtWidgets.QDialog.exec = capture_exec

    try:
        f.show_help()
    finally:
        QtWidgets.QDialog.exec = original_exec

    if 'dialog' in captured_dialog:
        dialog = captured_dialog['dialog']
        # Find the close button
        close_buttons = dialog.findChildren(QtWidgets.QPushButton)
        assert len(close_buttons) > 0, "dialog should have a Close button"
        close_button = close_buttons[0]
        assert close_button.text() == "Close"
        # Clicking the button should work without error
        close_button.click()

    f.close()


def test_help_mixin_method_exists():
    """HelpMixin.show_help exists and is callable on a LaFigure instance."""
    f = shown_figure()

    assert hasattr(f, "show_help"), "LaFigure should have a show_help method"
    assert callable(
        f.show_help
    ), "show_help should be callable on LaFigure instance"

    f.close()


def test_help_mixin_get_help_text():
    """HelpMixin._get_help_text contains required content."""
    text = HelpMixin._get_help_text()

    # Check for required mode names
    assert "Select" in text
    assert "Hand" in text
    assert "Zoom Rect" in text

    # Check for version pattern
    assert re.search(r"\d+\.\d+", text)

    # Check for credits
    assert "LaFigure" in text
    assert "Copyright" in text
    assert "2026" in text
    assert "Aurélien ROY" in text or "Aurelien ROY" in text


def test_help_version_string():
    """Version string is defined and matches expected format."""
    assert __version__
    assert re.match(r"\d+\.\d+\.\d+", __version__), f"version should match format X.Y.Z, got {__version__}"
