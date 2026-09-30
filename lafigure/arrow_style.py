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

""""Arrow Style..." -- the modeless popup (PLAN.md round 4, R4-STYLE) for
an arrow-family annotation's (`arrow`/`doublearrow`/`textarrow`)
arrowhead: head length, head width (both in px) and head type
(arrow/round/diamond/none, see annotations.arrowhead_polygon_points),
with a live preview and OK/Reset/Cancel -- modeled closely on
transform.py's TransformDialog (same modeless-popup, live-apply,
commit-as-one-undo-entry shape; read that module's docstring first).

Persistence (user-specified in scope): the length/width/type chosen here
are also saved to QSettings("LaFigure", "LaFigure") on commit, and read
back by default_head_style() as the default for the NEXT NEW arrow-family
annotation placed (annotation_ops.py's _create_annotation) -- a user
PREFERENCE, not per-annotation state (each annotation's own current style
is serialized on itself via to_dict/from_dict, same as everything else an
undo/copy-paste needs to survive)."""
import math

from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from .annotations import (ARROWHEAD_PX_DEFAULT, DEFAULT_HEAD_WIDTH_PX, DEFAULT_HEAD_TYPE,
                          ARROW_HEAD_TYPES, arrowhead_polygon_points)

SETTINGS_KEY_LENGTH = 'annotation/arrow_head_length'
SETTINGS_KEY_WIDTH = 'annotation/arrow_head_width'
SETTINGS_KEY_TYPE = 'annotation/arrow_head_type'

HEAD_TYPE_LABELS = (("Arrow", 'arrow'), ("Round", 'round'), ("Diamond", 'diamond'), ("None", 'none'))
LENGTH_RANGE = (4, 40)
WIDTH_RANGE = (2, 40)


def _settings(settings=None):
    return settings if settings is not None else QtCore.QSettings("LaFigure", "LaFigure")


def default_head_style(settings=None):
    """The persisted (length, width, type) a brand-new arrow-family
    annotation should start with -- today's fixed look
    (ARROWHEAD_PX_DEFAULT/DEFAULT_HEAD_WIDTH_PX/DEFAULT_HEAD_TYPE) until
    the user has ever clicked OK on this dialog at least once."""
    s = _settings(settings)
    length = float(s.value(SETTINGS_KEY_LENGTH, ARROWHEAD_PX_DEFAULT))
    width = float(s.value(SETTINGS_KEY_WIDTH, DEFAULT_HEAD_WIDTH_PX))
    head_type = str(s.value(SETTINGS_KEY_TYPE, DEFAULT_HEAD_TYPE))
    if head_type not in ARROW_HEAD_TYPES:
        head_type = DEFAULT_HEAD_TYPE
    return length, width, head_type


