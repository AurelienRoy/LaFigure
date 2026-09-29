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
calls (setPos/mapFromScene) are identical either way. Anything meant to
look a certain way ON SCREEN -- rotation, outline/hit-test margins,
arrowheads, the textarrow label's offset -- is instead built in scene
space and mapped back (see the lafigure-axes-geometry skill), since an
'axes' anchor's data->pixel scale is rarely 1:1.

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

# Kinds whose selected-outline is a box oriented along p0->p1 (tight around
# the segment) instead of the axis-aligned box of the two endpoints, which
# wastes visible space once the segment isn't horizontal/vertical. 'cursor'
# joins these (2026-09-29): its p0->p1_local segment (marker -> label) is
# exactly the same shape, so the same scene-space math applies unchanged.
ORIENTED_OUTLINE_KINDS = ('line', 'arrow', 'doublearrow', 'textarrow', 'cursor')

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


def _snap_vector_angle(vec, step_deg=45):
    """`vec` rotated to the nearest multiple of `step_deg`, same length."""
    length = math.hypot(vec.x(), vec.y())
    if length == 0:
        return QtCore.QPointF(vec)
    step = math.radians(step_deg)
    angle = round(math.atan2(vec.y(), vec.x()) / step) * step
    return QtCore.QPointF(length * math.cos(angle), length * math.sin(angle))


