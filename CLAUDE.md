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
    html_export.py                         # HTML export via plotly (EXPORTERS['html']),
                                            # decimation popup for too-large exports
    series.py                              # SeriesKind registry + Series wrapper --
                                            # _add_series is the one series-construction site
    axes.py                                 # Axes facade (fig.subplot() returns one),
                                             # module-level gca()/gcf()
    kinds/                                   # built-in SeriesKinds beyond 'line':
                                              # scatter/stairs/area/hist/bar/errorbar/imshow,
                                              # scatter3d/line3d/surface (axes_type='3d'),
                                              # one module each, self-registering on import
    view3d.py                                # View3DBox: a 3D cell's camera, offscreen
                                              # GL render + QPainter fallback, mouse handling
    console.py                               # embedded Python console dock, datatip,
                                              # src.filter(...) UI wiring
    groups.py                                # Group hierarchy, common label, HSL color offsets
    curve_style.py                           # curve line width/style, marker, color,
                                              # z-order: the one highlight-aware,
                                              # undoable path for style edits
    controls.py                              # ControlPanel/ControlPanelWindow: buttons,
                                              # sliders, dropdowns, checkboxes, reactive tables
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
    selection.py                    # brushing protocol (rows_in_rect/show_rows/
                                     # brush_bins) + RectBrush -- SelectionModel/
                                     # LinkedScatter deleted 2026-09-28 (WP-J)
    grid.py                          # fractional grid coordinates <-> figure
                                      # fractions (the free layout, WP-A)
    datasource.py                    # DataSource: shared columnar table, row
                                      # index = point ID, hide/filter (no Qt)
    handles.py                       # DragHandle base + ResizeHandle, MoveHandle,
                                      # AnnotationHandle (child-parented resize/
                                      # rotate/endpoint grip for one AnnotationItem)
    editable_text.py                  # in-place rich-text editing (title/axis-label/
                                       # legend/annotation text), FontDialog, the
                                       # font-spec dict, set_text/set_font undo paths
    richtext.py                        # to_html/to_plain/to_plotly: a small LaTeX-ish
                                        # subset -> Qt rich text / Unicode (bold,
                                        # italic, super/subscript, Greek, math symbols;
                                        # no dependency, no real LaTeX math)
    annotations.py                     # AnnotationItem (all 8 shape kinds) + the
                                        # figure/border/axes filiation model
    transform.py                        # per-series display Transform (dx/dy/sx/sy) +
                                         # its modeless popup -- display-only, the
                                         # DataSource/raw array is never written;
                                         # Remove Average is dy = -mean through this
    debug.py                             # enable_debug_mode(): logging + faulthandler +
                                          # exception hook + Qt message bridge, one
                                          # fixed overwritten log file for bug reports
  icons/
  tests/                   # helpers.py (Fake*Event, _mouse/_key, figure
                            # factories) + one test_<mixin>.py per module above
  run_tests.py             # plain runner (no pytest): `python run_tests.py`
                            # imports every tests/test_*.py and runs its
                            # test_* functions, prints ALL OK
  examples/                # runnable, customer-facing scripts -- see
                            # "Example scripts" below
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

## Example scripts (`examples/`, added 2026-09-29; 3 more in round 4, 2026-09-30)

Ten standalone, runnable scripts, each coded the way a library customer
would (`import lafigure`, `fig.subplot(...)`, `ax.plot`/`ax.scatter`/
`ax.bar`/etc.), one per broad slice of the public API:
`line_signal_annotations.py` (a line plot + textarrow/cursor/rect
annotations), `series_kinds_gallery.py` (bar/errorbar/area/stairs/hist/
imshow, one subplot each), `linked_brushing_scatter.py` (two scatters +
a histogram sharing one `DataSource`, annotated, with a comment on how
to try Brush mode live), `three_d_scene.py` (scatter3d/line3d/surface),
`interactive_controls.py` (a scatter cross-filtered live by a slider/
checkbox in a separate `ControlPanelWindow`, plus a reactive table —
needs `console.watch_source(source)` armed explicitly, since nothing
opened the console dock, which is what normally arms it),
`groups_and_style.py` (`raw_filtered_preset`/`sensor_family_preset`,
registered on `fig.groups`), and `copy_paste_across_figures.py` (two
LaFigure windows; a whole subplot and a single curve copied from one
into the other through the shared, process-wide `Clipboard`, by setting
`fig.focused_plot`/`fig.active_curve` the way a click would before
calling the same `copy_subplot`/`copy_curve`/`paste_subplot`/
`paste_curve` the toolbar/menu actions call). **Round 4 added three
more**: `custom_datatip_example.py` (`ax.datatip` as both a format
string and a Python callable, multi-line formats, and a 3D curve's
cursor text — data cursors placed non-interactively via
`_create_annotation`, text computed through `lafigure.console.
datatip_text`), `image_processing_with_controls_example.py` (a
procedural grayscale `imshow` image driven live by a
`ControlPanelWindow`: sliders for brightness/contrast/blur, a colormap
dropdown, an invert checkbox, a Reset button, and a reactive stats
table — every edit undoable via Ctrl+Z, routed through
`LaFigure._push_history` directly rather than `Series.set_data`, see
the gap noted below), and `expanded_series_kinds_gallery.py` (one
subplot per round-4 series kind — all 19, see the Round 4 section
below). Run any of them with `python examples/<name>.py` from
anywhere — each inserts the repo root into `sys.path` itself at the
top (`lafigure` isn't pip-installed; there's no `setup.py`/
`pyproject.toml`), so no `PYTHONPATH` or `-m` gymnastics are needed.

