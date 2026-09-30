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

"""In-place rich-text editing for every plot text: subplot title, axis
labels, legend entries (and, through the same editor, annotation text --
see AnnotationItem.start_text_edit).

Every text keeps a SOURCE string in the small LaTeX-ish markup of
richtext.py -- that is what's stored, edited, copied and serialized; only
the display goes through richtext.to_html. For the pyqtgraph items that
is done by wrapping their own render step per instance, so the source
stays in the attribute everyone already reads (LabelItem.text,
AxisItem.labelText, curve.name()) and every existing setTitle/setLabel/
legend.addItem call renders rich text without knowing about it.

Double-click a text: an InlineTextEditor opens over it, showing the
source with a caret. Enter commits, **Shift+Enter inserts a line break**,
Esc cancels, clicking anywhere else commits. Right-click a text: a small
menu with Edit Text and Font... (family/size/bold/italic via QFontDialog,
plus a color). Both are undoable.

Title/axis-label/legend right-clicks go through pyqtgraph's click
protocol (an instance mouseClickEvent that accepts the right button) --
deliberately, not a native contextMenuEvent: pyqtgraph would otherwise
also deliver the same click to the AxisItem/ViewBox beneath, opening the
subplot menu too (the double-menu class of bug CLAUDE.md describes for
annotations).
"""
import math
import weakref

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from .richtext import to_html


# -- the in-place editor ------------------------------------------------------
class InlineTextEditor(QtWidgets.QGraphicsTextItem):
    """A plain-text editor item placed over the text being edited, in
    scene pixels (above everything). Shows the SOURCE markup, not the
    rendered form. Enter commits, Shift+Enter inserts a newline, Esc
    cancels, losing focus (a click elsewhere, another window) commits.
    on_commit(text) is called once, only if the text changed."""
    Z = 1e6

    def __init__(self, source, on_commit, on_finish=None, font=None, select_all=False):
        super().__init__()
        self._on_commit = on_commit
        self._on_finish = on_finish
        self._original = source
        self._done = False
        self.setPlainText(source)
        if font is not None:
            self.setFont(font)
        self.setDefaultTextColor(QtGui.QColor('black'))
        self.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
        self.setZValue(self.Z)
        # A focused, editable QGraphicsTextItem's native caret painting can
        # crash outright (a real access violation, no Python traceback) the
        # instant it's drawn directly through pyqtgraph's OpenGL-backed
        # GraphicsView viewport (useOpenGL=True is the shipped app's
        # default -- see CLAUDE.md's "Millions-of-points performance" note).
        # Reproduced 100% of the time under an incomplete/unavailable GL
        # context (e.g. QT_QPA_PLATFORM=offscreen on Windows, CLAUDE.md bug
        # #10) and is a real risk on any real session whose OpenGL context
        # is similarly limited (remote desktop / a VM without GPU
        # passthrough / a broken driver). DeviceCoordinateCache renders
        # this item into an ordinary QPixmap once (through Qt's normal,
        # non-GL raster paint engine) and blits that onto the GL surface,
        # sidestepping whatever in Qt's text-control caret painting doesn't
        # get along with a GL paint engine -- confirmed to still commit
        # real typed edits correctly with this mode on.
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)
        self.document().contentsChanged.connect(self.update)
        # Caret at the end; or everything selected, so typing replaces it
        # (a placeholder, e.g. a just-placed annotation's "Text").
        cursor = self.textCursor()
        if select_all:
            cursor.select(QtGui.QTextCursor.Document)
        else:
            cursor.movePosition(QtGui.QTextCursor.End)
        self.setTextCursor(cursor)

    def text(self):
        return self.toPlainText()

    def paint(self, painter, option, widget=None):
        rect = self.boundingRect()
        painter.setPen(QtGui.QPen(QtGui.QColor(40, 110, 220), 1))
        painter.setBrush(QtGui.QColor(255, 255, 255, 245))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        # The default focus/selection frame is drawn by the base class
        # only when selected; the caret itself is part of its own paint.
        super().paint(painter, option, widget)

    def sceneEvent(self, ev):
        # Every key the editor sees is text editing: keep the figure's
        # window-wide QShortcuts (Del, arrows, Esc, Tab, Ctrl+C/V/Z ...)
        # from stealing them while it has focus. Qt asks the focus item
        # first via ShortcutOverride; accepting it delivers the key here.
        if ev.type() == QtCore.QEvent.ShortcutOverride:
            ev.accept()
            return True
        return super().sceneEvent(ev)

    def keyPressEvent(self, ev):
        key = ev.key()
        if key == QtCore.Qt.Key_Escape:
            self.cancel()
        elif key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if ev.modifiers() & QtCore.Qt.ShiftModifier:
                self.textCursor().insertText('\n')
            else:
                self.commit()
        elif key in (QtCore.Qt.Key_Tab, QtCore.Qt.Key_Backtab):
            pass  # no focus chain to walk inside the scene
        else:
            super().keyPressEvent(ev)
        ev.accept()

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        # The editor's own right-click menu takes focus as a popup: keep going.
        if ev.reason() != QtCore.Qt.PopupFocusReason:
            self.commit()

    def commit(self):
        if self._done:
            return
        text = self.toPlainText()
        self._finish()
        if text != self._original:
            self._on_commit(text)

    def cancel(self):
        if not self._done:
            self._finish()

    def _finish(self):
        self._done = True
        scene = self.scene()
        if scene is not None and getattr(scene, '_lafigure_inline_editor', None) is self:
            scene._lafigure_inline_editor = None
        self.setVisible(False)
        if self._on_finish is not None:
            self._on_finish()
        # Removed on the next event-loop turn: this may be running inside
        # this item's own focusOut/keyPress dispatch (CLAUDE.md bug #19's
        # rule -- don't tear down what the current event is still using).
        QtCore.QTimer.singleShot(0, self._remove)

    def _remove(self):
        scene = self.scene()
        if scene is not None:
            scene.removeItem(self)


