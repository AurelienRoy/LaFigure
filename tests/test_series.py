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

"""Series / SeriesKind registry and _add_series (series.py)."""
import ast
import glob
import os

import numpy as np
import pyqtgraph as pg

from lafigure.datasource import DataSource
from lafigure.series import (
    SERIES_KINDS, Series, SeriesKind, LineKind, register_series_kind,
)
from tests.helpers import m, first_curve, shown_figure


# Series construction sites that once lived in files this package didn't
# own -- the coordinator applied WP-H's reported diffs for layout.py and
# brushing.py, so this is empty. Anything calling .plot( outside series.py
# is a new bypass of _add_series.
_PENDING_MIGRATION = {}


def _construction_sites(text):
    """Count `<anything>.plot(...)` calls and PlotDataItem(...) constructions,
    by AST so docstrings/comments mentioning them don't count."""
    n = 0
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in ('plot', 'PlotDataItem'):
            n += 1
        elif isinstance(f, ast.Name) and f.id == 'PlotDataItem':
            n += 1
    return n


def test_add_series_is_the_only_series_construction_site():
    """_add_series is where a new series gets its kind bookkeeping and is
    made clickable; a second construction site would silently bypass that.
    Scans every module of the package."""
    package_dir = os.path.dirname(m.__file__)
    sites = {}
    for path in glob.glob(os.path.join(package_dir, '*.py')):
        with open(path, encoding='utf-8') as fh:
            n = _construction_sites(fh.read())
        if n:
            sites[os.path.basename(path)] = n
    expected = dict(_PENDING_MIGRATION, **{'series.py': 1})
    assert sites == expected, f"a new series construction site bypasses _add_series: {sites}"
    with open(os.path.join(package_dir, 'series.py'), encoding='utf-8') as fh:
        assert 'def _add_series' in fh.read()  # control: the scan is reading the right file


def _figure_with_plot():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    return f, p


def test_line_kind_is_registered_with_the_curve_capabilities():
    kind = SERIES_KINDS['line']
    assert isinstance(kind, LineKind) and kind.name == 'line'
    assert {'brush', 'fft', 'remove_average', 'fit', 'copy'} <= set(kind.capabilities)


def test_register_series_kind_adds_a_kind():
    class Dummy(SeriesKind):
        name = '_test_dummy'
        capabilities = frozenset()
    try:
        register_series_kind(Dummy())
        assert isinstance(SERIES_KINDS['_test_dummy'], Dummy)
    finally:
        SERIES_KINDS.pop('_test_dummy', None)


def test_add_series_makes_a_real_clickable_plot_data_item():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'line', [0, 1, 2], [3, 4, 5], pen=pg.mkPen('b'), name='abc')
    assert isinstance(s, Series) and s.kind == 'line'
    assert isinstance(s.item, pg.PlotDataItem) and s.item in p.listDataItems()
    assert s.item.curve.clickable, "_add_series must wire the curve clickable"
    assert s.item.name() == 'abc'
    assert f._series_of(s.item) is s, "the item maps back to the same Series"
    f.close()


def test_to_dict_create_round_trip():
    f, p = _figure_with_plot()
    x, y = np.linspace(0, 1, 50), np.linspace(0, 1, 50) ** 2
    pen = pg.mkPen((10, 20, 30), width=3)
    s = f._add_series(p, 'line', x, y, pen=pen, name='sq', clip_to_view=True, downsample='peak')
    d = s.to_dict()
    assert d['kind'] == 'line'
    x[:] = -1  # the dict must not alias the caller's arrays
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert np.array_equal(s2.x, np.linspace(0, 1, 50)) and np.array_equal(s2.y, s.y)
    assert s2.item.name() == 'sq'
    assert pg.mkPen(s2.item.opts['pen']).color() == pen.color()
    assert pg.mkPen(s2.item.opts['pen']).width() == 3
    assert s2.item.opts['clipToView'] and s2.item.opts['autoDownsample']
    assert s2.item.opts['downsampleMethod'] == 'peak'
    f.close()


def test_to_dict_uses_the_unhighlighted_pen():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'line', [0, 1], [0, 1], pen=pg.mkPen('b', width=1))
    f._select_curve(s.item)
    assert pg.mkPen(s.item.opts['pen']).width() > 1  # control: highlighted now
    assert pg.mkPen(s.to_dict()['pen']).width() == 1
    f.close()


def test_series_x_y_are_read_only():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'line', [0.0, 1.0, 2.0], [3.0, 4.0, 5.0])
    for arr in (s.x, s.y):
        try:
            arr[0] = 99
        except ValueError:
            pass
        else:
            raise AssertionError("Series.x/.y must not let a caller write the display data")
    assert s.item.xData[0] == 0.0 and s.item.yData[0] == 3.0
    f.close()


def test_set_data_is_undoable():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'line', [0.0, 1.0], [2.0, 3.0])
    n_undo = len(f.undo_stack)
    s.set_data([0.0, 1.0, 2.0], [5.0, 6.0, 7.0])
    assert list(s.y) == [5.0, 6.0, 7.0] and len(f.undo_stack) == n_undo + 1
    f.undo()
    assert list(s.x) == [0.0, 1.0] and list(s.y) == [2.0, 3.0]
    f.redo()
    assert list(s.y) == [5.0, 6.0, 7.0]
    f.close()


def test_plain_array_series_has_a_private_data_source():
    f, p = _figure_with_plot()
    s = f._add_series(p, 'line', [0.0, 1.0, 2.0], [3.0, 4.0, 5.0])
    assert isinstance(s.source, DataSource)
    assert s.rows is None
    assert list(s.source['x']) == [0.0, 1.0, 2.0] and list(s.source['y']) == [3.0, 4.0, 5.0]
    s.set_data([7.0], [8.0])
    assert list(s.source['y']) == [8.0], "a private source follows the series' data"
    f.close()


