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

"""Groups: a hierarchy over Series/AnnotationItem (CLAUDE.md's Phase 2b
"Groups" and "Group common label" bullets).

A Group is nestable (a Group can itself be a member of another Group) and
**never spans subplots** -- an explicit, already-made user decision (see
CLAUDE.md's Phase 2b heading); a group's "subplot" is fixed, at
construction, to its first member's subplot (None only for a group made
entirely of free-floating, 'figure'-anchored annotations). Constructing or
`add_member`-ing across a different subplot raises ValueError; callers
that want a silent no-op instead (e.g. Ctrl+G with a mixed selection)
catch it -- see GroupsMixin.group_selection below.

Color: `base_color` is always stored as a plain (r, g, b) 0-255 tuple.
Each member's *actual* rendered color is kept as an (hue, lightness)
offset from `base_color`, computed fresh (from whatever the member's
color actually is right now) every time `set_base_color` runs -- so a
member recolored by hand between two `set_base_color` calls has its new
offset derived from that hand-picked color, not from any earlier preset
offset. `colorsys` (stdlib) does the RGB<->HLS math; no new dependency.

This module also owns two mechanisms that don't yet have another owner
(K1 claims them here per PLAN.md's file-ownership table, same pattern as
any package that's first to need `history.py`/`annotation_ops.py`):
Ctrl+G/Ctrl+Shift+G (`GroupsMixin`, not yet wired into `LaFigure` itself --
see this package's report for the one-line `figure.py` diff) and
serialization (`Group.to_dict`/`from_dict`, `groups_from_dict` -- the hook
`clip_ops.py` would call after rebuilding a pasted subplot's series/
annotations, also reported rather than wired in directly, since K1
doesn't own clip_ops.py).
"""
import colorsys

import pyqtgraph as pg

from .annotations import AnnotationItem, SHAPE_LABELS
from .series import Series


# -- color helpers (module-level: also used by the preset functions before
# a Group has fully taken ownership of its members' colors) --------------
def _rgb_to_hls(rgb):
    r, g, b = (c / 255.0 for c in rgb)
    return colorsys.rgb_to_hls(r, g, b)  # (h, l, s), all 0..1


def _hls_to_rgb(h, l, s):
    h = h % 1.0
    l = max(0.0, min(1.0, l))
    s = max(0.0, min(1.0, s))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return tuple(int(round(c * 255)) for c in (r, g, b))


def _member_color(member):
    """The member's current, actual rendered color (a plain (r,g,b))."""
    if isinstance(member, Group):
        return member.base_color if member.base_color is not None else (128, 128, 128)
    if isinstance(member, AnnotationItem):
        c = member.pen.color()
        return (c.red(), c.green(), c.blue())
    # Series -- no set_color of its own (WP-H's docstrings call item the
    # public escape hatch); read/write its pen (and brush, if any) directly.
    item = member.item
    opts = getattr(item, 'opts', None)
    pen = opts.get('pen') if opts else None
    if pen is not None:
        c = pg.mkPen(pen).color()
        return (c.red(), c.green(), c.blue())
    return (0, 0, 0)


def _apply_member_color(member, rgb):
    if isinstance(member, Group):
        member.set_base_color(rgb)
        return
    if isinstance(member, AnnotationItem):
        new_pen = pg.mkPen(color=rgb, width=member.pen.widthF())
        new_pen.setCosmetic(True)
        member.pen = new_pen
        if member._text_item is not None:
            member._text_item.setDefaultTextColor(new_pen.color())
        member.update()
        return
    # Series
    item = member.item
    opts = getattr(item, 'opts', None)
    if opts is not None and 'pen' in opts and hasattr(item, 'setPen'):
        old_pen = pg.mkPen(opts.get('pen')) if opts.get('pen') is not None else pg.mkPen('k')
        new_pen = pg.mkPen(color=rgb, width=old_pen.widthF())
        item.setPen(new_pen)
        # selection_ui's _unhighlight_curve_pen restores from '_orig_pen'
        # (the pre-highlight pen) -- keep it in sync so deselecting a
        # currently-highlighted, just-recolored curve doesn't revert to
        # the color it had before this recolor.
        if '_orig_pen' in opts:
            opts['_orig_pen'] = new_pen
    if opts is not None and opts.get('brush') is not None and hasattr(item, 'setBrush'):
        item.setBrush(pg.mkBrush(rgb))


def _member_visible(member):
    if isinstance(member, Group):
        return member.visible
    if isinstance(member, AnnotationItem):
        return member.isVisible()
    return member.item.isVisible()


def _set_member_visible(member, value):
    if isinstance(member, Group):
        member.set_visible(value)
        return
    if isinstance(member, AnnotationItem):
        member.setVisible(value)
        return
    member.item.setVisible(value)


