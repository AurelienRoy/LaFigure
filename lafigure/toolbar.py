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

"""LaFigure's toolbar and keyboard shortcuts.

Every button and QShortcut is created here, in _build_toolbar; the slots
they call live in the other mixins. Packages that need a new button send
a one-line diff for this file rather than editing it (see PLAN.md).
"""
import os
import sys
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from .annotations import SHAPE_KINDS, SHAPE_LABELS

# icons/ lives next to this package's containing directory (the repo
# root), not inside the package itself.
ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'icons'
)


def _fit_icon(vertical):
    """Fit Vertical / Fit Horizontal toolbar icon, drawn here since icons/
    has none: a double arrow between two end bars."""
    pix = QtGui.QPixmap(18, 18)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtGui.QPen(QtGui.QColor(40, 40, 40), 1.6))
    lines = [(2, 2, 16, 2), (2, 16, 16, 16), (9, 4, 9, 14),
             (9, 4, 6, 7), (9, 4, 12, 7), (9, 14, 6, 11), (9, 14, 12, 11)]
    for x0, y0, x1, y1 in lines:
        if not vertical:
            x0, y0, x1, y1 = y0, x0, y1, x1
        painter.drawLine(QtCore.QPointF(x0, y0), QtCore.QPointF(x1, y1))
    painter.end()
    return QtGui.QIcon(pix)


