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

"""ax.loglog(x, y, **style) / ax.semilogx(...) / ax.semilogy(...) -- plain
line series (`kinds/_base.DerivedKind` on `'line'`, per round 4's "re-use
the same base function/base plots" requirement -- nothing new is drawn,
only the subplot's log-axis state differs) whose `setup` puts the SUBPLOT
into log mode via `PlotItem.setLogMode(x, y)`.

**One module for all three kinds, not three** (PLAN.md leaves this to the
package's own judgment): the three differ only in which axis(es) are log,
so a tiny shared `_LogKind` base (`log_x`/`log_y` class attributes) avoids
repeating the identical `setup()` body three times. Each subclass still
calls `register_series_kind` itself and is `import`ed by name from
`kinds/__init__.py`, exactly like a one-kind-per-file module would be.

**Log mode is a SUBPLOT-wide setting, not a per-series one** (this is
`PlotItem.setLogMode`'s own contract, not something this module invents --
see its docstring: "No other items[...] will be affected by this"; it only
flips the axes' own display mode and asks every current `PlotDataItem` on
the plot to remap itself). So `ax.loglog(...)` followed by `ax.semilogy(...)`
on the SAME subplot leaves that subplot in `(x=False, y=True)` -- the
second call's own explicit `(False, True)` overwrites the first call's
`(True, True)`, exactly as calling `plot_item.setLogMode(False, True)`
directly would. This mirrors MATLAB's own `semilogy` on an axes that was
`loglog`: the axes' scale is a single, shared, whole-axes property.

**Non-positive values -- read from the installed pyqtgraph source
(`graphicsItems/PlotDataItem.py`, `setLogMode`/`PlotDataset.applyLogMapping`),
not guessed, and never altered by this module**: `PlotItem.setLogMode`
checks the `logXCheck`/`logYCheck` controls, which (via `updateLogMode`)
call `item.setLogMode(x, y)` on every `PlotDataItem` currently on the
plot. That call maps the item's data through `np.log10` on the affected
axis/axes for DISPLAY only: `item.xData`/`item.yData` (and hence
`Series.x`/`.y`, `to_dict`, CSV/HTML export, brushing) stay exactly the
raw values passed in, negatives/zeros included -- nothing is dropped,
clipped or silently rewritten. Only the item's *displayed* dataset
(`item.getData()`, what pyqtgraph actually draws) changes: a zero or
negative value's `log10` is non-finite (`-inf` for zero, `nan` for a
negative), and pyqtgraph itself replaces every such non-finite result
with `nan` (`PlotDataset.applyLogMapping`'s own doc: "Values of -inf
resulting from zeros [...] are replaced by np.nan"). A `nan` in a Qt
painter path is simply not drawn -- it reads as a gap at that x/y, not a
shifted or reindexed curve (the array length is unchanged). See
`test_r4_log.test_loglog_nonpositive_values_become_nan_in_display_only`.

**A second series on an already-log subplot is still mapped correctly --
verified, not assumed.** `PlotItem.setLogMode` flips `Qt` checkboxes
(`QCheckBox.setChecked`), which only emit `toggled` -- and hence only run
`updateLogMode()`, the thing that calls `item.setLogMode(...)` on every
*current* item -- on an actual state change; a second `loglog` series
added to a subplot already in `(True, True)` mode would make
`plot_item.setLogMode(True, True)` a no-op there. That looked, before
checking, like it would leave the brand-new item unmapped -- but
`PlotItem.addItem` (called by the base `'line'` kind's own `create()`,
before `setup()` ever runs) independently re-applies the CURRENT checkbox
state to any item it adds that implements `setLogMode`, unconditionally
(`graphicsItems/PlotItem/PlotItem.py`'s own comment there: "Toggle log
mode if item implements setLogMode and selected in the context menu").
So every item -- first or later -- already gets the subplot's current log
state at the moment it's added, and `_LogKind.setup`'s own
`plot_item.setLogMode(...)` call only matters for the FIRST item on a
plot (or a call that changes the subplot's existing state). See
`test_r4_log.test_second_loglog_series_on_an_already_log_subplot_is_still_log_mapped`
(this was written expecting to catch a real gap; instead it caught that
pyqtgraph already closes it -- kept as a regression test either way).
"""
from ._base import DerivedKind
from ..series import register_series_kind


class _LogKind(DerivedKind):
    """Shared base for loglog/semilogx/semilogy -- see the module
    docstring. Not itself registered (`name` stays unset)."""
    base = 'line'
    log_x = False
    log_y = False

    def setup(self, plot_item, item, **kwargs):
        plot_item.setLogMode(self.log_x, self.log_y)


class LogLogKind(_LogKind):
    name = 'loglog'
    log_x = True
    log_y = True


class SemiLogXKind(_LogKind):
    name = 'semilogx'
    log_x = True
    log_y = False


class SemiLogYKind(_LogKind):
    name = 'semilogy'
    log_x = False
    log_y = True


register_series_kind(LogLogKind())
register_series_kind(SemiLogXKind())
register_series_kind(SemiLogYKind())
