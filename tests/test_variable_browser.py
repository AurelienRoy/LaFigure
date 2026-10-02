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

"""The Figure Manager's Variable Browser tab (manager.py's _build_variable_
browser/_var_* methods) and its backing logic (variable_browser.py).

The real QDrag/QMimeData machinery a mouse drag would normally drive isn't
exercised headless here (same class of thing CLAUDE.md flags as untestable
offscreen -- there is no real drag-and-drop without a real window manager);
instead these tests call variable_browser.handle_drop/create_new_subplot_
with_variables/add_variables_to_subplot directly, the same "drive the
underlying method directly" pattern test_manager.py already uses for modal
right-click menus. LayoutMixin.eventFilter's own Drag/Drop branch is
covered separately, by feeding it fake event objects (no real QDrag).
"""
import numpy as np
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

import lafigure as m
from lafigure import variable_browser

from tests.helpers import app, shown_figure


def _source():
    return m.DataSource({
        'time': np.arange(10, dtype=float),
        'temp': np.linspace(20, 30, 10),
        'pwm': np.linspace(0, 1, 10),
    })


def test_collect_variables_only_lists_explicit_sources():
    """A plain-array series' private DataSource (columns always named
    'x'/'y') must never show up -- only data a script actually shared via
    ax.plot(source, x=..., y=...)."""
    fig = shown_figure()
    src = _source()
    ax = fig.subplot(2, 0)
    ax.plot(src, x='time', y='temp')
    ax.plot(np.arange(5), np.arange(5))  # plain arrays: a private source

    registry = fig.registry
    rows = variable_browser.collect_variables(registry)
    names = sorted(col for s, col, _, _ in rows if s is src)
    assert names == ['pwm', 'temp', 'time']
    # No 'x'/'y' leaked in from the plain-array curve's private source.
    assert not any(col in ('x', 'y') for _, col, _, _ in rows)
    fig.close()


def test_collect_variables_dedups_a_shared_source():
    fig = shown_figure()
    src = _source()
    ax1 = fig.subplot(2, 0)
    ax2 = fig.subplot(2, 1)
    ax1.plot(src, x='time', y='temp')
    ax2.plot(src, x='time', y='pwm')

    rows = variable_browser.collect_variables(fig.registry)
    matching = [r for r in rows if r[0] is src]
    assert len(matching) == 3  # time/temp/pwm, not doubled
    fig.close()


def test_default_time_column_is_case_insensitive_and_falls_back_to_none():
    src = _source()
    assert variable_browser.default_time_column(src) == 'time'
    src2 = m.DataSource({'Time': np.arange(5.0), 'speed': np.arange(5.0)})
    assert variable_browser.default_time_column(src2) == 'Time'
    src3 = m.DataSource({'speed': np.arange(5.0)})
    assert variable_browser.default_time_column(src3) is None


def test_create_new_subplot_with_variables_builds_one_subplot_n_curves_with_legend():
    fig = shown_figure()
    src = _source()
    n_before = len(fig.plots)

    variable_browser.create_new_subplot_with_variables(fig, src, ['temp', 'pwm'], 'time')
    app.processEvents()

    assert len(fig.plots) == n_before + 1
    new_plot = fig.plots[-1]
    curves = fig._series_on(new_plot)
    assert sorted(c.name for c in curves) == ['pwm', 'temp']
    for c in curves:
        np.testing.assert_allclose(c.x, src['time'])
    # More than one curve -> legend shown by default.
    assert new_plot.legend is not None

    fig.undo()
    assert new_plot not in fig.plots
    fig.redo()
    app.processEvents()
    assert len(fig.plots) == n_before + 1
    restored = fig.plots[-1]
    assert sorted(c.name for c in fig._series_on(restored)) == ['pwm', 'temp']
    fig.close()


def test_create_new_subplot_falls_back_to_row_index_when_no_time_column():
    fig = shown_figure()
    src = m.DataSource({'speed': np.linspace(0, 1, 6)})
    variable_browser.create_new_subplot_with_variables(fig, src, ['speed'], None)
    app.processEvents()
    new_plot = fig.plots[-1]
    curve = fig._series_on(new_plot)[0]
    np.testing.assert_allclose(curve.x, np.arange(6))
    fig.close()


def test_add_variables_to_subplot_appends_curves_as_one_undo_entry():
    fig = shown_figure()
    src = _source()
    p1 = fig.plots[0]
    n_curves_before = len(fig._series_on(p1))

    variable_browser.add_variables_to_subplot(fig, p1, src, ['temp', 'pwm'], 'time')
    app.processEvents()
    assert len(fig._series_on(p1)) == n_curves_before + 2
    assert p1.legend is not None  # now has >1 curve total

    fig.undo()
    assert len(fig._series_on(p1)) == n_curves_before
    fig.redo()
    app.processEvents()
    assert len(fig._series_on(p1)) == n_curves_before + 2
    fig.close()