def _member_plot(member):
    """The PlotItem `member` lives on -- None only for a free-floating
    ('figure'-anchored) annotation, or a group made entirely of those."""
    if isinstance(member, Group):
        return member.subplot
    if isinstance(member, AnnotationItem):
        return member.parent_plot
    # Series
    return member.figure._curve_plot(member.item)


def _iter_leaf_members(members):
    for m in members:
        if isinstance(m, Group):
            yield from _iter_leaf_members(m.members)
        else:
            yield m


def _average_rgb(members):
    colors = [_member_color(m) for m in members]
    n = len(colors)
    return tuple(int(round(sum(c[i] for c in colors) / n)) for i in range(3))


class Group:
    """See the module docstring. `.members` is the flat, one-level list of
    Series/AnnotationItem/Group this group was built from; `.leaf_members`
    recursively expands nested groups."""

    def __init__(self, members, common_label='', label_position='prefix', base_color=None):
        members = list(members)
        if not members:
            raise ValueError("a group needs at least one member")
        if label_position not in ('prefix', 'suffix'):
            raise ValueError(f"label_position must be 'prefix' or 'suffix', got {label_position!r}")
        self.figure = members[0].figure
        self._subplot = _member_plot(members[0])
        for m in members[1:]:
            if _member_plot(m) is not self._subplot:
                raise ValueError("a group cannot span subplots")
        self.members = members
        self.common_label = common_label
        self.label_position = label_position
        self.base_color = None          # set below if given, else stays None until set_base_color
        self._offsets = {}              # id(member) -> (hue_delta, lightness_delta)
        if base_color is not None:
            self.set_base_color(base_color)

    def __repr__(self):
        return f"<Group {self.common_label!r} ({len(self.members)} members)>"

    # -- structure -----------------------------------------------------
    @property
    def subplot(self):
        return self._subplot

    @property
    def leaf_members(self):
        """Every Series/AnnotationItem this group ultimately contains,
        recursing through any nested Group members."""
        return list(_iter_leaf_members(self.members))

    def add_member(self, member):
        """Add `member` to this group -- rejects (ValueError) a member
        whose subplot differs from this group's (see module docstring)."""
        if _member_plot(member) is not self._subplot:
            raise ValueError("a group cannot span subplots")
        self.members.append(member)
        self._offsets.setdefault(id(member), (0.0, 0.0))
        if self.base_color is not None:
            h, l, s = _rgb_to_hls(self.base_color)
            dh, dl = self._offsets[id(member)]
            _apply_member_color(member, _hls_to_rgb(h + dh, l + dl, s))

    # -- visibility (view state -- NOT undoable, like every other
    # visibility toggle in this app; see CLAUDE.md's "Not covered by
    # undo" list) --------------------------------------------------------
    @property
    def visible(self):
        """True if every leaf member is shown, False if none are, None if
        it's a mix (tristate, for a future checkbox in the Curve browser)."""
        leaves = self.leaf_members
        if not leaves:
            return False
        states = [_member_visible(m) for m in leaves]
        if all(states):
            return True
        if not any(states):
            return False
        return None

    def set_visible(self, value):
        for m in self.leaf_members:
            _set_member_visible(m, value)

    # -- display label ---------------------------------------------------
    def display_name(self, member):
        """common_label + member's own name (or the reverse, per
        label_position) -- a pure display-layer transform: never touches
        the member's own stored name/text. Menus/legend/curve-browser call
        this to render a grouped member's label; the item's real
        `.name()`/`.text` is untouched so ungrouping needs no repair."""
        own = self._member_own_name(member)
        if not self.common_label:
            return own
        if self.label_position == 'prefix':
            return f"{self.common_label}{own}"
        return f"{own}{self.common_label}"

    @staticmethod
    def _member_own_name(member):
        if isinstance(member, Group):
            return member.common_label
        if isinstance(member, AnnotationItem):
            return member.text or SHAPE_LABELS.get(member.kind, member.kind)
        return member.name  # Series.name -> item.name(), never mutated here

    # -- HSL base color, preserving per-member variation ------------------
    def set_base_color(self, new_color):
        """Set/replace the group's base tone. Every member's CURRENT color
        is first re-expressed as an (hue, lightness) offset from the OLD
        base_color (or reset to a zero offset, the first time this group
        ever gets a base_color); that offset is then re-applied onto
        `new_color`. See the module docstring for why this makes a
        hand-recolored member "stick" to its own last color, not an
        earlier preset offset."""
        new_color = tuple(int(c) for c in new_color[:3])
        if self.base_color is not None:
            old_h, old_l, _old_s = _rgb_to_hls(self.base_color)
            for m in self.members:
                h, l, _s = _rgb_to_hls(_member_color(m))
                self._offsets[id(m)] = (h - old_h, l - old_l)
        else:
            for m in self.members:
                self._offsets.setdefault(id(m), (0.0, 0.0))
        self.base_color = new_color
        self._apply_base()

    def _apply_base(self):
        h, l, s = _rgb_to_hls(self.base_color)
        for m in self.members:
            dh, dl = self._offsets.get(id(m), (0.0, 0.0))
            _apply_member_color(m, _hls_to_rgb(h + dh, l + dl, s))

    # -- serialization (clipboard / subplot copy-paste) -------------------
    def to_dict(self):
        """common_label/label_position/base_color plus one ref per member:
        a ('series', index-in-_series_on)/('annotation', index-in-
        _annotations_on) pair for a leaf, or a nested dict for a Group
        member -- resolved back to live objects by from_dict's
        members_by_ref. Indices, not identities, because a pasted subplot
        rebuilds its series/annotations as new objects in the same order
        they were serialized (see clip_ops.py's copy_subplot/paste_subplot)."""
        return {
            'common_label': self.common_label,
            'label_position': self.label_position,
            'base_color': self.base_color,
            'members': [self._member_ref(m) for m in self.members],
        }

    def _member_ref(self, member):
        dh, dl = self._offsets.get(id(member), (0.0, 0.0))
        if isinstance(member, Group):
            return {'ref': 'group', 'group': member.to_dict(), 'offset': (dh, dl)}
        if isinstance(member, AnnotationItem):
            lst = _annotation_list_for(self.figure, self._subplot)
            return {'ref': 'annotation', 'index': lst.index(member), 'offset': (dh, dl)}
        lst = self._subplot.listDataItems() if self._subplot is not None else []
        return {'ref': 'series', 'index': lst.index(member.item), 'offset': (dh, dl)}

    @classmethod
    def from_dict(cls, figure, parent_plot, data, members_by_ref):
        """Inverse of to_dict(). `members_by_ref(ref_kind, index)` resolves
        a leaf ref to the live, just-rebuilt Series/AnnotationItem --
        `default_members_by_ref` below is a ready-made one. Recurses for
        nested 'group' refs."""
        members = []
        for ref in data['members']:
            if ref['ref'] == 'group':
                m = cls.from_dict(figure, parent_plot, ref['group'], members_by_ref)
            else:
                m = members_by_ref(ref['ref'], ref['index'])
            members.append(m)
        group = cls(members, common_label=data['common_label'], label_position=data['label_position'])
        for ref, m in zip(data['members'], members):
            group._offsets[id(m)] = tuple(ref['offset'])
        base_color = data.get('base_color')
        if base_color is not None:
            group.base_color = tuple(base_color)
            group._apply_base()
        return group


