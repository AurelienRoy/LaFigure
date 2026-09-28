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

"""FigureManager + registry: the tree tracks open figures/subplots, "New
Figure" makes a truly empty one, and the shared Clipboard carries a whole
subplot from one figure window to a separate one.
"""
import pyqtgraph as pg

from tests.helpers import (
    app, m, shown_figure,
)


def test_figure_manager_tracks_figures_and_cross_window_paste():
    """Tree tracks figures; an empty figure has no subplot floor; a subplot
    pastes into a separate window; closing unregisters."""
    win = shown_figure()
    p1, p2, p3, p4 = win.plots

    mgr = m.FigureManager()
    app.processEvents()
    assert win in mgr._figure_items
    win_item = mgr._figure_items[win]
    assert win_item.childCount() == len(win.plots)

    empty_win = mgr.new_figure()
    app.processEvents()
    assert empty_win.empty is True
    assert empty_win.plots == []
    assert empty_win in mgr._figure_items
    assert mgr._figure_items[empty_win].childCount() == 0

    # An empty figure has no floor on subplot count -- adding then deleting its
    # only subplot must be able to leave it at zero again (unlike `win`, whose
    # floor of 1 is exercised implicitly by every delete_subplot() call above).
    empty_win.add_new_subplot()
    app.processEvents()
    assert len(empty_win.plots) == 1
    assert mgr._figure_items[empty_win].childCount() == 1
    empty_win.delete_subplot(empty_win.plots[0])
    assert len(empty_win.plots) == 0

    # Copy a subplot out of `win` and paste it into the separate `empty_win`
    # window via the process-wide clipboard -- this is the cross-window path
    # that a single-window app couldn't support.
    win._on_plot_clicked(p1)
    n_curves_p1 = len([c for c in p1.listDataItems() if isinstance(c, pg.PlotDataItem)])
    win.copy_subplot()
    assert win.clipboard.subplot is not None
    assert win.clipboard is empty_win.clipboard  # same process-wide singleton

    empty_win.paste_subplot()
    app.processEvents()
    assert len(empty_win.plots) == 1
    pasted = empty_win.plots[0]
    assert pasted.titleLabel.text == p1.titleLabel.text
    pasted_curves = [c for c in pasted.listDataItems() if isinstance(c, pg.PlotDataItem)]
    assert len(pasted_curves) == n_curves_p1

    empty_win.undo()
    assert len(empty_win.plots) == 0
    empty_win.redo()
    assert len(empty_win.plots) == 1

    # Closing a figure unregisters it from both the registry and the manager's
    # tree.
    empty_win.close()
    app.processEvents()
    assert empty_win not in mgr._figure_items
    win.close()