def active_editor(scene):
    """The InlineTextEditor currently open on `scene`, or None."""
    return getattr(scene, '_lafigure_inline_editor', None) if scene is not None else None


def start_inline_edit(scene, text_rect, source, on_commit, font=None, hidden_item=None,
                      centered=False, select_all=False):
    """Open an InlineTextEditor on `scene` over `text_rect` (the edited
    text's box, scene coordinates) -- top-left aligned, or centered on it
    when `centered` (a rotated text, e.g. the y-axis label). `hidden_item`
    is faded out while editing so the rendered form doesn't show through.
    A second edit started while one is open commits the first."""
    previous = active_editor(scene)
    if previous is not None:
        previous.commit()
    restore = None
    if hidden_item is not None:
        old_opacity = hidden_item.opacity()
        hidden_item.setOpacity(0.0)

        def restore():
            try:
                hidden_item.setOpacity(old_opacity)
            except RuntimeError:
                pass  # the item was rebuilt meanwhile (a legend rename)
    editor = InlineTextEditor(source, on_commit, on_finish=restore, font=font, select_all=select_all)
    scene.addItem(editor)
    size = editor.boundingRect().size()
    pos = text_rect.center() - QtCore.QPointF(size.width() / 2, size.height() / 2) if centered \
        else text_rect.topLeft() - QtCore.QPointF(4, 4)  # 4px: QTextDocument's own margin
    # Keep it on screen, even for a text right at the figure's edge.
    visible = scene.sceneRect()
    views = scene.views()
    if views:
        visible = views[0].mapToScene(views[0].viewport().rect()).boundingRect()
    pos.setX(max(visible.left(), min(pos.x(), visible.right() - size.width())))
    pos.setY(max(visible.top(), min(pos.y(), visible.bottom() - size.height())))
    editor.setPos(pos)
    scene._lafigure_inline_editor = editor
    if views:
        views[0].setFocus(QtCore.Qt.OtherFocusReason)
    editor.setFocus(QtCore.Qt.OtherFocusReason)
    return editor


# -- font specs ---------------------------------------------------------------
# A font spec is a plain, serializable dict: {'family', 'size' (points),
# 'bold', 'italic', 'underline', 'strikeout', 'color' (r, g, b, a)}.
def font_from_spec(spec, base=None):
    font = QtGui.QFont(base) if base is not None else QtGui.QFont(QtWidgets.QApplication.font())
    if spec.get('family'):
        font.setFamily(spec['family'])
    if spec.get('size'):
        font.setPointSizeF(float(spec['size']))
    font.setBold(bool(spec.get('bold')))
    font.setItalic(bool(spec.get('italic')))
    font.setUnderline(bool(spec.get('underline')))
    font.setStrikeOut(bool(spec.get('strikeout')))
    return font


