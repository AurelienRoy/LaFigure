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

"""Two separate LaFigure windows, with a whole subplot AND a single curve
copied from the first into the second -- the scenario the project's
process-wide `Clipboard` (lafigure/clipboard.py) exists for: copy/paste
that reaches across independent windows, not just within one.

Interactively this is Ctrl+C/Ctrl+Shift+C and Ctrl+V/Ctrl+Shift+V, driven
by whatever's currently selected (selected_plots/selected_curves,
selection_ui.py). A script has no mouse selection to read, so it sets the
same state the click handlers would have set -- `fig.focused_plot` (a
public property) and `fig.active_curve` -- immediately before calling the
same `copy_subplot`/`copy_curve`/`paste_subplot`/`paste_curve` methods
the toolbar/menu actions call. Every paste below is undoable in its own
window exactly as if a user had pressed Ctrl+V there.

Run:
    python examples/copy_paste_across_figures.py
"""
import os
import sys

import numpy as np
from pyqtgraph.Qt import QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lafigure
_debug_log = lafigure.enable_debug_mode()
print(f"Debug log: {_debug_log}")


def main():
    app = QtWidgets.QApplication(sys.argv)

    t = np.linspace(0, 10, 2000)

    fig1 = lafigure.LaFigure(empty=True)
    fig1.setWindowTitle("Source figure")
    fig1.move(80, 80)

    ax1 = fig1.subplot(0, 0, title="Whole subplot -- gets copied")
    ax1.plot(t, np.sin(t), pen=(60, 120, 200), name="sin")
    ax1.plot(t, np.cos(t), pen=(200, 90, 60), name="cos")
    fig1.focused_plot = ax1.plot_item
    fig1.copy_subplot()

    ax1b = fig1.subplot(1, 0, title="Only 'smoothed' gets copied")
    kernel = np.ones(31) / 31
    raw = np.sin(t) + 0.3 * np.random.default_rng(1).standard_normal(t.size)
    smoothed = ax1b.plot(t, np.convolve(raw, kernel, mode='same'), pen=(60, 160, 90),
                          name="smoothed")
    ax1b.plot(t, raw, pen=(190, 190, 190), name="raw")
    fig1.active_curve = smoothed.item  # the specific curve Ctrl+C would target
    fig1.copy_curve()

    fig2 = lafigure.LaFigure(empty=True)
    fig2.setWindowTitle("Destination figure")
    fig2.move(760, 80)

    fig2.paste_subplot()  # lands as a new row -- the whole sin/cos subplot

    ax2b = fig2.subplot(1, 0, title="Paste target")
    fig2.focused_plot = ax2b.plot_item
    fig2.paste_curve()  # lands just the 'smoothed' curve, on this subplot

    fig1.show()
    fig2.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
