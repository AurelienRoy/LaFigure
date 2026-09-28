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

"""Help dialog showing controls reference, version, and credits."""

from pyqtgraph.Qt import QtWidgets, QtCore

__version__ = "0.1.0"


class HelpMixin:
    """Adds a show_help() method that opens a help dialog."""

    def show_help(self):
        """Open a dialog showing controls reference, version, and credits.

        Uses exec() for a modal dialog in normal mode; in testing/offscreen
        environments, the test can mock exec() to return immediately without blocking.
        """
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("LaFigure Help")
        dialog.setMinimumSize(420, 480)

        layout = QtWidgets.QVBoxLayout()

        # Create a text browser for scrollable, formatted content
        text_browser = QtWidgets.QTextBrowser()
        text_browser.setMarkdown(self._get_help_text())
        text_browser.setReadOnly(True)
        layout.addWidget(text_browser)

        # Close button
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)
        # Keep a reference to the dialog so it's not garbage collected immediately
        self._help_dialog = dialog
        dialog.exec()

    @staticmethod
    def _get_help_text():
        """Return the help text in Markdown format."""
        return f"""# LaFigure Help

## Controls Reference

### Select Mode (default)
- **Click a subplot** to select it (red border)
- **Drag border/corner handles** to resize the subplot
  - Border: resize in one dimension
  - Corner: resize both dimensions
- **Drag center handle** to move or swap the subplot with another
- **Shift+click** to select multiple items (subplots, curves, annotations)
- **Click a curve** to select it (thicker line)
- **Drag from empty space** to draw a selection rectangle
- **Ctrl+C / Ctrl+V** to copy/paste curves
- **Ctrl+Shift+C / Ctrl+Shift+V** to copy/paste subplots
- **Del** to delete the selected item(s)
- **Arrow keys** to nudge selected annotations (1 pixel)
- **Shift+Arrow keys** to nudge selected annotations (10 pixels)
- **Tab / Shift+Tab** to cycle through items
- **Esc** to deselect everything or cancel operations
- **Double-click** a subplot/curve/annotation to edit or deselect

### Hand Mode
- **Pan and zoom** the subplot under the cursor
- **No selection** borders or handles shown
- Toolbar actions still target the active subplot

### Zoom Rect Mode
- **Drag a rectangle** to zoom into that area
- **No selection** borders or handles shown

## Other Features

- **Toggle Legend** to show/hide curve names
- **Data Brushing** to select and analyze points (right-click for options)
- **Link X** to link X axes across all subplots
- **FFT** to compute and display FFT of the selected curve
- **Remove Average** to subtract the mean from all curves on the active subplot
- **Home** to reset the view and show all data
- **Fit Vertical/Horizontal** to adjust axis ranges

## Version
LaFigure {__version__}

## Credits
LaFigure — Copyright 2026, Aurélien ROY

Built on PyQtGraph and Qt

Licensed under BSD 2-Clause License
"""