def test_series_from_the_same_source_share_it():
    f, p = _figure_with_plot()
    src = DataSource({'t': np.arange(5.0), 'a': np.arange(5.0) * 2, 'b': np.arange(5.0) * 3})
    s1 = f._add_series(p, 'line', src['t'], src['a'], source=src, columns=('t', 'a'))
    s2 = f._add_series(p, 'line', src['t'][1:4], src['b'][1:4], source=src, rows=[1, 2, 3],
                       columns=('t', 'b'))
    assert s1.source is s2.source is src
    assert list(s1.rows) == [0, 1, 2, 3, 4] and list(s2.rows) == [1, 2, 3]
    # Same-length set_data keeps the row link (the rows are still those
    # points); a different length can't, so the series detaches.
    s2.set_data(s2.x, s2.y + 1)
    assert s2.source is src and list(s2.rows) == [1, 2, 3]
    s2.set_data([0.0], [0.0])
    assert s2.source is not src and s2.rows is None
    f.undo()
    assert s2.source is src and list(s2.rows) == [1, 2, 3], "undo restores the link"
    f.close()


def test_copy_paste_keeps_a_series_linked_to_its_source():
    f, p = _figure_with_plot()
    src = DataSource({'t': np.arange(5.0), 'a': np.arange(5.0) * 2})
    s = f._add_series(p, 'line', src['t'], src['a'], source=src, columns=('t', 'a'))
    f._select_curve(s.item)
    f.copy_curve()
    q = f.add_subplot(row=1, col=0)
    f.focused_plot = q
    f.paste_curve()
    pasted = f._series_on(q)
    assert len(pasted) == 1 and pasted[0].source is src and list(pasted[0].rows) == list(range(5))
    f.close()


def test_legacy_plot_data_item_gets_a_line_series():
    """An item made outside _add_series (a test's p.plot, until the
    pending migrations land) is still seen as a 'line' Series."""
    f, p = _figure_with_plot()
    item = p.plot([0, 1], [1, 2])
    s = f._series_of(item)
    assert s.kind == 'line' and s.item is item and f._series_of(item) is s
    assert [x.item for x in f._series_on(p)] == [item]
    f.close()


def test_demo_curves_are_series_with_millions_of_points_settings():
    f = shown_figure()
    s = f._series_of(first_curve(f.plots[0]))
    assert s.kind == 'line'
    assert s.item.opts['clipToView'] and s.item.opts['autoDownsample']
    f.close()


def test_remove_average_goes_through_set_data_as_one_undo_entry():
    f, p = _figure_with_plot()
    f._add_series(p, 'line', [0.0, 1.0], [1.0, 3.0])
    f._add_series(p, 'line', [0.0, 1.0], [10.0, 20.0])
    f.focused_plot = p
    n_undo = len(f.undo_stack)
    f.remove_average()
    assert len(f.undo_stack) == n_undo + 1
    assert [list(s.y) for s in f._series_on(p)] == [[-1.0, 1.0], [-5.0, 5.0]]
    f.undo()
    assert [list(s.y) for s in f._series_on(p)] == [[1.0, 3.0], [10.0, 20.0]]
    f.close()


def test_fft_curve_is_a_line_series_and_survives_undo_redo():
    f = shown_figure()
    f._on_plot_clicked(f.plots[1])
    f.fft_below()
    fft_plot = f.plots[-1]
    (s,) = f._series_on(fft_plot)
    assert s.kind == 'line' and s.item.curve.clickable
    mag = s.y.copy()
    f.undo()
    f.redo()
    (s2,) = f._series_on(f.plots[-1])
    assert np.array_equal(s2.y, mag) and s2.item.curve.clickable
    f.close()


def test_paste_subplot_rebuilds_series_from_dicts():
    f = shown_figure()
    p0 = f.plots[0]
    f._on_plot_clicked(p0)
    f.copy_subplot()
    d = f.clipboard.subplot[0]['series']
    assert len(d) == 1 and d[0]['kind'] == 'line'
    f.paste_subplot()
    (s,) = f._series_on(f.plots[-1])
    assert np.array_equal(s.y, first_curve(p0).yData) and s.item.curve.clickable
    f.close()


# -- coordinator addition (wave 3 prep): a kind whose item isn't a
# PlotDataItem must not crash _add_series -- I2 (bar/errorbar) and I3
# (heatmap) will build exactly this kind of item (BarGraphItem, ImageItem).
class _NoClickableProtocolKind(SeriesKind):
    """An item with no .curve at all -- like BarGraphItem/ImageItem, unlike
    every kind so far, which stayed PlotDataItem-based."""
    name = 'test_no_curve'
    capabilities = frozenset()

    def create(self, plot_item, x, y, pen=None, name=None, source=None, rows=None, **style):
        item = pg.BarGraphItem(x=x, height=y, width=0.5)
        plot_item.addItem(item)
        return item

    def to_dict(self, item):
        return {'x': [], 'y': [], 'pen': None, 'name': None, 'style': {}}

    def get_xy(self, item):
        return np.asarray(item.opts.get('x', [])), np.asarray(item.opts.get('height', []))


register_series_kind(_NoClickableProtocolKind())


def test_add_series_does_not_crash_for_an_item_without_a_curve_attribute():
    f = shown_figure()
    p0 = f.plots[0]
    s = f._add_series(p0, 'test_no_curve', [1, 2, 3], [4, 5, 6])
    assert s.kind == 'test_no_curve'
    assert list(s.x) == [1, 2, 3] and list(s.y) == [4, 5, 6]
    f.close()
