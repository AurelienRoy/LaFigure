# Copyright 2026, Aurélien ROY, <lafigure@proton.me>
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

"""A procedural grayscale image (`ax.imshow`, lafigure/kinds/imshow.py),
edited live from a separate `ControlPanelWindow` (lafigure/controls.py,
CLAUDE.md Phase 5): sliders for brightness/contrast/blur, a colormap
dropdown, an "invert" checkbox, and a reactive statistics table -- every
edit is undoable (Ctrl+Z steps back one edit at a time, all the way to
the untouched original).

No scipy, no real image file: the base image and the blur are both plain numpy.

**A real gap this example works around, reported rather than hidden.**
`Series.set_data(x, y)` (series.py) requires `len(x) == len(y)` with a
non-None `y` -- it has no way to represent an image kind's `get_xy`/
`set_xy` convention, `(2-D matrix, None)` (see lafigure/kinds/imshow.py's
own module docstring: "Series.y is always None"). Calling
`series.set_data(new_image, None)` raises `TypeError: len() of unsized
object` (confirmed empirically while building this example, not assumed).
So this script pushes undo entries directly through the same primitive
`Series.set_data` itself calls internally, `LaFigure._push_history`
(history.py) -- see `_push_image_edit` below. This mirrors
`_create_annotation`'s already-established precedent (CLAUDE.md's
"Annotations" feature entry) of an example calling one specific,
documented private method because there is genuinely no public
alternative yet; flagged in this package's own report as a suggested
follow-up (`Series.set_data` could grow an image-kind branch that skips
the length check when `y is None`).

**Embedding controls in a grid cell, not a separate window** -- the gap
CLAUDE.md's Phase 5 leaves open: "the grid-cell case is intentionally NOT
wired into layout.py"; `ControlPanel` is a plain, layout-agnostic
`QWidget`, ready to be wrapped in a `QGraphicsProxyWidget` and given
`axes_type='controls'` support in `layout.py` (controls.py's own module
docstring spells out the proposed hook) -- until a future package builds
that, `open_control_panel(figure=fig)` (a separate top-level window) is
the only host.

Run (from anywhere -- this file adds the repo root to sys.path itself,
since lafigure isn't pip-installed):
    python examples/image_processing_with_controls_example.py
"""
import os
import sys

import numpy as np
from pyqtgraph.Qt import QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lafigure
_debug_log = lafigure.enable_debug_mode()
print(f"Debug log: {_debug_log}")

IMAGE_SIZE = 160


def _procedural_image(size=IMAGE_SIZE):
    """A grayscale test image (0..255): a soft sinusoidal plaid plus three
    Gaussian blobs -- enough structure that brightness/contrast/blur are
    all visibly meaningful, with no file to download."""
    xs = np.linspace(-3, 3, size)
    ys = np.linspace(-3, 3, size)
    X, Y = np.meshgrid(xs, ys)
    base = 128 + 60 * np.sin(2.2 * X) * np.cos(2.2 * Y)
    for cx, cy, amp, sigma in ((-1.4, -1.0, 90, 0.55), (1.6, 1.2, -70, 0.7),
                               (0.3, -1.6, 55, 0.35)):
        base += amp * np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * sigma ** 2))
    return np.clip(base, 0, 255)


def _box_blur(img, radius):
    """A separable box blur via a cumulative-sum moving average -- plain
    numpy, no scipy. radius=0 is a no-op (returns img unchanged)."""
    if radius <= 0:
        return img
    out = img
    for axis in (0, 1):
        k = 2 * radius + 1
        pad_width = [(0, 0), (0, 0)]
        pad_width[axis] = (radius, radius)
        padded = np.pad(out, pad_width, mode='edge')
        csum = np.cumsum(padded, axis=axis)
        zeros_shape = list(csum.shape)
        zeros_shape[axis] = 1
        csum = np.concatenate([np.zeros(zeros_shape), csum], axis=axis)
        hi = [slice(None), slice(None)]
        lo = [slice(None), slice(None)]
        hi[axis] = slice(k, None)
        lo[axis] = slice(None, -k)
        out = (csum[tuple(hi)] - csum[tuple(lo)]) / k
    return out


