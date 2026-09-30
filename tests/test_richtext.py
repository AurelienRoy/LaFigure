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

"""Rich text (richtext.py) and in-place editing of the subplot title, axis
labels and legend entries (editable_text.py, naming.py). Annotation text
editing is in test_annotation_ops.py.

Every edit here is started by a REAL double-click (QMouseEvents sent to the
viewport, tests/helpers._dblclick) and typed with real key events sent to
the view, since both depend on Qt's own routing: which item gets the
double-click, and whether the figure's window-wide QShortcuts (Del, Esc,
arrows, Ctrl+Z ...) steal keys from the editor.
"""
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets, QtTest

from lafigure import editable_text, richtext
from lafigure.richtext import to_html, to_plain
from tests.helpers import (
    app, m, shown_figure, first_curve, _dblclick, _editor, _type, _click_away,
    _right_click_menu, _drive_font_dialog,
)


# -- the translator ------------------------------------------------------------

def test_bold_and_italic():
    assert to_html(r"\textbf{Gain}") == "<b>Gain</b>"
    assert to_html(r"\mathbf{v}") == "<b>v</b>"
    assert to_html(r"\textit{in situ}") == "<i>in situ</i>"
    assert to_html(r"\mathit{x} and \emph{y}") == "<i>x</i> and <i>y</i>"
    assert to_html(r"\textbf{\textit{both}}") == "<b><i>both</i></b>"


def test_super_and_subscript_need_braces():
    assert to_html("m/s^{2}") == "m/s<sup>2</sup>"
    assert to_html("x_{i,j}") == "x<sub>i,j</sub>"
    assert to_html(r"e^{-t/\tau}") == "e<sup>-t/τ</sup>"
    # Bare ^ and _ stay literal: plain curve names must not turn into subscripts.
    assert to_html("sensor_1 a^b _nolegend_") == "sensor_1 a^b _nolegend_"


def test_greek_letters():
    assert to_html(r"\alpha") == "α"
    assert to_html(r"\beta") == "β"
    assert to_html(r"\mu s") == "μ s"
    assert to_html(r"\Omega\omega") == "Ωω"
    assert to_html(r"\Delta t") == "Δ t"


def test_math_symbols():
    assert to_html(r"a \times b") == "a × b"
    assert to_html(r"\leq") == "≤" and to_html(r"\geq") == "≥"
    assert to_html(r"\pm") == "±"
    assert to_html(r"\infty") == "∞"
    assert to_html(r"x \to \infty") == "x → ∞"
    assert to_html(r"25\degree C") == "25° C"


def test_unknown_tokens_render_literally_and_never_raise():
    assert to_html(r"\notarealcommand") == r"\notarealcommand"
    assert to_html(r"\notarealcommand{x}") == r"\notarealcommand{x}"
    for weird in ("\\", "{", "}", "x^{", r"\textbf", r"\textbf{open", r"\textcolor{red}",
                  "{{}", "^_", "\\\\\\"):
        to_html(weird)  # must not raise
    assert to_html(r"\textbf{open") == r"\textbf{open"
    assert to_html("x^{") == "x^{"


def test_newlines_escapes_colors_and_html_safety():
    assert to_html("two\nlines") == "two<br>lines"
    assert to_html("a<b & c") == "a&lt;b &amp; c", "plain text is never parsed as HTML"
    assert to_html(r"\{x\} \_ \\") == "{x} _ \\"
    assert to_html(r"\textcolor{red}{hot}") == '<span style="color:red">hot</span>'
    assert to_html("") == "" and to_html(None) == ""


def test_to_plain_is_a_unicode_approximation():
    assert to_plain(r"\textbf{v} = 3\times10^{8} m/s") == "v = 3×10⁸ m/s"
    assert to_plain("x_{0}") == "x₀"
    assert to_plain("x_{ij}") == "x_(ij)"


def test_rendered_html_is_what_the_label_shows():
    """The display goes through Qt's rich text: the rendered document of a
    title holds the Unicode, not the markup."""
    f = shown_figure()
    p = f.plots[0]
    p.setTitle(r"\alpha = 2 \times \beta")
    assert p.titleLabel.text == r"\alpha = 2 \times \beta", "the label keeps the SOURCE"
    assert "α = 2 × β" in p.titleLabel.item.toPlainText()
    p.getAxis('bottom').setLabel(r"\textbf{t} (\mu s)")
    assert p.getAxis('bottom').labelText == r"\textbf{t} (\mu s)"
    assert "t (μ s)" in p.getAxis('bottom').label.toPlainText()
    f.close()


# -- in-place editing: title, axis labels, legend ------------------------------

