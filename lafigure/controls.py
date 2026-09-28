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

"""WP-N: CLAUDE.md's Phase 5 -- "interactive controls + reactive tables".

**Public API** (the shape a later reader needs, since nothing else in the
plan references this module yet):

    from lafigure.controls import ControlPanel, open_control_panel

    panel = ControlPanel()                     # a plain QWidget: usable
                                                # anywhere a widget fits --
                                                # a QMainWindow's central
                                                # widget, a QDockWidget, or
                                                # (once layout.py grows a
                                                # hook -- see this module's
                                                # own docstring note below)
                                                # a grid cell.
    panel.button('Reset', on_click=lambda: src.filter(None))
    panel.slider('min speed', 0, 30, on_change=lambda v: src.filter(src['speed'] >= v))
    panel.dropdown('mode', ['raw', 'filtered'], on_change=lambda v: print(v))
    panel.checkbox('show outliers', checked=False, on_change=lambda v: ...)
    panel.table(lambda: {'x': src['x'][src.visible_rows],
                          'y': src['y'][src.visible_rows]},
                depends_on=[src])

    # Separate-window use (the roadmap's other required host):
    win = open_control_panel(figure=fig, title="Controls")  # shows a QMainWindow
    win.slider(...)   # ControlPanelWindow forwards button/slider/dropdown/
                       # checkbox/table to its own .panel

Design decisions, since later code needs to match this shape exactly:

- **One generic container, `ControlPanel`**, a plain `QWidget` with no
  assumption about what hosts it (roadmap: "a generic container class
  usable for both" the grid-cell and separate-window cases). It owns its
  own vertical layout of controls plus one always-present status label at
  the bottom (see "error reporting" below) -- nothing about it requires a
  `QMainWindow`, a scene, or a figure.
- **`ControlPanelWindow`** is a thin `QMainWindow` host: `setCentralWidget`
  is the only thing it does beyond forwarding the five builder methods and
  wiring its own real `statusBar()` as a *second* place errors are also
  shown (`ControlPanel` works fully without one -- see below).
- **`open_control_panel(figure=None, title=None)`** is the documented
  entry point for the separate-window case, since this package does not
  own `figure.py` and so cannot add a `fig.open_control_panel()` method
  itself -- see this module's docstring note near the bottom (and the
  work package's final report) for the exact one-line diff a coordinator
  could apply to `figure.py`/`__init__.py` to add that convenience later.
  `figure` is not made a Qt *parent* of the returned window (a `QMainWindow`
  with a non-null Qt parent stops being a top-level window on most
  platforms) -- it's kept only as `win.figure`, for a caller who wants to
  title the window or read the figure back later.
- **The grid-cell case is intentionally NOT wired into `layout.py`** (not
  an owned file for this package): `ControlPanel` is layout-agnostic by
  construction (see above) so a later pass can embed one with minimal
  glue. See the "Proposed layout.py hook" note near the bottom of this
  docstring for the exact shape that later pass should probably take.
- **Discrete controls** (`button`, `dropdown`, `checkbox`) invoke the
  user's callback **immediately**, synchronously, on the Qt signal that
  fires the discrete change (`clicked`/`currentIndexChanged`/`toggled`) --
  no debounce, per the roadmap ("A button/checkbox/dropdown ... call
  immediately, no debounce needed" is this package's own brief, mirroring
  the Phase 5 roadmap wording that only calls out continuous controls).
- **`slider` is debounced (~50ms)**: every `valueChanged` restarts a
  single-shot `QTimer`; only the value that's still current when the timer
  finally fires reaches the user's callback -- so a fast drag calls it
  once, with the last (settled) value, not once per intermediate tick.
  `debounce_ms` is a constructor-time keyword (default 50) in case a
  future caller wants a different pause.
- **Error reporting is a label `ControlPanel` always carries itself**,
  not something borrowed from a host's real status bar -- a future grid
  cell has no `QMainWindow.statusBar()` to borrow, so relying on one would
  make the panel work in a window but silently swallow errors (back to
  stderr) in a cell. Every user callback (button/slider/dropdown/checkbox
  *and* a table's `fn`) is invoked through `_invoke_safe`, which never lets
  an exception escape: on failure it writes `traceback.format_exc()` into
  `panel.status_text` (a plain, always-visible `QLabel`, styled to stand
  out) and, if the panel is hosted by a `ControlPanelWindow` (which wires
  `panel._host_statusbar = self.statusBar()`), *also* posts the exception's
  last line to that real Qt status bar, so a windowed user sees the
  familiar transient status-bar message while the label keeps the full
  traceback visible/inspectable for as long as needed.
- **`table(fn, depends_on=())`**: `fn()` must return a **dict mapping
  column name -> a sequence/array of values, all the same length** (the
  same shape `DataSource(...)` itself accepts -- chosen for consistency
  with the rest of this project's data model, see `datasource.py`'s own
  docstring). The table (a plain, read-only `QTableWidget`) is populated
  once immediately, then again every time any `DataSource` in
  `depends_on` fires `on_change` (i.e. after `filter`/`hide_rows`/
  `show_rows`/`show_all`/`add_column` -- see `datasource.py`). Each
  subscription is recorded and reversed automatically when the panel
  widget is destroyed (connected to Qt's own `destroyed` signal, which
  fires for a plain child widget too, not just a top-level window) --
  and also reversible on demand via `panel.dispose()`, which
  `ControlPanelWindow.closeEvent` calls explicitly for a deterministic,
  synchronous cleanup instead of relying on GC/`destroyed` timing.
- **Nothing in this module ever calls `_push_history`/`undo_group`.**
  Every control-driven state change (a slider's debounced callback, a
  table recompute, a filter set from inside a callback if the *user's*
  callback does that) is view state, per the roadmap ("Control-driven
  filter changes are view state (not undo entries)"). If a user's own
  callback chooses to push undo itself (e.g. it edits a `Series` via
  `Series.set_data`, which is undoable on its own terms), that's the
  user's business, not this framework's -- this module simply never does
  it on the framework's own behalf.

**Proposed `layout.py` hook for the grid-cell case (not implemented
here -- layout.py is not an owned file for this package)**: an
`axes_type='controls'` branch in `add_subplot` (mirroring the existing
`axes_type` dispatch already documented in CLAUDE.md's Roadmap/WP-01
section: "any `axes_type` other than `'cartesian'` raises
`NotImplementedError`") that, instead of building a `PlotItem`, builds a
`QGraphicsProxyWidget` wrapping a fresh `ControlPanel` and inserts *that*
into the grid cell the same way a subplot's outer box is positioned --
since `ControlPanel` is a plain `QWidget` with no pyqtgraph/scene
dependency, `QGraphicsProxyWidget(panel)` is enough to make it a citizen
of the same `QGraphicsScene` a subplot lives in, so move/resize/snap can
treat it like any other grid item. A `ControlPanel` never needs a
`PlotItem`/`ViewBox`, so this hook would not have to touch any of
`layout.py`'s subplot-specific bookkeeping (link-x, brushing, series) --
only the grid geometry/selection parts.
"""
import traceback

