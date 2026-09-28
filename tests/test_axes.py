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

"""The Axes facade, fig.subplot(), gca()/gcf() (axes.py)."""
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

from lafigure.axes import Axes, gca, gcf
from lafigure.datasource import DataSource
from lafigure.series import Series
from tests.helpers import app, m, _mouse, _click_subplot


def _shown_empty():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    return f


def test_subplot_returns_an_axes_on_a_new_subplot():
    f = _shown_empty()
    ax = f.subplot(0, 0, title="T")
    assert isinstance(ax, Axes)
    assert ax.plot_item in f.plots and ax.figure is f
    assert ax.plot_item.titleLabel.text == "T"
    assert ax.series == []
    f.close()


def test_plot_arrays_returns_a_series_listed_by_the_axes():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.plot(np.arange(10.0), np.arange(10.0) ** 2, name="sq")
    assert isinstance(s, Series) and s.kind == 'line'
    assert isinstance(s.item, pg.PlotDataItem) and s.item.name() == "sq"
    assert ax.series == [s]
    assert isinstance(s.source, DataSource) and s.rows is None
    s2 = ax.plot(np.arange(3.0))  # MATLAB-style plot(y): x = 0..n-1
    assert list(s2.x) == [0.0, 1.0, 2.0]
    assert ax.series == [s, s2]
    assert pg.mkPen(s.item.opts['pen']).color() != pg.mkPen(s2.item.opts['pen']).color(), \
        "default pens cycle colors"
    f.close()


def test_plotted_series_is_selected_by_a_real_click():
    """Real mouse events to the viewport: the item ax.plot made is a
    genuine clickable PlotDataItem that selection_ui highlights."""
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.plot(np.linspace(0, 10, 101), np.zeros(101), pen=pg.mkPen('b', width=1))
    app.processEvents()
    pt = ax.plot_item.getViewBox().mapViewToScene(QtCore.QPointF(5, 0))
    L = QtCore.Qt.LeftButton
    _mouse(f, QtCore.QEvent.MouseButtonPress, pt, L)
    _mouse(f, QtCore.QEvent.MouseButtonRelease, pt, QtCore.Qt.NoButton)
    assert f.selected_curves == [s.item], f.selected_curves
    assert pg.mkPen(s.item.opts['pen']).width() > 1, "a selected curve gets the thicker pen"
    f.close()


def test_plot_from_a_shared_data_source():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    src = DataSource({'t': np.arange(6.0), 'a': np.arange(6.0) * 2, 'b': -np.arange(6.0)})
    sa = ax.plot(src, x='t', y='a')
    sb = ax.plot(src, x='t', y='b', rows=[2, 3, 4])
    assert sa.source is sb.source is src
    assert list(sa.rows) == list(range(6)) and list(sb.rows) == [2, 3, 4]
    assert list(sa.y) == [0, 2, 4, 6, 8, 10] and list(sb.y) == [-2, -3, -4]
    assert list(sb.x) == [2, 3, 4]
    assert ax.series == [sa, sb]
    f.close()


def test_plot_from_a_source_requires_column_names():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    src = DataSource({'t': np.arange(3.0)})
    try:
        ax.plot(src, y='t')
    except TypeError:
        pass
    else:
        raise AssertionError("a DataSource plot needs both x= and y= column names")
    f.close()


def test_axes_series_is_derived_live_from_the_plot():
    f = _shown_empty()
    ax = f.subplot(0, 0)
    s = ax.plot([0.0, 1.0], [0.0, 1.0])
    f.delete_curve(s.item)
    assert ax.series == []
    f.undo()
    (restored,) = ax.series
    assert list(restored.y) == [0.0, 1.0]
    f.close()


def test_gcf_and_gca_follow_the_focused_figure_and_subplot():
    f1 = _shown_empty()
    ax1 = f1.subplot(0, 0)
    f2 = _shown_empty()
    ax2a = f2.subplot(0, 0)
    ax2b = f2.subplot(0, 1)
    assert gcf() is f2, "a newly opened figure is the current one"
    _click_subplot(f2, ax2b.plot_item)
    assert gca() == ax2b and gca().plot_item is ax2b.plot_item
    _click_subplot(f1, ax1.plot_item)
    assert gcf() is f1 and gca() == ax1
    f1.close()
    assert gcf() is f2, "a closed figure is never current"
    f2.close()
    assert ax2a != ax2b


def test_gca_is_none_without_a_subplot():
    f = _shown_empty()
    assert gcf() is f and gca() is None
    f.close()
