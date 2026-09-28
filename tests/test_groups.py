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

"""Groups: hierarchy, common label, HSL color offsets (groups.py)."""
import colorsys

import pyqtgraph as pg

from lafigure.groups import (
    Group, GroupsMixin, raw_filtered_preset, sensor_family_preset,
    default_members_by_ref,
)
from tests.helpers import m, _place


# GroupsMixin isn't wired into LaFigure's class statement yet (K1 doesn't
# own figure.py -- see this package's report); drive it through the
# unbound-method / descriptor pattern instead of fig.group_selection().
def _groups(f):
    return GroupsMixin.groups.fget(f)


def _group_selection(f):
    return GroupsMixin.group_selection(f)


def _ungroup_selection(f):
    GroupsMixin.ungroup_selection(f)


def _rgb(item):
    c = pg.mkPen(item.opts['pen']).color()
    return (c.red(), c.green(), c.blue())


def _hls(rgb):
    return colorsys.rgb_to_hls(*(c / 255.0 for c in rgb))


def _two_curve_figure():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    s1 = f._add_series(p, 'line', [0, 1, 2], [0, 1, 2], pen=pg.mkPen((200, 50, 50)), name='raw')
    s2 = f._add_series(p, 'line', [0, 1, 2], [2, 1, 0], pen=pg.mkPen((50, 50, 200)), name='filtered')
    return f, p, s1, s2


# -- construction / "never spans subplots" --------------------------------
def test_group_mixed_curve_and_annotation_same_subplot_succeeds():
    f, p, s1, s2 = _two_curve_figure()
    ann = _place(f, 'rect', p)
    group = Group([s1, ann])
    assert group.subplot is p
    assert {id(m) for m in group.members} == {id(s1), id(ann)}
    f.close()


def test_group_rejects_members_from_different_subplots():
    f = m.LaFigure(empty=True)
    p1 = f.add_subplot(row=0, col=0)
    p2 = f.add_subplot(row=1, col=0)
    s1 = f._add_series(p1, 'line', [0, 1], [0, 1], name='a')
    s2 = f._add_series(p2, 'line', [0, 1], [0, 1], name='b')
    try:
        Group([s1, s2])
    except ValueError:
        pass
    else:
        raise AssertionError("grouping across subplots must be rejected")
    f.close()


def test_add_member_rejects_a_different_subplot():
    f = m.LaFigure(empty=True)
    p1 = f.add_subplot(row=0, col=0)
    p2 = f.add_subplot(row=1, col=0)
    s1 = f._add_series(p1, 'line', [0, 1], [0, 1], name='a')
    s2 = f._add_series(p2, 'line', [0, 1], [0, 1], name='b')
    group = Group([s1])
    try:
        group.add_member(s2)
    except ValueError:
        pass
    else:
        raise AssertionError("add_member must reject a member from a different subplot")
    assert s2 not in group.members
    f.close()


def test_group_selection_noop_across_subplots():
    f = m.LaFigure(empty=True)
    p1 = f.add_subplot(row=0, col=0)
    p2 = f.add_subplot(row=1, col=0)
    s1 = f._add_series(p1, 'line', [0, 1], [0, 1], name='a')
    s2 = f._add_series(p2, 'line', [0, 1], [0, 1], name='b')
    f._select_curve(s1.item)
    f._select_curve(s2.item, additive=True)
    n_before = len(_groups(f))
    result = _group_selection(f)
    assert result is None
    assert len(_groups(f)) == n_before
    f.close()


# -- display_name ----------------------------------------------------------
def test_display_name_prefix_and_suffix_do_not_mutate_the_item():
    f, p, s1, s2 = _two_curve_figure()
    group = Group([s1, s2], common_label='Ch1 ', label_position='prefix')
    assert group.display_name(s1) == 'Ch1 raw'
    assert s1.item.name() == 'raw', "display_name must not touch the item's own stored name"

    group.label_position = 'suffix'
    group.common_label = ' (Ch1)'
    assert group.display_name(s2) == 'filtered (Ch1)'
    assert s2.item.name() == 'filtered'
    f.close()


def test_display_name_falls_back_to_own_name_with_no_common_label():
    f, p, s1, s2 = _two_curve_figure()
    group = Group([s1, s2])
    assert group.display_name(s1) == 'raw'
    f.close()


# -- HSL base-color re-tinting ----------------------------------------------
def test_hsl_retint_preserves_relative_lightness_difference():
    f, p, s1, s2 = _two_curve_figure()
    base1 = (100, 100, 220)
    group = raw_filtered_preset([s1, s2], base_color=base1, light_delta=0.15)

    _, l1, _ = _hls(base1)
    _, got_l0, _ = _hls(_rgb(s1.item))
    _, got_l1, _ = _hls(_rgb(s2.item))
    assert abs(got_l0 - (l1 + 0.15)) < 0.02
    assert abs(got_l1 - (l1 - 0.15)) < 0.02

    base2 = (220, 60, 60)
    group.set_base_color(base2)
    _, l2, _ = _hls(base2)
    _, got_l0b, _ = _hls(_rgb(s1.item))
    _, got_l1b, _ = _hls(_rgb(s2.item))
    assert abs(got_l0b - (l2 + 0.15)) < 0.02
    assert abs(got_l1b - (l2 - 0.15)) < 0.02
    # The relative lightness difference between the two members is preserved
    # across the re-tint, even though the absolute values moved.
    assert abs((got_l0b - got_l1b) - (got_l0 - got_l1)) < 0.02
    f.close()


