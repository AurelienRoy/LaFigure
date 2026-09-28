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

"""LaFigure: a MATLAB-Figure-like window -- multiple subplots in a
resizable grid, click to select, drag borders/corners to resize, drag a
center handle to move/swap, curve selection, undo/redo, copy/paste curves
and whole subplots (including across separate LaFigure windows via the
shared Clipboard), FFT-to-new-subplot, linked brushing, editable
title/axis/legend text.

This module only holds __init__ (every piece of per-figure state, in one
place), window lifecycle, the demo content, and the mixin composition. The
behavior lives in one mixin per concern:

    toolbar.py         toolbar buttons + keyboard shortcuts
    menus.py           subplot / empty-space right-click menus
    layout.py          grid, add/delete subplot, resize/move/swap/float
    selection_ui.py    click dispatch, selection, focus, rubber band, Tab/nudge
    history.py         undo/redo stack, undo_group()
    brushing.py        Brush toggle + the four brushed-point actions
    clip_ops.py        copy/paste/delete of curves and subplots
    annotation_ops.py  annotation placement, eventFilter, relink, properties
    view_ops.py        interaction mode, Home/Fit, legend, Link X, Remove Average, FFT
    naming.py          figure/subplot/curve names and axis labels
    help.py            the "?" controls/version/credits dialog
    export.py          Save dialog: PNG/JPG/SVG/PDF + header preview
    series.py          series kinds, the Series wrapper, _add_series
    console.py         embedded Python console dock, datatip, filter wiring
    groups.py          Group hierarchy, common label, HSL color offsets

The library-facing API sits on top: fig.subplot() returns an Axes
(axes.py), whose plot() goes through _add_series.

See CLAUDE.md for the design lessons behind this structure -- in
particular, why "plain add/delete a subplot" and "FFT's whole-row
shift" are kept as two genuinely different code paths (layout.py).
"""
import numpy as np
from pyqtgraph.Qt import QtWidgets
import pyqtgraph as pg

from .datasource import DataSource
from .registry import get_registry
from .clipboard import get_clipboard
from .toolbar import ToolbarMixin
from .menus import MenusMixin
from .layout import LayoutMixin
from .selection_ui import SelectionUIMixin
from .history import HistoryMixin
from .brushing import BrushingMixin
from .clip_ops import ClipOpsMixin
from .annotation_ops import AnnotationOpsMixin
from .view_ops import ViewOpsMixin
from .naming import NamingMixin
from .help import HelpMixin
from .export import SaveMixin
from .series import SeriesMixin
from .console import ConsoleMixin
from .groups import GroupsMixin
from .axes import Axes

pg.setConfigOptions(antialias=False, useOpenGL=True, background='w', foreground='k')


