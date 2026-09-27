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

"""Click-to-edit text: title, axis labels, legend entries.

Text items become editable on double-click via a small popup dialog. This
is far simpler than true inline caret editing over a QGraphicsScene and
just as usable.
"""
from pyqtgraph.Qt import QtWidgets


def make_click_editable(item, get_text, set_text, prompt="Edit text:"):
    """item must be a QGraphicsObject (LabelItem, QGraphicsTextItem, ...) that
    supports the native Qt mouseDoubleClickEvent(event)."""
    def handler(ev):
        new_text, ok = QtWidgets.QInputDialog.getText(
            None, "Edit", prompt, QtWidgets.QLineEdit.Normal, get_text()
        )
        if ok and new_text:
            set_text(new_text)
        ev.accept()
    item.mouseDoubleClickEvent = handler


def wire_plot_labels_editable(plot_item):
    """Double-click title / x-label / y-label to rename them."""
    title_label = plot_item.titleLabel
    make_click_editable(
        title_label,
        get_text=lambda: title_label.text,
        set_text=lambda t: plot_item.setTitle(t),
        prompt="New title:",
    )
    for axis_name in ('bottom', 'left'):
        axis = plot_item.getAxis(axis_name)
        label = axis.label  # QGraphicsTextItem

        def make_set(axis=axis):
            return lambda t: axis.setLabel(t)

        make_click_editable(
            label,
            get_text=lambda axis=axis: axis.labelText,
            set_text=make_set(),
            prompt=f"New {axis_name} label:",
        )


def wire_legend_editable(legend):
    """Double-click a legend entry's text to rename that curve."""
    for sample, label in legend.items:
        def make_set(label=label):
            return lambda t: label.setText(t)

        make_click_editable(
            label,
            get_text=lambda label=label: label.text,
            set_text=make_set(),
            prompt="New curve name:",
        )
