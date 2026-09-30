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

"""DataSource -- a shared columnar table underlying one or more Series.

This is the data-model foundation for CLAUDE.md's Phase 2 ("DataSource +
Series kinds + console API"): "a shared columnar table (dict of numpy
arrays, or from a pandas DataFrame; pandas optional). A point's ID is its
row index; user IDs (database key, drone log, timestamp, ...) are just
columns. Series sharing a source are linked."

**No Qt import anywhere in this module, on purpose** (see PLAN.md's note
for package F): this needs to be usable from a plain console/script with
only numpy installed, and it needs to run fast enough for millions of
rows without the overhead or event-loop requirements of Qt signals. Later
packages (H, J, L, N) build `Series`/undo/UI machinery on top of this.

Design decisions worth calling out explicitly, since later packages code
directly against this shape:

- **Row index IS the point ID.** There is no separate "id" column
  created or required -- `source[col][i]` and row `i` are the same point
  everywhere, by construction. A caller who wants a *user-facing* id
  (database key, timestamp, ...) just stores it as an ordinary column and
  looks it up by row index like any other column; DataSource itself never
  interprets such a column specially.
- **Two independent, composable visibility mechanisms**, both folded into
  `visible_rows`:
  - `filter(...)`: a single, wholesale, re-appliable mask -- meant for a
    live expression like `"speed > 5"` that replaces the previous filter
    entirely each time it's set. Cleared with `filter(None)`.
  - `hide_rows`/`show_rows`/`show_all`: an accumulating, individually
    revertible set of specific hidden rows -- meant for "Hide Brushed
    Points" (Phase 3, package J), where each hide/show is its own undo
    step touching only the rows that one brush drag caught. Kept
    deliberately separate from `filter` rather than folded into the same
    mask, because the two have different update granularity and
    lifetimes.
  A row is visible only if it passes *both* (logical AND).
- **Returned column arrays are read-only views** (`writeable=False`) so a
  caller can't silently corrupt source data by mutating what they got
  back from `source[col]`; `add_column` is the explicit, intentional way
  to write derived data (Remove Average / Transform / FFT results, per
  Phase 3's "write a new derived column (revertible)" bullet -- the
  "revertible" part is that package's undo layer calling `add_column`
  again / removing the column, not something this module does itself).
- **Change notification is a plain callback list**, not a Qt signal --
  `on_change`/`off_change`. Fires synchronously, once per call to
  `add_column`, `filter`, `hide_rows`, `show_rows` or `show_all` (even if
  that call didn't actually change anything observable -- e.g. setting
  the same filter twice both fire; callers that care about no-op
  suppression can compare `visible_rows` themselves). A later `Series`
  subscribes to re-derive its own visible points reactively.
"""
import numpy as np

try:
    import pandas as pd
except ImportError:  # pragma: no cover -- pandas is optional
    pd = None


