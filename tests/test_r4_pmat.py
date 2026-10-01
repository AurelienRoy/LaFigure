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

"""lafigure.plotmatrix -- R4-PMAT."""
import numpy as np

from lafigure.datasource import DataSource
from lafigure.plotmatrix import plotmatrix
from tests.helpers import app, m, _brush_drag  # noqa: F401  (app: keep the QApplication alive)


def _cols(n=3, size=60):
    """n columns of evenly spaced, distinguishable data -- brushing a
    predictable range always catches a known, non-empty subset."""
    return {f"c{i}": np.linspace(0, size - 1, size) + i * 1000 for i in range(n)}


def test_plotmatrix_from_dict_builds_n_squared_grid_at_the_right_cells():
    f = m.LaFigure(empty=True)
    data = _cols(3)
    axes = plotmatrix(data, figure=f)
    try:
        assert len(axes) == 9
        assert len(f.plots) == 9
        cols = ['c0', 'c1', 'c2']
        for i, ycol in enumerate(cols):
            for j, xcol in enumerate(cols):
                ax = axes[i * 3 + j]
                # boxes[plot_item] = (left, top, right, bottom) in (col, row) units.
                assert f.boxes[ax.plot_item] == (j, i, j + 1, i + 1), (i, j, f.boxes[ax.plot_item])
    finally:
        f.close()


def test_plotmatrix_diagonal_is_a_histogram_off_diagonal_is_the_requested_kind():
    f = m.LaFigure(empty=True)
    data = _cols(3)
    axes = plotmatrix(data, figure=f, kind='scatter', diagonal='hist')
    try:
        for i in range(3):
            for j in range(3):
                ax = axes[i * 3 + j]
                series = f._series_on(ax.plot_item)
                assert len(series) == 1, (i, j, series)
                s = series[0]
                if i == j:
                    assert s.kind == 'hist', (i, j, s.kind)
                    assert s.columns == (f"c{j}",)
                else:
                    assert s.kind == 'scatter', (i, j, s.kind)
                    assert s.columns == (f"c{j}", f"c{i}")
    finally:
        f.close()


def test_plotmatrix_diagonal_none_leaves_diagonal_cells_empty():
    f = m.LaFigure(empty=True)
    data = _cols(3)
    axes = plotmatrix(data, figure=f, diagonal=None)
    try:
        for i in range(3):
            ax = axes[i * 3 + i]
            assert f._series_on(ax.plot_item) == []
        # control: off-diagonal cells still got their series
        assert f._series_on(axes[1].plot_item) != []
    finally:
        f.close()


def test_plotmatrix_kind_line_uses_the_line_kind():
    f = m.LaFigure(empty=True)
    data = _cols(2)
    axes = plotmatrix(data, figure=f, kind='line', diagonal=None)
    try:
        off_diag = axes[1]  # row 0, col 1
        series = f._series_on(off_diag.plot_item)
        assert len(series) == 1 and series[0].kind == 'line'
    finally:
        f.close()


def test_plotmatrix_off_diagonal_series_all_share_the_same_datasource():
    """The whole point: no per-cell private copy -- every off-diagonal
    series' .source is the identical DataSource object."""
    f = m.LaFigure(empty=True)
    data = _cols(3)
    axes = plotmatrix(data, figure=f)
    try:
        sources = []
        for i in range(3):
            for j in range(3):
                if i == j:
                    continue
                s = f._series_on(axes[i * 3 + j].plot_item)[0]
                sources.append(s.source)
        assert all(src is sources[0] for src in sources), "every off-diagonal series must share one DataSource"
    finally:
        f.close()


def test_plotmatrix_accepts_a_datasource_directly_without_copying_it():
    f = m.LaFigure(empty=True)
    src = DataSource(_cols(3))
    axes = plotmatrix(src, figure=f)
    try:
        s = f._series_on(axes[1].plot_item)[0]  # row 0, col 1: off-diagonal
        assert s.source is src
    finally:
        f.close()


