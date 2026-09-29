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

"""Grouping related curves (lafigure/groups.py, CLAUDE.md Phase 2b) with
the two built-in color presets:

  - `raw_filtered_preset`: same hue, alternating light/dark -- for a
    "raw" vs. "smoothed" pair that should read as one signal.
  - `sensor_family_preset`: small hue spread, same lightness -- for a
    family of related-but-distinct channels.

A Group is plain data (lafigure/groups.py), not a GUI-only concept: build
one from a list of `Series` (what `ax.plot(...)` returns) and register it
on `fig.groups` (a plain list; interactively this is what Ctrl+G does via
`GroupsMixin.group_selection`). Once registered, the Curve Browser (the
Figure Manager's second tab) shows each member under its group with
`group.display_name(member)`, and dragging the group's base-color swatch
there re-tints every member while preserving each one's own offset.

Run:
    python examples/groups_and_style.py
"""
import os
import sys

import numpy as np
from pyqtgraph.Qt import QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lafigure


def main():
    app = QtWidgets.QApplication(sys.argv)

    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- groups")

    t = np.linspace(0, 10, 3000)
    raw = np.sin(t) + 0.3 * np.random.default_rng(0).standard_normal(t.size)
    kernel = np.ones(31) / 31
    smoothed = np.convolve(raw, kernel, mode='same')

    ax1 = fig.subplot(0, 0, title="Raw / filtered pair")
    s_raw = ax1.plot(t, raw, name="raw")
    s_smoothed = ax1.plot(t, smoothed, name="smoothed")
    pair = lafigure.raw_filtered_preset([s_raw, s_smoothed], base_color=(60, 110, 190))
    pair.common_label = "channel 1 -- "
    fig.groups.append(pair)

    ax2 = fig.subplot(0, 1, title="Sensor family")
    sensors = [ax2.plot(t, np.sin(t + i * 0.4) + i * 0.15, name=f"sensor {i}")
               for i in range(5)]
    family = lafigure.sensor_family_preset(sensors, base_color=(160, 60, 60))
    family.common_label = " (bank A)"
    family.label_position = 'suffix'
    fig.groups.append(family)

    fig.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
