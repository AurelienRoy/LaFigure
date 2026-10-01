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

"""R4-CBAR: LaColorBar (lafigure/colorbar.py) -- the two fixed dashed
data-min/max lines, independently draggable level limits, live refresh,
and the figure-wide best-effort resync (history.py). Drag behavior is
exercised with real QMouseEvents on the limit lines (CLAUDE.md bugs #11/
#14/#19/#21/#22 -- a direct setter call can't show what Qt's own hit-test
and drag-event routing do), not only by calling set_levels() directly.
"""
import numpy as np
import pyqtgraph as pg

from lafigure.axes import Axes
from lafigure.colorbar import LaColorBar
from lafigure.datasource import DataSource
from tests.helpers import QtCore, _band_drag, app, m


def _imshow_figure(levels=(2, 10), matrix=None):
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    ax = Axes(f, p)
    if matrix is None:
        matrix = np.linspace(0, 14, 15).reshape(3, 5)
    s = ax.imshow(matrix, cmap='viridis', levels=levels)
    cb = s.item._lafigure_colorbar
    f.show()
    app.processEvents()
    return f, s, cb


def _scene_point_for(cb, value):
    """The real scene (screen-pixel) point of `value` on cb's own axis --
    x doesn't matter for an angle=0 (vertical-bar) line, since it's
    "infinite"/full-width; use the bar's own horizontal center."""
    vb = cb.getViewBox()
    if cb.horizontal:
        return vb.mapViewToScene(QtCore.QPointF(value, 0.5))
    return vb.mapViewToScene(QtCore.QPointF(0.5, cb._value_to_pos(value)))


def _drag_line_to_value(f, cb, line, value):
    start = _scene_point_for(cb, cb._pos_to_value(line.value()))
    end = _scene_point_for(cb, value)
    _band_drag(f, start, end)


# -- the two fixed dashed lines -----------------------------------------
def test_fixed_lines_sit_at_the_plotted_data_min_and_max():
    f, s, cb = _imshow_figure(levels=(2, 10), matrix=np.linspace(0, 14, 15).reshape(3, 5))
    assert cb.data_range() == (0.0, 14.0)
    assert not cb._fixed_min_line.movable
    assert not cb._fixed_max_line.movable
    lo_val = cb._pos_to_value(cb._fixed_min_line.value())
    hi_val = cb._pos_to_value(cb._fixed_max_line.value())
    assert lo_val == 0.0
    assert hi_val == 14.0
    f.close()


def test_fixed_lines_never_accept_mouse_buttons():
    f, s, cb = _imshow_figure()
    assert cb._fixed_min_line.acceptedMouseButtons() == QtCore.Qt.NoButton
    assert cb._fixed_max_line.acceptedMouseButtons() == QtCore.Qt.NoButton
    f.close()


def test_fixed_lines_move_after_set_image_with_a_different_range():
    f, s, cb = _imshow_figure(matrix=np.linspace(0, 14, 15).reshape(3, 5))
    assert cb.data_range() == (0.0, 14.0)
    new_matrix = np.linspace(100.0, 200.0, 15).reshape(3, 5)
    s.item.setImage(new_matrix)
    app.processEvents()
    assert cb.data_range() == (100.0, 200.0)
    lo_val = cb._pos_to_value(cb._fixed_min_line.value())
    hi_val = cb._pos_to_value(cb._fixed_max_line.value())
    assert lo_val == 100.0
    assert hi_val == 200.0
    f.close()


# -- dragging a limit line changes only that value -----------------------
def test_dragging_the_low_limit_leaves_the_high_level_byte_identical():
    f, s, cb = _imshow_figure(levels=(2, 10))
    original_lo, original_hi = cb.levels()
    _drag_line_to_value(f, cb, cb._lo_line, 4.0)
    new_lo, new_hi = cb.levels()
    assert new_hi == original_hi, "the untouched limit's value must not change at all"
    assert new_lo != original_lo, "the dragged limit's value must actually change"
    f.close()


def test_dragging_the_high_limit_leaves_the_low_level_byte_identical():
    f, s, cb = _imshow_figure(levels=(2, 10))
    original_lo, original_hi = cb.levels()
    _drag_line_to_value(f, cb, cb._hi_line, 8.0)
    new_lo, new_hi = cb.levels()
    assert new_lo == original_lo, "the untouched limit's value must not change at all"
    assert new_hi != original_hi, "the dragged limit's value must actually change"
    f.close()


def test_drag_past_the_display_range_grows_it_and_keeps_the_other_value():
    f, s, cb = _imshow_figure(levels=(2, 10))
    original_lo, original_hi = cb.levels()
    old_dhi = cb._display_range[1]
    far_value = old_dhi + 200.0  # well past today's display range
    _drag_line_to_value(f, cb, cb._hi_line, far_value)
    new_lo, new_hi = cb.levels()
    assert new_lo == original_lo, "dragging hi past range must not touch lo's value"
    assert new_hi > old_dhi
    assert cb._display_range[1] > old_dhi, "the display range must have grown to fit it"
    f.close()