def _annotation_list_for(figure, subplot):
    """Annotations belonging to `subplot`, in the same order to_dict/paste
    already use (_annotations_on) -- or every free-floating ('figure'-
    anchored) annotation in the figure, in creation order, when subplot is
    None (a group of nothing but free-floating annotations)."""
    if subplot is None:
        return [a for a in figure.annotations if a.anchor == 'figure']
    return figure._annotations_on(subplot)


def default_members_by_ref(figure, parent_plot):
    """A ready-made members_by_ref resolver for Group.from_dict: looks up
    a ('series', index)/('annotation', index) ref against parent_plot's
    CURRENT series/annotations. Callers (clip_ops.py, eventually) must
    call this only after parent_plot's series/annotations are rebuilt, so
    the indices line up with what to_dict recorded."""
    series_list = figure._series_on(parent_plot)
    ann_list = _annotation_list_for(figure, parent_plot)

    def resolve(ref_kind, index):
        if ref_kind == 'series':
            return series_list[index]
        if ref_kind == 'annotation':
            return ann_list[index]
        raise ValueError(f"unknown group member ref kind {ref_kind!r}")

    return resolve


def groups_from_dict(figure, parent_plot, groups_list):
    """Rebuild every top-level Group for parent_plot from a subplot dict's
    'groups' list (a list of Group.to_dict() outputs). THE HOOK clip_ops.py
    needs (see this package's report): call this right after rebuilding
    parent_plot's series and annotations, as
        groups_from_dict(self, new_plot, data.get('groups', []))
    inside paste_subplot's build(), and append its result to
    self.groups so copy/paste of a subplot carries its group hierarchy."""
    resolver = default_members_by_ref(figure, parent_plot)
    return [Group.from_dict(figure, parent_plot, d, resolver) for d in groups_list]


