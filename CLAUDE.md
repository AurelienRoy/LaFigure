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
    figure.py                 # LaFigure -- __init__ + composing the mixins below
                                # into class LaFigure(<mixins>, QMainWindow);
                                # everything else moved out by WP-01 (2026-09-28)
    toolbar.py                  # toolbar buttons/actions + global shortcuts
    menus.py                     # subplot right-click menu, empty-space menu
    layout.py                     # grid, resize/move/swap, floating subplots,
                                   # handle positioning (kept together: bug #6's
                                   # self.floating state ties them tightly)
    selection_ui.py                # click dispatch, selection (subplot/curve/
                                    # annotation), rubber band, Tab/nudge
    history.py                      # undo/redo stack, undo_group()
    brushing.py                      # RectBrush glue + the brushed-point actions
    clip_ops.py                       # copy/paste curve & subplot, delete_*
    annotation_ops.py                  # placement, relink, eventFilter
    view_ops.py                         # Home/Fit, Link X, remove average, FFT,
                                         # set_interaction_mode
    naming.py                           # figure/subplot/curve renaming, axis labels
    help.py                              # the "?" toolbar dialog (controls/version/credits)
    export.py                             # Save dialog: PNG/JPG/SVG/PDF + header preview
    series.py                              # SeriesKind registry + Series wrapper --
                                            # _add_series is the one series-construction site
    axes.py                                 # Axes facade (fig.subplot() returns one),
                                             # module-level gca()/gcf()
    kinds/                                   # built-in SeriesKinds beyond 'line':
                                              # scatter/stairs/area/hist/bar/errorbar/imshow,
                                              # one module each, self-registering on import
    console.py                               # embedded Python console dock, datatip,
                                              # src.filter(...) UI wiring
    groups.py                                # Group hierarchy, common label, HSL color offsets
    manager.py                 # FigureManager: tree of open figures/subplots,
                                # "New Figure" button (creates an empty figure)
    registry.py                 # FigureRegistry: process-wide list of open
                                 # LaFigure windows, with Qt signals
                                 # FigureManager listens to (figureOpened/
                                 # figureClosed/subplotsChanged/selectionChanged/
                                 # focusChanged/figureRenamed)
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
  tests/                   # helpers.py (Fake*Event, _mouse/_key, figure
                            # factories) + one test_<mixin>.py per module above
  run_tests.py             # plain runner (no pytest): `python run_tests.py`
                            # imports every tests/test_*.py and runs its
                            # test_* functions, prints ALL OK
