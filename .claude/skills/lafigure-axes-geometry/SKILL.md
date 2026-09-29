---
name: lafigure-axes-geometry
description: How to draw angle- or direction-dependent geometry (arrowheads, oriented outlines, rotation, offsets with a fixed screen direction) on an 'axes'-anchored annotation or any other item living inside a subplot's ViewBox, without it warping when the subplot's X and Y data-per-pixel scale isn't 1:1. Use before writing or reviewing any paint()/geometry code for a shape drawn inside a PlotItem's data coordinate space -- annotations, handles, guides, a future series-kind's own decoration. Also load when debugging a shape that "looks skewed", "looks squished", or "isn't the same angle it should be" on a subplot whose X and Y ranges have very different spans.
---

# No zoom-ratio warping for axes-anchored geometry

## The principle

An `'axes'`-anchored item (an `AnnotationItem`, a handle, anything added via
`plot_item.addItem(...)` or living inside a `ViewBox`'s child group) has
its own **local coordinate space in DATA units**, mapped to screen pixels
by the ViewBox's own transform. That transform is only ever
**shape-preserving** (angles, aspect ratios, "looks like a square" /
"points the same way it should") when the subplot's X and Y
data-per-pixel ratio is 1:1 -- which is the exception, not the rule. Most
real plots have wildly different X and Y spans (e.g. time in seconds on
X, a voltage in millivolts on Y).

**Any geometry with an inherent angle or direction, computed and drawn
purely in local (data) space, will look wrong on screen the moment that
ratio isn't 1:1** -- an arrowhead becomes a lopsided triangle, a "square"
selection box becomes a rectangle, a rotation the code thinks is 45°
renders as some other angle entirely.

**This does NOT apply** to a shape whose own definition IS a data-space
extent with no inherent angle -- a plain axis-aligned `rect`/`ellipse`
between two data corners is *correctly* axis-aligned in data space; that
is its real, intended shape, not a bug. The principle is specifically
about angles/directions that are meant to look a certain way *on screen*
(pointing at a target, hugging a line, appearing square/circular to the
viewer), not about data-space extents that are supposed to reflect the
data.

## The fix: compute in scene space, map back

1. Map every point the geometry depends on into **scene (screen-pixel)
   coordinates** via `self.mapToScene(local_point)`.
2. Do all the angle/trig/offset math there, in scene space, where "45
   degrees" and "perpendicular" and "this many pixels" mean what they
   look like on screen.
3. Map the *resulting* points back to local coordinates via
   `self.mapFromScene(scene_point)` before handing them to `painter`
   (which always draws in the item's local space).

Keep any point that must land *exactly* somewhere (e.g. an arrow's tip,
which must stay attached to the line's actual endpoint) in local
coordinates throughout, with no round trip -- only the points whose
*direction* matters need the scene-space detour.

### Worked examples (`lafigure/annotations.py`)

- `AnnotationItem._draw_arrowhead`: the two back corners of an arrowhead
  triangle are computed from an angle measured in scene space, then
  mapped back; the tip itself is never round-tripped, so it stays exactly
  on the line.
- `AnnotationItem._selection_outline_polygon`: the oriented dashed box
  around a `line`/`arrow`/`doublearrow`/`textarrow` annotation's segment
  is built as four corners in scene space (unit vector along the segment,
  perpendicular for width) and mapped back — not a local-space
  `painter.rotate()`, which was the original (buggy) approach: a rotation
  applied in local space, even at the exact angle the segment itself
  looks like on screen, does not stay perpendicular/parallel to that
  segment once mapped through a non-uniform local→scene transform.

## A known, NOT-yet-fixed gap this principle also covers

`AnnotationItem.setRotation()` — used by `rect`/`ellipse`/`text`
annotations' rotate handle — applies the rotation to the item's own
local→parent transform, which happens **before** the ViewBox's
data→scene transform is applied on top of it. So a rotated rect/ellipse/
text on an `'axes'`-anchored subplot with a non-1:1 data scale likely
warps too — same root cause as the arrowhead/outline bugs above, just
affecting the shape's own outline instead of a decoration around it.
Confirmed as a real, deeper issue while fixing the arrowhead/outline
bugs (2026-09-29); **not fixed** — it would mean redrawing the shape's
own geometry in scene space, not just a decorative overlay, a materially
bigger change. Check `CLAUDE.md`'s feature list for current status
before assuming it's still open.

## Checklist for new code

Before drawing (or reviewing a PR that draws) anything angle- or
direction-dependent on an `'axes'`-anchored item:

- [ ] Does this geometry have an inherent angle, direction, or "should
      look square/circular on screen" property?
- [ ] If yes: is it computed via scene-space round-trip
      (`mapToScene`/`mapFromScene`), not local-space trig?
- [ ] Is any point that must land exactly somewhere (an attachment point,
      an endpoint) kept in local coordinates with no round-trip, so
      floating-point drift from the mapping doesn't move it?
- [ ] Did you check the result on a subplot with a deliberately
      non-square data scale (e.g. `xRange=(0, 1000), yRange=(0, 1)`), not
      just the default demo figure, which may happen to be close to
      1:1 and hide the bug? `tests/test_annotation_ops.py`'s
      `test_oriented_outline_is_not_warped_by_a_non_square_data_scale`
      is the pattern to copy: assert adjacent edges of the drawn shape
      are perpendicular in *scene* space, not just check local-space
      numbers.
