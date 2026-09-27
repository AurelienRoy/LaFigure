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

"""Annotations overlaid on a LaFigure: shapes, text, arrows, and a data
cursor, each with a filiation (parent) that is one of:

  - 'figure': free-floating, positioned in scene (pixel) coordinates,
    added directly to the shared QGraphicsScene. Not carried by
    copy_subplot/paste_subplot (it isn't any subplot's).
  - 'border': tied to a subplot's screen position, positioned in scene
    (pixel) coordinates as an offset from that subplot's top-left corner.
    Added directly to the scene (siblings of the PlotItem, not children of
    it -- PlotItem is a layout-managed grid cell, not a useful coordinate
    parent). Travels with the subplot on copy/paste; repositioned manually
    whenever the subplot's screen rect changes (see
    LaFigure._reposition_annotations).
  - 'axes': tied to a subplot's DATA coordinates, so it pans/zooms with the
    plot. Added via PlotItem.addItem(...), which parents it under the
    ViewBox's internal child group -- that group's own transform IS the
    data<->pixel mapping, so this annotation's local coordinate space is
    data units for free, no manual repositioning needed on pan/zoom.

Every AnnotationItem's own geometry (self.pos(), self.p1_local, child
handle positions) is expressed in "whatever coordinate space its parent
puts it in" -- scene pixels for figure/border, data units for axes. This
is what lets one class's drag/resize/rotate math work unmodified across
all three anchor kinds: the *meaning* of a unit differs, but the Qt API
calls (setPos/setRotation/mapFromScene) are identical either way.

Filiation is shown, in Select mode, as a colored dashed outline around the
annotation using filiation_color(parent_plot, figure.plots) -- the same
color for every annotation (and, conceptually, the border-highlight of
the subplot itself) sharing a parent.
"""
import math
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .handles import AnnotationHandle

SHAPE_KINDS = ('rect', 'ellipse', 'line', 'arrow', 'doublearrow', 'text', 'textarrow', 'cursor')

SHAPE_LABELS = {
    'rect': 'Rectangle', 'ellipse': 'Ellipse', 'line': 'Line',
    'arrow': 'Arrow', 'doublearrow': 'Double Arrow', 'text': 'Text',
    'textarrow': 'Text + Arrow', 'cursor': 'Data Cursor',
}

# Two-click-to-place kinds need a start click (p0) and an end click (p1).
# The rest place on a single click.
TWO_CLICK_KINDS = ('rect', 'ellipse', 'line', 'arrow', 'doublearrow', 'textarrow')

# Kinds edited by dragging each endpoint/corner independently (both a
# start-point and end-point handle), in addition to (for rect/ellipse
# only -- see NO_ROTATE_KINDS below) a rotate handle. For 'rect'/'ellipse'
# the two points are opposite corners; for the rest, the two ends of the
# line/arrow.
TWO_ENDPOINT_KINDS = ('rect', 'ellipse', 'line', 'arrow', 'doublearrow', 'textarrow')

# Kinds with no inherent "up" direction to rotate around, or (for
# 'cursor') no rotate handle by design -- a line/arrow segment's rotation
# is already fully expressed by dragging its two endpoints independently,
# so a separate rotate handle would be redundant. 'rect'/'ellipse'/'text'
# are NOT here: they keep a rotate handle alongside their endpoint
# handle(s), since unlike a line segment they have a visual orientation
# that dragging corners/endpoints alone can't express.
NO_ROTATE_KINDS = ('cursor', 'line', 'arrow', 'doublearrow', 'textarrow')

SUBPLOT_FILIATION_COLOR = QtGui.QColor(220, 40, 40)
FIGURE_FILIATION_COLOR = QtGui.QColor(120, 120, 120)


def filiation_color(parent_plot, plots):
    """Dashed outline color for an annotation's filiation, by parent kind:
    red for any subplot parent, grey for a free-floating (figure-parented)
    annotation. `plots` is unused now (kept for call-site compatibility)."""
    if parent_plot is None:
        return FIGURE_FILIATION_COLOR
    return SUBPLOT_FILIATION_COLOR


