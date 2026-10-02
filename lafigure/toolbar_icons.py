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

"""Toolbar icons drawn in code instead of shipped as image files.

These icons replace icons/*.png files that were copied out of a MATLAB
installation (plotpicker-*, tool_rotate_3d, etc. -- identified during
the open-source cleanup) and can't be redistributed under this
project's BSD-2 license. Each function returns a QIcon painted once onto
a small QPixmap and cached by the QIcon it returns -- the same technique
toolbar.py's own pre-existing _fit_icon/_hide_points_icon already used,
just centralized here now that there are several of them.

fft_icon()/remove_average_icon() are deliberately NOT redrawn copies of
the original MATLAB icons' look (a spectrum-bars glyph and a
mean-removal glyph respectively) -- the user asked for different
concepts, not lookalikes, for exactly those two.

Eight further icons that used to live here (hand/zoom_in/data_brush/
data_cursor/legend/text_box/link/pencil) were replaced 2026-10-02 by
real icons/*.png artwork the user drew and confirmed is free of any
proprietary rights (tool_pan.png, tool_zoom.png, tool_brush.png,
tool_datacursor.png, tool_legend.png, tool_xylabels.png,
tool_link_x.png, tool_annotations.png) -- see toolbar.py's own
`action`/`menu_button` call sites for where each is wired in.
"""
import math

from pyqtgraph.Qt import QtCore, QtGui

_SIZE = 18
_PEN_COLOR = QtGui.QColor(40, 40, 40)


def _make_icon(draw, size=_SIZE):
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtGui.QPen(_PEN_COLOR, 1.5))
    draw(painter)
    painter.end()
    return QtGui.QIcon(pix)


def pointer_icon():
    """Select mode: a filled mouse-pointer silhouette."""
    def draw(p):
        p.setBrush(QtGui.QBrush(_PEN_COLOR))
        p.drawPolygon(QtGui.QPolygonF([
            QtCore.QPointF(3, 2), QtCore.QPointF(3, 14.5),
            QtCore.QPointF(6.6, 11.2), QtCore.QPointF(8.6, 16),
            QtCore.QPointF(10.6, 15), QtCore.QPointF(8.6, 10.2),
            QtCore.QPointF(13.2, 10.2),
        ]))
    return _make_icon(draw)


def _arrowhead(p, tip, dx, dy, length=3.2, width=2.4):
    """A small filled triangle pointing from (tip - length*(dx,dy)) to tip."""
    bx, by = tip.x() - dx * length, tip.y() - dy * length
    px, py = -dy * width / 2, dx * width / 2
    p.drawPolygon(QtGui.QPolygonF([
        tip, QtCore.QPointF(bx + px, by + py), QtCore.QPointF(bx - px, by - py),
    ]))


def rotate_3d_icon():
    """Rotate + Zoom mode: a circular rotate/orbit arrow -- an ellipse+dot
    read as a plain eye, and a ring+center-dot read as a target/record
    button, both at 18px (see this file's own render-and-check pass), so
    this is a plain gapped arc + arrowhead with nothing in the middle,
    the conventional "rotate" glyph (same family as a refresh icon)."""
    def draw(p):
        p.setPen(QtGui.QPen(_PEN_COLOR, 1.8))
        rect = QtCore.QRectF(3, 3, 12, 12)
        p.drawArc(rect, 40 * 16, 230 * 16)
        end_deg = 40 + 230
        rad = math.radians(end_deg)
        cx, cy = rect.center().x(), rect.center().y()
        rx, ry = rect.width() / 2, rect.height() / 2
        tip = QtCore.QPointF(cx + rx * math.cos(rad), cy - ry * math.sin(rad))
        tdx, tdy = math.sin(rad), math.cos(rad)
        p.setBrush(QtGui.QBrush(_PEN_COLOR))
        _arrowhead(p, tip, tdx, tdy, length=3.6, width=3.2)
    return _make_icon(draw)


def fft_icon():
    """FFT -> subplot below: a frequency-spectrum bar glyph (deliberately
    not a redraw of MATLAB's own fft_icon6.png -- see module docstring)."""
    def draw(p):
        p.drawLine(QtCore.QPointF(2.5, 15.5), QtCore.QPointF(15.5, 15.5))
        p.setBrush(QtGui.QBrush(_PEN_COLOR))
        bars = [(3.5, 6), (6.5, 11), (9.5, 4), (12.5, 9), (15, 7)]
        for x, h in bars:
            p.drawRect(QtCore.QRectF(x - 1, 15.5 - h, 2, h))
    return _make_icon(draw)


def remove_average_icon():
    """Remove Average: a wavy signal centered on a dashed zero line
    (deliberately not a redraw of MATLAB's own icon1b1.png -- see module
    docstring)."""
    def draw(p):
        pen = QtGui.QPen(_PEN_COLOR, 1.1, QtCore.Qt.DashLine)
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(2, 9), QtCore.QPointF(16, 9))
        p.setPen(QtGui.QPen(_PEN_COLOR, 1.6))
        path = QtGui.QPainterPath()
        path.moveTo(2, 9)
        path.cubicTo(4.5, 2, 6.5, 2, 9, 9)
        path.cubicTo(11.5, 16, 13.5, 16, 16, 9)
        p.drawPath(path)
    return _make_icon(draw)


def home_icon():
    """Home / reset view: a simple house pictogram."""
    def draw(p):
        p.drawPolygon(QtGui.QPolygonF([
            QtCore.QPointF(2.5, 9), QtCore.QPointF(9, 3),
            QtCore.QPointF(15.5, 9),
        ]))
        p.drawRect(QtCore.QRectF(4.5, 9, 9, 6.5))
        p.drawLine(QtCore.QPointF(7.8, 15.5), QtCore.QPointF(7.8, 11.5))
        p.drawLine(QtCore.QPointF(7.8, 11.5), QtCore.QPointF(10.2, 11.5))
        p.drawLine(QtCore.QPointF(10.2, 11.5), QtCore.QPointF(10.2, 15.5))
    return _make_icon(draw)
