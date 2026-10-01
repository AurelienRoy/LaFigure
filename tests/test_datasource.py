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

"""DataSource (datasource.py): pure-numpy, no Qt at all -- deliberately
importable and runnable without QT_QPA_PLATFORM/offscreen/QApplication.
See PLAN.md's note for package F: this must stay usable from a plain
console with only numpy installed, and fast for millions of rows.
"""
import time

import numpy as np

from lafigure.datasource import DataSource

try:
    import pandas as pd
except ImportError:
    pd = None


def _sample_dict(n=10):
    return {
        'x': np.arange(n, dtype=float),
        'y': np.arange(n, dtype=float) * 2.0,
        'label': np.array([f"p{i}" for i in range(n)], dtype=object),
    }


def test_construction_from_dict():
    src = DataSource(_sample_dict(5))
    assert len(src) == 5
    assert src.n_rows == 5
    assert set(src.columns) == {'x', 'y', 'label'}
    assert np.array_equal(src['x'], [0, 1, 2, 3, 4])
    assert np.array_equal(src['y'], [0, 2, 4, 6, 8])


def test_construction_from_dataframe_matches_dict():
    if pd is None:
        print("pandas not installed -- skipping DataFrame construction test")
        return
    data = _sample_dict(5)
    src_dict = DataSource(data)
    src_df = DataSource(pd.DataFrame(data))
    assert set(src_df.columns) == set(src_dict.columns)
    for col in src_dict.columns:
        assert np.array_equal(src_df[col], src_dict[col])


def test_columns_are_read_only():
    src = DataSource(_sample_dict(5))
    arr = src['x']
    assert arr.flags.writeable is False
    try:
        arr[0] = 999.0
        assert False, "expected assigning into a returned column to raise"
    except ValueError:
        pass
    # the underlying source data must be untouched
    assert src['x'][0] == 0.0


def test_add_column_validates_length():
    src = DataSource(_sample_dict(5))
    src.add_column('z', np.arange(5) * 3.0)
    assert np.array_equal(src['z'], [0, 3, 6, 9, 12])

    try:
        src.add_column('bad', np.arange(3))
        assert False, "expected mismatched-length add_column to raise"
    except ValueError:
        pass
    assert 'bad' not in src.columns


def test_add_column_copies_not_aliases():
    src = DataSource(_sample_dict(5))
    original = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    src.add_column('z', original)
    original[0] = -1.0
    assert src['z'][0] == 1.0


def test_filter_with_boolean_array():
    src = DataSource(_sample_dict(10))
    mask = src['x'] % 2 == 0
    src.filter(np.asarray(mask))
    assert np.array_equal(src.visible_rows, [0, 2, 4, 6, 8])
    src.filter(None)
    assert np.array_equal(src.visible_rows, np.arange(10))


def test_filter_with_string_expression():
    src = DataSource(_sample_dict(10))
    src.filter("(x > 2) & (y < 15)")
    # x>2 -> rows 3..9; y<15 -> y=2x<15 -> x<7.5 -> rows 0..7
    # intersection -> rows 3..7
    assert np.array_equal(src.visible_rows, [3, 4, 5, 6, 7])

    src.filter("np.sin(x) > 2")  # never true -- exercises np in scope
    assert len(src.visible_rows) == 0

    src.filter(None)
    assert np.array_equal(src.visible_rows, np.arange(10))


def test_filter_mask_property():
    src = DataSource(_sample_dict(5))
    assert src.filter_mask is None
    src.filter(np.array([True, False, True, False, True]))
    assert np.array_equal(src.filter_mask, [True, False, True, False, True])
    assert src.filter_mask.flags.writeable is False


def test_hide_show_independent_of_filter():
    src = DataSource(_sample_dict(10))
    src.hide_rows([1, 2])
    assert np.array_equal(src.visible_rows, [0, 3, 4, 5, 6, 7, 8, 9])

    # unrelated filter -- visible_rows must be the intersection
    src.filter(src['x'] < 5)
    assert np.array_equal(src.visible_rows, [0, 3, 4])

    src.show_rows([2])
    assert np.array_equal(src.visible_rows, [0, 2, 3, 4])

    src.show_all()
    assert np.array_equal(src.visible_rows, [0, 1, 2, 3, 4])  # filter alone


def test_hidden_mask_property():
    src = DataSource(_sample_dict(5))
    src.hide_rows([0, 4])
    assert np.array_equal(src.hidden_mask, [True, False, False, False, True])
    assert src.hidden_mask.flags.writeable is False
    src.show_all()
    assert not src.hidden_mask.any()


def test_on_change_fires_once_and_off_change_stops_it():
    src = DataSource(_sample_dict(5))
    calls = []
    cb = lambda: calls.append(1)
    src.on_change(cb)

    src.add_column('z', np.zeros(5))
    assert len(calls) == 1
    src.filter(src['x'] > 1)
    assert len(calls) == 2
    src.hide_rows([0])
    assert len(calls) == 3
    src.show_rows([0])
    assert len(calls) == 4
    src.show_all()
    assert len(calls) == 5
    src.filter(None)
    assert len(calls) == 6

    src.off_change(cb)
    src.filter(src['x'] > 0)
    assert len(calls) == 6  # unchanged -- callback was removed


def test_notify_change_fires_listeners_without_touching_any_mask():
    """notify_change() is for a caller that changed something ABOUT this
    source's rows without the source itself being able to tell (e.g.
    brushing.py's delete_brushed_points, which narrows a *series'* own
    drawn rows, never this source) -- it must wake up on_change
    subscribers exactly like a real mutation does, but leave n_rows,
    filter_mask and hidden_mask completely untouched."""
    src = DataSource(_sample_dict(5))
    calls = []
    src.on_change(lambda: calls.append(1))

    n_before = len(src)
    filter_before = src.filter_mask
    hidden_before = np.array(src.hidden_mask)

    src.notify_change()

    assert len(calls) == 1
    assert len(src) == n_before
    assert src.filter_mask is filter_before or (filter_before is None and src.filter_mask is None)
    assert np.array_equal(src.hidden_mask, hidden_before)


def test_multiple_listeners_independent():
    src = DataSource(_sample_dict(5))
    a_calls, b_calls = [], []
    a = lambda: a_calls.append(1)
    b = lambda: b_calls.append(1)
    src.on_change(a)
    src.on_change(b)
    src.filter(None)
    assert len(a_calls) == 1 and len(b_calls) == 1
    src.off_change(a)
    src.filter(None)
    assert len(a_calls) == 1 and len(b_calls) == 2


def test_row_index_is_the_point_id_no_extra_column():
    # A DataSource never invents an id column -- row i of every column
    # IS point i, by construction; a caller wanting a user-facing id
    # just stores one as an ordinary column.
    data = _sample_dict(5)
    data['drone_timestamp'] = np.array([100, 101, 102, 103, 104])
    src = DataSource(data)
    assert 'id' not in src.columns
    assert src['drone_timestamp'][3] == 103
    assert src['x'][3] == 3.0  # same row -- same point


def test_million_rows_is_fast():
    n = 1_000_000
    rng = np.random.default_rng(0)
    data = {'x': np.arange(n, dtype=float), 'y': rng.standard_normal(n)}

    t0 = time.perf_counter()
    src = DataSource(data)
    src.filter("y > 0")
    visible = src.visible_rows
    elapsed = time.perf_counter() - t0

    assert src.n_rows == n
    assert len(visible) > 0
    assert elapsed < 2.0, f"1M-row construct+filter+visible_rows took {elapsed:.3f}s"
