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

"""Right-click menus (menus.py). The menus are modal when exec'd, so these
inspect the subplot menu pyqtgraph owns and emit its aboutToShow, which is
where the menu selects the subplot and rebuilds its curve submenus."""
import csv
import os
import tempfile

import numpy as np

import lafigure as m
from tests.helpers import shown_figure, first_curve, _click_subplot, SHIFT


def _texts(menu):
    return [a.text() for a in menu.actions()]


def _submenu_titles(menu):
    return [a.menu().title() for a in menu.actions() if a.menu() is not None]


BRUSH_ACTION_LABELS = (
    "Delete Selected Points", "Transform Selected Points...",
    "Selection Stats...", "Fit Selected Points",
)


def test_subplot_menu_has_the_app_actions():
    f = shown_figure()
    texts = _texts(f.plots[0].getViewBox().menu)
    for label in ("Paste Curve", "Copy Subplot", "Paste Subplot", "Toggle Legend",
                  "Remove Average", "FFT -> Subplot Below", "Delete Selected Points",
                  "Transform Selected Points...", "Selection Stats...",
                  "Fit Selected Points", "Delete Curve", "Rename Curve"):
        assert label in texts, (label, texts)
    f.close()


def test_opening_the_menu_lists_curves_and_keeps_a_selection_involving_it():
    f = shown_figure()
    p0, p1 = f.plots[0], f.plots[1]
    menu = p0.getViewBox().menu
    submenus = {a.text(): a.menu() for a in menu.actions() if a.menu() is not None}
    _click_subplot(f, p1)
    menu.aboutToShow.emit()
    assert f.selected_plots == [p0] and f.focused_plot is p0, "right-click outside the selection selects"
    assert _texts(submenus["Delete Curve"]) == [first_curve(p0).name()]
    assert _texts(submenus["Rename Curve"]) == [first_curve(p0).name()]
    _click_subplot(f, p1, modifiers=SHIFT)
    menu.aboutToShow.emit()
    assert f.selected_plots == [p0, p1], "right-click inside the selection keeps it whole"
    f.close()


def test_pyqtgraph_export_and_axis_menus_are_removed():
    f = shown_figure()
    menu = f.plots[0].getViewBox().menu
    texts = _texts(menu)
    assert "Export..." not in texts, texts
    titles = _submenu_titles(menu)
    assert "X axis" not in titles, titles
    assert "Y axis" not in titles, titles
    assert "Mouse Mode" not in titles, titles
    # pyqtgraph's own "View All" and this app's own entries stay.
    assert "View All" in texts, texts
    assert "Export to CSV..." in texts, texts
    for label in ("Paste Curve", "Copy Subplot", "Paste Subplot", "Toggle Legend"):
        assert label in texts, (label, texts)
    f.close()


def test_export_to_csv_writes_padded_named_columns():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    p.plot(np.array([1.0, 2.0, 3.0]), np.array([10.0, 20.0, 30.0]), name="A")
    p.plot(np.array([1.0, 2.0]), np.array([5.0, 6.0]), name="B")

    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        f._export_subplot_csv(p, path)
        with open(path, newline="") as fh:
            rows = list(csv.reader(fh))
    finally:
        os.remove(path)
        f.close()

    assert rows[0] == ["A x", "A y", "B x", "B y"], rows[0]
    assert rows[1] == ["1.0", "10.0", "1.0", "5.0"], rows[1]
    assert rows[2] == ["2.0", "20.0", "2.0", "6.0"], rows[2]
    assert rows[3] == ["3.0", "30.0", "", ""], rows[3]  # B is shorter: padded with empty cells


def test_export_to_csv_falls_back_to_curve_n_when_unnamed():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    p.plot(np.array([1.0]), np.array([2.0]))

    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        f._export_subplot_csv(p, path)
        with open(path, newline="") as fh:
            rows = list(csv.reader(fh))
    finally:
        os.remove(path)
        f.close()

    assert rows[0] == ["curve 1 x", "curve 1 y"], rows[0]


def _labelled(menu):
    """Same as _brush_action_visibility's key set, but including the
    submenu's own action (its .text() is empty; its .menu().title() is
    "Fit Selected Points")."""
    out = {}
    for a in menu.actions():
        label = a.menu().title() if a.menu() is not None else a.text()
        if label in BRUSH_ACTION_LABELS:
            out[label] = (a.isVisible(), a.isEnabled())
    return out


def test_brushed_point_actions_hidden_when_brush_mode_is_off():
    f = shown_figure()
    assert not f.brushing, "control: Brush mode starts off"
    menu = f.plots[0].getViewBox().menu
    menu.aboutToShow.emit()
    vis = _labelled(menu)
    assert len(vis) == len(BRUSH_ACTION_LABELS), vis
    assert all(not visible for visible, _ in vis.values()), vis
    f.close()


def test_brushed_point_actions_visible_but_disabled_with_nothing_brushed():
    f = shown_figure()
    f.brush_action.trigger()
    assert f.brushing
    menu = f.plots[0].getViewBox().menu
    menu.aboutToShow.emit()
    vis = _labelled(menu)
    assert all(visible for visible, _ in vis.values()), vis
    assert all(not enabled for _, enabled in vis.values()), vis
    f.close()


def test_brushed_point_actions_visible_and_enabled_with_a_real_selection():
    f = shown_figure()
    f.brush_action.trigger()
    p0 = f.plots[0]
    curve = first_curve(p0)
    mask = np.zeros(len(curve.xData), dtype=bool)
    mask[:3] = True
    f._brushers[p0].set_selection({curve: mask})
    menu = p0.getViewBox().menu
    menu.aboutToShow.emit()
    vis = _labelled(menu)
    assert all(visible for visible, _ in vis.values()), vis
    assert all(enabled for _, enabled in vis.values()), vis
    f.close()
