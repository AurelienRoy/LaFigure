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

"""Annotation glue on the figure side: placement (including the scene
eventFilter), creation/deletion, scene bookkeeping per anchor kind,
Properties..., and reparenting ("Link to..."). The shapes themselves are
in annotations.py.
"""
import logging

import numpy as np
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .annotations import (AnnotationItem, TWO_CLICK_KINDS, ARROW_HEAD_KINDS, STROKE_KINDS,
                          constrain_extent_vector)
from .console import datatip_text
from .curve_style import LINE_STYLES
from .arrow_style import ArrowStyleDialog, default_head_style

logger = logging.getLogger('lafigure.annotation_ops')


class AnnotationOpsMixin:
    def _refresh_annotation_chrome(self, plot_item):
        """An 'axes'-anchored annotation's constant-pixel chrome (handle
        size, arrowhead size, dashed outline, ...) is either a) Qt-flag-
        based (AnnotationHandle's ItemIgnoresTransformations) or b)
        recomputed live inside paint()/boundingRect() every repaint (see
        AnnotationItem._px_to_local) -- both self-correct automatically as
        the subplot is panned/zoomed, no wiring needed. The one exception
        is the rotate handle's offset above the shape's center: that's a
        *position*, baked into a one-off setPos() call by
        _position_rotate_handle, which only runs when the annotation's own
        geometry changes, not on a bare view pan/zoom. Without this, a
        'text' annotation's rotate handle (the only kind that still has
        one -- see TWO_ENDPOINT_KINDS) would drift the wrong constant-pixel
        distance from the text after zooming without touching it."""
        for a in self._annotations_on(plot_item):
            if a.anchor == 'axes' and a._rotate_handle is not None:
                a._position_rotate_handle()

    # -- annotations -------------------------------------------------
    # Placement arms self._placing_kind, then the next scene interaction
    # creates the annotation instead of selecting a subplot/curve. The
    # 'text' point kind places on a single click, handled by
    # _handle_placement_click via _on_scene_clicked's sigMouseClicked.
    # ('cursor' used to place this same way too; it's now Data Cursor
    # mode's own click-to-move/add gesture, never self._placing_kind --
    # see _handle_cursor_mode_click.)
    # Extent kinds (TWO_CLICK_KINDS) place via a single press-drag-release
    # gesture instead: sigMouseClicked only fires for a genuine "click" (a
    # release near the press point within pyqtgraph's own click-vs-drag
    # threshold), so a real click-and-drag never reaches it at all -- hence
    # raw GraphicsSceneMousePress/Move/Release events are intercepted
    # directly via an event filter on the shared scene (see eventFilter
    # below and _placing_state).
    #
    # pos()/p1_local are in the anchor's coordinate space: scene pixels for
    # 'figure'/'border', data units for 'axes'. _add_annotation_to_scene /
    # _detach_/_reattach_annotation funnel all anchor-dependent bookkeeping
    # through one place.

    def _annotations_on(self, plot_item):
        return [a for a in self.annotations if a.parent_plot is plot_item and a.anchor in ('border', 'axes')]

    def _set_placing_cursor(self, on):
        """Push/pop the crosshair override cursor used while placing an
        annotation or relinking one. Checks Qt's own override-cursor stack
        (QApplication.overrideCursor()) rather than a hand-tracked flag, and
        pops in a loop when turning off -- self-healing against any missed
        push/pop pairing elsewhere (e.g. an exception, or a modal dialog
        popped up mid-placement) instead of silently leaving the crosshair
        stuck once the mismatch happens."""
        if on:
            if QtWidgets.QApplication.overrideCursor() is None:
                QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))
        else:
            while QtWidgets.QApplication.overrideCursor() is not None:
                QtWidgets.QApplication.restoreOverrideCursor()

    def start_placing_annotation(self, kind):
        self._cancel_relink()
        self._deselect_all()
        self._placing_kind = kind
        self._placing_state = None
        self._set_placing_cursor(True)
        logger.debug("annotation placement armed: kind=%s", kind)

    def _cancel_placing(self):
        """Clears any in-progress placement. This is the one method every
        cancellation path (the Esc shortcut in toolbar.py, a failed 3D
        cursor hit-test, starting a relink while a placement is pending)
        calls directly -- but it's ALSO called, as plain cleanup, right
        after every successful placement (see _handle_placement_click/
        eventFilter below). Those success sites null self._placing_kind
        themselves just before calling this, specifically so the log line
        below only fires for a real cancellation, never for the cleanup
        after a completed gesture."""
        if self._placing_kind is not None:
            logger.debug("annotation placement cancelled: kind=%s", self._placing_kind)
        self._placing_kind = None
        self._placing_state = None
        self._set_placing_cursor(False)

    def _annotation_zone(self, scene_pos):
        """Which parent a click at `scene_pos` implies: a subplot's data
        area (axes-anchored), a subplot's chrome/margins (border-anchored),
        or nowhere in particular (figure-anchored, free-floating)."""
        for p in self._plots_by_z():
            if p.getViewBox().sceneBoundingRect().contains(scene_pos):
                return 'axes', p
        for p in self._plots_by_z():
            if p.sceneBoundingRect().contains(scene_pos):
                return 'border', p
        return 'figure', None

    # -- data-cursor point references ('cursor' annotations only) ----------
    # A cursor's point_ref is {'is_3d', 'curve_index', 'row'}: 'curve_index'
    # is resolved fresh, every time, against the CURRENT curve/series list
    # of its parent_plot (never a live object reference held across undo/
    # redo, which would go stale -- see CLAUDE.md's staleness lesson on
    # this exact pattern for a curve). 'row' is a DataSource row id for a
    # source-backed series (stable across a delete elsewhere/hide/paste --
    # see the data model docs), or a plain array index for a private
    # series (which has no stable id at all; an unrelated delete on that
    # same series can shift it -- a known, inherent limit of a plain-array
    # series, not something a cursor reference can fix).
    def _plot_data_items_for_ref(self, parent_plot, is_3d):
        """The ordered list curve_index indexes into: PlotDataItems for a
        2D subplot, Series3DItems for a 3D one."""
        if is_3d:
            vb = parent_plot.getViewBox()
            return list(getattr(vb, '_series_items', []))
        return [c for c in parent_plot.listDataItems() if isinstance(c, pg.PlotDataItem)]

    @staticmethod
    def _row_id(series, array_idx):
        """The stable id to store in a point_ref for entry `array_idx` of
        `series`'s current data: its DataSource row if it has one, else
        the array index itself (see the class of helpers' own docstring)."""
        if series is not None and series.rows is not None:
            return int(series.rows[array_idx])
        return int(array_idx)

    def _cursor_ref_item(self, parent_plot, point_ref):
        """The curve/series `point_ref['curve_index']` currently names on
        `parent_plot`, or None if it's out of range (that curve is gone)."""
        items = self._plot_data_items_for_ref(parent_plot, bool(point_ref.get('is_3d')))
        idx = point_ref['curve_index']
        return items[idx] if 0 <= idx < len(items) else None

    @staticmethod
    def _cursor_ref_array_index(series, item, point_ref):
        """Where point_ref['row'] currently sits in `item`'s own data --
        re-searched every time (never cached), since a source-backed
        series' displayed rows can be reordered/narrowed (e.g. by Delete
        Selected Points) out from under a stale array index. None if that
        row isn't (or is no longer) part of what this series draws."""
        row_id = point_ref['row']
        if series is not None and series.rows is not None:
            pos = np.nonzero(np.asarray(series.rows) == row_id)[0]
            return int(pos[0]) if pos.size else None
        is_3d = bool(point_ref.get('is_3d'))
        n = len(item.positions()) if is_3d else (0 if item.xData is None else len(item.xData))
        return row_id if 0 <= row_id < n else None

    def _nearest_3d_point(self, parent_plot, scene_pos):
        """The closest entry, across every Series3DItem on this 3D cell, to
        a click at `scene_pos` -- in the cell's own projected screen space
        (View3DBox.projected, the same cached per-camera-state projection
        brushing uses), since a 3D click can't be compared to data-space
        curve samples the way a 2D click is. Returns (item, array_index,
        (x, y, z), local_pos) or None if the cell has no visible points;
        `local_pos` is the item's current projected pixel, in this
        ViewBox's own local (pinned-pixel) coordinate space -- what
        _create_annotation's `p0` expects for anchor='axes' here (see
        view3d.py's module docstring: 'axes' anchor on a 3D cell already
        lives in the rendered image's own pixel space)."""
        vb = parent_plot.getViewBox()
        click = vb.mapSceneToView(scene_pos)
        best = None
        for item in list(getattr(vb, '_series_items', [])):
            sx, sy, front = vb.projected(item)
            if len(sx) == 0:
                continue
            d2 = np.where(front, (sx - click.x()) ** 2 + (sy - click.y()) ** 2, np.inf)
            row = int(np.argmin(d2))
            if not np.isfinite(d2[row]):
                continue
            if best is None or d2[row] < best[0]:
                xyz = item.positions()[row]
                best = (d2[row], item, row,
                        (float(xyz[0]), float(xyz[1]), float(xyz[2])),
                        QtCore.QPointF(float(sx[row]), float(sy[row])))
        if best is None:
            return None
        _, item, row, xyz, local_pos = best
        return item, row, xyz, local_pos

    def _nearest_point_across_curves(self, parent_plot, scene_pos, exclude_item=None):
        """The (item, array_index, x, y) whose sample is closest, in real
        on-screen pixels, to scene_pos -- across every plottable 2D curve
        on parent_plot (never the downsampled display: full xData/yData).
        Each curve's own candidate sample is its nearest-X point (matching
        _nearest_sample_on_ref's existing same-curve convention below), so
        this only adds cross-curve comparison on top, not a different
        per-curve metric; candidates are then ranked by true 2-D scene
        distance (via mapViewToScene), not by X alone, since two curves
        can sit at very different Y -- see the lafigure-axes-geometry
        skill on not comparing raw data-space distances across curves
        with different units/scales. `exclude_item`: skip one curve (Alt-
        drag reassignment, which must land on a DIFFERENT curve than the
        one currently referenced). None if parent_plot has no data."""
        vb = parent_plot.getViewBox()
        data_pos = vb.mapSceneToView(scene_pos)
        best = None
        for item in parent_plot.listDataItems():
            if not isinstance(item, pg.PlotDataItem) or not item.isVisible() or item is exclude_item:
                continue
            x_arr, y_arr = item.xData, item.yData
            if x_arr is None or not len(x_arr):
                continue
            idx = int(np.argmin(np.abs(np.asarray(x_arr) - data_pos.x())))
            x, y = float(x_arr[idx]), float(y_arr[idx])
            scene_pt = vb.mapViewToScene(QtCore.QPointF(x, y))
            d2 = (scene_pt.x() - scene_pos.x()) ** 2 + (scene_pt.y() - scene_pos.y()) ** 2
            if best is None or d2 < best[0]:
                best = (d2, item, idx, x, y)
        if best is None:
            return None
        _, item, idx, x, y = best
        return item, idx, x, y

    def _cursor_hit_at(self, parent_plot, scene_pos, exclude_item=None):
        """(point_ref, local_pos, text) for the nearest curve/series sample
        to scene_pos on parent_plot -- 2D via _nearest_point_across_curves
        (every curve), 3D via _nearest_3d_point (already cross-curve,
        `exclude_item` not supported there -- Alt-reassign is a 2D-only
        gesture, see AnnotationItem._on_anchor_drag). None if parent_plot
        has no plottable data. Shared by Data Cursor mode's click-to-
        move/add gesture (_handle_cursor_mode_click) and the right-click
        'Add New Datacursor' action (_add_datacursor_near)."""
        if getattr(parent_plot, 'axes_type', 'cartesian') == '3d':
            hit = self._nearest_3d_point(parent_plot, scene_pos)
            if hit is None:
                return None
            item, array_idx, (x, y, z), local_pos = hit
            series = self._series_of(item)
            items = self._plot_data_items_for_ref(parent_plot, True)
            point_ref = {'is_3d': True, 'curve_index': items.index(item),
                         'row': self._row_id(series, array_idx)}
            text = datatip_text(self, parent_plot, item, array_idx, x, y, z=z)
            return point_ref, local_pos, text
        hit = self._nearest_point_across_curves(parent_plot, scene_pos, exclude_item=exclude_item)
        if hit is None:
            return None
        item, array_idx, x, y = hit
        series = self._series_of(item)
        items = self._plot_data_items_for_ref(parent_plot, False)
        point_ref = {'is_3d': False, 'curve_index': items.index(item),
                     'row': self._row_id(series, array_idx)}
        text = datatip_text(self, parent_plot, item, array_idx, x, y)
        return point_ref, QtCore.QPointF(x, y), text

    # -- Data Cursor mode: click-to-move/add, and the per-subplot "last
    # datacursor" tracking a plain click acts on (confirmed with the user
    # via /lafigure-scope: per-subplot, not one figure-wide pointer; a
    # plain click in a subplot with no datacursor yet creates one, same as
    # Shift) -----------------------------------------------------------
    def _move_cursor_annotation(self, ann, new_point_ref, new_local_pos, new_text):
        """Move an existing datacursor to a freshly hit-tested point, as
        one undo entry -- same apply-closure shape as AnnotationItem.
        _on_anchor_release, just driven from the figure side (Data Cursor
        mode's click, not a handle drag) and not restricted to the same
        curve."""
        old = {'pos': QtCore.QPointF(ann.pos()),
               'point_ref': dict(ann.point_ref) if ann.point_ref is not None else None,
               'text': ann.text}
        new = {'pos': QtCore.QPointF(new_local_pos), 'point_ref': dict(new_point_ref), 'text': new_text}
        if old['pos'] == new['pos'] and old['point_ref'] == new['point_ref']:
            return  # clicked back onto the same nearest sample -- nothing to push

        def apply(state):
            ann.prepareGeometryChange()
            ann.point_ref = dict(state['point_ref']) if state['point_ref'] is not None else None
            ann.setPos(state['pos'])
            ann.text = state['text']
            ann.update()

        apply(new)
        self._push_history(undo_fn=lambda: apply(old), redo_fn=lambda: apply(new))

    def _handle_cursor_mode_click(self, parent_plot, scene_pos, additive=False):
        """Data Cursor mode (toolbar), a left click inside parent_plot's
        data area: plain click moves this subplot's last datacursor to
        the nearest curve point; Shift always adds a new one instead. A
        plain click in a subplot with no datacursor yet creates one (the
        same as Shift), since there's nothing to move."""
        hit = self._cursor_hit_at(parent_plot, scene_pos)
        if hit is None:
            return
        point_ref, local_pos, text = hit
        existing = self._last_cursor_by_plot.get(parent_plot)
        if not additive and existing is not None and existing in self.annotations:
            logger.debug("cursor mode: moved datacursor on subplot")
            self._move_cursor_annotation(existing, point_ref, local_pos, text)
        else:
            logger.debug("cursor mode: added new datacursor on subplot")
            self._create_annotation('cursor', 'axes', parent_plot, local_pos, None,
                                     text=text, point_ref=point_ref)

    def _add_datacursor_near(self, ann):
        """Right-click 'Add New Datacursor' (kind == 'cursor' only): a new
        datacursor near this one, ANNOTATION_PASTE_OFFSET_PX scene pixels
        away (same convention as Paste Annotation) -- snapped to the
        nearest real sample there, not a frozen offset copy, so its
        point_ref/position never drift out of sync (see
        AnnotationItem.refresh_point)."""
        parent_plot = ann.parent_plot
        if parent_plot is None:
            return
        marker_scene = ann.mapToScene(QtCore.QPointF(0, 0))
        probe = marker_scene + QtCore.QPointF(self.ANNOTATION_PASTE_OFFSET_PX, self.ANNOTATION_PASTE_OFFSET_PX)
        hit = self._cursor_hit_at(parent_plot, probe)
        if hit is None:
            return
        point_ref, local_pos, text = hit
        self._create_annotation('cursor', 'axes', parent_plot, local_pos, None,
                                 text=text, point_ref=point_ref)

    def _nearest_sample_on_ref(self, parent_plot, point_ref, scene_pos):
        """While dragging a datacursor's round marker with no modifier held
        (annotations.py's AnnotationItem, kind == 'cursor', native
        mousePressEvent/mouseMoveEvent hit-testing -- no handle object):
        the nearest sample to a live drag position, on THE SAME curve/
        series point_ref already names -- never a different one, unless
        Alt is held (see _nearest_sample_switch_curve below). Returns
        (new_point_ref, local_pos, text) or None if that curve is gone."""
        item = self._cursor_ref_item(parent_plot, point_ref)
        if item is None:
            return None
        series = self._series_of(item)
        is_3d = bool(point_ref.get('is_3d'))
        if is_3d:
            vb = parent_plot.getViewBox()
            click = vb.mapSceneToView(scene_pos)
            sx, sy, front = vb.projected(item)
            if len(sx) == 0:
                return None
            d2 = np.where(front, (sx - click.x()) ** 2 + (sy - click.y()) ** 2, np.inf)
            row = int(np.argmin(d2))
            if not np.isfinite(d2[row]):
                return None
            xyz = item.positions()[row]
            new_ref = dict(point_ref, row=self._row_id(series, row))
            local_pos = QtCore.QPointF(float(sx[row]), float(sy[row]))
            text = datatip_text(self, parent_plot, item, row,
                                 float(xyz[0]), float(xyz[1]), z=float(xyz[2]))
            return new_ref, local_pos, text
        x_arr, y_arr = item.xData, item.yData
        if x_arr is None or not len(x_arr):
            return None
        data_pos = parent_plot.getViewBox().mapSceneToView(scene_pos)
        row = int(np.argmin(np.abs(np.asarray(x_arr) - data_pos.x())))
        new_ref = dict(point_ref, row=self._row_id(series, row))
        local_pos = QtCore.QPointF(float(x_arr[row]), float(y_arr[row]))
        text = datatip_text(self, parent_plot, item, row, float(x_arr[row]), float(y_arr[row]))
        return new_ref, local_pos, text

    def _nearest_sample_switch_curve(self, parent_plot, point_ref, scene_pos):
        """Alt-held marker drag (kind == 'cursor' only): re-pick the
        nearest sample to scene_pos on the nearest OTHER curve -- i.e. the
        same cross-curve search _cursor_hit_at does, excluding the curve
        point_ref currently names, so Alt always lands on a different
        curve rather than snapping right back. 2D only (3D has no
        Alt-reassign gesture -- a 3D cell's own camera-projection search,
        _nearest_3d_point, is already cross-curve with no 'current curve'
        concept to exclude). Returns (new_point_ref, local_pos, text) or
        None if no other curve has data."""
        if getattr(parent_plot, 'axes_type', 'cartesian') == '3d':
            return None
        current_item = self._cursor_ref_item(parent_plot, point_ref)
        return self._cursor_hit_at(parent_plot, scene_pos, exclude_item=current_item)

    def _annotation_at(self, scene_pos):
        """The topmost annotation whose shape contains scene_pos, or None.
        Mirrors _curve_at's role (menus.py) for annotations: an
        AnnotationItem's own contextMenuEvent (annotations.py, a native
        Qt event) fires independently of pyqtgraph's own right-click
        dispatch (ViewBox.raiseContextMenu / the scene's sigMouseClicked
        empty-space handling) -- two unrelated delivery mechanisms that
        both fire for the same right-click. Callers use this to skip
        their own menu when an annotation is about to show its own."""
        for a in sorted(self.annotations, key=lambda a: a.zValue(), reverse=True):
            if a.contains(a.mapFromScene(scene_pos)):
                return a
        return None

    def _subplots_under_annotation(self, ann):
        """Every subplot whose own scene box the annotation's UN-rotated
        bounding box overlaps -- ignores self.rotation() deliberately (an
        arrow tilted 80 degrees shouldn't "cover" a subplot only because
        its rotated silhouette swings over it; "bounding box" means the
        plain axis-aligned one, per the literal request). Feeds the
        "Link to subplot <name>" menu shortcuts on an unlinked
        (anchor='figure') annotation -- see _link_annotation_to_subplot.
        Ordered like self.plots (top-left reading order)."""
        box = ann.boundingRect().translated(ann.pos())
        return [p for p in self.plots if p.sceneBoundingRect().intersects(box)]

    def _link_annotation_to_subplot(self, ann, parent_plot):
        """"Link to subplot <name>" menu shortcut (annotations.py's
        contextMenuEvent): reparents `ann` in place, at wherever it's
        currently sitting on screen. Always anchor='border' -- a
        bounding-box "covers this subplot" relationship is coarse (the
        annotation may not even sit over the subplot's data area), so
        border (attaches to the subplot's chrome, valid anywhere) is the
        safer default; 'axes' anchoring is still reachable via the
        existing precise "Link to..." click-to-choose gesture."""
        self._reparent_annotation(ann, 'border', parent_plot, ann.scenePos())

    def _handle_placement_click(self, scene_pos):
        """Single-click placement for the 'text' point kind. Extent kinds
        (TWO_CLICK_KINDS) are placed by a press-drag-release gesture
        instead -- see eventFilter -- so they never reach here; guarded by
        _on_scene_clicked, which only calls this for non-extent kinds.
        'cursor' is no longer placed this way at all -- it's Data Cursor
        mode's own click-to-move/add gesture now (_handle_cursor_mode_click),
        not a one-shot "Annotate" entry."""
        kind = self._placing_kind
        anchor, parent_plot = self._annotation_zone(scene_pos)
        logger.debug("annotation placement start: kind=%s anchor=%s", kind, anchor)
        p0 = (parent_plot.getViewBox().mapSceneToView(scene_pos) if anchor == 'axes'
              else QtCore.QPointF(scene_pos))
        ann = self._create_annotation(kind, anchor, parent_plot, p0, None,
                                       "Text" if kind == 'text' else '')
        logger.debug("annotation placement completed: kind=%s anchor=%s p0=%s", kind, anchor, p0)
        self._placing_kind = None  # see _cancel_placing's own docstring
        self._cancel_placing()
        if kind == 'text':
            ann.start_text_edit(select_all=True)

    def eventFilter(self, obj, event):
        """Intercept raw press/move/release on the shared scene to place
        TWO_CLICK_KINDS (rect/ellipse/line/arrow/doublearrow/textarrow) via
        a single press-drag-release gesture, MATLAB-style, instead of two
        separate clicks. This can't be done through sigMouseClicked (used
        for every other click-driven interaction -- see _on_scene_clicked)
        because pyqtgraph's GraphicsScene only emits that signal for a
        genuine *click* (a release near the press point); a real
        click-and-drag never fires it at all. Returning True here consumes
        the event outright, so nothing else (a curve's own clickable
        handling, the ViewBox, subplot selection) reacts to it while a
        shape is being placed. A press+release with negligible movement
        (a plain click, no drag) falls back to the shape's default extent
        -- from AnnotationItem.__init__ -- so a single click still places
        something reasonable, matching the point-kind (text/cursor) gesture.

        Every other scene event goes on to the rubber band
        (selection_ui._band_event) -- this is the scene's one event filter."""
        if obj is self.layout_widget.scene() and self._placing_kind in TWO_CLICK_KINDS:
            etype = event.type()
            if etype == QtCore.QEvent.GraphicsSceneMousePress:
                if event.button() != QtCore.Qt.LeftButton:
                    return True
                anchor, parent_plot = self._annotation_zone(event.scenePos())
                logger.debug("annotation placement start: kind=%s anchor=%s", self._placing_kind, anchor)
                p0 = (parent_plot.getViewBox().mapSceneToView(event.scenePos()) if anchor == 'axes'
                      else QtCore.QPointF(event.scenePos()))
                self._placing_state = {
                    'anchor': anchor, 'parent_plot': parent_plot, 'p0': p0,
                    'press_scene_pos': QtCore.QPointF(event.scenePos()),
                }
                return True
            if etype == QtCore.QEvent.GraphicsSceneMouseMove and self._placing_state is not None:
                return True
            if etype == QtCore.QEvent.GraphicsSceneMouseRelease and self._placing_state is not None:
                state = self._placing_state
                anchor, parent_plot, p0 = state['anchor'], state['parent_plot'], state['p0']
                scene_delta = event.scenePos() - state['press_scene_pos']
                if abs(scene_delta.x()) < 3 and abs(scene_delta.y()) < 3:
                    p1_local = None
                else:
                    # Shift constrains the just-drawn shape the same way an
                    # existing one is constrained while being resized (see
                    # constrain_extent_vector) -- computed here, in scene
                    # space, before mapping into the anchor's own space.
                    if event.modifiers() & QtCore.Qt.ShiftModifier:
                        scene_delta = constrain_extent_vector(
                            self._placing_kind, scene_delta, AnnotationItem.SHIFT_SNAP_DEG)
                    end_scene_pos = state['press_scene_pos'] + scene_delta
                    p1 = (parent_plot.getViewBox().mapSceneToView(end_scene_pos) if anchor == 'axes'
                          else QtCore.QPointF(end_scene_pos))
                    p1_local = p1 - p0
                kind = self._placing_kind
                ann = self._create_annotation(kind, anchor, parent_plot, p0, p1_local,
                                               "Text" if kind == 'textarrow' else '')
                if p1_local is None:
                    logger.debug(
                        "annotation placement completed: kind=%s anchor=%s "
                        "(negligible drag, default extent)", kind, anchor)
                else:
                    logger.debug(
                        "annotation placement completed: kind=%s anchor=%s p0=%s p1_local=%s",
                        kind, anchor, p0, p1_local)
                self._placing_kind = None  # see _cancel_placing's own docstring
                self._cancel_placing()
                if kind == 'textarrow':
                    ann.start_text_edit(select_all=True)
                return True
        if obj is self.layout_widget.scene():
            if self._band_event(event):
                return True
        return super().eventFilter(obj, event)

    def _create_annotation(self, kind, anchor, parent_plot, p0, p1_local, text='', point_ref=None):
        pen = pg.mkPen('k', width=2)
        pen.setCosmetic(True)
        # A brand-new arrow-family annotation starts from the user's own
        # persisted Arrow Style preference (arrow_style.default_head_style),
        # not always today's fixed look -- "defaults carry across
        # sessions" (PLAN.md round 4, R4-STYLE). An existing annotation's
        # own current style is untouched by this (it's per-instance state,
        # only ever changed by its own Arrow Style... dialog).
        head_kwargs = {}
        if kind in ARROW_HEAD_KINDS:
            length, width, head_type = default_head_style()
            head_kwargs = {'head_length': length, 'head_width': width, 'head_type': head_type}
        ann = AnnotationItem(self, kind, anchor, parent_plot, pen=pen, brush=None, text=text,
                              point_ref=point_ref, **head_kwargs)
        if p1_local is not None:
            ann.p1_local = QtCore.QPointF(p1_local)
            if ann._end_handle is not None:
                ann._end_handle.setPos(ann._end_handle_pos())
            if ann._rotate_handle is not None:
                ann._position_rotate_handle()
        if anchor == 'border' and parent_plot is not None:
            ann.anchor_offset = self._box_fraction(parent_plot, p0)
        self._add_annotation_to_scene(ann, p0)
        if kind == 'cursor' and p1_local is None:
            # The default marker->label offset (AnnotationItem.__init__)
            # is a fixed up-and-right screen direction, which can land
            # the label outside the subplot near an edge -- only decidable
            # once the item is actually positioned in its subplot, hence
            # after _add_annotation_to_scene rather than inside __init__.
            ann.fit_cursor_label_onscreen()
        self._select_annotation(ann)
        self._track_last_cursor(ann)

        snapshot = ann.to_dict()
        holder = {'ann': ann}

        def undo_fn():
            a = holder.get('ann')
            if a is not None:
                self._purge_annotation(a)

        def redo_fn():
            a = AnnotationItem.from_dict(self, parent_plot, snapshot)
            holder['ann'] = a
            self._select_annotation(a)
            self._track_last_cursor(a)

        self._push_history(undo_fn, redo_fn)
        return ann

    def _track_last_cursor(self, ann):
        """Register `ann` as its subplot's last datacursor (Data Cursor
        mode's per-subplot tracking, see _handle_cursor_mode_click) -- a
        no-op for every other kind. Called from every site that can bring
        a 'cursor' annotation into existence (initial creation, redo of a
        delete/placement undo), so the map stays correct across undo/redo
        without each call site needing its own kind check."""
        if ann.kind == 'cursor':
            self._last_cursor_by_plot[ann.parent_plot] = ann

    def _add_annotation_to_scene(self, ann, local_pos):
        """Place `ann` into its anchor's coordinate parent: the shared
        scene directly for 'figure'/'border' (scene-pixel coordinates), or
        the parent PlotItem's ViewBox for 'axes' (data coordinates, so it
        pans/zooms with the plot for free). `ann.anchor_offset` must
        already be correct for a 'border' annotation before calling this --
        it's the source of truth for where a border annotation sits, not
        `local_pos` (which _reposition_annotations can't reliably supply
        after a subplot has been resized/moved, or when landing in a
        differently-sized subplot via paste).

        `ignoreBounds=True` on an 'axes' annotation: without it, pyqtgraph's
        ViewBox.childrenBounds() folds a plain QGraphicsItem's boundingRect()
        (padded, and -- for 'cursor' -- offset off to one side) straight into
        auto-range, so merely placing an annotation nudges or jumps the
        subplot's own view range while autorange is still on. An annotation
        is a view decoration, not data; it must never drive the camera."""
        if ann.anchor == 'axes':
            ann.parent_plot.addItem(ann, ignoreBounds=True)
            ann.setPos(local_pos)
        else:
            self.layout_widget.scene().addItem(ann)
            if ann.anchor == 'border' and ann.parent_plot is not None:
                self._place_border_annotation(ann)
            else:
                ann.setPos(local_pos)
        if ann not in self.annotations:
            self.annotations.append(ann)

    def _place_border_annotation(self, ann):
        if ann.parent_plot in self.plots:
            ann.setPos(self._box_point(ann.parent_plot, ann.anchor_offset))

    def _reposition_annotations(self):
        for a in self.annotations:
            if a.anchor == 'border':
                self._place_border_annotation(a)

    def _detach_annotation(self, ann):
        if ann.anchor == 'axes' and ann.parent_plot is not None:
            ann.parent_plot.removeItem(ann)
        elif ann.scene() is not None:
            ann.scene().removeItem(ann)

    def _purge_annotation(self, ann):
        """Remove `ann` for good without pushing its own undo entry --
        used when a whole subplot that owns it is itself being deleted/
        recreated as one undo step (see _remove_subplot)."""
        if ann in self.selected_annotations:
            ann.set_selected(False)
            self._forget_annotation_selection(ann)
        self._detach_annotation(ann)
        if ann in self.annotations:
            self.annotations.remove(ann)
        if self._last_cursor_by_plot.get(ann.parent_plot) is ann:
            del self._last_cursor_by_plot[ann.parent_plot]

    def delete_annotation(self, ann):
        """Right-click 'Delete' / Del key on a selected annotation."""
        snapshot = ann.to_dict()
        parent_plot = ann.parent_plot
        self._purge_annotation(ann)
        holder = {}

        def undo_fn():
            a = AnnotationItem.from_dict(self, parent_plot, snapshot)
            holder['ann'] = a
            self._select_annotation(a)
            self._track_last_cursor(a)

        def redo_fn():
            a = holder.get('ann')
            if a is not None:
                self._purge_annotation(a)

        self._push_history(undo_fn, redo_fn)

    # -- annotation styling menu (replaces the old single Properties...
    # dialog chain, 2026-09-30, R4-STYLE) -- one setter per menu entry,
    # each undoable as ONE entry for however many targets are selected.
    # Mirrors curve_style.py's CurveStyleMixin (same "apply, then push one
    # closure per changed target" shape), but simpler: an AnnotationItem's
    # pen/brush are plain attributes, not a pyqtgraph opts dict with a
    # separate selection-highlight overlay to work around.
    @staticmethod
    def _apply_annotation_pen(ann, pen):
        ann.pen = pen
        if ann._text_item is not None:
            ann._text_item.setDefaultTextColor(pen.color())
        ann.update()

    def _edit_annotation_pens(self, targets, change):
        """change(ann) -> a new QPen, or None to skip `ann`. One undo
        entry for the whole gesture, however many annotations."""
        steps = []
        for ann in targets:
            new_pen = change(ann)
            if new_pen is None or new_pen == ann.pen:
                continue
            steps.append((ann, ann.pen, new_pen))
        if not steps:
            return

        def apply(which):
            for ann, old, new in steps:
                self._apply_annotation_pen(ann, new if which else old)

        apply(True)
        self._push_history(lambda: apply(False), lambda: apply(True))

    def set_annotation_line_style(self, targets, code):
        """code: a MATLAB line style ('-', '--', ':', '-.', 'none') --
        same LINE_STYLES table the curve menu uses. Applies to every
        target with a real stroke (annotations.STROKE_KINDS); 'text' has
        nothing of its own to stroke."""
        style = next(v for _, c, v in LINE_STYLES if c == code)

        def change(ann):
            if ann.kind not in STROKE_KINDS:
                return None
            pen = pg.mkPen(ann.pen)
            color = QtGui.QColor(pen.color())
            if style is None:
                color.setAlpha(0)              # invisible, still selectable
            else:
                if color.alpha() == 0:
                    color.setAlpha(255)        # coming back from 'none'
                pen.setStyle(style)
            pen.setColor(color)
            pen.setCosmetic(True)
            return pen
        self._edit_annotation_pens(targets, change)

    def set_annotation_line_width(self, targets, width):
        def change(ann):
            if ann.kind not in STROKE_KINDS:
                return None
            pen = pg.mkPen(ann.pen)
            pen.setWidthF(width)
            pen.setCosmetic(True)
            return pen
        self._edit_annotation_pens(targets, change)

    def set_annotation_color(self, targets, rgb):
        """Recolor the pen (keeping its width/style/alpha) -- and, for a
        text/textarrow annotation, its text color too, same as the old
        Properties... dialog did."""
        def change(ann):
            pen = pg.mkPen(ann.pen)
            color = QtGui.QColor(*rgb)
            color.setAlpha(pen.color().alpha())
            pen.setColor(color)
            pen.setCosmetic(True)
            return pen
        self._edit_annotation_pens(targets, change)

    def set_annotation_fill(self, targets, brush):
        """'Fill...': only rect/ellipse targets in the selection are
        touched (the rest have no fill concept) -- one undo entry."""
        rect_ellipse = [a for a in targets if a.kind in ('rect', 'ellipse')]
        if not rect_ellipse:
            return

        def apply(ann, b):
            ann.brush = b
            ann.update()

        with self.undo_group():
            for ann in rect_ellipse:
                old_brush = ann.brush
                if brush == old_brush:
                    continue
                apply(ann, brush)
                self._push_history(
                    undo_fn=lambda ann=ann, b=old_brush: apply(ann, b),
                    redo_fn=lambda ann=ann, b=brush: apply(ann, b),
                )

    # -- "Arrow Style..." (arrow_style.py) --------------------------------
    def _apply_arrow_style_live(self, targets, length, width, head_type):
        """View-only, no undo -- called on every slider tick while the
        dialog is open, mirroring series.py's _apply_series_transform's
        own live-preview pattern."""
        for ann in targets:
            ann.prepareGeometryChange()
            ann.head_length = length
            ann.head_width = width
            ann.head_type = head_type
            ann.update()

    def set_arrow_style(self, targets, length, width, head_type, before):
        """Commit: one undo entry for the whole gesture, however many
        targets. `before` is {ann: (length, width, head_type)} as it was
        when the dialog opened (ArrowStyleDialog.opened_with)."""
        new = {ann: (length, width, head_type) for ann in targets}
        self._apply_arrow_style_live(targets, length, width, head_type)
        changed = {ann: (before[ann], new[ann]) for ann in targets if before.get(ann) != new[ann]}
        if not changed:
            return

        def apply(which):
            for ann, (old_v, new_v) in changed.items():
                l, w, t = new_v if which else old_v
                ann.prepareGeometryChange()
                ann.head_length, ann.head_width, ann.head_type = l, w, t
                ann.update()

        self._push_history(lambda: apply(False), lambda: apply(True))

    def open_arrow_style_dialog(self, ann):
        """Right-click 'Arrow Style...': the modeless popup (raised if
        already open) for every selected arrow-family annotation if `ann`
        is one of them, else just `ann` -- same selection rule every other
        annotation style entry follows."""
        targets = [a for a in (list(self.selected_annotations) if ann in self.selected_annotations else [ann])
                   if a.kind in ARROW_HEAD_KINDS]
        if not targets:
            return None
        dlg = getattr(self, '_arrow_style_dialog', None)
        if dlg is not None:
            dlg.close()
        dlg = ArrowStyleDialog(self, targets, parent=self)
        self._arrow_style_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    # -- reparenting ("filiation"): right-click an annotation -> Link to...
    # -> click its new parent (a subplot, or empty space for free-floating)
    def _start_relink(self, ann):
        self._cancel_placing()
        self._relink_source = ann
        self._set_placing_cursor(True)

    def _cancel_relink(self):
        self._relink_source = None
        self._set_placing_cursor(False)

    def _handle_relink_click(self, scene_pos):
        ann = self._relink_source
        self._relink_source = None
        self._set_placing_cursor(False)
        anchor, parent_plot = self._annotation_zone(scene_pos)
        if ann.kind == 'cursor' and anchor != 'axes':
            return  # a data cursor must stay tied to some subplot's data axes
        self._reparent_annotation(ann, anchor, parent_plot, scene_pos)

    def _reattach_annotation(self, ann, anchor, parent_plot, local_pos):
        """local_pos must already be in the coordinate space `anchor`
        implies -- scene pixels for figure/border, data units for axes."""
        ann.anchor = anchor
        ann.parent_plot = parent_plot
        if anchor == 'border' and parent_plot is not None:
            ann.anchor_offset = self._box_fraction(parent_plot, local_pos)
        self._add_annotation_to_scene(ann, local_pos)

    def _reparent_annotation(self, ann, new_anchor, new_parent_plot, scene_pos):
        old_anchor, old_parent_plot, old_local_pos = ann.anchor, ann.parent_plot, ann.pos()
        new_local_pos = (new_parent_plot.getViewBox().mapSceneToView(scene_pos) if new_anchor == 'axes'
                          else QtCore.QPointF(scene_pos))

        def undo_fn():
            self._detach_annotation(ann)
            self._reattach_annotation(ann, old_anchor, old_parent_plot, old_local_pos)
            self._select_annotation(ann)

        def redo_fn():
            self._detach_annotation(ann)
            self._reattach_annotation(ann, new_anchor, new_parent_plot, new_local_pos)
            self._select_annotation(ann)

        redo_fn()
        self._push_history(undo_fn, redo_fn)
