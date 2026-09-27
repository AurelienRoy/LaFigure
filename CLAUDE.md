# CLAUDE.md — LaFigure

This file is for a **future Claude session**, not this codebase's users. It
exists because a later session is more likely to be asked to build something
*similar* (a MATLAB-Figure-like editing UI, a PyQtGraph app, a grid-of-panels
editor with resize/move/undo) than to extend this exact file. Read this for
the principles and hard-won lessons; do not assume the code itself is a good
starting point to copy from — see "Should you reuse the code?" below.

## What this is

A PyQtGraph (Qt + OpenGL) library/app imitating MATLAB's interactive Figure
window: multiple subplots in a grid, click to select, drag borders/corners
to resize, drag a center handle to move/swap, curve selection, undo/redo,
copy/paste curves and whole subplots (including across separate figure
windows), FFT-to-new-subplot, linked brushing, editable title/axis/legend
text, plus a Figure Manager window for creating/tracking multiple figures.

**As of the library-refactor pass**, this is no longer a single file. It's
an importable package:

```
LaFigure/
  lafigure/              # the package -- `import lafigure`
    __init__.py            # public API: LaFigure, FigureManager, ...
    __main__.py             # `python3 -m lafigure`
    app.py                   # main(): opens a FigureManager + a demo LaFigure
    figure.py                 # LaFigure -- the core class (was the whole file)
    manager.py                 # FigureManager: tree of open figures/subplots,
                                # "New Figure" button (creates an empty figure)
    registry.py                 # FigureRegistry: process-wide list of open
                                 # LaFigure windows, with Qt signals
                                 # FigureManager listens to (figureOpened/
                                 # figureClosed/subplotsChanged)
    clipboard.py                  # Clipboard: process-wide singleton (not a
                                   # LaFigure attribute) so copy/paste of a
                                   # curve or a whole subplot works ACROSS
                                   # separate figure windows, not just within one
    selection.py                    # SelectionModel, LinkedScatter
    handles.py                       # DragHandle base + ResizeHandle, MoveHandle,
                                      # AnnotationHandle (child-parented resize/
                                      # rotate/endpoint grip for one AnnotationItem)
    editable_text.py                  # click-to-edit title/axis-label/legend text
    annotations.py                     # AnnotationItem (all 8 shape kinds) + the
                                        # figure/border/axes filiation model
  icons/
  smoke_test.py           # imports the package: `import lafigure as m`
```

Run it with `python3 -m lafigure` (not `python3 lafigure.py`
— that file no longer exists, replaced by the package above).

**Why the split happened before annotations**: annotations needed their
own module and touch both LaFigure and the clipboard (an annotation's
serialization is reused by subplot copy/paste); doing the split first
meant that code landed in the right module from the start instead of
needing a second refactor. Annotations have since been implemented — see
the feature list and "Annotations" design-debt section below.

`HANDOFF.md` no longer exists — it was the previous, timestamped backlog
doc from before the library refactor, superseded by this file once
annotations (its "next planned piece") were implemented. **This file's
feature list below is the source of truth.**

## Full feature list (the durable backlog)

Everything the user has asked for, across the whole project, with status.
Treat unchecked items as live backlog. Don't assume "done" without reading
the actual code — this list is a summary, not a substitute for checking.

- [x] Plot millions of points fluently
- [x] Zoom/pan (free-form, plus a dedicated Zoom Rect mode: drag a
      rectangle to zoom into it)
