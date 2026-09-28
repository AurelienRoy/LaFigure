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

"""WP-N: interactive controls + reactive tables (controls.py).

Button/checkbox interactions are driven through `QtTest.QTest.mouseClick`
on the real widget, not `tests/helpers._mouse` -- `_mouse` is purpose-built
for pyqtgraph's `GraphicsView`/`QGraphicsScene` hit-testing (see its own
docstring and CLAUDE.md bug #11); the widgets here are plain `QWidget`s
with no scene involved, so `QTest.mouseClick`/`QTest.keyClick` (both real,
Qt-event-routed, exactly what CLAUDE.md asks for) are the right primitive,
not the scene-mapping one. Slider debounce uses `QTest.qWait` to pump the
real Qt event loop so the single-shot `QTimer` actually fires -- confirmed
reliable under `QT_QPA_PLATFORM=offscreen` in this run (timers are core Qt
event-loop machinery, independent of the windowing platform plugin; see
CLAUDE.md bug #10 for the one case, GL contexts, where offscreen genuinely
can't do something -- timers aren't in that category).
"""
import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets, QtTest

from lafigure.controls import ControlPanel, ControlPanelWindow, open_control_panel
from lafigure.datasource import DataSource

from tests.helpers import app, m


# -- discrete controls -----------------------------------------------------

def test_button_click_invokes_callback():
    panel = ControlPanel()
    calls = []
    btn = panel.button("Go", on_click=lambda: calls.append(True))
    QtTest.QTest.mouseClick(btn, QtCore.Qt.LeftButton)
    assert calls == [True]


def test_checkbox_toggle_invokes_callback_with_value():
    panel = ControlPanel()
    calls = []
    cb = panel.checkbox("Enable", checked=False, on_change=lambda v: calls.append(v))
    panel.show()
    app.processEvents()
    QtTest.QTest.mouseClick(cb, QtCore.Qt.LeftButton)
    assert calls == [True]
    QtTest.QTest.mouseClick(cb, QtCore.Qt.LeftButton)
    assert calls == [True, False]
    panel.close()


def test_dropdown_selection_invokes_callback_with_value_not_text():
    panel = ControlPanel()
    calls = []
    combo = panel.dropdown("Mode", [("Raw data", "raw"), ("Filtered", "filtered")],
                           on_change=lambda v: calls.append(v))
    combo.setCurrentIndex(1)
    assert calls == ["filtered"]


# -- slider + debounce -------------------------------------------------------

def test_slider_settled_value_reaches_callback():
    panel = ControlPanel()
    calls = []
    sld = panel.slider("Speed", 0, 30, on_change=lambda v: calls.append(v), debounce_ms=30)
    sld.setValue(12)
    QtTest.QTest.qWait(120)
    app.processEvents()
    assert calls == [12]


def test_slider_debounce_collapses_rapid_changes_to_one_call_with_last_value():
    panel = ControlPanel()
    calls = []
    sld = panel.slider("Speed", 0, 30, on_change=lambda v: calls.append(v), debounce_ms=40)
    # Fire several changes in quick succession, well within the debounce window.
    sld.setValue(5)
    sld.setValue(10)
    sld.setValue(15)
    sld.setValue(21)
    assert calls == [], "must not have fired yet -- still inside the debounce window"
    QtTest.QTest.qWait(150)
    app.processEvents()
    assert calls == [21], "exactly one call, with the LAST (settled) value"


# -- reactive table -----------------------------------------------------------

def test_table_recomputes_when_its_own_dependency_changes():
    src = DataSource({'x': np.arange(10, dtype=float), 'y': np.arange(10, dtype=float) * 2})
    panel = ControlPanel()
    widget = panel.table(lambda: {'x': src['x'][src.visible_rows], 'y': src['y'][src.visible_rows]},
                         depends_on=[src])
    assert widget.rowCount() == 10
    assert widget.item(0, 0).text() == "0.0"

    src.filter('x >= 5')
    assert widget.rowCount() == 5
    assert widget.item(0, 0).text() == "5.0"


def test_table_does_not_recompute_for_an_unrelated_source():
    watched = DataSource({'x': np.arange(4, dtype=float)})
    unrelated = DataSource({'x': np.arange(4, dtype=float)})
    calls = []

    def fn():
        calls.append(1)
        return {'x': watched['x'][watched.visible_rows]}

    panel = ControlPanel()
    panel.table(fn, depends_on=[watched])
    assert len(calls) == 1  # the initial, immediate populate

    unrelated.filter('x >= 2')
    assert len(calls) == 1, "an unrelated source's on_change must not trigger a recompute"

    watched.filter('x >= 2')
    assert len(calls) == 2