class DataSource:
    """A shared columnar table. See module docstring for the full design.

    Parameters
    ----------
    data : dict[str, array-like] or pandas.DataFrame
        All dict values (or DataFrame columns) must have the same length.
        Stored internally as numpy arrays; dtype is inferred per column
        (numeric columns stay numeric, strings/objects/datetimes are kept
        as-is via `np.asarray`, not forced to float).
    """

    def __init__(self, data):
        if pd is not None and isinstance(data, pd.DataFrame):
            columns = {col: data[col].to_numpy() for col in data.columns}
        elif isinstance(data, dict):
            columns = {name: np.asarray(values) for name, values in data.items()}
        else:
            raise TypeError(
                "DataSource(data) expects a dict of array-like columns or a "
                f"pandas.DataFrame, got {type(data)!r}"
            )

        lengths = {name: len(arr) for name, arr in columns.items()}
        if lengths:
            n_rows = next(iter(lengths.values()))
            for name, length in lengths.items():
                if length != n_rows:
                    raise ValueError(
                        f"DataSource columns must all have the same length; "
                        f"column {name!r} has {length}, expected {n_rows}"
                    )
        else:
            n_rows = 0

        self._n_rows = n_rows
        self._columns = columns
        self._filter_mask = None  # bool array or None (unfiltered)
        self._hidden_mask = np.zeros(n_rows, dtype=bool)
        self._listeners = []

    # -- basic table protocol ------------------------------------------------

    @property
    def n_rows(self):
        return self._n_rows

    def __len__(self):
        return self._n_rows

    @property
    def columns(self):
        """Tuple of column names, in insertion order."""
        return tuple(self._columns.keys())

    def __getitem__(self, name):
        """The full column as a read-only numpy array view.

        Read-only so a caller can't mutate source data by surprise; use
        `add_column` to write a (new) column explicitly.
        """
        arr = self._columns[name]
        view = arr[...] if arr.ndim else arr.reshape(())
        view = view.view()
        view.flags.writeable = False
        return view

    def __contains__(self, name):
        return name in self._columns

    def add_column(self, name, array):
        """Add or replace a derived column. Must match `n_rows` in length.

        Used for Remove Average / Transform / FFT-style derived data
        (Phase 3) as well as the demo/tests here. The stored array is
        copied into a fresh numpy array; it does not alias `array`.
        """
        arr = np.asarray(array)
        if len(arr) != self._n_rows:
            raise ValueError(
                f"add_column({name!r}, ...) length {len(arr)} does not match "
                f"n_rows {self._n_rows}"
            )
        self._columns[name] = arr.copy()
        self._notify()

    # -- filter (wholesale, re-appliable) ------------------------------------

    @property
    def filter_mask(self):
        """The current filter's boolean mask (read-only view), or None."""
        if self._filter_mask is None:
            return None
        view = self._filter_mask.view()
        view.flags.writeable = False
        return view

    def filter(self, mask_or_expr_or_none):
        """Set (or clear) the wholesale visible-rows filter.

        Accepts a boolean numpy array of length `n_rows`, a string
        expression evaluated against this source's own columns (plus
        `np`) using a restricted `eval` -- mirroring the same
        restricted-eval pattern `brushing.py`'s Transform action uses --
        or `None` to clear the filter entirely.
        """
        if mask_or_expr_or_none is None:
            self._filter_mask = None
        elif isinstance(mask_or_expr_or_none, str):
            names = {name: self[name] for name in self._columns}
            names['np'] = np
            try:
                result = eval(mask_or_expr_or_none, {'__builtins__': {}}, names)
            except Exception as e:
                raise ValueError(
                    f"invalid filter expression {mask_or_expr_or_none!r}: {e}"
                ) from e
            mask = np.asarray(result, dtype=bool)
            if mask.shape != (self._n_rows,):
                raise ValueError(
                    f"filter expression {mask_or_expr_or_none!r} produced shape "
                    f"{mask.shape}, expected ({self._n_rows},)"
                )
            self._filter_mask = mask
        else:
            mask = np.asarray(mask_or_expr_or_none, dtype=bool)
            if mask.shape != (self._n_rows,):
                raise ValueError(
                    f"filter mask shape {mask.shape} does not match n_rows "
                    f"{self._n_rows}"
                )
            self._filter_mask = mask
        self._notify()

    # -- hidden rows (accumulating, individually revertible) -----------------

    @property
    def hidden_mask(self):
        """The current hidden-rows boolean mask (read-only view)."""
        view = self._hidden_mask.view()
        view.flags.writeable = False
        return view

    def hide_rows(self, row_indices):
        """Mark `row_indices` as hidden (adds to the existing hidden set)."""
        idx = np.asarray(row_indices)
        self._hidden_mask[idx] = True
        self._notify()

    def show_rows(self, row_indices):
        """Clear `row_indices` from the hidden set (others stay hidden)."""
        idx = np.asarray(row_indices)
        self._hidden_mask[idx] = False
        self._notify()

    def show_all(self):
        """Clear the entire hidden-rows set."""
        self._hidden_mask[...] = False
        self._notify()

    # -- combined visibility ---------------------------------------------------

    @property
    def visible_rows(self):
        """Integer row indices currently visible: pass filter AND not hidden."""
        if self._filter_mask is None:
            visible = ~self._hidden_mask
        else:
            visible = self._filter_mask & ~self._hidden_mask
        return np.nonzero(visible)[0]

    # -- change notification (plain callbacks, no Qt) --------------------------

    def on_change(self, callback):
        """Subscribe a zero-arg callable, invoked synchronously on any
        add_column/filter/hide_rows/show_rows/show_all call."""
        self._listeners.append(callback)

    def off_change(self, callback):
        """Unsubscribe a callback previously passed to `on_change`."""
        self._listeners.remove(callback)

    def _notify(self):
        for callback in list(self._listeners):
            callback()

    def notify_change(self):
        """Fire `on_change` for every subscriber without touching any mask
        or column -- for a caller that changed something *about* this
        source's rows without the source itself being able to tell (e.g.
        brushing.py's delete_brushed_points, which permanently narrows a
        *series'* own drawn rows, never this source: see this module's
        own "Two independent, composable visibility mechanisms" docstring
        note -- there is deliberately no third, "deleted", mask here, so a
        caller in that position has no `hide_rows`/`filter` call of its
        own to make and would otherwise have no way to wake up a
        `depends_on=[source]` table/control). n_rows and every mask stay
        exactly as they were; this is purely a "something changed, go
        re-read whatever you care about" signal.
        """
        self._notify()
