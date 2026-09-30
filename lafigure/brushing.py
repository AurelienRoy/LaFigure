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

"""Figure-wide data brushing: the Brush toggle, linking through DataSource
rows, Hide Brushed Points / Show All, derived columns, and the four
brushed-point actions (Delete, Transform, Stats, Fit).

**Selection.** Each subplot's RectBrush (selection.py) holds the rows
brushed on each of its series. The figure-wide selection is their union per
*brush key* -- the series' DataSource, or the item itself for a series of
plain arrays -- and is shown on every series with the same key, which is
what links two subplots of one source. Brushing stays per figure: another
window showing the same source keeps its own (and its own Brush toggle).

**Hidden rows.** Hide Brushed Points marks rows hidden on their DataSource
(`hide_rows`; the data itself is untouched) and every series of that
source, in every open figure, stops drawing them. A series drawing only
some of its rows keeps its complete data in a _RowView on its item (under
ROW_VIEW_ATTR), and only for as long as some row is left out; the drawn
data is the view's entries whose row is visible (`source.visible_rows`,
which also honours `source.filter`). A plain-array series has no source to
mark, so its view carries its own hidden mask. Values edited while rows are
hidden (Series.set_data) are written back into the view before it's used.

**Derived columns.** Remove Average and Transform, on a series whose y is
still exactly a column of a DataSource, write the result into a new column
of that source and point the series at it; the original column is never
written, and undo points the series back at it (the derived column stays in
the source, unused -- DataSource has no way to remove a column). A series of
plain arrays has nothing shared to protect and is still edited in place.
FFT results never had the time series' rows, so a source series' FFT gets
a new DataSource of its own (view_ops.py).
"""
import numpy as np
from pyqtgraph.Qt import QtCore, QtWidgets
import pyqtgraph as pg

from .datasource import DataSource
from .selection import positions_of_rows

# Attribute holding a series item's _RowView -- on the item, like the Series
# itself, so it dies with it.
ROW_VIEW_ATTR = '_lafigure_row_view'


class _RowView:
    """The complete data of a series some of whose entries aren't drawn:
    x, y and rows (None for plain arrays) of every entry, the source they
    come from (None for plain arrays), a hidden mask of its own for plain
    arrays, and which entries are drawn. Never mutated once stored: a
    change stores a new one, so undo snapshots can hold on to the old."""
    __slots__ = ('x', 'y', 'rows', 'source', 'hidden', 'shown')

    def __init__(self, x, y, rows, source, hidden, shown):
        self.x, self.y, self.rows = x, y, rows
        self.source, self.hidden, self.shown = source, hidden, shown

    def replace(self, **changes):
        fields = {name: getattr(self, name) for name in self.__slots__}
        fields.update(changes)
        return _RowView(**fields)


def _visible_mask(source):
    mask = ~source.hidden_mask
    if source.filter_mask is not None:
        mask &= source.filter_mask
    return mask


def _write_back(full, shown, drawn):
    out = np.array(full, dtype=np.result_type(full, drawn), copy=True)
    out[shown] = drawn
    return out


