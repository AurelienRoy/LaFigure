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

"""Curve display style -- line width, line style, marker, marker size,
color, z-order -- edited undoably and *highlight-aware*.

The one path for every style edit (the curve right-click menu, menus.py,
and the Curve Browser's editor, manager.py). The trap it exists for: while
a curve is selected, its opts['pen'] is the thick selection-highlight pen
and its real pen is parked in opts['_orig_pen'] (selection_ui.py). Editing
opts['pen'] directly then either bakes the highlight width into the style
or gets reverted by the next deselect. So every edit here unhighlights,
applies to the real style, and re-highlights.

MATLAB-style values: LINE_STYLES/MARKERS map MATLAB's codes onto QPen
styles and pyqtgraph symbols. Line style 'none' is a fully transparent
pen, never pen=None -- pyqtgraph skips building a curve's hit-test path
when its pen is None, which would make the curve unclickable (CLAUDE.md
bug #15; kinds/scatter.py does the same).
"""
from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph as pg

# (label, MATLAB code, value) -- value is a Qt pen style, or None for 'none'.
LINE_STYLES = [
    ("Solid", '-', QtCore.Qt.SolidLine),
    ("Dashed", '--', QtCore.Qt.DashLine),
    ("Dotted", ':', QtCore.Qt.DotLine),
    ("Dash-dot", '-.', QtCore.Qt.DashDotLine),
    ("None", 'none', None),
]
LINE_WIDTHS = [0.5, 1, 1.5, 2, 3, 4, 6]
# (label, MATLAB code, pyqtgraph symbol) -- pyqtgraph names its triangles
# by where they point: 't' down, 't1' up, 't2' right, 't3' left.
MARKERS = [
    ("None", 'none', None),
    ("Circle", 'o', 'o'),
    ("Plus", '+', '+'),
    ("Asterisk", '*', 'star'),
    ("Cross", 'x', 'x'),
    ("Square", 's', 's'),
    ("Diamond", 'd', 'd'),
    ("Triangle up", '^', 't1'),
    ("Triangle down", 'v', 't'),
    ("Triangle right", '>', 't2'),
    ("Triangle left", '<', 't3'),
    ("Pentagon", 'p', 'p'),
    ("Hexagon", 'h', 'h'),
]
MARKER_SIZES = [3, 4, 6, 8, 10, 12, 16]

# Which options apply to which kind. A scatter's line pen is transparent
# BY DEFAULT (its item is still a genuine PlotDataItem, kinds/scatter.py),
# not because the kind is incapable of one -- so it gets its own, broader
# membership (_LINE_CAPABLE_KINDS) below, distinct from _LINE_KINDS (the
# kinds whose line is meaningful unconditionally, regardless of whether
# it's currently visible -- width/color edits on these apply even while
# Line Style is 'none', so a later restyle shows the edited color/width;
# see test_line_color_on_a_none_style_line_stays_invisible). The step/fill
# kinds keep their pen in to_dict but not a marker, so markers stay
# line/scatter only.
_LINE_KINDS = ('line', 'stairs', 'area', 'hist', 'errorbar')
_LINE_CAPABLE_KINDS = _LINE_KINDS + ('scatter',)
_MARKER_KINDS = ('line', 'scatter')

_STATE_KEYS = ('pen', 'symbol', 'symbolSize', 'symbolBrush', 'symbolPen')


def line_options_apply(kind):
    """True for the kinds whose pen is always treated as a meaningful
    line, whatever it currently draws (see the module comment above)."""
    return kind in _LINE_KINDS


def line_capable(kind):
    """True for any kind whose item can draw a real connecting line at
    all -- the broader set line_options_apply doesn't cover, e.g.
    'scatter': its default pen is fully transparent (CLAUDE.md bug #15),
    but nothing stops the user from turning a real line on via Line
    Style. Used to gate the curve menu's Line Style submenu, which must
    stay enabled for a line-capable kind regardless of whether a line is
    CURRENTLY drawn -- that's exactly how the user turns one on."""
    return kind in _LINE_CAPABLE_KINDS


