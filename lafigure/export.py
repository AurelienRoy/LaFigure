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

"""Save / export (CLAUDE.md roadmap Phase 4, non-HTML part): a Save dialog
with a Word-style print preview and a format-pluggable exporter registry.

`SaveMixin.show_save_dialog` is the only thing another mixin is meant to
call (wired to a toolbar "Save" button + Ctrl+S -- see PLAN.md, which keeps
`toolbar.py` coordinator-owned; this module does not touch it). Nothing on
disk changes just from constructing/showing the dialog -- only pressing
"Export" writes files, and only the QSettings-remembered header template is
written as the user edits it (a UI preference, not a data/document write).

**The exporter registry -- read this before adding a format (WP-M/HTML):**

    EXPORTERS: dict[str, callable | None]
        format name (lowercase, e.g. 'png') -> a function
        `(pixmap, path, header_text, header_pos) -> None` that paints
        `pixmap` (a QPixmap: the whole figure, already grabbed with the
        selection chrome hidden) into `path`, baking `header_text` at the
        fractional position `header_pos = (x_frac, y_frac)` (0..1 of the
        pixmap's width/height -- proportional, so it holds up across the
        different export sizes/formats). A `None` value means the format's
        *name* is a known, planned entry but not currently wired up (either
        an optional dependency is missing in this environment -- see
        `UNAVAILABLE_REASONS[format]` for why -- or, for 'html', that it is
        someone else's package's job: WP-M plugs a plotly-based HTML
        exporter in here).

    `register_exporter(name, fn)` just does `EXPORTERS[name] = fn`; it
    exists so a caller doesn't need this module's other internals.

    HTML's *input* is a plotly figure, not a QPixmap -- forcing it through
    the same `(pixmap, path, header_text, header_pos)` signature would be
    fake genericity. The decision of *which* function to call for a given
    format IS table-driven (`SaveDialog._do_export` just does
    `EXPORTERS[fmt](...)` in a loop over the checked formats) -- but WP-M is
    free to special-case 'html' with its own call signature right there
    (one `if fmt == 'html': ...` branch) rather than contort this one.
    `EXPORTERS['html']` is pre-seeded to `None` (checkbox present, disabled,
    with an explanatory tooltip) precisely so that one line -- assigning a
    real callable, and adjusting that one `_do_export` branch -- is the
    entire integration; nothing else in this module or the dialog needs to
    change.
"""
import os
from datetime import datetime

from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

# -- exporter registry -----------------------------------------------------

EXPORTERS = {}          # format name -> callable(pixmap, path, header_text, header_pos) or None
UNAVAILABLE_REASONS = {}  # format name -> str, only set when EXPORTERS[name] is None because
                          # an optional Qt module failed to import here


def register_exporter(name, fn):
    """Register (or replace) the exporter for `name` (e.g. 'html', by
    WP-M). See this module's docstring for the function shape."""
    EXPORTERS[name] = fn


def _paint_header_on_painter(painter, header_text, header_pos, width, height):
    """Draw `header_text` with `painter`, at the fractional (0..1) position
    `header_pos` of a `width` x `height` canvas -- shared by every format's
    exporter below so the header lands in the same relative spot regardless
    of the output's pixel size."""
    if not header_text:
        return
    painter.save()
    font = painter.font()
    font.setPointSizeF(max(8.0, height * 0.022))
    painter.setFont(font)
    metrics = QtGui.QFontMetricsF(font)
    x = header_pos[0] * width
    y = header_pos[1] * height + metrics.ascent()
    painter.setPen(QtGui.QColor(20, 20, 20))
    painter.drawText(QtCore.QPointF(x, y), header_text)
    painter.restore()


def _export_raster(fmt):
    """PNG/JPG share everything except the format string QPixmap.save wants."""
    def _export(pixmap, path, header_text, header_pos):
        baked = QtGui.QPixmap(pixmap)
        painter = QtGui.QPainter(baked)
        try:
            _paint_header_on_painter(painter, header_text, header_pos,
                                      baked.width(), baked.height())
        finally:
            painter.end()
        if not baked.save(path, fmt):
            raise IOError(f"Failed to write {fmt} file: {path}")
    return _export


