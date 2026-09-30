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

"""lafigure/kinds/log_kinds.py -- loglog/semilogx/semilogy."""
import numpy as np
import pyqtgraph as pg

from lafigure.axes import Axes
from tests.helpers import m


def _figure_with_plot():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    return f, p


def _log_state(plot_item):
    return (plot_item.ctrl.logXCheck.isChecked(), plot_item.ctrl.logYCheck.isChecked())


# -- loglog ---------------------------------------------------------------
def test_loglog_builds_a_real_plotdataitem_and_registers_in_ax_series():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    x, y = [1.0, 10.0, 100.0], [2.0, 20.0, 200.0]
    s = ax.loglog(x, y, name='ll')
    assert isinstance(s.item, pg.PlotDataItem)
    assert s.item in p.listDataItems()
    assert s.kind == 'loglog'
    assert [x.item for x in ax.series] == [s.item]
    f.close()


def test_loglog_sets_both_axes_log_and_maps_both_axes_data():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    x, y = [1.0, 10.0, 100.0], [2.0, 20.0, 200.0]
    s = ax.loglog(x, y)
    assert _log_state(p) == (True, True)
    disp_x, disp_y = s.item.getData()
    np.testing.assert_allclose(disp_x, np.log10(x))
    np.testing.assert_allclose(disp_y, np.log10(y))
    # The raw (undisplayed) data is untouched.
    np.testing.assert_allclose(s.item.xData, x)
    np.testing.assert_allclose(s.item.yData, y)
    np.testing.assert_allclose(s.x, x)
    np.testing.assert_allclose(s.y, y)
    f.close()


# -- semilogx ---------------------------------------------------------------
def test_semilogx_sets_only_x_log_and_maps_only_x_data():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    x, y = [1.0, 10.0, 100.0], [2.0, 4.0, -6.0]
    s = ax.semilogx(x, y, name='lx')
    assert s.kind == 'semilogx'
    assert _log_state(p) == (True, False)
    disp_x, disp_y = s.item.getData()
    np.testing.assert_allclose(disp_x, np.log10(x))
    np.testing.assert_allclose(disp_y, y), "y is unmapped -- semilogx only logs x"
    f.close()


# -- semilogy ---------------------------------------------------------------
def test_semilogy_sets_only_y_log_and_maps_only_y_data():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    x, y = [1.0, 2.0, 3.0], [1.0, 10.0, 100.0]
    s = ax.semilogy(x, y, name='ly')
    assert s.kind == 'semilogy'
    assert _log_state(p) == (False, True)
    disp_x, disp_y = s.item.getData()
    np.testing.assert_allclose(disp_x, x), "x is unmapped -- semilogy only logs y"
    np.testing.assert_allclose(disp_y, np.log10(y))
    f.close()


# -- non-positive values (pyqtgraph's own behavior; see module docstring) ---
def test_loglog_nonpositive_values_become_nan_in_display_only():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    x = [1.0, 0.0, -5.0, 100.0]
    y = [1.0, 10.0, 100.0, 1000.0]
    s = ax.loglog(x, y)
    # Nothing dropped: the raw data keeps every point, non-positive included.
    assert len(s.item.xData) == 4
    np.testing.assert_allclose(s.item.xData, x)
    disp_x, disp_y = s.item.getData()
    assert len(disp_x) == 4, "non-positive values are mapped to NaN, not dropped"
    assert np.isfinite(disp_x[0]) and disp_x[0] == 0.0  # log10(1) == 0
    assert np.isnan(disp_x[1]), "log10(0) is -inf, replaced by NaN"
    assert np.isnan(disp_x[2]), "log10(negative) is NaN"
    assert np.isfinite(disp_x[3])
    np.testing.assert_allclose(disp_y, np.log10(y))
    f.close()


def test_semilogy_nonpositive_y_becomes_nan_x_untouched():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    x = [1.0, 2.0, 3.0]
    y = [10.0, 0.0, -1.0]
    s = ax.semilogy(x, y)
    disp_x, disp_y = s.item.getData()
    np.testing.assert_allclose(disp_x, x)
    assert np.isfinite(disp_y[0])
    assert np.isnan(disp_y[1])
    assert np.isnan(disp_y[2])
    # Raw data is preserved exactly, zero/negative included.
    np.testing.assert_allclose(s.item.yData, y)
    f.close()


