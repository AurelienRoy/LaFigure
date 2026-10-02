# LaFigure

A MATLAB-Figure-like interactive plotting window, built on [PyQtGraph](https://www.pyqtgraph.org/)
(Qt + OpenGL) so it stays fluent with millions of points.

Multiple subplots in a free-form grid, click to select, drag to resize/move/swap,
curve and subplot copy-paste (including across separate figure windows), undo/redo,
annotations, data brushing/linked selection, 3D scenes, interactive controls, and a
Figure Manager for tracking multiple open figures — see the full feature list and
design notes in [CLAUDE.md](CLAUDE.md).

It is aimed at data analysis, with a lot of freedom in the interactive plotting to
make it easier to find unknown patterns, investigate time series, then share reports
with the rest of the team.

![One of the series-kinds gallery figures, showing bubblechart3d, barh, stem, heatmap, errorband, quiver, feather, contour, and surface subplots](docs/screenshot_series_kind_gallery3.png)

## Install

Requires Python >= 3.9.

```bash
git clone https://github.com/AurelienRoy/LaFigure.git
cd LaFigure
pip install -e .
```

Optional extras: `pip install -e ".[pandas]"` (DataSource from a DataFrame),
`pip install -e ".[html]"` (HTML export via plotly).

Tested on Windows and Ubuntu 22.04/24.04 — see `.github/workflows/tests.yml`.

## Quickstart

```bash
python -m lafigure
```

opens a Figure Manager plus a demo figure. As a library:

```python
from pyqtgraph.Qt import QtWidgets
from lafigure import LaFigure

app = QtWidgets.QApplication([])
fig = LaFigure(empty=True)
ax = fig.subplot(0, 0, title="My data")
ax.plot([0, 1, 2, 3], [0, 1, 4, 9])
fig.show()
app.exec()
```

More runnable examples — series kinds, annotations, linked brushing, 3D scenes,
interactive controls, copy/paste across figures — are in [`examples/`](examples/).
Run any of them directly: `python examples/series_kinds_gallery.py`.

## Running the tests

```bash
QT_QPA_PLATFORM=offscreen python run_tests.py
```

No pytest — `run_tests.py` is a small standalone runner; pass name filters to
narrow it, e.g. `python run_tests.py layout`.

## Contributing

See [CLAUDE.md](CLAUDE.md) for the architecture, the module layout, and the
hard-won lessons behind this codebase's design. If you're coding here with
Claude Code, read it first — it's written for that.

Future directions:
Give maximal freedom to the user to manipulate figures/plots/data through mouse
clicks or keyboard shortcuts.
Once satisfied, give the ability to generate the equivalent code, to reproduce
the same figures immediately.
Exports are aimed to share with a team, with graphs providing zooming and data
cursor inspection capabilities, and .png images for document reports.
Many real world signals are noisy, only interesting on some time phases unknown
or described in enclosed metadata (modes, messages, ...), give capacities for
easy filtering and plotting these metadata.

## License

BSD 2-Clause — see [LICENSE](LICENSE).