register_exporter('png', _export_raster('PNG'))
register_exporter('jpg', _export_raster('JPG'))

try:
    from pyqtgraph.Qt import QtSvg

    def _export_svg(pixmap, path, header_text, header_pos):
        generator = QtSvg.QSvgGenerator()
        generator.setFileName(path)
        generator.setSize(pixmap.size())
        generator.setViewBox(QtCore.QRect(0, 0, pixmap.width(), pixmap.height()))
        generator.setTitle("LaFigure export")
        painter = QtGui.QPainter(generator)
        try:
            painter.drawPixmap(0, 0, pixmap)
            _paint_header_on_painter(painter, header_text, header_pos,
                                      pixmap.width(), pixmap.height())
        finally:
            painter.end()

    register_exporter('svg', _export_svg)
except ImportError as e:
    UNAVAILABLE_REASONS['svg'] = str(e)
    register_exporter('svg', None)

try:
    # QPdfWriter lives in QtGui in both PyQt5 and PySide -- no separate
    # QtPrintSupport import needed (verified importable in this env: PyQt5).
    QtGui.QPdfWriter

    def _export_pdf(pixmap, path, header_text, header_pos):
        writer = QtGui.QPdfWriter(path)
        # A pixel grid at a fixed, explicit DPI keeps the painter's
        # coordinate space equal to the pixmap's own pixel size, so the
        # same header_pos fraction/font-size math as the other formats
        # lands in the same relative spot.
        dpi = 96
        writer.setResolution(dpi)
        mm_per_px = 25.4 / dpi
        writer.setPageSizeMM(QtCore.QSizeF(pixmap.width() * mm_per_px,
                                            pixmap.height() * mm_per_px))
        painter = QtGui.QPainter(writer)
        try:
            painter.drawPixmap(0, 0, pixmap)
            _paint_header_on_painter(painter, header_text, header_pos,
                                      pixmap.width(), pixmap.height())
        finally:
            painter.end()

    register_exporter('pdf', _export_pdf)
except (ImportError, AttributeError) as e:
    UNAVAILABLE_REASONS['pdf'] = str(e)
    register_exporter('pdf', None)

# Placeholder: present so the dialog can show an (disabled) HTML checkbox
# and so WP-M's integration is "assign a callable here", not "add a new key
# and rewire the dialog" -- see this module's docstring.
register_exporter('html', None)


# -- header template -------------------------------------------------------

DEFAULT_HEADER_TEMPLATE = "Source: {source} | {date:%Y-%m-%d %H:%M} | {user}"


def default_info(figure):
    """`figure.info` (created lazily -- see SaveMixin.show_save_dialog, this
    module doesn't own figure.py's __init__) layered over the built-in
    date/user defaults; keys in figure.info win so a user-set 'date' or
    'user' isn't silently clobbered."""
    info = {
        'date': datetime.now(),
        'user': os.environ.get('USERNAME') or os.environ.get('USER', ''),
    }
    info.update(getattr(figure, 'info', {}) or {})
    info.setdefault('source', figure.windowTitle() if hasattr(figure, 'windowTitle') else '')
    return info


def render_header(template, info):
    """Plain str.format() -- e.g. "{date:%Y-%m-%d %H:%M}" uses datetime's
    own __format__, so a format spec after the colon works for free."""
    try:
        return template.format(**info)
    except Exception as e:
        return f"<header template error: {e}>"


def _default_base_name(figure):
    title = figure.windowTitle() if hasattr(figure, 'windowTitle') else ''
    safe = ''.join(c if (c.isalnum() or c in '-_') else '_' for c in title).strip('_')
    return safe or 'figure'


# -- hide/restore selection chrome for the pixmap grab ----------------------

