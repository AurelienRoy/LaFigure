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

"""Small drag grips used for interactive editing.

DragHandle is the shared base: a QGraphicsRectItem using native Qt
mousePress/Move/ReleaseEvent overrides (not pyqtgraph's own "clickable"
protocol -- see CLAUDE.md, "Native Qt event overrides for custom graphics
items"). Subclasses just report drag
deltas/positions to whatever owns them; they don't know how to interpret
the drag themselves.

ResizeHandle/MoveHandle drive subplot resize/move, GutterHandle drags a
grid line (layout.py). AnnotationHandle (annotations.py) reuses DragHandle
the same way for annotation resize/rotate/endpoint editing.
"""
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import pyqtgraph as pg


# Stacking of the layout chrome: subplots sit at 1..n (layout.py), then
# gutters, annotations (800), the snap guides, and handles on top.
GUTTER_Z = 700
GUIDES_Z = 900


class DragHandle(QtWidgets.QGraphicsRectItem):
    """A square (or, with round_shape=True, circular) grip that forwards
    press/move/release to callbacks supplied by its owner, instead of
    hardcoding what the drag means. round_shape only changes what's
    painted -- the hit-testing bounding box stays the square QRectF passed
    to QGraphicsRectItem, same click target size either way."""

    def __init__(self, size, on_press, on_move, on_release,
                 brush_color=(255, 190, 0, 230), cursor=None, z_value=1000,
                 round_shape=False):
        super().__init__(0, 0, size, size)
        self.size = size
        self._round_shape = round_shape
        self._on_press = on_press
        self._on_move = on_move
        self._on_release = on_release
        # Keyboard modifiers of the latest press/move/release, for owners
        # whose drag reads them (Alt = no snapping, Ctrl+drop = swap).
        self.modifiers = QtCore.Qt.NoModifier
        self.setBrush(pg.mkBrush(*brush_color))
        self.setPen(pg.mkPen('k', width=1))
        self.setZValue(z_value)
        if cursor is not None:
            self.setCursor(QtGui.QCursor(cursor))
        self.hide()

    def paint(self, painter, option, widget=None):
        if not self._round_shape:
            super().paint(painter, option, widget)
            return
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawEllipse(self.rect())

    def mousePressEvent(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            ev.ignore()
            return
        self.modifiers = ev.modifiers()
        self._on_press(ev.scenePos())
        ev.accept()

    def mouseMoveEvent(self, ev):
        self.modifiers = ev.modifiers()
        self._on_move(ev.scenePos())
        ev.accept()

    def mouseReleaseEvent(self, ev):
        self.modifiers = ev.modifiers()
        self._on_release(ev.scenePos())
        ev.accept()


class ResizeHandle(DragHandle):
    """A drag grip on the border/corner of the selected subplot. It only
    reports drag positions; LaFigure owns the resize (layout.py), which
    changes that one subplot's box and nothing else."""
    SIZE = 10
    _CURSORS = {
        'top': QtCore.Qt.SizeVerCursor, 'bottom': QtCore.Qt.SizeVerCursor,
        'left': QtCore.Qt.SizeHorCursor, 'right': QtCore.Qt.SizeHorCursor,
        'top-left': QtCore.Qt.SizeFDiagCursor, 'bottom-right': QtCore.Qt.SizeFDiagCursor,
        'top-right': QtCore.Qt.SizeBDiagCursor, 'bottom-left': QtCore.Qt.SizeBDiagCursor,
    }

    def __init__(self, figure, role):
        self.figure = figure
        self.role = role
        super().__init__(
            self.SIZE,
            on_press=lambda pos: figure._begin_resize(role, pos),
            on_move=lambda pos: figure._update_resize(pos, self.modifiers),
            on_release=lambda pos: figure._end_resize(),
            cursor=self._CURSORS[role],
        )


class MoveHandle(DragHandle):
    """A center drag grip on the selected subplot (Select mode only) that
    moves it by dragging -- distinct from ResizeHandle's border/corner
    grips. A plain drop moves it; Ctrl+drop onto another subplot swaps
    their boxes."""
    SIZE = 14

    def __init__(self, figure):
        self.figure = figure
        super().__init__(
            self.SIZE,
            on_press=lambda pos: figure._begin_move(pos),
            on_move=lambda pos: figure._update_move(pos, self.modifiers),
            on_release=lambda pos: figure._end_move(pos, self.modifiers),
            brush_color=(70, 130, 255, 230),
            cursor=QtCore.Qt.SizeAllCursor,
        )


class GutterHandle(DragHandle):
    """An invisible hit strip over one draggable stretch of an interior
    grid line (layout.py's _update_gutters makes one per stretch no
    subplot crosses). Left-drag moves the line -- every subplot edge
    between its two neighbor lines follows; right-click opens the line's
    insert/delete/equalize menu. Shows a split cursor, and a faint strip
    on hover so the gutter is discoverable.

    axis is 'col' (a vertical line between columns) or 'row'; index is the
    line's number, 1..n-1."""
    _CURSORS = {'col': QtCore.Qt.SplitHCursor, 'row': QtCore.Qt.SplitVCursor}
    _IDLE = (0, 0, 0, 0)
    _HOVER = (40, 90, 200, 60)

    def __init__(self, figure, axis, index):
        self.figure = figure
        self.axis = axis
        self.index = index
        super().__init__(
            0,
            on_press=lambda pos: figure._begin_gutter_drag(axis, index, pos),
            on_move=lambda pos: figure._update_gutter_drag(pos, self.modifiers),
            on_release=lambda pos: figure._end_gutter_drag(),
            brush_color=self._IDLE, cursor=self._CURSORS[axis], z_value=GUTTER_Z,
        )
        self.setPen(pg.mkPen(None))
        self.setAcceptHoverEvents(True)
        self._dragging = False

    def mousePressEvent(self, ev):
        if self.figure._placing_kind is not None or self.figure._relink_source is not None:
            ev.ignore()  # the click belongs to placement / Link to...
            return
        if ev.button() == QtCore.Qt.RightButton:
            ev.accept()
            self.figure._show_gutter_menu(self.axis, self.index, ev.screenPos())
            return
        super().mousePressEvent(ev)
        self._dragging = ev.isAccepted()

    def mouseMoveEvent(self, ev):
        if self._dragging:
            super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._dragging:
            self._dragging = False
            super().mouseReleaseEvent(ev)
        else:
            ev.accept()

    def hoverEnterEvent(self, ev):
        self.setBrush(pg.mkBrush(*self._HOVER))

    def hoverLeaveEvent(self, ev):
        self.setBrush(pg.mkBrush(*self._IDLE))


class AnnotationHandle(DragHandle):
    """A drag grip owned by an annotations.AnnotationItem, added as that
    item's Qt *child* (setParentItem) rather than added to the scene
    directly like ResizeHandle/MoveHandle are. Being a child means Qt
    automatically keeps it positioned in the annotation's own local
    coordinate frame as the annotation moves/rotates -- including when
    that frame is a PlotItem's data-coordinate space (axes-anchored
    annotations), not scene pixels. Don't add this to the scene yourself;
    AnnotationItem does it via setParentItem in its own __init__.

    `size` is always literal screen pixels, regardless of the parent's
    anchor/coordinate space -- ItemIgnoresTransformations makes Qt ignore
    inherited ancestor scale/rotation for this item's own rendering (so a
    data-space ancestor transform, e.g. an axes-anchored annotation's
    ViewBox zoom, can't stretch/shrink it), and the rect is centered on
    this item's own local origin so callers can setPos() straight to the
    anchor point with no half-size arithmetic. Only the *position* itself
    still goes through the parent's transform as normal (so the handle
    tracks the shape correctly on pan/zoom) -- only its size/orientation
    is fixed."""

    def __init__(self, size, on_press, on_move, on_release,
                 brush_color=(255, 190, 0, 230), cursor=QtCore.Qt.SizeAllCursor,
                 round_shape=False):
        super().__init__(size, on_press, on_move, on_release,
                          brush_color=brush_color, cursor=cursor, z_value=1001,
                          round_shape=round_shape)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setRect(-size / 2, -size / 2, size, size)


class XLinkBadge(QtWidgets.QGraphicsItem):
    """A small clickable "X-<n>" chip in a subplot's top-right corner,
    shown only while Link X is on (layout.py's _update_x_link_badges /
    _create_x_link_badge / _discard_x_link_badge). Clicking it cycles
    which X-link group the subplot belongs to
    (ViewOpsMixin._cycle_x_link_group). A plain QGraphicsItem (not a
    DragHandle) since it's a click target, not a drag grip; added
    directly to the scene like ResizeHandle/MoveHandle, not parented to
    the PlotItem, since its position is recomputed in scene pixels every
    layout pass (_update_x_link_badges)."""

    WIDTH = 30
    HEIGHT = 16
    Z = 1002   # above resize/move handles (1000/1001): always clickable

    def __init__(self, figure, plot_item):
        super().__init__()
        self.figure = figure
        self.plot_item = plot_item
        self._label = ''
        self.setZValue(self.Z)
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setToolTip("Click to change this subplot's X-link group")

    def set_label(self, text):
        if text != self._label:
            self._label = text
            self.update()

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = pg.mkPen((90, 90, 90), width=1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(pg.mkBrush(255, 255, 255, 225))
        painter.drawRoundedRect(self.boundingRect(), 3, 3)
        painter.setPen(pg.mkPen((30, 30, 30)))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(self.boundingRect(), QtCore.Qt.AlignCenter, self._label)

    def mousePressEvent(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            ev.ignore()
            return
        ev.accept()

    def mouseReleaseEvent(self, ev):
        ev.accept()
        if self.contains(ev.pos()):
            self.figure._cycle_x_link_group(self.plot_item)
