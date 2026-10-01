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
- **Click again at (about) the same spot** to step through whatever else
  is stacked there (a curve, an annotation, an overlapping subplot) --
  wraps back to the top after the last one; clicking elsewhere (or
  pausing over a second) starts a fresh stack there instead
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
- **Double-click** a subplot/curve to deselect; **double-click a title, axis
  label, legend entry or annotation text** to edit it in place: **Enter**
  commits, **Shift+Enter** starts a new line, **Esc** cancels, clicking
  elsewhere commits
- **Right-click** a title, axis label, legend entry or annotation text for
  **Edit Text** and **Font...** (family, size, bold, italic, underline,
  strikeout, color; undoable)
- Text markup: `\textbf{{..}}` `\textit{{..}}` `x^{{2}}` `x_{{i}}` `\alpha`
  `\times` `\leq` `\pm` `\infty` ... `\textcolor{{red}}{{..}}`; braces are
  required for super/subscript, and unknown commands show as typed
- **Click a legend** to select it; drag it to move it (undoable); Del hides it
- **Right-click a curve** for its own menu: copy/paste, front/back, line
  style, line width, line color, marker, marker size, marker color,
  Transform... (per-curve display offset/scale, resettable), rename, delete
- **Right-click a subplot** (off any curve or annotation) for the subplot
  menu: copy/paste subplot, paste curve, front/back, legend, Reorder
  Curves..., Remove Average, FFT, CSV

### Annotations
- **Annotate toolbar button** to place a shape: **text** on a single
  click; rect/ellipse/line/arrow/double arrow/text+arrow via
  press-drag-release. Data cursors are placed via their own **Data
  Cursor mode** instead (below), not this button.
- **Drag the shape body** to move it; **drag its end-point handle(s)** to
  resize; **drag its rotate handle** (green) to rotate
- **Hold Shift** while placing, resizing, dragging, or rotating an
  annotation to constrain it, LibreOffice-Draw style: rectangles/ellipses
  stay square/circular, every directional shape (line/arrow/double
  arrow/text+arrow) snaps its angle to 45°, movement locks to a 45° screen
  direction, and rotation snaps to 45° steps
- **Ctrl+C / Ctrl+V** copy/paste the selected annotation(s) too (offset a
  few pixels so a same-window paste doesn't land exactly on the original)
- **Right-click** an annotation for Copy/Paste Annotation, Line Style/Line
  Width/Color... (Fill... too for a rectangle/ellipse), Arrow Style...
  (head length/width/type -- arrow/round/diamond/none, for a
  line/arrow/double arrow/text+arrow), Link to... (click a subplot to
  reparent) -- an
  unlinked annotation also lists a direct **Link to subplot `<name>`**
  shortcut for every subplot its own bounding box currently overlaps --
  and Delete
- **Data Cursor** annotations are a special case, unlike every other
  kind: no yellow grab handles at all. **Drag the round marker** on the
  curve to slide it to a nearby sample on the SAME curve (**Alt+drag**
  switches it to the nearest sample on a DIFFERENT curve instead); **drag
  the label text** to reposition it (Shift snaps the angle, same as a
  line). Hovering shows an insertion cursor over the marker, a
  horizontal/vertical-arrows cursor over the text. Clicking the marker,
  text, or line selects it -- **no dashed outline**; the line turns red
  instead. Its right-click menu has no Copy/Paste or Link to... (only
  **Add New Datacursor**, a nearby copy), but keeps Line Style/Width/
  Color/Font. Its point stays pinned exactly on a curve sample (2D or
  3D, following the camera as it orbits); deleting that sample via Brush
  mode removes the cursor too, as one undo. These gestures and this menu
  work in **both** Select mode and Data Cursor mode (below).

### Hand Mode
- **Pan and zoom** the subplot under the cursor
- **No selection** borders or handles shown
- Toolbar actions still target the active subplot

### Zoom Rect Mode
- **Drag a rectangle** to zoom into that area
- **Click** (no drag) to zoom in 3x, centered on the clicked point
- **Double-click** to zoom out 3x, same centering
- **Right-drag** to zoom/unzoom dynamically (per axis)
- **No selection** borders or handles shown -- a click never selects a
  subplot/curve/annotation in this mode, even one right under the cursor

### Rotate + Zoom Mode
- **3D subplots only** -- enabled only while a 3D subplot is focused;
  acts like Hand mode on a 2D subplot
- **Drag** to orbit the camera, **right-drag** to pan, **wheel** to dolly
  (today's default 3D camera behavior, moved under its own mode)
- A 3D subplot's right-click menu adds a **Camera View** submenu (X-Y,
  X-Z, Y-Z, Sideway presets) and a **Projection** submenu
  (Perspective/Orthographic), and drops FFT (not meaningful on a 3D
  scene); a 2D subplot's menu gets a **Scale** submenu instead (X/Y:
  Linear/Log), undoable

### Brush Mode
- **Drag a rectangle** to brush points; **Shift+drag** adds to the brushed set
- **Right-click** for the brushed-point actions (delete, transform, stats, fit, hide)
- **Del** deletes the brushed points (not a subplot/curve/annotation selection)
- A mode like Select/Hand/Zoom Rect/Rotate + Zoom/Data Cursor: choosing
  one unchecks the others

### Data Cursor Mode
- A persistent mode (toolbar), not a one-shot placement: **no pan**
- **Click** a subplot's data area to move that subplot's own last
  datacursor to the nearest curve point; **Shift+click** always adds a
  new one instead of moving
- A plain click in a subplot with no datacursor yet creates one (same as
  Shift+click), since there's nothing to move
- Each subplot tracks its own "last datacursor" independently -- clicking
  in one subplot never moves another subplot's
- An existing datacursor's own marker/text drag, hover cursors, and Del
  to delete all still work in this mode exactly as in Select mode (see
  the Data Cursor annotation bullet above)

Every zoom and pan (rectangle, wheel, drag, Home, Fit, View All) is one
**Ctrl+Z / Ctrl+Y** step.

## Other Features

- **Figure Manager** (toolbar, leftmost) to open the Figure Browser /
  Curve Browser window -- the Curve Browser lists **Curves** and
  **Annotations** as two separate categories, each with its own
  checkbox that shows/hides every item under it
- **Toggle Legend** to show/hide curve names; a curve named with a
  leading `_` (matplotlib's `"_nolegend_"` convention) is never listed;
  entries are ordered front-most (highest z-order) first
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