def _hide_selection_chrome(figure):
    """Temporarily clear every subplot's red border, the resize/move
    handles, curve-selection highlight pens and annotation dashed outlines,
    so none of them show up in the exported pixmap -- without touching
    `selected_plots`/`selected_curves`/`selected_annotations` themselves,
    so `_restore_selection_chrome` can put the exact same visuals back.
    Uses only existing, public-ish figure/annotation methods (selection_ui.py,
    layout.py, annotations.py), read-only -- see CLAUDE.md/PLAN.md's note on
    not editing those files."""
    for p in getattr(figure, 'plots', []):
        p.getViewBox().setBorder(None)
    if hasattr(figure, '_hide_handles'):
        figure._hide_handles()
    for c in list(getattr(figure, 'selected_curves', [])):
        figure._unhighlight_curve_pen(c)
    for a in list(getattr(figure, 'selected_annotations', [])):
        a.set_selected(False)


def _restore_selection_chrome(figure):
    if hasattr(figure, '_mark_active'):
        figure._mark_active(figure.focused_plot, keep_selection=True)
    for c in list(getattr(figure, 'selected_curves', [])):
        figure._highlight_curve_pen(c)
    for a in list(getattr(figure, 'selected_annotations', [])):
        a.set_selected(True)


def _grab_figure_pixmap(figure):
    widget = getattr(figure, 'layout_widget', None) or figure.centralWidget()
    _hide_selection_chrome(figure)
    try:
        return widget.grab()
    finally:
        _restore_selection_chrome(figure)


# -- the dialog --------------------------------------------------------------

SETTINGS_KEY_TEMPLATE = 'export/header_template'
SETTINGS_KEY_DIRECTORY = 'export/directory'