class ToolbarMixin:
    def _build_toolbar(self):
        tb = QtWidgets.QToolBar("Tools")
        tb.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(tb)
        style = self.style()

        def action(label, slot, checkable=False, icon=None, tooltip=None):
            act = QtGui.QAction(label, self)
            if isinstance(icon, str):
                # Filename in icons/; missing file falls back to no icon.
                path = os.path.join(ICON_DIR, icon)
                if os.path.isfile(path):
                    act.setIcon(QtGui.QIcon(path))
                else:
                    print(f"WARNING: icon file not found: {path}", file=sys.stderr)
            elif icon is not None:
                act.setIcon(style.standardIcon(icon))
            act.setToolTip(tooltip or label)
            act.setCheckable(checkable)
            act.triggered.connect(slot)
            tb.addAction(act)
            return act

        def menu_button(icon, tooltip, entries):
            # entries: list of (label, slot)
            btn = QtWidgets.QToolButton()
            btn.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
            path = os.path.join(ICON_DIR, icon)
            if os.path.isfile(path):
                btn.setIcon(QtGui.QIcon(path))
            else:
                print(f"WARNING: icon file not found: {path}", file=sys.stderr)
            btn.setToolTip(tooltip)
            btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
            menu = QtWidgets.QMenu(btn)
            for entry_label, slot in entries:
                menu.addAction(entry_label).triggered.connect(slot)
            btn.setMenu(menu)
            tb.addWidget(btn)
            return btn

        SP = QtWidgets.QStyle

        action("Save", self.show_save_dialog, icon=SP.SP_DialogSaveButton,
               tooltip="Save: export the figure as PNG/JPG/SVG/PDF, with a "
                       "customizable header (Ctrl+S)")

        action("Add Subplot", self.add_new_subplot, icon=SP.SP_FileDialogNewFolder,
               tooltip="Add Subplot: fill the first empty grid cell, else add a new row")
        action("Delete", self.delete_selection, icon=SP.SP_TrashIcon,
               tooltip="Delete: remove the selected curve, or the active subplot if no curve is selected (Del)")
        self.undo_action = action("Undo", self.undo, icon=SP.SP_ArrowBack, tooltip="Undo last action (Ctrl+Z)")
        self.redo_action = action("Redo", self.redo, icon=SP.SP_ArrowForward, tooltip="Redo last undone action (Ctrl+Y)")
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)

        tb.addSeparator()
        menu_button('pencil.png', "Annotate: place a shape on the figure", [
            (SHAPE_LABELS[kind], lambda checked=False, kind=kind: self.start_placing_annotation(kind))
            for kind in SHAPE_KINDS if kind != 'cursor'
        ])
        action("Data Cursor", lambda: self.start_placing_annotation('cursor'),
               icon='tool_data_cursor.png', tooltip="Data Cursor: place a data-readout marker")

        action("Toggle Legend", self.toggle_legend, icon='tool_legend.png',
               tooltip="Toggle Legend")

        menu_button('tool_text_textbox.png', "Axis Labels", [
            ("X Label", lambda: self.set_axis_label('bottom')),
            ("Y Label", lambda: self.set_axis_label('left')),
        ])

        self.brush_action = action(
            "Brush", self.toggle_brush, checkable=True,
            icon='tool_data_brush.png',
            tooltip="Brush: rectangular data brushing on any subplot -- right-click a "
                     "selection to delete/transform/fit/stat it",
        )
        action("Hide Brushed Points", self.hide_brushed_points, icon=SP.SP_DialogDiscardButton,
               tooltip="Hide Brushed Points: stop drawing the brushed points, in every "
                       "subplot showing the same rows (the data stays intact)")
        action("Show All Points", self.show_all_hidden_points, icon=SP.SP_DialogResetButton,
               tooltip="Show All Points: draw every hidden point again")

        tb.addSeparator()
        mode_group = QtGui.QActionGroup(self)
        mode_group.setExclusive(True)
        self.select_action = action(
            "Select", lambda checked: self.set_interaction_mode('select'), checkable=True,
            icon='tool_pointer.png',
            tooltip="Select: click a subplot to select it, drag its border/corner "
                    "handles to resize, drag its center handle to move/swap it. "
                    "(default)",
        )
        self.hand_action = action(
            "Hand", lambda checked: self.set_interaction_mode('hand'), checkable=True,
            icon='tool_hand.png',
            tooltip="Hand: pan/zoom/grab the subplot under the cursor. No selection.",
        )
        self.zoom_action = action(
            "Zoom Rect", lambda checked: self.set_interaction_mode('zoom'), checkable=True,
            icon='tool_zoom_in.png',
            tooltip="Zoom Rect: drag a rectangle to zoom into it. No selection.",
        )
        mode_group.addAction(self.select_action)
        mode_group.addAction(self.hand_action)
        mode_group.addAction(self.zoom_action)
        self.select_action.setChecked(True)
        action("Home", self.reset_view, icon='ico_breadcrumb_home_on.png',
               tooltip="Home: reset the subplot's view to show all its data (autorange)")
        fit_y = action("Fit Vertical", self.fit_view_vertical,
                       tooltip="Fit Vertical: stretch the Y range to the min/max of the "
                               "curves inside the current X range")
        fit_y.setIcon(_fit_icon(vertical=True))
        fit_x = action("Fit Horizontal", self.fit_view_horizontal,
                       tooltip="Fit Horizontal: stretch the X range to the min/max of the "
                               "curves inside the current Y range")
        fit_x.setIcon(_fit_icon(vertical=False))

        tb.addSeparator()
        self.link_x_action = action(
            "Link X", self.toggle_link_x, checkable=True,
            icon='tool_plot_linked.png', tooltip="Link X: link the X axis across all subplots",
        )
        action("FFT -> subplot below", self.fft_below, icon='fft_icon6.png',
               tooltip="FFT: compute the FFT of the selected curve into a new subplot below")
        action("Remove Average", self.remove_average, icon='icon1b1.png',
               tooltip="Remove Average: subtract the mean from every curve on the active subplot")

        self.console_action = action(
            "Console", self.toggle_console, checkable=True,
            icon=SP.SP_ComputerIcon,
            tooltip="Console: toggle an embedded Python console (fig/gca()/gcf()/np preloaded)",
        )

        tb.addSeparator()
        action("Help", self.show_help, icon=SP.SP_MessageBoxQuestion,
               tooltip="Help: show controls reference (mouse/keys per mode), version, and credits")

        QtGui.QShortcut(QtGui.QKeySequence.Save, self, activated=self.show_save_dialog)
        QtGui.QShortcut(QtGui.QKeySequence.Copy, self, activated=self.copy_selection)
        QtGui.QShortcut(QtGui.QKeySequence.Paste, self, activated=self.paste_selection)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+C"), self, activated=self.copy_subplot)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+V"), self, activated=self.paste_subplot)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), self, activated=self.delete_selection)
        QtGui.QShortcut(QtGui.QKeySequence.Undo, self, activated=self.undo)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Y"), self, activated=self.redo)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+G"), self, activated=self.group_selection)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+G"), self, activated=self.ungroup_selection)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self,
                         activated=lambda: (self._cancel_placing(), self._cancel_relink(),
                                            self._deselect_all()))
        for key, dx, dy in ((QtCore.Qt.Key_Left, -1, 0), (QtCore.Qt.Key_Right, 1, 0),
                            (QtCore.Qt.Key_Up, 0, -1), (QtCore.Qt.Key_Down, 0, 1)):
            for mod, step in ((0, self.NUDGE_PX), (QtCore.Qt.SHIFT, self.NUDGE_BIG_PX)):
                QtGui.QShortcut(QtGui.QKeySequence(int(mod) | int(key)), self,
                                activated=lambda dx=dx, dy=dy, s=step: self.nudge_selection(dx * s, dy * s))
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Tab), self,
                        activated=lambda: self.cycle_selection(1))
        # "Shift+Tab", not Key_Backtab: a real Shift+Tab arrives as Backtab
        # *with* Shift held, which Qt's shortcut map matches as Shift+Tab.
        QtGui.QShortcut(QtGui.QKeySequence("Shift+Tab"), self,
                        activated=lambda: self.cycle_selection(-1))
