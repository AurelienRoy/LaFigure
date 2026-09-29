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

"""Shared test fixtures: the QApplication, fake pyqtgraph/Qt events for
driving handlers directly, real-event drivers (_mouse, _key) for behavior
that depends on Qt's or pyqtgraph's own event routing, and figure
factories. Import from here; never create a second QApplication.
"""
import time

import numpy as np
import pyqtgraph as pg
pg.setConfigOptions(useOpenGL=False)  # test-only; the shipped app keeps useOpenGL=True
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets, QtTest
import lafigure as m
# figure.py sets useOpenGL=True as a module-level side effect on import
# (correct for the shipped app), which stomps the line above. Offscreen
# QPA has no real GL context, so re-assert False now that the import is done.
pg.setConfigOptions(useOpenGL=False)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def shown_figure():
    """A fresh demo figure (2x2: two curves, two linked scatters), shown so
    geometry is real."""
    f = m.LaFigure()
    f.show()
    app.processEvents()
    return f


def first_curve(plot_item):
    return [c for c in plot_item.listDataItems() if isinstance(c, pg.PlotDataItem)][0]


class FakeClickEvent:
    """Duck-types pyqtgraph's MouseClickEvent enough to drive
    _on_scene_clicked() directly, without going through real Qt mouse-event
    dispatch. Fine for testing the dispatcher's own logic; behavior that
    depends on Qt's or pyqtgraph's routing needs _mouse/_key instead (see
    CLAUDE.md, "Headless testing by calling methods directly")."""

    def __init__(self, pos, double=False, accepted=False, button=QtCore.Qt.LeftButton,
                 modifiers=QtCore.Qt.NoModifier):
        self._pos = pos
        self._double = double
        self._accepted = accepted
        self._button = button
        self._modifiers = modifiers

    def scenePos(self):
        return self._pos

    def double(self):
        return self._double

    def isAccepted(self):
        return self._accepted

    def button(self):
        return self._button

    def modifiers(self):
        return self._modifiers


def has_border(plot_item):
    """pyqtgraph's ViewBox.setBorder(None) stores fn.mkPen(None) -- a QPen
    styled NoPen, never the Python singleton None -- so `.border is None`
    can never be true. Check pen style instead."""
    return plot_item.getViewBox().border.style() != QtCore.Qt.NoPen


class FakeSceneEvent:
    """Duck-types a raw QGraphicsScene mouse event enough to drive
    LaFigure.eventFilter() directly. TWO_CLICK_KINDS (rect/ellipse/line/
    arrow/doublearrow/textarrow) are placed via a press-drag-release gesture
    intercepted by eventFilter, NOT via sigMouseClicked/_on_scene_clicked
    (see eventFilter's own docstring: a real click-and-drag never fires
    sigMouseClicked at all) -- so exercising that placement path means
    feeding eventFilter raw press/release events like this, not
    FakeClickEvent."""

    def __init__(self, etype, pos, button=QtCore.Qt.LeftButton):
        self._type = etype
        self._pos = pos
        self._button = button

    def type(self):
        return self._type

    def scenePos(self):
        return self._pos

    def button(self):
        return self._button


def _is_x_linked(plot_item):
    return plot_item.getViewBox().linkedView(pg.ViewBox.XAxis) is not None


SHIFT = QtCore.Qt.ShiftModifier


class FakePressEvent:
    """Duck-types the QGraphicsSceneMouseEvent AnnotationItem.mousePressEvent reads."""

    def __init__(self, pos, modifiers=QtCore.Qt.NoModifier):
        self._pos = pos
        self._modifiers = modifiers

    def button(self):
        return QtCore.Qt.LeftButton

    def modifiers(self):
        return self._modifiers

    def scenePos(self):
        return self._pos

    def accept(self):
        pass


def _vb_center(plot_item):
    return plot_item.getViewBox().sceneBoundingRect().center()


def _click_subplot(f, plot_item, modifiers=QtCore.Qt.NoModifier):
    f._on_scene_clicked(FakeClickEvent(_vb_center(plot_item), modifiers=modifiers))


def _click_curve(f, plot_item, curve, modifiers=QtCore.Qt.NoModifier):
    curve.curve.sigClicked.emit(curve.curve, FakeClickEvent(_vb_center(plot_item), modifiers=modifiers))
    f._on_scene_clicked(FakeClickEvent(_vb_center(plot_item), accepted=True, modifiers=modifiers))


def _click_annotation(f, ann, modifiers=QtCore.Qt.NoModifier):
    ann.mousePressEvent(FakePressEvent(ann.scenePos(), modifiers=modifiers))


def _selection_figure():
    """A fresh figure in Select mode with one rect annotation on plots[1],
    and nothing selected."""
    f = m.LaFigure()
    f.show()
    app.processEvents()
    plot = f.plots[1]
    f.start_placing_annotation('rect')
    scene = f.layout_widget.scene()
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMousePress, _vb_center(plot)))
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMouseRelease,
                                        _vb_center(plot) + QtCore.QPointF(40, 30)))
    f._deselect_all()
    ann = f.annotations[-1]
    curve = f.plots[0].listDataItems()[0]
    return f, curve, ann


def _selected(f):
    return list(f.selected_plots), list(f.selected_curves), f.active_annotation