class LaFigure(ToolbarMixin, MenusMixin, LayoutMixin, SelectionUIMixin, HistoryMixin,
               BrushingMixin, ClipOpsMixin, AnnotationOpsMixin, ViewOpsMixin, NamingMixin,
               HelpMixin, SaveMixin, SeriesMixin, ConsoleMixin, GroupsMixin,
               QtWidgets.QMainWindow):
    # The mixins come before QMainWindow so their Qt event overrides
    # (eventFilter, resizeEvent) win, and their super() calls still reach Qt.
    # No mixin defines __init__: all state is created here.

    def __init__(self, empty=False):
        super().__init__()
        self.setWindowTitle("MATLAB-like Figure")
        self.resize(1100, 750)

        # If True, delete_subplot's "keep at least one" floor is relaxed to zero.
        self.empty = empty

        self.layout_widget = pg.GraphicsLayoutWidget()
        self.setCentralWidget(self.layout_widget)

        self.plots = []          # list of PlotItem, in creation order
        # The focused subplot: the selected one, or else the one that got
        # the last action -- the toolbar target. Written only through the
        # focused_plot property (selection_ui.py), which emits the
        # registry's focusChanged; the backing field is set directly here
        # so construction emits nothing.
        self._focused_plot = None
        self.active_curve = None
        # Multi-select via Shift+click, a superset of {focused_plot}/
        # {active_curve} respectively. Only Copy, Delete, axis labels,
        # curve rename, and Toggle Legend act on the whole set -- FFT,
        # Remove Average, and everything else still target only
        # focused_plot/active_curve (see set_axis_label/toggle_legend/
        # _rename_curve/copy_curve/copy_subplot/delete_selection).
        self.selected_plots = []
        self.selected_curves = []
        # What the registry's selectionChanged last reported, so it only
        # fires on a real change (see _notify_selection_changed), and how
        # deep we are in nested selection_op calls (only depth 0 reports).
        self._last_selection = ((), (), ())
        self._selection_depth = 0
        # Last subplot the mouse moved over, tracked live (sigMouseMoved)
        # independently of click-selection -- lets "Reset View" act on
        # whichever subplot the user was just working in even in Hand/Zoom
        # mode, where panning/zooming never clicks (and so never touches
        # focused_plot) and the user then moves the mouse away to the
        # toolbar before clicking the button. Never reset to None on its
        # own; only updated when the mouse is actually over a subplot.
        self._hover_plot = None
        self.linked_x = False
        self.brushing = False

        self.max_history = 20
        self.undo_stack = []     # list of (undo_fn, redo_fn)
        self.redo_stack = []
        self._undo_group = None  # list of steps while an undo_group() block is open
        # Rubber-band selection (drag on empty space): {'origin', 'additive', 'item'}.
        self._band = None
        # A finished band drag reaches pyqtgraph as a plain click (it never
        # saw the consumed moves); this swallows that one click.
        self._suppress_click = False

        # Layout state (grid lines, boxes, z_order, drag states) is created
        # by _create_resize_handles below -- see layout.py.

        # plot_item -> RectBrush, the brush-select wired onto every subplot
        # by add_subplot (see selection.py's RectBrush docstring); idle, with
        # nothing allocated or connected, until Brush is turned on.
        self._brushers = {}

        # -- annotations ---------------------------------------------
        self.annotations = []       # every AnnotationItem in this figure
        self.selected_annotations = []
        self.active_annotation = None   # most recently selected of selected_annotations
        # Set by "Annotate > <shape>": next scene click(s) place it instead of selecting.
        self._placing_kind = None
        self._placing_state = None  # {'anchor','parent_plot','p0'} between a two-click shape's clicks
        # Set by "Link to...": next click on a subplot/empty space reparents this annotation.
        self._relink_source = None

        # select: click to select, drag handles to resize/move. Default.
        # hand: plain pan/zoom, no selection UI.
        # zoom: like hand but drag zooms to a rectangle.
        self.interaction_mode = 'select'

        # Register before building subplots so FigureManager's tree/clipboard
        # already has an entry when the first subplotsChanged signal fires.
        self.registry = get_registry()
        self.clipboard = get_clipboard()
        self.registry.register(self)

        self._build_toolbar()
        self._create_resize_handles()
        if not empty:
            self._build_demo_subplots()
        self.set_interaction_mode('select')

        # One shared QGraphicsScene for all subplots -- connect once here, not per-subplot.
        self.layout_widget.scene().sigMouseClicked.connect(self._on_scene_clicked)
        self.layout_widget.scene().sigMouseMoved.connect(self._on_scene_hovered)
        # Raw press/move/release for drag-to-draw placement of extent-having
        # annotations -- see eventFilter's own docstring for why sigMouseClicked
        # alone (used above) can't do this.
        self.layout_widget.scene().installEventFilter(self)

    def subplot(self, row, col, rowspan=1, colspan=1, title='', axes_type='cartesian'):
        """The library entry point: add_subplot, wrapped in an Axes
        (ax.plot, ax.series; ax.plot_item is the raw PlotItem)."""
        return Axes(self, self.add_subplot(row, col, rowspan=rowspan, colspan=colspan,
                                           title=title, axes_type=axes_type))

    def closeEvent(self, ev):
        self.registry.unregister(self)
        super().closeEvent(ev)

    def _build_demo_subplots(self):
        t = np.linspace(0, 10, 200_000)
        y1 = np.sin(2 * np.pi * 1.0 * t) + 0.05 * np.random.randn(t.size) + 2.0
        y2 = np.sin(2 * np.pi * 2.5 * t) * np.exp(-0.1 * t)

        # clip_to_view + peak downsampling: the millions-of-points settings.
        p1 = self.add_subplot(row=0, col=0, title="Signal A")
        self._add_series(p1, 'line', t, y1, pen=pg.mkPen((80, 120, 220), width=1), name="signal A",
                         clip_to_view=True, downsample='peak')

        p2 = self.add_subplot(row=0, col=1, title="Signal B")
        self._add_series(p2, 'line', t, y2, pen=pg.mkPen((220, 100, 80), width=1), name="signal B",
                         clip_to_view=True, downsample='peak')

        # Two views of the same rows: two series of one DataSource, so
        # brushing either highlights the same rows on both (brushing.py).
        rng = np.random.default_rng(0)
        n = 20_000
        a = rng.normal(size=n)
        source = DataSource({'a': a, 'b': a * 0.6 + rng.normal(scale=0.5, size=n)})

        p3 = self.add_subplot(row=1, col=0, title="Scatter view 1 (brush me)")
        self._demo_scatter(p3, source, 'a', 'b', (80, 160, 90))

        p4 = self.add_subplot(row=1, col=1, title="Scatter view 2 (same rows)")
        self._demo_scatter(p4, source, 'b', 'a', (160, 90, 160))

        self.focused_plot = p1
        self._mark_active(p1)

    def _demo_scatter(self, plot_item, source, x, y, color):
        """A line series drawn as dots. TODO: ax.scatter once a scatter kind
        exists (this style isn't carried by the line kind's copy/paste)."""
        item = self._add_series(plot_item, 'line', source[x], source[y],
                                name=f"{y} vs {x}", source=source, columns=(x, y)).item
        item.setPen(None)  # the line kind reads pen=None as "default pen"
        item.setSymbol('o')
        item.setSymbolSize(4)
        item.setSymbolPen(None)
        item.setSymbolBrush(pg.mkBrush(*color, 160))