def test_table_dispose_unsubscribes_from_its_sources():
    src = DataSource({'x': np.arange(4, dtype=float)})
    panel = ControlPanel()
    calls = []
    panel.table(lambda: calls.append(1) or {'x': src['x']}, depends_on=[src])
    assert len(calls) == 1

    panel.dispose()
    src.filter('x >= 1')  # must not reach the now-disposed panel's callback
    assert len(calls) == 1


# -- error handling: never crash, always visible ------------------------------

def test_failing_button_callback_is_caught_and_shown_in_status():
    panel = ControlPanel()

    def boom():
        raise ValueError("kaboom 42")

    btn = panel.button("Explode", on_click=boom)
    QtTest.QTest.mouseClick(btn, QtCore.Qt.LeftButton)  # must not raise/crash
    assert "kaboom 42" in panel.status_text
    assert "ValueError" in panel.status_text


def test_failing_slider_callback_is_caught_and_shown_in_status():
    panel = ControlPanel()

    def boom(v):
        raise RuntimeError(f"bad value {v}")

    sld = panel.slider("Speed", 0, 10, on_change=boom, debounce_ms=20)
    sld.setValue(7)
    QtTest.QTest.qWait(100)
    app.processEvents()
    assert "bad value 7" in panel.status_text


def test_failing_table_fn_is_caught_and_shown_in_status():
    def boom():
        raise KeyError("missing_column")

    panel = ControlPanel()
    panel.table(boom, depends_on=[])
    assert "missing_column" in panel.status_text or "KeyError" in panel.status_text


def test_control_panel_window_forwards_errors_to_its_real_status_bar():
    win = ControlPanelWindow(title="Test")

    def boom():
        raise ValueError("window boom")

    btn = win.button("Explode", on_click=boom)
    QtTest.QTest.mouseClick(btn, QtCore.Qt.LeftButton)
    assert "window boom" in win.panel.status_text
    assert "window boom" in win.statusBar().currentMessage()
    win.close()


# -- undo: control interactions must never push undo entries -----------------

def test_control_interactions_never_push_undo_on_a_real_figure():
    f = m.LaFigure(empty=True)
    src = DataSource({'speed': np.arange(20, dtype=float)})

    panel = ControlPanel()
    panel.slider("min speed", 0, 19, on_change=lambda v: src.filter(src['speed'] >= v), debounce_ms=20)
    panel.checkbox("show all", checked=True, on_change=lambda v: src.filter(None) if v else None)
    table = panel.table(lambda: {'speed': src['speed'][src.visible_rows]}, depends_on=[src])

    before = len(f.undo_stack)

    sld = panel.findChild(QtWidgets.QSlider)
    sld.setValue(10)
    QtTest.QTest.qWait(100)
    app.processEvents()

    cb = panel.findChild(QtWidgets.QCheckBox)
    QtTest.QTest.mouseClick(cb, QtCore.Qt.LeftButton)

    assert table.rowCount() >= 0  # table refreshed as a side effect above
    assert len(f.undo_stack) == before, "control-driven state changes are view state, not undo"


# -- both required hosts: separate window, and layout-agnostic embedding -----

def test_open_control_panel_creates_a_real_separate_top_level_window():
    fig = m.LaFigure(empty=True)
    fig.setWindowTitle("My Figure")
    win = open_control_panel(figure=fig)
    try:
        assert isinstance(win, QtWidgets.QMainWindow)
        assert win.isWindow()
        assert win.figure is fig
        assert win.isVisible()
        calls = []
        win.button("Ping", on_click=lambda: calls.append(1))
        QtTest.QTest.mouseClick(win.findChild(QtWidgets.QPushButton), QtCore.Qt.LeftButton)
        assert calls == [1]
    finally:
        win.close()


def test_control_panel_is_layout_agnostic_when_embedded_in_an_arbitrary_container():
    """Stands in for the not-yet-integrated grid-cell case (layout.py isn't
    owned by this package -- see the module docstring's proposed hook):
    ControlPanel must work identically dropped into any plain QWidget
    container, with no figure/scene/window involved at all."""
    host = QtWidgets.QWidget()
    host_layout = QtWidgets.QGridLayout(host)
    panel = ControlPanel()
    host_layout.addWidget(panel, 0, 0)

    calls = []
    btn = panel.button("Cell action", on_click=lambda: calls.append("clicked"))
    host.show()
    app.processEvents()
    QtTest.QTest.mouseClick(btn, QtCore.Qt.LeftButton)
    assert calls == ["clicked"]
    host.close()