def _place(f, kind, plot_item, offset=QtCore.QPointF(0, 0)):
    scene = f.layout_widget.scene()
    start = _vb_center(plot_item) + offset
    f.start_placing_annotation(kind)
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMousePress, start))
    f.eventFilter(scene, FakeSceneEvent(QtCore.QEvent.GraphicsSceneMouseRelease,
                                        start + QtCore.QPointF(40, 30)))
    return f.annotations[-1]


def _two_annotation_figure():
    """rect on plots[1], ellipse on plots[0] -- two subplots, so two
    different data-unit coordinate systems. Nothing selected."""
    f, curve, rect = _selection_figure()
    ellipse = _place(f, 'ellipse', f.plots[0], QtCore.QPointF(-60, -40))
    f._deselect_all()
    app.processEvents()  # let the ViewBoxes' lazy auto-range settle before positions are read
    return f, curve, rect, ellipse


def _empty_scene_point(f):
    pt = QtCore.QPointF(2, 2)
    assert not any(p.getViewBox().sceneBoundingRect().contains(pt) for p in f.plots), \
        "control: the 'empty' point must really be outside every subplot"
    return pt


def _press_escape(f):
    esc = [s for s in f.findChildren(QtGui.QShortcut)
           if s.key() == QtGui.QKeySequence(QtCore.Qt.Key_Escape)]
    assert len(esc) == 1, "control: exactly one Esc shortcut is bound"
    esc[0].activated.emit()


def _scene_pos(ann):
    return ann.parentItem().mapToScene(ann.pos()) if ann.parentItem() else ann.pos()


def _mouse(f, etype, scene_pt, buttons, button=QtCore.Qt.LeftButton, mods=QtCore.Qt.NoModifier):
    """The short QMouseEvent(type, localPos, button, buttons, modifiers)
    constructor sets globalPos to QCursor.pos() -- and QGraphicsScene picks
    the *item* under the mouse from the global position (mapped back
    through the viewport), not from localPos/scenePos. So that short form
    reaches the scene's own event filter (which reads scenePos) at the
    right point -- enough for rubber-band/click dispatch, which is why
    that worked before this fix -- but hands the actual press to whatever
    item sits under the real, arbitrary OS cursor instead of scene_pt.
    Dragging a handle, gutter or annotation needs the item at scene_pt to
    receive the press, so the global position must be the same point too
    (found by WP-A; see CLAUDE.md)."""
    view = f.layout_widget
    local = QtCore.QPointF(view.mapFromScene(scene_pt))
    global_pos = QtCore.QPointF(view.viewport().mapToGlobal(local.toPoint()))
    ev = QtGui.QMouseEvent(etype, local, local, global_pos, button, buttons, mods)
    QtWidgets.QApplication.sendEvent(view.viewport(), ev)
    app.processEvents()


def _band_drag(f, a, b, mods=QtCore.Qt.NoModifier):
    """Paced (found by WP-O, 2026-09-28): pyqtgraph's GraphicsScene drops a
    mouse move closer than 1/mouseRateLimit s (10ms) to the previous one,
    so unpaced synthetic moves risk never becoming a real drag event for
    anything routed through pyqtgraph's own drag dispatch (e.g. RectBrush,
    via _brush_drag below -- the rubber band itself reads raw events via
    eventFilter and is immune, but shares this helper). 12ms mirrors
    tests/test_3d.py's own _drag, written for the same reason."""
    L = QtCore.Qt.LeftButton
    _mouse(f, QtCore.QEvent.MouseButtonPress, a, L, mods=mods)
    for t in (0.1, 0.5, 1.0):
        time.sleep(0.012)
        _mouse(f, QtCore.QEvent.MouseMove, a + (b - a) * t, L, button=QtCore.Qt.NoButton, mods=mods)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, b, QtCore.Qt.NoButton, mods=mods)


def _brush_drag(f, plot_item, a, b, mods=QtCore.Qt.NoModifier):
    """A real left-button drag on plot_item from data point `a` to data
    point `b` (each an (x, y) tuple) -- a brush rectangle while Brush is on."""
    vb = plot_item.getViewBox()
    _band_drag(f, vb.mapViewToScene(QtCore.QPointF(*a)), vb.mapViewToScene(QtCore.QPointF(*b)),
               mods=mods)


def _key(f, key, mods=QtCore.Qt.NoModifier):
    f.activateWindow()
    app.processEvents()
    QtTest.QTest.keyClick(f, key, mods)
    app.processEvents()


def _band_start_up_left_of(f, pt):
    """A point up-left of `pt`, still inside the same data area, where a band
    can start -- i.e. clear of curves, legends and annotation padding."""
    for d in range(25, 120, 5):
        for dx, dy in ((d, d), (d, 25), (25, d)):
            cand = pt - QtCore.QPointF(dx, dy)
            if f._can_start_band_at(cand):
                return cand
    raise AssertionError("control: no free point to start a band near %r" % pt)


def _ramp_figure():
    """One subplot, y = x on x in [0, 100], hovered so the view actions target it."""
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    x = np.linspace(0, 100, 1001)
    p.plot(x, x)
    f._hover_plot = p
    return f, p.getViewBox()
