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

"""WP-I3: the 'imshow' SeriesKind (lafigure/kinds/imshow.py) -- heatmap/
image + colorbar. See that module's docstring for the axis-order and
colorbar-attachment design decisions this file's tests defend."""
import numpy as np
import pyqtgraph as pg

from lafigure.axes import Axes
from lafigure.kinds.imshow import ImshowKind
from lafigure.series import SERIES_KINDS, Series
from tests.helpers import app, m


def _figure_with_axes():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    return f, Axes(f, p), p


def test_imshow_kind_is_registered_with_only_copy_capability():
    kind = SERIES_KINDS['imshow']
    assert isinstance(kind, ImshowKind) and kind.name == 'imshow'
    assert kind.capabilities == frozenset({'copy'})


def test_ax_imshow_returns_a_series_and_adds_a_real_image_item_to_the_plot():
    f, ax, p = _figure_with_axes()
    matrix = np.arange(15).reshape(3, 5)
    s = ax.imshow(matrix)
    assert isinstance(s, Series) and s.kind == 'imshow'
    assert isinstance(s.item, pg.ImageItem)
    # Not a PlotDataItem/curve, so it doesn't show up in listDataItems() --
    # see the "hasattr(item, 'curve')" guard in series.py's _add_series --
    # but it IS really added to the subplot, via PlotItem.items.
    assert s.item not in p.listDataItems()
    assert s.item in p.items
    f.close()


def test_imshow_orientation_matches_the_documented_convention():
    """Documented convention (imshow.py's module docstring): axisOrder is
    'row-major', so item.image is byte-for-byte the input matrix (no
    transpose) -- matrix[row, col], row=axis0=vertical, col=axis1=
    horizontal, matching numpy/matplotlib indexing -- and the ViewBox is Y-
    inverted so row 0 draws at the top, matching matplotlib.pyplot.imshow's
    default (origin='upper'). Uses an asymmetric (3, 5) matrix so a
    transpose or axis swap would be caught."""
    f, ax, p = _figure_with_axes()
    matrix = np.arange(15).reshape(3, 5)
    s = ax.imshow(matrix)
    assert s.item.image.shape == (3, 5)
    assert np.array_equal(s.item.image, matrix)
    assert s.item.axisOrder == 'row-major'
    assert p.getViewBox().yInverted(), "row 0 must draw at the top, like matplotlib imshow"
    f.close()


def test_imshow_x_is_the_matrix_y_is_none():
    f, ax, p = _figure_with_axes()
    matrix = np.arange(15).reshape(3, 5)
    s = ax.imshow(matrix)
    assert np.array_equal(s.x, matrix)
    assert s.y is None
    f.close()


def test_imshow_x_is_read_only():
    f, ax, p = _figure_with_axes()
    matrix = np.arange(15).reshape(3, 5).astype(float)
    s = ax.imshow(matrix)
    try:
        s.x[0, 0] = 99
    except ValueError:
        pass
    else:
        raise AssertionError("Series.x must not let a caller write the display data")
    f.close()


def test_to_dict_create_round_trip_rebuilds_an_identical_image():
    f, ax, p = _figure_with_axes()
    matrix = np.arange(15).reshape(3, 5).astype(float)
    s = ax.imshow(matrix, cmap='viridis', levels=(0, 20))
    d = s.to_dict()
    assert d['kind'] == 'imshow'
    assert d['y'] is None
    matrix[:] = -1  # the dict must not alias the caller's array
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert np.array_equal(s2.item.image, np.arange(15).reshape(3, 5))
    assert s2.item.axisOrder == 'row-major'
    assert tuple(s2.item.getLevels()) == (0, 20)
    assert getattr(s2.item, '_lafigure_cmap', None) == 'viridis'
    f.close()


def test_to_dict_style_carries_the_colormap_name_and_levels():
    f, ax, p = _figure_with_axes()
    matrix = np.arange(6).reshape(2, 3)
    s = ax.imshow(matrix, cmap='plasma')
    d = s.to_dict()
    assert d['style']['cmap'] == 'plasma'
    assert d['style']['levels'] is not None  # autoscaled from the data
    f.close()


def test_imshow_attaches_a_visible_colorbar_to_the_same_subplot():
    """ColorBarItem.setImageItem(item, insert_in=plot_item) inserts the bar
    into PlotItem's OWN internal layout (its axes/title grid) -- not
    lafigure's fractional grid -- so this needs no layout.py change. Check
    it landed there for real: present in that layout, parented to the same
    PlotItem, visible, with real on-screen geometry once shown."""
    f, ax, p = _figure_with_axes()
    matrix = np.arange(15).reshape(3, 5)
    s = ax.imshow(matrix)
    cb = s.item._lafigure_colorbar
    assert isinstance(cb, pg.ColorBarItem)
    in_layout = any(cb is p.layout.itemAt(i) for i in range(p.layout.count()))
    assert in_layout, "the colorbar must be inserted into the subplot's own layout"
    assert cb.parentItem() is p
    assert cb.isVisible()
    f.show()
    app.processEvents()
    geom = cb.geometry()
    assert geom.width() > 0 and geom.height() > 0, "the colorbar must have real on-screen geometry"
    f.close()


def test_imshow_accepts_a_colormap_instance_not_just_a_name():
    f, ax, p = _figure_with_axes()
    matrix = np.arange(6).reshape(2, 3)
    cmap = pg.colormap.get('plasma')
    s = ax.imshow(matrix, cmap=cmap)
    assert s.item.getColorMap() is not None
    f.close()


def test_set_xy_replaces_the_image_data():
    f, ax, p = _figure_with_axes()
    matrix = np.arange(6).reshape(2, 3)
    s = ax.imshow(matrix)
    kind = SERIES_KINDS['imshow']
    new_matrix = np.arange(6, 12).reshape(2, 3)
    kind.set_xy(s.item, new_matrix, None)
    assert np.array_equal(s.item.image, new_matrix)
    assert np.array_equal(s.x, new_matrix)
    f.close()