**`Series.set_data` has no image-kind branch.** It requires `len(x) ==
len(y)` with a non-`None` y; an image kind's `get_xy` returns `(2-D
matrix, None)`, so calling `set_data` on an `imshow`/`heatmap` series
raises `TypeError: len() of unsized object` (confirmed empirically
while building `image_processing_with_controls_example.py`, round 4).
The example works around it by pushing undo directly through
`LaFigure._push_history` instead — the same precedent
`_create_annotation` already set for a construct with no public
undoable setter. A future session giving `Series.set_data` a real
image-kind branch should update that example to use it.

**Annotations have no public, non-interactive constructor yet.**
Normally a user picks a shape from the toolbar's "Annotate" dropdown and
clicks/drags it into place (`annotation_ops.py`'s `start_placing_
annotation` + `eventFilter`). A script that wants one without a mouse
calls `LaFigure._create_annotation(kind, anchor, parent_plot, p0,
p1_local, text=...)` directly — underscore-prefixed (no dedicated public
wrapper exists), but it's the one real, undoable annotation-creation
path in the app; this project's own test suite uses it exactly this way
(grep `_create_annotation` under `tests/`). `p0`/`p1_local` are in the
anchor's own coordinate space: DATA units for `anchor='axes'` (so the
shape pans/zooms with the subplot), scene PIXELS for `anchor='figure'`/
`'border'`. If a future session builds a real public wrapper for
non-interactive placement, update these four scripts to use it instead.

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
      second window there's nothing to paste into. **Toolbar button**
      (2026-09-29, `toolbar.py`/`menus.py`'s `open_figure_manager`): the
      leftmost toolbar action, just before Save, opens/raises the Figure
      Manager on its Figure Browser tab (`FigureManager.show_figure_browser`,
      mirroring `show_curve_browser`'s create-if-none-open pattern) — no
      subplot right-click needed just to see the manager.
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
- [~] Change the z-order of curves: the Curve browser's Z-order buttons
      (WP-K2, `manager.py`) and the curve menu's Bring to Front / Send to
      Back (`curve_style.curves_to_front`), undoable. The subplot menu's
      **Reorder Curves...** opens the Figure Manager on the Curve browser
      tab for that subplot (`LaFigure.open_curve_browser` →
      `FigureManager.show_curve_browser`; `registry.manager` is the one
      manager, created on demand). Reordering the legend to match is
      **not implemented**.
- [x] **Curve display style, MATLAB-like** (2026-09-29): the curve menu's
      Line Width / Line Style (`-` `--` `:` `-.` none) / Marker (o + * x s d
      ^ v > < p h, none) / Marker Size submenus, acting on the curve
      selection if the right-clicked curve is in it (one undo entry).
      Gated by kind (`curve_style._LINE_KINDS`/`_MARKER_KINDS`). Every
      style edit — menu and Curve browser editor alike — goes through
      `CurveStyleMixin._edit_curve_styles`, which unhighlights, applies,
      re-highlights: while a curve is selected `opts['pen']` is the
      highlight and the real pen is parked in `opts['_orig_pen']` (popped
      on deselect). Line style "none" is a transparent pen, never
      `pen=None` (bug #15). **Line Color.../Marker Color...** added to the
      curve menu (2026-09-29): `set_curve_line_color`/`set_curve_marker_color`
      (`curve_style.py`) recolor only their own target — unlike the
      pre-existing `set_curve_color` (still used by the Curve Browser's
      single color swatch, which recolors "whatever the curve draws" as
      one field), these are two independent menu entries, each gated
      the same way its sibling submenu is (Line Color enabled whenever
      the kind has a line; Marker Color only once a marker is actually
      set, mirroring Marker Size). Recoloring a line kept invisible by
      Line Style "none" preserves the alpha-0 invisibility (keeps the
      new color parked underneath, same trick as bug #15) rather than
      making it reappear. **Menu order and gating fixed** (2026-09-29,
      P2): the submenu order is now Line Style / Line Width / Line Color
      / Marker / Marker Size / Marker Color; a scatter series with a
      visible connecting line now correctly enables Line Style/Width/
      Color (the old gate was purely by kind string, so a scatter could
      never show them regardless of whether a line was actually drawn —
      see bug #15's own "no line is three different states" lesson,
      recurring here). **Transform...** (2026-09-30, P7): a modeless
      per-curve popup — offset X/Y, scale X/Y, live-applied, OK/Reset/
      Cancel — display-only (`transform.py`): the underlying `DataSource`/
      raw array is never written, so Reset is exact and free forever;
      brushing, Selection Stats, Fit, and CSV/HTML export all see the
      transformed values because they already read the item's drawn
      data. Applies to `line`/`scatter`/`stairs`/`area` only. Remove
      Average is now `dy = -mean` through this same mechanism (no more
      derived column for this path), so its effect is visible in, and
      resettable from, the popup. Click/selection tolerance on a curve
      or scatter point is also widened a few screen pixels beyond the
      exact drawn path (`selection_ui.py`), and a right-click on an
      already-selected curve reliably keeps it selected while its own
      menu opens (traced to click-cycling firing on right-clicks too,
      not just left — see bug #22 for the click-tolerance mechanism).
      **Surface Color.../Surface Opacity** (round 4, 2026-09-30,
      `curve_style.has_fill`/`set_curve_fill_color`/
      `set_curve_fill_opacity`): two curve-menu entries for any series
      whose kind actually fills, gated on the item's own
      `opts.get('fillBrush') is not None` rather than a hardcoded kind
      list (CLAUDE.md bug #16's lesson applied going forward) — present
      for `area` and absent for a plain line.
- [ ] Manipulate individual numeric points (drag a sample to edit its
      value) — not implemented
- [x] Add/remove a legend (toolbar toggle, or the subplot right-click
      menu). **Selectable and movable** (2026-09-29): click it in Select
      mode → red dashed border, exclusive like any selection
      (`selected_legend`); drag it → one undo entry; Del hides it. Fixed
      the same day: a legend toggled on over existing curves was **empty**
      (zero size, invisible) — pyqtgraph enters an item in a legend only
      from `PlotItem.addItem`, and only if the legend already exists, so
      `_show_legend` adds the named plot-data items itself. **Underscore-
      hiding and z-order (2026-09-29, P3):** a curve named with a leading
      `_` (matplotlib's `"_nolegend_"` convention — used by this
      project's own `line_signal_annotations.py` example) is never
      listed; entries are ordered front-most (highest z-order) first,
      ties by creation order, via `LaFigure._refresh_legend_order()`,
      called from `_show_legend`, `curves_to_front`/`send_to_back`, and a
      curve rename.
- [x] **Right-click menus split by target** (2026-09-29, `menus.py`), each
      starting with a disabled bold header ("Subplot: <title>" / "Curve:
      <name>"). A right-click on a curve reaches the ViewBox, not the
      curve (`PlotCurveItem.mouseClickEvent` is left-button only), so the
      ViewBox's `raiseContextMenu` is wrapped: a hit on a curve
      (`_curve_at`: its `mouseShape`, or a scatter point) opens the curve
      menu, else pyqtgraph's own subplot menu. Subplot menu: View All
      (undoable), Copy/Paste Subplot, Paste Curve (enabled only when a
      curve is on the clipboard), Bring Subplot to Front / Send
      Subplot to Back, Toggle Legend, Reorder Curves..., Remove Average,
      FFT, Export to CSV, brushed-point actions, Delete/Rename Curve
      submenus. Curve menu: Copy/Paste Curve, Bring to Front / Send to
      Back, the four style submenus, Rename, Delete — no Toggle Legend.
      In Brush mode a right-click always opens the subplot menu (its
      brushed-point actions are the point there).
- [x] Edit a legend entry's name by clicking (double-click the legend label,
      or right-click → Rename Curve)
- [x] Edit a subplot's title by clicking (double-click it)
- [x] Edit a subplot's x/y-axis label by clicking (double-click it), *and*
      via dedicated "X Label"/"Y Label" toolbar buttons (same effect,
      discoverable without knowing the double-click gesture — useful right
      after adding a new, unlabeled subplot)
- [x] **All four of the above (title/axis-label/legend/annotation text)
      edit in place now, not via a popup** (2026-09-30, P8,
      `editable_text.py`): double-click opens a real caret-visible editor
      positioned over the text itself, showing the SOURCE markup; Enter
      commits, Shift+Enter inserts a line break (multi-line supported
      everywhere, including a growable title row), Esc cancels, clicking
      elsewhere commits — one undo entry per commit (title edits are now
      undoable at all, which they weren't before). **Rich text**: a small
      LaTeX-ish subset (`richtext.py`) translates to Qt rich text/Unicode
      — `\textbf{}`/`\textit{}`, `^{}`/`_{}` (braces required, so
      `sensor_1`/`_nolegend_` don't turn into subscripts), ~30 Greek
      letters, ~60 math symbols, `\textcolor{}{}` — deliberately **not**
      real LaTeX math (no fractions/integrals/matrices), no new
      dependency; an unrecognized token renders literally, never raises.
      The stored source string (not the rendered HTML) is what
      copy/paste and rename round-trip. **Right-click → Font...**
      (`QFontDialog` + a color button) on all four, undoable — including
      underline/strikeout (bug #25's fix: applied via
      `QTextCursor.mergeCharFormat`, since rich-text HTML doesn't let the
      base font supply that the way it does bold/italic/family/size).
      HTML export runs title/axis/legend/annotation text through the
      same translator (`to_plotly`) so the markup isn't shown literally
      in exported figures.
- [x] Toolbar with custom buttons. **Open-source cleanup (2026-10-01):**
      `icons/` originally held PNG/GIF files copied out of a MATLAB
      install (`plotpicker-*`, `tool_rotate_3d`, etc.) — not
      redistributable under this project's BSD-2 license. The 13 that
      were actually wired into the toolbar (pointer/hand/zoom-in/
      rotate-3d/data-brush/data-cursor/legend/text-box/link/pencil/fft/
      remove-average/home) were replaced with `lafigure/toolbar_icons.py`,
      small QPainter-drawn QIcons in the same style `toolbar.py`'s own
      pre-existing `_fit_icon`/`_hide_points_icon` already used (fft and
      remove-average deliberately got new, different-looking glyphs
      rather than redraws of the originals). All 53 original files
      (used and unused) now live in `icons/nonpublished-icons/`, which
      `.gitignore` excludes — nothing under `icons/` ships publicly
      except what `toolbar_icons.py` draws. `action()`/`menu_button()`
      in `toolbar.py` still accept a plain filename-in-`icons/` string
      too (for any future real icon asset someone has the rights to
      ship), but every built-in toolbar icon today is code-drawn. A few
      actions without a drawn icon keep a generic Qt fallback (Add
      Subplot, Delete, Undo, Redo, Grid Layout).
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
      writer, `_apply_mouse_enabled`: pan is off in Select and Brush modes.
      Before 2026-09-27, Brush and Link X only reached
      existing subplots, and turning Brush off re-enabled pan in Select mode.
- [x] Data brushing, generalized to every kind by WP-J (2026-09-28,
      superseding the two-hardcoded-scatter-subplots `LinkedScatter`/
      `SelectionModel` mechanism this bullet used to describe — both
      classes are deleted; see Phase 3 in the Roadmap below for the
      current design). `RectBrush` (`selection.py`) wires rectangular
      drag-select onto every subplot's `ViewBox`, only while Brush mode is
      on; hit-testing goes through `rows_in_rect`/a kind's `get_xy`, never
      the downsampled display. **The selection is rows of a `DataSource`**
      (or point positions for a plain-array series), pooled figure-wide
      via `LaFigure._brushers`/`_figure_brush_items` — so two series
      sharing a source (e.g. the demo's two scatter subplots, now built
      from one shared `DataSource`) link automatically, with no separate
      "linked" mechanism needed.

        **Brushing is a figure-wide concept, not per-subplot**: a plain
        (non-Shift) brush drag on any subplot unbrushes every other
        subplot's selection in the *same figure* first, then selects just
        what this drag caught. **Shift-held drag adds** to whatever's
        already brushed anywhere in the figure instead of clearing it
        (modifier read once, at drag-release, via `ev.modifiers()` —
        mirroring how pyqtgraph's own `ViewBox` reads Ctrl for its
        box-zoom). The right-click actions below act on the pooled
        figure-wide selection, not just the subplot you right-clicked.

        Selecting points enables six right-click actions (menus.py) on
        that selection: **Delete Selected Points**, **Transform Selected
        Points...** (an arbitrary `eval`'d numpy expression in `x`/`y`,
        restricted `__builtins__`), **Selection Stats...** (mean/std, per
        curve and pooled), **Fit Selected Points** (linear or degree-N
        polynomial, via `np.polyfit` on the pooled selection — overlays a
        new fit curve, + a `pg.TextItem` with the equation/R²), and (WP-J)
        **Hide Brushed Points** / **Show All Points** (also on the toolbar)
        — hides/restores the brushed rows on their `DataSource`, reaching
        every series of that source in every open figure, dataset left
        intact. All six go through undo/redo. On a `DataSource`-backed
        series, Transform and Remove Average (below) write a **new derived
        column** instead of overwriting; a plain-array series is still
        edited in place. Fit's overlay curve is a fresh `'line'` series,
        so it can itself be brushed/deleted/fit again like any other.
- [x] Right-click selection rules (the menus' contents: see "Right-click
      menus split by target" above). Right-clicking a subplot selects it, unless the
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
      **Zoom and pan are covered too** (2026-09-29, `view_ops.py`, "view
      history"): every mouse gesture on the scene is bracketed press →
      release by before/after range snapshots (an observe-only scene
      filter, closing one event-loop turn after the release, since
      pyqtgraph applies e.g. a rect zoom while handling it); a wheel burst
      is one entry (closed 400 ms after the last tick, or by undo/redo);
      Home/Fit/View All are wrapped explicitly. No entry if another entry
      was pushed during the gesture (a resize, a legend move — that was
      the gesture), nor for an axis auto-ranging before and after (a
      selection border resizing the view is not a zoom). **Not** covered
      (view/UI toggles): legend on/off, Link X, interaction mode, Grid
      Layout toggle.
- [x] Four interaction modes, exclusive toolbar toggle (Select is default;
      **Brush** joined the group 2026-09-29 — choosing any mode unchecks
      the others, and `toggle_brush(False)` returns to Select;
      `self.brushing` is derived from the mode):
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
        The cursor is a drawn magnifying-glass-with-"+" (`view_ops.
        _zoom_cursor`, 2026-09-29) — Qt has no built-in cursor shape for
        this, unlike Hand's `OpenHandCursor`, so it's a cached `QPixmap`
        painted once, wrapped in a `QCursor` with its hotspot at the
        lens's center (the point actually being zoomed into). During a
        right-drag (pyqtgraph's dynamic zoom/unzoom) an override cursor
        shows a lens with "±" and horizontal/vertical double arrows
        (`_zoom_drag_cursor`), restored on release.
      - **Brush**: left-drag brushes points (see Data brushing); pan off.
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
      each pushing one undo/redo entry. **Right-click styling menu**
      (replaced a single "Properties..." dialog in round 4, 2026-09-30 —
      see the Round 4 section below): individual Line Style / Line
      Width / Color... entries (Line Style/Width disabled for `text`,
      which has no stroke), plus Fill... for rect/ellipse, each applying
      to the whole annotation selection as one undo entry. A shape with
      an arrowhead (`arrow`/`doublearrow`/`textarrow`) also gets an
      **Arrow Style...** popup (head length/width/type —
      arrow/round/diamond/none — live-previewed, modeless, undoable as
      one entry on commit). `'border'`- and
      `'axes'`-anchored annotations are parented to the **subplot**
      (`PlotItem`), not the figure, so they travel along with
      `copy_subplot`/`paste_subplot` above (`'figure'`-anchored ones don't
      — they aren't any subplot's). Placed via one dropdown "Annotate"
      toolbar button listing 7 of the 8 shapes (data cursor excluded,
      2026-10-02 — see "Data Cursor mode" below): the `text` point kind
      places on a single click; every extent-having shape (rect, ellipse,
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
- [x] **Shift constrains annotation move/resize/rotate/placement**
      (2026-09-29), LibreOffice-Draw style — user-specified behavior, not a
      default: holding Shift while dragging a shape body, an end-point
      handle, a rotate handle, or while placing a new extent shape,
      constrains it. `rect`/`ellipse` become a screen-square/circle;
      every directional shape (`line`/`arrow`/`doublearrow`/`textarrow`,
      and `cursor`'s label line) snaps its angle to 45°; whole-body move
      (single or grouped) locks to a 45° screen direction; rotation snaps
      to 45° steps — the user's own explicit choice, even though real
      LibreOffice Draw's actual default rotation snap is 15°.
      `AnnotationItem.SHIFT_SNAP_DEG` (`annotations.py`) is the one place
      to change the step. The constraint is always computed in **scene
      (screen-pixel) space**, never local/data space — deliberate, so it
      looks the same on screen regardless of anchor (`figure`/`border`/
      `axes`) or a subplot's data scale; see `constrain_extent_vector`'s
      own docstring. Implementation: `AnnotationHandle`'s `on_move`
      callbacks (`handles.py`-built, wired in `AnnotationItem.__init__`)
      now pass the handle's live `.modifiers` through to
      `_on_endpoint_drag`/`_on_start_drag`/`_on_rotate_drag`, mirroring
      the pattern `ResizeHandle`/`MoveHandle` already used; whole-body
      drag reads `ev.modifiers()` directly in `mouseMoveEvent`. Covered
      by `tests/test_annotation_ops.py`'s `test_shift_*`/`test_plain_*`
      pairs (one shift-held, one unconstrained control, per gesture).
- [x] **A batch of annotation/curve-browser fixes and one small feature**
      (2026-09-29), scoped and confirmed with the user via `/lafigure-scope`
      before implementation, each independently tested:
      - **Tight, oriented selection outline for arrows** (`annotations.py`):
        `line`/`arrow`/`doublearrow`/`textarrow`'s dashed selection box, when
        selected, now hugs the p0→p1 segment at an angle
        (`AnnotationItem._selection_outline_geometry`) instead of the
        axis-aligned box of the two endpoints, which wasted visible space on
        a non-horizontal/vertical segment. `rect`/`ellipse`/`text`/`cursor`
        are unaffected (angle 0 — see the method's own docstring for why).
      - **Arrowheads no longer distort on an 'axes'-anchored subplot** whose
        X/Y data scale isn't 1:1: `_draw_arrowhead` (now an `AnnotationItem`
        method, not a free function) builds the triangle in SCENE
        (screen-pixel) space and maps it back to local coordinates, instead
        of computing it directly in local (data) space. `paint()` also now
        sets `QPainter.Antialiasing` (previously unset — visible on a
        diagonal line/rotated shape).
      - **Fixed: right-click on an annotation opened both its own menu and
        the subplot's (or, outside any subplot, the empty-space "Paste
        Subplot" menu)** — two independent right-click delivery paths
        (pyqtgraph's own click dispatch vs. Qt's native `contextMenuEvent`)
        both fired. New `_annotation_at(scene_pos)` hit-test
        (`annotation_ops.py`) guards both `menus.py`'s `raise_context_menu`
        and `selection_ui.py`'s `_on_scene_clicked` empty-space branch.
      - **New: "Link to subplot `<name>`" menu shortcuts.** An unlinked
        (`anchor='figure'`) annotation's own right-click menu now lists one
        direct-reparent action per subplot its own **un-rotated** bounding
        box overlaps (`_subplots_under_annotation`/
        `_link_annotation_to_subplot`, `annotation_ops.py`), alongside the
        existing precise "Link to..." click-to-choose gesture. Always
        reparents as `anchor='border'` (a bounding-box "covers this
        subplot" relationship is coarse — see the method's own docstring);
        `'axes'` anchoring is still reachable via the click gesture.
      - **New: annotations are copy/pastable**, including across figure
        windows, mirroring curve/subplot copy/paste: `Clipboard.annotation`
        (`clipboard.py`), `copy_annotation`/`paste_annotation`
        (`clip_ops.py`, added as `copy_selection`/`paste_selection`'s third
        dispatch tier — after curve, before the subplot fallback), and
        Copy/Paste Annotation entries on the right-click menu
        (`annotations.py`). A pasted annotation lands on the **focused**
        subplot (same convention as `paste_curve` — not necessarily the one
        it was copied from), offset `ANNOTATION_PASTE_OFFSET_PX` (20) scene
        pixels so a same-window paste doesn't land exactly on the original
        — computed in scene space and converted into the annotation's own
        parent frame (`_offset_pasted_annotation`), same approach the Shift
        move-constraint above uses. User-confirmed choice over an
        exact-position paste.
      - **Del in Brush mode now deletes the brushed points**
        (`clip_ops.py`'s `delete_selection`, one added branch at the top)
        instead of acting on `selected_plots`/`selected_curves`/
        `selected_annotations` — a different, usually-empty selection
        concept in that mode, so Del previously did nothing useful there.
      - **Fixed: renaming a curve via its legend didn't propagate.**
        `editable_text.py`'s `wire_legend_editable` used to only set the
        legend label's own displayed text, leaving `curve.opts['name']` (and
        hence everywhere else that reads it) untouched and the edit
        un-undoable. Now routes through `NamingMixin._apply_curve_rename`,
        the same path the curve menu's Rename already used — its signature
        gained `figure`/`plot_item` params; both call sites (`naming.py`,
        `view_ops.py`) updated.
      - **Fixed: the Curve Browser and the Figure Browser's "Show Curves"
        tree didn't live-update when a curve was added, deleted, or
        renamed** on an already-open subplot — only a whole-subplot add/
        remove/rename fired `registry.notify_subplots_changed`, which both
        browsers rebuild from (`manager.py`'s `_on_subplots_changed`). Now
        also fired from `series.py`'s `_add_series` (the one series-
        construction site) and `clip_ops.py`'s `delete_curve` (both its
        direct removal and redo's); the rename fix above already covers
        itself via `_apply_curve_rename`.
      - **Investigated, NOT reproduced: "Link X + resize changes a linked
        subplot's zoom."** Tried three real-drag reproductions — a
        subplot's own border-handle resize, a gutter (grid-line) drag
        resizing two subplots at once, and a whole-window resize — all via
        real `QMouseEvent`s / `figure.resize()`, all checking each linked
        `ViewBox.viewRange()` before/after. **All three passed cleanly**
        (`tests/test_layout.py`'s three `test_link_x_*` tests) — kept as
        regression coverage either way, but the reported mechanism wasn't
        observed in this environment across three plausible readings of
        "resizing a subplot." Per CLAUDE.md's own established practice for
        an unreproducible bug (see bug #5 below): don't guess a fix for a
        mechanism never actually observed — ask for the exact repro steps
        (which handle/gesture, with/without Alt, how many subplots linked)
        instead.
- [x] **A second batch: tighter/correct arrow outline, a scene-space
      geometry skill, Zoom-mode click behavior, and click-cycling**
      (2026-09-29), scoped via `/lafigure-scope` again, each independently
      tested:
      - **Arrow selection outline fixed twice over.** The oriented box
        added in the first batch (above) was itself still computed in
        LOCAL space (`math.atan2`/`hypot` on `p1_local`, then
        `painter.rotate()`) — same warping bug class as the arrowhead
        fix, just missed there. `AnnotationItem._selection_outline_polygon`
        (replacing `_selection_outline_geometry`) now builds all 4
        corners in SCENE space and maps them back, exactly like
        `_draw_arrowhead`; `paint()` now always `drawPolygon`s it, no more
        `painter.rotate()`. Also widened 1.5x perpendicular to the segment
        (`OUTLINE_PERP_PAD_PX = 6`, was the shared 4px `inset`) per an
        explicit request — `OUTLINE_END_PAD_PX` (along the segment) is
        unchanged.
      - **New skill: `lafigure-axes-geometry`**
        (`.claude/skills/lafigure-axes-geometry/SKILL.md`) — the general
        principle behind both the arrowhead and outline fixes: any
        angle/direction-dependent geometry on an `'axes'`-anchored item
        must be computed in scene space and mapped back, never computed
        directly in local (data) space, since the ViewBox's transform
        only preserves angles when X/Y data-per-pixel is 1:1 (the
        exception, not the rule). Documents a **known, NOT-yet-fixed**
        deeper gap found while fixing this: `AnnotationItem.setRotation()`
        itself (`rect`/`ellipse`/`text`'s rotate handle) applies rotation
        in local space too, so a rotated one on a non-square-scaled
        subplot likely also warps — bigger fix (the shape's own geometry,
        not a decoration), deliberately out of scope for this pass.
      - **Fixed: a click on an annotation in a non-Select mode (Zoom
        Rect, Hand, Brush) used to select/ready-to-drag it anyway** —
        `AnnotationItem.mousePressEvent` now also checks
        `self.figure.interaction_mode != 'select'` and ignores the press,
        letting it fall through to the ViewBox beneath (same double-
        dispatch class as the earlier double-context-menu bug).
      - **New: Zoom Rect mode's plain click zooms.** A click with no drag
        previously did nothing there. Now: click zooms in to 1/3 the
        current view (`ViewOpsMixin.CLICK_ZOOM_FACTOR = 3.0`), double-
        click zooms out to 3x — both centered on the **clicked data
        point** (re-derived from the *current* view mapping each time,
        not a fixed screen pixel — that point is the new view center
        after a zoom-in, by definition of a centered zoom), one undo
        entry each via the existing `_undoable_view_change`
        (`_click_zoom`, `view_ops.py`; dispatched from
        `_on_scene_clicked`, `selection_ui.py`). 3D cells are excluded
        (`axes_type == '3d'`; a `View3DBox` has no `viewRange()`/
        `setRange()` the same way).
      - **New: click-cycling through overlapping objects in Select
        mode.** Clicking (about) the same spot again — within
        `CLICK_CYCLE_TOLERANCE_PX` (4px) and `CLICK_CYCLE_TIMEOUT_S`
        (1.0s) of the previous plain click — steps to the next
        curve/annotation/subplot stacked there instead of re-selecting
        the same one, wrapping around; a click elsewhere (or a pause)
        resets to the top. User-specified scope: curves included from
        the start (the harder option — see below), state resets on
        distance-or-timeout (both confirmed via `/lafigure-scope`'s
        AskUserQuestion). `LaFigure._stacked_click_targets` (
        `selection_ui.py`) builds the ordered stack from the app's own
        existing hit-tests (`_curves_at` — `_curve_at`'s per-plot check,
        now factored out in `menus.py` so cycling can see the whole
        overlapping set, not just the topmost curve — and
        `_annotation_at`-style annotation containment, plus a subplot's
        own `ViewBox`), not Qt's raw item stack, so every target cycling
        can reach is one a normal click could reach too. Ordering
        approximates real render z-order (annotations first, any anchor
        — they're always zValue=800, above every subplot; then subplots
        by their own z, each contributing its curves then its own body)
        rather than perfectly replicating Qt's hit-testing.
        `_apply_click_cycle` (`selection_ui.py`) runs *after* ordinary
        click dispatch already selected something, and overrides it if
        this was a repeat — reusing the ordinary single-target selection
        setters (`_select_curve`/`_select_annotation`/`_on_plot_clicked`),
        never reimplementing selection itself. **One real architectural
        wrinkle, found only by testing with real Qt events (not a direct
        method call — see CLAUDE.md's own established lesson on this)**:
        an annotation's native `mousePressEvent`/`mouseReleaseEvent`
        (see CLAUDE.md's note on native-vs-pyqtgraph dispatch) fully
        consumes a click on it, so pyqtgraph's own `sigMouseClicked` —
        and hence `_on_scene_clicked`'s own tail call to
        `_apply_click_cycle` — never fires for it at all. Fixed by also
        calling `_apply_click_cycle` directly from
        `AnnotationItem.mouseReleaseEvent` (when nothing moved and Shift
        wasn't held) — the two call sites are mutually exclusive per
        click, confirmed live, not assumed.
- [x] **Data cursor overhaul** (2026-09-29), scoped via `/lafigure-scope`
      (two judgment calls confirmed with the user: re-picking the anchor
      stays on the SAME curve only, and 3D support was built in this same
      pass rather than split off):
      - **Oriented selection outline**: `'cursor'` joined
        `ORIENTED_OUTLINE_KINDS` (`annotations.py`) — its p0->p1_local
        (marker->label) segment gets the same tight, angle-hugging box as
        line/arrow, built in scene space per the `lafigure-axes-geometry`
        skill.
      - **The point stays pinned to a real sample, live** — never a
        frozen `(x, y)` baked in at placement time. A cursor now carries
        `point_ref` (`{'is_3d', 'curve_index', 'row'}`): `curve_index` is
        resolved fresh every time against its `parent_plot`'s CURRENT
        curve/series list (never a live object reference held across
        undo/redo, which would go stale — see the staleness lesson this
        file already had for a curve, item 7's annotations section);
        `row` is a `DataSource` row id for a source-backed series, or a
        plain array index for a private one.
        `AnnotationItem.refresh_point()` re-derives position + label text
        from it. A figure-wide, best-effort resync
        (`HistoryMixin._resync_cursor_points`) runs after every
        `_push_history`/`undo`/`redo` — so any undoable action (a value
        edit, Remove Average, Transform, undo/redo of any of them) moves
        the cursor along automatically, with no per-mutation-site wiring
        needed. This intentionally does NOT distinguish "hidden" from
        "still there" (both just mean "not currently drawn by this
        curve") and never purges on its own — see the next bullet for why
        that has to be separate.
      - **Deleting the cursor's own point removes the cursor too, as ONE
        undo entry with the delete** (`brushing.py`'s
        `_cursors_targeting` + `delete_brushed_points`, wrapped in
        `undo_group()`) — precise and explicit, unlike the position
        resync above: the underlying `DataSource` is never actually
        shrunk by a delete (only a series' own drawn `rows` narrows — see
        the class docstring above "Derived columns" in `brushing.py`), so
        there is no generic "does this row still exist" signal to hang a
        purge off; only the delete action itself, at the moment it
        removes an entry from THIS curve, can tell deleted from merely
        hidden. Hide Brushed Points / Show All never removes a cursor —
        confirmed by a dedicated test.
      - **3D**: a data cursor can now be placed on a 3D curve
        (`annotation_ops.py`'s `_nearest_3d_point`, reusing
        `View3DBox.projected`'s cached per-camera-state screen
        projection — the same one brushing already used, never computed
        twice), and follows the camera through orbit/pan/dolly
        (`View3DBox.render_now` calls a new `_refresh_axes_cursors` after
        every render, re-projecting any cursor it finds via
        `childGroup.childItems()` — not `addedItems`, CLAUDE.md item 17's
        own lesson on why). This is possible cheaply because an
        `'axes'`-anchored item on a 3D cell already lives in the rendered
        image's own pinned pixel space (view3d.py's module docstring), so
        "follow the camera" is just "re-read the cached projection every
        render" — no new coordinate system, no touching the deeper
        `setRotation()`-in-local-space gap the `lafigure-axes-geometry`
        skill documents as separately unfixed. The text includes Z
        (`datatip_text` grew an optional `z=` param). Building this also
        surfaced and fixed a real, independent, previously-uncaught bug
        — see item 20 below — where the four brushed-point actions
        (Delete included) silently never reached ANY 3D selection at all,
        one layer below where this feature needed them to.
      - **Drag behavior, made explicit**: only the label end (p1) does
        a free whole-shape-independent drag, exactly as before (p0 was
        never draggable at all until this pass). p0 itself now has its
        own handle (`AnnotationHandle._anchor_handle`, `annotations.py`)
        that, while dragged, re-picks WHICH sample on the SAME curve/
        series it's pinned to — never a different curve, even one whose
        point is screen-closer (`annotation_ops.py`'s
        `_nearest_sample_on_ref`, deliberately curve-scoped, per the
        user's own confirmed choice) — one undo entry per drag, only if
        the row actually changed. **Superseded by the Data Cursor mode
        pass below (2026-10-02)**: `_anchor_handle` (and the generic
        `_end_handle`) are gone for `'cursor'` — the same curve-scoped
        drag is still there, just driven by native hit-testing instead
        of a handle object, and Alt now lets it switch curves.
      - **The label's drag handle no longer masks the label text.**
        `AnnotationItem.END_HANDLE_PULLBACK` (0.7): the end handle sits
        70% of the way from p0 to the label point instead of exactly on
        it, where the label's own white text bubble is centered too.
        **Superseded by the Data Cursor mode pass below**: with no
        handle object left to mask the label, `END_HANDLE_PULLBACK`
        itself is gone too.
- [x] **Data Cursor mode** (2026-10-02), scoped via `/lafigure-scope`
      (four judgment calls confirmed with the user — see below): the
      toolbar's "Data Cursor" button is now a persistent, exclusive
      interaction mode (`toolbar.py`'s `cursor_action`, joins the same
      `mode_group` as Select/Hand/Zoom Rect/Rotate + Zoom/Brush; Brush's
      own 2026-09-29 precedent — "exclusive, not a one-shot" — applied
      here too), not a one-shot "Annotate" placement entry (removed from
      both the toolbar and `_handle_placement_click`'s `'cursor'`
      branch, now dead and deleted).
      - **Click-to-move/add** (`annotation_ops.py`'s
        `_handle_cursor_mode_click`, dispatched from `selection_ui.
        _on_scene_clicked`'s new `'cursor'`-mode branch, mirroring Zoom
        Rect's own click branch): a plain left click in a subplot's data
        area moves that **one subplot's own last datacursor**
        (`self._last_cursor_by_plot`, a `{plot_item: AnnotationItem}`
        map — **per-subplot, confirmed with the user**, not one
        figure-wide pointer) to the nearest curve point; Shift+click
        always adds a new one instead. **A plain click in a subplot
        with no datacursor yet creates one** (same as Shift — confirmed
        with the user), since there's nothing to move yet. Nearest-point
        search across every curve on the subplot
        (`_nearest_point_across_curves`: each curve's own nearest-X
        candidate, same convention `_nearest_sample_on_ref` already
        used, then ranked by true on-screen distance across curves) or,
        on a 3D cell, the pre-existing `_nearest_3d_point` (already
        cross-curve). `_track_last_cursor`/`_purge_annotation` keep the
        map correct across undo/redo of a create or delete.
      - **Datacursors are a distinct kind with special-cased UI**
        (`annotations.py`'s `AnnotationItem`, `kind == 'cursor'`), all
        working in **both** Select mode and Data Cursor mode (the
        user's own confirmed choice, over Select-mode-only like every
        other kind): no grab-handle objects at all (`_end_handle`/
        `_anchor_handle` removed from `__init__`); the round marker and
        the label's own bounding box are grabbed directly via native
        hit-testing (`_cursor_region_at`, device-pixel distance, so it
        works the same regardless of an `'axes'` anchor's data scale) in
        new `_cursor_mouse_press`/`_cursor_mouse_move`/
        `_cursor_mouse_release` methods, dispatched from the existing
        `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` overrides
        by an early `if self.kind == 'cursor':` branch. Marker drag
        without Alt stays on the same curve (`_nearest_sample_on_ref`,
        unchanged); **Alt switches to the nearest sample on a different
        curve** (`_nearest_sample_switch_curve`, new — excludes the
        current curve from `_nearest_point_across_curves`). Text drag
        repositions the label (Shift snaps the angle, same
        `constrain_extent_vector` every line-like shape already used).
        No whole-body drag on the connecting line (click there selects
        only) — unlike every other kind. Hover cursors
        (`hoverEnterEvent`/`hoverMoveEvent`/`_update_cursor_hover_cursor`):
        a crosshair over the marker, `SizeAllCursor` over the text,
        default elsewhere. Selection is **no dashed outline** — the
        line turns `SUBPLOT_FILIATION_COLOR` red instead
        (`paint()`'s `'cursor'` branch, guarded out of the generic
        dashed-outline block at the bottom of `paint()`). Right-click
        menu (`contextMenuEvent`'s new `is_cursor` branch): no Copy/
        Paste Annotation, no Link to.../Link-to-subplot shortcuts —
        instead **Add New Datacursor** (`_add_datacursor_near`: a
        nearest-real-sample snap `ANNOTATION_PASTE_OFFSET_PX` scene
        pixels away, confirmed with the user over an exact-position
        copy or a frozen offset — reusing the Paste Annotation offset
        convention so position/point_ref never drift apart); Line
        Style/Width/Color/Font... all stay (not called out for
        removal). Del still deletes a selected datacursor in either
        mode — `delete_selection`/`delete_annotation` are mode-agnostic
        already, so this needed no new code.
      - `menus.py`/`handles.py` untouched (out of scope, confirmed in
        the scope proposal): the cursor-kind menu lives entirely in
        `AnnotationItem.contextMenuEvent`, and the marker/text grab uses
        native hit-testing rather than a new `AnnotationHandle`
        subclass.
- [x] **Debug mode** (2026-09-30, `lafigure/debug.py`): `lafigure.
      enable_debug_mode(log_path=None) -> str` configures the root
      `'lafigure'` logger (every `logging.getLogger('lafigure.<module>')`
      child is affected for free — no import needed from `debug.py`
      itself) to write DEBUG-level, human-readable lines to one fixed
      log file (`lafigure_debug.log` by default, overwritten every run —
      a user's deliberate choice over a timestamped-per-run file) and to
      stderr. Also enables `faulthandler` (writes to the same file — the
      one thing that can leave any trace of a native crash with **no**
      Python traceback at all, exactly bug #24's class), wraps
      `sys.excepthook` (logs, then still chains to whatever hook was
      installed), and bridges Qt's own C++-side warnings via
      `qInstallMessageHandler`. Idempotent (a second call replaces
      handlers rather than stacking them). Every example script under
      `examples/` calls it automatically and prints the log path, so
      running any of them produces something a user can copy/paste back
      for a bug report. On top of the crash-safety foundation, three
      more modules log at their own central choke points: interaction-
      mode changes and every undo/redo push/run (`view_ops.py`/
      `history.py`), click/selection dispatch — gesture, what was hit,
      the resulting selection (`selection_ui.py`), and brush-drag/
      annotation-placement gesture start/end (`brushing.py`/
      `annotation_ops.py`).

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
- [x] **Subplot right-click menu slimmed down**: remove pyqtgraph's
      "Export..." (export becomes the figure-wide toolbar Save, Phase 4),
      "X axis", "Y axis" and "Mouse Mode"; add **"Export to CSV..."** (the
      subplot's curves, full data); the brushed-point actions (Delete /
      Transform / Fit Selected Points, and Selection Stats with them) are
      **shown only while Brush mode is on**, and **disabled when no point
      is brushed**. **Built by WP-B** (2026-09-28, `menus.py`).

### Phase 1 — free layout on a fractional grid (replaces QGraphicsGridLayout)
**Built by WP-A** (2026-09-28, `lafigure/grid.py`, `lafigure/layout.py`) —
every bullet below verified against the shipped code and its tests, not
assumed. (This whole roadmap section's checkboxes went un-ticked for
several sessions after WP-A actually merged — caught and fixed in this
pass; a reminder that "done" here means confirmed against code, not
against memory of having launched the package.)
- [x] Dropped `QGraphicsGridLayout` entirely. Subplots are positioned
      directly (`setGeometry`/box math), recomputed on window resize. The
      float/placeholder/reattach code, stretch factors, the private
      `GraphicsLayout.layout` access, and the bug #5 guard are all gone —
      see "The one thing to internalize" section below, now historical.
- [x] Figure owns a **grid**: column and row boundaries as figure
      fractions (`self.grid_cols`/`grid_rows`). Every subplot edge is a
      **fractional grid coordinate** (`self.boxes[plot_item] = (left, top,
      right, bottom)`; `left=1.5` = halfway between column lines 1 and 2),
      mapped piecewise-linearly through the boundaries (`grid.py`). Spans
      = integer ranges > 1; free sizes and insets = any fraction. Dragging
      a grid line rescales every edge referencing it, insets included.
- [x] Positions are the subplot's **outer box** (axes/labels included),
      per the user's explicit choice over MATLAB's inner data-area
      Position. "Align data areas" not built (may come later).
- [x] Overlap allowed; per-subplot z-order via `self.z_order`,
      `bring_to_front`/`send_to_back` (also on the subplot's right-click
      menu, WP-A's diff to `menus.py`); a subplot above another gets an
      opaque background.
- [x] Select mode: drag a **gutter on a grid line** (a `GutterHandle`,
      `handles.py`) = move that row/column line, rescaling every attached
      edge; drag a selected subplot's border/corner handle = resize that
      subplot only; drag its move handle = move it; **Ctrl+drop onto
      another subplot = swap** (plain drop just moves).
- [x] **Magnetic sub-grid shown only during a drag** (`SnapGuides`): snaps
      to grid lines, cell subdivisions (`self.snap_subdivisions`, default
      halves), other subplots' edges, and figure margins; `SNAP_PX = 8`;
      **Alt** disables snapping.
- [x] Mouse cursor changes on hover in Select mode: split cursors over
      draggable gutters, resize cursors over handles, move cursor over the
      move handle.
- [x] Gutter right-click: insert/delete row/column, equalize
      rows/columns. Add Subplot fills the first empty cell, else appends a
      row. Delete leaves a hole, never shifts (bug #1's lesson).
- [x] **FFT → subplot** adds a new grid row right under the time plot's
      row (`insert_subplot_below`); the result is an ordinary, freely
      movable subplot, undo/redo included.
- [x] Layout changes (move/resize/swap/grid-line drag, insert/delete/
      equalize a track) **go through undo** — a layout snapshot is just a
      few numbers.
- [x] `'border'` annotation offset is a fraction of the subplot box
      (`_box_fraction`/`_box_point`, applied via WP-A's diff to
      `annotation_ops.py`/`annotations.py`), fixing Annotations
      simplification #5.
- [x] **"?" toolbar button**: popup with explained controls (mouse/keys
      per mode), version, and credits. **Built by WP-C** (2026-09-28,
      `lafigure/help.py`).

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
      `rows_in_rect`/`show_rows` (+ `brush_bins` for histogram-style
      linking) were built by WP-J, in `selection.py` rather than as
      `SeriesKind` methods proper (J didn't own `series.py` either) — see
      Phase 3 below. `to_plotly` and true click-selection for a
      non-`PlotDataItem` kind are still **not yet built** (M and a future
      package, respectively). **19 more kinds built in round 4**
      (2026-09-30) — `loglog`/`semilogx`/`semilogy`, `boxchart`/
      `violinplot`, `polar`/`polarhistogram`/`piechart`, `bubblechart`/
      `swarmchart`/`binscatter`/`spy`, `quiver`/`feather`/`contour`,
      `barh`/`stem`/`heatmap`/`errorband`, `plot3`/`bubblechart3d` — see
      the dedicated **Round 4** section below for what each one draws,
      its capabilities, and known gaps; every one delegates to an
      existing kind (`line`/`scatter`/`bar`/`imshow`/`line3d`) or to the
      shared `lafigure/kinds/_base.py` rather than building a from-scratch
      item, per that round's own explicit requirement.
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
- [x] **Curve browser tab** (`manager.py`'s second tab, WP-D's
      placeholder filled in by **WP-K2**, 2026-09-28): shows only the
      **focused subplot**'s series/groups/annotations as a tree, following
      focus live (its own small "most recently used figure" tracker,
      reimplementing `axes.py`'s `gcf()` pattern locally rather than
      editing that file). A grouped member shows `group.display_name`,
      never its raw name. Tristate visibility checkbox per row; right-click
      Delete (+ "Edit common label..." on a group row — Copy/Paste a group
      is **not built**, since there's no single-group clipboard concept
      today and adding one needs `clipboard.py`/`clip_ops.py`, neither
      owned by K2 — reported, not guessed at). Selection synced both ways
      with the figure. Bottom editor: name, Z order (front/back via
      `item.setZValue` — verified live that this actually changes real
      on-screen stacking order, not assumed; "drag rows to reorder" not
      implemented, only the front/back buttons), color, line width, line
      style, marker (gated by `Series.kind`, not by `item.opts` key
      presence — see the lesson after bug #15: a `PlotDataItem`
      pre-populates `opts['symbol']` etc. to `None` regardless of what was
      actually plotted, so key presence alone can't tell you what kind of
      series it is), alpha. Property edits are undoable; visibility
      checkboxes are view state (not undo). An `AnnotationItem` row shows
      no editor controls yet (only Delete) — its own right-click
      "Properties…" in the figure itself still covers full editing.
      **Two top-level categories, "Curves" and "Annotations"** (2026-09-29,
      P5), each with its own tristate checkbox (unchecking it hides every
      descendant recursively through groups; checking one child while its
      category is unchecked re-checks the category — same True/False/None
      convention `Group.visible` already used). Tree row order stays
      creation order (a deliberate decision, so groups stay visually
      grouped — z-order drives the legend only, not this tree). Also
      fixed the same day: the tree could go stale after re-clicking an
      already-focused subplot (`focused_plot`'s setter only fires
      `registry.focusChanged` on an actual change) — an app-wide mouse-
      press event filter now touches the "most recently active figure"
      tracker on every real click, independent of whether `focused_plot`
      itself changed.
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
      **Built by WP-K1** (2026-09-28) — data model + Ctrl+G/Ctrl+Shift+G;
      grouped-annotation move/select-together already existed (multi-
      select) and needs no group-specific code. Copy/paste of a subplot
      now carries its groups too (`clip_ops.py`'s hook, applied by the
      coordinator after WP-J — see Phase 3 above).
- [x] Group **common label**: `Group.display_name(member)` (WP-K1) shown
      in the Curve browser tree for every grouped member; the prefix/
      suffix position toggle lives in the bottom editor when a group row
      is selected, and the group-node right-click menu has Edit common
      label / Delete (**Copy/Paste a group is not built** — see the Curve
      browser tab bullet above).

### Phase 3 — brushing/linking on every kind
**Built by WP-J** (2026-09-28, `lafigure/selection.py`, `brushing.py`).
- [x] Brushing works on any kind via `rows_in_rect`/`show_rows`; histogram
      bars ↔ time-series points through a per-row bin index
      (`np.digitize` once); brushed bars show a stacked partial bar. The
      protocol lives in `selection.py` (module-level functions, since J
      couldn't edit `series.py`), with a default that covers any kind
      whose `get_xy` returns two parallel 1-D arrays (line, scatter,
      stairs, area, errorbar) for free; a kind opts into brushing via
      `'brush' in capabilities` and, for histogram-style linking, a
      `kind.brush_bins(item, series) -> (values, edges[, heights])`
      method. **I1's `hist` kind doesn't define `brush_bins` yet** — its
      bars brush nothing (harmlessly) until it does; a real TODO, not a
      bug.
- [x] **Near-zero overhead when off**: no masks, overlays or connections
      until the Brush toggle is on (`RectBrush` only wraps the ViewBox
      drag handler while Brush is on); selection = one sorted row array
      per `DataSource` (or per item for a plain-array series); hit-test
      on full data via `get_xy`, never the downsampled display. Verified
      by a test that a million-row series with Brush off allocates/wraps/
      connects nothing.
- [x] Generalizes and replaces `SelectionModel`/`LinkedScatter` and the
      hardcoded `scatter1`/`scatter2` — **both classes deleted** from
      `selection.py` (nothing referenced them once the demo moved to a
      shared `DataSource`); the demo's two scatter subplots are now two
      ordinary `ax.scatter(source, x=, y=)` series of one `DataSource`,
      linked by construction like any other pair sharing a source.
- [x] **Dataset stays intact.** Figure menu/toolbar action **"Hide
      Brushed Points"** (+ **"Show All Points"**): marks brushed rows on
      the source via `DataSource.hide_rows`; every series of that source,
      in every open figure, stops drawing them; a hidden series' full
      data survives a value edit made while hidden. Undoable.
- [x] Transform / Remove Average / FFT write a **new derived column**
      (revertible), never overwrite source data — **only for a series
      backed by a real (non-private) `DataSource`**; a plain-array series
      is still edited in place (nothing else could read a private source
      anyway). FFT's output rows don't line up with the input's (frequency
      bins vs. time samples), so an FFT'd source-backed series gets its
      own fresh `DataSource` instead of a derived column.
- [x] Pasted series (incl. across figure windows) **stay linked** to their
      source — confirmed true since WP-H; `clip_ops.py`'s copy/paste (and
      delete/undo) now go through `_series_full_dict`/`_add_series_restoring`
      (not bare `to_dict`/`_add_series_from_dict`) so a pasted or
      undo-restored series also keeps its not-currently-drawn rows and
      stays hidden if they were hidden.
- [x] **Groups also carry through subplot copy/paste** (coordinator
      addition, closing the gap WP-K1 reported and couldn't fix itself,
      since `clip_ops.py` wasn't K1's to edit): `copy_subplot`/
      `paste_subplot` now call `Group.to_dict`/`groups_from_dict`
      (`groups.py`) right after rebuilding a subplot's series and
      annotations, and the paste's own undo/redo removes/restores the
      carried groups along with the subplot.

### Phase 4 — Save / export
- [x] Save button, **leftmost** in the toolbar (+ Ctrl+S): choose any of
      PNG / JPG / HTML (+ SVG / PDF); several formats at once, same base
      name. **Built by WP-E** (2026-09-28, `lafigure/export.py`), with
      `'html'` added by WP-M below.
- [x] Header info text (source, date, user, custom `fig.info` keys) from a
      customizable format template (`{date:%Y-%m-%d}` …), remembered in
      `QSettings`. **Word-style print preview**: the user edits the text
      and its placement on a preview, then exports when satisfied. Built
      by WP-E.
- [x] HTML via plotly (optional dependency, lazily imported so `import
      lafigure` never needs it): subplots placed by absolute `domain`
      (exact for free layout/insets, via `grid.to_frac` — the same math
      `layout.py` itself uses), WebGL (`Scattergl`) traces for point-cloud
      kinds, annotations as plotly shapes/annotations (a rotated
      rect/ellipse degrades to unrotated — plotly shapes don't support
      arbitrary rotation; noted, not silent), source metadata in
      `customdata` so hover datatips work in the browser (`ax.datatip`
      format strings translate directly to a plotly `hovertemplate`; a
      Python callable can't run in static HTML, so it falls back to a
      generic x/y + every column hover), hidden rows excluded (recomputed
      at export time from `source.visible_rows`, independent of whether
      `console.watch_source` was ever armed). **Built by WP-M** (2026-09-28,
      `lafigure/html_export.py`) — a small `{kind_name: converter}` dict
      there (not a `SeriesKind.to_plotly` hook — `series.py` isn't M's to
      edit), covering every built-in kind, with a generic `Scattergl`
      fallback for an unrecognized future kind. Linked brushing in the
      HTML is still a later extra, not attempted. Controls (WP-N) export
      as their current state only — n/a today since nothing wires a
      control panel into a figure yet.
- [x] Too-large HTML: a **popup asks**: keep all / decimate 1:N (N
      editable, default 10, a `QSpinBox`) / peak-preserving decimation
      (same look — a plain-numpy per-bucket min/max, mirroring what
      `setDownsampling(method='peak')` does for the live display).
      Triggers per-series above `MAX_POINTS_PER_SERIES` (200,000, a named
      constant); applies only to point-cloud-shaped kinds (`line`,
      `scatter`, `area`, `bar`, `errorbar` — not `stairs`/`hist`, whose
      edges/values arrays have a different-by-one length, or `imshow`, a
      2D image).

### Phase 5 — interactive controls + reactive tables
**Built by WP-N** (2026-09-28, `lafigure/controls.py`), fully standalone
-- no edits needed anywhere else in the package.
- [x] Buttons, sliders, dropdowns, checkboxes with user Python callbacks
      (e.g. drive `src.filter`), and editable tables: `table(fn,
      depends_on=[src])` (`fn()` returns `{column_name: sequence}`,
      matching `DataSource`'s own shape) recomputes on any dependency's
      `on_change` (filter / hide/show / add_column).
- [x] Controls live **in a separate figure window**
      (`ControlPanelWindow`/`open_control_panel(figure=None)`) — built
      and tested. **In grid cells**: `ControlPanel` itself is already
      layout-agnostic (a plain `QWidget`, no figure/scene dependency), so
      it's ready to embed, but the actual grid-cell integration is **not
      yet wired** — that needs a `layout.py` change (`axes_type=
      'controls'`, wrapping `ControlPanel` in a `QGraphicsProxyWidget`)
      that WP-N didn't own; the proposed hook is written up in
      `controls.py`'s own module docstring for whoever picks it up next
      (O, or a later pass, since O now owns `layout.py`).
- [x] Slider callbacks debounced (~50 ms, single-shot `QTimer` restarted
      on each change); a failing callback (including a `table`'s `fn`) is
      caught and its traceback shown in the status bar/label, never
      crashes; nothing in `controls.py` ever calls `_push_history` itself
      — control-driven changes are view state (a callback that itself
      edits a `Series` and wants undo, e.g. via `Series.set_data`, still
      gets it — that's the callback's own business, not the framework's).

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
- [x] `axes_type='3d'`: `scatter3d`, `line3d`, `surface`; brushing via
      camera-matrix projection in numpy → rows (links with 2D plots).
      **Built by WP-O** (2026-09-28, `lafigure/view3d.py`,
      `lafigure/kinds/{scatter3d,line3d,surface}.py`). A 3D cell is still
      the one `pg.PlotItem` `add_subplot` builds (2D axes hidden, its
      `ViewBox` replaced with `View3DBox`) — so box/z-order/move/resize/
      select/copy/delete/undo, all already generic in `layout.py`, work
      on it unchanged; only its own mouse handling (orbit/pan/dolly, Hand/
      Zoom-Rect mode only) and its offscreen-render-to-pixmap are new.
      **Real GPU rendering confirmed working** (RTX 4070 SUPER, GL 4.6;
      ≈1ms/frame at 1M points, matching the spike's estimate) — verified
      via a child process on the native platform, since `QT_QPA_PLATFORM=
      offscreen` still has no GL at all here (bug #10); a `QPainter`
      fallback (same projection, drawn on the CPU) covers the offscreen
      test suite and any environment with no GL context. Brushing reuses
      WP-J's `rows_in_rect`/`show_rows` protocol via the kind's own hooks
      — no change needed to `selection.py`/`brushing.py`; a rectangle
      brushed on a 3D view links to the same `DataSource` rows on a 2D
      plot and back. `Series.source`'s plain-array path (`series.py`) and
      `_apply_link_x` (a 3D cell's view is its own pixels, never a Link X
      reference or follower — `view_ops.py`) both needed small coordinator
      diffs, applied and covered by new tests. **Known gaps**: a 3D
      series isn't click-selectable (no `.curve`, same as bar/imshow);
      the four brushed-point right-click actions (Delete/Transform/Stats/
      Fit) skip 3D series; annotations anchored to a 3D cell's axes don't
      follow the camera; brushing ignores occlusion (ray/rect-tests every
      point, not just the frontmost); the fallback draws one flat color
      per primitive with no depth buffer, and a `surface` over ~20k
      triangles falls back to vertices only. `PyOpenGL` itself was never
      installed — the renderer uses PyQt5's own raw GL bindings, per the
      spike's own approach.

## Round 4 — new plot kinds, colorbar, 3D modes, styling (2026-09-30)

A second user-driven push after the roadmap above (WP-00 through WP-O)
was already fully merged. Delivered as waves of parallel worker agents,
same pattern as the roadmap; full execution plan, file ownership and
package briefs are in `PLAN.md`'s own "Round 4" section — this is the
durable summary. Explicit requirement across every new kind: **reuse an
existing kind or the shared base, never a from-scratch item** — every
kind below delegates to `line`/`scatter`/`bar`/`imshow`/`line3d` or to
`lafigure/kinds/_base.py` (new: `CompositeSeriesItem`, `DerivedKind`,
plus `categories`/`jitter`/`value_colors`/`size_scale`/`quantiles`/
`kde`/`bin2d` helpers shared by several kinds below). Full suite: 746
tests, green.

### 19 new SeriesKinds

- **Log kinds** (`loglog`, `semilogx`, `semilogy`, `log_kinds.py`):
  `DerivedKind` on `'line'` — a plain `pg.PlotDataItem`, `setup()` just
  calls `PlotItem.setLogMode(log_x, log_y)`. **Log mode is a
  SUBPLOT-wide pyqtgraph setting, not per-series** — calling
  `semilogy` after `loglog` on the same subplot overwrites the axis
  mode. Non-positive values aren't dropped from the raw data, only the
  *displayed* mapped value becomes NaN (a gap in the curve).
- **Distribution kinds** (`boxchart`, `violinplot`, `kinds/{box,violin}
  chart.py`): each a single composite item, one box/violin per category
  code (`_base.categories`), `{'copy'}` only — **not click-selectable**
  (no `.curve`). `boxchart` draws whiskers/box/median/outliers (Tukey
  1.5×IQR via `_base.quantiles`); `violinplot` draws a mirrored KDE
  outline (`_base.kde`, plain-numpy Gaussian KDE, Silverman bandwidth)
  normalized to its own peak. Both round-trip through the *original*
  category labels, not codes.
- **Polar family** (`polar`, `polarhistogram`, `piechart`,
  `kinds/_polar_base.py` + their own files) — **confirmed decision: no
  new `axes_type`**; each draws on an ordinary cartesian `PlotItem`
  with hidden axes and a locked 1:1 aspect (`setup_polar_axes`).
  `polar` is a `DerivedKind` on `'line'` (real `PlotDataItem`,
  cartesian-converted via `polar_to_xy`; capabilities narrowed to
  `{'brush','copy'}` — FFT/Remove Average/Fit judged not meaningful on
  a polar projection); it draws/grows a shared radial-ring +
  angular-spoke grid (`draw_polar_grid`/`grow_polar_grid`, cached on
  `plot_item._lafigure_polar_grid`). `polarhistogram` and `piechart`
  are each a single composite wedge-path item, `{'copy'}` only, not
  brushable (no per-point identity in a wedge); `piechart` skips the
  radial grid (nothing to annotate) and draws its own label+percentage
  text per slice from a qualitative color cycle.
- **Scatter-derived kinds** (`bubblechart`, `swarmchart`, `binscatter`,
  `spy`) — all delegate their actual drawing to `SERIES_KINDS['scatter'
  ].create(...)`, so they get a real `PlotDataItem`/`ScatterPlotItem`,
  `{'brush','copy'}`, for free:
  - `bubblechart`: `size=`/`color=` columns map to exact per-point
    `symbolSize`/`symbolBrush` (`_base.size_scale`/`value_colors`); a
    colorbar attaches only when `color=` is given.
  - `swarmchart`: jitters X position by category (`_base.jitter`,
    seeded `np.random.default_rng` — `to_dict` stores the RAW category
    + seed so copy/paste re-derives the identical jitter, not frozen
    positions); sets category tick labels.
  - `binscatter`: one colored point per non-empty 2-D histogram bin
    (`_base.bin2d`) — deliberately NOT an `ImageItem`, so it stays
    click-selectable/brushable; round-trips the raw (x,y) samples, so
    brush/delete acts on bin centers and can't trace back to originals
    (documented, non-recoverable).
  - `spy` (MATLAB's `spy(matrix)`): plots nonzero `(col,row)` positions
    of a 2-D matrix, `invertY(True)` to match `imshow`'s row-0-at-top
    convention; only the nonzero PATTERN round-trips, not cell values.
- **Field kinds** (`quiver`, `feather`, `contour`, `kinds/{quiver,
  feather,contour}.py`) — `{'copy'}` only, not click-selectable:
  - `quiver`: one composite item, a shaft + filled triangular arrowhead
    per sample; autoscales so the longest arrow is `fraction` (default
    0.15) of the data's bounding-box diagonal unless `scale=` is given
    explicit. Arrowhead built in SCENE space then mapped back (mirrors
    `AnnotationItem._draw_arrowhead`, duplicated not shared, per the
    `lafigure-axes-geometry` skill).
  - `feather`: `QuiverKind` subclass — every arrow's tail pinned to
    `(x[i], 0)` (MATLAB `feather()` convention), reuses quiver's
    autoscale/arrowhead machinery.
  - `contour`: **marching squares from scratch in plain numpy — no
    scipy/skimage**, per the round's own constraint
    (`marching_squares(matrix, level)`, standalone and independently
    testable; resolves the 4-crossing "saddle" case via the cell's mean
    corner value). Draws one independent line-segment set per level
    (not stitched into continuous polylines — same visual result since
    adjacent cells share exact edge points). Grid-index coordinates
    (`matrix[row,col]`), **not** Y-inverted like `imshow` — a `contour`
    over the same array as an `imshow` needs an explicit flip to align.
    `Series.set_data` is a documented no-op (the real data is the 2-D
    matrix).
- **`barh`/`stem`/`heatmap`/`errorband`** (`kinds/{barh,stem,heatmap,
  errorband}.py`):
  - `barh`: `DerivedKind` on `'bar'` but fully overrides `create`/
    `to_dict`/`get_xy`/`set_xy` to swap axis roles on the same
    `BarGraphItem`; category ticks go on the left axis via its own
    code path (not shared with `bar.py`'s bottom-axis version —
    documented duplication).
  - `stem`: plain `SeriesKind` (not derived), one composite item per
    series (vertical line + tip marker) — deliberately ONE item, not a
    line+scatter pair, to avoid the companion-item orphan-on-delete gap
    `errorbar.py` already has. Marker size is constant SCREEN pixels
    (`pixelWidth()`/`pixelHeight()`), not data units.
  - `heatmap`: `DerivedKind` on `'imshow'` — inherits everything
    (colorbar included) except `setup()`, which places the image via
    `x_coords=`/`y_coords=` (not `x=`/`y=`, reserved by `Axes._plot_kind`
    for source-column selection) using only their first/last values —
    non-uniform spacing isn't modeled pixel-by-pixel.
  - `errorband`: TWO real `PlotDataItem`s — a center line plus a
    transparent-filled polygon band (`fillLevel='enclosed'`, alpha-0
    pen per bug #15's lesson, never `pen=None`), kept in lockstep via
    `item._lafigure_band`. **Same orphan-on-delete gap as
    `errorbar.py`**: `clip_ops.py`'s `delete_curve` only knows the
    primary item, so deleting an errorband leaves its shaded region on
    the plot (flagged, not fixed — `clip_ops.py` wasn't this package's
    file to own).
- **3D kinds** (`plot3`, `bubblechart3d`, `kinds/{plot3,bubblechart3d}
  .py`), 3D-cell only (`axes_type='3d'`):
  - `plot3`: a pure `DerivedKind` alias of `'line3d'` — adds nothing,
    exists only so `ax.plot3(x, y, z=z)` matches MATLAB's name.
  - `bubblechart3d`: per-point size is **degraded, not exact** — the
    3D renderer supports only one point size per GL draw call (or one
    pen width in the `QPainter` fallback), unlike 2D scatter's free
    per-point size. Buckets sizes into up to 6 discrete groups
    (`_base.size_scale`, area-proportional), each its own GL primitive.
    Sizes are pre-scaled once at construction from the full raw array
    (stable under Hide Brushed Points); a later full position
    replacement via `Series.set_data` can desync sizes from positions —
    a known, unexercised limitation.

None of the above except `bubblechart`/`swarmchart`/`binscatter`/`spy`/
`polar` claim `'brush'`; none have an HTML/plotly export converter yet
(falls back to a generic Scattergl, losing size/color/shape — same gap
Phase 4's HTML export already had for any future unrecognized kind).

### `lafigure.plotmatrix(data, columns=None, figure=None, kind='scatter', diagonal='hist')`

New top-level function (`lafigure/plotmatrix.py`), not a `SeriesKind`.
Builds an N×N grid of `Axes` from one shared `DataSource` — `data` can
be a `DataSource` directly, a dict of columns, or a 2-D array (`columns=`
names the variables). Off-diagonal cell `(row, col)` is
`ax.<kind>(source, x=columns[col], y=columns[row])`; diagonal cells are
`ax.hist(source, x=columns[i])` (or left empty if `diagonal=None`).
Labels only the outer edge, MATLAB/pandas style. **Every cell is built
from the SAME `DataSource`** — deliberately, so brushing a rectangle on
one cell highlights the same rows on every other cell for free, through
the pre-existing source-keyed brushing machinery; `plotmatrix.py` itself
has no bespoke linking code. Returns the flat, row-major list of `Axes`.

### Interactive colorbar (R4-CBAR, `lafigure/colorbar.py`)

A colorbar's axis spans a *display range* covering both the data's
min/max and both movable limit values. Two FIXED, non-draggable dashed
lines mark the data min/max, refreshed live when the underlying data
changes. Two movable limit lines control the actual color mapping;
dragging one changes only that limit's *value* — the untouched limit
keeps its value and only moves in *pixels* if the display range has to
grow to keep showing it. Used by `imshow`/`heatmap` (already had a
colorbar pre-round-4) and now also `bubblechart` (conditional on
`color=`) and `binscatter` (always).

### 3D interaction modes (R4-3D)

A new **"Rotate + Zoom"** toolbar mode, to the right of Zoom Rect,
holding the pre-round-4 3D camera behavior (orbit/pan/dolly) — greyed
out unless the focused subplot is 3D. **Zoom Rect on a 3D cell is now a
real drag-a-rectangle zoom** (previously 3D cells only supported
Rotate+Zoom-style camera moves). A 3D subplot's right-click menu gained
a "Camera View" submenu (X-Y, X-Z, Y-Z, Sideway presets) and a
"Projection" submenu (Perspective/Orthographic), and lost FFT (never
meaningful on a 3D scene). Also
added, cross-cutting: a subplot-menu **"Scale"** submenu (X/Y:
Linear/Log), undoable — so an existing 2D plot can be switched to log
mode without rebuilding it as `loglog`/`semilogx`/`semilogy`.

### Figure-browser tree focus-on-click (R4-TREE)

Clicking a row in the Figure Manager's figure-browser tree now also
sets that figure's `focused_plot` to the clicked subplot (previously
the tree only showed/edited state, never drove focus) — so toolbar
actions and the Curve Browser tab immediately target the subplot you
just clicked in the tree, not whatever was last clicked in the figure
itself.

### Annotation and area styling

Covered under the **Annotations** and curve-style bullets in the
feature list above (search "round 4" there) — not repeated here.

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
5. ~~A `'border'`-anchored annotation's offset is a raw scene-pixel
   offset that doesn't rescale with its subplot.~~ **Fixed by WP-A
   (2026-09-28):** `anchor_offset` is now a fraction of the subplot box
   (`_box_fraction`/`_box_point`), so it follows a resize.
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

### 14. A pyqtgraph drag reports `isStart()` on the first *move*, not the press

**Symptom (found by WP-J, 2026-09-28):** a brush-select rectangle
consistently caught fewer points than the drawn rectangle actually
covered — about 12% fewer in one repeatable case — even though the
rectangle was visually drawn correctly on screen.

**Root cause:** the brush drag handler anchored the selection rectangle's
origin at `ev.pos()` read on the event where `ev.isStart()` is `True`.
pyqtgraph's `MouseDragEvent.isStart()` fires on the *first move* of the
drag, not the press itself — by then the cursor has already moved away
from the actual press point, so `ev.pos()` at that moment is not where the
drag began. The existing test's tolerance (±0.2 data units) was loose
enough to hide the resulting ~12% miss rate rather than fail outright.

**Lesson:** this is the same family as bug #11 (a Qt/pyqtgraph object's
field doesn't hold the value its name suggests) — don't assume an
event's "start" flag lines up with the coordinate at the true gesture
origin; use `ev.buttonDownPos()` (or the equivalent "where the button
actually went down" accessor) for the anchor, and verify with a tight
tolerance, not a loose one that can silently absorb a real miss.

### 15. `setPen(None)` on a `PlotDataItem` does not mean "no line" — and a kind's own `create()` may not treat `pen=None` as "none" either

**Symptom (found by WP-J, 2026-09-28):** the demo's scatter-style dots
had a faint gray line connecting them in a real screenshot, though no
test caught it (an invisible-line property was never asserted against a
rendered pixel).

**Root cause:** two compounding issues, both about what `pen=None` really
means at different layers.
1. `PlotDataItem.setPen(None)` stores a `NoPen`-styled `QPen` for the
   *item's own* pen state — same family as bug #7/#8 (`setBorder(None)`,
   `rbScaleBox`) — but was applied *after* the item had already been
   built via `_add_series(..., 'line', ...)` with `pen=None` passed
   through to `LineKind.create`, which (by design, see its own docstring)
   reads a missing `pen` as "use the kind's own default pen", not "no
   pen" — so a real, visible default-colored line was drawn first, and
   the later `setPen(None)` call changed a *different* pen attribute than
   the one actually painting that line.
2. Separately (see WP-I1's own finding, folded in here since it's the
   same root issue from the opposite direction): a fully click-selectable
   "no visible line" scatter effect needs a fully-transparent pen
   (alpha 0), not `pen=None` or a `NoPen`-styled pen — pyqtgraph's
   `PlotDataItem.updateItems` skips building the underlying
   `PlotCurveItem`'s hit-testable path data entirely when `opts['pen'] is
   None`, which would make the item permanently unclickable.

**Lesson:** "no line" is not one concept in pyqtgraph — a kind's own
`create()` may interpret a missing/`None` pen as "use my default" rather
than "draw nothing", and even when you deliberately want an invisible
line, `None`/`NoPen` and "fully transparent" behave differently for
downstream hit-testing. Read the specific class's own handling of a
`None`/missing pen (don't assume it matches `QPen`'s or another
pyqtgraph class's convention), and verify the *rendered* result (a real
screenshot or a pixel/hit-test check), not just that a style-comparison
assertion passes on the wrong object.

### 16. A `PlotDataItem`'s `opts` dict pre-populates keys you didn't set

**Symptom (found by WP-K2, 2026-09-28):** an early attempt to gate the
Curve browser's "marker" property control on `'symbol' in item.opts`
(to decide whether the selected series is scatter-like) always showed
the control, even for a plain line series.

**Root cause:** `pg.PlotDataItem.opts` is populated with a full, fixed
set of keys at construction (`'symbol'`, `'pen'`, `'fillLevel'`, ... all
defaulting to `None`/a default value) regardless of which keyword
arguments were actually passed to `.plot(...)` — so `'symbol' in
item.opts` is `True` for every `PlotDataItem`, line or scatter alike;
only `item.opts['symbol'] is None` vs. not tells them apart, and even
that only works by accident (nothing stops a future kind from setting
`symbol=None` deliberately for some other reason).

**Lesson:** don't gate behavior on whether a pyqtgraph item's `opts` dict
*contains* a key — check `Series.kind` (the string name) or
`SeriesKind.capabilities` instead, both of which this project already
maintains precisely for this purpose. This is the same family as bug
#7/#8's "an object's attribute doesn't hold what its presence/absence
seems to suggest" — verify the actual value and its real meaning for the
specific class, never infer meaning from a dict key merely existing.

### 17. Three lessons from WP-O (3D integration, 2026-09-28)

**pyqtgraph's `GraphicsScene` drops a mouse move closer than
`1/mouseRateLimit` seconds (10ms) to the previous one.** A synthetic drag
that fires its moves back-to-back with no real delay can silently lose
every one of them to this rate limit — the drag never becomes a
pyqtgraph drag event at all, with no error raised. It only "worked" in
this project's existing `tests/helpers._band_drag`/`_brush_drag` by
accident: enough real wall-clock time already passed between synthetic
`QMouseEvent`s (Python call overhead, `app.processEvents()`) to clear the
threshold on this machine. Discovered because a *second*, immediately-
following synthetic drag in the same test — whose prior-move timestamp
was now fresh — reliably failed where the first one hadn't. **This is
now fixed**: `_band_drag` (and `tests/test_3d.py`'s own `_drag`) sleep
12ms between moves. **Lesson:** a headless drag helper needs to pace its
synthetic moves against real time, not just send them in the right
order — and don't trust a drag helper "because the existing tests using
it pass"; they may only be passing by the same accident bug #11's fix
also had to correct for a different reason.

**`ViewBox.addedItems` only lists items that count toward the view's
autorange bounds.** Anything added with `plot_item.addItem(item,
ignoreBounds=True)` — an overlay, an image, a legend — is invisible to
that list. To find "everything actually in this ViewBox" regardless of
bounds participation, walk `viewbox.childGroup.childItems()` instead, or
keep your own explicit registry.

**In a render-on-demand loop, profile everything the renderer touches,
not just the draw call.** A first version of the 3D cell's per-frame
cost was 51ms, almost all of it re-scanning a 1M-point array's min/max
for camera-fit bounds on every single render — the actual GL draw was
~1ms. Caching that scan (recompute only when the underlying data or
visibility actually changes, not every frame) dropped it to the expected
~1ms. The lesson generalizes past this one case: "redraw only when
something changed" (as WP-G's spike itself recommended) has to apply to
every expensive step inside the redraw, not only to the decision of
whether to redraw at all.

### 18. State parked "while X is on" must be dropped when X ends (2026-09-29)

**Symptom:** a curve restyled while unselected (Curve browser width
spin) snapped back to its old width the next time it was selected and
deselected. Separately, the legend button did nothing visible.

**Root cause:** the selection highlight parked the real pen in
`opts['_orig_pen']` with `setdefault` and restored it on deselect with
`get` — so the parked copy outlived the highlight, and the *next*
highlight's `setdefault` kept the stale one. The legend: pyqtgraph
fills a legend only as items are added *after* it exists; `addLegend()`
over existing curves gives an empty, zero-size item — "created" and
"visible" are different claims.

**Lesson:** a value parked for the duration of a temporary state
(highlight, drag, preview) is popped, not read, when that state ends,
and every edit made during the state goes through one path that knows
about it (`curve_style.py`). And test the user-visible outcome (the
legend has items and a size), not that the object exists.

### 19. Rebuilding a QTreeWidget from inside its own itemChanged handler nulls out the pending itemClicked for the same click (2026-09-29)

**Symptom:** clicking a checkbox in the Curve Browser tree (reported for
an ellipse and a text+arrow annotation row, but not specific to either
kind) raised `AttributeError: 'NoneType' object has no attribute 'data'`
in `_on_curve_tree_item_clicked`. Not reproducible by calling
`item.setCheckState(0, ...)` directly (what the existing checkbox tests
did) — only by a real click on the checkbox indicator.

**Root cause:** a real click on a `QTreeWidgetItem`'s checkbox delivers
**two** signals for that one click: `itemChanged` (the checkbox state
toggling) fires first, synchronously, followed by `itemClicked` (the
click itself). `_on_curve_item_changed` (the `itemChanged` handler)
called `self._curve_rebuild_tree()` directly, which does
`self.curve_tree.clear()` — destroying every `QTreeWidgetItem`,
including the one the still-pending `itemClicked` delivery was about to
hand to `_on_curve_tree_item_clicked`. Qt then delivers that signal with
a null item instead of a deleted-wrapper error (contrast bug #11's
"wrapped C/C++ object has been deleted" for a different kind of stale
reference) — `item.data(...)` on `None` is the `AttributeError` above.

**Fix:** `_on_curve_item_changed` now defers the rebuild
(`QtCore.QTimer.singleShot(0, self._curve_rebuild_tree)`) instead of
calling it inline, so both signals for the same click finish being
delivered to the *original* tree before it's torn down.
`_on_curve_tree_item_clicked` also gained a defensive `item is None`
guard, belt-and-suspenders. Existing tests that call
`item.setCheckState(0, ...)` directly and then `app.processEvents()`
still see an up-to-date tree — a `QTimer.singleShot(0, ...)` is due
immediately, so `processEvents()` dispatches it in the same call.

**Lesson:** don't mutate/rebuild a Qt item view synchronously from
inside a signal handler fired *by that same view*, for a gesture (here,
one click) known to emit more than one signal — an earlier handler in
the chain can destroy state a later one for the same event still needs.
When in doubt, defer the mutation with `QTimer.singleShot(0, ...)` and
let the current event finish being dispatched first. Also: a bug that
only reproduces via a real Qt-delivered event, not a direct method/
setter call, needs a test built the same way (real `QTest.mouseClick`
here) — see bug #11's and #14's own versions of this same lesson.

### 20. A brushed-point action silently saw "nothing selected" for every 3D series — and a modal QMessageBox segfaults under `QT_QPA_PLATFORM=offscreen`
**Symptom (found building the data-cursor overhaul, 2026-09-29):**
`delete_brushed_points()` on a real 3D selection crashed the whole
process (`Segmentation fault`, no Python traceback at all — see CLAUDE.md
item 7's own note on segfaults being harder to debug than a raised
exception) the instant it ran under the test suite's offscreen platform.

**Root cause, two layers:** `selection.py`'s `_point_xy` (the fallback
used by `positions_of_rows`, which `brushing._figure_brush_items` calls
for every one of the four brushed-point actions, regardless of kind) only
ever recognized a plain 1-D `(x, y)` pair as "point-like" — a 3D kind's
`get_xy` of `(positions (N, 3), None)` made it return `None` unconditionally
(`y is None` failed the old `x is None or y is None` check). So
`_figure_brush_items()` saw *zero* items for a 3D selection that the
ViewBox/RectBrush plumbing had, in fact, already brushed correctly (3D
brushing itself works fine — it's a completely separate code path,
`Kind3D.rows_in_rect`/`show_rows`, which `positions_of_rows` never
touches). `_require_brush_selection()` then did exactly what it's
supposed to when nothing is selected: pop a `QMessageBox.information(...)`
— which is where the process actually died, since a real modal dialog's
`exec_()` has no sane thing to do with no real display under `offscreen`.
This is a second, independent confirmation of CLAUDE.md item 7/10's own
running theme (an offscreen/headless environment fails in ways a real
session wouldn't) — plus a new one of its own: **a bug that looks like
"my new code crashed" can actually be "my new code finally reached a much
older, never-before-exercised code path"**. Don't assume the crash site
is the bug site; here the crash was three call-frames away from the real
gap, in code nobody had ever touched (CLAUDE.md's own 3D section already
flagged "the four brushed-point right-click actions... skip 3D series" as
a known gap — this was *why*, precisely, not just *that*).

**Fix:** `_point_xy` now also accepts `(positions (N, 3), None)`, treating
it as one point per row (using only the x/y columns — row *membership* is
all `positions_of_rows` needs, it never reads coordinates back through
this path) via `_row_ids`, the same row-id-or-array-index convention every
other kind already used. `delete_brushed_points` itself also needed one
narrower fix once selection was actually reaching it: its array-slicing
line assumed `y` was always an array (`np.asarray(y)[keep]`), which raises
on `y is None` — now guarded.

**Lesson:** when a new feature is the first thing to ever exercise an
existing "generic, kind-agnostic" function against a kind that function's
own author never tested it against (here: `positions_of_rows` against a
3D series), verify that path explicitly with a real test *before* trusting
CLAUDE.md's own "known gap" wording at face value — "skip 3D series" could
have meant anything from "not implemented" to "silently n-op" to, as it
turned out, "the selection never even reaches the code that would delete
anything." And: bisect a segfault by adding `flush`ed logging between
every single call (`print`/file-append, not relying on default buffering
even with `python -u` — a genuine segfault can still lose already-written
buffered output), never by staring at the last line of a traceback that
doesn't exist.

### 21. A pyqtgraph `ViewBox` clips its children, so Qt ignores a custom `shape()` for hit-testing unless `contains()`/`collidesWithPath()` are also overridden

**Symptom (found tightening annotation hit-tests, 2026-09-29):** giving
`AnnotationItem` a real `shape()` override — the dashed selection outline
instead of the padded `boundingRect()` — worked for a `'figure'`-anchored
annotation but had **no effect at all** for an `'axes'`-anchored one: a
click well outside the tight shape, in the old padded corner, still
selected it.

**Root cause:** `QGraphicsItem.contains()` (what a real mouse press's
`collidesWithPath()` hit-test actually calls) uses the item's **clip
path**, not `shape()`, whenever the item is clipped by an ancestor — and
`shape()` is only consulted for an item that clips *itself*
(`ItemClipsToShape`). A `PlotItem`'s `ViewBox` clips its children to its
own data-area rect, so every `'axes'`-anchored item was silently hit-tested
against that ancestor clip rect, never the item's own `shape()`. Only
visible by testing an axes-anchored shape with real mouse events (a
`'figure'`-anchored one, or a direct method call, never exercises the clip
path at all) — CLAUDE.md's own recurring lesson (items 7/11/14/19) that a
real event, not a direct call, is what surfaces this class of bug.

**Fix:** override both `contains()` and `collidesWithPath()` on the item
to intersect `shape()` with whatever clip path is already in effect,
instead of relying on Qt's default (clip-path-only) behavior.

**Lesson:** a tight custom `shape()` on any `QGraphicsItem` living inside
a clipping ancestor (any pyqtgraph `ViewBox`, not just this project's own
code) needs the same two-method override, or it silently has no effect on
hit-testing for that specific case — a gap invisible from `boundingRect()`
being correct and `shape()` "looking right" in isolation.

### 22. `GraphicsScene`'s click-candidate search filters by a fixed radius/`boundingRect()` *before* an item's own hit-test ever runs

**Symptom (found widening click tolerance, 2026-09-29):** padding
`ScatterPlotItem.pointsAt()`'s own per-point hit-test by a few screen
pixels did nothing for a near-miss click on an isolated marker — the
click simply never reached that method at all.

**Root cause:** pyqtgraph's `GraphicsScene.itemsNearEvent` (the function
that decides which items are even *candidates* for a click, before
calling any item's own `mouseClickEvent`) filters first by each item's
`shape()`/`boundingRect()` within a small, separate `_clickRadius`
(default 2px) — an item whose own drawn extent doesn't reach that far
from the click point is never handed the event, regardless of how
generous its own hit-test method is.

**Fix:** widen both — the item-level hit-test (via a small per-instance
monkeypatch of `pointsAt`) **and** the scene's own `_clickRadius`
(`GraphicsScene.setClickRadius`). Padding only one silently fixes nothing
for a truly isolated point/curve.

**Lesson:** pyqtgraph's click dispatch has two independent filters in
series (scene-level candidate search, then item-level hit-test) — widening
click/selection tolerance needs both, and only a real `QMouseEvent` sent
to the viewport (not a direct call to the item's own hit-test method)
shows whether the *first* filter is even letting the click through.

### 23. A function monkeypatched onto a Qt/pyqtgraph item must reach that item only through a `weakref`

**Symptom (found building in-place rich-text editing, 2026-09-29):** the
full test suite passed, but stderr showed
`'LabelItem' object has no attribute '_sizeHint'` and several pyqtgraph
error blocks that master's own baseline run never produced — a real
regression a passing suite alone didn't surface.

**Root cause:** a closure stored directly on an item as `label.setText =
closure` held a **strong** reference back to `label` inside the closure's
own cell — `item.__dict__` holds the closure, the closure holds the item:
a reference cycle. Once the item is dropped from Python (e.g. a legend
label replaced on rename), the garbage collector breaks the cycle by
clearing the item's `__dict__` while the underlying Qt/C++ object is still
alive and in use — so the *next* call into it (Qt's own `sizeHint()`)
fails on a pyqtgraph attribute that's simply gone.

**Fix:** reach the item only through a `weakref` captured inside the
closure, and call the class's own method (`type(item).setText(item, ...)`)
rather than a previously-saved bound method.

**Lesson:** monkeypatching a method onto a live Qt/pyqtgraph instance is
sometimes unavoidable (see item 25 below for another instance) — but the
replacement must never close over a strong reference back to that same
instance. And: **check stderr for stray tracebacks, not just the test
count** — a passing suite can still be quietly leaking broken objects.

### 24. A focused, editable `QGraphicsTextItem` can crash outright — a real access violation, no Python traceback — when painted through an OpenGL-backed `GraphicsView` viewport with an incomplete GL context

**Symptom (reported live, 2026-09-30):** right-clicking a subplot title
and choosing "Edit Text" crashed the whole app with **no error message at
all** — not a Python exception, a native crash.

**Investigation:** reproduced 100% reliably by giving a
`QGraphicsTextItem` (`TextEditorInteraction`, focused via `setFocus()`)
keyboard focus while it sits in a scene whose `GraphicsView` viewport is
GL-backed (`pg.setConfigOptions(useOpenGL=True)`, this project's own
shipped-app default — see "What worked well") **and** the GL context
itself is incomplete or unavailable — confirmed exactly reproducing under
`QT_QPA_PLATFORM=offscreen` on Windows (item 10's own "no OpenGL at all"
finding), and NOT reproducing with a real, working GL context in the same
environment. A plain `QGraphicsView`, pyqtgraph's own bare `GraphicsView`
with no `PlotItem`, and a `GraphicsLayoutWidget` with a `PlotItem` but
outside this project's own `LaFigure` window all survived the identical
focused item fine — the crash needed the *combination* of this project's
real window setup and a broken/absent GL context, so a fix couldn't be
"just don't use `useOpenGL`" (the millions-of-points feature needs it).

**Fix:** `setCacheMode(QGraphicsItem.DeviceCoordinateCache)` on the
editor item. This renders it to an ordinary `QPixmap` once, through Qt's
normal raster paint engine, and blits that onto the GL surface — sidestepping
whatever inside Qt's native text-control caret painting doesn't get along
with a GL paint engine that has nothing real behind it.

**Lesson:** a "no error message at all" crash report is a native crash,
not a silently-swallowed exception — reach for `faulthandler.enable()`
immediately (see the new debug mode, `lafigure/debug.py`) rather than
guessing from behavior alone. And: a bug that can't be reproduced with a
real, working GL context but reproduces 100% under this project's own
`offscreen` test platform (item 10) may still be a real risk on a user's
actual machine, if *their* GL context is similarly limited (remote
desktop, a VM without GPU passthrough, a broken driver) — ship the
defensive fix anyway rather than dismissing it as a test-environment
artifact.

### 25. Rich-text HTML always fully specifies `text-decoration` per span — unlike font-family/size/weight/style, it does not inherit from the item's own base `QFont`

**Symptom (reported live, 2026-09-30):** the Font dialog's
Underline/Strikeout checkboxes had no visible effect, and reopening the
dialog always showed them unchecked again, even though the same dialog's
Bold/Italic/Color all worked and persisted correctly.

**Root cause:** every rich-text item in this project (`pg.LabelItem`'s
CSS-based `setText`, and `richtext.to_html` for annotation text) renders
through per-character HTML spans. Empirically confirmed: setting the
item's own base `font.setUnderline(True)` has no effect on the rendered
text once *any* styled span exists, because Qt's rich-text engine always
resolves `text-decoration` explicitly per span (defaulting to none)
instead of falling through to the base font the way it does for
font-family/size/weight/style.

**Fix:** apply underline/strikeout via `QTextCursor.mergeCharFormat` over
the whole document, not via the item's base font — and reapply it after
any subsequent full-document rebuild (a later plain text edit calls
`setHtml`/`setText` again, which wipes the previous `mergeCharFormat`;
`editable_text.set_text`'s `_retext_keeping_decoration` reads the current
decoration before a text change and reapplies it after, in the one shared
choke point every text edit already goes through).

**Lesson:** don't assume every `QFont` property behaves the same way once
rich text is involved — verify empirically (read back the actual
`QTextCursor.charFormat()`, not just that `setFont()` was called) which
properties the base font actually supplies as a fallback and which a
styled span always pins down itself.

### 26. `run_tests.py` never closed a test's `LaFigure` windows, so the whole suite eventually crashed the process outright — with no Python traceback

**Symptom (found merging round 4's wave 1, 2026-09-30):** the full suite
(`QT_QPA_PLATFORM=offscreen python run_tests.py`) crashed the whole
process with exit code `-1073740791` (`0xC0000409`,
`STATUS_STACK_BUFFER_OVERRUN` — a native fastfail, the same "no Python
traceback at all" class as bug #24) about 500 tests in, reproducing
deterministically at the exact same test both times. Running just the
tests immediately before and after that point (even a much wider slice)
never reproduced it — only the full run did.

**Root cause:** almost every test builds a `LaFigure` (a `QMainWindow`)
and never calls `.close()`. `registry.py`'s `FigureRegistry.register`
appends every one to `self.figures` and nothing ever removes it except
`LaFigure.closeEvent -> registry.unregister` — so an unclosed test
figure is kept alive **forever**, by a process-wide singleton, for the
rest of the run. By ~500 tests in, hundreds of live `QMainWindow`s (each
with its own `GraphicsView`, `PlotItem`s, and — after round 4 added the
Rotate+Zoom/3D work — extra per-cell render state) had accumulated
enough native Qt/Windows resources to crash outright, not fail
gracefully. This had been silently growing since the very first test
package (WP-01) — round 4 simply added enough tests (and enough
per-figure state) to finally cross the threshold; the crash is not a bug
in any round-4 package's own logic, confirmed by bisection (isolated
slices of the new tests all passed cleanly on their own).

**Fix:** `run_tests.py`'s main loop calls
`QtWidgets.QApplication.closeAllWindows()` after every test (before
`app.processEvents()`), which sends a real close event to every
top-level widget still open — for a `LaFigure` this runs its
`closeEvent`, which unregisters it, letting Python (and Qt) actually
free it. One line, no test file needed to change.

**Lesson:** a process-wide registry that a per-test fixture registers
itself with, but not explicitly out of, is a leak by construction —
Python's own reference counting can't save you if the registry itself
holds the strong reference. This is invisible for a long time (each
individual test, and even a moderate slice of the suite, looks fine) and
then fails catastrophically once some resource limit is finally crossed,
with a native crash that carries no hint of *which* recent change is at
fault (bisecting on suspicion of the newest code is the wrong move here
— the real fix is almost always "the accumulation itself," not the last
thing that happened to tip it over). When a shared singleton is involved,
audit the register/unregister pair, not the code that runs right before
the crash.

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

The original text:

> **PyQtGraph's `GraphicsLayoutWidget` grid is a real `QGraphicsGridLayout`.**
> Layouts exist specifically to prevent overlap by construction. Every bug
> and every non-trivial feature traced back to either respecting that fact
> or fighting it:
>
> - Resizing one cell without disturbing others → done *for free* by
>   setting row/column stretch factors and letting the layout redistribute
>   space.
> - Making a subplot visually overlap its neighbors ("float") →
>   **impossible** while the layout manages it. You must detach it first.
> - "Move/swap two subplots" → same detach-and-reattach trick, then swap
>   which cell each item is reinserted into.
>
> If you're building something similar with a different library, look for
> the equivalent "manages the item" vs. "manages nothing" boundary in that
> library's layout system — the same class of bug will show up wherever
> you cross it carelessly.

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
- **Superseded by WP-J (2026-09-28):** brushing used to be hardcoded to
  two named scatter subplots (`self.scatter1`/`self.scatter2`). It now
  works on any brush-capable series, linked through shared `DataSource`
  rows (`selection.py`, `brushing.py`).
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
- **Coordinator Skill `/lafigure-next` — retired 2026-09-29**, once the
  roadmap was complete (it only triggered `PLAN.md`'s resume/merge/launch
  cycle; recover it from git history if a new multi-package roadmap
  starts). The procedure itself stays in `PLAN.md`.
- **Wrap-up Skill — `/lafigure-ship`
  (`.claude/skills/lafigure-ship/SKILL.md`, 2026-09-29).** After the
  roadmap, work became one user request at a time, each ending with the
  same checklist: offscreen suite, sync the "?" help dialog
  (`help.py`) and this file, then commit only this session's files (the
  user's own edits separate or left out, `git commit -F`). The help
  dialog and the commit split were the steps most easily forgotten.
- **Scoping Skill — `/lafigure-scope`
  (`.claude/skills/lafigure-scope/SKILL.md`, 2026-09-29).** The opposite
  bookend to `lafigure-ship`: before writing any implementation code for a
  nontrivial change (multi-file, user-visible behavior, or touching undo/
  data-model/annotation/selection/layout code), read the relevant modules
  first, then write a short scope proposal — what changes file-by-file,
  what's explicitly out of scope — and wait for the user's go-ahead. User
  request: confirm the change's perimeter before starting, not just
  report what was done afterward.
- **Reference Skill — `lafigure-axes-geometry`**
  (`.claude/skills/lafigure-axes-geometry/SKILL.md`, 2026-09-29). Not a
  workflow bookend like the two above — a standing reference, loaded
  before writing or reviewing paint()/geometry code for anything
  angle- or direction-dependent on an `'axes'`-anchored item. Captures a
  lesson learned the hard way twice in one session (the arrowhead, then
  the selection outline, both needed the same scene-space-then-map-back
  fix) so a future session applies it up front instead of rediscovering
  it per shape.

Still **not** Skills: the test recipe (one command:
`QT_QPA_PLATFORM=offscreen python run_tests.py`, since WP-01 landed
2026-09-28) and design decisions (they belong in this file, which every
session and agent already reads).

## License

BSD 2-Clause (see `LICENSE`). Every source file carries the same header;
add it to any new file rather than leaving new files unheadered.