def spec_from_font(font, color):
    c = QtGui.QColor(color)
    size = font.pointSizeF()
    if size <= 0:  # a pixel-sized font
        size = QtWidgets.QApplication.font().pointSizeF()
    return {'family': font.family(), 'size': round(size, 2), 'bold': font.bold(),
            'italic': font.italic(), 'underline': font.underline(),
            'strikeout': font.strikeOut(), 'color': (c.red(), c.green(), c.blue(), c.alpha())}


def _apply_text_decoration(text_item, underline, strikeout):
    """Underline/strikeout on a rich-text QGraphicsTextItem (title/axis/
    legend labels and annotation text are all rendered as per-character
    HTML spans, via pg.LabelItem.setText's CSS or richtext.to_html) can't
    be set through the item's own base QFont: an HTML span with ANY style
    always fully specifies text-decoration, defaulting it to 'none'
    regardless of the base font -- confirmed empirically, unlike
    font-family/size/weight/style, which the span DOES inherit from the
    base font when not overridden. A QTextCursor.mergeCharFormat over the
    whole document is the one mechanism that actually sticks."""
    if text_item is None:
        return
    doc = text_item.document()
    cursor = QtGui.QTextCursor(doc)
    cursor.select(QtGui.QTextCursor.Document)
    fmt = QtGui.QTextCharFormat()
    fmt.setFontUnderline(bool(underline))
    fmt.setFontStrikeOut(bool(strikeout))
    cursor.mergeCharFormat(fmt)


def _read_text_decoration(text_item):
    """(underline, strikeout) as _apply_text_decoration last set them --
    read from the document's own char format, the same place it wrote
    them, rather than from the item's base font (see that function's
    docstring for why the base font doesn't reflect it)."""
    if text_item is None:
        return False, False
    doc = text_item.document()
    cursor = QtGui.QTextCursor(doc)
    cursor.setPosition(0)
    cursor.setPosition(min(1, doc.characterCount() - 1), QtGui.QTextCursor.KeepAnchor)
    fmt = cursor.charFormat()
    return fmt.fontUnderline(), fmt.fontStrikeOut()


def _css_pt(value, default):
    try:
        if isinstance(value, str) and value.endswith('pt'):
            return float(value[:-2])
    except ValueError:
        pass
    return default


class FontDialog(QtWidgets.QDialog):
    """QFontDialog (family/size/bold/italic, embedded) plus a text color
    button -- Qt's own font dialog has no color. spec() reads the choice."""

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Font")
        self.font_widget = QtWidgets.QFontDialog(self)
        self.font_widget.setOptions(QtWidgets.QFontDialog.NoButtons
                                    | QtWidgets.QFontDialog.DontUseNativeDialog)
        self.font_widget.setWindowFlags(QtCore.Qt.Widget)
        self._font = font_from_spec(spec)
        self.font_widget.currentFontChanged.connect(self._on_font_changed)
        self.set_font(self._font)
        self._color = QtGui.QColor(*spec.get('color', (0, 0, 0, 255)))
        self.color_button = QtWidgets.QPushButton("Color...")
        self.color_button.clicked.connect(self._pick_color)
        self._update_color_button()
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                             | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.font_widget)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.color_button)
        row.addStretch(1)
        row.addWidget(buttons)
        layout.addLayout(row)

    def set_font(self, font):
        """Select `font` in the dialog. Kept as given even where the font
        database can't show it (e.g. the offscreen test platform has no
        fonts at all, so QFontDialog would read back its default)."""
        self.font_widget.setCurrentFont(font)
        self._font = QtGui.QFont(font)

    def _on_font_changed(self, font):
        self._font = QtGui.QFont(font)

    def set_color(self, color):
        self._color = QtGui.QColor(color)
        self._update_color_button()

    def _pick_color(self):
        color = QtWidgets.QColorDialog.getColor(self._color, self, "Text color",
                                                QtWidgets.QColorDialog.ShowAlphaChannel)
        if color.isValid():
            self.set_color(color)

    def _update_color_button(self):
        self.color_button.setStyleSheet(
            f"QPushButton {{ border-left: 14px solid {self._color.name()}; padding: 3px 8px; }}")

    def spec(self):
        return spec_from_font(self._font, self._color)