def _title_center(p):
    return p.titleLabel.item.mapToScene(p.titleLabel.item.boundingRect().center())


def test_double_click_title_edits_in_place_and_click_away_commits():
    f = shown_figure()
    p = f.plots[1]
    saved = QtWidgets.QInputDialog.getText
    QtWidgets.QInputDialog.getText = staticmethod(
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no QInputDialog popup")))
    try:
        text_rect = p.titleLabel.item.sceneBoundingRect()
        _dblclick(f, _title_center(p))
        ed = _editor(f)
        assert ed is not None, "a double-click on the title opens the in-place editor"
        assert ed.sceneBoundingRect().intersects(text_rect), "positioned over the title"
        assert ed.text() == "Signal B", "it edits the source, caret-ready"
        assert ed.hasFocus()
        n_undo = len(f.undo_stack)
        _type(f, " (V)")
        _click_away(f)
        assert _editor(f) is None
        assert p.titleLabel.text == "Signal B (V)"
        assert f.subplot_name(p) == "Signal B (V)"
        assert len(f.undo_stack) == n_undo + 1, "one undo entry"
        f.undo()
        assert p.titleLabel.text == "Signal B"
        f.redo()
        assert p.titleLabel.text == "Signal B (V)"
    finally:
        QtWidgets.QInputDialog.getText = saved
    f.close()


def test_inline_editor_caches_to_a_pixmap_so_a_focused_paint_never_hits_the_gl_engine():
    """A focused, editable QGraphicsTextItem's native caret painting can
    segfault (a real access violation, no Python traceback -- see
    CLAUDE.md) the instant it paints directly through pyqtgraph's
    OpenGL-backed viewport with an incomplete/unavailable GL context
    (confirmed 100% reproducible under QT_QPA_PLATFORM=offscreen on
    Windows with useOpenGL forced back on, matching the shipped app's
    default -- see CLAUDE.md bug #10). DeviceCoordinateCache renders the
    item to an ordinary QPixmap once, through Qt's normal raster paint
    engine, sidestepping it. This suite always runs with useOpenGL=False
    (tests/helpers.py), so it can't reproduce the crash itself -- this is
    a guard that the mitigation stays in place, not a repro of the bug."""
    f = shown_figure()
    p = f.plots[1]
    _dblclick(f, _title_center(p))
    ed = _editor(f)
    assert ed is not None
    assert ed.hasFocus()
    assert ed.cacheMode() == QtWidgets.QGraphicsItem.DeviceCoordinateCache
    _click_away(f)
    f.close()


def test_enter_commits_esc_cancels_and_keys_never_reach_the_figure_shortcuts():
    f = shown_figure()
    p = f.plots[1]
    n_plots = len(f.plots)
    _dblclick(f, _title_center(p))
    f._on_plot_clicked(p)  # selected: Del would delete it, if the editor lost the key
    assert p in f.selected_plots and _editor(f) is not None
    _type(f, "XY")
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Backspace)
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Left)
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Delete)
    app.processEvents()
    assert len(f.plots) == n_plots, "Del edited the text, not the figure"
    assert _editor(f).text() == "Signal B", _editor(f).text()  # XY, Backspace, Left, Del
    _type(f, "2")
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Return)
    app.processEvents()
    assert _editor(f) is None and p.titleLabel.text == "Signal B2"
    # Esc cancels -- and doesn't reach the figure's own Esc (deselect all).
    _dblclick(f, _title_center(p))
    f._on_plot_clicked(p)
    _type(f, "zzz")
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Escape)
    app.processEvents()
    assert _editor(f) is None and p.titleLabel.text == "Signal B2"
    assert p in f.selected_plots, "the figure's Esc (deselect all) never saw the key"
    f.close()


def test_shift_enter_inserts_a_line_break_rendered_as_two_lines():
    f = shown_figure()
    p = f.plots[1]
    one_line = p.titleLabel.item.boundingRect().height()
    _dblclick(f, _title_center(p))
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Return, QtCore.Qt.ShiftModifier)
    _type(f, "second")
    assert _editor(f) is not None, "Shift+Enter does not commit"
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Return)
    app.processEvents()
    assert p.titleLabel.text == "Signal B\nsecond"
    assert p.titleLabel.item.document().toPlainText().count("\n") + \
        p.titleLabel.item.document().toPlainText().count(" ") == 1
    assert p.titleLabel.item.boundingRect().height() > 1.6 * one_line, "renders as two lines"
    assert p.titleLabel.sceneBoundingRect().height() > 1.6 * one_line, "and the title row grew to show both"
    f.close()