class ArrowPreviewWidget(QtWidgets.QWidget):
    """A small flat widget drawing one horizontal line + the currently
    chosen arrowhead, in plain device pixels -- shares its geometry with
    the real annotation's own paint() via arrowhead_polygon_points, so
    the preview is never out of sync with what gets drawn on the figure."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 60)
        self._length, self._width, self._head_type = ARROWHEAD_PX_DEFAULT, DEFAULT_HEAD_WIDTH_PX, DEFAULT_HEAD_TYPE

    def set_style(self, length, width, head_type):
        self._length, self._width, self._head_type = length, width, head_type
        self.update()

    def paintEvent(self, ev):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        tail = QtCore.QPointF(20, self.height() / 2)
        tip = QtCore.QPointF(self.width() - 20, self.height() / 2)
        pen = QtGui.QPen(QtGui.QColor('black'), 2)
        painter.setPen(pen)
        painter.drawLine(tail, tip)
        pts = arrowhead_polygon_points(tip, tail, self._length, self._width, self._head_type)
        if pts:
            painter.setBrush(QtGui.QBrush(QtGui.QColor('black')))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPolygon(QtGui.QPolygonF(pts))
        painter.end()


class ArrowStyleDialog(QtWidgets.QDialog):
    """The per-selection popup opened by an arrow-family annotation's
    right-click 'Arrow Style...' (AnnotationOpsMixin.open_arrow_style_dialog,
    annotation_ops.py). Modeless (a user-specified requirement, not
    TransformDialog's default either): edits apply live to every target
    while dragging a slider, OK commits as ONE undo entry (and persists
    the choice as the default for the next NEW arrow-family annotation),
    Cancel (or Esc, or closing the window some other way -- see reject())
    restores what the dialog opened with, Reset goes back to today's
    fixed look (not the persisted default -- a literal "start over")."""

    def __init__(self, figure, targets, parent=None, settings=None):
        super().__init__(parent)
        self.figure = figure
        self.targets = list(targets)
        self._settings = _settings(settings)
        self._done = False
        self.setModal(False)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self.setWindowTitle("Arrow Style")
        # {ann: (length, width, type)} as of opening -- Cancel's target,
        # and set_arrow_style's "before" for the eventual undo entry.
        self.opened_with = {a: (a.head_length, a.head_width, a.head_type) for a in self.targets}
        seed = self.targets[0]

        self.preview = ArrowPreviewWidget(self)

        self.length_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.length_slider.setRange(*LENGTH_RANGE)
        self.length_label = QtWidgets.QLabel(self)

        self.width_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.width_slider.setRange(*WIDTH_RANGE)
        self.width_label = QtWidgets.QLabel(self)

        self.type_group = QtWidgets.QButtonGroup(self)
        self.type_buttons = {}
        type_row = QtWidgets.QHBoxLayout()
        for label, code in HEAD_TYPE_LABELS:
            btn = QtWidgets.QRadioButton(label, self)
            self.type_group.addButton(btn)
            self.type_buttons[code] = btn
            type_row.addWidget(btn)
            btn.toggled.connect(self._on_value_changed)

        self._show_values(*self.opened_with[seed])

        form = QtWidgets.QFormLayout()
        length_row = QtWidgets.QHBoxLayout()
        length_row.addWidget(self.length_slider)
        length_row.addWidget(self.length_label)
        width_row = QtWidgets.QHBoxLayout()
        width_row.addWidget(self.width_slider)
        width_row.addWidget(self.width_label)
        form.addRow("Head length (px)", length_row)
        form.addRow("Head width (px)", width_row)
        form.addRow("Head type", type_row)

        self.length_slider.valueChanged.connect(self._on_value_changed)
        self.width_slider.valueChanged.connect(self._on_value_changed)

        buttons = QtWidgets.QDialogButtonBox(self)
        self.ok_button = buttons.addButton(QtWidgets.QDialogButtonBox.Ok)
        self.reset_button = buttons.addButton("Reset", QtWidgets.QDialogButtonBox.ResetRole)
        self.cancel_button = buttons.addButton(QtWidgets.QDialogButtonBox.Cancel)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.reset_button.clicked.connect(self.reset)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.preview)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _show_values(self, length, width, head_type):
        for slider, value in ((self.length_slider, length), (self.width_slider, width)):
            slider.blockSignals(True)
            slider.setValue(int(round(value)))
            slider.blockSignals(False)
        btn = self.type_buttons.get(head_type, self.type_buttons[DEFAULT_HEAD_TYPE])
        btn.blockSignals(True)
        btn.setChecked(True)
        btn.blockSignals(False)
        self._refresh_preview()

    def current_head_type(self):
        for code, btn in self.type_buttons.items():
            if btn.isChecked():
                return code
        return DEFAULT_HEAD_TYPE

    def current(self):
        """(length, width, head_type) the sliders/radios show right now."""
        return self.length_slider.value(), self.width_slider.value(), self.current_head_type()

    def _refresh_preview(self):
        length, width, head_type = self.current()
        self.length_label.setText(f"{length:g}")
        self.width_label.setText(f"{width:g}")
        self.preview.set_style(length, width, head_type)

    def _on_value_changed(self, *_args):
        self._refresh_preview()
        if not self._done:
            length, width, head_type = self.current()
            self.figure._apply_arrow_style_live(self.targets, length, width, head_type)

    def reset(self):
        """Back to today's fixed look (ARROWHEAD_PX_DEFAULT/
        DEFAULT_HEAD_WIDTH_PX/DEFAULT_HEAD_TYPE) -- applied live like any
        other edit, same as TransformDialog.reset()."""
        self._show_values(ARROWHEAD_PX_DEFAULT, DEFAULT_HEAD_WIDTH_PX, DEFAULT_HEAD_TYPE)
        self._on_value_changed()

    def _finish(self, commit):
        if self._done:
            return
        self._done = True
        if commit:
            length, width, head_type = self.current()
            self.figure.set_arrow_style(self.targets, length, width, head_type, self.opened_with)
            self._settings.setValue(SETTINGS_KEY_LENGTH, length)
            self._settings.setValue(SETTINGS_KEY_WIDTH, width)
            self._settings.setValue(SETTINGS_KEY_TYPE, head_type)
        else:
            for ann, (length, width, head_type) in self.opened_with.items():
                ann.prepareGeometryChange()
                ann.head_length, ann.head_width, ann.head_type = length, width, head_type
                ann.update()
        if getattr(self.figure, '_arrow_style_dialog', None) is self:
            self.figure._arrow_style_dialog = None

    def accept(self):
        self._finish(commit=True)
        super().accept()

    def reject(self):
        """Cancel and Esc: back to what the popup opened with."""
        self._finish(commit=False)
        super().reject()

    def closeEvent(self, ev):
        """Closing the window keeps the edits (QDialog's default would
        reject them) -- same convention as TransformDialog.closeEvent."""
        self._finish(commit=True)
        ev.accept()
        self.hide()