```

Run it with `python3 -m lafigure` (not `python3 lafigure.py`
— that file no longer exists, replaced by the package above).

**As of WP-01 (2026-09-28)**, `figure.py` is no longer one 2,478-line
class — it's `LaFigure`'s `__init__`/lifecycle/demo, composed with the ten
mixins listed above (moved verbatim, guarded by an AST-level diff against
the pre-split file). `smoke_test.py` is gone, replaced by `tests/` +
`run_tests.py` (`QT_QPA_PLATFORM=offscreen python run_tests.py`; takes
optional name filters, e.g. `python run_tests.py layout`). This was
Wave 0 of the roadmap below (see `PLAN.md`) — a behavior-preserving split,
done first so parallel work packages could each own one module without
colliding. It also froze the interfaces later packages build on:
`focused_plot` (renamed from `active_plot`; a property whose setter is the
one place `registry.focusChanged(fig, plot)` fires), `registry.
selectionChanged(fig)` (once per outermost selection change), `registry.
figureRenamed(fig)` with undoable `fig.rename_figure`/`rename_subplot`/
`subplot_name`, and `add_subplot(..., rowspan=1, colspan=1,
axes_type='cartesian')` (spans passed through; any other `axes_type`
raises `NotImplementedError` for now). Running the never-before-executed
Phase 0 tests during this split surfaced three real bugs, now fixed — see
the dedicated lesson after bug #7 below.

**Why the split happened before annotations**: annotations needed their
own module and touch both LaFigure and the clipboard (an annotation's
serialization is reused by subplot copy/paste); doing the split first
meant that code landed in the right module from the start instead of
needing a second refactor. Annotations have since been implemented — see
the feature list and "Annotations" design-debt section below.

`HANDOFF.md` no longer exists — it was the previous, timestamped backlog
doc from before the library refactor, superseded by this file once
annotations (its "next planned piece") were implemented. **This file's
feature list below is the source of truth**, together with the phased
**Roadmap** section after it (the agreed next work).

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
      `tests/`) didn't need to change:
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
      in `tests/test_layout.py`, which scans every module in the package).
      A ViewBox's mouse-enabled state has exactly one
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
      Curve submenu. Right-clicking a subplot selects it, unless the
      subplot (or a selected curve on it) is already part of the selection,
      which is then kept whole so menu actions see the entire Shift-built
      set (`_on_plot_context`); the same rule applies to right-clicking a
      curve or an annotation. Right-
      clicking **empty space outside every subplot** instead opens a
      minimal menu with just Paste Subplot (`_show_empty_space_menu`,
      dispatched from `_on_scene_clicked` since there's no `ViewBox` there
      for pyqtgraph's own per-subplot menu to attach to).
- [x] Clicking a subplot makes it the visually active one (red border) —
      this used to be broken (see bug #0 below) and is now fixed
- [x] Clicking a curve selects/highlights it (thicker pen), and that
      selection — not just "the first curve" — is what FFT and Remove
      Average act on (those two stay single-target deliberately, see below)
- [x] **Multi-select via Shift+click, LibreOffice Draw / MATLAB style**
      (`self.selected_plots`/`self.selected_curves`/
      `self.selected_annotations`, each a superset of `focused_plot`/
      `active_curve`/`active_annotation`, the most recently selected one):
      Shift+click **toggles** a subplot, curve or annotation in or out of
      the selection, leaving every other selected item, of any kind,
      selected. Visually, every selected subplot gets the same red border
      and every selected annotation its dashed outline and handles.
      Only some actions read the multi-select — **Copy/Paste (curve and
      subplot), Delete, the X/Y-axis-label toolbar buttons, Toggle
      Legend, Rename Curve, annotation Properties… (color/width/fill, the
      fill only on rect/ellipse) and annotation drag** all act on the
      whole set. Dragging any selected annotation moves every selected
      annotation by the same on-screen offset, even across subplots; a
      plain press on a selected annotation keeps the group for that drag
      and collapses to just that annotation if released without moving.
      Link to… stays single-target. FFT, Remove Average, and everything else
      deliberately keep targeting only the single most-recently-clicked
      `focused_plot`/`active_curve`, unaffected by any wider selection —
      this split was an explicit product decision, not an oversight; don't
      "complete" it by wiring more actions to the multi-select without
      checking first. Deleting/removing an item also drops it from these
      lists (`_forget_curve_selection`, and the plot-side cleanup in
      `_forget_removed_plot`) so a stale reference never lingers in them.
- [x] **Selection is exclusive across kinds unless Shift is held.** A
      plain click on a subplot, a curve or an annotation deselects every
      other selected item of *every* kind. Clicking a curve deselects the
      selected subplot, including the curve's own subplot, which loses its
      red border and handles but stays `focused_plot` as the toolbar target.
      Every non-Shift selection, including programmatic ones (Add Subplot,
      FFT, paste, undo), goes through `_clear_selection` first, and
      move/resize handles only show on a subplot in `selected_plots`.
      Guarded by the `test_*click*` / `test_*selection*` functions in
      `tests/test_selection_ui.py`.
- [x] Deselection: **Esc**, double-clicking a subplot (or a curve, or
      empty space), or a plain single click that lands outside every
      subplot clears every selection of every kind. One Esc press also
      cancels an in-progress annotation placement or Link to…. A
      **Shift**+click on empty space does nothing.
- [x] Del key: deletes **everything selected, whatever its kind** —
      annotations, then curves, then subplots — each through its own
      existing single-item `delete_annotation`/`delete_curve`/
      `delete_subplot` call. Curves and subplot-owned annotations whose
      subplot is also being deleted are skipped: the subplot's own undo
      restores them, while separate steps would target the dead
      `PlotItem`.
- [x] **Rubber-band selection** (Select mode, LibreOffice Draw style):
      dragging from a point with nothing selectable under it — the figure
      margin, or a subplot's data area clear of curves, legends,
      annotations and handles — draws a dashed rectangle; on release,
      every subplot (by its data area) and annotation (by its shape, not
      its handle padding, `AnnotationItem.shape_scene_rect`) lying
      **fully** inside is selected, replacing the selection, or added to
      it with Shift. Curves are never band-selected. The data area is
      allowed as a start point because the gutters between subplots are
      only a few pixels wide; brushing, when on, keeps that drag instead.
      Mechanism (`_band_event`, from the scene `eventFilter`): press and
      release pass through to pyqtgraph, the moves are consumed once the
      band shows, so pyqtgraph ends the gesture with one plain click at
      the press point, which `_suppress_click` swallows. That is also why
      a band never starts on a curve or legend: pyqtgraph would deliver
      that click to it. Tested with real `QMouseEvent`s to the viewport.
- [x] **Keyboard** (Select mode): arrow keys nudge every selected
      annotation 1 screen pixel, Shift+arrow 10 (`NUDGE_PX`/
      `NUDGE_BIG_PX`), one undo entry per press, whatever each one's
      parent coordinates; subplots and curves don't move. Tab / Shift+Tab
      select the next / previous item exclusively, in reading order
      (`_tab_order`: subplots top-left first, each followed by its
      clickable curves and its annotations; free-floating annotations
      last), wrapping around; from zero or several selected items it
      starts at either end. Shift+Tab is bound as `"Shift+Tab"`, not
      `Key_Backtab`: a real keyboard sends Backtab *with* Shift, which Qt
      matches as Shift+Tab — a bare Backtab binding never fires, and the
      unhandled key then moves focus to the toolbar.
- [x] **One gesture = one Undo**, as in LibreOffice Draw / MATLAB:
      `with self.undo_group():` folds every `_push_history` inside it into
      a single entry (undo runs the steps in reverse, redo in order —
      exactly what N separate presses did, so each step's closures stay
      valid; groups nest; a one-step group is pushed unwrapped). Used by
      multi-delete, group annotation drag and multi-annotation
      Properties…. Any new action that loops over a selection pushing
      one entry per item should wrap its loop the same way.
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
        move/swap. Normal data pan/zoom is disabled while Select is
        active; dragging from a free point of a subplot's data area (or the
        figure margin) draws a selection rubber band instead — see below.
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

## Roadmap (agreed with the user 2026-09-28) — live backlog

Decided in one design conversation; every choice below is the user's, not
a default. No backward compatibility with earlier versions of this
library is required. Phases in order; tick items off as they land.

**Execution plan:** the work packages, their order, which ones can run as
parallel agents, file ownership and the merge protocol are in `PLAN.md`.
Read it before starting any roadmap item; update its status table when a
package lands.

### Phase 0 — small UI items
- [x] Zoom Rect's drag rectangle is **light gray**, not pyqtgraph's yellow
      (`layout.py`, `vb.rbScaleBox`). Verified by WP-01 running the
      never-before-executed test: it failed (pyqtgraph's
      `setMouseMode(PanMode)` discards `rbScaleBox`, so styling it once at
      creation never reached a real zoom drag — see the dedicated lesson
      after bug #7). Fixed by restyling on every switch to Zoom Rect
      (`view_ops._apply_view_mouse_mode`); `tests/test_view_ops.py`.
- [x] Toolbar after Zoom Rect: **Home** (reset view = autorange, was "Reset
      View"), **Fit Vertical** (Y to the min/max of the data inside the
      current X range) and **Fit Horizontal** (X to the min/max of the data
      inside the current Y range) — `view_ops.reset_view`,
      `fit_view_vertical`, `fit_view_horizontal`, `_fit_view`. Full data,
      never the downsampled display; hidden items ignored. Verified by
      WP-01; `tests/test_view_ops.py`.
- [ ] **Subplot right-click menu slimmed down**: remove pyqtgraph's
      "Export..." (export becomes the figure-wide toolbar Save, Phase 4),
      "X axis", "Y axis" and "Mouse Mode"; add **"Export to CSV..."** (the
      subplot's curves, full data); the brushed-point actions (Delete /
      Transform / Fit Selected Points, and Selection Stats with them) are
      **shown only while Brush mode is on**, and **disabled when no point
      is brushed**.

### Phase 1 — free layout on a fractional grid (replaces QGraphicsGridLayout)
- [ ] Drop `QGraphicsGridLayout` entirely. Subplots are positioned directly
      (`setGeometry`), recomputed on window resize. This deletes the float/
      placeholder/reattach code, stretch factors, the private
      `GraphicsLayout.layout` access, and the bug #5 guard — and the
      "one thing to internalize" section below then describes history.
- [ ] Figure owns a **grid**: column and row boundaries as figure fractions.
      Every subplot edge is a **fractional grid coordinate** (`left=1.5` =
      halfway between column lines 1 and 2), mapped piecewise-linearly
      through the boundaries. Spans = integer ranges > 1; free sizes and
      insets = any fraction. Dragging a grid line therefore rescales every
      edge referencing it, insets included.
- [ ] Positions are the subplot's **outer box** (axes/labels included), not
      MATLAB's inner data-area Position. "Align data areas" may come later.
- [ ] Overlap allowed; per-subplot z-order (Bring to Front / Send to Back);
      a subplot above another gets an opaque background (insets).
- [ ] Select mode: drag a **gutter on a grid line** = move that row/column
      line (all attached subplots follow); drag a selected subplot's
      **border/corner handle** = resize that subplot only; drag its **move
      handle** = move it; **Ctrl+drop onto another subplot = swap** (plain
      drop just moves).
- [ ] **Magnetic sub-grid shown only during a drag**: snaps to grid lines,
      cell subdivisions (½/¼, configurable), other subplots' edges
      (alignment guides) and figure margins; ~8 px threshold; **Alt**
      disables snapping.
- [ ] Mouse cursor changes on hover in Select mode: split cursors over
      draggable gutters, resize cursors over handles, move cursor over the
      move handle.
- [ ] Gutter right-click: insert/delete row/column, equalize rows/columns.
      Add Subplot fills the first empty cell, else appends a row. Delete
      leaves a hole, never shifts (bug #1 lesson).
- [ ] **FFT → subplot** adds a new grid row right under the time plot's row;
      the result is an ordinary, freely movable subplot.
- [ ] Layout changes (move/resize/swap/grid-line drag) **go through undo**
      (a layout is a few numbers — snapshot it).
- [ ] `'border'` annotation offset becomes a fraction of the subplot box
      (fixes Annotations simplification #5).
- [ ] **"?" toolbar button**: popup with explained controls (mouse/keys per
      mode), version, and credits.

### Phase 2 — data model: DataSource + Series kinds + console API
- [x] `DataSource`: shared columnar table (dict of numpy arrays, or from a
      pandas DataFrame; pandas optional). **A point's ID is its row index**;
      user IDs (database key, drone log, timestamp, …) are just columns.
      Series sharing a source are linked. **Built by WP-F** (2026-09-28,
      `lafigure/datasource.py`, no Qt dependency) — see its own docstrings
      for the exact API (`filter`, `hide_rows`/`show_rows`, `on_change`).
- [x] `SeriesKind` registry (`register_series_kind`), each kind: `create`,
      `to_dict`, `capabilities`. Replaces every `(x, y, pen, name)` tuple
      and `isinstance(c, pg.PlotDataItem)` filter with `_add_series`, the
      one series construction site (`tests/test_series.py`'s
      `test_add_series_is_the_only_series_construction_site`, same
      AST-scan pattern as `add_subplot`'s guard). **Built by WP-H**
      (2026-09-28, `lafigure/series.py`) with one kind, `'line'`
      (`{'brush','fft','remove_average','fit','copy'}`), which still
      creates a genuine `pg.PlotDataItem` via `plot_item.plot(...)` — the
      `Series` wrapper doesn't replace it, so every existing curve
      consumer (`selection_ui.py`'s click/highlight/Tab-order,
      `menus.py`'s curve submenus, `brushing.py`'s `RectBrush`) keeps
      working unmodified. **Seven more kinds built 2026-09-28**:
      `scatter`/`stairs`/`area`/`hist` (WP-I1), `bar`/`errorbar` (WP-I2),
      `imshow` (WP-I3, + a `pg.ColorBarItem`) — all in `lafigure/kinds/`,
      self-registering on `import lafigure`. Only `scatter`/`area` are
      `'brush'`-capable so far (real parallel x/y `RectBrush` can zip
      directly); `bar`/`errorbar`/`imshow` needed `SeriesKind.get_xy`/
      `set_xy` overrides (added generically to the base class alongside
      this work, so `Series.x`/`.y`/`.set_data` work for a kind whose item
      isn't a plain `PlotDataItem`) and a `hasattr(item, 'curve')` guard
      on `_add_series`'s click-wiring (an item without `.curve`, e.g.
      `BarGraphItem`/`ImageItem`, is plotted but not yet click-selectable).
      The `highlight`/`hit`/`rows_in_rect`/`show_rows`/`to_plotly` hooks
      and true click-selection for non-`PlotDataItem` kinds are still
      **not yet built** — that's WP-J (brushing-on-every-kind).
- [x] `Axes` facade, `lafigure/axes.py` (WP-H): `fig.subplot(row, col,
      ...)` returns one (`add_subplot` itself is unchanged, still returns
      a raw `PlotItem`); `ax.plot(x, y)` / `ax.plot(source, x='col',
      y='col')`, `ax.series` (derived live, no separate list to go
      stale), `ax.plot_item`. `s.x`/`s.y` (read-only views), `s.rows`,
      `s.source` (a private per-series `DataSource` when built from plain
      arrays, so linking costs nothing unless opted into), `s.set_data`
      (undoable). Only `ax.plot` exists so far — `scatter/stairs/area/
      hist/bar/errorbar/imshow` come with their respective kind packages.
      Module-level `lafigure.gca()`/`gcf()` (`axes.py`): the current
      figure is tracked via weak refs + `QApplication.focusChanged`
      (`registry.focusChanged` alone misses "clicked back into an
      already-focused subplot"), not a `registry` field — see WP-H's
      lesson below if extending this.
- [x] Embedded Python console panel (`lafigure/console.py`, WP-L,
      2026-09-28): `pyqtgraph.console.ConsoleWidget` in a `QDockWidget`,
      toggled by a toolbar button, namespace `{fig, gca, gcf, np}`.
- [x] Datatip: `ax.datatip = "fmt string"` or a callable, wired into the
      data-cursor annotation's placement text
      (`annotation_ops.py`'s `'cursor'` branch). Since `Axes` is
      deliberately stateless (any `Axes(fig, plot)` on the same subplot
      compares equal), the spec is stored keyed by `plot_item` in
      `console.py`, not as an `Axes` instance attribute — reachable via a
      `property` `console.py` adds to the `Axes` class at import time.
      Plotly `hovertemplate` export not yet done (that's WP-M's job, when
      it builds HTML export).
- [x] `src.filter(mask | expr | None)`: `console.watch_source`/
      `refresh_series_for_source` subscribe to `DataSource.on_change` and
      re-derive every linked series' displayed x/y from
      `source.visible_rows` via `SeriesKind.get_xy`/`set_xy` — view state,
      not pushed to undo. A histogram-like kind's own `set_xy` would need
      to rebin internally for this to "just work" on it; unverified (no
      histogram kind was present in WP-L's own worktree when it built
      this — confirm once I1's `hist` kind and this are both live).

### Phase 2b — Figure Manager renaming, curve browser, groups
- [x] **Glossary — "focused subplot"**: the subplot that is selected, or
      else the one that received the last action. Renamed from `active_plot`
      to `focused_plot` by WP-01 (2026-09-28); a property whose setter is
      the only writer and the one place `registry.focusChanged(fig, plot)`
      fires. Toolbar actions and the curve browser target it. Distinct
      from `_hover_plot` (Home/Fit only).
- [x] The Figure Manager becomes **two tabs: "Figure browser" and "Curve
      browser"**. **Built by WP-D** (2026-09-28, `manager.py`) — the Curve
      Browser tab is a structural placeholder only (K2 fills it in).
- [x] Figure browser tree: **every node text-editable** (double-click / F2):
      a figure node renames the figure (window title), a subplot node
      renames the subplot (its title). Undoable in that figure.
- [x] Figure browser: rows of **selected subplots are colored blue**, synced
      live with each figure's selection.
- [x] Figure browser: **right-click menu on every node: Copy / Paste /
      Delete** (same actions and undo as in the figure itself).
- [x] Figure browser: **three checkboxes at the top — show curves, show
      annotations, show GUI controls**. When checked, those items appear as
      sub-levels under their subplot (groups as a further sub-level, once
      K2 wires `Group`/`GroupsMixin`, built below, into this tree).
- [ ] **Curve browser tab** (a toolbar icon in each figure opens the manager
      on this tab): shows only the **focused subplot**'s series and
      annotations as a tree, following focus live (the focused subplot of
      the most recently active figure). Visibility checkbox per row
      (tristate on groups) for quick inspection; right-click menu on every
      node; selection synced both ways with the figure. Bottom editor acts
      on the selected row(s): name, Z order (up/down/front/back; drag rows
      to reorder), color, line width, line style, marker, alpha. Property
      edits are undoable; visibility checkboxes are view state (not undo).
- [x] **Groups** (hierarchy for series and annotations, nestable; **a group
      never spans subplots** — user decision, enforced by raising on a
      mismatched member): group / ungroup (Ctrl+G / Ctrl+Shift+G,
      undoable), show/hide a whole group (view state, not undoable — same
      rule as every other visibility toggle in this app), a group **base
      color**: each member stores its color as an HSL offset from the
      group base (via `colorsys`), so changing the group tone preserves
      the members' small variations; re-deriving a member's offset uses
      its color *as of the next retint*, not a stale preset offset, if the
      user recolored it individually in between. Presets: "raw/filtered"
      (same hue, light vs dark) and "sensor family" (small hue spread).
      Serialized (`Group.to_dict`/`from_dict`, `lafigure/groups.py`).
      **Built by WP-K1** (2026-09-28) — data model + Ctrl+G/Ctrl+Shift+G
      only; grouped-annotation move/select-together already existed
      (multi-select) and needs no group-specific code. **Not yet wired**:
      the `clip_ops.py` hook that carries a group through copy/paste
      (K1 doesn't own that file; reported diff pending, see PLAN.md).
- [ ] Group **common label**: `Group.display_name(member)` (prefix/suffix,
      built by WP-K1) exists and never mutates the underlying item's own
      name, but isn't wired into anything a user sees yet — that's part of
      **K2** (the Curve browser's bottom editor, where the prefix/suffix
      position toggle and the group-node right-click menu — Copy/Paste/
      Delete the whole group, Edit common label — both live).

### Phase 3 — brushing/linking on every kind
- [ ] Brushing works on any kind via `rows_in_rect`/`show_rows`; histogram
      bars ↔ time-series points through a per-row bin index
      (`np.digitize` once); brushed bars show a stacked partial bar.
- [ ] **Near-zero overhead when off**: no masks, overlays or connections
      until the Brush toggle is on; selection = one sorted int array per
      DataSource; hit-test on full data, never the downsampled display.
- [ ] Generalizes and replaces `SelectionModel`/`LinkedScatter` and the
      hardcoded `scatter1`/`scatter2`.
- [ ] **Dataset stays intact.** Figure menu action "Hide Brushed Points":
      marks brushed rows in a hidden-rows column of the source; every
      linked subplot stops drawing them. Undoable, plus "Show All".
- [ ] Transform / Remove Average / FFT write a **new derived column**
      (revertible), never overwrite source data.
- [ ] Pasted series (incl. across figure windows) **stay linked** to their
      source.

### Phase 4 — Save / export
- [ ] Save button, **leftmost** in the toolbar (+ Ctrl+S): choose any of
      PNG / JPG / HTML (+ SVG / PDF); several formats at once, same base
      name.
- [ ] Header info text (source, date, user, custom `fig.info` keys) from a
      customizable format template (`{date:%Y-%m-%d}` …), remembered in
      `QSettings`. **Word-style print preview**: the user edits the text
      and its placement on a preview, then exports when satisfied.
- [ ] HTML via plotly (optional dependency): subplots placed by absolute
      `domain` (exact for free layout/insets), WebGL traces, annotations as
      shapes, source metadata in `customdata` so hover datatips work in
      the browser, hidden rows excluded. Linked brushing in the HTML is a
      later extra. Controls export as their current state only.
- [ ] Too-large HTML: a **popup asks**: keep all / decimate 1:N (N
      editable, default 10) / peak-preserving decimation (same look).

### Phase 5 — interactive controls + reactive tables
- [ ] Buttons, sliders, dropdowns, checkboxes with user Python callbacks
      (e.g. drive `src.filter`), and editable tables (e.g. live stats of
      brushed points: `table(fn, depends_on=[src])` recomputes on selection
      / filter / hidden changes).
- [ ] Controls live **in grid cells** (a cell kind like a subplot, same
      move/resize/snap) **or in a separate figure window** — a generic
      container class usable for both.
- [ ] Slider callbacks debounced (~50 ms); a failing callback shows its
      traceback in the status bar, never crashes; control-driven filter
      changes are view state (not undo entries).

### Phase 6 — 3D
- [x] **Option A**: a 3D cell is a normal grid item that renders an
      offscreen GL view to an image each frame and forwards mouse input to
      its camera — keeps move/resize/select/copy/annotations working.
      **Spiked and confirmed GO by WP-G** (2026-09-28, `spikes/README.md`,
      `spikes/gl_offscreen_readback.py`): on a real GPU, one 3D cell costs
      ≤2.4ms/frame at 1600x1000 up to 1M points (readback is 70-95% of
      that, cost tracks image size not point count); four 1M-point cells
      in a realistic window cost 6.8ms/frame — well inside a 16.7ms/60fps
      budget. Software (Mesa llvmpipe) rendering is a **no-go** for large
      data (1M points: ~170ms/frame) — the draw itself is slow, same as a
      native GLViewWidget would be on the same software renderer, so this
      doesn't count against Option A specifically. Camera math (orbit/pan/
      wheel, reimplemented in numpy since PyOpenGL wasn't installable
      here) matches Qt's own to 2.6e-6, verified against real lit pixels
      after real mouse-driven drags. Brushing via numpy projection: ~30ms
      for 1M points, too slow per mouse-move — project once on drag-press
      (camera doesn't move mid-drag) and rect-test per move instead (~2ms).
      **WP-O's five conditions, from the spike's own recommendation**:
      redraw only when something changed; one offscreen context per figure,
      made current before each draw; brush projects once per drag, not per
      move; size images for high-DPI; a placeholder when no GL context
      exists. GLViewWidget/GLScatterPlotItem themselves were never actually
      run (PyOpenGL unavailable) — the spike's own drawing/readback calls
      stand in, documented as unverified against pyqtgraph's real classes.
- [ ] `axes_type='3d'`: `scatter3d`, `line3d`, `surface`; brushing via
      camera-matrix projection in numpy → rows (links with 2D plots).

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
  etc. directly and assert on state. *Corrected 2026-09-27:* this said
  simulating a real drag headlessly was unreliable, which is false with
  PyQt5 offscreen — building `QtGui.QMouseEvent`s and `sendEvent`-ing them
  to `layout_widget.viewport()` (press, moves with `LeftButton` held,
  release), and `QtTest.QTest.keyClick` on an activated window for keys,
  both work (`smoke_test.py`'s `_mouse`/`_key`). Use them whenever the
  behavior depends on Qt's or pyqtgraph's own event routing — a direct
  method call can't show it: the rubber band's leftover-click bug and
  the dead Shift+Tab binding were both invisible to direct calls.
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

### 8. A pyqtgraph item you style once can be silently rebuilt later
**Symptom (found by WP-01, 2026-09-28):** Zoom Rect's drag rectangle was
restyled to light gray at subplot creation (`vb.rbScaleBox.setPen(...)`),
and a test read `vb.rbScaleBox.pen()` right after and saw the new color —
apparently fixed. But a real zoom drag still showed pyqtgraph's yellow.

**Root cause:** pyqtgraph's `ViewBox.setMouseMode(PanMode)` — called right
after the styling, as part of the same `add_subplot`, to set the default
mode — discards the existing `rbScaleBox` and lets pyqtgraph build a fresh
one, unstyled, the next time a rectangle is needed. The one-time styling
survived only until the very next mode switch, and the original test
happened to read the item before that switch ran, in the mode where a
zoom drag never triggers it at all.

**Lesson:** a library object exposed as a persistent attribute (`self.
rbScaleBox`) isn't necessarily kept for the object's lifetime — it can be
an internal cache the library is free to rebuild, and the docs/API give no
signal either way. Two defenses, both needed here: apply styling at every
call site that can plausibly trigger a rebuild (here: every switch into
the mode that uses it), not just once at creation; and test the actual
user-visible path (a real drag, in the mode the user would use it in), not
whatever state happens to exist right after setup.

### 9. Checking "did the flag get set" instead of "did the real state change"
**Symptom (found by WP-01, 2026-09-28):** turning Grid Layout back on
after floating a subplot recomputed the right stretch factors into
`self.row_stretch`/`col_stretch`, but the grid visually snapped back to
equal-sized cells instead of the floated size.

**Root cause:** `toggle_overlap_resize(False)`'s reattach loop popped every
entry out of `self.floating` as it went; the `if self.floating:` guard
that then decided whether to apply the new stretch factors ran *after*
that loop, so it always saw an empty dict and skipped applying them. The
values were computed correctly and simply never reached the layout.

**Lesson:** this is bug #2's lesson again in a new shape — a collection
that a loop empties as a side effect can't be used afterward to ask "did
that loop have anything to do". Snapshot whatever the check needs (here:
`bool(self.floating)`, or just always apply) before the loop that consumes
the collection runs, not after.

### 10. `QT_QPA_PLATFORM=offscreen` gives no OpenGL at all on Windows/Qt 5.15
**Symptom (found by WP-G's 3D spike, 2026-09-28):** a standalone script
using `QOpenGLContext`/`QOffscreenSurface` to render a 3D scene and read it
back (the Phase 6 "Option A" approach) needs a real GL context; under this
project's own headless test platform (`QT_QPA_PLATFORM=offscreen`),
`QOpenGLContext.create()` simply returns `False` — no context, no error
message pointing at why.

**Root cause:** the `offscreen` QPA platform plugin on Windows provides no
GL support at all (unlike Linux, where Mesa's llvmpipe can back it). This
is a platform-plugin limitation, not something the app or pyqtgraph can
work around. Confirmed real GPU rendering *does* work when a real Windows
session is used (no `QT_QPA_PLATFORM` override) even with no window ever
shown; software rendering can be forced app-wide with `QT_OPENGL=software`,
but that also demotes the *2D* viewport's `useOpenGL=True` to software,
not just the offscreen surface — the two aren't independently selectable.

**Lesson:** don't assume the same `offscreen` platform trick that makes
this project's 2D headless tests possible (`smoke_test.py`/`run_tests.py`
since day one) extends to GL features — verify with a plain
`QOpenGLContext().create()` check, not just "pyqtgraph imported fine", the
same caution CLAUDE.md already gives for `PySide6.QtCore` imports (see
item 7 above). Any GL-dependent feature (3D, Phase 6's WP-O) needs its own
logic (camera math, hit-testing, brushing projection) kept GL-free and
independently testable — exactly what WP-G's spike did, reimplementing
`GLViewWidget`'s camera math in numpy so it could be verified without a
real context — plus a runtime fallback (a placeholder cell) for when no GL
context can be created at all, which the offscreen test suite will always
hit.

### 11. A short `QMouseEvent` constructor's `globalPos` defaults to `QCursor.pos()`, breaking item-level hit-testing in headless tests
**Symptom (found by WP-A, 2026-09-28):** dragging a resize handle, a
gutter, or an annotation via `tests/helpers._mouse` never worked — the
handle simply never received its press — even though the same helper's
events reached the scene's own `eventFilter` (rubber-band selection,
built entirely on `eventFilter`, worked fine) at exactly the right
`scenePos()`.

**Root cause:** `_mouse` built its `QMouseEvent` with the short
constructor, `QMouseEvent(type, localPos, button, buttons, modifiers)`,
which sets `windowPos`/`screenPos` to `QCursor.pos()` — the real, arbitrary
OS cursor position, unrelated to `localPos` — rather than to the point
being simulated. `QGraphicsScene`'s own item-picking (which `QGraphicsItem`
receives a press) is driven by the event's *global* position mapped back
through the view, not by `scenePos()`/`localPos()`. So every simulated
press landed, for hit-testing purposes, whatever was under the real,
never-moved OS cursor — while the scene's `eventFilter` (which reads
`event.scenePos()` directly, computed from `localPos`/`pos()`, not from
the global position) still saw the intended point. Two different pieces of
Qt machinery reading two different fields of the same event, only one of
which the short constructor sets correctly.

**Lesson:** when a headless mouse-event helper needs an *item* (not just
the scene's own event filter) to receive the simulated event, use the full
`QMouseEvent(type, localPos, windowPos, screenPos, button, buttons,
modifiers)` constructor with `windowPos`/`screenPos` explicitly mapped
from the same point via `view.viewport().mapToGlobal(...)` — never rely on
the short constructor's `QCursor.pos()` default for anything that depends
on Qt's own hit-testing. Fixed in `tests/helpers._mouse`, used by every
package's drag tests from here on. A related, smaller lesson from the same
fix: once handles correctly receive clicks, a test's *fixed* screen-space
point (e.g. `QtCore.QPointF(2, 2)`, chosen when "the figure margin is
always empty") can silently start landing on a *different* interactive
element (a newly-selected subplot's resize handle, now positioned right
there) after some earlier step in the same test changes what's selected —
`test_band_from_the_margin_selects_enclosed_subplots_only` hit exactly
this. Don't assume a magic coordinate stays "empty space" once the
test has changed what's selected; pick a point relative to what should
still be empty at that specific moment, or re-verify with
`_can_start_band_at`/equivalent rather than reusing an earlier point.

### 12. Two lessons from WP-H (Series/SeriesKind, 2026-09-28)

**A "one construction site" guard can span files across package
ownership boundaries.** WP-H's brief asked for a test asserting exactly
one series-construction call site, mirroring `add_subplot`'s existing
guard — but two curve-building call sites turned out to live in
`layout.py` (`delete_subplot`'s undo, `_insert_subplot_at`) and
`brushing.py` (the Fit overlay curve), neither of which WP-H owned or
could edit. **Lesson:** when a coordinator plans a package that adds a
"there is exactly one construction site" invariant, check first whether
every current call site already sits inside that package's owned files —
if not, either widen ownership for that package, or have it ship the
guard with an explicit, temporary exceptions list (`_PENDING_MIGRATION`
in `tests/test_series.py`) plus ready-to-apply diffs for the
out-of-ownership sites, so the coordinator can close the gap in one pass
right after merging — which is what happened here (both diffs applied,
the exceptions list is now empty).

**`registry.focusChanged` alone can't track "the current figure" for a
module-level `gcf()`.** It only fires when `focused_plot` actually
*changes* — so clicking back into a figure whose focused subplot is
already correct (e.g. switching window focus without touching a subplot)
never fires it, and a `gcf()` built only on that signal would keep
returning a stale figure. `axes.py` also listens to
`QApplication.focusChanged` (connected lazily, since `axes.py` can be
imported before a `QApplication` exists) to catch plain window-focus
changes the subplot-level signal misses. **Lesson:** a "most recently
used X" tracker needs to listen at the same granularity as what "using"
actually means to the caller — a signal that fires on a narrower
condition (subplot focus) will silently miss a broader one (window
focus) that the caller cares about just as much.

### 13. A worker's "not wired in yet" test shim breaks the moment the coordinator actually wires it in

**Symptom (recurring — WP-E/WP-C in wave 1, WP-L in wave 3, all
2026-09-28):** a work package builds a new mixin (`SaveMixin`, `HelpMixin`,
`ConsoleMixin`, ...) that isn't yet a base class of `LaFigure` (the
package doesn't own `figure.py`, or `figure.py` is being edited by a
sibling package in the same wave). To test it anyway, the package writes
`class _SomeFigure(NewMixin, m.LaFigure): pass` and builds figures with
that instead. Every time, once the coordinator applies the reported diff
and `NewMixin` becomes a REAL base of `LaFigure` (`class LaFigure(...,
NewMixin, QtWidgets.QMainWindow)`), that test-only subclass throws
`TypeError: Cannot create a consistent method resolution order (MRO) for
bases NewMixin, LaFigure` — `LaFigure` now already has `NewMixin`
somewhere in its own MRO, so putting it first in a subclass's bases
creates a contradiction Python's C3 linearization can't resolve.

**Root cause:** the shim's whole premise (`NewMixin` reachable only
through this test subclass) stops being true the moment the coordinator's
wiring lands, but nothing signals the test file to stop using it.

**Lesson:** once a coordinator applies a "mix `NewMixin` into `LaFigure`"
diff, immediately grep that package's own test file for a
`class _X(NewMixin, m.LaFigure)` (or similarly named) shim and replace
every use of it with `m.LaFigure` directly — this is now a required,
predictable step of applying that specific kind of diff, not an
occasional cleanup. A worker package can preempt it: if you know your
mixin will likely need `figure.py` wiring later, say so plainly in your
report next to the diff, so the coordinator expects this exact fix.

## The one thing to internalize before touching this kind of code — historical (until WP-A, 2026-09-28)

**This section described the codebase from the original single-file POC
through the library refactor, up to Phase 1's free-layout rewrite. WP-A
deleted `QGraphicsGridLayout` entirely** — subplots are now positioned
directly by fractional grid coordinates (`lafigure/grid.py`,
`lafigure/layout.py`), so the "layouts prevent overlap by construction"
framing below, and bugs #1/#2/#3/#5/#6 it explains, are history: none of
that code exists any more. Kept for the *general* lesson (a container
managing an item's placement takes back exactly the affordances you're
using it for), which still applies to `QGraphicsScene`, undo stacks, and
anything else "managing" this code touches next.

## Should you reuse the code?

Only if you're extending *this exact app*. If you're building something
similar from scratch, prefer re-deriving the design from the principles
above over copying this file's structure — a few things in it are
POC-grade simplifications made under the sandbox constraints above, not
necessarily the right call in a codebase you can actually test:

- **Superseded by WP-A (2026-09-28):** this bullet used to describe manual
  resizing/moving forgetting custom sizing across a structural grid change,
  because the grid was `QGraphicsGridLayout` row/col stretch factors that
  couldn't be precisely reindexed. The free-layout rewrite's fractional
  grid coordinates (`lafigure/grid.py`) don't have this problem — an edge
  is a fraction referencing specific grid lines, so it survives an
  add/delete elsewhere in the grid exactly, with no reindexing needed.
- Brushing is hardcoded to two named scatter subplots (`self.scatter1`/
  `self.scatter2`) rather than a general registry — a known, documented
  shortcut, not a pattern to repeat.
- **Superseded by WP-A:** `_grid_layout()`, which reached into pyqtgraph's
  private `GraphicsLayout.layout` for row/column stretch factors, is gone
  along with `QGraphicsGridLayout` itself — subplots are positioned
  directly now, so there's no pyqtgraph layout object left to reach into.
  The "fail loud, not silent" pattern it used (a runtime `WARNING` to
  stderr on an unexpected pyqtgraph internal) is still worth keeping if a
  future package reaches into another undocumented pyqtgraph attribute.

## Does this need a Skill?

**Revisited 2026-09-28: partly yes.** The earlier answer was "no" for a
small POC with one short test recipe, with the note to revisit it if the
project grew a recurring, elaborate loop. The roadmap and `PLAN.md` created
exactly that: many work packages, run as parallel worker agents across
several sessions, each following the same rules, and a coordinator
repeating the same resume/merge/launch cycle every session. So:

- **Worker agent definition — `.claude/agents/lafigure-worker.md`.** A
  custom subagent type rather than a
  Skill: it holds the standing rules every worker repeats — read CLAUDE.md
  and PLAN.md, edit only the package's owned files, tests first, run the
  offscreen suite, BSD header on new files, commit on `wp/<id>`, the fixed
  final-report format — plus its tools and default model. Each launch
  prompt then carries only the package-specific part (goal, owned files,
  interfaces). `PLAN.md`'s brief template holds only the package-specific
  part; the standing rules live in the agent file — change them there.
- **Coordinator Skill — `/lafigure-next`
  (`.claude/skills/lafigure-next/SKILL.md`).** A
  thin trigger for `PLAN.md`'s "How to resume" and "Merge protocol":
  status table, branches and worktrees, merge finished packages, run the
  suite, update the docs, launch the next wave. The logic stays in
  `PLAN.md`; the skill only saves re-explaining it every session.

Still **not** Skills: the test recipe (one command:
`QT_QPA_PLATFORM=offscreen python run_tests.py`, since WP-01 landed
2026-09-28) and design decisions (they belong in this file, which every
session and agent already reads).

## License

BSD 2-Clause (see `LICENSE`). Every source file carries the same header;
add it to any new file rather than leaving new files unheadered.