# -- the checkbox-no-op wrinkle (module docstring) ---------------------------
def test_second_loglog_series_on_an_already_log_subplot_is_still_log_mapped():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    ax.loglog([1.0, 10.0], [1.0, 10.0])
    assert _log_state(p) == (True, True)
    # This second series' own item.setLogMode is never reached through the
    # checkbox (already checked -> no toggled signal) -- must still be
    # mapped directly by _LogKind.setup.
    s2 = ax.loglog([1.0, 100.0], [1.0, 1000.0])
    disp_x, disp_y = s2.item.getData()
    np.testing.assert_allclose(disp_x, np.log10([1.0, 100.0]))
    np.testing.assert_allclose(disp_y, np.log10([1.0, 1000.0]))
    f.close()


# -- calling one log kind after another on the same subplot (documented) ----
def test_semilogy_after_loglog_on_same_subplot_turns_x_log_back_off():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    ax.loglog([1.0, 10.0], [1.0, 10.0])
    assert _log_state(p) == (True, True)
    ax.semilogy([1.0, 2.0], [1.0, 10.0])
    assert _log_state(p) == (False, True), \
        "log mode is subplot-wide -- the later call's own state wins"
    f.close()


# -- to_dict / create round trip ---------------------------------------------
def test_loglog_to_dict_create_round_trip():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    x, y = [1.0, 10.0, 100.0], [3.0, 4.0, 5.0]
    s = ax.loglog(x, y, name='abc')
    d = s.to_dict()
    assert d['kind'] == 'loglog'
    np.testing.assert_allclose(d['x'], x)
    np.testing.assert_allclose(d['y'], y)

    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'loglog'
    assert s2.item.name() == 'abc'
    np.testing.assert_allclose(s2.x, x)
    np.testing.assert_allclose(s2.y, y)
    assert _log_state(q) == (True, True), "re-creating from the dict must re-apply log mode"
    f.close()


def test_semilogx_to_dict_create_round_trip():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.semilogx([1.0, 2.0, 4.0], [1.0, 2.0, 3.0], name='sx')
    d = s.to_dict()
    assert d['kind'] == 'semilogx'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'semilogx'
    assert _log_state(q) == (True, False)
    f.close()


def test_semilogy_to_dict_create_round_trip():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.semilogy([1.0, 2.0, 4.0], [1.0, 2.0, 3.0], name='sy')
    d = s.to_dict()
    assert d['kind'] == 'semilogy'
    q = f.add_subplot(row=1, col=0)
    s2 = f._add_series_from_dict(q, d)
    assert s2.kind == 'semilogy'
    assert _log_state(q) == (False, True)
    f.close()


# -- copy/paste through the real clipboard path (mirrors _base's own test) --
def test_loglog_round_trips_through_copy_paste():
    f, p = _figure_with_plot()
    ax = Axes(f, p)
    s = ax.loglog([1.0, 2.0, 4.0], [10.0, 20.0, 40.0], name='cp')
    f._select_curve(s.item)
    f.copy_curve()
    q = f.add_subplot(row=1, col=0)
    f.focused_plot = q
    f.paste_curve()
    (pasted,) = f._series_on(q)
    assert pasted.kind == 'loglog'
    np.testing.assert_allclose(pasted.x, [1.0, 2.0, 4.0])
    np.testing.assert_allclose(pasted.y, [10.0, 20.0, 40.0])
    assert pasted.item.name() == 'cp'
    assert _log_state(q) == (True, True)
    f.close()


# -- capabilities delegate to the base 'line' kind ---------------------------
def test_log_kinds_capabilities_match_line():
    from lafigure.series import SERIES_KINDS
    line = SERIES_KINDS['line']
    for name in ('loglog', 'semilogx', 'semilogy'):
        assert SERIES_KINDS[name].capabilities == line.capabilities