# -- undo/redo -------------------------------------------------------------
def test_one_undo_entry_per_completed_drag_and_undo_restores_both_levels():
    f, s, cb = _imshow_figure(levels=(2, 10))
    original = cb.levels()
    assert len(f.undo_stack) == 0
    _drag_line_to_value(f, cb, cb._lo_line, 4.0)
    assert len(f.undo_stack) == 1, "exactly one undo entry for the whole drag gesture"
    dragged = cb.levels()
    assert dragged != original
    f.undo()
    assert cb.levels() == original
    f.redo()
    assert cb.levels() == dragged
    f.close()


def test_live_update_while_dragging_fires_sigLevelsChanged():
    f, s, cb = _imshow_figure(levels=(2, 10))
    seen = []
    cb.sigLevelsChanged.connect(lambda bar: seen.append(bar.levels()))
    _drag_line_to_value(f, cb, cb._lo_line, 5.0)
    assert len(seen) >= 1, "sigLevelsChanged must fire live, not only at the end"
    f.close()


# -- gradient clamps outside the level sub-range --------------------------
def test_gradient_clamps_to_end_colors_outside_the_level_sub_range():
    f, s, cb = _imshow_figure(levels=(2, 10), matrix=np.linspace(0, 14, 15).reshape(3, 5))
    img = cb.bar.pixmap().toImage()
    cmap = cb._colorMap
    lo_color = tuple(int(c) for c in cmap.map(np.array([0.0]), mode=pg.ColorMap.BYTE)[0])
    hi_color = tuple(int(c) for c in cmap.map(np.array([1.0]), mode=pg.ColorMap.BYTE)[0])
    # Sample index 0 is the display range's own low end (below the data
    # min, which is itself below the level lo=2) -- must clamp to lo_color.
    below = img.pixelColor(0, 0).getRgb()
    above = img.pixelColor(0, img.height() - 1).getRgb()
    assert below == lo_color
    assert above == hi_color
    f.close()


# -- attach() serves more than an ImageItem --------------------------------
def test_attach_tracks_a_datasource_backed_scatter_via_on_change():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    scatter = pg.ScatterPlotItem(x=[0, 1, 2], y=[0, 1, 2])
    p.addItem(scatter)
    src = DataSource({'x': [0, 1, 2], 'y': [0, 1, 2], 'c': [5.0, 10.0, 15.0]})
    cb = LaColorBar(colorMap='plasma')
    cb.attach(scatter, lambda: src['c'][src.visible_rows], p, source=src)
    assert cb.data_range() == (5.0, 15.0)
    src.filter(np.array([True, True, False]))  # hides the row valued 15.0
    assert cb.data_range() == (5.0, 10.0), "DataSource.on_change must refresh the dashed lines"
    src.filter(None)
    assert cb.data_range() == (5.0, 15.0)
    f.close()


def test_attach_sets_the_colorbar_marker_used_by_the_figure_wide_resync():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    scatter = pg.ScatterPlotItem(x=[0, 1], y=[0, 1])
    p.addItem(scatter)
    cb = LaColorBar()
    cb.attach(scatter, lambda: [1.0, 2.0], p)
    assert scatter._lafigure_colorbar is cb
    f.close()


def test_figure_wide_resync_refreshes_a_colorbar_after_any_undo_history_change():
    """HistoryMixin._resync_colorbars (history.py), called from
    _push_history/undo/redo, catches a data change that fired no signal at
    all -- mirroring _resync_cursor_points's own best-effort stance."""
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    scatter = pg.ScatterPlotItem(x=[0, 1], y=[0, 1])
    p.addItem(scatter)
    box = {'arr': np.array([1.0, 2.0])}
    cb = LaColorBar()
    cb.attach(scatter, lambda: box['arr'], p)
    assert cb.data_range() == (1.0, 2.0)
    box['arr'] = np.array([-5.0, 42.0])  # mutated with no signal of any kind
    assert cb.data_range() == (1.0, 2.0), "control: nothing refreshed it yet"
    f._push_history(lambda: None, lambda: None)  # any undoable action landing
    assert cb.data_range() == (-5.0, 42.0)
    f.undo()
    assert cb.data_range() == (-5.0, 42.0), "resync also runs from undo()"
    f.redo()
    assert cb.data_range() == (-5.0, 42.0), "resync also runs from redo()"
    f.close()


def test_refresh_limits_never_raises_on_a_bad_values_fn():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    scatter = pg.ScatterPlotItem(x=[0, 1], y=[0, 1])
    p.addItem(scatter)
    cb = LaColorBar()

    def bad():
        raise RuntimeError("boom")

    cb.attach(scatter, bad, p)  # must not raise
    assert cb.data_range() == (None, None)
    f.close()