class BrushingMixin:
    def toggle_brush(self, checked):
        """Brush is an exclusive interaction mode (view_ops.
        set_interaction_mode, since 2026-09-29): on = Brush mode, off =
        back to Select. Kept as the API/test entry point it always was."""
        if checked:
            self.set_interaction_mode('brush')
        elif self.interaction_mode == 'brush':
            self.set_interaction_mode('select')

    # -- the figure-wide, row-linked selection -------------------------------
    @staticmethod
    def _brush_key(series):
        """What a series' brushed rows are rows *of*: its DataSource, shared
        with every other series of that source, or itself (plain arrays)."""
        return series.source if series.rows is not None else series.item

    def _brushed_rows(self):
        """{brush key: sorted rows} brushed anywhere in this figure."""
        keyed = {}
        for brusher in self._brushers.values():
            for item, rows in brusher.selection.items():
                series = self._series_of(item)
                if series is None:
                    continue
                key = self._brush_key(series)
                keyed[key] = np.union1d(keyed[key], rows) if key in keyed else rows
        return keyed

    def _show_brushed_rows(self, keyed):
        """Make {brush key: rows} the whole figure's selection: every
        brushable series shows the rows of its key it has."""
        for brusher in self._brushers.values():
            selection = {}
            for series in brusher.brushable_series():
                rows = keyed.get(self._brush_key(series))
                if rows is None:
                    continue
                if series.rows is not None:
                    rows = rows[np.isin(rows, series.rows)]
                selection[series.item] = rows
            brusher.set_selection(selection)

    def _on_rect_brush_finished(self, plot_item, matches, additive):
        """RectBrush's on_finished callback (see selection.py) -- brushing
        is a figure-wide concept: a fresh, non-additive brush drag anywhere
        unbrushes every other subplot in this figure first; a Shift-held
        drag instead adds to whatever's already selected everywhere. Either
        way the result is shown on every series sharing a source."""
        keyed = self._brushed_rows() if additive else {}
        for item, rows in matches.items():
            key = self._brush_key(self._series_of(item))
            keyed[key] = np.union1d(keyed[key], rows) if key in keyed else rows
        self._show_brushed_rows(keyed)

    def _clear_all_brush_selection(self, except_plot=None):
        for plot_item, brusher in self._brushers.items():
            if plot_item is not except_plot:
                brusher.clear_selection()

    def _redraw_brush(self):
        for brusher in self._brushers.values():
            if brusher.selection:
                brusher.redraw()

    def _figure_brush_items(self):
        """Every (item, mask over its drawn points) with an active brush
        selection, figure-wide -- pooled across every subplot's RectBrush,
        since brushing is a figure-level concept (see
        _on_rect_brush_finished). Only point-like series: a histogram's
        bars aren't points to delete, transform or fit."""
        items = []
        for brusher in self._brushers.values():
            for item, rows in brusher.selection.items():
                series = self._series_of(item)
                mask = positions_of_rows(series, rows) if series is not None else None
                if mask is not None and mask.any():
                    items.append((item, mask))
        return items

    def _item_xy(self, item):
        x, y = self._series_of(item).kind_obj.get_xy(item)
        return np.asarray(x), np.asarray(y)

    def _pooled_brush_xy(self, items):
        xs, ys = [], []
        for item, mask in items:
            x, y = self._item_xy(item)
            xs.append(x[mask])
            ys.append(y[mask])
        if not xs:
            return np.array([]), np.array([])
        return np.concatenate(xs), np.concatenate(ys)

    def _require_brush_selection(self):
        """Shared guard for the four brushed-selection actions below --
        returns the figure-wide list of (item, mask) if there's a live
        selection anywhere, else tells the user what to do and returns None."""
        items = self._figure_brush_items()
        if not items:
            QtWidgets.QMessageBox.information(
                self, "No selection",
                "Brush-select some points first: toggle Brush mode, then drag "
                "a rectangle over the points (on any subplot; Shift+drag to "
                "add more, from any subplot).",
            )
            return None
        return items

    # -- row views: series drawing only some of their rows ------------------
    def _all_series(self):
        return [s for p in self.plots for s in self._series_on(p)]

    def _synced_row_view(self, series):
        """The series' _RowView with the drawn values written back into it,
        or None -- also dropping a view the drawn data no longer matches
        (the series was replaced wholesale since, e.g. set_data to another
        length): then the drawn data is all there is."""
        item = series.item
        view = getattr(item, ROW_VIEW_ATTR, None)
        if view is None:
            return None
        x, y = series.kind_obj.get_xy(item)
        rows = series.rows
        n_shown = int(np.count_nonzero(view.shown))
        if (x is None or y is None or len(x) != n_shown or len(y) != n_shown
                or (rows is None) != (view.rows is None)
                or (rows is not None and (series.source is not view.source
                                          or not np.array_equal(rows, view.rows[view.shown])))):
            delattr(item, ROW_VIEW_ATTR)
            return None
        view = view.replace(x=_write_back(view.x, view.shown, x), y=_write_back(view.y, view.shown, y))
        setattr(item, ROW_VIEW_ATTR, view)
        return view

    def _point_view(self, series):
        """The synced view, or a fresh one with every entry drawn; None if
        the series isn't one x/y point per row (nothing to leave out)."""
        view = self._synced_row_view(series)
        if view is not None:
            return view
        x, y = series.kind_obj.get_xy(series.item)
        if x is None or y is None or np.ndim(x) != 1 or np.shape(x) != np.shape(y):
            return None
        rows = series.rows
        if rows is not None and len(rows) != len(x):
            return None
        n = len(x)
        return _RowView(np.asarray(x), np.asarray(y), rows,
                        series.source if rows is not None else None,
                        np.zeros(n, dtype=bool) if rows is None else None,
                        np.ones(n, dtype=bool))

    def _apply_row_visibility(self, series):
        """Draw exactly the series' visible entries: rows visible in its
        source, or not in its own hidden mask. Returns whether that changed
        what's drawn. The one place a row view is applied."""
        view = self._synced_row_view(series)
        if view is None:
            if series.rows is None:
                return False  # plain arrays without a view: nothing is hidden
            if _visible_mask(series.source)[series.rows].all():
                return False
            view = self._point_view(series)
            if view is None:
                return False
        if view.source is not None:
            keep = _visible_mask(view.source)[view.rows]
        else:
            keep = ~view.hidden
        if np.array_equal(keep, view.shown):
            return False
        self._draw_view(series, view, keep)
        return True

    def _draw_view(self, series, view, keep):
        item = series.item
        series._apply(view.x[keep], view.y[keep], view.source,
                      None if view.rows is None else view.rows[keep])
        if keep.all():
            if hasattr(item, ROW_VIEW_ATTR):
                delattr(item, ROW_VIEW_ATTR)
        else:
            setattr(item, ROW_VIEW_ATTR, view.replace(shown=keep))
        if view.rows is None:
            # Plain arrays: a brush holds positions, which just moved.
            for brusher in self._brushers.values():
                if item in brusher.selection:
                    brusher.forget_curve(item)

    def _set_private_hidden(self, series, entries, hidden):
        """Hide/show entries (indices into the complete data) of a
        plain-array series, which has no source to mark them on."""
        view = self._point_view(series)
        if view is None or view.hidden is None:
            return
        mask = view.hidden.copy()
        mask[entries] = hidden
        setattr(series.item, ROW_VIEW_ATTR, view.replace(hidden=mask))
        self._apply_row_visibility(series)

    def _refresh_sources(self, sources):
        """Redraw every series of `sources` in every open figure -- hidden
        rows live on the source, so they reach pasted copies elsewhere."""
        figures = list(self.registry.figures)
        if self not in figures:
            figures.append(self)
        for fig in figures:
            for series in fig._all_series():
                if series.rows is not None and series.source in sources:
                    fig._apply_row_visibility(series)
            fig._redraw_brush()

    # -- the complete data, for copy/paste and delete/undo ------------------
    def _series_full_dict(self, series):
        """Series.to_dict, but with the rows it's not drawing right now
        included, so a paste (or an undone delete) keeps them -- and, via
        _add_series_restoring, keeps them hidden."""
        d = series.to_dict()
        view = self._synced_row_view(series)
        if view is not None:
            d['x'], d['y'] = np.array(view.x, copy=True), np.array(view.y, copy=True)
            if view.rows is not None:
                d['rows'] = np.array(view.rows, copy=True)
            else:
                d['hidden'] = view.hidden.copy()
        return d

    def _add_series_restoring(self, plot_item, d):
        """_add_series_from_dict, then leave out what should be: rows
        hidden in its source, or the entries a plain-array copy had hidden."""
        series = self._add_series_from_dict(plot_item, d)
        hidden = d.get('hidden')
        if hidden is not None and np.any(hidden):
            self._set_private_hidden(series, np.nonzero(hidden)[0], True)
        else:
            self._apply_row_visibility(series)
        return series

    # -- Hide Brushed Points / Show All --------------------------------------
    def _refresh_show_all_action(self):
        """Keep the toolbar's "Show All Points" QAction's enabled state in
        sync with has_hidden_points() -- the subplot menu already does
        this itself, on its own aboutToShow (menus.py); a toolbar button
        has no such hook, so every place below that can change whether
        anything is hidden calls this directly. `show_all_points_action`
        is created by toolbar.py (a coordinator diff, not owned here) --
        guarded so this is a no-op before that diff lands / in a test
        LaFigure with no toolbar."""
        action = getattr(self, 'show_all_points_action', None)
        if action is not None:
            action.setEnabled(self.has_hidden_points())

    def hide_brushed_points(self):
        """Stop drawing the brushed rows everywhere they're shown: hidden on
        their DataSource (the data stays intact), so every series of that
        source in every figure leaves them out. Undoable."""
        sources, private = {}, []
        for key, rows in self._brushed_rows().items():
            if isinstance(key, DataSource):
                rows = rows[~key.hidden_mask[rows]]
                if rows.size:
                    sources[key] = rows
            else:
                series = self._series_of(key)
                view = self._point_view(series)
                if view is not None and view.hidden is not None:
                    drawn = np.nonzero(view.shown)[0]
                    private.append((series, drawn[rows[rows < drawn.size]]))
        if not sources and not private:
            return
        self._clear_all_brush_selection()

        def apply(hidden):
            for src, rows in sources.items():
                (src.hide_rows if hidden else src.show_rows)(rows)
            for series, entries in private:
                self._set_private_hidden(series, entries, hidden)
            self._refresh_sources(sources)
            self._refresh_show_all_action()

        apply(True)
        self._push_history(undo_fn=lambda: apply(False), redo_fn=lambda: apply(True))

    def show_all_hidden_points(self):
        """Draw every hidden row again, for every series of this figure
        (DataSource.show_all on their sources). Undoable."""
        sources, private = {}, []
        for series in self._all_series():
            if series.rows is not None:
                src = series.source
                if src not in sources and src.hidden_mask.any():
                    sources[src] = np.nonzero(src.hidden_mask)[0]
            else:
                view = self._synced_row_view(series)
                if view is not None and view.hidden.any():
                    private.append((series, np.nonzero(view.hidden)[0]))
        if not sources and not private:
            return

        def show():
            for src in sources:
                src.show_all()
            for series, entries in private:
                self._set_private_hidden(series, entries, False)
            self._refresh_sources(sources)
            self._refresh_show_all_action()

        def hide():
            for src, rows in sources.items():
                src.hide_rows(rows)
            for series, entries in private:
                self._set_private_hidden(series, entries, True)
            self._refresh_sources(sources)
            self._refresh_show_all_action()

        show()
        self._push_history(undo_fn=hide, redo_fn=show)

    def has_hidden_points(self):
        """For enabling Show All: is any row of this figure's series hidden?"""
        for series in self._all_series():
            if series.rows is not None:
                if series.source.hidden_mask.any():
                    return True
            elif getattr(series.item, ROW_VIEW_ATTR, None) is not None:
                return True
        return False

    # -- snapshots: one series' whole drawn state, for undo -----------------
    def _snapshot(self, series):
        view = self._synced_row_view(series)
        x, y = series.kind_obj.get_xy(series.item)
        source = series.source if series.rows is not None else None
        return (x, y, source, series.rows, series.columns, view)

    def _restore(self, series, snapshot):
        x, y, source, rows, columns, view = snapshot
        series._apply(x, y, source, rows)
        series.columns = columns
        if view is not None:
            setattr(series.item, ROW_VIEW_ATTR, view)
        elif hasattr(series.item, ROW_VIEW_ATTR):
            delattr(series.item, ROW_VIEW_ATTR)

    def _push_snapshots(self, changes):
        """Push one undo step for [(series, before, after)], already applied."""
        self._push_history(
            undo_fn=lambda: [self._restore(s, before) for s, before, _ in reversed(changes)],
            redo_fn=lambda: [self._restore(s, after) for s, _, after in changes],
        )

    # -- derived columns --------------------------------------------------
    def _column_backed(self, series):
        """The DataSource if the series' y is still exactly its y column
        (for all its rows, hidden ones included), else None."""
        columns = series.columns
        if series.rows is None or not columns or len(columns) < 2 or not isinstance(columns[1], str):
            return None
        source = series.source
        if columns[1] not in source:
            return None
        view = self._synced_row_view(series)
        y, rows = (view.y, view.rows) if view is not None else (series.y, series.rows)
        if y is None or len(y) != len(rows):
            return None
        try:
            same = np.array_equal(source[columns[1]][rows], y, equal_nan=True)
        except TypeError:
            same = np.array_equal(source[columns[1]][rows], y)
        return source if same else None

    def _derive_y_column(self, series, label, values):
        """Write `values` (one per source row) into a new column of the
        series' source, named after its y column and `label`, and point the
        series' y at it. Undoable; the original column is never written."""
        source = series.source
        xcol, ycol = series.columns[0], series.columns[1]
        name = f"{ycol} {label}"
        n = 2
        while name in source:
            name, n = f"{ycol} {label} ({n})", n + 1
        source.add_column(name, values)
        new_y = source[name]
        before = self._snapshot(series)
        x, _y, _src, rows, columns, view = before
        if view is not None:
            view = view.replace(y=new_y[view.rows])
        after = (x, new_y[rows], source, rows, (xcol, name) + tuple(columns[2:]), view)
        self._restore(series, after)
        self._push_snapshots([(series, before, after)])

    # -- the four brushed-point actions -------------------------------------
    def _cursors_targeting(self, item, removed_ids):
        """Data-cursor annotations (annotation_ops.py) whose point_ref
        currently resolves to `item` and one of `removed_ids` (a row id
        for a DataSource-backed series, an array index for a private one
        -- see _row_id's own docstring) -- i.e. cursors about to lose the
        exact entry they're pinned to, on THIS series specifically. Note
        the underlying DataSource, if any, is never itself shrunk by a
        delete (see this method's own docstring below): this is the one
        place that can tell "deleted from this curve" from merely
        "hidden" or "not currently drawn", which is why cursor removal is
        hooked in here rather than in refresh_point's generic resync."""
        if len(removed_ids) == 0:
            return []
        removed = set(np.asarray(removed_ids).tolist())
        hits = []
        for ann in self.annotations:
            if ann.kind != 'cursor' or ann.point_ref is None:
                continue
            target = self._cursor_ref_item(ann.parent_plot, ann.point_ref)
            if target is item and ann.point_ref['row'] in removed:
                hits.append(ann)
        return hits

    def delete_brushed_points(self):
        """Remove the brushed points from their series. A series of a
        DataSource stays linked to it, drawing fewer of its rows; the
        source itself is untouched -- but every source a change actually
        narrowed gets a `notify_change()` (datasource.py), so a reactive
        control/table (`ControlPanel.table(..., depends_on=[source])`)
        re-runs even though nothing about the source's own masks changed;
        see notify_change's own docstring for why deleting can't just
        call hide_rows instead (it isn't figure-wide/source-wide -- a
        delete narrows only THIS series' own drawn rows, not every series
        sharing the source). Undo/redo of the delete notify too. Any
        data-cursor annotation pinned to one of the removed points is
        deleted too, in the same undo entry."""
        items = self._require_brush_selection()
        if items is None:
            return
        self._clear_all_brush_selection()
        changes = []
        removed_cursors = []
        with self.undo_group():
            for item, mask in items:
                series = self._series_of(item)
                before = self._snapshot(series)
                x, y, source, rows, columns, view = before
                keep = ~mask
                removed_ids = rows[mask] if rows is not None else np.nonzero(mask)[0]
                removed_cursors.extend(self._cursors_targeting(item, removed_ids))
                if view is not None:
                    entries = np.ones(len(view.x), dtype=bool)
                    entries[np.nonzero(view.shown)[0][mask]] = False
                    view = view.replace(
                        x=view.x[entries], y=view.y[entries], shown=view.shown[entries],
                        rows=None if view.rows is None else view.rows[entries],
                        hidden=None if view.hidden is None else view.hidden[entries])
                after = (np.asarray(x)[keep], None if y is None else np.asarray(y)[keep], source,
                         None if rows is None else rows[keep], columns, view)
                self._restore(series, after)
                changes.append((series, before, after))
            sources = {before[2] for _, before, _ in changes if before[2] is not None}

            def undo_fn():
                for s, before, _ in reversed(changes):
                    self._restore(s, before)
                for src in sources:
                    src.notify_change()

            def redo_fn():
                for s, _, after in changes:
                    self._restore(s, after)
                for src in sources:
                    src.notify_change()

            self._push_history(undo_fn, redo_fn)
            for src in sources:
                src.notify_change()
            for ann in removed_cursors:
                self.delete_annotation(ann)

    def transform_brushed_points(self):
        items = self._require_brush_selection()
        if items is None:
            return
        expr, ok = QtWidgets.QInputDialog.getText(
            self, "Transform selected points",
            "Expression in terms of x, y (numpy available as np), applied to the\n"
            "selected points' y-values, e.g. \"y * 2\" or \"np.log(y)\":",
            QtWidgets.QLineEdit.Normal, "y",
        )
        if not ok or not expr:
            return

        results = []
        for item, mask in items:
            x_full, y_full = self._item_xy(item)
            x_sel, y_sel = x_full[mask], y_full[mask]
            try:
                new_y_sel = np.asarray(
                    eval(expr, {'__builtins__': {}}, {'np': np, 'x': x_sel, 'y': y_sel}),
                    dtype=float,
                )
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Invalid expression", str(e))
                return
            if new_y_sel.shape != y_sel.shape:
                QtWidgets.QMessageBox.warning(
                    self, "Invalid expression",
                    "Result must have the same shape as the selected points.",
                )
                return
            results.append((self._series_of(item), mask, new_y_sel))

        self._clear_all_brush_selection()
        # One gesture, one undo entry, however many series it changes.
        with self.undo_group():
            for series, mask, new_y_sel in results:
                source = self._column_backed(series)
                if source is not None:
                    values = np.array(source[series.columns[1]], dtype=float)
                    values[series.rows[mask]] = new_y_sel
                    self._derive_y_column(series, "(transformed)", values)
                    continue
                before = self._snapshot(series)
                x, y, src, rows, columns, view = before
                new_y = np.array(y, dtype=float)
                new_y[mask] = new_y_sel
                after = (x, new_y, src, rows, columns, view)
                self._restore(series, after)
                self._push_snapshots([(series, before, after)])

    def show_selection_stats(self):
        items = self._require_brush_selection()
        if items is None:
            return
        lines = []
        for item, mask in items:
            x, y = self._item_xy(item)
            x, y = x[mask], y[mask]
            label = item.name() or "(unnamed curve)"
            lines.append(
                f"{label}: n={mask.sum()}  "
                f"x: mean={x.mean():.4g} std={x.std():.4g}  "
                f"y: mean={y.mean():.4g} std={y.std():.4g}"
            )
        if len(items) > 1:
            pooled_x, pooled_y = self._pooled_brush_xy(items)
            lines.append("")
            lines.append(
                f"All curves pooled: n={pooled_x.size}  "
                f"x: mean={pooled_x.mean():.4g} std={pooled_x.std():.4g}  "
                f"y: mean={pooled_y.mean():.4g} std={pooled_y.std():.4g}"
            )
        QtWidgets.QMessageBox.information(self, "Selection stats", "\n".join(lines))

    def fit_brushed_points(self, plot_item, degree):
        items = self._require_brush_selection()
        if items is None:
            return
        if degree is None:
            degree, ok = QtWidgets.QInputDialog.getInt(
                self, "Polynomial fit", "Degree:", 2, 1, 10
            )
            if not ok:
                return
        x, y = self._pooled_brush_xy(items)
        if x.size < degree + 1:
            QtWidgets.QMessageBox.warning(
                self, "Fit failed",
                f"Need at least {degree + 1} selected points for a degree-{degree} fit.",
            )
            return

        coeffs = np.polyfit(x, y, degree)
        y_hat = np.polyval(coeffs, x)
        ss_res = np.sum((y - y_hat) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
        label = "Linear fit" if degree == 1 else f"Polynomial fit (deg={degree})"
        terms = " + ".join(
            f"{c:.4g}*x^{degree - i}" if degree - i > 0 else f"{c:.4g}"
            for i, c in enumerate(coeffs)
        )
        text = f"{label}\ny = {terms}\nR² = {r2:.4g}"

        order = np.argsort(x)
        xs_sorted = x[order]
        ys_fit = np.polyval(coeffs, xs_sorted)

        def build():
            fit_pen = pg.mkPen((200, 30, 30), width=2, style=QtCore.Qt.DashLine)
            curve = self._add_series(plot_item, 'line', xs_sorted, ys_fit, pen=fit_pen, name=label).item
            text_item = pg.TextItem(text, color=(200, 30, 30), anchor=(0, 1))
            text_item.setPos(xs_sorted[-1], ys_fit[-1])
            plot_item.addItem(text_item)
            return curve, text_item

        holder = {}
        holder['curve'], holder['text'] = build()

        def undo_fn():
            c, t = holder.get('curve'), holder.get('text')
            if c is not None:
                plot_item.removeItem(c)
                self._forget_curve_selection(c)
            if t is not None:
                plot_item.removeItem(t)
            holder['curve'] = holder['text'] = None

        def redo_fn():
            holder['curve'], holder['text'] = build()

        self._push_history(undo_fn, redo_fn)
