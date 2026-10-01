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

"""R4-K3D: `plot3` (a _base.DerivedKind on 'line3d') and `bubblechart3d`
(a per-point-sized 3D scatter, degraded to discrete size buckets -- see
kinds/bubblechart3d.py's module docstring for why).

Runs under QT_QPA_PLATFORM=offscreen, so every 3D cell renders through the
QPainter fallback (no GL context, CLAUDE.md bug #10) -- exactly what these
tests exercise; see tests/test_3d.py's own module docstring for what that
does and doesn't cover.
"""
import numpy as np

from lafigure import DataSource, SERIES_KINDS
from lafigure.kinds._base import size_scale
from lafigure.kinds.bubblechart3d import Bubble3DItem, DEFAULT_HI_PX, DEFAULT_LO_PX
from lafigure.kinds.line3d import Line3DItem
from lafigure.view3d import Kind3D
from tests.helpers import app, m

N = 12


def _cell():
    f = m.LaFigure(empty=True)
    ax = f.subplot(0, 0, axes_type='3d')
    return f, ax


# -- plot3 ---------------------------------------------------------------

def test_plot3_is_registered_as_a_derived_kind_of_line3d():
    kind = SERIES_KINDS['plot3']
    assert kind.base == 'line3d'
    assert kind.capabilities == SERIES_KINDS['line3d'].capabilities
    assert 'brush' in kind.capabilities and 'copy' in kind.capabilities
    assert not {'fft', 'remove_average', 'fit'} & kind.capabilities


def test_plot3_builds_a_line3d_item_with_the_exact_trajectory():
    f, ax = _cell()
    t = np.linspace(0, 2 * np.pi, N)
    x, y, z = np.cos(t), np.sin(t), t
    s = ax.plot3(x, y, z=z, name="helix", pen=(10, 20, 30))
    assert s.kind == 'plot3'
    assert isinstance(s.item, Line3DItem)
    assert s.item in ax.plot_item.listDataItems()
    assert [ser.item for ser in ax.series] == [s.item]
    assert s.y is None and s.x.shape == (N, 3)
    assert np.allclose(s.x[:, 0], x) and np.allclose(s.x[:, 1], y) and np.allclose(s.x[:, 2], z)
    f.close()


def test_plot3_to_dict_round_trips_through_add_series_from_dict():
    f, ax = _cell()
    t = np.linspace(0, 10, N)
    s = ax.plot3(t, t * 2, z=t * 3, name="ramp")
    d = s.to_dict()
    assert d['kind'] == 'plot3'
    s2 = f._add_series_from_dict(ax.plot_item, d)
    assert s2.kind == 'plot3'
    assert np.array_equal(s2.x, s.x)
    assert s2.name == "ramp"
    f.close()


def test_plot3_from_a_shared_datasource_stays_linked():
    f, ax = _cell()
    src = DataSource({'a': np.arange(N, dtype=float), 'b': np.arange(N, dtype=float) * 2,
                      'c': np.arange(N, dtype=float) * 3})
    s = ax.plot3(src, x='a', y='b', z='c')
    assert s.source is src
    assert np.allclose(s.x[:, 0], src['a'])
    f.close()


def test_plot3_refuses_on_a_2d_subplot():
    f = m.LaFigure(empty=True)
    ax2 = f.subplot(0, 0)
    try:
        ax2.plot3([1, 2], [3, 4], z=[5, 6])
    except ValueError:
        pass
    else:
        raise AssertionError("plot3 on a 2D subplot must refuse clearly")
    f.close()


# -- bubblechart3d ---------------------------------------------------------

def test_bubblechart3d_is_registered_with_kind3d_capabilities():
    kind = SERIES_KINDS['bubblechart3d']
    assert isinstance(kind, Kind3D)
    assert 'brush' in kind.capabilities and 'copy' in kind.capabilities
    assert not {'fft', 'remove_average', 'fit'} & kind.capabilities


def test_bubblechart3d_requires_a_size_argument():
    f, ax = _cell()
    try:
        ax.bubblechart3d([1, 2], [3, 4], z=[5, 6])
    except TypeError:
        pass
    else:
        raise AssertionError("bubblechart3d with no size= must refuse clearly")
    f.close()


def test_bubblechart3d_refuses_on_a_2d_subplot():
    f = m.LaFigure(empty=True)
    ax2 = f.subplot(0, 0)
    try:
        ax2.bubblechart3d([1, 2], [3, 4], z=[5, 6], size=[1, 2])
    except ValueError:
        pass
    else:
        raise AssertionError("bubblechart3d on a 2D subplot must refuse clearly")
    f.close()


def test_bubblechart3d_builds_an_item_with_exact_positions_and_scaled_sizes():
    f, ax = _cell()
    rng = np.random.default_rng(0)
    x, y, z = rng.normal(size=N), rng.normal(size=N), rng.normal(size=N)
    sizes = np.linspace(1.0, 100.0, N)
    s = ax.bubblechart3d(x, y, z=z, size=sizes, pen=(0, 0, 0))
    assert s.kind == 'bubblechart3d'
    item = s.item
    assert isinstance(item, Bubble3DItem)
    assert np.allclose(item.positions()[:, 0], x)
    assert np.allclose(item.positions()[:, 1], y)
    assert np.allclose(item.positions()[:, 2], z)
    assert np.array_equal(item._raw_sizes, sizes)
    expected_px = size_scale(sizes, DEFAULT_LO_PX, DEFAULT_HI_PX)
    assert np.allclose(item._pixel_sizes, expected_px)
    f.close()