def ask_font(spec, parent=None):
    """The chosen font spec, or None if cancelled. Module-level so tests
    can drive the real FontDialog without a modal exec_()."""
    dialog = FontDialog(spec, parent)
    if dialog.exec_() != QtWidgets.QDialog.Accepted:
        return None
    return dialog.spec()


# -- text targets -------------------------------------------------------------
class TextTarget:
    """One editable plot text. Subclasses say where it is and how to read/
    write its source and font; the undo bookkeeping is shared (set_text/
    set_font below)."""
    label = "Text"
    allow_empty = False
    centered = False

    def __init__(self, figure):
        self.figure = figure

    def source(self):
        raise NotImplementedError

    def apply_source(self, text):
        raise NotImplementedError

    def font_spec(self):
        raise NotImplementedError

    def apply_font(self, spec):
        raise NotImplementedError

    def text_item(self):
        """The QGraphicsItem showing the text (faded while editing)."""
        raise NotImplementedError

    def scene_rect(self):
        return self.text_item().sceneBoundingRect()


class TitleTarget(TextTarget):
    label = "Title"
    allow_empty = True

    def __init__(self, figure, plot_item):
        super().__init__(figure)
        self.plot_item = plot_item

    def source(self):
        return self.plot_item.titleLabel.text or ''

    def apply_source(self, text):
        # setTitle('') would keep an empty row; None hides the title row.
        self.plot_item.setTitle(text if text else None)
        if not text:
            self.plot_item.titleLabel.text = ''
        if self.figure is not None:
            self.figure.registry.notify_subplots_changed(self.figure)

    def font_spec(self):
        return _label_item_spec(self.plot_item.titleLabel)

    def apply_font(self, spec):
        _apply_label_item_spec(self.plot_item.titleLabel, spec)

    def text_item(self):
        return self.plot_item.titleLabel.item

    def scene_rect(self):
        label = self.plot_item.titleLabel
        if not label.isVisible() or not label.text:
            r = self.plot_item.sceneBoundingRect()
            return QtCore.QRectF(r.center().x() - 40, r.top() + 4, 80, 20)
        return label.item.sceneBoundingRect()


class AxisLabelTarget(TextTarget):
    allow_empty = True

    def __init__(self, figure, plot_item, axis_name):
        super().__init__(figure)
        self.plot_item = plot_item
        self.axis_name = axis_name
        self.label = "X Label" if axis_name == 'bottom' else "Y Label"
        self.centered = axis_name in ('left', 'right')

    @property
    def axis(self):
        return self.plot_item.getAxis(self.axis_name)

    def source(self):
        return self.axis.labelText or ''

    def apply_source(self, text):
        axis = self.axis
        axis.setLabel(text, units=axis.labelUnits or None, unitPrefix=axis.labelUnitPrefix or None)

    def font_spec(self):
        axis = self.axis
        style = dict(axis.labelStyle)
        font = QtGui.QFont(axis.label.font())
        if style.get('font-family'):
            font.setFamily(style['font-family'])
        font.setPointSizeF(_css_pt(style.get('font-size'), font.pointSizeF()))
        font.setBold(style.get('font-weight') == 'bold')
        font.setItalic(style.get('font-style') == 'italic')
        underline, strikeout = _read_text_decoration(axis.label)
        font.setUnderline(underline)
        font.setStrikeOut(strikeout)
        color = QtGui.QColor(style['color']) if style.get('color') else axis.textPen().color()
        return spec_from_font(font, color)

    def apply_font(self, spec):
        axis = self.axis
        c = QtGui.QColor(*spec['color'])
        style = {'font-family': spec['family'], 'font-size': f"{spec['size']}pt",
                 'font-weight': 'bold' if spec['bold'] else 'normal',
                 'font-style': 'italic' if spec['italic'] else 'normal',
                 'color': c.name(QtGui.QColor.HexArgb)}
        axis.setLabel(axis.labelText, units=axis.labelUnits or None,
                      unitPrefix=axis.labelUnitPrefix or None, **style)
        # AxisItem.setLabel has no underline/strikeout of its own -- same
        # second-pass reasoning as _apply_label_item_spec.
        _apply_text_decoration(axis.label, spec.get('underline'), spec.get('strikeout'))

    def text_item(self):
        return self.axis.label

    def scene_rect(self):
        axis = self.axis
        if axis.label.isVisible() and axis.labelText:
            return axis.label.sceneBoundingRect()
        r = axis.sceneBoundingRect()
        return QtCore.QRectF(r.center().x() - 30, r.center().y() - 10, 60, 20)


