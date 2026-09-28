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

"""Right-click menus: the per-subplot menu (extending pyqtgraph's own
ViewBox menu) and the minimal empty-space menu (Paste Subplot).
"""
from pyqtgraph.Qt import QtGui, QtWidgets
import pyqtgraph as pg


class MenusMixin:
    def _wire_context_menu(self, plot_item):
        """Extend PyQtGraph's built-in right-click menu (View All / Mouse Mode /
        Plot Options, all still present) with app-specific actions. Right-clicking
        also makes this the focused subplot, same as a left click does."""
        menu = plot_item.getViewBox().menu
        menu.addSeparator()

        def bound(fn):
            return lambda: (self._on_plot_context(plot_item), fn())

        menu.addAction("Paste Curve").triggered.connect(bound(self.paste_curve))
        menu.addAction("Copy Subplot").triggered.connect(bound(self.copy_subplot))
        menu.addAction("Paste Subplot").triggered.connect(bound(self.paste_subplot))
        menu.addAction("Toggle Legend").triggered.connect(bound(self.toggle_legend))
        menu.addAction("Remove Average").triggered.connect(bound(self.remove_average))
        menu.addAction("FFT -> Subplot Below").triggered.connect(bound(self.fft_below))

        menu.addSeparator()
        menu.addAction("Delete Selected Points").triggered.connect(
            bound(self.delete_brushed_points)
        )
        menu.addAction("Transform Selected Points...").triggered.connect(
            bound(self.transform_brushed_points)
        )
        menu.addAction("Selection Stats...").triggered.connect(
            bound(self.show_selection_stats)
        )
        fit_menu = menu.addMenu("Fit Selected Points")
        fit_menu.addAction("Linear").triggered.connect(
            bound(lambda: self.fit_brushed_points(plot_item, degree=1))
        )
        fit_menu.addAction("Polynomial...").triggered.connect(
            bound(lambda: self.fit_brushed_points(plot_item, degree=None))
        )

        delete_menu = menu.addMenu("Delete Curve")
        rename_menu = menu.addMenu("Rename Curve")

        def rebuild_curve_menus():
            delete_menu.clear()
            rename_menu.clear()
            for curve in plot_item.listDataItems():
                if not isinstance(curve, pg.PlotDataItem):
                    continue
                label = curve.name() or "(unnamed curve)"
                delete_menu.addAction(label).triggered.connect(
                    lambda checked=False, c=curve: self.delete_curve(c)
                )
                rename_menu.addAction(label).triggered.connect(
                    lambda checked=False, c=curve: self._rename_curve(plot_item, c)
                )

        menu.aboutToShow.connect(lambda: (self._on_plot_context(plot_item), rebuild_curve_menus()))

    def _show_empty_space_menu(self):
        """Right-click landing outside every subplot: offer Paste Subplot,
        since that's otherwise only reachable via Ctrl+Shift+V or a
        subplot's own right-click menu -- neither is discoverable when
        there's no subplot to right-click yet (e.g. a freshly emptied
        figure)."""
        menu = QtWidgets.QMenu(self)
        paste_action = menu.addAction("Paste Subplot")
        paste_action.setEnabled(bool(self.clipboard.subplot))
        paste_action.triggered.connect(self.paste_subplot)
        menu.exec_(QtGui.QCursor.pos())