def test_double_click_axis_labels_edit_in_place():
    f = shown_figure()
    p = f.plots[0]
    for axis_name in ('bottom', 'left'):
        axis = p.getAxis(axis_name)
        axis.setLabel("before")
        app.processEvents()
        label = axis.label
        rect = label.sceneBoundingRect()
        _dblclick(f, label.mapToScene(label.boundingRect().center()))
        ed = _editor(f)
        assert ed is not None, axis_name
        assert ed.sceneBoundingRect().intersects(rect), (axis_name, ed.sceneBoundingRect(), rect)
        assert ed.text() == "before"
        QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        _type(f, r"\omega (rad/s)")
        _click_away(f)
        assert axis.labelText == r"\omega (rad/s)", axis_name
        assert "ω (rad/s)" in axis.label.toPlainText()
        f.undo()
        assert axis.labelText == "before"
    f.close()


def test_axis_label_toolbar_button_edits_in_place_on_every_selected_subplot():
    f = shown_figure()
    p0, p1 = f.plots[0], f.plots[1]
    f._on_plot_clicked(p0)
    f._on_plot_clicked(p1, additive=True)
    saved = QtWidgets.QInputDialog.getText
    QtWidgets.QInputDialog.getText = staticmethod(
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no QInputDialog popup")))
    try:
        f.set_axis_label('bottom')
        app.processEvents()
        assert _editor(f) is not None
        _type(f, "Time")
        QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Return)
        app.processEvents()
    finally:
        QtWidgets.QInputDialog.getText = saved
    assert p0.getAxis('bottom').labelText.endswith("Time")
    assert p1.getAxis('bottom').labelText == p0.getAxis('bottom').labelText
    f.undo()
    assert not p0.getAxis('bottom').labelText.endswith("Time")
    assert not p1.getAxis('bottom').labelText.endswith("Time")
    f.close()


def _legend_label(p, curve):
    for sample, label in p.legend.items:
        if sample.item is curve:
            return label
    raise AssertionError("curve not in legend")


def test_double_click_legend_entry_renames_through_apply_curve_rename():
    f = shown_figure()
    p = f.plots[0]
    f._show_legend(p)
    app.processEvents()
    curve = first_curve(p)
    label = _legend_label(p, curve)
    calls = []
    native = f._apply_curve_rename

    def spy(plot_item, c, name):
        calls.append((plot_item, c, name))
        native(plot_item, c, name)

    f._apply_curve_rename = spy
    try:
        _dblclick(f, label.item.mapToScene(label.item.boundingRect().center()))
        ed = _editor(f)
        assert ed is not None and ed.text() == "signal A"
        assert ed.sceneBoundingRect().intersects(label.item.sceneBoundingRect())
        QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        _type(f, r"V_{out}")
        n_undo = len(f.undo_stack)
        _click_away(f)
        assert calls == [(p, curve, r"V_{out}")], calls
        assert curve.opts['name'] == r"V_{out}", "the SOURCE is the curve's name"
        assert len(f.undo_stack) == n_undo + 1
        new_label = _legend_label(p, curve)
        assert "Vout" in new_label.item.toPlainText(), "the legend renders it"
        # Editing again shows the original markup, not the rendered text.
        _dblclick(f, new_label.item.mapToScene(new_label.item.boundingRect().center()))
        assert _editor(f).text() == r"V_{out}"
        QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Escape)
        app.processEvents()
        f.undo()
        assert calls[-1] == (p, curve, "signal A") and curve.name() == "signal A"
    finally:
        f._apply_curve_rename = native
    f.close()


def test_legend_entries_stay_editable_after_a_z_order_rebuild():
    """_refresh_legend_order (P3) rebuilds every legend label from scratch;
    the new labels must still be editable and rich."""
    f = shown_figure()
    p = f.plots[0]
    f._show_legend(p)
    curve = first_curve(p)
    f._apply_curve_rename(p, curve, r"\alpha")
    f._refresh_legend_order(p)
    app.processEvents()
    label = _legend_label(p, curve)
    assert label.item.toPlainText() == "α"
    _dblclick(f, label.item.mapToScene(label.item.boundingRect().center()))
    assert _editor(f) is not None and _editor(f).text() == r"\alpha"
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Escape)
    f.close()


def test_curve_menu_rename_edits_in_place_over_the_legend():
    f = shown_figure()
    p = f.plots[0]
    f._show_legend(p)
    app.processEvents()
    curve = first_curve(p)
    f._rename_curve(p, curve)
    app.processEvents()
    assert _editor(f) is not None and _editor(f).text() == "signal A"
    _type(f, "!")
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Return)
    app.processEvents()
    assert curve.name() == "signal A!"
    f.close()


