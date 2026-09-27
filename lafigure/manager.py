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

"""FigureManager: a small persistent window listing every open LaFigure
and its subplots, plus a button to create a new, empty figure window --
this is what makes whole-subplot copy/paste between *separate* figure
windows something you can actually set up and test (see LaFigure.
copy_subplot/paste_subplot and clipboard.py).

Deliberately its own top-level window, not a dock inside a LaFigure --
it must outlive any single figure and list them all.
"""
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from .figure import LaFigure
from .registry import get_registry


class FigureManager(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Figure Manager")
        self.resize(320, 480)

        self.registry = get_registry()
        # Keep our own open LaFigure instances alive -- nothing else
        # holds a strong reference to a figure created here once its local
        # variable goes out of scope.
        self._owned_figures = []

        tb = QtWidgets.QToolBar("Figures")
        self.addToolBar(tb)
        new_fig_action = QtGui.QAction("New Figure", self)
        new_fig_action.setToolTip("Create a new, empty figure window (no subplots) -- "
                                   "useful for testing copy/paste between figures.")
        new_fig_action.triggered.connect(self.new_figure)
        tb.addAction(new_fig_action)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Figure / Subplot"])
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.setCentralWidget(self.tree)

        self._figure_items = {}  # LaFigure -> QTreeWidgetItem

        self.registry.figureOpened.connect(self._on_figure_opened)
        self.registry.figureClosed.connect(self._on_figure_closed)
        self.registry.subplotsChanged.connect(self._on_subplots_changed)

        # Any figures already open (e.g. the demo figure app.main() creates
        # before this manager) won't have fired figureOpened while we
        # weren't listening yet -- backfill them.
        for fig in list(self.registry.figures):
            self._add_figure_item(fig)

    def new_figure(self):
        fig = LaFigure(empty=True)
        fig.show()
        self._owned_figures.append(fig)
        return fig

    # -- tree maintenance --------------------------------------------
    def _add_figure_item(self, fig):
        if fig in self._figure_items:
            return
        item = QtWidgets.QTreeWidgetItem([fig.windowTitle()])
        item.setData(0, QtCore.Qt.UserRole, fig)
        self.tree.addTopLevelItem(item)
        self._figure_items[fig] = item
        self._refresh_subplots(fig)

    def _refresh_subplots(self, fig):
        item = self._figure_items.get(fig)
        if item is None:
            return
        item.setText(0, fig.windowTitle())
        item.takeChildren()
        for plot_item in fig.plots:
            title = plot_item.titleLabel.text or "(untitled subplot)"
            child = QtWidgets.QTreeWidgetItem([title])
            child.setData(0, QtCore.Qt.UserRole, fig)
            item.addChild(child)
        item.setExpanded(True)

    def _on_figure_opened(self, fig):
        self._add_figure_item(fig)

    def _on_figure_closed(self, fig):
        item = self._figure_items.pop(fig, None)
        if item is not None:
            idx = self.tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self.tree.takeTopLevelItem(idx)
        if fig in self._owned_figures:
            self._owned_figures.remove(fig)

    def _on_subplots_changed(self, fig):
        self._refresh_subplots(fig)

    def _on_item_double_clicked(self, item, column):
        """Double-clicking any row (the figure itself or one of its
        subplots) raises and focuses that figure window."""
        fig = item.data(0, QtCore.Qt.UserRole)
        if fig is None:
            return
        fig.show()
        fig.raise_()
        fig.activateWindow()
