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

"""Save dialog + exporter registry (export.py, WP-E). SaveMixin is mixed
into the real LaFigure in figure.py (applied by the coordinator alongside
WP-C's HelpMixin, since both landed as diffs against figure.py before
WP-H); tests here just use LaFigure directly.
"""
import os
import tempfile
from datetime import datetime

from pyqtgraph.Qt import QtCore, QtGui

from tests.helpers import app, m, has_border
from lafigure import export


def _demo_save_figure():
    f = m.LaFigure()
    f.show()
    app.processEvents()
    return f


def _ini_settings(directory):
    """A QSettings backed by a private file in `directory`, so tests never
    touch the real per-user LaFigure/LaFigure settings."""
    return QtCore.QSettings(os.path.join(directory, 'settings.ini'), QtCore.QSettings.IniFormat)


def test_show_save_dialog_opens_without_error():
    """The real entry point (SaveMixin.show_save_dialog) constructs and
    shows the dialog without raising -- exec_() is stubbed so the modal
    loop doesn't block this headless test."""
    f = _demo_save_figure()
    original_exec = export.SaveDialog.exec_
    export.SaveDialog.exec_ = lambda self: None
    try:
        dlg = f.show_save_dialog()
    finally:
        export.SaveDialog.exec_ = original_exec
    assert isinstance(dlg, export.SaveDialog)
    assert dlg._pixmap.width() > 0
    assert dlg._pixmap.height() > 0
    f.close()


def test_header_template_renders_date_and_multiple_keys():
    info = {'source': 'demo.csv', 'user': 'aurroy', 'date': datetime(2026, 9, 28, 14, 30)}
    template = "Source: {source} | {date:%Y-%m-%d %H:%M} | {user}"
    assert export.render_header(template, info) == "Source: demo.csv | 2026-09-28 14:30 | aurroy"


def test_default_info_lets_figure_info_override_defaults():
    f = _demo_save_figure()
    f.info = {'source': 'custom.csv'}
    info = export.default_info(f)
    assert info['source'] == 'custom.csv'
    assert 'date' in info and 'user' in info
    f.close()


def test_default_info_lazy_creates_info_via_show_save_dialog():
    f = _demo_save_figure()
    assert not hasattr(f, 'info')
    original_exec = export.SaveDialog.exec_
    export.SaveDialog.exec_ = lambda self: None
    try:
        f.show_save_dialog()
    finally:
        export.SaveDialog.exec_ = original_exec
    assert f.info == {}
    f.close()


def test_exporter_registry_shape():
    """png/jpg always work (QPixmap.save); svg/pdf are present, either a
    real callable or None (see UNAVAILABLE_REASONS) depending on what's
    importable in this environment; html is a real callable since WP-M
    filled the placeholder in with `register_exporter('html', fn)`
    (lafigure/html_export.py)."""
    assert set(export.EXPORTERS) == {'png', 'jpg', 'svg', 'pdf', 'html'}
    assert callable(export.EXPORTERS['png'])
    assert callable(export.EXPORTERS['jpg'])
    assert callable(export.EXPORTERS['html'])
    for fmt in ('svg', 'pdf'):
        assert export.EXPORTERS[fmt] is None or callable(export.EXPORTERS[fmt])


def test_html_checkbox_enabled_now_that_plotly_export_exists():
    with tempfile.TemporaryDirectory() as tmp:
        f = _demo_save_figure()
        dlg = export.SaveDialog(f, settings=_ini_settings(tmp))
        cb = dlg._format_checks['html']
        assert cb.isEnabled()
        f.close()


def test_opening_dialog_writes_no_figure_files():
    """Constructing the dialog, and editing the header template live,
    writes nothing to the export folder -- only Export does."""
    with tempfile.TemporaryDirectory() as tmp:
        f = _demo_save_figure()
        dlg = export.SaveDialog(f, settings=_ini_settings(tmp))
        dlg.dir_edit.setText(tmp)
        dlg.name_edit.setText("nothing_yet")
        dlg.template_edit.setText("Edited template -- still no figure file")
        app.processEvents()
        written = [n for n in os.listdir(tmp) if not n.endswith('.ini')]
        assert written == []
        f.close()


def test_export_png_and_svg_creates_valid_files():
    with tempfile.TemporaryDirectory() as tmp:
        f = _demo_save_figure()
        dlg = export.SaveDialog(f, settings=_ini_settings(tmp))
        dlg.name_edit.setText("myfig")
        dlg.dir_edit.setText(tmp)
        dlg._format_checks['png'].setChecked(True)
        dlg._format_checks['svg'].setChecked(True)
        dlg._format_checks['jpg'].setChecked(False)
        dlg.template_edit.setText("Source: {source} | {user}")

        dlg._do_export()

        png_path = os.path.join(tmp, "myfig.png")
        svg_path = os.path.join(tmp, "myfig.svg")
        assert os.path.isfile(png_path) and os.path.getsize(png_path) > 0
        assert os.path.isfile(svg_path) and os.path.getsize(svg_path) > 0

        img = QtGui.QImage(png_path)
        assert not img.isNull()
        assert img.width() == dlg._pixmap.width()
        assert img.height() == dlg._pixmap.height()
        f.close()


def test_export_underlying_function_directly():
    """The registry function is usable standalone, without any dialog --
    the shape WP-M's HTML branch and any non-GUI caller relies on."""
    with tempfile.TemporaryDirectory() as tmp:
        pixmap = QtGui.QPixmap(100, 60)
        pixmap.fill(QtGui.QColor('white'))
        path = os.path.join(tmp, "direct.png")
        export.EXPORTERS['png'](pixmap, path, "hello", (0.1, 0.1))
        assert os.path.isfile(path) and os.path.getsize(path) > 0


def test_qsettings_template_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        f = _demo_save_figure()
        settings1 = _ini_settings(tmp)
        dlg1 = export.SaveDialog(f, settings=settings1)
        custom_template = "Round-trip {user} template"
        dlg1.template_edit.setText(custom_template)
        settings1.sync()
        dlg1.close()

        settings2 = _ini_settings(tmp)  # fresh instance, same backing file
        dlg2 = export.SaveDialog(f, settings=settings2)
        assert dlg2.template_edit.text() == custom_template
        f.close()


def test_dialog_hides_and_restores_selection_chrome_around_the_grab():
    with tempfile.TemporaryDirectory() as tmp:
        f = _demo_save_figure()
        p0 = f.plots[0]
        f._on_plot_clicked(p0)
        assert f.selected_plots == [p0]
        assert has_border(p0)

        dlg = export.SaveDialog(f, settings=_ini_settings(tmp))

        # The grab-time hide/restore must leave the real selection exactly
        # as it was -- only the transient pixmap should ever lack the border.
        assert f.selected_plots == [p0]
        assert has_border(p0)
        f.close()