def test_handle_drop_on_empty_space_creates_a_new_subplot():
    fig = shown_figure()
    src = _source()
    n_before = len(fig.plots)
    # A scene position clearly outside every subplot's box.
    empty_pos = QtCore.QPointF(-500, -500)
    variable_browser.handle_drop(fig, empty_pos, [(src, 'temp')])
    app.processEvents()
    assert len(fig.plots) == n_before + 1
    assert fig._series_on(fig.plots[-1])[0].name == 'temp'
    fig.close()


def test_handle_drop_on_an_existing_subplot_asks_and_adds():
    fig = shown_figure()
    src = _source()
    p1 = fig.plots[0]
    n_curves_before = len(fig._series_on(p1))
    scene_pos = p1.getViewBox().sceneBoundingRect().center()

    original_ask = variable_browser.ask_create_or_add
    variable_browser.ask_create_or_add = lambda parent, name: 'existing'
    try:
        variable_browser.handle_drop(fig, scene_pos, [(src, 'temp')])
        app.processEvents()
    finally:
        variable_browser.ask_create_or_add = original_ask
    assert len(fig._series_on(p1)) == n_curves_before + 1
    fig.close()


def test_handle_drop_only_uses_variables_from_the_first_sources_source():
    fig = shown_figure()
    src1 = _source()
    src2 = m.DataSource({'other': np.arange(4.0)})
    empty_pos = QtCore.QPointF(-500, -500)
    variable_browser.handle_drop(fig, empty_pos, [(src1, 'temp'), (src2, 'other'), (src1, 'pwm')])
    app.processEvents()
    new_plot = fig.plots[-1]
    assert sorted(c.name for c in fig._series_on(new_plot)) == ['pwm', 'temp']
    fig.close()


# -- manager.py's tab: table population, filter, arm/select, drag payload --

def test_variable_table_header_does_not_bold_on_row_selection():
    """QHeaderView.highlightSections defaults to True, which would bold
    every column header when a row is selected -- distracting, and this
    table already has its own red/blue row coloring for what's picked."""
    mgr = m.FigureManager()
    app.processEvents()
    assert mgr.var_table.horizontalHeader().highlightSections() is False
    mgr.close()


def test_variable_table_lists_columns_with_size_and_type_and_filters_live():
    fig = shown_figure()
    src = _source()
    fig.subplot(2, 0).plot(src, x='time', y='temp')

    mgr = m.FigureManager()
    app.processEvents()

    names = [mgr.var_table.item(r, 0).text() for r in range(mgr.var_table.rowCount())]
    assert set(['time', 'temp', 'pwm']) <= set(names)
    row = names.index('temp')
    assert mgr.var_table.item(row, 1).text() == str(len(src))
    assert mgr.var_table.item(row, 2).text() == str(src['temp'].dtype)

    mgr.var_filter_edit.setText('^temp$')
    visible = [r for r in range(mgr.var_table.rowCount()) if not mgr.var_table.isRowHidden(r)]
    assert len(visible) == 1
    assert mgr.var_table.item(visible[0], 0).text() == 'temp'

    mgr.close()
    fig.close()


def _click_with_ctrl(mgr, item):
    """itemClicked carries no QMouseEvent, so _on_var_table_clicked reads
    the Ctrl state _VariableTable's own mousePressEvent override last
    recorded (see its docstring) -- set that directly for one click, the
    same "drive the underlying method directly" pattern test_manager.py
    already uses for modal menus."""
    original = mgr.var_table.last_click_modifiers
    mgr.var_table.last_click_modifiers = QtCore.Qt.ControlModifier
    try:
        mgr._on_var_table_clicked(item)
    finally:
        mgr.var_table.last_click_modifiers = original


def test_plain_y_click_replaces_the_selection_ctrl_click_adds_to_it():
    fig = shown_figure()
    src = _source()
    fig.subplot(2, 0).plot(src, x='time', y='temp')

    mgr = m.FigureManager()
    app.processEvents()

    def row_for(name):
        for r in range(mgr.var_table.rowCount()):
            if mgr.var_table.item(r, 0).text() == name:
                return r
        raise AssertionError(name)

    mgr._var_arm_select('y')
    mgr._on_var_table_clicked(mgr.var_table.item(row_for('temp'), 0))
    assert mgr.var_y_field.text() == 'temp'
    # A plain click on a DIFFERENT row replaces the selection, not adds to it.
    mgr._on_var_table_clicked(mgr.var_table.item(row_for('pwm'), 0))
    assert mgr.var_y_field.text() == 'pwm'
    # Ctrl+click adds instead.
    _click_with_ctrl(mgr, mgr.var_table.item(row_for('time'), 0))
    assert mgr.var_y_field.text() == 'pwm, time'
    # Ctrl+click on an already-selected row toggles it back off.
    _click_with_ctrl(mgr, mgr.var_table.item(row_for('pwm'), 0))
    assert mgr.var_y_field.text() == 'time'

    mgr.close()
    fig.close()