def test_bubblechart3d_from_a_datasource_size_column():
    f, ax = _cell()
    src = DataSource({'a': np.arange(N, dtype=float), 'b': np.arange(N, dtype=float),
                      'c': np.arange(N, dtype=float), 's': np.linspace(1.0, 5.0, N)})
    s = ax.bubblechart3d(src, x='a', y='b', z='c', size='s')
    assert s.source is src
    assert np.array_equal(s.item._raw_sizes, src['s'])
    f.close()


def test_bubblechart3d_to_dict_round_trips_positions_and_raw_sizes():
    f, ax = _cell()
    x, y, z = np.arange(N, dtype=float), np.arange(N, dtype=float) + 1, np.arange(N, dtype=float) + 2
    sizes = np.linspace(2.0, 40.0, N)
    s = ax.bubblechart3d(x, y, z=z, size=sizes, name="bubbles")
    d = s.to_dict()
    assert d['kind'] == 'bubblechart3d'
    assert np.array_equal(d['style']['size'], sizes)
    assert d['style']['lo_px'] == DEFAULT_LO_PX and d['style']['hi_px'] == DEFAULT_HI_PX
    s2 = f._add_series_from_dict(ax.plot_item, d)
    assert s2.kind == 'bubblechart3d' and s2.name == "bubbles"
    assert np.array_equal(s2.x, s.x)
    assert np.array_equal(s2.item._raw_sizes, sizes)
    assert np.allclose(s2.item._pixel_sizes, s.item._pixel_sizes)
    f.close()


def test_bubblechart3d_degrades_to_discrete_size_buckets_that_actually_differ():
    """The renderer has no true per-vertex size (module docstring): confirm
    the bucketing actually produces more than one Primitive with genuinely
    different `size` values when the input sizes vary widely, and exactly
    one Primitive (covering every point) when they don't."""
    f, ax = _cell()
    sizes = np.concatenate([np.full(N // 2, 1.0), np.full(N // 2, 500.0)])
    s = ax.bubblechart3d(np.arange(N, dtype=float), np.arange(N, dtype=float),
                         z=np.arange(N, dtype=float), size=sizes)
    prims = s.item.primitives()
    total_points = sum(len(p.pos) for p in prims)
    assert total_points == N, "every point is drawn exactly once across the buckets"
    rendered_sizes = sorted({p.size for p in prims})
    assert len(rendered_sizes) >= 2, "widely different values render at genuinely different sizes"
    assert rendered_sizes[0] < rendered_sizes[-1]

    uniform = ax.bubblechart3d(np.arange(N, dtype=float) + 100, np.arange(N, dtype=float),
                               z=np.arange(N, dtype=float), size=np.full(N, 7.0))
    prims_uniform = uniform.item.primitives()
    assert len(prims_uniform) == 1 and len(prims_uniform[0].pos) == N
    f.close()


def test_bubblechart3d_renders_through_the_offscreen_fallback():
    """No GL under QT_QPA_PLATFORM=offscreen (CLAUDE.md bug #10): confirm
    the cell still produces a real, non-null image via the QPainter
    fallback, exactly like the other 3D kinds' own tests."""
    f, ax = _cell()
    f.show()
    app.processEvents()
    sizes = np.linspace(1.0, 50.0, N)
    ax.bubblechart3d(np.arange(N, dtype=float), np.arange(N, dtype=float),
                     z=np.zeros(N), size=sizes, pen=(0, 0, 0))
    vb = ax.plot_item.getViewBox()
    vb.render_now()
    assert vb.last_backend in ('gl', 'painter')
    assert not vb.image_item.pixmap().isNull()
    f.close()


def test_bubblechart3d_brushing_selects_rows_by_projection():
    """rows_in_rect/show_rows (Kind3D, unmodified) work unchanged on a
    Bubble3DItem, the same brushing contract every other 3D kind gets."""
    f, ax = _cell()
    f.show()
    app.processEvents()
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.0, 0.0, 0.0, 0.0])
    z = np.array([0.0, 0.0, 0.0, 0.0])
    sizes = np.array([1.0, 2.0, 3.0, 4.0])
    s = ax.bubblechart3d(x, y, z=z, size=sizes)
    vb = ax.plot_item.getViewBox()
    vb.render_now()
    kind = SERIES_KINDS['bubblechart3d']
    sx, sy, front = vb.projected(s.item)
    assert front.all()
    # The default isometric camera projects this straight line on a
    # diagonal (not axis-aligned), so build the rect from points 0/1's
    # own projected extent rather than assuming a horizontal spread.
    from pyqtgraph.Qt import QtCore
    pad = 3.0
    rect = QtCore.QRectF(min(sx[0], sx[1]) - pad, min(sy[0], sy[1]) - pad,
                         abs(sx[1] - sx[0]) + 2 * pad, abs(sy[1] - sy[0]) + 2 * pad)
    assert not rect.contains(QtCore.QPointF(sx[2], sy[2])), "control: point 2 must fall outside the rect"
    rows = kind.rows_in_rect(s.item, s, rect)
    assert set(rows.tolist()) == {0, 1}
    f.close()
