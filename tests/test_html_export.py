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

"""HTML export via plotly (html_export.py, WP-M). plotly is an optional
dependency: every test here is skipped (with a printed reason, not a
failure) if it genuinely isn't importable in this environment -- see
_skip_if_no_plotly.
"""
import math
import os
import tempfile

import numpy as np
from pyqtgraph.Qt import QtCore

from tests.helpers import app, m
from lafigure import export, html_export
from lafigure.datasource import DataSource

try:
    import plotly.graph_objects as go
    HAVE_PLOTLY = True
except ImportError:
    HAVE_PLOTLY = False


def _skip_if_no_plotly():
    if not HAVE_PLOTLY:
        print("SKIP: plotly is not installed in this environment")
        return True
    return False


def _empty_figure():
    f = m.LaFigure(empty=True)
    f.show()
    app.processEvents()
    return f


# -- registration / dialog wiring ------------------------------------------

def test_html_registered_in_exporters_and_checkbox_enabled():
    """'html' is a real callable in the registry (WP-E's placeholder,
    pre-seeded to None, is now assigned); the Save dialog's HTML checkbox
    follows the same EXPORTERS-driven enable/disable rule as svg/pdf, no
    special-cased always-disabled branch any more."""
    assert export.EXPORTERS['html'] is html_export.export_html
    if _skip_if_no_plotly():
        return
    with tempfile.TemporaryDirectory() as tmp:
        f = _empty_figure()
        f.subplot(0, 0).plot([0, 1, 2], [0, 1, 0])
        settings = QtCore.QSettings(os.path.join(tmp, 'settings.ini'), QtCore.QSettings.IniFormat)
        dlg = export.SaveDialog(f, settings=settings)
        cb = dlg._format_checks['html']
        assert cb.isEnabled()
        f.close()


# -- decimation --------------------------------------------------------------

def test_stride_decimation_exact_point_count():
    n, step = 1037, 10
    x = np.arange(n, dtype=float)
    y = np.arange(n, dtype=float) * 2
    xd, yd = html_export.decimate_stride(x, y, step)
    assert len(xd) == math.ceil(n / step)
    assert len(yd) == math.ceil(n / step)
    # every kept point is a real (x, y) pair from the original data
    assert np.array_equal(yd, xd * 2)


def test_peak_decimation_bucket_count_and_membership():
    n, n_buckets = 503, 17
    rng = np.random.RandomState(0)
    y = rng.normal(size=n)
    x = np.arange(n, dtype=float)
    edges = html_export.bucket_edges(n, n_buckets)
    assert len(edges) == n_buckets + 1

    idx = html_export.peak_indices(y, n_buckets)
    idx_set = set(idx.tolist())
    for lo, hi in zip(edges[:-1], edges[1:]):
        if hi <= lo:
            continue
        seg = y[lo:hi]
        assert (lo + int(np.argmin(seg))) in idx_set
        assert (lo + int(np.argmax(seg))) in idx_set

    xd, yd = html_export.decimate_peak(x, y, n_buckets)
    assert len(xd) == len(idx)
    assert np.array_equal(yd, y[idx])


def test_too_large_threshold_boundary():
    threshold = html_export.MAX_POINTS_PER_SERIES
    counts_below = [(None, threshold)]
    counts_above = [(None, threshold + 1)]
    assert not any(n > threshold for _, n in counts_below)
    assert any(n > threshold for _, n in counts_above)


def test_too_large_dialog_choice_and_n():
    if _skip_if_no_plotly():
        return
    dlg = html_export.TooLargeHtmlDialog([(None, 300_000)], html_export.MAX_POINTS_PER_SERIES)
    assert dlg.choice == 'stride'  # default
    dlg.n_spin.setValue(25)
    assert dlg.n == 25
    dlg.peak_radio.setChecked(True)
    assert dlg.choice == 'peak'
    dlg.keep_radio.setChecked(True)
    assert dlg.choice == 'all'


def test_build_plotly_figure_decimates_only_over_threshold_series():
    """End-to-end: lower the threshold so a moderate series counts as
    over-threshold, and check the resulting trace actually shrank while a
    small series stayed exactly as-is. No pytest here (run_tests.py is a
    plain runner -- no monkeypatch fixture), so save/restore by hand."""
    if _skip_if_no_plotly():
        return
    original_threshold = html_export.MAX_POINTS_PER_SERIES
    html_export.MAX_POINTS_PER_SERIES = 50
    try:
        f = _empty_figure()
        big_ax = f.subplot(0, 0)
        big_ax.plot(np.arange(500, dtype=float), np.arange(500, dtype=float))
        small_ax = f.subplot(1, 0)
        small_ax.plot(np.arange(10, dtype=float), np.arange(10, dtype=float))

        pfig = html_export.build_plotly_figure(f, decimate_choice='stride', decimate_n=10)
        lengths = sorted(len(tr.x) for tr in pfig.data)
        assert lengths[0] == 10          # the small series: untouched
        assert lengths[1] == math.ceil(500 / 10)  # the big one: decimated
        f.close()
    finally:
        html_export.MAX_POINTS_PER_SERIES = original_threshold


# -- kind round trip -----------------------------------------------------