def has_current_line(kind, pen):
    """True if `kind`'s item is drawing a real, visible line right now.
    Unconditionally true for line_options_apply's kinds (mirrors their
    existing behavior: Line Width/Color already applied regardless of the
    pen's current visibility, e.g. while Line Style is 'none' -- kept
    as-is, not just for menu gating). For a merely line_capable kind
    (e.g. 'scatter'), true only once its pen is actually visible -- Line
    Width/Color stay grayed (and gated a no-op, see set_curve_line_width/
    set_curve_line_color) until Line Style has turned a real line on."""
    if line_options_apply(kind):
        return True
    return line_capable(kind) and pen_style_of(pen) != 'none'


def marker_options_apply(kind):
    return kind in _MARKER_KINDS


def pen_style_of(pen):
    """The MATLAB line-style code a pen draws: 'none' for no/transparent line."""
    if pen is None:
        return 'none'
    pen = pg.mkPen(pen)
    if pen.style() == QtCore.Qt.NoPen or pen.color().alpha() == 0:
        return 'none'
    for _, code, style in LINE_STYLES:
        if style == pen.style():
            return code
    return '-'


class CurveStyleMixin:
    # -- the real (un-highlighted) style ---------------------------------------
    @staticmethod
    def _curve_style_state(item):
        o = item.opts
        state = {k: o.get(k) for k in _STATE_KEYS}
        if '_orig_pen' in o:
            state['pen'] = o['_orig_pen']
        if '_orig_symbol_pen' in o:
            state['symbolPen'] = o['_orig_symbol_pen']
        return state

    def _apply_curve_style_state(self, item, state):
        highlighted = item in self.selected_curves
        if highlighted:
            self._unhighlight_curve_pen(item)
        # Only what differs: pyqtgraph's setters normalize None into a
        # NoPen/NoBrush object, so re-applying an unchanged None would
        # quietly change what opts holds (and what to_dict then records).
        setters = {'pen': item.setPen, 'symbol': item.setSymbol, 'symbolSize': item.setSymbolSize,
                   'symbolBrush': item.setSymbolBrush, 'symbolPen': item.setSymbolPen}
        for key, setter in setters.items():
            value, current = state[key], item.opts.get(key)
            if value is current or (value is not None and current is not None and value == current):
                continue
            if key in ('pen', 'symbolSize') and value is None:
                continue
            setter(value)
        if highlighted:
            self._highlight_curve_pen(item)

    def _edit_curve_styles(self, items, change):
        """change(item, state) -> the new state dict, or None to skip
        `item`. One undo entry for the whole gesture, however many curves."""
        steps = []
        for item in items:
            old = self._curve_style_state(item)
            new = change(item, dict(old))
            if new is None or new == old:
                continue
            steps.append((item, old, new))
        if not steps:
            return

        def apply(which):
            for item, old, new in steps:
                self._apply_curve_style_state(item, new if which else old)

        apply(True)
        self._push_history(lambda: apply(False), lambda: apply(True))

    @staticmethod
    def _line_color(state):
        pen = state['pen']
        return pg.mkPen(pen).color() if pen is not None else QtGui.QColor('k')

    # -- public edits ----------------------------------------------------------
    def set_curve_line_width(self, items, width):
        def change(item, s):
            # Gated on has_current_line, not line_capable: a merely
            # line-capable kind (e.g. scatter) with no visible line yet
            # has nothing to widen -- Line Style is what turns one on.
            if not has_current_line(self._curve_kind(item), s['pen']):
                return None
            pen = pg.mkPen(s['pen']) if s['pen'] is not None else pg.mkPen('k')
            pen.setWidthF(width)
            s['pen'] = pen
            return s
        self._edit_curve_styles(items, change)

    def set_curve_line_style(self, items, code):
        """code: a MATLAB line style ('-', '--', ':', '-.', 'none')."""
        style = next(v for _, c, v in LINE_STYLES if c == code)

        def change(item, s):
            # Gated on line_capable, the broader set: this is the one
            # edit that can turn a line on in the first place (e.g. for a
            # scatter whose pen is transparent by default), so it must
            # apply regardless of whether a line is CURRENTLY visible.
            if not line_capable(self._curve_kind(item)):
                return None
            pen = pg.mkPen(s['pen']) if s['pen'] is not None else pg.mkPen('k')
            color = QtGui.QColor(pen.color())
            if style is None:
                color.setAlpha(0)              # invisible, still hit-testable
            else:
                if color.alpha() == 0:
                    color.setAlpha(255)        # coming back from 'none'
                pen.setStyle(style)
            pen.setColor(color)
            s['pen'] = pen
            return s
        self._edit_curve_styles(items, change)

    def set_curve_marker(self, items, symbol):
        """symbol: a pyqtgraph symbol name, or None for no marker. A marker
        added to a line takes the line's color (MATLAB's 'auto') and size 6
        (pyqtgraph's own default, 10, is kept in opts even with no marker)."""
        def change(item, s):
            if not marker_options_apply(self._curve_kind(item)):
                return None
            if s['symbol'] is None and symbol is not None:
                color = self._line_color(s)
                color.setAlpha(255)
                s['symbolBrush'] = pg.mkBrush(color)
                s['symbolPen'] = pg.mkPen(color)
                s['symbolSize'] = 6            # MATLAB's default MarkerSize
            s['symbol'] = symbol
            return s
        self._edit_curve_styles(items, change)

    def set_curve_marker_size(self, items, size):
        def change(item, s):
            if not marker_options_apply(self._curve_kind(item)):
                return None
            s['symbolSize'] = size
            return s
        self._edit_curve_styles(items, change)

    def set_curve_color(self, items, rgba):
        """Recolor whatever the curve actually draws: its line if visible,
        its marker brush/outline if it has markers. Keeps line width/style."""
        def change(item, s):
            color = pg.mkColor(rgba)
            pen = pg.mkPen(s['pen']) if s['pen'] is not None else None
            if pen is not None and pen.color().alpha() > 0:
                pen.setColor(color)
                s['pen'] = pen
            if s['symbolBrush'] is not None:
                s['symbolBrush'] = pg.mkBrush(color)
            if s['symbolPen'] is not None:
                s['symbolPen'] = pg.mkPen(color)
            return s
        self._edit_curve_styles(items, change)

    def set_curve_line_color(self, items, rgba):
        """Recolor only the line pen, keeping width/style (incl. 'none'
        invisibility -- the chosen alpha is discarded, the pen's own is
        kept, so picking a color while Line Style is 'none' doesn't make
        the line reappear)."""
        def change(item, s):
            # Same has_current_line gate as set_curve_line_width -- see
            # its own comment.
            if not has_current_line(self._curve_kind(item), s['pen']):
                return None
            pen = pg.mkPen(s['pen']) if s['pen'] is not None else pg.mkPen('k')
            color = pg.mkColor(rgba)
            color.setAlpha(pen.color().alpha())
            pen.setColor(color)
            s['pen'] = pen
            return s
        self._edit_curve_styles(items, change)

    def set_curve_marker_color(self, items, rgba):
        """Recolor only the marker fill/outline, leaving the line alone."""
        def change(item, s):
            if not marker_options_apply(self._curve_kind(item)):
                return None
            color = pg.mkColor(rgba)
            s['symbolBrush'] = pg.mkBrush(color)
            s['symbolPen'] = pg.mkPen(color)
            return s
        self._edit_curve_styles(items, change)

    def _curve_kind(self, item):
        series = self._series_of(item)
        return series.kind if series is not None else 'line'

    # -- z-order within a subplot ----------------------------------------------
    def _notify_legend_order_changed(self):
        """Package P3 (view_ops.py) owns the legend-order-follows-z-order
        feature; this package doesn't implement or depend on it, but any
        z-mutating action here should still poke it if it's been wired in
        (may not be merged yet -- see this package's own report)."""
        refresh = getattr(self, '_refresh_legend_order', None)
        if refresh is not None:
            refresh()

    def curves_to_front(self, items, front=True):
        """Draw `items` above (front=True) or below every other data item of
        their subplot. Undoable, one entry."""
        steps = []
        for item in items:
            plot_item = self._curve_plot(item)
            if plot_item is None:
                continue
            zs = [c.zValue() for c in plot_item.listDataItems() if c is not item] or [item.zValue()]
            new_z = max(zs) + 1 if front else min(zs) - 1
            if new_z != item.zValue():
                steps.append((item, item.zValue(), new_z))
                # Stack several moved curves in order, not all on one z.
                item.setZValue(new_z)
        if not steps:
            return
        self._notify_legend_order_changed()

        def apply(which):
            for item, old, new in steps:
                item.setZValue(new if which else old)
            self._notify_legend_order_changed()

        self._push_history(lambda: apply(False), lambda: apply(True))