- [x] Add a new curve to an existing subplot
- [x] Delete a curve (right-click menu, or Del key when it's the selected curve)
- [x] Copy/paste a curve between subplots. Plain Ctrl+C/Ctrl+V
      (`LaFigure.copy_selection`/`paste_selection`) is a *smart*
      dispatch: it copies/pastes curve(s) if any curve is selected, else
      falls back to the active subplot's first curve, else — if a subplot
      but no curve is selected — copies/pastes the **subplot** instead
      (`Clipboard.last_copied` records which kind a plain Ctrl+V should
      mirror). Shift+click selects more than one curve (see multi-select
      bullet below); Copy then copies all of them, and Paste pastes all of
      them onto the active subplot. Uses a process-wide `Clipboard`
      singleton (`clipboard.py`; `.curve`/`.subplot` are lists, one entry
      per copied item), so it also works across separate figure windows.
- [x] Copy/paste a **whole subplot between separate figures/windows**
      (Ctrl+Shift+C/Ctrl+Shift+V always target the subplot explicitly;
      plain Ctrl+C/Ctrl+V do too when a subplot but no curve is selected —
      see above; or right-click → Copy/Paste Subplot, including a
      right-click on **empty space outside every subplot**, which opens a
      minimal menu with just Paste Subplot — see `_show_empty_space_menu`)
      — `LaFigure.copy_subplot`/`paste_subplot`, going through the same
      shared `Clipboard`. Shift+click selects more than one subplot; both
      copy and paste act on the whole set (paste inserts one new row per
      copied subplot, stacked at the bottom). Carries title/axis-labels/
      curves/annotations; goes through undo/redo like every other
      structural change.
- [x] Multiple figure windows + a **Figure Manager** window
      (`manager.py`): a "New Figure" button creates a truly empty
      `LaFigure(empty=True)` (no subplots, and its "keep at least one
      subplot" floor is relaxed to zero — see `delete_subplot`), plus a
      tree listing every open figure and its subplots, kept in sync via
      `FigureRegistry` signals (`registry.py`). Double-clicking a tree row
      raises/focuses that figure window. This is what makes the
      whole-subplot-copy-paste item above actually testable: without a
      second window there's nothing to paste into.
- [x] Add a new, empty subplot via a toolbar button (always a new row)
- [x] Delete a subplot (right-click, or Del key when no curve is selected) —
      removes only that subplot's own cell, never a sibling's
- [x] Resize a subplot by dragging its border (pure horizontal/vertical) or
      corner (both at once), with a toolbar toggle button, **"Grid
      Layout"**, between two behaviors. Checked (default) = grid/reflow;
      unchecked = overlap — inverted from the underlying
      `self.overlap_resize`/`toggle_overlap_resize(checked)`, which still
      means `checked = overlap` internally exactly as before; only the
      toolbar action's own connection inverts it
      (`lambda checked: self.toggle_overlap_resize(not checked)`), so
      `toggle_overlap_resize`'s own call sites/semantics (incl. in
      `smoke_test.py`) didn't need to change:
      - **Reflow** (Grid Layout checked, default): the grid resizes live as
        you drag; neighbors shrink/grow to fit, never overlapping.
      - **Overlap** (Grid Layout unchecked): the dragged subplot detaches
        and visually overlaps its neighbors, which never change size,
        until Grid Layout is checked again (which then reflows everything
        back into the grid).
- [x] Move a subplot / swap it with another: in Select mode, drag its
      center handle onto another subplot to swap their grid positions
- [ ] Change the z-order of curves (bring to front/back, reorder legend) —
      not implemented
- [ ] Manipulate individual numeric points (drag a sample to edit its
      value) — not implemented
- [x] Add/remove a legend (toolbar toggle, or right-click menu)
- [x] Edit a legend entry's name by clicking (double-click the legend label,
      or right-click → Rename Curve)
- [x] Edit a subplot's title by clicking (double-click it)
- [x] Edit a subplot's x/y-axis label by clicking (double-click it), *and*
      via dedicated "X Label"/"Y Label" toolbar buttons (same effect,
      discoverable without knowing the double-click gesture — useful right
      after adding a new, unlabeled subplot)
- [x] Toolbar with custom buttons, using the MATLAB-style icons in `icons/`
      where one matches (pointer/hand/zoom/legend/linked-plots/data-brush/
      text-box); a few actions without a matching icon in that set keep a
      generic fallback (Reset View, Add Subplot, Delete, Undo, Redo,
      Grid Layout)
- [x] "Remove the average" button (subtracts the mean from every curve on
      the active subplot)