class LegendEntryTarget(TextTarget):
    """A legend entry's text IS its curve's name: every edit goes through
    NamingMixin._apply_curve_rename, like the curve menu's Rename, so
    curve.opts['name'] (the Curve browser, CSV export, ...) follows. Its
    font is the whole legend's (stored on the subplot, since a legend's
    labels are rebuilt on every rename/reorder)."""
    label = "Legend"

    def __init__(self, figure, plot_item, curve):
        super().__init__(figure)
        self.plot_item = plot_item
        self.curve = curve

    def source(self):
        return self.curve.name() or ''

    def apply_source(self, text):
        self.figure._apply_curve_rename(self.plot_item, self.curve, text)

    def _label(self):
        legend = self.plot_item.legend
        if legend is not None:
            for sample, label in legend.items:
                if sample.item is self.curve:
                    return label
        return None

    def font_spec(self):
        spec = getattr(self.plot_item, '_lafigure_legend_font', None)
        if spec is not None:
            return dict(spec)
        label = self._label()
        return _label_item_spec(label) if label is not None else spec_from_font(
            QtWidgets.QApplication.font(), QtGui.QColor('black'))

    def apply_font(self, spec):
        self.plot_item._lafigure_legend_font = dict(spec) if spec is not None else None
        legend = self.plot_item.legend
        if legend is not None and spec is not None:
            for _sample, label in legend.items:
                _apply_label_item_spec(label, spec)
            legend.updateSize()

    def text_item(self):
        label = self._label()
        return label.item if label is not None else None

    def scene_rect(self):
        item = self.text_item()
        return item.sceneBoundingRect() if item is not None else QtCore.QRectF()


class AnnotationTextTarget(TextTarget):
    """A 'text'/'textarrow' annotation's text. Its geometry (the label's
    box feeds shape()/boundingRect()) stays AnnotationItem's business:
    everything goes through its own _apply_text/_apply_font."""
    label = "Text"

    def __init__(self, annotation):
        super().__init__(annotation.figure)
        self.annotation = annotation
        self.plot_item = annotation.parent_plot

    def source(self):
        return self.annotation.text or ''

    def apply_source(self, text):
        self.annotation._apply_text(text)

    def font_spec(self):
        return self.annotation.font_spec()

    def apply_font(self, spec):
        self.annotation._apply_font(spec)

    def text_item(self):
        return self.annotation._text_item

    def scene_rect(self):
        return self.annotation._text_scene_rect()


def _label_item_spec(label):
    """The effective font of a pg.LabelItem: its opts (the CSS pyqtgraph
    builds from them wins over the item's own font) over item.font()."""
    opts = label.opts
    font = QtGui.QFont(label.item.font())
    if opts.get('family'):
        font.setFamily(opts['family'])
    font.setPointSizeF(_css_pt(opts.get('size'), font.pointSizeF()))
    font.setBold(bool(opts.get('bold', False)))
    font.setItalic(bool(opts.get('italic', False)))
    underline, strikeout = _read_text_decoration(label.item)
    font.setUnderline(underline)
    font.setStrikeOut(strikeout)
    color = opts.get('color')
    color = pg.mkColor(color if color is not None else pg.getConfigOption('foreground'))
    return spec_from_font(font, color)


def _apply_label_item_spec(label, spec):
    label.setText(label.text, family=spec['family'], size=f"{spec['size']}pt",
                  bold=bool(spec['bold']), italic=bool(spec['italic']),
                  color=QtGui.QColor(*spec['color']))
    # pg.LabelItem.setText has no underline/strikeout kwarg of its own
    # (see _apply_text_decoration's docstring) -- apply it as a second pass.
    _apply_text_decoration(label.item, spec.get('underline'), spec.get('strikeout'))


