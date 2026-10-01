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

The 13 icons here replace icons/*.png files that were copied out of a
MATLAB installation (plotpicker-*, tool_rotate_3d, etc. -- identified
during the open-source cleanup) and can't be redistributed under this
project's BSD-2 license. Each function returns a QIcon painted once onto
a small QPixmap and cached by the QIcon it returns -- the same technique
toolbar.py's own pre-existing _fit_icon/_hide_points_icon already used,
just centralized here now that there are 13 of them instead of 2.

fft_icon()/remove_average_icon() are deliberately NOT redrawn copies of
the original MATLAB icons' look (a spectrum-bars glyph and a
mean-removal glyph respectively) -- the user asked for different
concepts, not lookalikes, for exactly those two.
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


def hand_icon():
    """Hand mode: a four-way move/pan glyph (ldr arrows meeting at center) --
    chosen over a literal hand silhouette, which didn't read clearly at
    18px (see this file's own render-and-check pass)."""
    def draw(p):
        p.setBrush(QtGui.QBrush(_PEN_COLOR))
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            tip = QtCore.QPointF(9 + dx * 7.5, 9 + dy * 7.5)
            p.drawLine(QtCore.QPointF(9, 9), QtCore.QPointF(9 + dx * 4.5, 9 + dy * 4.5))
            _arrowhead(p, tip, dx, dy)
    return _make_icon(draw)


def zoom_in_icon():
    """Zoom Rect mode: a magnifying glass with a '+' in the lens."""
    def draw(p):
        p.drawEllipse(QtCore.QPointF(7.5, 7.5), 5, 5)
        p.drawLine(QtCore.QPointF(11.2, 11.2), QtCore.QPointF(16, 16))
        p.drawLine(QtCore.QPointF(7.5, 5), QtCore.QPointF(7.5, 10))
        p.drawLine(QtCore.QPointF(5, 7.5), QtCore.QPointF(10, 7.5))
    return _make_icon(draw)


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


def data_brush_icon():
    """Brush mode: a selection marquee around a few data points (a dashed
    rounded rect rendered as corner-brackets-only at 18px -- see this
    file's own render-and-check pass -- so this uses a solid outline)."""
    def draw(p):
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(2.5, 2.5, 13, 13), 1.5, 1.5)
        p.setBrush(QtGui.QBrush(_PEN_COLOR))
        for x, y in ((6, 11.5), (9.5, 6), (13, 10)):
            p.drawEllipse(QtCore.QPointF(x, y), 1.4, 1.4)
    return _make_icon(draw)


def data_cursor_icon():
    """Data Cursor: a crosshair readout marker."""
    def draw(p):
        p.drawLine(QtCore.QPointF(9, 2), QtCore.QPointF(9, 6))
        p.drawLine(QtCore.QPointF(9, 12), QtCore.QPointF(9, 16))
        p.drawLine(QtCore.QPointF(2, 9), QtCore.QPointF(6, 9))
        p.drawLine(QtCore.QPointF(12, 9), QtCore.QPointF(16, 9))
        p.setBrush(QtGui.QBrush(_PEN_COLOR))
        p.drawEllipse(QtCore.QPointF(9, 9), 2.2, 2.2)
    return _make_icon(draw)


def legend_icon():
    """Toggle Legend: a small box containing two swatch+line entries."""
    def draw(p):
        p.drawRoundedRect(QtCore.QRectF(2.5, 3.5, 13, 11), 1.5, 1.5)
        p.setBrush(QtGui.QBrush(_PEN_COLOR))
        p.drawRect(QtCore.QRectF(4.5, 6.5, 2.5, 2.5))
        p.drawRect(QtCore.QRectF(4.5, 10.5, 2.5, 2.5))
        p.drawLine(QtCore.QPointF(8.5, 7.7), QtCore.QPointF(14, 7.7))
        p.drawLine(QtCore.QPointF(8.5, 11.7), QtCore.QPointF(14, 11.7))
    return _make_icon(draw)


def text_box_icon():
    """X/Y axis label menu: a 'T' inside an outlined box, drawn with
    plain lines rather than QPainter.drawText -- text didn't render at
    all under an offscreen/fontless Qt platform during this file's own
    render-and-check pass, and plain lines also avoid any font/DPI
    dependency across the Windows/Ubuntu platforms this ships on."""
    def draw(p):
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(2.5, 2.5, 13, 13), 1.5, 1.5)
        pen = QtGui.QPen(_PEN_COLOR, 2.0)
        pen.setCapStyle(QtCore.Qt.FlatCap)
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(6, 6.5), QtCore.QPointF(12, 6.5))
        p.drawLine(QtCore.QPointF(9, 6.5), QtCore.QPointF(9, 12.5))
    return _make_icon(draw)


def link_icon():
    """Link X: two overlapping chain-link rings (thicker pen, non-rounded
    ellipses -- the rounded-rect version merged into one blob at 18px,
    see this file's own render-and-check pass)."""
    def draw(p):
        p.setPen(QtGui.QPen(_PEN_COLOR, 2.0))
        p.setBrush(QtCore.Qt.NoBrush)
        p.save()
        p.translate(6.5, 6.5)
        p.rotate(-40)
        p.drawEllipse(QtCore.QRectF(-3.6, -2.3, 7.2, 4.6))
        p.restore()
        p.save()
        p.translate(11.5, 11.5)
        p.rotate(-40)
        p.drawEllipse(QtCore.QRectF(-3.6, -2.3, 7.2, 4.6))
        p.restore()
    return _make_icon(draw)


def pencil_icon():
    """Place a shape (Annotate dropdown): a pencil, built the same
    rotate/translate way as link_icon -- hand-picked polygon points for
    a diagonal pencil rendered as a single near-invisible line, see this
    file's own render-and-check pass."""
    def draw(p):
        p.setBrush(QtGui.QBrush(_PEN_COLOR))
        p.save()
        p.translate(9, 9)
        p.rotate(-45)
        # Shaft, then a triangular tip just past the shaft's end.
        p.drawRect(QtCore.QRectF(-7.5, -1.6, 11, 3.2))
        p.drawPolygon(QtGui.QPolygonF([
            QtCore.QPointF(3.5, -1.6), QtCore.QPointF(3.5, 1.6), QtCore.QPointF(7.5, 0),
        ]))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRect(QtCore.QRectF(-7.5, -1.6, 2.2, 3.2))
        p.restore()
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
