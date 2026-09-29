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

"""Figure-wide brushing (brushing.py)."""
import numpy as np
from pyqtgraph.Qt import QtCore

from tests.helpers import (
    app, m, _mouse,
)


def test_new_subplot_adopts_brushing():
    f = m.LaFigure()
    f.brush_action.trigger()
    f.add_new_subplot()
    new = f.plots[-1]
    assert f._brushers[new].brushing_enabled, "a subplot added while Brush is on must brush"
    f.close()


def test_brushing_works_in_a_figure_without_the_demo_scatters():
    """A "New Figure" has no linked-scatter SelectionModel: a real brush
    drag (which unbrushes the rest of the figure first) and turning Brush
    off both used to raise AttributeError on self.selection_model."""
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    p = f.add_subplot(row=0, col=0)
    x = np.linspace(0, 100, 1001)
    curve = p.plot(x, x)
    p.getViewBox().setRange(xRange=(0, 100), yRange=(0, 100), padding=0)
    app.processEvents()
    f.brush_action.trigger()
    vb = p.getViewBox()
    a = vb.mapViewToScene(QtCore.QPointF(20, 80))
    b = vb.mapViewToScene(QtCore.QPointF(40, 10))
    L = QtCore.Qt.LeftButton
    _mouse(f, QtCore.QEvent.MouseButtonPress, a, L)
    for t in (0.1, 0.5, 1.0):
        _mouse(f, QtCore.QEvent.MouseMove, a + (b - a) * t, L, button=QtCore.Qt.NoButton)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, b, QtCore.Qt.NoButton)
    items = f._figure_brush_items()
    assert len(items) == 1 and items[0][0] is curve, "control: the real drag brushed the curve"
    brushed_x = curve.xData[items[0][1]]
    assert brushed_x.min() >= 20 - 0.2 and brushed_x.max() <= 40 + 0.2, (brushed_x.min(), brushed_x.max())
    f.select_action.trigger()  # Brush off (Select replaces it)
    f.close()
