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

"""Per-series display transform: drawn = raw * scale + offset, per axis.

Display-only (PLAN.md round 2, decision 2): a Series keeps a `Transform`
(dx, dy, sx, sy) and draws `apply(raw)`; its DataSource / raw arrays are
never written, so Reset is exact. The item's own data IS the transformed
data, so everything that reads what's drawn (brush hit-test, Selection
Stats, Fit, CSV export, a data cursor) sees the transformed values without
knowing transforms exist. The state lives on the Series (series.py); this
module holds the value type and the popup.

`TransformDialog` is the modeless popup opened by the curve menu's
"Transform...": edits apply live (view only, no undo entry), OK -- or
closing the window -- commits the whole session as ONE undo entry, Cancel
(or Esc) restores the values it opened with, Reset sets offsets 0 and
scales 1 (still live; OK commits it).
"""
from collections import namedtuple

import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets

# Kinds whose get_xy/set_xy are two 1-D arrays drawn as-is, so an
# elementwise offset/scale means exactly "move/stretch what's drawn".
# Not hist (set_xy rebins raw samples), bar/errorbar (bar widths and error
# heights would not follow a scale), imshow or the 3D kinds.
TRANSFORM_KINDS = frozenset({'line', 'scatter', 'stairs', 'area'})


def transform_applies(kind_name):
    return kind_name in TRANSFORM_KINDS


class Transform(namedtuple('Transform', 'dx dy sx sy')):
    """drawn_x = raw_x * sx + dx, drawn_y = raw_y * sy + dy."""
    __slots__ = ()

    def __new__(cls, dx=0.0, dy=0.0, sx=1.0, sy=1.0):
        dx, dy, sx, sy = float(dx), float(dy), float(sx), float(sy)
        if sx == 0 or sy == 0:
            raise ValueError("a transform scale can't be 0 (the raw data couldn't be recovered)")
        return super().__new__(cls, dx, dy, sx, sy)

    @property
    def is_identity(self):
        return self == IDENTITY

    @staticmethod
    def _axis(a, s, d):
        if a is None or (s == 1.0 and d == 0.0):
            return a   # identity on this axis: the very same array, exact
        return np.asarray(a, dtype=float) * s + d

    @staticmethod
    def _axis_inv(a, s, d):
        if a is None or (s == 1.0 and d == 0.0):
            return a
        return (np.asarray(a, dtype=float) - d) / s

    def apply(self, x, y):
        return self._axis(x, self.sx, self.dx), self._axis(y, self.sy, self.dy)

    def invert(self, x, y):
        return self._axis_inv(x, self.sx, self.dx), self._axis_inv(y, self.sy, self.dy)


IDENTITY = Transform()


class TransformDialog(QtWidgets.QDialog):
    """The per-series popup; see the module docstring. One per series at a
    time (SeriesMixin.open_transform_dialog raises an open one)."""

    FIELDS = (('dx', "Offset X"), ('dy', "Offset Y"), ('sx', "Scale X"), ('sy', "Scale Y"))

    def __init__(self, figure, series, parent=None):
        super().__init__(parent)
        self.figure = figure
        self.series = series
        self.opened_with = series.transform
        self._done = False
        self.setModal(False)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self.setWindowTitle("Transform: " + (series.name or "(unnamed curve)"))

        form = QtWidgets.QFormLayout()
        self.spins = {}
        for field, label in self.FIELDS:
            spin = QtWidgets.QDoubleSpinBox(self)
            spin.setDecimals(6)
            spin.setRange(-1e12, 1e12)
            spin.setKeyboardTracking(True)   # live while typing, not only on Enter
            spin.setSingleStep(0.1 if field in ('sx', 'sy') else 1.0)
            self.spins[field] = spin
            form.addRow(label, spin)
        self.dx_spin, self.dy_spin = self.spins['dx'], self.spins['dy']
        self.sx_spin, self.sy_spin = self.spins['sx'], self.spins['sy']
        self._show_values(self.opened_with)
        for spin in self.spins.values():
            spin.valueChanged.connect(self._on_value_changed)

        buttons = QtWidgets.QDialogButtonBox(self)
        self.ok_button = buttons.addButton(QtWidgets.QDialogButtonBox.Ok)
        self.reset_button = buttons.addButton("Reset", QtWidgets.QDialogButtonBox.ResetRole)
        self.cancel_button = buttons.addButton(QtWidgets.QDialogButtonBox.Cancel)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.reset_button.clicked.connect(self.reset)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _show_values(self, t):
        for field, spin in self.spins.items():
            spin.blockSignals(True)
            spin.setValue(getattr(t, field))
            spin.blockSignals(False)

    def current(self):
        """The fields as a Transform, or None while a scale reads 0 (not
        invertible; the last valid one stays drawn)."""
        try:
            return Transform(*(self.spins[f].value() for f, _ in self.FIELDS))
        except ValueError:
            return None

    def _on_value_changed(self, _value=None):
        t = self.current()
        if t is not None and not self._done:
            self.figure._apply_series_transform(self.series, t)

    def reset(self):
        """Offsets 0, scales 1 -- applied live like any edit."""
        self._show_values(IDENTITY)
        self._on_value_changed()

    def _finish(self, commit):
        if self._done:
            return
        self._done = True
        if commit:
            final = self.series.transform
            self.figure.set_series_transform(self.series, final, before=self.opened_with)
        else:
            self.figure._apply_series_transform(self.series, self.opened_with)
        if getattr(self.series, '_transform_dialog', None) is self:
            self.series._transform_dialog = None

    def accept(self):
        self._finish(commit=True)
        super().accept()

    def reject(self):
        """Cancel and Esc: back to what the popup opened with."""
        self._finish(commit=False)
        super().reject()

    def closeEvent(self, ev):
        """Closing the window keeps the edits (QDialog's default would
        reject them)."""
        self._finish(commit=True)
        ev.accept()
        self.hide()