def test_plotmatrix_accepts_a_2d_array_with_explicit_column_names():
    f = m.LaFigure(empty=True)
    arr = np.column_stack([np.arange(10), np.arange(10) * 2, np.arange(10) * 3])
    axes = plotmatrix(arr, columns=['a', 'b', 'c'], figure=f)
    try:
        s = f._series_on(axes[1].plot_item)[0]  # row 0, col 1 -> x='b', y='a'
        assert s.columns == ('b', 'a')
        assert 'a' in s.source.columns and 'b' in s.source.columns and 'c' in s.source.columns
    finally:
        f.close()


def test_plotmatrix_2d_array_without_columns_gets_default_names():
    f = m.LaFigure(empty=True)
    arr = np.column_stack([np.arange(5), np.arange(5) * 2])
    axes = plotmatrix(arr, figure=f)
    try:
        s = f._series_on(axes[1].plot_item)[0]
        assert s.columns == ('col1', 'col0')
    finally:
        f.close()


def test_plotmatrix_columns_param_subsets_a_datasource():
    f = m.LaFigure(empty=True)
    src = DataSource(_cols(4))
    axes = plotmatrix(src, columns=['c0', 'c2'], figure=f)
    try:
        assert len(axes) == 4
        s = f._series_on(axes[1].plot_item)[0]
        assert s.columns == ('c2', 'c0')
    finally:
        f.close()


def test_plotmatrix_without_a_figure_creates_a_new_empty_one():
    axes = plotmatrix(_cols(2), diagonal=None)
    try:
        fig = axes[0].figure
        assert isinstance(fig, m.LaFigure)
        assert len(fig.plots) == 4
    finally:
        axes[0].figure.close()


def test_plotmatrix_rejects_a_1d_array():
    try:
        plotmatrix(np.arange(10))
        assert False, "a 1-D array must raise"
    except TypeError:
        pass


def test_plotmatrix_rejects_mismatched_columns_length_for_an_array():
    try:
        plotmatrix(np.column_stack([np.arange(5), np.arange(5)]), columns=['only_one'])
        assert False, "a columns= list of the wrong length must raise"
    except ValueError:
        pass


# -- the actual point: brushing links every cell through the shared source --
def test_brushing_one_off_diagonal_cell_links_rows_on_another_cell():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    size = 60
    data = _cols(3, size=size)  # c0 in [0, 59], c1 in [1000, 1059], c2 in [2000, 2059]
    axes = plotmatrix(data, figure=f, diagonal=None)
    try:
        cell_01 = axes[1].plot_item   # row 0, col 1: x=c1, y=c0
        cell_10 = axes[3].plot_item   # row 1, col 0: x=c0, y=c1

        # Known data ranges (not the possibly-not-yet-settled autoRange) --
        # a real drag is driven by the CURRENT screen, but here what matters
        # is catching a predictable, non-empty subset, so pin the range
        # explicitly rather than racing pyqtgraph's own lazy auto-range.
        vb01 = cell_01.getViewBox()
        vb01.setRange(xRange=(1000, 1000 + size - 1), yRange=(0, size - 1), padding=0)
        app.processEvents()

        f.brush_action.trigger()

        mid = 1000 + (size - 1) / 2
        _brush_drag(f, cell_01, (1000, 0), (mid, size - 1))

        brushed_01 = f._brushers[cell_01]
        assert brushed_01.has_selection(), "control: the drag on cell (0,1) selected something"
        rows_01 = sorted(set(np.concatenate(list(brushed_01.selection.values())).tolist()))
        assert rows_01, "control: some rows were actually caught"

        brushed_10 = f._brushers[cell_10]
        assert brushed_10.has_selection(), "brushing cell (0,1) must also select rows on cell (1,0)"
        rows_10 = sorted(set(np.concatenate(list(brushed_10.selection.values())).tolist()))
        assert rows_10 == rows_01, (
            "the two cells share one DataSource: the SAME rows must be highlighted on both",
            rows_01, rows_10,
        )
    finally:
        f.close()


def test_brushing_off_when_no_cell_is_brushed_has_no_stray_selection():
    f = m.LaFigure(empty=True)
    data = _cols(3)
    axes = plotmatrix(data, figure=f, diagonal=None)
    try:
        for ax in axes:
            assert not f._brushers[ax.plot_item].has_selection()
    finally:
        f.close()