def constrain_extent_vector(kind, vec, step_deg=45):
    """Shift-constrained version of a resize/placement vector (the offset
    from a shape's fixed point to the one being dragged), LibreOffice Draw
    style: 'rect'/'ellipse' become a square/circle (equal |dx|/|dy|,
    signs preserved), every other extent kind (line-like shapes, and
    'cursor's label line) snaps its angle to the nearest `step_deg`. Always
    called with `vec` in SCENE (screen-pixel) space, never local/data
    space, so the constraint looks the same on screen regardless of an
    annotation's anchor, subplot data scale, or own rotation -- matching
    how the analogous move-direction constraint (AnnotationItem.
    mouseMoveEvent) also works in scene space."""
    if kind in ('rect', 'ellipse'):
        dx, dy = vec.x(), vec.y()
        m = max(abs(dx), abs(dy))
        sx = 1 if dx >= 0 else -1
        sy = 1 if dy >= 0 else -1
        return QtCore.QPointF(sx * m, sy * m)
    return _snap_vector_angle(vec, step_deg)


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
    SHIFT_SNAP_DEG = 45  # LibreOffice-Draw-style constraint step while Shift is held
    # 'cursor' only: how far back toward p0 its end handle sits, as a
    # fraction of p1_local -- pulled off the exact label point (see
    # paint()'s cursor branch, which centers the text bubble there too),
    # so the opaque handle box doesn't mask the text.
    END_HANDLE_PULLBACK = 0.7

    def __init__(self, figure, kind, anchor, parent_plot, pen, brush=None, text='', point_ref=None):
        super().__init__()
        self._text_item = None
        self._rotate_handle = None
        # On-screen rotation in degrees (Qt's convention: clockwise, since
        # scene Y points down) -- see _update_rotation_transform for why
        # this is NOT QGraphicsItem.rotation(), which stays 0.
        self._angle = 0.0
        self._watched_vb = None  # the ancestor ViewBox whose zoom we follow, if any
        self.figure = figure
        self.kind = kind
        self.anchor = anchor          # 'figure' | 'border' | 'axes'
        self.parent_plot = parent_plot  # PlotItem or None (None only for 'figure')
        self.pen = pen
        self.brush = brush
        self.text = text
        # 'cursor' only: {'is_3d', 'curve_index', 'row'} -- which curve/
        # series entry this cursor is pinned to, resolved fresh (never a
        # live object reference, which would go stale across undo/redo --
        # see CLAUDE.md's staleness lesson) by annotation_ops.py's
        # _plot_data_items_for_ref. None for a free-floating cursor placed
        # with no curve under it, or any other shape kind.
        self.point_ref = point_ref
        # Offset from parent subplot's top-left, in scene px; only used for anchor=='border'.
        self.anchor_offset = QtCore.QPointF(0, 0)

        self._group_drag = None            # [(annotation, origin_pos, start_pt)] while dragging
        self._group_drag_origin_scene = None  # press point, for the Shift move constraint
        self._collapse_on_release = False
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

        if kind in ('text', 'textarrow'):
            self._text_item = QtWidgets.QGraphicsTextItem(self)
            self._text_item.setPlainText(text or SHAPE_LABELS[kind])
            self._text_item.setFont(QtWidgets.QApplication.font())
            self._text_item.setDefaultTextColor(pen.color())
            self._text_item.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            # Without this flag, an 'axes'-anchored text would be scaled/mirrored
            # by the ViewBox transform. It also cancels this item's own
            # rotation transform (see _update_rotation_transform), so
            # _apply_rotation re-applies the screen angle directly on the
            # text item to keep it turning together with the shape.
            self._text_item.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            self._layout_label()  # 'textarrow': beside p1 -- see _layout_label

        self._end_handle = None
        if has_p1_handle:
            self._end_handle = AnnotationHandle(
                self.HANDLE_SIZE, on_press=self._on_endpoint_press,
                on_move=lambda pos: self._on_endpoint_drag(pos, self._end_handle.modifiers),
                on_release=self._on_endpoint_release,
            )
            self._end_handle.setParentItem(self)
            self._end_handle.setPos(self._end_handle_pos())

        # TWO_ENDPOINT_KINDS get a second handle at p0 (this item's own
        # origin, always local (0,0) by this class's convention -- see
        # class docstring) instead of a rotate handle, so each end of the
        # shape can be dragged independently.
        self._start_handle = None
        if kind in TWO_ENDPOINT_KINDS:
            self._start_handle = AnnotationHandle(
                self.HANDLE_SIZE, on_press=self._on_start_press,
                on_move=lambda pos: self._on_start_drag(pos, self._start_handle.modifiers),
                on_release=self._on_start_release,
            )
            self._start_handle.setParentItem(self)
            self._start_handle.setPos(0, 0)

        if kind not in NO_ROTATE_KINDS:
            self._rotate_handle = AnnotationHandle(
                self.HANDLE_SIZE, on_press=lambda pos: None,
                on_move=lambda pos: self._on_rotate_drag(pos, self._rotate_handle.modifiers),
                on_release=lambda pos: None,
                brush_color=(90, 220, 120, 230), cursor=QtCore.Qt.PointingHandCursor,
                round_shape=True,
            )
            self._rotate_handle.setParentItem(self)
            self._position_rotate_handle()

        # 'cursor' only: a handle at p0 (its own origin) that re-picks
        # WHICH sample this cursor is pinned to, on the SAME curve/series
        # point_ref already names (never a different one -- confirmed with
        # the user via /lafigure-scope) -- unlike TWO_ENDPOINT_KINDS'
        # _start_handle, which moves p0 freely. p0 stays fixed exactly on
        # a curve value at all times; only WHICH value it names changes.
        self._anchor_handle = None
        self._anchor_drag_origin = None
        if kind == 'cursor':
            self._anchor_handle = AnnotationHandle(
                self.HANDLE_SIZE, on_press=self._on_anchor_press,
                on_move=self._on_anchor_drag, on_release=self._on_anchor_release,
                cursor=QtCore.Qt.PointingHandCursor,
            )
            self._anchor_handle.setParentItem(self)
            self._anchor_handle.setPos(0, 0)

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

    def _end_handle_pos(self):
        """Where the end-point drag handle sits: exactly at p1_local for
        every kind except 'cursor', which pulls it back toward p0 (see
        END_HANDLE_PULLBACK) so it doesn't sit on top of the label's own
        text bubble -- both would otherwise be centered on the same point."""
        if self.p1_local is None:
            return QtCore.QPointF(0, 0)
        if self.kind == 'cursor':
            return self.p1_local * self.END_HANDLE_PULLBACK
        return QtCore.QPointF(self.p1_local)

    @property
    def p1_local(self):
        return self._p1_local

    @p1_local.setter
    def p1_local(self, pt):
        """Every write of p1 (handle drags, undo/redo, from_dict, a direct
        assignment from _create_annotation) re-lays the 'textarrow' label
        out beside it, so no call site can forget to."""
        self.prepareGeometryChange()
        self._p1_local = pt
        self._layout_label()

    def _parent_linear(self):
        """The 2x2 linear part (a, b, c, d) of this item's parent -> scene
        map, as x' = a*x + c*y, y' = b*x + d*y (QTransform's m11/m12/m21/
        m22). Identity for 'figure'/'border' (the parent frame IS scene
        pixels); the ViewBox's data->pixel scale for 'axes', usually with
        Y mirrored and nowhere near 1:1."""
        parent = self.parentItem()
        t = parent.sceneTransform() if parent is not None else QtGui.QTransform()
        return t.m11(), t.m12(), t.m21(), t.m22()

    def _scene_vec_to_parent(self, vec):
        """A scene (screen-pixel) vector expressed in the parent frame --
        e.g. "34px straight up on screen" in data units, per axis."""
        a, b, c, d = self._parent_linear()
        det = a * d - c * b
        if det == 0:
            return QtCore.QPointF(vec)
        return QtCore.QPointF((d * vec.x() - c * vec.y()) / det, (-b * vec.x() + a * vec.y()) / det)

    def _position_rotate_handle(self):
        """Rest the rotate handle ROTATE_OFFSET screen px straight above the
        shape's center ON SCREEN (before rotation) -- converted into local
        units through the parent's real per-axis scale, not _px_to_local's
        averaged one, which on an 'axes' anchor with a mirrored Y put it
        below the center and at a data-scale-dependent distance. Also
        re-pivots the rotation on the (possibly moved) center."""
        self._update_rotation_transform()
        if self._rotate_handle is None:
            return
        center = self._shape_center_local()
        self._rotate_handle.setPos(center + self._scene_vec_to_parent(QtCore.QPointF(0, -self.ROTATE_OFFSET)))

    def _view_transform(self):
        """Scene -> viewport-pixel transform of the view showing this item
        (identity for LaFigure's own layout_widget, but read rather than
        assumed). ItemIgnoresTransformations children (the text item) and
        the cursor's QPainter-drawn label live in those device pixels."""
        scene = self.scene()
        views = scene.views() if scene is not None else []
        return views[0].viewportTransform() if views else QtGui.QTransform()

    def _text_scene_quad(self):
        """The text item's box as 4 scene points, rotation included.
        Its own boundingRect() is in device pixels (ItemIgnoresTransformations),
        so it's mapped through deviceTransform -- sceneTransform() is not
        meaningful for such an item -- and back out of the view transform."""
        vt = self._view_transform()
        dt = self._text_item.deviceTransform(vt)
        inv = vt.inverted()[0]
        r = self._text_item.boundingRect()
        return [inv.map(dt.map(pt)) for pt in (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]

    def _text_scene_rect(self):
        """Axis-aligned scene rect of the text item's box."""
        return QtGui.QPolygonF(self._text_scene_quad()).boundingRect()

    LABEL_GAP_PX = 6  # 'textarrow': screen px between the arrow tip and its label

    def _layout_label(self):
        """'textarrow' only: put the label BESIDE p1 (the arrowhead), on
        the side of the segment facing up on screen (right, for a vertical
        segment), LABEL_GAP_PX clear of the line -- at any angle, any
        anchor. Computed in scene space and mapped back (the text item
        draws in screen pixels, see the lafigure-axes-geometry skill);
        rerun whenever p0/p1 or the data->screen scale changes. It used to
        sit at a fixed (8, -10) local offset from p0, the tail."""
        if self.kind != 'textarrow' or self._text_item is None or self.p1_local is None:
            return
        p0 = self.mapToScene(QtCore.QPointF(0, 0))
        p1 = self.mapToScene(self.p1_local)
        vec = p1 - p0
        length = math.hypot(vec.x(), vec.y())
        ux, uy = (vec.x() / length, vec.y() / length) if length else (1.0, 0.0)
        nx, ny = -uy, ux
        if ny > 1e-9 or (abs(ny) <= 1e-9 and nx < 0):
            nx, ny = -nx, -ny
        tb = self._text_item.boundingRect()
        w, h = tb.width(), tb.height()
        # How far the box reaches toward the line from its own center.
        support = abs(nx) * w / 2 + abs(ny) * h / 2
        center = p1 + QtCore.QPointF(nx, ny) * (self.LABEL_GAP_PX + support)
        self._text_item.setPos(self.mapFromScene(center - QtCore.QPointF(w / 2, h / 2)))

    def _base_local_rect(self):
        """The drawn shape's own extent in local coordinates, no padding
        (None for a kind with nothing to measure)."""
        if self.kind == 'cursor':
            end = self.p1_local if self.p1_local is not None else QtCore.QPointF(50, -30)
            return QtCore.QRectF(QtCore.QPointF(0, 0), end).normalized()
        if self.p1_local is not None:
            return QtCore.QRectF(QtCore.QPointF(0, 0), self.p1_local).normalized()
        if self._text_item is not None:
            return QtGui.QPolygonF([self.mapFromScene(q) for q in self._text_scene_quad()]).boundingRect()
        return None

    def boundingRect(self):
        """The shape padded by 20px (handles and the dashed stroke need the
        room), and never smaller than shape() -- which reaches the text
        label/bubble -- or Qt's item index would skip hits on it."""
        pad = self._px_to_local(20)
        rect = self._base_local_rect()
        if rect is None:
            rect = QtCore.QRectF(-pad, -pad, 2 * pad, 2 * pad)
        return rect.adjusted(-pad, -pad, pad, pad).united(self.shape().boundingRect())

    def shape(self):
        """What Qt hit-tests a click against (QGraphicsItem.contains, scene
        item picking): the dashed selection outline itself, a few screen px
        around the drawn shape -- not the padded boundingRect(), which for
        every kind was a 20px axis-aligned box, far looser than what's
        drawn. See _outline_scene_polygons for the per-kind geometry."""
        return self._selection_outline_path()

    def contains(self, point):
        """shape(), also for an 'axes' annotation. Qt's own contains() --
        which scene item picking calls too -- tests clipPath() instead of
        shape() for any item under a clipping ancestor, and a ViewBox clips
        its children; clipPath() starts from boundingRect() and only
        intersects shape() when the item ITSELF has ItemClipsToShape. So
        without this, every 'axes' annotation kept the padded box."""
        if not self.shape().contains(point):
            return False
        return not self.isClipped() or self.clipPath().contains(point)

    def collidesWithPath(self, path, mode=QtCore.Qt.IntersectsItemShape):
        """Same fix as contains(), for the other half of Qt's hit-testing:
        a real mouse press picks its item with a 1x1 px rect through
        collidesWithPath(), whose default also swaps shape() for the
        boundingRect()-based clipPath() under a clipping ancestor."""
        if mode in (QtCore.Qt.IntersectsItemBoundingRect, QtCore.Qt.ContainsItemBoundingRect):
            return super().collidesWithPath(path, mode)
        shape = self.shape()
        if self.isClipped():
            shape = shape.intersected(self.clipPath())
        if mode == QtCore.Qt.ContainsItemShape:
            return path.contains(shape)
        return path.intersects(shape)

    def shape_scene_rect(self):
        """The shape's own extent in scene coordinates, without the
        boundingRect's handle padding -- what a rubber band must enclose."""
        rect = self._base_local_rect()
        if rect is None:
            return QtCore.QRectF(self.scenePos(), QtCore.QSizeF(0, 0))
        return self.mapRectToScene(rect)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(self.pen)
        p0 = QtCore.QPointF(0, 0)
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
            self._draw_arrowhead(painter, self.p1_local, p0)
        elif self.kind == 'doublearrow':
            painter.drawLine(p0, self.p1_local)
            painter.setBrush(QtGui.QBrush(self.pen.color()))
            self._draw_arrowhead(painter, self.p1_local, p0)
            self._draw_arrowhead(painter, p0, self.p1_local)
        elif self.kind == 'textarrow':
            painter.drawLine(p0, self.p1_local)
            painter.setBrush(QtGui.QBrush(self.pen.color()))
            self._draw_arrowhead(painter, self.p1_local, p0)
        elif self.kind == 'cursor':
            label_pos = self.p1_local if self.p1_local is not None else QtCore.QPointF(50, -30)
            painter.drawLine(p0, label_pos)
            # Can't use ItemIgnoresTransformations here (raw QPainter draw) --
            # map to device pos and reset transform so the marker stays a
            # round 4px dot (a local-space radius is an ellipse on a
            # non-1:1 'axes' subplot) and the text upright/constant-size.
            painter.save()
            marker_pos = painter.transform().map(p0)
            painter.resetTransform()
            painter.setBrush(QtGui.QBrush(self.pen.color()))
            painter.drawEllipse(marker_pos, self.CURSOR_MARKER_PX, self.CURSOR_MARKER_PX)
            painter.restore()
            label = self._cursor_label()
            if label:
                painter.save()
                device_pos = painter.transform().map(label_pos)
                painter.resetTransform()
                box = self._cursor_bubble_device_rect(label, device_pos)
                painter.setFont(QtWidgets.QApplication.font())
                painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 220)))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRect(box)
                painter.setPen(self.pen)
                painter.drawText(box, QtCore.Qt.AlignCenter, label)
                painter.restore()
        # 'text' has nothing of its own to paint -- the child QGraphicsTextItem
        # does all the rendering.

        if self._selected:
            outline_pen = pg.mkPen(filiation_color(self.parent_plot, self.figure.plots),
                                    width=2, style=QtCore.Qt.DashLine)
            outline_pen.setCosmetic(True)  # constant on-screen width/dash length, not data-scaled
            painter.setPen(outline_pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawPath(self._selection_outline_path())

    CURSOR_MARKER_PX = 4        # 'cursor': radius of the dot on the data point, screen px
    OUTLINE_END_PAD_PX = 4      # along the segment, past each end
    OUTLINE_PERP_PAD_PX = 6     # perpendicular to it -- 1.5x END_PAD, so the box reads clearly
    OUTLINE_PAD_PX = 4          # around a rect / ellipse / text box / label bubble
    ELLIPSE_OUTLINE_POINTS = 48

    def _cursor_label(self):
        return f"({self.text})" if self.text else ""

    @staticmethod
    def _cursor_bubble_device_rect(label, device_center):
        """The cursor label's white bubble, in device pixels -- shared by
        paint() and the hit-test so both agree on where it is."""
        metrics = QtGui.QFontMetricsF(QtWidgets.QApplication.font())
        box = metrics.boundingRect(label).adjusted(-4, -2, 4, 2)
        box.moveCenter(device_center)
        return box

    @staticmethod
    def _unit(vec, fallback):
        length = math.hypot(vec.x(), vec.y())
        return (QtCore.QPointF(vec.x() / length, vec.y() / length), length) if length else (fallback, 0.0)

    @classmethod
    def _quad_axes(cls, quad):
        """Unit vectors along a scene quad's c0->c1 and c0->c3 edges, and
        their lengths -- falling back to a perpendicular (or screen X/Y)
        when an edge is degenerate (a zero-width rect)."""
        c0, c1, _, c3 = quad
        u, lu = cls._unit(c1 - c0, None)
        v, lv = cls._unit(c3 - c0, None)
        if u is None and v is None:
            u, v = QtCore.QPointF(1, 0), QtCore.QPointF(0, 1)
        elif u is None:
            u = QtCore.QPointF(v.y(), -v.x())
        elif v is None:
            v = QtCore.QPointF(-u.y(), u.x())
        return u, lu, v, lv

    @classmethod
    def _pad_quad(cls, quad, pad):
        """A scene quad (c0, c1, c2, c3 around a rectangle) grown by `pad`
        screen px on every side, along its own edges (so a rotated
        rectangle stays that rectangle, just larger)."""
        u, _, v, _ = cls._quad_axes(quad)
        du, dv = u * pad, v * pad
        c0, c1, c2, c3 = quad
        return QtGui.QPolygonF([c0 - du - dv, c1 + du - dv, c2 + du + dv, c3 - du + dv])

    @classmethod
    def _padded_ellipse(cls, quad, pad, n):
        """The ellipse inscribed in a scene quad, with each semi-axis grown
        by `pad` screen px: a bounding ellipse, not a box."""
        u, lu, v, lv = cls._quad_axes(quad)
        center = (quad[0] + quad[2]) / 2
        a, b = lu / 2 + pad, lv / 2 + pad
        return QtGui.QPolygonF([
            center + u * (a * math.cos(t)) + v * (b * math.sin(t))
            for t in (2 * math.pi * i / n for i in range(n))
        ])

    def _outline_scene_polygons(self):
        """The dashed selection outline -- also the hit-test shape() -- as
        polygons in SCENE (screen-pixel) space, every margin a literal
        screen-pixel count, whatever the anchor or the subplot's X/Y data
        scale (see the lafigure-axes-geometry skill; a per-axis
        _px_to_local margin is wildly uneven on a non-1:1 'axes' subplot).
        The first polygon is the main one; 'textarrow'/'cursor' add their
        text label / bubble:
          - ORIENTED_OUTLINE_KINDS: a box hugging the p0->p1 segment;
          - 'rect': the drawn rect, OUTLINE_PAD_PX larger on each side;
          - 'ellipse': a bounding ellipse OUTLINE_PAD_PX larger;
          - 'text': the text box, padded the same."""
        pad = self.OUTLINE_PAD_PX
        polys = []
        if self.kind in ORIENTED_OUTLINE_KINDS and self.p1_local is not None:
            p0_scene = self.mapToScene(QtCore.QPointF(0, 0))
            p1_scene = self.mapToScene(self.p1_local)
            u, _ = self._unit(p1_scene - p0_scene, QtCore.QPointF(1, 0))
            along = u * self.OUTLINE_END_PAD_PX
            perp = QtCore.QPointF(-u.y(), u.x()) * self.OUTLINE_PERP_PAD_PX
            polys.append(QtGui.QPolygonF([
                p0_scene - along - perp, p0_scene - along + perp,
                p1_scene + along + perp, p1_scene + along - perp,
            ]))
            if self.kind == 'textarrow' and self._text_item is not None:
                polys.append(self._pad_quad(self._text_scene_quad(), pad))
            label = self._cursor_label() if self.kind == 'cursor' else ""
            if label:
                vt = self._view_transform()
                bubble = self._cursor_bubble_device_rect(label, vt.map(p1_scene))
                inv = vt.inverted()[0]
                polys.append(self._pad_quad(
                    [inv.map(pt) for pt in (bubble.topLeft(), bubble.topRight(),
                                            bubble.bottomRight(), bubble.bottomLeft())], pad))
        elif self.kind in ('rect', 'ellipse') and self.p1_local is not None:
            p1 = self.p1_local
            quad = [self.mapToScene(QtCore.QPointF(x, y))
                    for x, y in ((0, 0), (p1.x(), 0), (p1.x(), p1.y()), (0, p1.y()))]
            if self.kind == 'rect':
                polys.append(self._pad_quad(quad, pad))
            else:
                polys.append(self._padded_ellipse(quad, pad, self.ELLIPSE_OUTLINE_POINTS))
        elif self._text_item is not None:
            polys.append(self._pad_quad(self._text_scene_quad(), pad))
        else:
            o = self.mapToScene(QtCore.QPointF(0, 0))
            polys.append(QtGui.QPolygonF(QtCore.QRectF(o.x() - pad, o.y() - pad, 2 * pad, 2 * pad)))
        return polys

    def _selection_outline_polygon(self):
        """The main outline polygon (see _outline_scene_polygons) in local
        coordinates: 4 corners for a segment/rect/text box, many points for
        an ellipse. Built in scene space, then mapped back -- same reasoning
        as _draw_arrowhead's own docstring."""
        return QtGui.QPolygonF([self.mapFromScene(pt) for pt in self._outline_scene_polygons()[0]])

    def _selection_outline_path(self):
        """Every outline polygon, united, in local coordinates: what paint()
        strokes when selected, and what shape() returns."""
        path = QtGui.QPainterPath()
        for poly in self._outline_scene_polygons():
            sub = QtGui.QPainterPath()
            sub.addPolygon(QtGui.QPolygonF([self.mapFromScene(pt) for pt in poly]))
            sub.closeSubpath()
            path = sub if path.isEmpty() else path.united(sub)
        return path

    ARROWHEAD_PX = 10  # a literal on-screen pixel size -- see _draw_arrowhead

    def _draw_arrowhead(self, painter, tip, tail):
        """Draw a filled triangular arrowhead at `tip` (local coords),
        pointing away from `tail` -- shared by 'arrow' (one head) and
        'doublearrow' (two).

        Built in SCENE (screen-pixel) space, not local space: for an
        'axes'-anchored annotation, local units are DATA units, and a
        rotation computed and applied purely in data space is only
        shape-preserving on screen when the subplot's X/Y data-per-pixel
        ratio is 1:1 -- otherwise the triangle comes out visibly skewed
        (see CLAUDE.md). `tip` itself is kept exact (no scene round-trip)
        so the arrowhead stays attached exactly at the line's endpoint;
        only the two back corners go through the scene<->local mapping."""
        tip_scene = self.mapToScene(tip)
        tail_scene = self.mapToScene(tail)
        angle = math.atan2(tip_scene.y() - tail_scene.y(), tip_scene.x() - tail_scene.x())
        spread = math.pi / 7
        size = self.ARROWHEAD_PX
        p1_scene = tip_scene - QtCore.QPointF(size * math.cos(angle - spread), size * math.sin(angle - spread))
        p2_scene = tip_scene - QtCore.QPointF(size * math.cos(angle + spread), size * math.sin(angle + spread))
        poly = QtGui.QPolygonF([tip, self.mapFromScene(p1_scene), self.mapFromScene(p2_scene)])
        painter.drawPolygon(poly)

    # -- selection / handles ------------------------------------------
    def set_selected(self, selected):
        self._selected = selected
        for handle in (self._end_handle, self._rotate_handle, self._start_handle, self._anchor_handle):
            if handle is not None:
                handle.setVisible(selected)
        self.update()

    # -- anchor handle ('cursor' only): re-pick WHICH sample p0 names -----
    def _on_anchor_press(self, scene_pos):
        self._anchor_drag_origin = {
            'pos': QtCore.QPointF(self.pos()),
            'point_ref': dict(self.point_ref) if self.point_ref is not None else None,
            'text': self.text,
        }

    def _on_anchor_drag(self, scene_pos):
        if self.point_ref is None or self.parent_plot is None:
            return
        hit = self.figure._nearest_sample_on_ref(self.parent_plot, self.point_ref, scene_pos)
        if hit is None:
            return
        new_ref, local_pos, text = hit
        self.prepareGeometryChange()
        self.point_ref = new_ref
        self.setPos(local_pos)
        self.text = text
        self.update()

    def _on_anchor_release(self, scene_pos):
        old = self._anchor_drag_origin
        self._anchor_drag_origin = None
        if old is None or old['point_ref'] == self.point_ref:
            return  # never actually landed on a different sample
        new = {
            'pos': QtCore.QPointF(self.pos()),
            'point_ref': dict(self.point_ref) if self.point_ref is not None else None,
            'text': self.text,
        }

        def apply(state):
            self.prepareGeometryChange()
            self.point_ref = dict(state['point_ref']) if state['point_ref'] is not None else None
            self.setPos(state['pos'])
            self.text = state['text']
            self.update()

        self.figure._push_history(undo_fn=lambda: apply(old), redo_fn=lambda: apply(new))

    # -- whole-body drag (native Qt overrides -- see CLAUDE.md) ----------
    def _parent_point(self, scene_pt):
        parent = self.parentItem()
        return parent.mapFromScene(scene_pt) if parent is not None else scene_pt

    def _parent_to_scene(self, parent_pt):
        """Inverse of _parent_point: a point in this item's parent frame
        (data units for 'axes', scene pixels for 'figure'/'border') back
        into scene pixels -- used to constrain a resize vector in scene
        space (see constrain_extent_vector) starting from a parent-frame
        fixed point."""
        parent = self.parentItem()
        return parent.mapToScene(parent_pt) if parent is not None else parent_pt

    def mousePressEvent(self, ev):
        """LibreOffice Draw / MATLAB style: Shift toggles this annotation in
        or out of the selection; a plain press on an already-selected one
        keeps the group so it can be dragged together, and collapses to
        just this one on release if nothing moved.

        Outside Select mode there's nothing to select/drag -- Hand/Zoom
        Rect/Brush are all "no selection" modes (see CLAUDE.md), and a
        click there needs to fall through to the ViewBox instead (Zoom
        Rect's own click-to-zoom, Hand's pan-drag start, ...), not be
        eaten here just because an annotation happens to sit on top."""
        if ev.button() != QtCore.Qt.LeftButton or self.figure.interaction_mode != 'select':
            ev.ignore()
            return
        fig = self.figure
        additive = bool(ev.modifiers() & QtCore.Qt.ShiftModifier)
        self._collapse_on_release = False
        if additive:
            fig._select_annotation(self, additive=True)
        elif self in fig.selected_annotations:
            self._collapse_on_release = True
        else:
            fig._select_annotation(self)
        ev.accept()
        if self not in fig.selected_annotations:
            self._group_drag = None  # Shift just toggled it off: no drag
            return
        # Each member's own parent coordinates: members may sit in
        # different subplots (data units) or the figure (pixels).
        self._group_drag = [(a, a.pos(), a._parent_point(ev.scenePos()))
                            for a in fig.selected_annotations]
        self._group_drag_origin_scene = QtCore.QPointF(ev.scenePos())

    def mouseMoveEvent(self, ev):
        if self._group_drag is None:
            return
        scene_pos = ev.scenePos()
        if ev.modifiers() & QtCore.Qt.ShiftModifier:
            # Movement is constrained to a screen-relative 0/45/90...
            # direction -- unlike resize, this doesn't depend on any
            # member's kind, so it's the plain angle snap, not
            # constrain_extent_vector's square/circle branch.
            delta = _snap_vector_angle(scene_pos - self._group_drag_origin_scene, self.SHIFT_SNAP_DEG)
            scene_pos = self._group_drag_origin_scene + delta
        for a, origin, start in self._group_drag:
            a.setPos(origin + (a._parent_point(scene_pos) - start))
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if self._group_drag is None:
            return
        group, self._group_drag = self._group_drag, None
        moved = False
        with self.figure.undo_group():
            for a, origin, _ in group:
                if a.pos() != origin:
                    moved = True
                    a._push_move_history(origin, a.pos())
        if not moved and self._collapse_on_release:
            self.figure._select_annotation(self)
        if not moved and not (ev.modifiers() & QtCore.Qt.ShiftModifier):
            # A genuine click (not a drag) on this annotation -- give
            # click-cycling a chance to override the selection above, if
            # this landed on (about) the same spot as the previous plain
            # click (see selection_ui.py's _apply_click_cycle). Needed
            # here specifically because this is a NATIVE Qt override (see
            # CLAUDE.md): unlike a curve click or the empty-space/subplot
            # fallback, it fully consumes the event before pyqtgraph's own
            # sigMouseClicked -- and hence _on_scene_clicked's own tail
            # call to the same method -- ever gets a look at it.
            self.figure._apply_click_cycle(ev.scenePos())
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
        self.prepareGeometryChange()  # the label's size feeds shape()/boundingRect()
        self.text = text
        if self._text_item is not None:
            self._text_item.setPlainText(text)
        self._layout_label()

    def _push_move_history(self, origin, moved_to):
        def set_pos(pos):
            self.setPos(pos)
            if self.anchor == 'border' and self.parent_plot in self.figure.plots:
                self.anchor_offset = self.figure._box_fraction(self.parent_plot, pos)
        self.figure._push_history(
            undo_fn=lambda: set_pos(origin),
            redo_fn=lambda: set_pos(moved_to),
        )
        set_pos(moved_to)  # normalize anchor_offset for the move that just happened

    # -- end-point handle: resize / redefine extent -----------------------
    def _on_endpoint_press(self, scene_pos):
        self._end_drag_start_local = QtCore.QPointF(self.p1_local)

    def _on_endpoint_drag(self, scene_pos, modifiers=QtCore.Qt.NoModifier):
        self.prepareGeometryChange()
        if modifiers & QtCore.Qt.ShiftModifier:
            # p0 (this item's own origin) is the fixed point; constrain in
            # scene space -- see constrain_extent_vector's own docstring
            # for why scene space, not local space.
            origin_scene = self.mapToScene(QtCore.QPointF(0, 0))
            scene_pos = origin_scene + constrain_extent_vector(
                self.kind, scene_pos - origin_scene, self.SHIFT_SNAP_DEG)
        self.p1_local = self.mapFromScene(scene_pos)
        if self._end_handle is not None:
            self._end_handle.setPos(self._end_handle_pos())
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
                self._end_handle.setPos(self._end_handle_pos())
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

    def _on_start_drag(self, scene_pos, modifiers=QtCore.Qt.NoModifier):
        """Move this item's own origin (p0) to track the cursor directly
        (matching _on_endpoint_drag's own direct-snap style for p1), while
        keeping p1 fixed in the *parent* frame -- dragging p0 must not
        also drag p1 along with it, unlike whole-body drag. mapFromParent
        recomputes p1_local from the fixed parent-frame point using this
        item's *current* rotation/transformOriginPoint, so this stays
        correct even while rotated. (Like _on_endpoint_drag, moving
        transformOriginPoint after p1_local changes -- via
        _position_rotate_handle below -- can still cause the classic
        "resize-while-rotated jump"; see CLAUDE.md.)

        With Shift held, p1 (in scene space, via _parent_to_scene) is the
        fixed point the constraint anchors on; p0 is placed so the p0->p1
        vector matches the constraint, same scene-space approach as
        _on_endpoint_drag."""
        self.prepareGeometryChange()
        if modifiers & QtCore.Qt.ShiftModifier:
            p1_scene = self._parent_to_scene(self._start_drag_p1_abs)
            scene_pos = p1_scene + constrain_extent_vector(
                self.kind, scene_pos - p1_scene, self.SHIFT_SNAP_DEG)
        self.setPos(self._parent_point(scene_pos))
        self.p1_local = self.mapFromParent(self._start_drag_p1_abs)
        if self._end_handle is not None:
            self._end_handle.setPos(self._end_handle_pos())
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
                self.anchor_offset = self.figure._box_fraction(self.parent_plot, pos)
            if self._end_handle is not None:
                self._end_handle.setPos(self._end_handle_pos())
            if self._rotate_handle is not None:
                self._position_rotate_handle()
            self.update()

        self.figure._push_history(undo_fn=lambda: apply(old_pos, old_p1), redo_fn=lambda: apply(new_pos, new_p1))

    # -- rotate handle -----------------------------------------------
    def _on_rotate_drag(self, scene_pos, modifiers=QtCore.Qt.NoModifier):
        """Angle the shape so its "up" direction (the rotate handle's
        resting position, straight above center ON SCREEN) points at the
        mouse. Measured in SCENE space, so the angle -- and Shift's
        SHIFT_SNAP_DEG steps, LibreOffice-Draw style -- are what the user
        sees, whatever the anchor or the subplot's X/Y data scale. (It was
        measured in the parent frame: data units for 'axes', where "45
        degrees" means nothing on screen.)"""
        center = self.mapToScene(self._shape_center_local())
        vec = scene_pos - center
        angle = math.degrees(math.atan2(vec.y(), vec.x())) + 90
        if modifiers & QtCore.Qt.ShiftModifier:
            angle = round(angle / self.SHIFT_SNAP_DEG) * self.SHIFT_SNAP_DEG
        self._apply_rotation(angle)

    def screen_rotation(self):
        """The on-screen rotation in degrees (clockwise, Qt's convention).
        Use this, not QGraphicsItem.rotation(), which is always 0 -- see
        _update_rotation_transform."""
        return self._angle

    def _apply_rotation(self, angle):
        """Rotate the shape by `angle` degrees ON SCREEN, and the child text
        item (if any) with it. self._text_item has ItemIgnoresTransformations
        (see __init__), so it ignores this item's transform the way it
        ignores the ViewBox's -- it must be told explicitly, and since it
        draws in screen pixels, the screen angle is exactly right for it
        (no more mirror-sign correction for an inverted-Y axis)."""
        self._angle = float(angle)
        self._update_rotation_transform()
        if self._text_item is not None:
            self._text_item.setRotation(self._angle)
        self._layout_label()
        self.update()

    def _update_rotation_transform(self):
        """Apply self._angle as a rotation in SCREEN space, around the
        shape's center.

        QGraphicsItem.setRotation() rotates in the item's own local frame,
        which for an 'axes' anchor is DATA units: the ViewBox's per-axis
        data->pixel scale A is applied on top of it afterward, so a
        non-1:1 A turns the rotated rect into a skewed parallelogram at
        some other angle. Instead this sets the item's transform() to
        L = A^-1 R A (plus the translation keeping the center fixed): the
        full local->scene map then has linear part A L = R A, i.e. "draw
        the shape as usual, then rotate it by R on screen". For
        'figure'/'border' A is the identity and L is just R. Depends on A,
        so it's rebuilt on every zoom/resize of the watched ViewBox and on
        every reparent (see itemChange) -- rotation() itself stays 0."""
        if not self._angle:
            if not self.transform().isIdentity():
                self.setTransform(QtGui.QTransform())
            return
        a, b, c, d = self._parent_linear()
        det = a * d - c * b
        if det == 0:
            return  # a collapsed view (zero-size ViewBox): keep the last good transform
        th = math.radians(self._angle)
        cs, sn = math.cos(th), math.sin(th)
        # Column-vector form: A = [[a, c], [b, d]], R = [[cs, -sn], [sn, cs]].
        ra = ((cs * a - sn * b, cs * c - sn * d),
              (sn * a + cs * b, sn * c + cs * d))
        l00 = (d * ra[0][0] - c * ra[1][0]) / det
        l01 = (d * ra[0][1] - c * ra[1][1]) / det
        l10 = (-b * ra[0][0] + a * ra[1][0]) / det
        l11 = (-b * ra[0][1] + a * ra[1][1]) / det
        ctr = self._shape_center_local()
        tx = ctr.x() - (l00 * ctr.x() + l01 * ctr.y())
        ty = ctr.y() - (l10 * ctr.x() + l11 * ctr.y())
        self.setTransform(QtGui.QTransform(l00, l10, l01, l11, tx, ty))

    # -- following the parent's data->screen scale ('axes' anchor) ---------
    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemParentHasChanged:
            self._watch_view()
            self._refresh_screen_geometry()
        return super().itemChange(change, value)

    def _watch_view(self):
        """Follow the zoom/resize of the ViewBox this item now sits in (if
        any): everything built in screen space (rotation, rotate handle,
        textarrow label) depends on its data->pixel scale."""
        vb = self.parentItem()
        while vb is not None and not isinstance(vb, pg.ViewBox):
            vb = vb.parentItem()
        if vb is self._watched_vb:
            return
        if self._watched_vb is not None:
            try:
                self._watched_vb.sigTransformChanged.disconnect(self._on_view_transform_changed)
            except (TypeError, RuntimeError):
                pass
        self._watched_vb = vb
        if vb is not None:
            vb.sigTransformChanged.connect(self._on_view_transform_changed)

    def _on_view_transform_changed(self, *args):
        try:
            self._refresh_screen_geometry()
        except RuntimeError:
            pass  # the C++ item is already gone

    def _refresh_screen_geometry(self):
        self.prepareGeometryChange()
        self._position_rotate_handle()  # also rebuilds the rotation transform
        self._layout_label()
        self.update()

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
            'rotation': self._angle,  # on-screen degrees -- see screen_rotation()
            'point_ref': dict(self.point_ref) if self.point_ref is not None else None,
        }

    @classmethod
    def from_dict(cls, figure, parent_plot, data):
        """Rebuild an annotation from to_dict() output, re-parented onto
        `parent_plot` (used by paste_subplot -- the annotation may be
        landing in a different LaFigure window than it was copied
        from). anchor='figure' annotations are never included in a
        subplot's serialized dict in the first place (see
        LaFigure.copy_subplot), so parent_plot is always a real
        PlotItem here. A carried-over point_ref's curve_index is resolved
        fresh against `parent_plot`'s CURRENT curve list on the next
        refresh_point(), so it still points at the right curve after a
        cross-figure paste as long as that figure's curves are in the same
        order (paste_subplot rebuilds them in their original order)."""
        ann = cls(
            figure, data['kind'], data['anchor'], parent_plot,
            pen=_pen_from_tuple(data['pen']), brush=_brush_from_tuple(data['brush']),
            text=data.get('text', ''), point_ref=data.get('point_ref'),
        )
        if data['p1_local'] is not None:
            ann.p1_local = QtCore.QPointF(*data['p1_local'])
            if ann._end_handle is not None:
                ann._end_handle.setPos(ann._end_handle_pos())
        if ann._rotate_handle is not None:
            ann._position_rotate_handle()
        ann._apply_rotation(data.get('rotation', 0))
        ann.anchor_offset = QtCore.QPointF(*data['anchor_offset'])
        figure._add_annotation_to_scene(ann, QtCore.QPointF(*data['pos']))
        return ann

    # -- live point tracking (self.kind == 'cursor' only) ------------------
    def refresh_point(self):
        """Re-derive this cursor's position and label from point_ref
        against the CURRENT data -- never a value frozen at placement
        time. Resolves via the referenced curve/series' full data (not
        just what it's currently drawing), so a hide/show cycle doesn't
        disturb it; only annotation_ops.py's/brushing.py's own delete path
        removes the annotation outright, precisely when its own row is
        removed from that curve (see brushing.delete_brushed_points).

        Safe to call whenever -- best-effort: if the reference can't be
        resolved at all (curve gone, index out of range), it just leaves
        the annotation where it last was rather than raising. Returns
        whether it resolved.

        For an 'axes'-anchored cursor on a 3D cell, self.pos() is set to
        the item's current PROJECTED screen pixel (View3DBox.projected),
        not a data-space point -- 'axes' anchor on a 3D cell already lives
        in the rendered image's own pixel space (see view3d.py's module
        docstring), so this is what makes the cursor follow the camera on
        orbit/pan/dolly: View3DBox.render_now calls this after every
        render, i.e. after every camera move."""
        ref = self.point_ref
        if ref is None or self.parent_plot is None or self.figure is None:
            return True
        item = self.figure._cursor_ref_item(self.parent_plot, ref)
        if item is None:
            return False
        series = self.figure._series_of(item)
        array_idx = self.figure._cursor_ref_array_index(series, item, ref)
        if array_idx is None:
            return False
        is_3d = bool(ref.get('is_3d'))
        if is_3d:
            xyz = item.positions()
            if array_idx >= len(xyz):
                return False
            x, y, z = (float(v) for v in xyz[array_idx])
            vb = self.parent_plot.getViewBox()
            sx, sy, front = vb.projected(item)
            if array_idx >= len(sx) or not bool(front[array_idx]):
                return False
            self.prepareGeometryChange()
            self.setPos(QtCore.QPointF(float(sx[array_idx]), float(sy[array_idx])))
        else:
            x_arr, y_arr = item.xData, item.yData
            if x_arr is None or array_idx >= len(x_arr):
                return False
            x, y, z = float(x_arr[array_idx]), float(y_arr[array_idx]), None
            self.prepareGeometryChange()
            self.setPos(QtCore.QPointF(x, y))
        from .console import datatip_text
        self.text = datatip_text(self.figure, self.parent_plot, item, array_idx, x, y, z=z)
        self.update()
        return True

    # -- context menu (native override -- see CLAUDE.md) -------------------
    def contextMenuEvent(self, ev):
        if self not in self.figure.selected_annotations:  # right-click inside the selection keeps it
            self.figure._select_annotation(self)
        menu = QtWidgets.QMenu()
        menu.addAction("Copy Annotation").triggered.connect(lambda: self.figure.copy_annotation())
        paste_action = menu.addAction("Paste Annotation")
        paste_action.setEnabled(bool(self.figure.clipboard.annotation))
        paste_action.triggered.connect(lambda: self.figure.paste_annotation())
        menu.addSeparator()
        menu.addAction("Properties...").triggered.connect(lambda: self.figure._edit_annotation_properties(self))
        if self.figure._relink_source is self:
            menu.addAction("Cancel Link").triggered.connect(self.figure._cancel_relink)
        else:
            menu.addAction("Link to...").triggered.connect(lambda: self.figure._start_relink(self))
            if self.anchor == 'figure':
                # Unlinked: offer a direct shortcut for every subplot its
                # own (un-rotated) bounding box currently overlaps, instead
                # of always requiring the click-to-choose gesture above.
                for p in self.figure._subplots_under_annotation(self):
                    name = self.figure.subplot_name(p) or "(untitled)"
                    menu.addAction(f"Link to subplot {name}").triggered.connect(
                        lambda checked=False, p=p: self.figure._link_annotation_to_subplot(self, p)
                    )
        menu.addSeparator()
        menu.addAction("Delete").triggered.connect(lambda: self.figure.delete_annotation(self))
        menu.exec_(ev.screenPos())
        ev.accept()