def test_curve_rename_source_round_trips_through_copy_paste():
    f = shown_figure()
    p0, p1 = f.plots[0], f.plots[1]
    curve = first_curve(p0)
    f._apply_curve_rename(p0, curve, r"\textbf{V}_{in} \times 2")
    f.active_curve = curve
    f.selected_curves = [curve]
    f.focused_plot = p0
    f.copy_curve()
    f.focused_plot = p1
    f.paste_curve()
    pasted = p1.listDataItems()[-1]
    assert pasted.name() == r"\textbf{V}_{in} \times 2", "the source, not rendered HTML"
    f._show_legend(p1)
    app.processEvents()
    label = _legend_label(p1, pasted)
    assert label.item.toPlainText() == "Vin × 2"
    _dblclick(f, label.item.mapToScene(label.item.boundingRect().center()))
    assert _editor(f).text() == r"\textbf{V}_{in} \times 2"
    QtTest.QTest.keyClick(f.layout_widget, QtCore.Qt.Key_Escape)
    f.close()


def test_subplot_copy_paste_keeps_title_and_axis_label_sources():
    f = shown_figure()
    p = f.plots[1]
    p.setTitle(r"\Delta p")
    p.getAxis('left').setLabel(r"x^{2}")
    f._clear_selection()
    f._on_plot_clicked(p)
    f.copy_subplot()
    f.paste_subplot()
    pasted = f.plots[-1]
    assert pasted.titleLabel.text == r"\Delta p"
    assert "Δ p" in pasted.titleLabel.item.toPlainText()
    assert pasted.getAxis('left').labelText == r"x^{2}"
    f.close()


# -- Font dialog ---------------------------------------------------------------

def _font_on(f, open_menu, spec_check, undo_check):
    chosen = {'family': QtGui.QFont().defaultFamily(), 'size': 17.0, 'bold': True,
              'italic': True, 'underline': True, 'strikeout': True, 'color': (200, 30, 40, 255)}
    menu = open_menu()
    texts = [a.text() for a in menu.actions()]
    assert "Font..." in texts and "Edit Text" in texts, texts
    n_undo = len(f.undo_stack)
    seen = _drive_font_dialog(chosen, lambda: [a for a in menu.actions() if a.text() == "Font..."][0].trigger())
    assert seen, "Font... opened the FontDialog"
    spec_check(chosen)
    assert len(f.undo_stack) == n_undo + 1, "one undo entry"
    f.undo()
    undo_check()
    f.redo()
    spec_check(chosen)


def test_right_click_title_offers_font_and_applies_it_undoably():
    f = shown_figure()
    p = f.plots[1]
    before = editable_text.TitleTarget(f, p).font_spec()

    def check(chosen):
        spec = editable_text.TitleTarget(f, p).font_spec()
        assert spec['bold'] and spec['italic'] and spec['size'] == 17.0, spec
        assert spec['underline'] and spec['strikeout'], spec
        assert spec['color'] == chosen['color']
        font = p.titleLabel.item.document().firstBlock().begin().fragment().charFormat().font()
        assert font.bold() and font.italic() and abs(font.pointSizeF() - 17) < 0.01, "rendered"
        assert font.underline() and font.strikeOut(), "rendered underline/strikeout"

    _font_on(f, lambda: _right_click_menu(f, _title_center(p)), check,
             lambda: _assert_eq(editable_text.TitleTarget(f, p).font_spec(), before))
    f.close()


