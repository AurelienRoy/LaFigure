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

"""Pure fractional-grid math for the free layout (layout.py) -- no Qt.

A figure's grid is two lists of line positions, as figure fractions:
`lines[0] == 0`, `lines[-1] == 1`, increasing; n tracks (columns or rows)
have n + 1 lines. A subplot's box is (left, top, right, bottom) in *grid
coordinates*: left=1.5 is halfway between column lines 1 and 2. Grid
coordinates map to figure fractions piecewise-linearly through the lines,
so moving one line rescales exactly the edges lying between its two
neighbors -- insets included -- and nothing else. Integer coordinates are
cells and spans; anything else is a free size or an inset.
"""
import math

EPS = 1e-9


def to_frac(lines, g):
    """Grid coordinate -> figure fraction (clamped to the grid)."""
    n = len(lines) - 1
    g = min(max(g, 0.0), float(n))
    k = min(int(math.floor(g)), n - 1)
    return lines[k] + (g - k) * (lines[k + 1] - lines[k])


def from_frac(lines, f):
    """Figure fraction -> grid coordinate (clamped to the grid)."""
    n = len(lines) - 1
    if f <= lines[0]:
        return 0.0
    for k in range(n):
        if f <= lines[k + 1]:
            span = lines[k + 1] - lines[k]
            return k + ((f - lines[k]) / span if span > 0 else 0.0)
    return float(n)


def equal_lines(n):
    return [k / n for k in range(n + 1)]


def _sizes(lines):
    return [lines[k + 1] - lines[k] for k in range(len(lines) - 1)]


def _from_sizes(sizes):
    total = sum(sizes) or 1.0
    lines = [0.0]
    for s in sizes:
        lines.append(lines[-1] + s / total)
    lines[-1] = 1.0
    return lines


def insert_track(lines, index):
    """Lines after inserting a new track at line `index` (0..n; n appends).
    The new track gets 1/(n+1) of the figure; the others keep their
    proportions, so equal tracks stay equal and delete_track undoes it."""
    n = len(lines) - 1
    sizes = [s * n / (n + 1) for s in _sizes(lines)]
    sizes.insert(index, 1.0 / (n + 1))
    return _from_sizes(sizes)


def delete_track(lines, index):
    """Lines after removing track `index` (between lines index and
    index + 1); the others grow proportionally to fill the figure."""
    sizes = _sizes(lines)
    del sizes[index]
    return _from_sizes(sizes)


def shift_span_for_insert(lo, hi, index):
    """A box's (lo, hi) edges on one axis after a track is inserted at line
    `index`: a span starting at or after the line moves by one, a span
    crossing it grows by one, a span ending at or before it stays. Safe
    for any grid, unlike shifting integer cells (CLAUDE.md bug #1): no
    edge can land inside another box that it wasn't already inside."""
    if lo >= index - EPS:
        return lo + 1, hi + 1
    if hi > index + EPS:
        return lo, hi + 1
    return lo, hi


def shift_span_for_delete(lo, hi, index):
    """Inverse of shift_span_for_insert: track `index` is removed. Edges
    beyond it move back by one; an edge inside it collapses onto it."""
    def shift(e):
        if e >= index + 1 - EPS:
            return e - 1
        if e > index:
            return float(index)
        return e
    return shift(lo), shift(hi)


def spans_overlap(a0, a1, b0, b1):
    """Open intervals (a0, a1) and (b0, b1) share a positive length."""
    return a0 < b1 - EPS and b0 < a1 - EPS


def boxes_overlap(a, b):
    return spans_overlap(a[0], a[2], b[0], b[2]) and spans_overlap(a[1], a[3], b[1], b[3])


def track_is_empty(boxes, axis, index):
    """No box covers any part of track `index` ('col' or 'row')."""
    lo, hi = (0, 2) if axis == 'col' else (1, 3)
    return not any(spans_overlap(b[lo], b[hi], index, index + 1) for b in boxes)


def first_empty_cell(boxes, n_rows, n_cols):
    """(row, col) of the first cell in reading order that no box covers
    any part of, or None."""
    for r in range(n_rows):
        for c in range(n_cols):
            cell = (c, r, c + 1, r + 1)
            if not any(boxes_overlap(cell, b) for b in boxes):
                return r, c
    return None


def gutter_segments(boxes, axis, index, extent):
    """Parts of interior line `index` that no box crosses, as (g0, g1)
    intervals along the other axis, which runs from 0 to `extent`. A
    'col' line is vertical: its segments run along rows. These are the
    draggable gutters -- a line hidden under a spanning subplot isn't."""
    lo, hi, o_lo, o_hi = (0, 2, 1, 3) if axis == 'col' else (1, 3, 0, 2)
    blocked = sorted((b[o_lo], b[o_hi]) for b in boxes
                     if b[lo] < index - EPS and b[hi] > index + EPS)
    segments = []
    start = 0.0
    for b0, b1 in blocked:
        if b0 > start + EPS:
            segments.append((start, b0))
        start = max(start, b1)
    if extent > start + EPS:
        segments.append((start, float(extent)))
    return segments