# -- color presets: initial per-member HSL offsets, then applied once ------
def raw_filtered_preset(members, base_color=None, light_delta=0.16):
    """Same hue, alternating light/dark lightness (member 0, 2, 4... get
    +light_delta, member 1, 3, 5... get -light_delta) -- e.g. a "raw"/
    "filtered" pair of curves that should read as the same signal, one
    lighter. base_color defaults to the members' current average color."""
    group = Group(list(members))
    if base_color is None:
        base_color = _average_rgb(group.members)
    for i, m in enumerate(group.members):
        dl = light_delta if i % 2 == 0 else -light_delta
        group._offsets[id(m)] = (0.0, dl)
    group.base_color = tuple(int(c) for c in base_color[:3])
    group._apply_base()
    return group


def sensor_family_preset(members, base_color=None, hue_spread=0.05):
    """Small, evenly spread hue offsets, same lightness -- e.g. a family of
    sensors that should read as related but distinguishable. base_color
    defaults to the members' current average color."""
    group = Group(list(members))
    if base_color is None:
        base_color = _average_rgb(group.members)
    n = len(group.members)
    for i, m in enumerate(group.members):
        frac = 0.0 if n <= 1 else (i - (n - 1) / 2.0) / (n - 1)
        group._offsets[id(m)] = (frac * hue_spread, 0.0)
    group.base_color = tuple(int(c) for c in base_color[:3])
    group._apply_base()
    return group


GROUP_COLOR_PRESETS = {
    'raw_filtered': raw_filtered_preset,
    'sensor_family': sensor_family_preset,
}


def _group_list(figure):
    """`figure`'s list of top-level Group objects, created on first use.
    A plain function, not a bound method -- so it works via a direct
    `_group_list(fig)` call even before GroupsMixin is a real base class
    of LaFigure (see GroupsMixin's own docstring): `self.groups` inside a
    GroupsMixin method would resolve through `type(self).__mro__`, i.e.
    plain `LaFigure`'s MRO, which doesn't include GroupsMixin until the
    reported figure.py diff lands, and so would raise AttributeError."""
    if not hasattr(figure, '_groups'):
        figure._groups = []
    return figure._groups


def _ungroup_one(figure, group):
    """Remove `group` from `figure`'s top-level group list, undoably. A
    plain function for the same reason `_group_list` is (see its
    docstring) -- used by GroupsMixin.ungroup_selection, inside an
    undo_group() block so N dissolved groups still cost one undo entry."""
    group_list = _group_list(figure)

    def undo_fn():
        if group not in group_list:
            group_list.append(group)

    def redo_fn():
        if group in group_list:
            group_list.remove(group)

    redo_fn()
    figure._push_history(undo_fn, redo_fn)


class GroupsMixin:
    """Ctrl+G / Ctrl+Shift+G. K1 doesn't own figure.py (PLAN.md's
    ownership table), so this mixin isn't yet in LaFigure's class
    statement -- see this package's report for the one-line diff. Until
    that lands, drive it as GroupsMixin.group_selection(fig), not
    fig.group_selection()."""

    @property
    def groups(self):
        """Every top-level Group in this figure (a nested Group is only
        reachable through its parent's .members, not listed here too).
        Lazily created so this mixin needs no entry in LaFigure.__init__."""
        return _group_list(self)

    def group_selection(self):
        """Ctrl+G: group the current curve + annotation multi-select
        (selection_ui.py's selected_curves/selected_annotations) into one
        Group. No-op (returns None) with fewer than two items selected, or
        if they don't all share one subplot (CLAUDE.md: 'a group never
        spans subplots') -- Group's own ValueError is swallowed here so a
        stray Ctrl+G on a mixed selection just does nothing, silently."""
        members = [s for s in (self._series_of(c) for c in self.selected_curves) if s is not None]
        members.extend(self.selected_annotations)
        if len(members) < 2:
            return None
        try:
            group = Group(members)
        except ValueError:
            return None
        group_list = _group_list(self)
        group_list.append(group)

        def undo_fn():
            if group in group_list:
                group_list.remove(group)

        def redo_fn():
            if group not in group_list:
                group_list.append(group)

        self._push_history(undo_fn, redo_fn)
        return group

    def ungroup_selection(self):
        """Ctrl+Shift+G: dissolve every top-level group that has at least
        one currently-selected curve/annotation among its (possibly
        nested) leaf members, all as one undo entry."""
        hit = []
        for group in _group_list(self):
            leaves = group.leaf_members
            curve_hit = any(isinstance(m, Series) and m.item in self.selected_curves for m in leaves)
            ann_hit = any(isinstance(m, AnnotationItem) and m in self.selected_annotations for m in leaves)
            if curve_hit or ann_hit:
                hit.append(group)
        if not hit:
            return
        with self.undo_group():
            for group in hit:
                _ungroup_one(self, group)