class SaveDialog(QtWidgets.QDialog):
    """Word-style print-preview Save dialog: filename + folder, one
    checkbox per format, a header-template field, and a QGraphicsView
    preview (the grabbed figure as a background pixmap + a draggable
    QGraphicsTextItem showing the rendered header). Nothing is written to
    disk until "Export" is clicked.

    `settings` defaults to the real, process-wide QSettings("LaFigure",
    "LaFigure") but can be overridden (a test passes an INI-backed one so
    tests don't touch the real user registry/config file)."""

    def __init__(self, figure, parent=None, settings=None):
        super().__init__(parent if parent is not None else figure)
        self.figure = figure
        self.setWindowTitle("Save Figure")
        self.resize(760, 660)
        self._settings = settings if settings is not None else QtCore.QSettings("LaFigure", "LaFigure")

        # Grabbed once, with selection chrome hidden for the grab only --
        # both the preview and the eventual export reuse this same pixmap,
        # so what the user previews is exactly what gets written.
        self._pixmap = _grab_figure_pixmap(figure)
        self._info = default_info(figure)

        name_row = QtWidgets.QHBoxLayout()
        self.name_edit = QtWidgets.QLineEdit(_default_base_name(figure))
        self.dir_edit = QtWidgets.QLineEdit(
            self._settings.value(SETTINGS_KEY_DIRECTORY, os.getcwd()))
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        name_row.addWidget(QtWidgets.QLabel("File name:"))
        name_row.addWidget(self.name_edit)
        name_row.addWidget(QtWidgets.QLabel("Folder:"))
        name_row.addWidget(self.dir_edit, 1)
        name_row.addWidget(browse_btn)

        fmt_row = QtWidgets.QHBoxLayout()
        fmt_row.addWidget(QtWidgets.QLabel("Formats:"))
        self._format_checks = {}
        for fmt in ('png', 'jpg', 'svg', 'pdf', 'html'):
            cb = QtWidgets.QCheckBox(fmt.upper())
            if fmt == 'html':
                cb.setEnabled(False)
                cb.setToolTip("Requires the plotly export package (coming soon)")
            elif EXPORTERS.get(fmt) is None:
                cb.setEnabled(False)
                cb.setToolTip("Unavailable in this environment"
                               + (f": {UNAVAILABLE_REASONS[fmt]}" if fmt in UNAVAILABLE_REASONS else ""))
            self._format_checks[fmt] = cb
            fmt_row.addWidget(cb)
        fmt_row.addStretch(1)
        self._format_checks['png'].setChecked(True)

        header_row = QtWidgets.QHBoxLayout()
        header_row.addWidget(QtWidgets.QLabel("Header:"))
        last_template = self._settings.value(SETTINGS_KEY_TEMPLATE, DEFAULT_HEADER_TEMPLATE)
        self.template_edit = QtWidgets.QLineEdit(last_template)
        header_row.addWidget(self.template_edit, 1)

        self.scene = QtWidgets.QGraphicsScene(self)
        self.pixmap_item = QtWidgets.QGraphicsPixmapItem(self._pixmap)
        self.scene.addItem(self.pixmap_item)
        self.text_item = QtWidgets.QGraphicsTextItem()
        self.text_item.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.text_item.setDefaultTextColor(QtGui.QColor(20, 20, 20))
        self.text_item.setPos(self._pixmap.width() * 0.03, self._pixmap.height() * 0.03)
        self.scene.addItem(self.text_item)
        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setRenderHint(QtGui.QPainter.Antialiasing)
        self._update_header_text()
        self.template_edit.textChanged.connect(self._update_header_text)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        export_btn = QtWidgets.QPushButton("Export")
        export_btn.setDefault(True)
        export_btn.clicked.connect(self._do_export)
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(export_btn)
        btn_row.addWidget(cancel_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(name_row)
        layout.addLayout(fmt_row)
        layout.addLayout(header_row)
        layout.addWidget(self.view, 1)
        layout.addLayout(btn_row)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.view.fitInView(self.scene.itemsBoundingRect(), QtCore.Qt.KeepAspectRatio)

    def _browse(self):
        chosen = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose folder", self.dir_edit.text())
        if chosen:
            self.dir_edit.setText(chosen)

    def _update_header_text(self):
        template = self.template_edit.text()
        self.text_item.setPlainText(render_header(template, self._info))
        # Remembered live, not just on Export, so a template survives even
        # if the dialog is closed with Cancel/the window's close button.
        self._settings.setValue(SETTINGS_KEY_TEMPLATE, template)

    def _header_fraction(self):
        pos = self.text_item.pos()
        w = self._pixmap.width() or 1
        h = self._pixmap.height() or 1
        return (pos.x() / w, pos.y() / h)

    def _do_export(self):
        base = self.name_edit.text().strip()
        directory = self.dir_edit.text().strip()
        if not base or not directory:
            QtWidgets.QMessageBox.warning(self, "Save Figure", "Choose a file name and folder.")
            return
        chosen = [fmt for fmt, cb in self._format_checks.items() if cb.isChecked() and cb.isEnabled()]
        if not chosen:
            QtWidgets.QMessageBox.warning(self, "Save Figure", "Choose at least one format.")
            return
        header_text = self.text_item.toPlainText()
        header_pos = self._header_fraction()

        errors = []
        for fmt in chosen:
            fn = EXPORTERS.get(fmt)
            if fn is None:
                continue
            path = os.path.join(directory, f"{base}.{fmt}")
            try:
                fn(self._pixmap, path, header_text, header_pos)
            except Exception as e:
                errors.append(f"{fmt}: {e}")

        self._settings.setValue(SETTINGS_KEY_TEMPLATE, self.template_edit.text())
        self._settings.setValue(SETTINGS_KEY_DIRECTORY, directory)

        if errors:
            QtWidgets.QMessageBox.warning(self, "Save Figure", "Some formats failed:\n" + "\n".join(errors))
        else:
            self.accept()


class SaveMixin:
    """Adds the Save dialog to LaFigure. The only method another mixin/
    toolbar.py should call is show_save_dialog(); everything else in this
    module is either the dialog class itself or the standalone exporter
    registry (usable without any LaFigure instance at all -- see PLAN.md's
    note that WP-M needs the registry decoupled from the dialog's widgets).
    """

    def show_save_dialog(self):
        # figure.py doesn't (and, per file ownership, shouldn't yet) create
        # self.info in __init__ -- lazily create it here on first use.
        if not hasattr(self, 'info'):
            self.info = {}
        dlg = SaveDialog(self)
        dlg.exec_()
        return dlg
