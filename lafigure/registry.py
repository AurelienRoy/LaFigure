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

"""Process-wide registry of open LaFigure windows.

A single shared QObject instance (get_registry()) that every LaFigure
registers itself with on creation and unregisters from on close. FigureManager
listens to its signals to keep its tree of figures/subplots in sync, instead
of polling. Kept separate from LaFigure itself so figure.py doesn't need
to know about FigureManager (or vice versa) -- both only depend on this.
"""
from pyqtgraph.Qt import QtCore

_registry = None


class FigureRegistry(QtCore.QObject):
    figureOpened = QtCore.Signal(object)       # emits the LaFigure
    figureClosed = QtCore.Signal(object)
    subplotsChanged = QtCore.Signal(object)    # emits the LaFigure whose subplots changed

    def __init__(self):
        super().__init__()
        self.figures = []

    def register(self, figure):
        self.figures.append(figure)
        self.figureOpened.emit(figure)

    def unregister(self, figure):
        if figure in self.figures:
            self.figures.remove(figure)
            self.figureClosed.emit(figure)

    def notify_subplots_changed(self, figure):
        self.subplotsChanged.emit(figure)


def get_registry():
    global _registry
    if _registry is None:
        _registry = FigureRegistry()
    return _registry