def _push_image_edit(fig, item, old_image, new_image):
    """Bridges LaFigure's central undo primitive directly for a kind
    Series.set_data can't represent yet -- see the module docstring above
    for exactly why. One undo/redo entry per call, same contract
    Series.set_data itself offers for every other kind."""
    item.setImage(new_image)
    fig._push_history(lambda: item.setImage(old_image), lambda: item.setImage(new_image))


def main():
    app = QtWidgets.QApplication(sys.argv)

    original = _procedural_image()

    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- image processing with live controls")
    ax = fig.subplot(0, 0, title="Processed image")
    # 'CET-L1' is pyqtgraph's built-in linear-lightness (black-to-white)
    # colormap -- there is no plain 'gray'/'grey' name in the installed
    # pyqtgraph's own registry (confirmed empirically), only a matplotlib-
    # style 'Greys' or this CET one; CET-L1 needs no extra 'source=' kwarg.
    series = ax.imshow(original, cmap='CET-L1')
    item = series.item  # a real pg.ImageItem -- ordinary pyqtgraph calls
                        # (setImage, setColorMap) work on it directly, the
                        # same "ax.plot_item is a real PlotItem" convention
                        # line_signal_annotations.py already uses.

    # A tiny trigger-only DataSource purely to drive the reactive stats
    # table below via its public notify_change() -- the image itself
    # isn't a DataSource (an imshow series has no row-per-pixel model, see
    # kinds/imshow.py's own module docstring), so nothing would otherwise
    # tell a table(..., depends_on=[...]) to refresh after an edit.
    trigger = lafigure.DataSource({'tick': [0]})

    state = {'brightness': 0.0, 'contrast': 100.0, 'blur': 0, 'invert': False}

    def recompute():
        img = original * (state['contrast'] / 100.0) + state['brightness']
        img = _box_blur(img, state['blur'])
        img = np.clip(img, 0, 255)
        if state['invert']:
            img = 255 - img
        return img

    def apply_edit():
        old_image = np.array(item.image, copy=True)
        new_image = recompute()
        _push_image_edit(fig, item, old_image, new_image)
        trigger.notify_change()

    def on_brightness(v):
        state['brightness'] = float(v)
        apply_edit()

    def on_contrast(v):
        state['contrast'] = float(v)
        apply_edit()

    def on_blur(v):
        state['blur'] = int(v)
        apply_edit()

    def on_invert(v):
        state['invert'] = bool(v)
        apply_edit()

    def on_colormap(name):
        import pyqtgraph as pg
        cmap = pg.colormap.get(name)
        item.setColorMap(cmap)
        colorbar = getattr(item, '_lafigure_colorbar', None)
        if colorbar is not None:
            colorbar.setColorMap(cmap)

    def on_reset():
        state.update(brightness=0.0, contrast=100.0, blur=0, invert=False)
        old_image = np.array(item.image, copy=True)
        _push_image_edit(fig, item, old_image, original)
        trigger.notify_change()

    def stats():
        img = item.image
        return {
            'stat': ['mean', 'std', 'min', 'max'],
            'value': [f"{img.mean():.2f}", f"{img.std():.2f}",
                      f"{img.min():.2f}", f"{img.max():.2f}"],
        }

    win = lafigure.open_control_panel(figure=fig, title="Image controls")
    win.slider('Brightness', -100, 100, value=0, on_change=on_brightness)
    win.slider('Contrast %', 10, 300, value=100, on_change=on_contrast)
    win.slider('Blur radius', 0, 8, value=0, on_change=on_blur)
    win.dropdown('Colormap', ['CET-L1', 'viridis', 'plasma', 'inferno'],
                value='CET-L1', on_change=on_colormap)
    win.checkbox('Invert', checked=False, on_change=on_invert)
    win.button('Reset (undoable)', on_click=on_reset)
    # The colorbar's two fixed dashed lines already track item.sigImageChanged
    # on their own -- every setImage() call above moves them live, with no extra
    # wiring needed here.
    win.table(stats, depends_on=[trigger])

    fig.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
