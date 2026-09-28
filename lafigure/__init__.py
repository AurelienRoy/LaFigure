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

"""lafigure -- a MATLAB-Figure-like interactive plotting library,
built on PyQtGraph (Qt + OpenGL) so it stays fluent with millions of points.

Run as an app:
    python3 -m lafigure

Use as a library:
    from lafigure import LaFigure, FigureManager
    app = QtWidgets.QApplication([])
    fig = LaFigure()          # a demo figure with sample subplots
    empty_fig = LaFigure(empty=True)  # a blank figure, no subplots
    fig.add_subplot(row=0, col=0, title="My data")
    fig.show()
    app.exec()

See CLAUDE.md for the design lessons behind this package's structure.
"""
from .figure import LaFigure
from .manager import FigureManager
from .selection import SelectionModel, LinkedScatter
from .registry import get_registry, FigureRegistry
from .clipboard import get_clipboard, Clipboard
from .annotations import AnnotationItem, SHAPE_KINDS
from .datasource import DataSource
from .series import Series, SeriesKind, register_series_kind, SERIES_KINDS
from .axes import Axes, gca, gcf
from .kinds import bar, errorbar, imshow  # noqa: F401  (registers 'bar'/'errorbar'/'imshow')
from .app import main

__all__ = [
    "LaFigure",
    "FigureManager",
    "SelectionModel",
    "LinkedScatter",
    "get_registry",
    "FigureRegistry",
    "get_clipboard",
    "Clipboard",
    "AnnotationItem",
    "SHAPE_KINDS",
    "DataSource",
    "Series",
    "SeriesKind",
    "register_series_kind",
    "SERIES_KINDS",
    "Axes",
    "gca",
    "gcf",
    "main",
]