def test_underline_and_strikeout_apply_show_as_checked_on_reopen_and_survive_a_text_edit():
    """The two symptoms as reported: choosing Underline/Strikeout in the
    Font dialog didn't change anything, and reopening the dialog always
    showed them unchecked again -- both because spec_from_font/
    font_from_spec silently dropped the two properties (QFontDialog's own
    checkboxes worked fine; nothing downstream read them). Also covers a
    gap found while fixing it: rich-text HTML always resets
    text-decoration per span, so a later, unrelated text edit would
    otherwise silently drop it again -- see set_text's
    _retext_keeping_decoration."""
    f = shown_figure()
    p = f.plots[1]
    target = editable_text.TitleTarget(f, p)
    assert target.font_spec()['underline'] is False
    assert target.font_spec()['strikeout'] is False

    on_spec = dict(target.font_spec(), underline=True, strikeout=True)
    _drive_font_dialog(on_spec, lambda: editable_text.edit_font(target))
    assert target.font_spec()['underline'] and target.font_spec()['strikeout'], \
        "choosing Underline/Strikeout in the dialog must actually apply them"
    font = p.titleLabel.item.document().firstBlock().begin().fragment().charFormat().font()
    assert font.underline() and font.strikeOut(), "rendered, not just recorded in the spec"

    # Reopen: the dialog must be SEEDED from the current (now on) state.
    seen2 = []
    real_ask = editable_text.ask_font
    editable_text.ask_font = lambda spec, parent=None: (seen2.append(spec), None)[1]
    try:
        editable_text.edit_font(target)
    finally:
        editable_text.ask_font = real_ask
    assert seen2[0]['underline'] and seen2[0]['strikeout'], \
        "reopening the dialog must show the CURRENT state, not reverted to unchecked"

    # A subsequent, ordinary text edit (double-click, retype, commit) must
    # not silently drop the underline/strikeout that was already applied.
    _dblclick(f, _title_center(p))
    ed = _editor(f)
    assert ed is not None
    _type(f, " v2")
    _click_away(f)
    spec = editable_text.TitleTarget(f, p).font_spec()
    assert spec['underline'] and spec['strikeout'], \
        "underline/strikeout must survive an unrelated text edit"
    font = p.titleLabel.item.document().firstBlock().begin().fragment().charFormat().font()
    assert font.underline() and font.strikeOut(), "still rendered after the text edit"
    f.close()


def test_right_click_axis_label_offers_font_and_applies_it_undoably():
    f = shown_figure()
    p = f.plots[0]
    axis = p.getAxis('left')
    axis.setLabel("Amplitude")
    app.processEvents()
    target = editable_text.AxisLabelTarget(f, p, 'left')
    before = target.font_spec()

    def check(chosen):
        spec = target.font_spec()
        assert spec['bold'] and spec['italic'] and spec['size'] == 17.0 and spec['color'] == chosen['color']
        assert spec['underline'] and spec['strikeout'], spec
        assert "font-weight: bold" in axis.labelString()

    center = axis.label.mapToScene(axis.label.boundingRect().center())
    _font_on(f, lambda: _right_click_menu(f, center), check,
             lambda: _assert_eq(target.font_spec(), before))
    f.close()


def test_right_click_legend_entry_offers_font_for_the_whole_legend():
    f = shown_figure()
    p = f.plots[0]
    f._show_legend(p)
    app.processEvents()
    curve = first_curve(p)
    label = _legend_label(p, curve)
    before = editable_text.LegendEntryTarget(f, p, curve).font_spec()

    def check(chosen):
        for _s, lab in p.legend.items:
            spec = editable_text._label_item_spec(lab)
            assert spec['bold'] and spec['italic'] and spec['size'] == 17.0, spec
            assert spec['underline'] and spec['strikeout'], spec

    center = label.item.mapToScene(label.item.boundingRect().center())
    _font_on(f, lambda: _right_click_menu(f, center), check,
             lambda: _assert_eq(editable_text.LegendEntryTarget(f, p, curve).font_spec(), before))
    # The legend font survives a rename, which rebuilds every label.
    f._apply_curve_rename(p, curve, "renamed")
    check(None)
    f.close()


def _assert_eq(a, b):
    assert a == b, (a, b)


def test_right_click_on_title_opens_only_the_text_menu():
    """The title/axis/legend right-click goes through pyqtgraph's click
    protocol and is accepted there, so the empty-space or subplot menu
    never opens as well."""
    f = shown_figure()
    p = f.plots[1]
    menus = []
    real_exec = QtWidgets.QMenu.exec_
    QtWidgets.QMenu.exec_ = lambda self, *a, **k: menus.append([a.text() for a in self.actions()])
    try:
        pt = _title_center(p)
        from tests.helpers import _mouse
        _mouse(f, QtCore.QEvent.MouseButtonPress, pt, QtCore.Qt.RightButton, button=QtCore.Qt.RightButton)
        _mouse(f, QtCore.QEvent.MouseButtonRelease, pt, QtCore.Qt.NoButton, button=QtCore.Qt.RightButton)
        axis = p.getAxis('bottom')
        axis.setLabel("t")
        app.processEvents()
        pt = axis.label.mapToScene(axis.label.boundingRect().center())
        _mouse(f, QtCore.QEvent.MouseButtonPress, pt, QtCore.Qt.RightButton, button=QtCore.Qt.RightButton)
        _mouse(f, QtCore.QEvent.MouseButtonRelease, pt, QtCore.Qt.NoButton, button=QtCore.Qt.RightButton)
    finally:
        QtWidgets.QMenu.exec_ = real_exec
    assert len(menus) == 2, menus
    assert all("Font..." in texts for texts in menus), menus
    f.close()