def test_sensor_family_preset_spreads_hue_keeps_lightness():
    f = m.LaFigure(empty=True)
    p = f.add_subplot(row=0, col=0)
    members = [f._add_series(p, 'line', [0, 1], [0, 1], name=f"s{i}") for i in range(3)]
    base = (180, 90, 60)  # must have real saturation -- a gray base (s=0) makes hue irrelevant
    group = sensor_family_preset(members, base_color=base, hue_spread=0.06)
    _, base_l, _ = _hls(base)
    hues = []
    for s in members:
        h, l, _ = _hls(_rgb(s.item))
        hues.append(h)
        assert abs(l - base_l) < 0.02, "sensor_family_preset must keep lightness constant"
    assert len(set(round(h, 4) for h in hues)) == 3, "each member should get a distinct hue"
    f.close()


def test_individual_recolor_then_base_color_change_uses_the_new_color():
    f, p, s1, s2 = _two_curve_figure()
    base1 = (120, 120, 120)
    group = raw_filtered_preset([s1, s2], base_color=base1, light_delta=0.15)

    # Recolor s1 by hand, bypassing the group entirely -- a very different hue.
    custom = (10, 200, 10)
    s1.item.setPen(pg.mkPen(color=custom, width=1))
    assert _rgb(s1.item) == custom  # control: the manual recolor landed

    base2 = (50, 50, 200)
    group.set_base_color(base2)

    h_custom, l_custom, _ = _hls(custom)
    h_old, l_old, _ = _hls(base1)
    expected_dh = h_custom - h_old
    expected_dl = l_custom - l_old
    h2, l2, _ = _hls(base2)
    expected_h = (h2 + expected_dh) % 1.0
    expected_l = max(0.0, min(1.0, l2 + expected_dl))

    got_h, got_l, _ = _hls(_rgb(s1.item))
    hue_dist = min(abs(got_h - expected_h), abs(got_h - expected_h - 1), abs(got_h - expected_h + 1))
    assert hue_dist < 0.02
    assert abs(got_l - expected_l) < 0.02

    # It must NOT match what the ORIGINAL preset offset (dl=+0.15 from
    # base2) would have produced -- the offset was re-derived from the
    # hand-picked color, not the stale preset offset.
    preset_would_have_been = l2 + 0.15
    assert abs(got_l - preset_would_have_been) > 0.03
    f.close()


# -- group / ungroup, undoable ----------------------------------------------
def test_group_and_ungroup_are_undoable():
    f, p, s1, s2 = _two_curve_figure()
    f._select_curve(s1.item)
    f._select_curve(s2.item, additive=True)

    n_undo = len(f.undo_stack)
    group = _group_selection(f)
    assert group is not None and group in _groups(f)
    assert len(f.undo_stack) == n_undo + 1

    f.undo()
    assert group not in _groups(f)
    f.redo()
    assert group in _groups(f)

    f._select_curve(s1.item)  # re-select (undo/redo above didn't touch selection)
    n_undo2 = len(f.undo_stack)
    _ungroup_selection(f)
    assert group not in _groups(f)
    assert len(f.undo_stack) == n_undo2 + 1

    f.undo()
    assert group in _groups(f)
    f.redo()
    assert group not in _groups(f)
    f.close()


def test_group_selection_requires_at_least_two_items():
    f, p, s1, s2 = _two_curve_figure()
    f._select_curve(s1.item)
    assert _group_selection(f) is None
    assert _groups(f) == []
    f.close()


# -- nested groups -----------------------------------------------------------
def test_nested_group_show_hide():
    f, p, s1, s2 = _two_curve_figure()
    ann = _place(f, 'rect', p)
    inner = Group([s1, s2], common_label='Inner')
    outer = Group([inner, ann], common_label='Outer', base_color=(80, 80, 200))

    assert outer.subplot is p
    assert {id(m) for m in outer.leaf_members} == {id(s1), id(s2), id(ann)}
    assert outer.visible is True

    outer.set_visible(False)
    assert s1.item.isVisible() is False
    assert s2.item.isVisible() is False
    assert ann.isVisible() is False
    assert outer.visible is False

    outer.set_visible(True)
    assert outer.visible is True
    f.close()


def test_nested_group_to_dict_from_dict_round_trip():
    f, p, s1, s2 = _two_curve_figure()
    ann = _place(f, 'rect', p)
    inner = Group([s1, s2], common_label='Inner')
    outer = Group([inner, ann], common_label='Outer', label_position='suffix', base_color=(80, 80, 200))

    data = outer.to_dict()
    resolver = default_members_by_ref(f, p)
    rebuilt = Group.from_dict(f, p, data, resolver)

    assert rebuilt.common_label == 'Outer'
    assert rebuilt.label_position == 'suffix'
    assert rebuilt.base_color == outer.base_color
    assert len(rebuilt.members) == 2
    inner2, ann2 = rebuilt.members
    assert isinstance(inner2, Group) and inner2.common_label == 'Inner'
    assert {id(m) for m in inner2.members} == {id(s1), id(s2)}
    assert ann2 is ann
    f.close()


# -- flat to_dict/from_dict round trip ---------------------------------------
def test_to_dict_from_dict_round_trip_preserves_fields():
    f, p, s1, s2 = _two_curve_figure()
    group = Group([s1, s2], common_label='Grp-', label_position='suffix', base_color=(30, 144, 255))
    data = group.to_dict()

    resolver = default_members_by_ref(f, p)
    rebuilt = Group.from_dict(f, p, data, resolver)

    assert rebuilt.common_label == 'Grp-'
    assert rebuilt.label_position == 'suffix'
    assert rebuilt.base_color == group.base_color
    assert list(rebuilt.members) == [s1, s2]
    f.close()