# -- undoable edits (shared by every target) ----------------------------------
def _retext_keeping_decoration(target, text):
    """apply_source(text), preserving whatever underline/strikeout was
    showing beforehand. Every target's rich text (pg.LabelItem's CSS, or
    richtext.to_html for an annotation) is fully rebuilt by a text change,
    which wipes the document-level mergeCharFormat _apply_text_decoration
    uses (see its own docstring) -- title/axis labels and annotation text
    have nowhere else that decoration is durably stored, unlike bold/
    italic/color/family (pg.LabelItem.opts persists those across a plain
    setText, and a legend rename separately reapplies its own persisted
    _lafigure_legend_font spec) -- so this is the one place that has to
    survive every target kind's own apply_source."""
    item = target.text_item()
    decoration = _read_text_decoration(item)
    target.apply_source(text)
    _apply_text_decoration(target.text_item(), *decoration)


def set_text(targets, text):
    """Set `text` (a source string) on every target, one undo entry."""
    targets = [t for t in targets if t.source() != text]
    if not targets:
        return
    figure = targets[0].figure
    old = [(t, t.source()) for t in targets]

    def apply_new():
        for t in targets:
            _retext_keeping_decoration(t, text)

    def undo_fn():
        for t, source in old:
            _retext_keeping_decoration(t, source)

    apply_new()
    figure._push_history(undo_fn=undo_fn, redo_fn=apply_new)


def set_font(targets, spec):
    """Apply a font spec to every target, one undo entry."""
    if not targets:
        return
    figure = targets[0].figure
    old = [(t, t.font_spec()) for t in targets]

    def apply_new():
        for t in targets:
            t.apply_font(spec)

    def undo_fn():
        for t, s in old:
            t.apply_font(s)

    apply_new()
    figure._push_history(undo_fn=undo_fn, redo_fn=apply_new)


def edit_in_place(target, also=(), select_all=False):
    """Open the in-place editor on `target`; on commit, the new source goes
    to it (and to every target in `also` -- a multi-selection) as one undo
    entry. Returns the editor, or None if the text isn't on screen."""
    item = target.text_item()
    scene = item.scene() if item is not None else None
    if scene is None and getattr(target, 'plot_item', None) is not None:
        scene = target.plot_item.scene()
    if scene is None:
        return None
    font = font_from_spec(target.font_spec())

    def on_commit(text):
        if text or target.allow_empty:
            set_text([target, *also], text)

    return start_inline_edit(scene, target.scene_rect(), target.source(), on_commit, font=font,
                             hidden_item=item, centered=target.centered, select_all=select_all)


def edit_font(target, also=()):
    """Ask for a font (FontDialog), apply it to target (+ `also`), undoable."""
    spec = ask_font(target.font_spec())
    if spec is not None:
        set_font([target, *also], spec)


def _show_text_menu(target, ev):
    menu = QtWidgets.QMenu()
    header = menu.addAction(target.label)
    header.setEnabled(False)
    bold = header.font()
    bold.setBold(True)
    header.setFont(bold)
    menu.addAction("Edit Text").triggered.connect(lambda: edit_in_place(target))
    menu.addAction("Font...").triggered.connect(lambda: edit_font(target))
    pos = ev.screenPos()
    menu.exec_(pos.toPoint() if hasattr(pos, 'toPoint') else pos)


def _figure_of(item):
    """The LaFigure showing `item` (via its scene's view), or None."""
    scene = item.scene()
    for view in (scene.views() if scene is not None else []):
        window = view.window()
        if hasattr(window, '_push_history'):
            return window
    return None


def wire_text_target(item, make_target):
    """Double-click `item` = in-place edit; right-click = Edit Text / Font
    menu. make_target() builds the TextTarget lazily, at event time (the
    figure isn't reachable yet when a subplot is being built)."""
    def double_click(ev):
        target = make_target()
        if target is not None:
            edit_in_place(target)
        ev.accept()

    def click(ev):
        if ev.button() != QtCore.Qt.RightButton:
            return
        target = make_target()
        if target is None:
            return
        ev.accept()
        _show_text_menu(target, ev)

    item.mouseDoubleClickEvent = double_click
    item.mouseClickEvent = click


# -- rich rendering hooks on pyqtgraph's own items ----------------------------
# Every function stored on an item below reaches that item (and its
# subplot/figure) only through a weakref. A strong one would make a
# cycle item -> __dict__ -> closure -> item; once such an item is dropped
# (a legend label replaced on rename) the garbage collector breaks the
# cycle by CLEARING the item's __dict__ while Qt still holds the C++
# object -- whose next sizeHint() call then fails on a pyqtgraph attribute
# that no longer exists ('LabelItem' object has no attribute '_sizeHint').
TITLE_ROW_PX = 30  # pyqtgraph's own fixed title row height