from pyqtgraph.Qt import QtCore, QtWidgets

DEFAULT_DEBOUNCE_MS = 50


class ControlPanel(QtWidgets.QWidget):
    """A generic, layout-agnostic container of interactive controls (see
    the module docstring for the full public API and design notes)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host_statusbar = None  # optionally set by a host (e.g. ControlPanelWindow)

        outer = QtWidgets.QVBoxLayout(self)
        self._controls_layout = QtWidgets.QVBoxLayout()
        outer.addLayout(self._controls_layout)
        outer.addStretch(1)

        self._status_label = QtWidgets.QLabel("")
        self._status_label.setObjectName("lafigure_control_panel_status")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #a00000; font-family: monospace;")
        outer.addWidget(self._status_label)

        # (source, callback) pairs to unsubscribe on dispose/destroy -- see
        # the module docstring's "table" bullet.
        self._subscriptions = []
        subs = self._subscriptions

        def _cleanup(*_args):
            for src, cb in subs:
                try:
                    src.off_change(cb)
                except ValueError:
                    pass  # already unsubscribed
            subs.clear()

        self._dispose_subscriptions = _cleanup
        self.destroyed.connect(_cleanup)

    # -- error reporting ---------------------------------------------------

    @property
    def status_text(self):
        """The full text currently shown in this panel's own status label
        (empty string if no callback has failed yet)."""
        return self._status_label.text()

    def _show_error(self, text):
        self._status_label.setText(text)
        if self._host_statusbar is not None:
            stripped = text.strip()
            last_line = stripped.splitlines()[-1] if stripped else text
            self._host_statusbar.showMessage(last_line, 8000)

    def _invoke_safe(self, callback, *args):
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:
            self._show_error(traceback.format_exc())

    # -- discrete controls ---------------------------------------------------

    def button(self, label, on_click=None):
        """A push button; `on_click()` fires immediately on each click."""
        btn = QtWidgets.QPushButton(label)
        btn.clicked.connect(lambda: self._invoke_safe(on_click))
        self._controls_layout.addWidget(btn)
        return btn

    def checkbox(self, label, checked=False, on_change=None):
        """A checkbox; `on_change(bool)` fires immediately on each toggle."""
        cb = QtWidgets.QCheckBox(label)
        cb.setChecked(checked)
        cb.toggled.connect(lambda v: self._invoke_safe(on_change, v))
        self._controls_layout.addWidget(cb)
        return cb

    def dropdown(self, label, options, value=None, on_change=None):
        """A labeled combo box. `options` is a list of either plain values
        (their `str()` is shown) or `(label_text, value)` pairs. `on_change
        (value)` fires immediately with the *value*, not the display text,
        on each selection change."""
        row = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(QtWidgets.QLabel(label))
        combo = QtWidgets.QComboBox()
        values = []
        for opt in options:
            if isinstance(opt, tuple):
                text, val = opt
            else:
                text, val = str(opt), opt
            values.append(val)
            combo.addItem(text, val)
        hl.addWidget(combo, 1)
        if value is not None and value in values:
            combo.setCurrentIndex(values.index(value))
        combo.currentIndexChanged.connect(lambda i: self._invoke_safe(on_change, combo.itemData(i)))
        self._controls_layout.addWidget(row)
        return combo

    # -- continuous control (debounced) ---------------------------------------

    def slider(self, label, minimum, maximum, value=None, step=1, on_change=None,
               debounce_ms=DEFAULT_DEBOUNCE_MS):
        """A labeled horizontal slider. `on_change(value)` is **debounced**:
        it fires `debounce_ms` (default 50) after the last `valueChanged`,
        with whatever value is current at that point -- a fast drag calls
        it once, with the settled value, never once per intermediate tick."""
        row = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(QtWidgets.QLabel(label))
        sld = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        sld.setMinimum(minimum)
        sld.setMaximum(maximum)
        sld.setSingleStep(step)
        sld.setValue(minimum if value is None else value)
        hl.addWidget(sld, 1)
        value_label = QtWidgets.QLabel(str(sld.value()))
        hl.addWidget(value_label)

        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(debounce_ms)
        timer.timeout.connect(lambda: self._invoke_safe(on_change, sld.value()))

        def _on_value_changed(v):
            value_label.setText(str(v))
            if on_change is not None:
                timer.start()  # restart the debounce window on every tick

        sld.valueChanged.connect(_on_value_changed)
        self._controls_layout.addWidget(row)
        return sld

    # -- reactive table --------------------------------------------------------

    def table(self, fn, depends_on=()):
        """A read-only table kept in sync with `fn()`.

        `fn()` must return a dict mapping column name -> a sequence/array
        of values (all the same length) -- see the module docstring for
        why this shape was chosen. Recomputed once immediately, then again
        every time any `DataSource` in `depends_on` notifies via its own
        `on_change` (filter/hide_rows/show_rows/show_all/add_column)."""
        widget = QtWidgets.QTableWidget()
        widget.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        def refresh():
            try:
                data = fn()
            except Exception:
                self._show_error(traceback.format_exc())
                return
            self._populate_table(widget, data)

        for source in depends_on:
            source.on_change(refresh)
            self._subscriptions.append((source, refresh))

        refresh()
        self._controls_layout.addWidget(widget)
        return widget

    @staticmethod
    def _populate_table(widget, data):
        columns = list(data.keys())
        n_rows = len(next(iter(data.values()))) if columns else 0
        widget.setColumnCount(len(columns))
        widget.setHorizontalHeaderLabels(columns)
        widget.setRowCount(n_rows)
        for col_idx, name in enumerate(columns):
            column = data[name]
            for row_idx in range(n_rows):
                widget.setItem(row_idx, col_idx, QtWidgets.QTableWidgetItem(str(column[row_idx])))

    # -- cleanup ---------------------------------------------------------------

    def dispose(self):
        """Unsubscribe every table's DataSource.on_change eagerly, rather
        than waiting for this widget's own `destroyed` signal (which still
        does the same thing, as a safety net) -- for deterministic cleanup
        when a host (e.g. ControlPanelWindow.closeEvent) knows the panel is
        going away right now."""
        self._dispose_subscriptions()


class ControlPanelWindow(QtWidgets.QMainWindow):
    """A separate top-level window hosting one `ControlPanel` as its
    central widget, per the roadmap's "in a separate figure window" host.
    Forwards the five builder methods to `self.panel` for convenience, and
    wires its own real `statusBar()` as a second place a failing
    callback's message is shown (`self.panel` already works fully without
    this -- see the module docstring)."""

    def __init__(self, parent=None, title="Controls"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.figure = None  # set by open_control_panel(figure=...), if any
        self.panel = ControlPanel()
        self.panel._host_statusbar = self.statusBar()
        self.setCentralWidget(self.panel)
        self.resize(360, 420)

    def button(self, *args, **kwargs):
        return self.panel.button(*args, **kwargs)

    def slider(self, *args, **kwargs):
        return self.panel.slider(*args, **kwargs)

    def dropdown(self, *args, **kwargs):
        return self.panel.dropdown(*args, **kwargs)

    def checkbox(self, *args, **kwargs):
        return self.panel.checkbox(*args, **kwargs)

    def table(self, *args, **kwargs):
        return self.panel.table(*args, **kwargs)

    def closeEvent(self, ev):
        self.panel.dispose()
        super().closeEvent(ev)


def open_control_panel(figure=None, title=None):
    """The documented entry point for the separate-window case (see the
    module docstring for why this is a plain function rather than a
    `fig.open_control_panel()` method: this package doesn't own
    `figure.py`). Builds, shows and returns a `ControlPanelWindow`;
    `figure`, if given, is kept as `win.figure` (NOT set as the window's
    Qt parent -- see the module docstring) and used to build a default
    title when `title` isn't given explicitly."""
    if title is None:
        title = "Controls" if figure is None else f"Controls -- {figure.windowTitle()}"
    win = ControlPanelWindow(title=title)
    win.figure = figure
    win.show()
    return win