def _pen_to_tuple(pen):
    c = pen.color()
    return (c.red(), c.green(), c.blue(), c.alpha(), pen.widthF())


def _pen_from_tuple(t):
    r, g, b, a, w = t
    pen = pg.mkPen(color=(r, g, b, a), width=w)
    # Cosmetic: stroke width is always real screen pixels, unaffected by
    # an 'axes'-anchored annotation's ViewBox zoom transform -- otherwise
    # the same width value would render thicker/thinner as the subplot is
    # zoomed (a non-cosmetic pen's width is in the painter's local units).
    pen.setCosmetic(True)
    return pen


def _brush_to_tuple(brush):
    if brush is None:
        return None
    c = brush.color()
    return (c.red(), c.green(), c.blue(), c.alpha())


def _brush_from_tuple(t):
    if t is None:
        return None
    return pg.mkBrush(*t)


def _draw_arrowhead(painter, tip, tail, size=10):
    """Draw a filled triangular arrowhead at `tip`, pointing away from
    `tail` -- shared by 'arrow' (one head) and 'doublearrow' (two)."""
    angle = math.atan2(tip.y() - tail.y(), tip.x() - tail.x())
    spread = math.pi / 7
    p1 = tip - QtCore.QPointF(size * math.cos(angle - spread), size * math.sin(angle - spread))
    p2 = tip - QtCore.QPointF(size * math.cos(angle + spread), size * math.sin(angle + spread))
    painter.drawPolygon(QtGui.QPolygonF([tip, p1, p2]))