def make_label_item_rich(label, on_rendered=None):
    """From now on, label.setText(source) shows to_html(source) while
    label.text keeps the source. Idempotent. on_rendered(label) runs
    after each render."""
    if getattr(label, '_lafigure_rich', False):
        return
    ref = weakref.ref(label)

    def set_text(text, **args):
        lab = ref()
        if lab is None:
            return
        type(lab).setText(lab, to_html(text), **args)
        lab.text = text
        if on_rendered is not None:
            on_rendered(lab)

    label.setText = set_text
    label._lafigure_rich = True
    if label.text:
        label.setText(label.text)


def make_axis_label_rich(axis):
    """axis.labelText keeps the source; the drawn label is its to_html."""
    if getattr(axis, '_lafigure_rich', False):
        return
    ref = weakref.ref(axis)

    def label_string():
        ax = ref()
        source = ax.labelText
        ax.labelText = to_html(source)
        try:
            return type(ax).labelString(ax)
        finally:
            ax.labelText = source

    axis.labelString = label_string
    axis._lafigure_rich = True
    if axis.labelText:
        axis._updateLabel()


def _fit_title_row(label):
    """pyqtgraph pins the title row to 30px: grow it for a multi-line title."""
    plot_item = label.parentItem()
    if label.maximumHeight() <= 0 or not hasattr(plot_item, 'titleLabel'):
        return  # setTitle(None): hidden, row collapsed
    need = max(TITLE_ROW_PX, int(math.ceil(label.item.boundingRect().height())))
    label.setMaximumHeight(need)
    plot_item.layout.setRowFixedHeight(0, need)


def wire_plot_labels_editable(plot_item):
    """Double-click title / x-label / y-label to edit them in place;
    right-click for Edit Text / Font. All three render rich text."""
    ref = weakref.ref(plot_item)
    title_label = plot_item.titleLabel
    make_label_item_rich(title_label, on_rendered=_fit_title_row)
    wire_text_target(title_label, lambda: _target_if_figure(ref(), TitleTarget))
    for axis_name in ('bottom', 'left'):
        axis = plot_item.getAxis(axis_name)
        make_axis_label_rich(axis)
        wire_text_target(axis.label, lambda axis_name=axis_name: _target_if_figure(
            ref(), lambda f, p: AxisLabelTarget(f, p, axis_name)))


def _target_if_figure(plot_item, build):
    figure = _figure_of(plot_item) if plot_item is not None else None
    return build(figure, plot_item) if figure is not None else None


def _wire_legend_label(figure, plot_item, curve, label):
    make_label_item_rich(label)
    spec = getattr(plot_item, '_lafigure_legend_font', None)
    if spec is not None:
        _apply_label_item_spec(label, spec)
    refs = weakref.ref(figure), weakref.ref(plot_item), weakref.ref(curve)

    def make_target():
        f, p, c = (r() for r in refs)
        return LegendEntryTarget(f, p, c) if None not in (f, p, c) else None

    wire_text_target(label, make_target)


def wire_legend_editable(figure, plot_item, legend):
    """Double-click a legend entry's text to rename that curve in place.

    Goes through the same undoable rename path as the curve menu's Rename
    (NamingMixin._apply_curve_rename) instead of just setting the legend
    label's own displayed text -- the latter used to leave curve.opts
    ['name'] untouched, so the new name never reached anywhere else that
    reads it (the Curve browser, Export to CSV's header, ...).

    Also wraps legend.addItem, so an entry added later -- a rename, a
    z-order change (_refresh_legend_order rebuilds every entry), a new
    curve -- is editable and rich too without every caller re-wiring."""
    for sample, label in legend.items:
        _wire_legend_label(figure, plot_item, sample.item, label)
    if getattr(legend, '_lafigure_wired', False):
        return
    refs = weakref.ref(figure), weakref.ref(plot_item), weakref.ref(legend)

    def add_item(item, name):
        f, p, leg = (r() for r in refs)
        type(leg).addItem(leg, item, name)
        if f is not None and p is not None and leg.items and leg.items[-1][0].item is item:
            _wire_legend_label(f, p, item, leg.items[-1][1])
            leg.updateSize()

    legend.addItem = add_item
    legend._lafigure_wired = True
    legend.updateSize()
