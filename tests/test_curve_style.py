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

"""Curve display style (curve_style.py): every edit is undoable and goes
through the selection highlight, so it survives select/deselect, and
to_dict (copy/paste) records the real style, never the highlight."""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

from tests.helpers import app, m


def _line_figure():
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0, title="T")
    s = ax.plot(np.arange(10.0), np.arange(10.0) ** 2, pen=pg.mkPen((200, 50, 50), width=1), name="sq")
    return f, ax.plot_item, s.item


def test_width_edit_on_a_selected_curve_survives_deselect_and_undoes():
    f, p, c = _line_figure()
    f._select_curve(c)
    highlight_width = pg.mkPen(c.opts['pen']).widthF()
    f.set_curve_line_width([c], 3)
    assert pg.mkPen(c.opts['pen']).widthF() > 3, "still highlighted: the thicker pen shows"
    f._deselect_curve()
    assert pg.mkPen(c.opts['pen']).widthF() == 3, "the real style changed, not the highlight"
    f.undo()
    assert pg.mkPen(c.opts['pen']).widthF() == 1
    f.redo()
    assert pg.mkPen(c.opts['pen']).widthF() == 3
    f._select_curve(c)
    assert pg.mkPen(c.opts['pen']).widthF() > highlight_width, "re-highlight builds on the new width"
    f.close()


def test_edit_while_unselected_is_not_reverted_by_a_later_deselect():
    f, p, c = _line_figure()
    f._select_curve(c)
    f._deselect_curve()
    f.set_curve_line_width([c], 4)
    f._select_curve(c)
    f._deselect_curve()
    assert pg.mkPen(c.opts['pen']).widthF() == 4, "no stale parked pen restored"
    f.close()


def test_line_style_none_keeps_the_curve_hit_testable_and_comes_back():
    f, p, c = _line_figure()
    f.set_curve_line_style([c], 'none')
    assert c.opts['pen'] is not None and pg.mkPen(c.opts['pen']).color().alpha() == 0
    f.set_curve_line_style([c], '--')
    pen = pg.mkPen(c.opts['pen'])
    assert pen.style() == QtCore.Qt.DashLine and pen.color().alpha() == 255
    f.close()


def test_marker_on_a_line_takes_its_color_and_survives_copy_paste():
    f, p, c = _line_figure()
    f.set_curve_marker([c], 'o')
    assert c.opts['symbol'] == 'o' and c.opts['symbolSize'] == 6
    assert pg.mkBrush(c.opts['symbolBrush']).color().getRgb()[:3] == (200, 50, 50)
    f.set_curve_marker_size([c], 10)
    f._select_curve(c)
    f.copy_curve()
    f.focused_plot = p
    f.paste_curve()
    pasted = p.listDataItems()[-1]
    assert pasted is not c
    assert pasted.opts['symbol'] == 'o' and pasted.opts['symbolSize'] == 10
    assert pg.mkPen(pasted.opts['pen']).widthF() == 1, "the highlight isn't copied"
    f.undo()   # paste
    f.undo()   # size
    f.undo()   # marker
    assert c.opts['symbol'] is None
    f.close()


def test_scatter_marker_edits_apply_and_line_edits_do_not():
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0)
    s = ax.scatter(np.arange(5.0), np.arange(5.0), size=4)
    n = len(f.undo_stack)
    f.set_curve_line_width([s.item], 5)
    assert len(f.undo_stack) == n, "a scatter has no line: nothing to undo"
    f.set_curve_marker([s.item], 's')
    assert s.item.opts['symbol'] == 's' and len(f.undo_stack) == n + 1
    f.close()


def test_curves_to_front_and_back_are_undoable():
    f, p, c = _line_figure()
    c2 = f._add_series(p, 'line', np.arange(10.0), np.arange(10.0), name="lin").item
    f.curves_to_front([c], True)
    assert c.zValue() > c2.zValue()
    f.curves_to_front([c], False)
    assert c.zValue() < c2.zValue()
    f.undo()
    assert c.zValue() > c2.zValue()
    f.close()