class AnnotationItem(QtWidgets.QGraphicsObject):
    """One annotation. `kind` selects both its geometry (self.p1_local,
    relative to self.pos() == p0) and how paint() renders it.

    TWO_ENDPOINT_KINDS (rect/ellipse/line/arrow/doublearrow/textarrow) get
    a second draggable point handle in addition to the usual end handle:
    both p0 (this item's own self.pos(), normally fixed) and p1 become
    independently draggable, each moving its own end while leaving the
    other in place -- see _on_start_press/_drag/_release. For
    'rect'/'ellipse' the two points are opposite corners (self.p1_local is
    the diagonal, not a width/height); for the rest, the two ends of the
    line/arrow.

    NO_ROTATE_KINDS (cursor/line/arrow/doublearrow/textarrow) additionally
    get no rotate handle: a line/arrow segment's rotation is already fully
    expressed by its two independently draggable endpoints, so a separate
    rotate handle would be redundant, and 'cursor' has no shape to orient.
    'rect'/'ellipse'/'text' DO keep a rotate handle (alongside their
    endpoint handle(s) for rect/ellipse), since they have a visual
    orientation two corner-drags alone can't express.

    Every handle (_end_handle/_start_handle/_rotate_handle) is a constant
    on-screen pixel size via AnnotationHandle's own ItemIgnoresTransformations
    flag (see handles.py), so it doesn't shrink/balloon with an
    'axes'-anchored annotation's subplot zoom -- only the shape's own
    *geometry* (self.p1_local, i.e. where its endpoints sit) is meant to
    track the data/zoom, per the anchor model above.

    Whole-body drag (click empty shape interior, or the shape's own
    outline/fill, and drag) moves the annotation via native
    mousePress/Move/ReleaseEvent overrides -- see CLAUDE.md's note that
    custom QGraphicsItem subclasses in this app use Qt's own convention,
    not pyqtgraph's parallel "clickable" protocol.
    """
    HANDLE_SIZE = 8
    ROTATE_OFFSET = 34  # constant on-screen px above the shape's center, pre-rotation

    def __init__(self, figure, kind, anchor, parent_plot, pen, brush=None, text=''):
        super().__init__()
        self.figure = figure
        self.kind = kind
        self.anchor = anchor          # 'figure' | 'border' | 'axes'
        self.parent_plot = parent_plot  # PlotItem or None (None only for 'figure')
        self.pen = pen
        self.brush = brush
        self.text = text
        # Offset from parent subplot's top-left, in scene px; only used for anchor=='border'.
        self.anchor_offset = QtCore.QPointF(0, 0)

        self._drag_start = None
        self._drag_origin = None
        self._end_drag_start_local = None
        self._start_drag_origin_pos = None
        self._start_drag_origin_p1 = None
        self._start_drag_p1_abs = None

        self.setZValue(800)
        self.setCursor(QtCore.Qt.SizeAllCursor)

        has_extent = kind in ('rect', 'ellipse', 'line', 'arrow', 'doublearrow', 'textarrow')
        # 'cursor' has no extent, but p1 is draggable: label offset from the data point.
        has_p1_handle = has_extent or kind == 'cursor'
        if has_extent:
            self.p1_local = QtCore.QPointF(self._px_to_local(60), self._px_to_local(40))
        elif kind == 'cursor':
            self.p1_local = QtCore.QPointF(self._px_to_local(60), self._px_to_local(-40))
        else:
            self.p1_local = None

        self._text_item = None
        if kind in ('text', 'textarrow'):
            self._text_item = QtWidgets.QGraphicsTextItem(self)
            self._text_item.setPlainText(text or SHAPE_LABELS[kind])
            self._text_item.setFont(QtWidgets.QApplication.font())
            self._text_item.setDefaultTextColor(pen.color())
            self._text_item.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            # Without this flag, an 'axes'-anchored text would be scaled/mirrored
            # by the ViewBox transform. It also cancels inherited ancestor
            # rotation (this item's own self.rotation()), so _apply_rotation
            # below re-applies rotation directly on the text item to keep it
            # turning together with the shape despite the flag.
            self._text_item.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            if kind == 'textarrow':
                self._text_item.setPos(self._px_to_local(8), self._px_to_local(-10))

        self._end_handle = None
        if has_p1_handle:
            self._end_handle = AnnotationHandle(
                self.HANDLE_SIZE, on_press=self._on_endpoint_press,
                on_move=self._on_endpoint_drag, on_release=self._on_endpoint_release,
            )
            self._end_handle.setParentItem(self)
            self._end_handle.setPos(self.p1_local)

        # TWO_ENDPOINT_KINDS get a second handle at p0 (this item's own
        # origin, always local (0,0) by this class's convention -- see
        # class docstring) instead of a rotate handle, so each end of the
        # shape can be dragged independently.
        self._start_handle = None
        if kind in TWO_ENDPOINT_KINDS:
            self._start_handle = AnnotationHandle(
                self.HANDLE_SIZE, on_press=self._on_start_press,
                on_move=self._on_start_drag, on_release=self._on_start_release,
            )
            self._start_handle.setParentItem(self)
            self._start_handle.setPos(0, 0)

        self._rotate_handle = None
        if kind not in NO_ROTATE_KINDS:
            self._rotate_handle = AnnotationHandle(
                self.HANDLE_SIZE, on_press=lambda pos: None,
                on_move=self._on_rotate_drag, on_release=lambda pos: None,
                brush_color=(90, 220, 120, 230), cursor=QtCore.Qt.PointingHandCursor,
                round_shape=True,
            )
            self._rotate_handle.setParentItem(self)
            self._position_rotate_handle()

        self.set_selected(False)

    # -- geometry ----------------------------------------------------
    def _px_to_local(self, px):
        """Convert a constant on-screen pixel length into this
        annotation's own local coordinate units. For 'figure'/'border'
        anchors, local units already ARE scene pixels, so this is a
        no-op. For 'axes' anchor, local units are DATA units (see the
        module docstring) -- a literal pixel constant like HANDLE_SIZE
        or the boundingRect padding would otherwise be wildly wrong
        (e.g. an "8px" handle rendered as 8 full data units), so it's
        scaled by the ViewBox's current data-per-pixel ratio instead,
        keeping chrome like handles/padding a constant screen size
        regardless of the subplot's data range or zoom level."""
        if self.anchor == 'axes' and self.parent_plot is not None:
            dx, dy = self.parent_plot.getViewBox().viewPixelSize()
            return px * (abs(dx) + abs(dy)) / 2
        return px

    def _shape_center_local(self):
        if self.kind == 'cursor':
            return QtCore.QPointF(0, 0)
        if self.p1_local is not None:
            return QtCore.QPointF(self.p1_local) / 2
        return QtCore.QPointF(0, 0)

    def _position_rotate_handle(self):
        center = self._shape_center_local()
        self.setTransformOriginPoint(center)
        self._rotate_handle.setPos(
            center.x(), center.y() - self._px_to_local(self.ROTATE_OFFSET),
        )

    def boundingRect(self):
        pad = self._px_to_local(20)
        if self.kind == 'cursor':
            end = self.p1_local if self.p1_local is not None else QtCore.QPointF(50, -30)
            rect = QtCore.QRectF(QtCore.QPointF(0, 0), end).normalized()
        elif self.p1_local is not None:
            rect = QtCore.QRectF(QtCore.QPointF(0, 0), self.p1_local).normalized()
        elif self._text_item is not None:
            # self._text_item has ItemIgnoresTransformations (see __init__),
            # so its own boundingRect() is in constant-screen-pixel units,
            # not this item's local units (data units for 'axes' anchor) --
            # convert its width/height before treating it as a rect in our
            # own coordinate space, or it renders wildly wrong-sized (only
            # its position, already in local units, needs no conversion).
            tb = self._text_item.boundingRect()
            size = QtCore.QSizeF(self._px_to_local(tb.width()), self._px_to_local(tb.height()))
            rect = QtCore.QRectF(self._text_item.pos(), size)
        else:
            rect = QtCore.QRectF(-pad, -pad, 2 * pad, 2 * pad)
        return rect.adjusted(-pad, -pad, pad, pad)

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen)
        p0 = QtCore.QPointF(0, 0)
        # _draw_arrowhead's own `size` default (10) is a literal pixel
        # length, wrong for 'axes' anchor's data-unit local space -- same
        # class of fix as _px_to_local elsewhere in this file.
        arrow_size = self._px_to_local(10)
        if self.kind == 'rect':
            painter.setBrush(self.brush or QtCore.Qt.NoBrush)
            painter.drawRect(QtCore.QRectF(p0, self.p1_local).normalized())
        elif self.kind == 'ellipse':
            painter.setBrush(self.brush or QtCore.Qt.NoBrush)
            painter.drawEllipse(QtCore.QRectF(p0, self.p1_local).normalized())
        elif self.kind == 'line':
            painter.drawLine(p0, self.p1_local)
        elif self.kind == 'arrow':
            painter.drawLine(p0, self.p1_local)
            painter.setBrush(QtGui.QBrush(self.pen.color()))
            _draw_arrowhead(painter, self.p1_local, p0, size=arrow_size)
        elif self.kind == 'doublearrow':
            painter.drawLine(p0, self.p1_local)
            painter.setBrush(QtGui.QBrush(self.pen.color()))
            _draw_arrowhead(painter, self.p1_local, p0, size=arrow_size)
            _draw_arrowhead(painter, p0, self.p1_local, size=arrow_size)
        elif self.kind == 'textarrow':
            painter.drawLine(p0, self.p1_local)
            painter.setBrush(QtGui.QBrush(self.pen.color()))
            _draw_arrowhead(painter, self.p1_local, p0, size=arrow_size)
        elif self.kind == 'cursor':
            painter.setBrush(QtGui.QBrush(self.pen.color()))
            marker_r = self._px_to_local(4)
            painter.drawEllipse(p0, marker_r, marker_r)
            label_pos = self.p1_local if self.p1_local is not None else QtCore.QPointF(50, -30)
            painter.drawLine(p0, label_pos)
            label = f"({self.text})" if self.text else ""
            if label:
                # Can't use ItemIgnoresTransformations here (raw QPainter draw) --
                # map to device pos and reset transform so text stays upright/constant-size.
                painter.save()
                device_pos = painter.transform().map(label_pos)
                painter.resetTransform()
                painter.setFont(QtWidgets.QApplication.font())
                metrics = QtGui.QFontMetricsF(painter.font())
                box = metrics.boundingRect(label).adjusted(-4, -2, 4, 2)
                box.moveCenter(device_pos)
                painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 220)))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRect(box)
                painter.setPen(self.pen)
                painter.drawText(box, QtCore.Qt.AlignCenter, label)
                painter.restore()
        # 'text' has nothing of its own to paint -- the child QGraphicsTextItem
        # does all the rendering.

        if self._selected:
            inset = self._px_to_local(4)
            outline_pen = pg.mkPen(filiation_color(self.parent_plot, self.figure.plots),
                                    width=2, style=QtCore.Qt.DashLine)
            outline_pen.setCosmetic(True)  # constant on-screen width/dash length, not data-scaled
            painter.setPen(outline_pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(inset, inset, -inset, -inset))

    # -- selection / handles ------------------------------------------
    def set_selected(self, selected):
        self._selected = selected
        for handle in (self._end_handle, self._rotate_handle, self._start_handle):
            if handle is not None:
                handle.setVisible(selected)
        self.update()

    # -- whole-body drag (native Qt overrides -- see CLAUDE.md) ----------
    def _parent_point(self, scene_pt):
        parent = self.parentItem()
        return parent.mapFromScene(scene_pt) if parent is not None else scene_pt

    def mousePressEvent(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            ev.ignore()
            return
        self.figure._select_annotation(self)
        self._drag_origin = self.pos()
        self._drag_start = self._parent_point(ev.scenePos())
        ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag_start is None:
            return
        cur = self._parent_point(ev.scenePos())
        self.setPos(self._drag_origin + (cur - self._drag_start))
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if self._drag_start is None:
            return
        self._drag_start = None
        origin, moved_to = self._drag_origin, self.pos()
        if moved_to != origin:
            self._push_move_history(origin, moved_to)
        ev.accept()

    def mouseDoubleClickEvent(self, ev):
        if self._text_item is not None:
            new_text, ok = QtWidgets.QInputDialog.getText(
                None, "Edit text", "Text:", QtWidgets.QLineEdit.Normal, self.text
            )
            if ok and new_text:
                old_text = self.text
                self._apply_text(new_text)
                self.figure._push_history(
                    undo_fn=lambda: self._apply_text(old_text),
                    redo_fn=lambda: self._apply_text(new_text),
                )
        ev.accept()

    def _apply_text(self, text):
        self.text = text
        if self._text_item is not None:
            self._text_item.setPlainText(text)

    def _push_move_history(self, origin, moved_to):
        def set_pos(pos):
            self.setPos(pos)
            if self.anchor == 'border' and self.parent_plot in self.figure.plots:
                self.anchor_offset = pos - self.parent_plot.sceneBoundingRect().topLeft()
        self.figure._push_history(
            undo_fn=lambda: set_pos(origin),
            redo_fn=lambda: set_pos(moved_to),
        )
        set_pos(moved_to)  # normalize anchor_offset for the move that just happened

    # -- end-point handle: resize / redefine extent -----------------------
    def _on_endpoint_press(self, scene_pos):
        self._end_drag_start_local = QtCore.QPointF(self.p1_local)

    def _on_endpoint_drag(self, scene_pos):
        self.prepareGeometryChange()
        self.p1_local = self.mapFromScene(scene_pos)
        if self._end_handle is not None:
            self._end_handle.setPos(self.p1_local)
        if self._rotate_handle is not None:
            self._position_rotate_handle()
        self.update()

    def _on_endpoint_release(self, scene_pos):
        old = self._end_drag_start_local
        new = QtCore.QPointF(self.p1_local)
        self._end_drag_start_local = None
        if old is None or old == new:
            return

        def set_p1(pt):
            self.prepareGeometryChange()
            self.p1_local = pt
            if self._end_handle is not None:
                self._end_handle.setPos(pt)
            if self._rotate_handle is not None:
                self._position_rotate_handle()
            self.update()

        self.figure._push_history(undo_fn=lambda: set_p1(old), redo_fn=lambda: set_p1(new))

    # -- start-point handle (TWO_ENDPOINT_KINDS only): drag p0 itself -----
    def _on_start_press(self, scene_pos):
        self._start_drag_origin_pos = QtCore.QPointF(self.pos())
        self._start_drag_origin_p1 = QtCore.QPointF(self.p1_local)
        # p1's location in the *parent* frame, fixed for the whole drag --
        # using mapToParent (not a plain delta) makes this correct even
        # when this item is rotated (rect/ellipse keep a rotate handle;
        # see NO_ROTATE_KINDS), since it goes through this item's actual
        # rotation/transformOriginPoint instead of assuming local==parent.
        self._start_drag_p1_abs = self.mapToParent(self.p1_local)

    def _on_start_drag(self, scene_pos):
        """Move this item's own origin (p0) to track the cursor directly
        (matching _on_endpoint_drag's own direct-snap style for p1), while
        keeping p1 fixed in the *parent* frame -- dragging p0 must not
        also drag p1 along with it, unlike whole-body drag. mapFromParent
        recomputes p1_local from the fixed parent-frame point using this
        item's *current* rotation/transformOriginPoint, so this stays
        correct even while rotated. (Like _on_endpoint_drag, moving
        transformOriginPoint after p1_local changes -- via
        _position_rotate_handle below -- can still cause the classic
        "resize-while-rotated jump"; see CLAUDE.md.)"""
        self.prepareGeometryChange()
        self.setPos(self._parent_point(scene_pos))
        self.p1_local = self.mapFromParent(self._start_drag_p1_abs)
        if self._end_handle is not None:
            self._end_handle.setPos(self.p1_local)
        if self._rotate_handle is not None:
            self._position_rotate_handle()
        self.update()

    def _on_start_release(self, scene_pos):
        old_pos, old_p1 = self._start_drag_origin_pos, self._start_drag_origin_p1
        new_pos, new_p1 = QtCore.QPointF(self.pos()), QtCore.QPointF(self.p1_local)
        self._start_drag_origin_pos = None
        self._start_drag_origin_p1 = None
        self._start_drag_p1_abs = None
        if old_pos == new_pos and old_p1 == new_p1:
            return

        def apply(pos, p1):
            self.prepareGeometryChange()
            self.setPos(pos)
            self.p1_local = p1
            if self.anchor == 'border' and self.parent_plot in self.figure.plots:
                self.anchor_offset = pos - self.parent_plot.sceneBoundingRect().topLeft()
            if self._end_handle is not None:
                self._end_handle.setPos(p1)
            if self._rotate_handle is not None:
                self._position_rotate_handle()
            self.update()

        self.figure._push_history(undo_fn=lambda: apply(old_pos, old_p1), redo_fn=lambda: apply(new_pos, new_p1))

    # -- rotate handle -----------------------------------------------
    def _on_rotate_drag(self, scene_pos):
        """Angle the shape so its "up" direction (the rotate handle's
        resting position, straight above center) points at the mouse.
        Both points are converted into the item's *parent* frame (fixed
        during the drag) before computing the angle, matching the
        approach used for whole-body drag above."""
        cursor = self._parent_point(scene_pos)
        center = self.mapToParent(self._shape_center_local())
        vec = cursor - center
        angle = math.degrees(math.atan2(vec.y(), vec.x())) + 90
        self._apply_rotation(angle)

    def _apply_rotation(self, angle):
        """Set this item's rotation, and keep the child text item (if any)
        turning with it. self._text_item has ItemIgnoresTransformations
        (see __init__) so it doesn't inherit this item's rotation the way
        a normal child would -- it must be told explicitly, which is fine
        because ItemIgnoresTransformations only cancels *inherited*
        ancestor transforms, not the item's own rotation/transform
        properties.

        For 'axes' anchor, `angle` lives in DATA space -- it was computed
        in _on_rotate_drag via _parent_point, i.e. relative to the
        ViewBox's own (data<->pixel) transform, which for a typical plot
        mirrors one axis (Y increases upward in data but downward on
        screen). The shape itself (painted directly under that same
        mirrored ancestor transform) rotates correctly on screen as a
        result, but the text item bypasses that ancestor transform
        entirely (that's the whole point of ItemIgnoresTransformations),
        so handing it the same raw angle spins it the opposite screen
        direction from the shape. _rotation_mirror_sign() detects that
        mirroring (empirically, not by assuming Y-is-always-inverted) and
        negates the angle to compensate."""
        self.setRotation(angle)
        if self._text_item is not None:
            self._text_item.setRotation(self._rotation_mirror_sign() * angle)

    def _rotation_mirror_sign(self):
        """+1 normally; -1 if this item's 'axes' ViewBox transform mirrors
        (an odd number of axis flips -- e.g. the default inverted-Y plot
        axis). Detected empirically by mapping two unit vectors through
        the ViewBox's own view<->scene mapping and checking whether their
        cross product flips sign, rather than relying on any specific
        pyqtgraph flag name/version."""
        if self.anchor != 'axes' or self.parent_plot is None:
            return 1
        vb = self.parent_plot.getViewBox()
        origin = vb.mapViewToScene(QtCore.QPointF(0, 0))
        vx = vb.mapViewToScene(QtCore.QPointF(1, 0)) - origin
        vy = vb.mapViewToScene(QtCore.QPointF(0, 1)) - origin
        cross = vx.x() * vy.y() - vx.y() * vy.x()
        return -1 if cross < 0 else 1

    # -- serialization (clipboard / subplot copy-paste) -------------------
    def to_dict(self):
        return {
            'kind': self.kind,
            'anchor': self.anchor,
            'pos': (self.pos().x(), self.pos().y()),
            'anchor_offset': (self.anchor_offset.x(), self.anchor_offset.y()),
            'p1_local': (self.p1_local.x(), self.p1_local.y()) if self.p1_local is not None else None,
            'text': self.text,
            'pen': _pen_to_tuple(self.pen),
            'brush': _brush_to_tuple(self.brush),
            'rotation': self.rotation(),
        }

    @classmethod
    def from_dict(cls, figure, parent_plot, data):
        """Rebuild an annotation from to_dict() output, re-parented onto
        `parent_plot` (used by paste_subplot -- the annotation may be
        landing in a different LaFigure window than it was copied
        from). anchor='figure' annotations are never included in a
        subplot's serialized dict in the first place (see
        LaFigure.copy_subplot), so parent_plot is always a real
        PlotItem here."""
        ann = cls(
            figure, data['kind'], data['anchor'], parent_plot,
            pen=_pen_from_tuple(data['pen']), brush=_brush_from_tuple(data['brush']),
            text=data.get('text', ''),
        )
        if data['p1_local'] is not None:
            ann.p1_local = QtCore.QPointF(*data['p1_local'])
            if ann._end_handle is not None:
                ann._end_handle.setPos(ann.p1_local)
        if ann._rotate_handle is not None:
            ann._position_rotate_handle()
        ann._apply_rotation(data.get('rotation', 0))
        ann.anchor_offset = QtCore.QPointF(*data['anchor_offset'])
        figure._add_annotation_to_scene(ann, QtCore.QPointF(*data['pos']))
        return ann

    # -- context menu (native override -- see CLAUDE.md) -------------------
    def contextMenuEvent(self, ev):
        self.figure._select_annotation(self)
        menu = QtWidgets.QMenu()
        menu.addAction("Properties...").triggered.connect(lambda: self.figure._edit_annotation_properties(self))
        if self.figure._relink_source is self:
            menu.addAction("Cancel Link").triggered.connect(self.figure._cancel_relink)
        else:
            menu.addAction("Link to...").triggered.connect(lambda: self.figure._start_relink(self))
        menu.addSeparator()
        menu.addAction("Delete").triggered.connect(lambda: self.figure.delete_annotation(self))
        menu.exec_(ev.screenPos())
        ev.accept()