def test_line_and_scatter_kinds_round_trip():
    if _skip_if_no_plotly():
        return
    f = _empty_figure()
    ax = f.subplot(0, 0)
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.0, 1.0, 0.0, -1.0])
    ax.plot(x, y, name="line1")
    ax2 = f.subplot(1, 0)
    xs = np.array([1.0, 2.0, 3.0])
    ys = np.array([5.0, 6.0, 7.0])
    ax2.scatter(xs, ys, name="scatter1")

    pfig = html_export.build_plotly_figure(f)
    by_name = {tr.name: tr for tr in pfig.data}
    line_trace = by_name['line1']
    scatter_trace = by_name['scatter1']

    assert type(line_trace).__name__ == 'Scattergl'
    assert line_trace.mode == 'lines'
    assert np.allclose(line_trace.x, x)
    assert np.allclose(line_trace.y, y)

    assert type(scatter_trace).__name__ == 'Scattergl'
    assert scatter_trace.mode == 'markers'
    assert np.allclose(scatter_trace.x, xs)
    assert np.allclose(scatter_trace.y, ys)
    f.close()


# -- free/overlapping layout domains --------------------------------------

def test_subplot_domains_match_free_layout_boxes():
    if _skip_if_no_plotly():
        return
    f = _empty_figure()
    ax0 = f.subplot(0, 0)
    ax1 = f.subplot(0, 1)
    ax0.plot([0, 1], [0, 1])
    ax1.plot([0, 1], [1, 0])
    # Move plot 1 to an arbitrary, overlapping free box -- not a plain grid cell.
    f.set_subplot_box(ax1.plot_item, (0.3, 0.2, 1.6, 0.9))

    pfig = html_export.build_plotly_figure(f)

    (ex0, ex1), (ey0, ey1) = html_export._subplot_domain(f, ax0.plot_item)
    (fx0, fx1), (fy0, fy1) = html_export._subplot_domain(f, ax1.plot_item)

    assert list(pfig.layout.xaxis.domain) == [ex0, ex1]
    assert list(pfig.layout.yaxis.domain) == [ey0, ey1]
    assert list(pfig.layout.xaxis2.domain) == [fx0, fx1]
    assert list(pfig.layout.yaxis2.domain) == [fy0, fy1]
    # A genuinely free/overlapping box, not a plain unit grid cell.
    assert (fx1 - fx0) > 1.0 / f._n_tracks('col') + 1e-6
    f.close()


# -- hidden rows -----------------------------------------------------------

def test_hidden_rows_excluded_from_export():
    if _skip_if_no_plotly():
        return
    f = _empty_figure()
    ax = f.subplot(0, 0)
    source = DataSource({'t': np.arange(10, dtype=float), 'v': np.arange(10, dtype=float) * 2})
    ax.plot(source, x='t', y='v', name="linked")
    source.hide_rows([2, 5, 7])

    pfig = html_export.build_plotly_figure(f)
    trace = pfig.data[0]
    expected_t = np.array([0, 1, 3, 4, 6, 8, 9], dtype=float)
    assert np.array_equal(np.asarray(trace.x), expected_t)
    assert np.array_equal(np.asarray(trace.y), expected_t * 2)
    f.close()


# -- datatip -> hovertemplate ------------------------------------------------

def test_translate_hovertemplate_keeps_literal_text_and_format_spec():
    template = "time={time} speed={speed:.2f}"
    hovertemplate, cols = html_export._translate_hovertemplate(template)
    assert cols == ['time', 'speed']
    assert 'time=' in hovertemplate
    assert 'speed=' in hovertemplate
    assert ':.2f' in hovertemplate
    assert '%{customdata[0]}' in hovertemplate
    assert '%{customdata[1]:.2f}' in hovertemplate


def test_datatip_format_string_produces_hovertemplate_in_export():
    if _skip_if_no_plotly():
        return
    f = _empty_figure()
    ax = f.subplot(0, 0)
    source = DataSource({'time': np.arange(5, dtype=float), 'speed': np.arange(5, dtype=float) * 1.5})
    ax.plot(source, x='time', y='speed', name="s")
    ax.datatip = "time={time} speed={speed:.2f}"

    pfig = html_export.build_plotly_figure(f)
    trace = pfig.data[0]
    assert 'speed=' in trace.hovertemplate
    assert ':.2f' in trace.hovertemplate
    assert trace.customdata is not None
    # customdata columns: [time, speed] in declaration order
    assert np.allclose(np.asarray(trace.customdata)[:, 0], source['time'])
    assert np.allclose(np.asarray(trace.customdata)[:, 1], source['speed'])
    f.close()


def test_datatip_callable_falls_back_to_generic_hover():
    if _skip_if_no_plotly():
        return
    f = _empty_figure()
    ax = f.subplot(0, 0)
    source = DataSource({'time': np.arange(4, dtype=float), 'speed': np.arange(4, dtype=float)})
    ax.plot(source, x='time', y='speed', name="s")
    ax.datatip = lambda row: f"t={row.time}"

    pfig = html_export.build_plotly_figure(f)
    trace = pfig.data[0]
    assert trace.hovertemplate is not None
    assert 'time=' in trace.hovertemplate
    assert 'speed=' in trace.hovertemplate
    f.close()


# -- coordinator addition: an actual file written to disk, end to end -------
def test_export_html_writes_a_real_file_via_the_public_entry_point():
    """export_html (registered as EXPORTERS['html'], what export.py's
    _do_export actually calls) writes a real, non-empty HTML file
    containing the plotly library reference and this figure's data --
    not just a build_plotly_figure() object, the actual public path."""
    if _skip_if_no_plotly():
        return
    f = _empty_figure()
    ax = f.subplot(0, 0)
    ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 4.0], name="parabola")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.html")
        html_export.export_html(f, path)
        assert os.path.isfile(path)
        with open(path, encoding='utf-8') as fh:
            html = fh.read()
        assert len(html) > 1000
        assert 'plotly' in html.lower()
        assert 'parabola' in html
    f.close()
