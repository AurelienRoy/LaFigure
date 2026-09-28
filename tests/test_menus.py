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
from tests.helpers import shown_figure, first_curve, _click_subplot, SHIFT


def _texts(menu):
    return [a.text() for a in menu.actions()]


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
