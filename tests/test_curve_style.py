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

"""Curve display style (curve_style.py): every edit is undoable and goes
through the selection highlight, so it survives select/deselect, and
to_dict (copy/paste) records the real style, never the highlight."""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

from lafigure.curve_style import has_current_line, line_capable
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
    assert c.opts['pen'] is not None and pg.mkPen(c.opts['pen']).style() == QtCore.Qt.NoPen, \
        "NoPen, not merely a transparent color -- paintGL() ignores alpha (CLAUDE.md bug #27)"
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


def test_line_color_and_marker_color_are_independent():
    f, p, c = _line_figure()
    f.set_curve_marker([c], 'o')
    line_before = pg.mkPen(c.opts['pen']).color().getRgb()[:3]
    f.set_curve_marker_color([c], (0, 255, 0))
    assert pg.mkBrush(c.opts['symbolBrush']).color().getRgb()[:3] == (0, 255, 0)
    assert pg.mkPen(c.opts['symbolPen']).color().getRgb()[:3] == (0, 255, 0)
    assert pg.mkPen(c.opts['pen']).color().getRgb()[:3] == line_before, "line untouched"
    f.set_curve_line_color([c], (0, 0, 255))
    assert pg.mkPen(c.opts['pen']).color().getRgb()[:3] == (0, 0, 255)
    assert pg.mkBrush(c.opts['symbolBrush']).color().getRgb()[:3] == (0, 255, 0), "marker untouched"
    f.undo()   # line color
    assert pg.mkPen(c.opts['pen']).color().getRgb()[:3] == line_before
    f.undo()   # marker color
    assert pg.mkBrush(c.opts['symbolBrush']).color().getRgb()[:3] == (200, 50, 50), \
        "back to the marker's original auto-color"
    f.close()


def test_line_color_on_a_none_style_line_stays_invisible():
    f, p, c = _line_figure()
    f.set_curve_line_style([c], 'none')
    f.set_curve_line_color([c], (0, 255, 0))
    pen = pg.mkPen(c.opts['pen'])
    assert pen.style() == QtCore.Qt.NoPen, "still invisible: 'none' style isn't undone by recoloring"
    assert pen.color().getRgb()[:3] == (0, 255, 0), "but the color underneath did change"
    f.set_curve_line_style([c], '-')
    assert pg.mkPen(c.opts['pen']).color().getRgb()[:3] == (0, 255, 0), "the new color shows once visible"
    f.close()


def test_scatter_marker_color_applies_line_color_does_not():
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0)
    s = ax.scatter(np.arange(5.0), np.arange(5.0), size=4)
    n = len(f.undo_stack)
    f.set_curve_line_color([s.item], (255, 0, 0))
    assert len(f.undo_stack) == n, "a scatter has no line: nothing to undo"
    f.set_curve_marker_color([s.item], (255, 0, 0))
    assert pg.mkBrush(s.item.opts['symbolBrush']).color().getRgb()[:3] == (255, 0, 0)
    assert len(f.undo_stack) == n + 1
    f.close()


def test_scatter_is_line_capable_but_has_no_current_line_by_default():
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0)
    s = ax.scatter(np.arange(5.0), np.arange(5.0), size=4)
    c = s.item
    assert line_capable('scatter'), "a scatter's item is a real PlotDataItem: it CAN draw a line"
    assert not has_current_line('scatter', c.opts['pen']), "but not by default (transparent pen)"
    f.close()


def test_scatter_line_style_turns_a_real_line_on_then_width_and_color_apply():
    """The root bug this package fixes: gating Line Width/Style/Color
    purely by kind string ('scatter' not in the old _LINE_KINDS) meant
    these never applied even once a scatter was visibly drawing a real
    line. Line Style must be able to turn one on regardless of kind
    membership; once a real line is visible, Width/Color must actually
    apply too, not just report as "enabled" cosmetically."""
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0)
    s = ax.scatter(np.arange(5.0), np.arange(5.0), size=4)
    c = s.item
    n = len(f.undo_stack)
    f.set_curve_line_style([c], '-')
    pen = pg.mkPen(c.opts['pen'])
    assert pen.color().alpha() == 255 and pen.style() == QtCore.Qt.SolidLine
    assert len(f.undo_stack) == n + 1
    assert has_current_line('scatter', c.opts['pen']), "now a real line is drawn"

    f.set_curve_line_width([c], 5)
    assert pg.mkPen(c.opts['pen']).widthF() == 5, "width now applies: a real line exists"
    f.set_curve_line_color([c], (0, 255, 0))
    assert pg.mkPen(c.opts['pen']).color().getRgb()[:3] == (0, 255, 0)
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


def test_curves_to_front_pokes_refresh_legend_order_only_if_present():
    """Package P3 (view_ops.py) owns _refresh_legend_order; this package
    must call it if present. P3 is merged now, so the real method exists --
    monkeypatch it on the instance to observe the call sites without
    depending on its own implementation."""
    f, p, c = _line_figure()
    c2 = f._add_series(p, 'line', np.arange(10.0), np.arange(10.0), name="lin").item
    assert hasattr(f, '_refresh_legend_order'), "P3's real method should be present"
    f.curves_to_front([c], True)   # must not raise
    f.undo()

    calls = []
    f._refresh_legend_order = lambda: calls.append(True)
    try:
        f.curves_to_front([c], True)
        assert calls, "called on the initial apply"
        f.undo()
        assert len(calls) == 2, "called on undo too"
        f.redo()
        assert len(calls) == 3, "called on redo too"
    finally:
        del f._refresh_legend_order
    f.close()


def test_style_edits_and_selection_keep_a_curve_transform():
    """WP-P7: the transform lives in the drawn data, the style in the pen --
    restyling, marking and (de)selecting a transformed curve touch neither
    the transform nor the transformed data."""
    from lafigure.transform import IDENTITY, Transform
    f, p, c = _line_figure()
    s = f._series_of(c)
    t = Transform(dx=1.0, dy=-5.0, sx=2.0, sy=0.5)
    f.set_series_transform(s, t)
    drawn = np.array(s.y, copy=True)
    f._select_curve(c)
    f.set_curve_line_width([c], 3)
    f.set_curve_marker([c], 'o')
    f.set_curve_line_style([c], '--')
    f._deselect_curve()
    assert s.transform == t
    np.testing.assert_array_equal(s.y, drawn)
    f._apply_series_transform(s, IDENTITY)
    np.testing.assert_array_equal(s.y, np.arange(10.0) ** 2)
    assert pg.mkPen(c.opts['pen']).widthF() == 3
    f.close()