def test_arming_y_then_x_updates_fields_and_new_figure_button_builds_a_figure():
    fig = shown_figure()
    src = _source()
    fig.subplot(2, 0).plot(src, x='time', y='temp')

    mgr = m.FigureManager()
    app.processEvents()

    def row_for(name):
        for r in range(mgr.var_table.rowCount()):
            if mgr.var_table.item(r, 0).text() == name:
                return r
        raise AssertionError(name)

    mgr._var_arm_select('y')
    mgr._on_var_table_clicked(mgr.var_table.item(row_for('temp'), 0))
    _click_with_ctrl(mgr, mgr.var_table.item(row_for('pwm'), 0))
    assert mgr.var_y_field.text() == 'temp, pwm'

    mgr._var_arm_select('x')
    mgr._on_var_table_clicked(mgr.var_table.item(row_for('time'), 0))
    assert mgr.var_x_field.text() == 'time'
    assert not mgr.var_x_reset_btn.isHidden()

    mgr._var_reset_x()
    assert mgr.var_x_field.text() == ''
    assert mgr.var_x_reset_btn.isHidden()

    n_owned_before = len(mgr._owned_figures)
    mgr._var_new_figure_clicked()
    app.processEvents()
    assert len(mgr._owned_figures) == n_owned_before + 1
    new_fig = mgr._owned_figures[-1]
    assert len(new_fig.plots) == 1
    assert sorted(c.name for c in new_fig._series_on(new_fig.plots[0])) == ['pwm', 'temp']

    new_fig.close()
    mgr.close()
    fig.close()


def test_picking_a_y_variable_from_a_different_source_clears_the_previous_selection():
    fig = shown_figure()
    src1 = _source()
    src2 = m.DataSource({'other': np.arange(4.0)})
    fig.subplot(2, 0).plot(src1, x='time', y='temp')
    fig.subplot(2, 1).plot(src2, x='other', y='other')

    mgr = m.FigureManager()
    app.processEvents()

    def row_for(name):
        for r in range(mgr.var_table.rowCount()):
            if mgr.var_table.item(r, 0).text() == name:
                return r
        raise AssertionError(name)

    mgr._var_arm_select('y')
    mgr._on_var_table_clicked(mgr.var_table.item(row_for('temp'), 0))
    assert mgr.var_y_field.text() == 'temp'
    mgr._on_var_table_clicked(mgr.var_table.item(row_for('other'), 0))
    # 'other' belongs to a different DataSource than 'temp' -- the previous
    # Y selection is dropped, not appended to.
    assert mgr.var_y_field.text() == 'other'

    mgr.close()
    fig.close()


def test_armed_field_is_highlighted_and_unarmed_field_is_not():
    fig = shown_figure()
    src = _source()
    fig.subplot(2, 0).plot(src, x='time', y='temp')

    mgr = m.FigureManager()
    app.processEvents()

    # 'y' is armed from the start -- the tab's whole point is picking Y
    # variables, so no click on <variables> should be needed first.
    assert mgr.var_y_field.styleSheet() == mgr.ARMED_FIELD_STYLE
    assert mgr.var_x_field.styleSheet() == ""

    mgr._var_arm_select('x')
    assert mgr.var_y_field.styleSheet() == ""
    assert mgr.var_x_field.styleSheet() == mgr.ARMED_FIELD_STYLE

    mgr.close()
    fig.close()


def test_x_variable_row_is_red_and_y_variable_rows_are_blue():
    fig = shown_figure()
    src = _source()
    fig.subplot(2, 0).plot(src, x='time', y='temp')

    mgr = m.FigureManager()
    app.processEvents()

    def row_for(name):
        for r in range(mgr.var_table.rowCount()):
            if mgr.var_table.item(r, 0).text() == name:
                return r
        raise AssertionError(name)

    mgr._var_arm_select('y')
    mgr._on_var_table_clicked(mgr.var_table.item(row_for('pwm'), 0))
    mgr._var_arm_select('x')
    mgr._on_var_table_clicked(mgr.var_table.item(row_for('time'), 0))

    pwm_row, time_row, temp_row = row_for('pwm'), row_for('time'), row_for('temp')
    assert mgr.var_table.item(pwm_row, 0).background().color() == mgr.SELECTED_BG
    assert mgr.var_table.item(time_row, 0).background().color() == mgr.X_SELECTED_BG
    assert mgr.var_table.item(temp_row, 0).background() == QtGui.QBrush()

    mgr.close()
    fig.close()


def test_layout_event_filter_accepts_and_handles_a_variable_drop():
    """LayoutMixin.eventFilter's own Drag/Drop branch, driven with a real
    QDropEvent carrying our mime format (no real QDrag -- see module
    docstring) -- a plain duck-typed object doesn't survive the eventFilter
    chain, since AnnotationOpsMixin.eventFilter's own fallthrough calls the
    real super().eventFilter(obj, event), which requires a genuine QEvent."""
    fig = shown_figure()
    src = _source()
    n_before = len(fig.plots)

    mime = QtCore.QMimeData()
    mime.setData(variable_browser.VARIABLE_MIME_TYPE, b'1')
    ev = QtGui.QDropEvent(QtCore.QPointF(-500, -500), QtCore.Qt.CopyAction, mime,
                         QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)

    variable_browser.set_drag_payload([(src, 'temp')])
    handled = fig.eventFilter(fig.layout_widget, ev)
    app.processEvents()

    assert handled is True
    assert len(fig.plots) == n_before + 1
    fig.close()
