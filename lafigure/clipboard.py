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

"""Process-wide clipboard shared by every LaFigure window.

Curve copy/paste always worked "within one window" because it lived on
LaFigure.clipboard_curve, a plain instance attribute. Now that multiple
LaFigure windows can be open at once (FigureManager's "New Figure"),
Ctrl+C in one window and Ctrl+V in another needs a clipboard that isn't
scoped to either instance -- hence a module-level singleton, same pattern
as registry.get_registry().

`curve`, `subplot` and `annotation` are all lists, one entry per copied
item -- Shift+click can multi-select curves/subplots/annotations, and
Copy/Paste (see LaFigure.copy_curve/copy_subplot/copy_annotation) act on
the whole selection, not just one. `curve` is a list of (x, y, pen, name)
tuples. `subplot` is a list of plain dicts: {title, xlabel, ylabel,
curves, annotations}, where curves is again a list of (x, y, pen, name)
tuples -- the same shape LaFigure._insert_subplot_at already consumes, so
paste_subplot is a thin wrapper, not a parallel reconstruction path.
annotations is a list of AnnotationItem.to_dict() dicts. `annotation` is a
list of AnnotationItem.to_dict() dicts too -- the same shape, reused
directly by LaFigure.paste_annotation (annotation_ops.py's
AnnotationItem.from_dict is the one reconstruction path either way). Any
list is None (not just empty) until the first copy of that kind.

last_copied records which of the three ('curve', 'subplot' or
'annotation') was most recently copied, so a plain Ctrl+V
(LaFigure.paste_selection) can mirror whichever a plain Ctrl+C most
recently copied, instead of always pasting a curve.
"""

_clipboard = None


class Clipboard:
    def __init__(self):
        self.curve = None        # list of (x, y, pen, name), or None
        self.subplot = None      # list of dict, or None
        self.annotation = None   # list of AnnotationItem.to_dict(), or None
        self.last_copied = None  # 'curve', 'subplot', 'annotation', or None


def get_clipboard():
    global _clipboard
    if _clipboard is None:
        _clipboard = Clipboard()
    return _clipboard