- [x] Compute FFT and plot on a new subplot beneath the current one, acting
      on the **selected curve** if one is selected (falls back to the
      subplot's first curve otherwise — no longer *always* first-curve-only)
- [x] Link subplots by X axis (toolbar toggle). Every subplot links to
      `plots[0]`, re-applied on every add/remove (`_apply_link_x`), so a
      subplot added/pasted/FFT'd while Link X is on is linked too, and
      deleting `plots[0]` re-links the rest to the new `plots[0]`.
- [x] **Figure-wide toggles reach subplots created later.** Mode, Brush and
      Link X are all adopted in `add_subplot`, the only `addPlot()` call site
      (guarded by `test_add_subplot_is_the_only_subplot_construction_site`
      in `smoke_test.py`). A ViewBox's mouse-enabled state has exactly one
      writer, `_apply_mouse_enabled`: pan is off if Select mode **or**
      brushing is on. Before 2026-09-27, Brush and Link X only reached
      existing subplots, and turning Brush off re-enabled pan in Select mode.
- [x] Data brushing, two layers:
      - **Linked** (`LinkedScatter`, `selection.py`): rectangular drag-select
        on a scatter subplot, broadcast through a shared `SelectionModel` to
        highlight the same point ids on every other subplot that shares
        them — **still limited to the two hardcoded demo scatter subplots**
        (`self.scatter1`/`self.scatter2`), not generalized to any new
        scatter subplot added later.
      - **Generic** (`RectBrush`, `selection.py`): the same rectangular
        drag-select, but wired onto *every* subplot's own ordinary
        `PlotDataItem` curves by `add_subplot` (so it's automatic for any
        subplot, including ones pasted/added/FFT'd in later), independent
        of any shared selection model. `LaFigure._brushers` maps
        `plot_item -> RectBrush`; a `LinkedScatter` plot has its default
        one removed at construction (see `LinkedScatter.__init__`) so the
        two layers never stack on the same `ViewBox.mouseDragEvent`.

        **Brushing is a figure-wide concept, not per-subplot**: a plain
        (non-Shift) brush drag on any subplot unbrushes every other
        subplot's selection in the *same figure* first (including the
        linked-scatter pair's shared `SelectionModel`), then selects just
        what this drag caught — `LaFigure._on_rect_brush_finished` and
        `_clear_all_brush_selection` are the coordinators; `LinkedScatter`
        calls the latter directly since its own brushing is a separate code
        path. **Shift-held drag adds** to whatever's already brushed
        anywhere in the figure instead of clearing it (`RectBrush.
        merge_selection`; modifier is read once, at drag-release, via
        `ev.modifiers()` — mirroring how pyqtgraph's own `ViewBox` reads
        Ctrl for its box-zoom). The four right-click actions below act on
        the pooled figure-wide selection (`LaFigure._figure_brush_items`),
        not just the subplot you right-clicked.

        Selecting points enables four right-click actions on that
        selection: **Delete Selected Points**, **Transform Selected
        Points...** (an arbitrary `eval`'d numpy expression in `x`/`y`,
        restricted `__builtins__`), **Selection Stats...** (mean/std, per
        curve and pooled), and **Fit Selected Points** (linear or degree-N
        polynomial, via `np.polyfit` on the pooled selection — overlays a
        new fit curve, on whichever subplot's menu was used, + a
        `pg.TextItem` with the equation/R²). All four go through undo/redo
        like every other data-mutating action. Fit's overlay curve is a
        fresh `PlotDataItem`, so it can itself be brushed/deleted/fit again
        like any other curve.
- [x] Right-click context menu, extending pyqtgraph's default one (View
      All / Mouse Mode / Plot Options) with: Paste Curve, Copy/Paste
      Subplot, Toggle Legend, Remove Average, FFT → Subplot Below, the
      four brushed-selection actions above, Delete Curve submenu, Rename
      Curve submenu. Right-clicking also selects that subplot. Right-
      clicking **empty space outside every subplot** instead opens a
      minimal menu with just Paste Subplot (`_show_empty_space_menu`,
      dispatched from `_on_scene_clicked` since there's no `ViewBox` there
      for pyqtgraph's own per-subplot menu to attach to).
- [x] Clicking a subplot makes it the visually active one (red border) —
      this used to be broken (see bug #0 below) and is now fixed
- [x] Clicking a curve selects/highlights it (thicker pen), and that
      selection — not just "the first curve" — is what FFT and Remove
      Average act on (those two stay single-target deliberately, see below)
- [x] **Multi-select via Shift+click** (`self.selected_plots`/
      `self.selected_curves`, a superset of `active_plot`/`active_curve`):
      Shift+clicking a subplot or curve adds it to the selection (a union,
      never a toggle-off) instead of replacing it; visually, every
      selected subplot gets the same red border. Only some actions read
      the multi-select — **Copy/Paste (curve and subplot), Delete, the
      X/Y-axis-label toolbar buttons, Toggle Legend, and Rename Curve**
      all act on the whole set. FFT, Remove Average, and everything else
      deliberately keep targeting only the single most-recently-clicked
      `active_plot`/`active_curve`, unaffected by any wider selection —
      this split was an explicit product decision, not an oversight; don't
      "complete" it by wiring more actions to the multi-select without
      checking first. Deleting/removing an item also drops it from these
      lists (`_forget_curve_selection`, and the plot-side cleanup in
      `_forget_removed_plot`) so a stale reference never lingers in them.
- [x] Deselection: double-clicking a subplot (or a curve, or empty space),
      or a single click that lands outside every subplot, clears the
      selected curve/subplot *and* the multi-select
- [x] Del key: deletes every selected curve if any are selected, else
      every selected subplot, each through its own existing single-item
      `delete_curve`/`delete_subplot` call and its own undo entry — a
      multi-delete of N items takes N presses of Undo to fully revert,
      since there's no batched-undo-entry concept anywhere else in this
      codebase either. Deliberate, not an oversight; don't add one without
      checking first, since it'd be the first of its kind here.
- [x] Ctrl+Z / Ctrl+Y: undo/redo for the last N actions (bounded history,
      `max_history = 20`), covering delete/rename/paste a curve, remove
      average, add/delete a subplot, FFT insert, and axis-label edits. The
      Undo/Redo toolbar buttons are enabled/disabled to match whether
      their respective stack is non-empty (`_update_undo_redo_actions`,
      called from `_push_history`/`undo`/`redo`) — both start disabled.
      **Not** covered by undo (deliberately — these are view/UI toggles,
      not data edits): legend on/off, Link X, Brush mode, Pan/Select/Zoom
      Rect mode, Grid Layout toggle, view reset, subplot move/swap
- [x] Three interaction modes, exclusive toolbar toggle (Select is default):
      - **Select** (mouse-pointer icon): click a subplot to select it;
        drag its border/corner handles to resize, its center handle to
        move/swap. Dragging inside a subplot's data area does nothing in
        this mode (freed up for the handles) — normal data pan/zoom is
        disabled while Select is active.
      - **Hand**: plain pan/zoom on whichever subplot is under the cursor.
        No selection border/handles ever show, though the active subplot
        is still tracked silently so toolbar actions keep a sensible
        target. The mouse cursor turns into an open-hand cursor over every
        subplot's data area while this mode is active
        (`LaFigure._cursor_for_mode`, applied by both
        `set_interaction_mode` and `add_subplot` so a subplot
        added/pasted while already in Hand mode gets it immediately too).
      - **Zoom Rect**: same as Hand but drag draws a zoom-to-rectangle.
- [x] **Annotations** (ellipse, rectangle, text, text+arrow, arrow, double
      arrow, line, data cursor) with a filiation (parent/child) model:
      free-floating in the figure (`anchor='figure'`), tied to a subplot's
      border/chrome (`anchor='border'`, scene-pixel offset from the
      subplot's top-left), or tied to a subplot's data axes
      (`anchor='axes'`, added into the `PlotItem`'s `ViewBox` so it pans/
      zooms with the plot for free) — see `annotations.py`. Filiation shown
      as a colored dashed outline in Select mode when an annotation is
      selected (color = `filiation_color(parent_plot, figure.plots)`, a
      stable per-subplot color); reparenting via right-click an annotation
      → "Link to..." → click its new parent (a subplot, or empty space for
      free-floating) — `LaFigure._start_relink`/`_handle_relink_click`/
      `_reparent_annotation`. Move (drag the shape body), resize (single
      end-point handle — the opposite corner for rect/ellipse, the tip for
      line/arrow/textarrow/cursor's label), and rotate (a second handle
      above the shape's center) are all native `QGraphicsItem` overrides,
      each pushing one undo/redo entry. Right-click properties menu (line
      color/width, and a fill color for rect/ellipse). `'border'`- and
      `'axes'`-anchored annotations are parented to the **subplot**
      (`PlotItem`), not the figure, so they travel along with
      `copy_subplot`/`paste_subplot` above (`'figure'`-anchored ones don't
      — they aren't any subplot's). Placed via one dropdown "Annotate"
      toolbar button listing all 8 shapes: point kinds (text, data cursor)
      place on a single click; every extent-having shape (rect, ellipse,
      line, arrow, double arrow, text+arrow) places via one MATLAB-style
      press-drag-release gesture, intercepted with a scene `eventFilter`
      because pyqtgraph's `sigMouseClicked` never fires for a real
      click-and-drag (see `eventFilter`'s docstring in `figure.py`). A
      press+release with negligible movement falls back to the shape's
      default extent, so a plain click still places something reasonable.
      **Verified live** (see bug #6 below) — this is drag-based, not the
      two-click gesture an earlier, never-executed pass of this file
      described here; that description was corrected once a session could
      actually run Qt and catch the mismatch via a failing smoke-test
      assertion.

## The one thing to internalize before touching this kind of code

**PyQtGraph's `GraphicsLayoutWidget` grid is a real `QGraphicsGridLayout`.**
Layouts exist specifically to prevent overlap by construction. Every bug and
every non-trivial feature in this file traces back to either respecting that
fact or fighting it:

- Resizing one cell without disturbing others → done *for free* by setting
  row/column stretch factors and letting the layout redistribute space.
  Don't hand-roll geometry math for this.
- Making a subplot visually overlap its neighbors ("float") → **impossible**
  while the layout manages it. You must detach it from the layout first.
- "Move/swap two subplots" → same detach-and-reattach trick, then swap which
  cell each item is reinserted into.

If you're building something similar with a different library, look for the
equivalent "manages the item" vs. "manages nothing" boundary in that
library's layout system — the same class of bug will show up wherever you
cross it carelessly.

## What worked well (keep doing this)

- **Millions-of-points performance**: `setClipToView(True)` +
  `setDownsampling(auto=True, method='peak')` + `useOpenGL=True` per curve.
  Validated, didn't need revisiting.
- **Undo/redo as a generic bounded stack of `(undo_fn, redo_fn)` closures**,
  wired into every state-changing action from the start (delete curve,
  rename, remove-average, add/delete subplot, FFT insert, axis label edit).
  Retrofitting undo per-feature is much more painful than building the stack
  once and pushing to it everywhere. `max_history` truncation from the oldest
  end was trivial with this design.
- **One central click dispatcher, one mode variable.** Once the app grew a
  real Hand/Select/Zoom-Rect mode split, every click-meaning decision routed
  through a single `interaction_mode` check in one place
  (`_on_scene_clicked`, `_mark_active`) rather than being duplicated in each
  handler. Do this from the start if you know multiple modes are coming.
- **Native Qt event overrides for custom graphics items.** `QGraphicsItem`
  subclasses you write yourself (drag handles, editable text) should use
  plain `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent`/
  `mouseDoubleClickEvent` overrides. PyQtGraph's *own* "clickable" protocol
  (`item.setClickable(True)` + `sigClicked`, or overriding
  `mouseClickEvent(ev)`) is a separate, parallel convention used by
  `ViewBox`/`PlotDataItem`-like objects and dispatched by pyqtgraph's custom
  `GraphicsScene`. The two coexist in the same scene without conflict, but
  don't mix them up on your own classes — native overrides is what worked.
- **Headless testing by calling methods directly**, not simulating mouse
  drags through Qt's event system. `QT_QPA_PLATFORM=offscreen` +
  `pg.setConfigOptions(useOpenGL=False)` (test-only — never disable OpenGL
  in the shipped app) gets you a running `QApplication` and real widget
  geometry; then call `win._begin_resize(...)`, `win.delete_curve(...)`,
  etc. directly and assert on state. Simulating an actual drag through Qt's
  synthetic event queue was tried implicitly and is not reliable headless —
  don't bother.
- **A shared scene-level click event carries more than you'd think.**
  pyqtgraph's `MouseClickEvent` (delivered via `scene().sigMouseClicked`)
  exposes both `.double()` (single vs. double click) and `.isAccepted()`
  (whether some clickable item already consumed it). That combination is
  enough to implement "click elsewhere deselects" and "double-click
  deselects" cleanly from one place, without per-item bookkeeping.

## What was buggy, and the actual root cause (not just the patch)

### 1. Deleting one subplot corrupted the grid / crashed on undo
**Symptom:** deleting a single subplot in a 2-column row sometimes deleted
its sibling too, and threw `QGridLayoutEngine::addItem: ... already taken`
or a `KeyError` — sometimes not immediately, but later when undo ran.

**Root cause:** the delete/insert logic modeled "delete a subplot" as "shift
every row below it up by one" (and the inverse for insert). That's only
correct when a row is atomically single-column. The moment a row has a
surviving sibling in another column, shifting later rows walks another
plot straight into that sibling's still-occupied cell.

**Fix, and the generalizable lesson:** don't conflate two different
operations just because they both "add/remove a subplot":
  - A **plain single-cell** add/delete must never shift anything else — it
    just fills or leaves a gap in its own cell.
  - A **dedicated whole-row** insert/delete (this app's "FFT → subplot
    below", which always creates its own new single-column row) can safely
    shift whole rows, specifically *because* that row is guaranteed to be
    exclusive.

  Before writing any "shift to close/open a gap" logic in a grid, ask: *is
  this row/column truly exclusive to the one item I'm moving?* If you can't
  prove yes, don't shift — leave the cell empty and let something else
  (a resize, a re-layout pass) reclaim the space later.

### 2. A second drag on an already-detached ("floating") item crashed
**Symptom:** dragging to resize an overlapping subplot worked once; a
second drag on the same still-floating subplot raised `KeyError` from
pyqtgraph's own internal grid bookkeeping.

**Root cause:** the code computed "which cell does this item belong to" by
querying the layout's own bookkeeping (`GraphicsLayout.items[item]`). The
instant an item is detached from the layout (to float/overlap), that query
stops working — but the code kept calling it unconditionally.

**Lesson:** the moment you detach an item from a layout for manual control,
its origin/identity within that layout is gone from the layout's own
records. Capture whatever you'll need (its row/col) **at detach time**, in
your own state, and never re-query the layout for an item you know might
currently be detached — guard every such call.

### 3. A "floating" subplot became invisible (only the drag handles showed)
**Symptom:** in overlap-resize mode, the resized subplot's content
disappeared entirely; only the always-on-top drag handles remained visible.

**Root cause:** removing a `QGraphicsWidget` from a `QGraphicsGridLayout`
is not documented (in the parts of pyqtgraph reachable here) to guarantee
it stays visible, keeps its parent, or stays in the scene. The code trusted
that removal was purely a layout-membership change and didn't re-assert
those things.

**Lesson:** when you manually detach a widget from a layout, treat every
implicit invariant as suspect and restore it explicitly: scene membership
(`scene() is not None`, else `scene().addItem(...)`), `setParentItem(None)`,
`.show()`, and z-order. Don't assume "it compiled and didn't crash" means
"it renders."

### 4. A resize preview didn't match what was actually asked for
**Symptom:** "Overlap Resize" mode was implemented first as a dashed
preview rectangle overlay during the drag, with the *real* reflow applied
on release — but the user's actual request was for neighbors to **never**
resize in that mode; the subplot itself should grow and genuinely overlap,
permanently, until explicitly toggled off.

**Lesson:** a plausible-sounding "preview, then commit" implementation can
quietly reinterpret a literal request ("it should spill over and stay
overlapping") into something more familiar/generic ("show a preview, then
snap to a clean layout"). Re-read the literal wording of a UI-behavior
request before assuming a common UX pattern satisfies it.

### 5. Undo after move/swap could KeyError in `_remove_subplot` (root cause unconfirmed)
**Symptom:** Paste Subplot → drag its move handle to swap it with another
subplot → Ctrl+Z (undoing the *paste*, since move/swap itself pushes no
undo entry) → `KeyError` inside `_grid_position`
(`self.layout_widget.ci.items[plot_item][0]`), called from
`_remove_subplot`, called from the paste's `undo_fn`.

**Investigation:** traced `_swap_subplots`, `_start_floating`/
`_reattach_floating`, and `_end_move` line by line under this same
sandbox's Qt-import restriction (see item 7 below) and found nothing that
should leave the swapped plot_item out of both the grid layout's own
item map (`ci.items`) and
`self.floating`. Both reattach paths mirror the already-validated
patterns from bugs #2/#3 above. Could not reproduce or confirm the exact
mechanism without a live run.

**What was done instead of guessing further:** made the failure
survivable rather than shipping an unverified fix for an unconfirmed
cause. `_remove_subplot` now uses `_try_grid_position` (returns `None`
instead of raising) and, on `None`, logs a loud `WARNING` to stderr and
still cleans up bookkeeping instead of crashing the calling undo/redo/
delete outright; `delete_subplot`'s undo closure falls back to appending
a new row if `row is None`. `_swap_subplots` now also verifies, right
after its two `addItem` calls, that both items actually landed in
`ci.items`, and warns immediately (with which one, `a` or `b`) if not —
this fires at the moment of the real bug rather than later at an
unrelated undo call, so if it recurs, that warning plus the exact
drag/drop steps should finally pin down the mechanism.

**Lesson:** when a bug can't be reproduced in a sandbox without Qt, don't
spend unbounded effort trying to prove a fix correct by static reading
alone — instrument the suspected site with a loud, specific diagnostic
and make the failure mode survivable, then let the next real run supply
the missing evidence. This is a variant of item 7 below ("say so
explicitly," "ask for the exact traceback") applied to a case where even
the traceback wasn't enough on its own.

### 6. Overlap Resize could shift/resize an uninvolved neighbor, the instant a subplot floated
**Symptom:** entering Overlap Resize and starting to drag one subplot's
corner would immediately shift a *different*, non-selected sibling
subplot's position and size by tens of pixels — before the drag had even
moved the mouse. This directly violated the documented Overlap Resize
contract ("neighbors never resize" — see bug #4 above) and the code's own
`_start_floating` docstring claim that "every other row/col keeps exactly
its current size while it floats."

**Root cause:** `_start_floating` detaches the dragged subplot from the
`QGraphicsGridLayout` and inserts an invisible placeholder `QGraphicsWidget`
in its cell, with `setPreferredSize`/`setMinimumSize`/`setMaximumSize` all
pinned to the subplot's pre-detach size — the comment's theory was that a
fixed-size placeholder alone would pin that row/column. It doesn't:
`QGraphicsGridLayout` computes a row's height (and a column's width) from
**every** item sharing it, so a sibling occupying the same row/column with
its own, more flexible size hints (small preferred size, expanded only by
stretch-factor distribution) can still pull the row/column away from the
placeholder's fixed size once the layout redistributes — an item's own
`setMaximumSize` does not automatically cap the row/column it sits in if
sibling items in that row/column want to grow. Confirmed live by comparing
`effectiveSizeHint()` on the placeholder vs. the neighbor: the neighbor's
hints were completely unchanged, yet its actual `sceneBoundingRect()`
still moved, before any drag input at all — the distortion happened purely
from the `removeItem`/`addItem(placeholder)` sequence itself.

**Fix:** don't rely on item-level size hints to pin a row/column at all.
Use the layout's own authoritative, row/column-level API instead —
`QGraphicsGridLayout.setRowFixedHeight(row, height)` /
`setColumnFixedWidth(col, width)` — called right after the placeholder is
inserted, followed by an explicit `layout.activate()` (the placeholder's
own `addItem` already ran one `activate()` pass using only the item-level
hints, so a second explicit pass is needed to correct whatever that first
pass distorted). `_start_floating` now captures the row/column's prior
`rowMinimumHeight`/`rowMaximumHeight`/`rowPreferredHeight` (and the column
equivalents) *before* pinning them, storing that alongside `(placeholder,
row, col)` in `self.floating`; `_reattach_floating` and `_swap_subplots`
restore those exact captured values when the float ends, rather than
guessing an "unbounded" sentinel. Verified live: the neighbor's
`sceneBoundingRect()` is now byte-for-byte identical before and after
floating, during the drag, and after release.

**Lesson:** an item's own `setMinimumSize`/`setMaximumSize` inside a Qt
grid layout constrains *that item*, not the row/column it occupies — a row
or column's actual size is a joint function of every item sharing it, so
"give the placeholder a fixed size" is not the same guarantee as "fix this
row's height." When a layout offers an explicit row/column-level sizing
API (`setRowFixedHeight`, `setColumnFixedWidth`, etc.), prefer it over
leaning on a single item's hints to control shared geometry — and verify
with the neighbor's actual `sceneBoundingRect()` before and after, not
just that the code you added didn't touch `row_stretch`/`col_stretch`
(those were untouched here too — the distortion route was different from
what those variables track, which is exactly why it went unnoticed by the
stretch-factor-based assertions alone).

### Annotations: known simplifications (read before extending)
Written at the point annotations were implemented, entirely blind (no live
Qt available in that sandbox either — see item 7 below). Treat everything
here as "reasoned from the API, unverified," not "confirmed working" —
**except item 1, corrected below once a session with live Qt actually
caught the mismatch (see bug #6).**

1. ~~Placement is click-based, not drag-based.~~ **Corrected, verified
   live:** extent shapes (rect/ellipse/line/arrow/doublearrow/textarrow)
   actually place via a single MATLAB-style press-drag-release gesture,
   intercepted by a scene `eventFilter` — not two separate clicks as this
   item originally claimed. That original claim was never true of the
   shipped code; it went uncaught because nothing had ever run it (see bug
   #6 above for how a live run finally surfaced the mismatch, via
   `smoke_test.py`'s own annotation-placement assertions failing). Point
   kinds (text, cursor) genuinely are single-click, via
   `_handle_placement_click`/`_on_scene_clicked` — that half of the
   original claim was correct.
2. **A rotated shape's resize can visually jump.** `AnnotationItem`
   resets `setTransformOriginPoint()` to the shape's current center every
   time its extent changes (so the rotation pivot tracks a resized
   shape), including mid-drag. Changing the transform origin while a
   non-zero rotation is already applied can shift the shape on screen
   instead of resizing it cleanly in place. Only manifests when resizing
   an *already-rotated* annotation — not verified live; if a user reports
   a rotated shape "jumping" during resize, this is the first place to
   look.
3. **FFT-generated subplots don't carry annotations across their own
   undo/redo.** `_remove_subplot_with_shift`/`insert_subplot_below` (the
   FFT-only whole-row-shift path) purge any annotations on the removed
   subplot like every other removal path, but FFT's own undo/redo never
   snapshots/restores them the way `delete_subplot`/`paste_subplot` do.
   Low-stakes today (nothing auto-adds annotations to an FFT plot), but
   would silently drop a user's annotation if they added one to an FFT
   subplot and then undid the FFT itself.
4. **A double-click on an annotation could theoretically also trigger the
   scene's "double-click deselects everything" handler**
   (`_on_scene_clicked`'s `ev.double()` branch, which doesn't check
   `ev.isAccepted()`). This exact tension already exists for double-
   clicking a title/axis-label to edit it (`editable_text.py`) and
   evidently doesn't cause a practical problem there, so annotation text
   editing reuses the same native-`mouseDoubleClickEvent` pattern rather
   than defending against a coexistence issue that may not be real. If
   double-clicking a text annotation to rename it visibly also
   deselects the annotation afterward, this is where to fix it.
5. **A `'border'`-anchored annotation's on-screen offset from its
   subplot is a raw scene-pixel offset (`anchor_offset`)** that does not
   itself rescale if the subplot is resized — same class of simplification
   as this app's own subplot-resize code forgetting manual sizing across
   a structural grid change (see "Should you reuse the code?" below). A
   border annotation can end up looking oddly placed relative to a
   subplot that's since been resized a lot. Acceptable for a POC;
   fixing it means storing a fractional (not absolute-pixel) offset.
6. **Filiation color is purely visual (a dashed outline when selected)**,
   derived live from `plots.index(parent_plot)` — it is NOT stored on the
   annotation itself, so if subplots are reordered (there's currently no
   UI for that — see the unchecked "z-order of curves" item above, which
   is a different thing, curves not subplots) two annotations that used
   to show different colors could end up matching. Not reachable today
   since nothing reorders `self.plots`.

### 7. Every one of bugs #1-6 above was found blind or by the user running it — until one session finally had working Qt
This sandbox could not install system Qt libraries (`sudo apt-get` blocked)
or read pyqtgraph's own installed source (`Read`/`Bash` denied on
site-packages) — so every fix in this file was written from API knowledge
and static reasoning, never by actually running the GUI. Multiple bugs
(the `KeyError`s, the invisible floating subplot) were only caught because
the user pasted back real tracebacks.

**Lesson for a future session in a similarly restricted environment:** say
so explicitly and early. Don't imply confidence a change "works" beyond
"it compiles and the headless smoke-test assertions I could write pass."
Ask the user to run a small standalone smoke-test script and paste back the
*exact* traceback rather than a description — the exact traceback is what
made each of these bugs fixable in one pass instead of several guesses.

**Still true in the library-refactor/Figure-Manager pass**: `pyqtgraph` and
`PySide6` were both importable here, but `import PySide6.QtCore` itself
failed (`ImportError: libglib-2.0.so.0: cannot open shared object file`),
and `sudo apt-get install libglib2.0-0` was denied — same class of
restriction as before, just a different missing `.so`. Verification for
that pass was `python3 -m py_compile` on every new module plus a grep for
leftover references to removed/renamed things (e.g. the old
`self.clipboard_curve` instance attribute after it moved to the shared
`Clipboard`), not an actual run of `smoke_test.py`. Don't assume a future
sandbox has the missing lib just because it has more of the Qt stack than
last time — check with a plain `import PySide6.QtCore`, not just
`import pyqtgraph`, since pyqtgraph's own import can get further before
failing.

**Worse still in the annotations pass**: this sandbox's permission rules
denied `import PySide6.QtCore` outright as a policy decision (not a
missing `.so`), so *no* Python-level Qt import at all was available —
`smoke_test.py`'s annotations section was written, hand-traced line by
line for undo/redo object-identity bugs (see its own top-of-section
comment on why references go stale across undo/redo, discovered exactly
this way), and `python3 -m py_compile`'d, but genuinely never executed.
Don't trust the traced-by-hand reasoning over an actual run if a
future session *can* get Qt importable — run `smoke_test.py` first thing
and treat any assertion failure in the annotations section as more likely
a real bug than a bad assertion.

**Finally confirmed in a Windows session with working Qt** (`PyQt5` +
`pyqtgraph` both installed and importable, `QT_QPA_PLATFORM=offscreen`):
this is exactly what happened. Running `smoke_test.py` for the first time
ever surfaced four failures. Two were real bugs in the test file, not the
app — `viewbox.border is None`/`is not None` checks that can never pass
(pyqtgraph's `setBorder(None)` stores a `NoPen`-styled `QPen`, never the
Python singleton `None`) and a stale curve reference (`c1`) left dangling
by an earlier delete+undo/redo dance that recreated the curve as a new
object, exactly the staleness pattern this file's own annotations-section
comment already warned about, just for a curve instead of an annotation.
One was the annotations-placement mismatch documented in "Annotations:
known simplifications" item 1 above (fixed by correcting `smoke_test.py`
to drive the real `eventFilter` gesture instead of `_on_scene_clicked`).
And one was a genuine, previously-undetected app bug — see bug #6 above.
`smoke_test.py` now runs clean end to end (`ALL OK`). The lesson holds:
every one of these was findable ONLY by actually running the thing: the
overlap-resize bug in particular reproduced instantly and consistently,
but nothing about reading `_start_floating`'s code would have surfaced it
without comparing a neighbor's real `sceneBoundingRect()` before and after.

## Should you reuse the code?

Only if you're extending *this exact app*. If you're building something
similar from scratch, prefer re-deriving the design from the principles
above over copying this file's structure — a few things in it are
POC-grade simplifications made under the sandbox constraints above, not
necessarily the right call in a codebase you can actually test:

- Manual resizing/moving deliberately **forgets** custom sizing across any
  structural grid change (add/delete a subplot) rather than trying to
  reindex row/col stretch factors precisely. Simpler and safer than getting
  renumbering exactly right blind — but a real product likely wants better.
- Brushing is hardcoded to two named scatter subplots (`self.scatter1`/
  `self.scatter2`) rather than a general registry — a known, documented
  shortcut, not a pattern to repeat.
- `_grid_layout()` reaches into `GraphicsLayout.layout`, a private/
  undocumented pyqtgraph attribute, because it's the only way found to get
  at row/column stretch factors. It prints a runtime `WARNING` to stderr if
  that attribute is missing (version mismatch) instead of failing silently
  — keep that pattern (fail loud, not silent) if you reuse this technique,
  but look for a public API first if this pyqtgraph version has one.

## Does this need a Skill?

**No.** This is a small POC with one clear, short testing recipe
(`QT_QPA_PLATFORM=offscreen python3 smoke_test.py`, documented in
`smoke_test.py` itself). A Skill earns its keep when a procedure is used repeatedly
across many sessions/files or is complex enough to be worth packaging and
reusing verbatim. Here, the whole recipe fits in a few lines of this file —
turning it into a Skill would be overhead without benefit. If this project
ever grows into a multi-file app with a recurring, elaborate test-and-verify
loop, revisit that answer then, not now.

## License

BSD 2-Clause (see `LICENSE`). Every source file carries the same header;
add it to any new file rather than leaving new files unheadered.
