# PLAN.md — parallel execution plan for the CLAUDE.md roadmap

Written 2026-09-28 for work that spans several Claude sessions and several
parallel worker agents. **CLAUDE.md's "Roadmap" says *what* to build and
why (user decisions); this file says *who* builds it, in *what order*, and
*how the pieces merge*.** Don't restate requirements here — link to the
roadmap item instead, so there is one source of truth for each decision.

## How to resume in a new session (coordinator checklist)

1. Read CLAUDE.md (roadmap) and this file's **Status** table.
2. `git status`, `git branch --list "wp/*"`, `git worktree list` — find
   packages that were started, finished-but-unmerged, or abandoned.
3. For each finished branch: merge it (see **Merge protocol**), run the
   full test suite, tick its status here and its items in CLAUDE.md.
4. Launch the next wave: every package whose dependencies are all
   `merged` and that doesn't own a file another running package owns.
5. Before ending the session, update the Status table (and commit it), so
   the next session starts from facts, not memory.

Only the **coordinator** (the main session) edits this file, CLAUDE.md and
`lafigure/__init__.py`; worker agents report back and the coordinator
records it. This avoids merge conflicts on the shared docs.

## Why a wave 0 is needed before any parallelism

`lafigure/figure.py` was one 2,478-line class and `smoke_test.py` one
1,300-line script. Almost every roadmap item would have edited both, so
parallel agents would have conflicted on every merge. **Wave 0 (WP-01,
merged as `cda9273`/merge commit `git log --oneline -1`) split them**
along the seams the roadmap uses, and froze the interfaces the later waves
code against — see "WP-01" below for what actually landed, and CLAUDE.md's
package-tree comment and bug #8/#9 for what it found along the way.

## Status

`todo` → `running` (branch exists) → `review` (agent done, not merged) →
`merged` (on master, suite green). Update on every transition.

| WP | Title | Wave | Depends on | Model | Status |
|----|-------|------|-----------|-------|--------|
| 00 | Commit current state (Phase 0 edits, docs) | 0 | — | coordinator | merged (0ba7284) |
| 01 | Split figure.py into mixins; split tests; freeze interfaces | 0 | 00 | opus | merged (cda9273; 3 real bugs found & fixed, see CLAUDE.md bug #8/#9) |
| A  | Free layout engine on fractional grid (Phase 1) | 1 | 01 | opus | merged (0a72601); coordinator applied its 4 cross-file diffs + a figure.py cleanup + a real _mouse bug fix (tests/helpers.py) — see CLAUDE.md bug #11 |
| B  | Context-menu cleanup + CSV export; verify Home/Fit/zoom color (Phase 0) | 1 | 01 | sonnet | merged (06cda8d) |
| C  | "?" help dialog | 1 | 01 | haiku | merged (35c6069); figure.py/toolbar.py wiring applied directly by coordinator (mechanical, no owner yet) |
| D  | Figure Manager: tabs, editable nodes, blue selection, node menus (Phase 2b, figure-browser part) | 1 | 01 | sonnet | merged (9c2c820) |
| E  | Save dialog: PNG/JPG/SVG/PDF + header preview (Phase 4, non-HTML part) | 1 | 01 | sonnet | merged (0069605); figure.py/toolbar.py wiring applied directly by coordinator |
| F  | `DataSource` (pure numpy, no Qt) | 1 | 01 | sonnet | merged (7b85e7c) |
| G  | 3D offscreen-readback spike (standalone, not integrated) | 1 | 01 | opus | merged (89b253e) — **go**, see spikes/README.md and CLAUDE.md bug #10 |
| H  | Series/SeriesKind registry, Axes facade, gca/gcf; migrate all curve tuples (Phase 2 core) | 2 | A, F | opus | merged (6f79f52); coordinator applied its layout.py/brushing.py/__init__.py diffs — migration gap fully closed, `_PENDING_MIGRATION` empty |
| I1 | Kinds: scatter, stairs, area, hist | 3 | H | sonnet | merged (bf63d55) |
| I2 | Kinds: bar, errorbar | 3 | H | sonnet | merged (de052cf); found+fixed a real ErrorBarItem shape-mismatch crash |
| I3 | Kind: heatmap/imshow + colorbar | 3 | H | sonnet | merged (e2b84ec); found a real Series.name gap (fixed by coordinator, see series.py) |
| J  | Brushing on every kind, hide/show brushed, derived columns (Phase 3) | 3 | H | opus | merged (b638b99); coordinator applied its menus.py/toolbar.py/layout.py diffs, replaced the demo's line-drawn-as-dots workaround with real ax.scatter (I1's kind), deleted dead SelectionModel/LinkedScatter — see CLAUDE.md bug #14/#15 |
| K1 | Groups model: hierarchy, common label, HSL color offsets (Phase 2b) | 3 | H | sonnet | merged (cccf853); clip_ops.py copy/paste hook applied by coordinator alongside J's merge (both owned clip_ops.py) — 2 new tests in test_groups.py confirm it round-trips through undo |
| K2 | Curve browser tab + bottom property editor (Phase 2b) | 4 | D, K1 | sonnet | merged (96f40e2); group Copy/Paste in the tree not built (no clipboard concept for a single group yet); see CLAUDE.md bug #16 (a PlotDataItem's opts dict pre-populates keys) |
| L  | Console panel + datatip + `src.filter` wiring (Phase 2) | 3 | H | sonnet | merged (00556a7) |
| M  | HTML export via plotly + decimation popup (Phase 4) | 4 | E, I1, I2, I3 | sonnet | merged (da3fcf8); fixed 2 of its own pre-existing tests in test_export.py that asserted the pre-M placeholder state (html disabled/None) — its job was exactly to replace that; added a real file-on-disk export test |
| N  | Controls & reactive tables in grid cells / separate window (Phase 5) | 3 | A, F | sonnet | merged (a500df0); separate-window variant fully built, grid-cell integration left as a documented layout.py hook (see controls.py docstring) for O or a later pass |
| O  | 3D integration: `axes_type='3d'`, kinds, projected brushing (Phase 6) | 4 | A, G, H, J | opus | merged (54f49fa); **real GPU rendering confirmed working** in this environment (not just the offscreen fallback) — see CLAUDE.md bug #17. Coordinator applied its 3 cross-file diffs (clip_ops.py, view_ops.py, series.py) + 3 new tests, and hardened tests/helpers._band_drag against a real, latent pyqtgraph mouse-rate-limit bug WP-O found. **This is the last package in the plan — every WP through O is now merged.** |

Waves: **0** → {A, B, C, D, E, F, G} in parallel → **H** alone →
{I1, I2, I3, J, K1, L, N} in parallel → {K2, M, O}.
N only needs A and F, so it may start as soon as those two merge.

Model column: `opus` for the packages that redesign shared structure or
touch Qt/GL edge cases (01, A, G, H, J, O); `sonnet` for well-bounded
features; `haiku` only for the trivial one. The coordinator may override.

## WP-01 — the split (done; defines the file ownership everything else relies on)

Landed 2026-09-28, `cda9273`, merged to master. Behavior-preserving
refactor — the full suite (72 tests) passes on master after the merge.

- `figure.py` → `LaFigure(<9 mixins>, QMainWindow)`: `toolbar.py` (toolbar
  + shortcuts), `menus.py` (subplot/empty-space context menus), `layout.py`
  (grid, resize, move, swap, float, handles — kept as one module: the
  `self.floating` state ties them too tightly to split further), `naming.py`
  (figure/subplot/curve renaming, axis labels — added; not in the original
  module list), `selection_ui.py` (click dispatch, selection, rubber band,
  Tab/nudge), `history.py` (undo stack, `undo_group`), `brushing.py`
  (RectBrush glue + the four brushed-point actions), `clip_ops.py`
  (copy/paste curve & subplot, `delete_selection`/`delete_curve`),
  `annotation_ops.py` (placement, relink, `eventFilter`), `view_ops.py`
  (Home, Fit, Link X, remove average, FFT, `set_interaction_mode`).
  `figure.py` keeps `__init__`, `closeEvent`, the demo, and the composition.
- `smoke_test.py` → deleted; replaced by `tests/` (`tests/helpers.py` — the
  Fake* events, `_mouse`, `_key`, figure factories — plus one
  `tests/test_<area>.py` per mixin module, 11 files) and `run_tests.py` at
  the repo root (plain runner, no pytest; takes optional name filters,
  e.g. `python run_tests.py layout`). Every prior test moved (none
  dropped); the never-before-run Phase 0 tests (gray zoom box, Home/Fit)
  ran for the first time here.
- **Interfaces frozen, exactly as later packages should assume:**
  - `registry.py` signals: existing `figureOpened/figureClosed/
    subplotsChanged`, plus `selectionChanged(fig)` (fires once per
    outermost selection change, via a `@selection_op` decorator, only on a
    real change), `focusChanged(fig, plot)`, `figureRenamed(fig)`.
  - `active_plot` → `focused_plot`, now a **property**; its setter is the
    only writer and the one emission site of `focusChanged` (a test
    guards "no other writer"). `_hover_plot` is unchanged (Home/Fit only).
  - `add_subplot(row, col, rowspan=1, colspan=1, title='',
    axes_type='cartesian')` — spans pass through to the grid now; any
    `axes_type` other than `'cartesian'` raises `NotImplementedError` (a
    placeholder for Phase 6, not yet implemented). Still the single
    construction site (`tests/test_layout.py` now scans every module in
    the package for `addPlot(`, not just one file).
  - `fig.subplot_name(plot)` / `fig.rename_subplot(plot, name)` /
    `fig.rename_figure(name)`, all undoable, in `naming.py`.
- **Three real bugs found by finally running long-dead/never-run code**,
  fixed as part of this package — see CLAUDE.md bugs #8 and #9 for the
  first two:
  1. Zoom Rect's box was still yellow in a real drag (pyqtgraph rebuilds
     `rbScaleBox` on `setMouseMode`, dropping the one-time styling).
  2. Turning Grid Layout back on didn't apply the floated size (an
     emptied-by-the-loop `self.floating` was checked after the loop).
  3. Brushing crashed (`AttributeError`) in any figure without the demo's
     `selection_model` (i.e. every `FigureManager` "New Figure").
- **Known gaps, from the worker's own report** — pick these up in whichever
  package touches the same area, don't assume they're handled:
  - A subplot's explicit name (`rename_subplot`) isn't yet carried through
    copy/paste or delete/undo as its own field — it survives only because
    `rename_subplot` also sets the title, and copy/paste/delete already
    carry the title. Relevant to **D** (Figure Manager renaming) and **K2**
    (curve browser) — decide there whether "name" needs to be a first-class
    serialized field once groups/browsers depend on it.
  - Double-click title editing (`editable_text.py`) still doesn't update
    the stored explicit name, so the two can drift apart after a rename.
  - A few toolbar/menu tooltips still say "active subplot" (stale text,
    not logic) and Delete's tooltip doesn't mention it now deletes every
    selected kind, not just a curve/subplot — cosmetic, worth a pass
    whenever **B** or **C** next touches that area.

## File ownership (valid after WP-01)

A running package may edit **only** its owned files plus new files it
creates, and its own `tests/test_<wp>.py`. Needing to touch someone
else's file = stop and report to the coordinator (it may be a missing
interface, which the coordinator adds on master first).

| Files | Owner WP(s), in wave order |
|-------|----------------------------|
| `layout.py`, `handles.py` | A → O |
| `menus.py` | B → J → K1 |
| `help.py` (new) + one toolbar line | C |
| `manager.py`, `naming.py`, `registry.py` (signal emission sites only) | D → K2 |
| `export.py` (new) | E → M |
| `datasource.py` (new) | F → J |
| `spikes/` (new) | G |
| `figure.py`, `clip_ops.py`, `view_ops.py` | H → J |
| `series.py`, `axes.py` | H, then the coordinator generalized both (2026-09-28, `1858c4a`) so no kind/brushing/group package needs to touch either — see the note below the table |
| `kinds/<name>.py` (new, one per kind) | I1, I2, I3, O |
| `brushing.py`, `selection.py`, `selection_ui.py` | J |
| `groups.py` (new) | K1 |
| `console.py` (new) | L |
| `controls.py` (new) | N |
| `history.py`, `annotation_ops.py` | untouched by any package below wave 4; whichever package first needs to (e.g. layout-undo work in **A**, or group drag in **K1**) claims it there and reports the claim |
| `tests/helpers.py` | shared read-only fixture module — any package may **add** a helper function to it but must not modify or remove an existing one (other packages' tests depend on it); if an existing helper must change, stop and report instead of editing |
| `toolbar.py` | coordinator: packages that need a button send a one-line diff in their report |

When two packages in the same wave would own the same file, they are
**not** parallel — the table above already sequences them. `figure.py`
(the thin composition root) is listed once, under H, because H is the
first package likely to need a new mixin registered there; earlier
packages (A/B/C/D/E/F/G) should not need to touch it — if one does,
report it rather than editing.

**`series.py`/`axes.py` after the coordinator's wave-3 prep (`1858c4a`,
2026-09-28):** I1/I2/I3/K1/L do **not** own or need to edit either file.
A new kind gets `ax.<kind name>(...)` automatically once registered
(`Axes.__getattr__`/`_plot_kind` route any name in `SERIES_KINDS` there —
only `'line'` keeps its own `plot()` method, for its single-array
convenience). `SeriesKind.get_xy`/`set_xy` (new, override the
`item.xData`/`item.yData`/`item.setData` default) make `Series.x`/`.y`/
`.set_data`/`.source` work for a kind whose item isn't a plain
`PlotDataItem` — needed by any kind building a `BarGraphItem`,
`ErrorBarItem` or `ImageItem`. `_add_series`'s click-wiring
(`_wire_curve_clickable`, which assumes `item.curve`) is now guarded by
`hasattr(item, 'curve')` — a kind without that attribute is plotted, just
not yet click-selectable; making it selectable is **J**'s job, not the
kind package's. If a kind package finds it genuinely needs to change
`series.py`/`axes.py` beyond registering a kind (not just using the
mechanisms above), stop and report rather than editing.

## Worker agent brief (template the coordinator fills in)

Launch each package with `Agent(subagent_type="lafigure-worker",
isolation="worktree", model=<Model>, run_in_background=true)`. The
standing rules (reading order, ownership, tests first, suite, license
header, commit, report format) live in `.claude/agents/lafigure-worker.md`;
the prompt carries only the package-specific part:

```
Work package WP-<id>: <title>. Branch: wp/<id>.

Goal: <1–3 sentences, pointing at the CLAUDE.md roadmap items by heading>.
Owned files: <list>. Test file: tests/test_<id>.py.
Interfaces you consume: <names>. Interfaces you must provide: <names>.
Acceptance tests must cover: <list>.
Package note: see PLAN.md "Per-package notes" → <id> (plus anything new).
```

## Merge protocol (coordinator)

1. Merge branches **one at a time**, in the wave's table order, into
   master: `git merge --no-ff wp/<id>`.
2. Apply the report's diffs to coordinator-owned files
   (toolbar/`__init__`/docs).
3. Run the full suite after **each** merge; a red suite is fixed before the
   next merge (by the coordinator, or by re-sending the agent its failure
   with SendMessage).
4. Tick CLAUDE.md roadmap items, set Status here to `merged`, commit.
5. Remove the worktree and branch.

## Per-package notes (only what the roadmap item doesn't already say)

- **B**: pyqtgraph builds the subplot menu from three places — the
  ViewBox menu (View All / X axis / Y axis / Mouse Mode), PlotItem's
  "Plot Options", and the scene's "Export..." — read the installed
  pyqtgraph source to remove entries robustly (by action object, not by
  text). CSV: one file per subplot; columns `<curve name> x`,
  `<curve name> y` per curve; unequal lengths padded with empty cells;
  full data (`xData`/`yData`), never the downsampled display. The
  brushed-point entries must be updated on `aboutToShow`, since brushing
  state changes after the menu is built. (The Phase 0 Home/Fit/zoom-color
  tests were already run and fixed by WP-01 — nothing left to do there.)
- **A**: all bug #1–#6 code paths disappear; rewrite those tests against
  the new model rather than deleting coverage. FFT "row under the time
  plot" = insert a grid row after the source's bottom edge, shifting only
  grid-line indices (fractional coordinates make that safe — every edge
  below moves by one row index). Test neighbors' `sceneBoundingRect()`
  before/after every drag (bug #6 lesson).
- **E**: the Word-style preview is a dialog showing a rendered page image
  with the header text item draggable on it; export only on "Export".
  Keep the exporter API format-pluggable so M only adds a format.
- **F**: no Qt import at all, so its tests run in milliseconds and it can
  be used from a plain console. **Done** (`7b85e7c`) — final API for H/J/L/N
  to code against: `DataSource(dict_or_dataframe)`, `len(src)`/`src.n_rows`,
  `src.columns`, `src[name]` (read-only array), `src.add_column(name, arr)`,
  `src.filter(bool_array | "expr" | None)` + `src.filter_mask`,
  `src.hide_rows(idx)`/`show_rows(idx)`/`show_all()` + `src.hidden_mask`,
  `src.visible_rows` (filter AND NOT hidden), `src.on_change(cb)`/
  `off_change(cb)` (plain callback list, no Qt signal). Row index is the
  point ID; no id column exists or is needed.
- **G**: deliverable is a standalone script + a measured number (ms per
  frame at 800×600 and 1600×1000, 1M points) + a go/no-go recommendation
  in the report. No integration into LaFigure.
- **H**: the largest single change; nothing else in wave 2 runs alongside
  it. Must leave a smoke-test guard that `_add_series` is the only series
  construction site (like `add_subplot`'s).
- **J**: the "near-zero overhead when off" requirement gets a test: with
  Brush off, adding a million-point series allocates no selection mask and
  connects no brush handlers.
- **M**: the decimation popup offers keep all / 1:N (N editable, default
  10) / peak-preserving; plotly stays an optional import with a clear error
  if missing.

---

# Round 2 — post-roadmap batch (planned 2026-09-29)

The roadmap (WP-01..O) is complete and merged. This is a **second round**,
from one user request listing ~20 items: annotation geometry, curve
styling/menu correctness, legend correctness, a new per-curve Transform,
in-place rich-text editing, curve-browser structure, brushing fixes.

**Requirements live here, not in CLAUDE.md's roadmap** (which describes the
shipped state). Four design calls were confirmed with the user before
planning; they are requirements, not suggestions:

1. **Rich text = Qt rich text + Unicode math, no new dependency.** The
   in-place editor's source string supports a small LaTeX-ish subset
   translated to HTML + Unicode (`\alpha`, `^{}`, `_{}`, `\times`,
   `\leq`, `\infty`, `\mathbf{}`, `\mathit{}`, ...). **No** matplotlib
   mathtext, **no** fractions/integrals/matrices. Unknown tokens render
   literally rather than raising.
2. **Transform is display-only.** A series keeps `(dx, dy, sx, sy)`; the
   underlying `DataSource`/array is never modified, so Reset is exact and
   free forever. Everything user-facing (brush hit-test, Selection Stats,
   Fit, CSV export, HTML export) sees the **transformed** values, because
   they all re-derive from the item's drawn data.
3. **Z-order drives the legend only.** Front-most (highest `zValue`) first
   in the legend. The Curve Browser and Figure Browser trees keep
   **creation order** — user's explicit reason: so groups stay grouped.
4. **The Curve Browser's "shows the selected, not the focused, subplot"
   report is a bug to reproduce**, not a request to change which attribute
   it reads — it already reads `focused_plot` (`manager.py:339`).

## Status (round 2)

| WP | Title | Wave | Depends on | Model | Status |
|----|-------|------|-----------|-------|--------|
| P1 | Annotation geometry: tight hit-test, scene-space rotation, textarrow label | 1 | — | opus | merged (db64a90); found a real bug along the way — a pyqtgraph ViewBox clips its children, so Qt ignores a custom `shape()` for hit-testing unless `contains()`/`collidesWithPath()` are also overridden; textarrow label placed beside p1 on the up-facing side (MATLAB itself anchors at the tail — confirm with user if this matters) |
| P2 | Curve menu: style gating + order, click tolerance, right-click stickiness | 1 | — | sonnet | merged (9df20aa); found two real bugs — scatter markers were never actually wired to click-selection (`sigClicked` unconnected, so a click on a marker silently selected nothing) and pyqtgraph's `GraphicsScene._clickRadius` gates click candidates before an item's own hit-test ever runs, so widening `pointsAt` alone doesn't widen tolerance; right-click stickiness traced to click-cycling (`_apply_click_cycle`) also firing on right-clicks, not left-only |
| P3 | Legend: menu-toggle bug, `_`-prefix hiding, z-order ordering | 1 | — | sonnet | merged (3573b94); the menu-toggle bug was investigated with extensive real-Qt-event repro attempts and NOT reproduced — a regression test covers the real-menu path instead (see CLAUDE.md bug #5's standing rule); rename-updates-legend and z-order-after-front/back need one-line hooks from `naming.py`/`curve_style.py` (P8/P2's job — see the diff in the branch's own report) |
| P4 | Brushing: post-hide brush bug, Show-All enabled state, delete signal, example | 1 | — | sonnet | merged (7d481b6 + toolbar diff 22cea61); the post-hide lockup was investigated extensively with real, correctly-paced drags and NOT reproduced — traced the one apparent repro to the test harness reusing a stale `viewRange()` across a data-narrowing action, not a real bug (CLAUDE.md bug #5's rule); two regression tests kept for the exact reported sequence anyway |
| P5 | Curve Browser: focus divergence, Curves/Annotations categories + parent checkboxes | 1 | — | sonnet | merged (3573b94); found a real bug — `focused_plot`'s setter only fires `focusChanged` on an actual change, so re-clicking an already-focused subplot never re-notified the tree; fixed via an app-wide mouse-press event filter, not a registry-signal change |
| P7 | Transform popup (display-only) + Remove Average rebuilt on it | 2 | P2, P3, P4 | opus | merged (21a5fa3 + cross-file diffs d8cf553); transform lives in the drawn data itself (not a Qt item transform, not a proxy), so brushing/stats/fit/CSV/most exports see it for free; two gaps needed coordinator diffs (html_export.py's DataSource-backed path, console.py's src.filter refresh — both re-derived drawn data straight from source columns, bypassing the transform); applies to line/scatter/stairs/area only (not hist/bar/errorbar/imshow/3d) |
| P8 | In-place rich-text editing for every plot text + Font dialog | 2 | P1 | opus | merged (63e3539 + cross-file diffs 4add3cb); found a real reference-cycle bug — a monkeypatched closure held a strong ref back to the pyqtgraph item it was attached to, so GC clearing the item's `__dict__` on rename corrupted pyqtgraph's own internal state (silent unless stderr is checked, not just the pass count); font choice is untestable headlessly (`offscreen` has no fonts on Windows at all) |

Waves: **{P1, P2, P3, P4, P5} in parallel** then **{P7, P8} in parallel**.
(No P6: the example-script fix folded into P4, which owns the signal it
consumes.)

## File ownership (round 2)

| File | Owner |
|------|-------|
| `annotations.py`, `handles.py`, `tests/test_annotation_ops.py` | P1, then P8 (wave 2, text-editing parts only) |
| `menus.py`, `curve_style.py`, `selection_ui.py`, `tests/test_menus.py`, `tests/test_curve_style.py`, `tests/test_selection_ui.py` | P2, then P7 (wave 2, adds the Transform entry) |
| `view_ops.py`, `tests/test_view_ops.py` | P3, then P7 (wave 2, rebuilds `remove_average`) |
| `brushing.py`, `selection.py`, `datasource.py`, `examples/interactive_controls.py`, `tests/test_brushing.py`, `tests/test_datasource.py` | P4 |
| `manager.py`, `tests/test_curve_browser.py`, `tests/test_manager.py` | P5 |
| `transform.py` (new), `series.py` | P7 |
| `editable_text.py`, `naming.py` | P8 |
| `toolbar.py`, `help.py`, `icons/`, `__init__.py`, `CLAUDE.md`, `PLAN.md` | coordinator (send a diff in the report) |

Within wave 1 every package's file set is disjoint. `menus.py`,
`view_ops.py` and `annotations.py` are each wanted by a wave-2 package
too — that is exactly why those packages are in wave 2.

## Package briefs (round 2)

### P1 — Annotation geometry (opus)
**Load the `lafigure-axes-geometry` skill first.** Every item here is one
of its cases.
- `AnnotationItem` has **no `shape()` override**, so Qt hit-tests the
  20px-padded axis-aligned `boundingRect()` (`annotations.py:365-384`) for
  every kind. Add a real `shape()` that returns the **displayed dashed
  outline**: the oriented polygon for `ORIENTED_OUTLINE_KINDS`, a tight
  rect for `rect`/`text`, an **ellipse** for `ellipse`, and for
  `textarrow`/`cursor` the union of the segment outline **and** the text
  bubble. `boundingRect()` keeps its pad (it must still cover handles and
  the dashed stroke) — only `shape()` tightens.
- **Ellipse outline** becomes a bounding *ellipse* a few screen px larger
  than the drawn one; **rect** hugs the shape with a few screen px of
  spacing. Both paddings are **screen pixels**, built in scene space and
  mapped back — never `_px_to_local` applied per-axis on a non-1:1 subplot.
- **Rotation in screen space.** `_apply_rotation` (`annotations.py:791-814`)
  calls `setRotation()`, which rotates in local/data space — the gap the
  axes-geometry skill documents as known-unfixed. Fix it so a rotation
  reads as the same on-screen angle whatever the subplot's X/Y scale.
  Shift's 45 degree snap (`SHIFT_SNAP_DEG`) must snap to **screen** angles.
- **textarrow label placement**: `annotations.py:266` positions the text at
  a fixed `(8, -10)px` offset from **p0** (the item origin), not from the
  arrow endpoint — which is why it reads as "too low" relative to the
  endpoint. Place it relative to **p1**, offset perpendicular/along the
  segment in screen px, so it sits beside the tip at any angle.
- Out of scope: annotation text *editing* (P8), the Properties... dialog
  contents, filiation/anchoring.

### P2 — Curve menu correctness (sonnet)
- **Scatter line-props discrepancy**: gating is purely by kind string —
  `_LINE_KINDS` excludes `'scatter'` (`curve_style.py:76-87`), so Line
  Width/Style/Color are always disabled for a scatter even when it is
  visibly drawing a connecting line. Replace kind-only gating with the
  user's rule: **Line Style is never grayed** (for any kind that can draw
  a line at all — the user may want to *add* lines to a marker-only
  series); **Line Width and Line Color stay grayed while no line is
  drawn** (a pen that is `None`, `NoPen`-styled, or alpha-0 — see
  CLAUDE.md bug #15: "no line" is three different states in pyqtgraph).
  Setting Line Style away from "none" must make the line appear, and must
  then enable Width/Color.
- **Menu order** becomes: Line Style / Line Width / Line Color / Marker /
  Marker Size / Marker Color (currently Width, Style, Marker, Marker Size,
  Line Color, Marker Color — `menus.py:296-322`).
- **Click tolerance**: `_curves_at` (`menus.py:220-237`) hit-tests
  `curve.mouseShape()` and `scatter.pointsAt()` exactly. Widen both by a
  few **screen** pixels so a curve/point is easier to grab. Keep
  `selection_ui.py:475`'s `_can_start_band_at` consistent, or a rubber
  band will start on a curve the click would now select.
- **Right-click stickiness**: a right-click on an already-selected curve
  sometimes flips the selection to the subplot while opening the curve
  menu. `_curve_menu_targets` (`menus.py:244-254`) sets
  `self.focused_plot = plot_item` *first*, then only re-selects when the
  curve isn't already in `selected_curves` — so the reported symptom comes
  from somewhere else in the dispatch (`raise_context_menu`
  `menus.py:199-217`, `_on_plot_context` `menus.py:187-188`, or the
  exact hit-test missing the curve on the *second* press).
  **Reproduce with real `QMouseEvent`s before fixing** — a direct method
  call cannot show it (CLAUDE.md bugs #11/#19).
- Provides, for P3: `curves_to_front` (and any other z-mutating path in
  `curve_style.py`) calls `self._refresh_legend_order()` when it exists.

### P3 — Legend correctness (sonnet)
- **Menu "Toggle Legend" doesn't work; the toolbar button does** — yet
  both call the same `self.toggle_legend` (`menus.py:119`,
  `toolbar.py:130`, `view_ops.py:278-293`). So the difference is in *when*
  it runs, not *what* it calls (a `QAction` bound in a menu built per
  right-click, an `aboutToShow` rebuild, a stale `plot_item` captured in
  the closure, or focus moving on the right-click). **Reproduce through a
  real menu action trigger**, not by calling `toggle_legend` directly.
- **Hide `_`-prefixed names**, matplotlib's convention: `_show_legend`
  (`view_ops.py:295-307`) filters only on `item.name()` being truthy, so
  `examples/line_signal_annotations.py:72`'s `name="_nolegend_"` renders
  literally. Skip any name starting with `_`. Renaming a curve to/from a
  `_` prefix updates the legend.
- **Legend order follows z-order, front-most first.** `_show_legend`
  iterates `listDataItems()` (creation order). Sort by `zValue()`
  descending, ties by creation order. Provide
  `LaFigure._refresh_legend_order()` — rebuild/reorder the live legend —
  and call it wherever the legend is (re)built. P2 calls it from
  `curves_to_front`; P5's Curve Browser z buttons already go through that.
- Out of scope: legend position/styling, and the Curve Browser / Figure
  Browser tree orders (they stay creation-ordered, per decision 3).

### P4 — Brushing fixes (sonnet)
- **"After Hide Brushed Points I can't brush any other displayed point."**
  Static reading of `brushing.py`/`selection.py` found no cause — the path
  re-derives from `get_xy` each drag and `_synced_row_view`
  (`brushing.py:211-231`) self-heals. So **reproduce it first** with real
  drags (`_brush_drag`, pacing moves 12ms apart or more — CLAUDE.md bug
  #17's rate-limit lesson), including the exact user sequence: brush,
  Hide, then brush elsewhere. Suspect the *pooled figure-wide* selection
  state (`_brushers`/`_figure_brush_items`) still holding the hidden rows,
  not the hit-test itself.
- **"Show All Points" enabled only when something is hidden.** The subplot
  menu already does this (`menus.py:171-176` via `has_hidden_points()`);
  the toolbar action is always enabled (`toolbar.py:145-147`). Report a
  `toolbar.py` diff for the coordinator to apply: keep a handle on both
  actions and refresh their enabled state wherever brush/hide state
  changes.
- **A distinct Hide icon.** `SP_DialogDiscardButton` (hide) reads as a
  delete/discard, too close to Delete. Propose a replacement — either an
  existing asset in `icons/` or a small drawn `QPixmap` (an eye with a
  slash), the way `view_ops._zoom_cursor` draws its own. The coordinator
  adds any new file to `icons/`.
- **Deleting brushed points must notify.** `delete_brushed_points`
  (`brushing.py:498-529`) narrows only the series' own rows and **never
  touches the DataSource**, so `on_change` never fires and no reactive
  control/table re-runs. Give a delete a change notification that
  `depends_on=[source]` picks up, without pretending the source shrank
  (it doesn't — the data-cursor resync depends on that being false).
  Undo/redo of a delete must notify too.
- **`examples/interactive_controls.py`** then becomes reactive to deleted
  points: its `visible_stats` (lines 98-108) reads `source.visible_rows`,
  which is correct for *hidden* rows but blind to *deleted* ones. Its
  metric must match what is actually on screen after a brush + Del.

### P5 — Curve Browser structure (sonnet)
- **Reproduce the focus divergence.** The tab already keys off
  `focused_plot` via `registry.focusChanged` (`manager.py:190,339-344`),
  which fires **only on an actual change** — so re-clicking an
  already-focused subplot, or a click that lands on a curve (which
  deselects the subplot but keeps it focused), can leave the tree stale
  while the user reads it as "it follows the selection". Fix the real
  mechanism; do not re-point it at `selected_plots`.
- **Two categories.** Today `_curve_rebuild_tree` (`manager.py:513-530`)
  adds ungrouped series, then groups, then ungrouped annotations as
  siblings. Split into two top-level category rows, **Curves** and
  **Annotations**, each with its own checkbox. Groups keep working inside
  the category their members belong to.
- **Parent checkbox both ways.** Checking/unchecking a category sets every
  child. Checking a child while the parent is unchecked **re-checks the
  parent** — the reverse propagation that doesn't exist today
  (`_on_curve_item_changed`, `manager.py:579-598`, only pushes down; the
  `Group` tristate at `manager.py:569-576` is recomputed on rebuild).
  Reuse `Group.visible`'s tristate convention (True/False/None).
  Visibility stays **view state, never undo** — the project-wide rule.
- **Rebuild only via `QTimer.singleShot(0, ...)`** from inside an
  `itemChanged` handler — CLAUDE.md bug #19 is exactly this tree, and a
  real `QTest.mouseClick` on the checkbox indicator is the only way to
  catch a regression of it.
- Out of scope: tree row **order** (stays creation order, decision 3) and
  anything in the Figure Browser tab.

### P7 — Transform (opus, wave 2)
- New modeless popup per curve, opened from the curve right-click menu's
  **Transform...**: offset X, offset Y, scale X, scale Y, applied live as
  the user edits, with **OK / Reset / Cancel**. Closing saves the state so
  it can be inspected and reset later; Cancel restores the values the
  popup opened with.
- **Display-only (decision 2).** Store `(dx, dy, sx, sy)` per series
  (`transform.py`, with `series.py` holding the state and re-deriving the
  drawn arrays from the raw ones). The `DataSource`/raw array is never
  written. Everything downstream already re-derives from the item's drawn
  data, so brushing, Stats, Fit, CSV and HTML export see the transformed
  values for free — **verify each of those**, don't assume.
- **Remove Average is rebuilt on this.** Today it writes a derived column
  or edits in place and discards the mean (`view_ops.py:488-507`). It
  becomes: compute the mean, write it into the series' transform as
  `dy = -mean`, done — so the value is visible in, and resettable from,
  the popup. Its derived-column machinery
  (`_derive_y_column`/`_column_backed`) is no longer needed for this path;
  remove it only if nothing else uses it.
- Undo: one entry per applied change (a live-edit burst while dragging a
  field is one entry, the `undo_group()` pattern). Interacts with the
  cursor resync (`_resync_cursor_points`) — a pinned data cursor must
  follow a transformed point.
- Copy/paste of a curve or subplot carries the transform; so does
  `to_dict`/`from_dict` if a kind serializes it.

### P8 — In-place rich-text editing (opus, wave 2)
- **Replace every `QInputDialog` text popup with in-place editing**: the
  subplot title and axis labels (`editable_text.py:34-68`), legend entries
  (`editable_text.py:71-103`, which must keep routing through
  `figure._apply_curve_rename` so the rename stays undoable and reaches
  `curve.opts['name']`), and annotation text
  (`annotations.py:644-661`). Double-click starts an editor **where the
  text is**, with a caret; Shift+Enter (or the platform norm you document)
  inserts a **line break**, Esc cancels, click-away commits.
- **Rich text, decision 1**: Qt rich text + Unicode math, no new
  dependency. One translator module turns the stored source string into
  HTML for `QGraphicsTextItem`/`pg.LabelItem` (both already HTML-capable);
  the editor edits the **source**, the item displays the rendered form.
  Bold/italic, super/subscript, colors, multi-line, and common Greek/math
  tokens. Unknown tokens render literally.
- **Right-click on any of these texts offers a Font dialog** (`QFontDialog`
  — nothing in the project uses one yet) for family/size/bold/italic, plus
  color. Applied to the selection where that makes sense; undoable.
- The stored source string is what serializes (copy/paste, subplot
  copy/paste, save/export). PNG/SVG/PDF export renders the rich text;
  HTML export should carry at least bold/italic/Unicode — report, don't
  silently drop, anything it can't.
- Out of scope: annotation *geometry* (P1 owns it), real LaTeX math
  (fractions, integrals, matrices), and the `Properties...` dialog's
  existing line/fill controls.

## Round-2 notes for every package

- CLAUDE.md's bug list is the prior art for most of these: **#11** (use
  the full `QMouseEvent` constructor or Qt hit-testing sees the wrong
  point), **#15** ("no line" is three different states), **#16** (`opts`
  dict keys exist even when unset — gate on `Series.kind`), **#17** (pace
  synthetic drag moves 12ms apart or more), **#19** (never rebuild a tree
  synchronously inside its own `itemChanged`), **#20** (a segfault under
  `offscreen` usually means a modal dialog — never `exec_()` one in a test
  path).
- Four of these items are **"reproduce first"** bugs (P2's right-click
  stickiness, P3's menu toggle, P4's post-hide brushing, P5's focus
  divergence). Static reading already failed to explain three of them. If
  a package cannot reproduce its bug with real Qt events, it reports that
  — with what it tried — rather than shipping a speculative fix, per
  CLAUDE.md bug #5's standing rule.

## Round 2 — known gaps after both waves (2026-09-30)

Round 2 (P1-P5, P7-P8) is fully merged, 471/471 tests green. These are
real, reported gaps left deliberately unfixed (either genuinely out of
scope, or needing a file no round-2 package owned) -- not regressions.
Worth picking up in a future pass, not urgent:

- **Font choice is untestable headlessly.** `QT_QPA_PLATFORM=offscreen`
  on Windows has no fonts installed at all (`QFontDatabase().families()`
  is empty), so `QFontDialog`'s own family/size list can't be exercised by
  the suite. P8 tested everything around it (the dialog opens, undo,
  serialization) but not a real font pick -- try that once by hand.
- **Curve-menu Rename with no legend showing still opens a `QInputDialog`**
  (editable_text.py/naming.py): there's no on-screen text to attach an
  in-place editor to in that case.
- **Subplot copy/paste doesn't carry title/axis fonts** (only the text
  markup) -- the font lives on the pyqtgraph item, and `clip_ops.py`
  wasn't owned by P8.
- **Stale-reference risk on undo/redo of an annotation text/font edit**,
  same class as `set_data`'s existing pattern: if the annotation was
  recreated by an intervening delete-undo or create-undo-redo, a later
  undo of the edit targets the dead object. Not new to this round, just
  inherited by the new editor.
- **Possible drag conflict**: a mouse-drag *inside* an open in-place text
  editor (to select text) might also start the Select-mode rubber band,
  since `_band_event` doesn't know an editor is open. Not reproduced or
  tested.
- **An open Transform popup doesn't refresh if the transform changes out
  from under it** (an undo, or Remove Average run while it's open), and
  committing after the curve was deleted while the popup was open pushes
  an undo entry for a dead series -- both harmless no-ops today, not
  crashes.
- **Hidden rows round-tripped through a transform change can be off by
  about one ulp** (invert-then-reapply); drawn rows are always exact.
- **A custom `ax.datatip` format string on a source-backed, transformed
  series still shows raw source columns**, not the transformed values (the
  default, non-custom datatip text is correct).
- Transform applies to `line`/`scatter`/`stairs`/`area` only -- not
  `hist` (rebins), `bar`/`errorbar` (a scale wouldn't mean bar
  width/error height), `imshow` or any 3D kind.

---

# Round 3 — debug mode (planned 2026-09-30)

User request: a debug mode with a verbose log the user can copy/paste
back for future bug reports, enabled in every example script. Motivated
directly by two real bugs just found/fixed in round 2's follow-up
(title Edit Text's native GL crash -- no Python traceback at all -- and
the Font dialog's underline/strikeout). Confirmed with the user:
- **Log destination**: one fixed file, `lafigure_debug.log`, overwritten
  every run (not timestamped-per-run), always also streamed to stderr.
- **Log scope**: crash-safety (faulthandler, a Python exception hook, a
  bridge for Qt's own C++-side warnings) is the foundation everyone
  wants; on top of that, log interaction mode changes, every undo/redo
  push and run, click/selection dispatch, and brushing/annotation
  placement gestures.

**Frozen interface (every package codes against this, don't invent your
own):** `import logging; logger = logging.getLogger('lafigure.<module
name, e.g. history/view_ops/selection_ui/brushing/annotation_ops>')` --
ordinary hierarchical stdlib logging, no shared helper needed. WP-DBG1's
`lafigure.debug.enable_debug_mode()` configures handlers/level on the
root `'lafigure'` logger once; every child logger under it is affected
for free. Log at `logging.DEBUG`. `enable_debug_mode(log_path=None) ->
str` returns the absolute path it wrote to (default `lafigure_debug.log`
in the current working directory), so a caller (an example script) can
print it.

## Status

| WP | Title | Wave | Depends on | Model | Status |
|----|-------|------|-----------|-------|--------|
| DBG1 | Debug core: logging setup, faulthandler, exception hook, Qt message bridge | 1 | -- | sonnet | merged (7d36c7d); idempotency implemented as replace-not-stack; root `'lafigure'` logger's `propagate=False` (own addition, not spec'd) |
| DBG2 | Log interaction-mode changes + undo/redo push/run | 1 | -- | sonnet | merged (fd5c95a); a grouped undo_group() logs exactly one "landed on stack" line for the whole group, not one per inner _push_history call, since the group's own finally already resets state before its own push |
| DBG3 | Log click/selection dispatch | 1 | -- | sonnet | todo |
| DBG4 | Log brushing + annotation placement gestures | 1 | -- | sonnet | todo |
| DBG5 | Enable debug mode in all 7 example scripts | 1 | DBG1 (interface frozen above; codes in parallel, merges after) | sonnet | merged (531b5c1) |

All five run in parallel worktrees; DBG5 codes against the frozen
`enable_debug_mode()` signature above without waiting for DBG1's branch
to exist, but is merged only after DBG1 lands.

## File ownership

| File | Owner |
|------|-------|
| `lafigure/debug.py` (new), `lafigure/__init__.py`, `tests/test_debug.py` (new) | DBG1 |
| `lafigure/view_ops.py` (`set_interaction_mode` only), `lafigure/history.py`, `tests/test_view_ops.py`, `tests/test_history.py` | DBG2 |
| `lafigure/selection_ui.py`, `tests/test_selection_ui.py` | DBG3 |
| `lafigure/brushing.py`, `lafigure/annotation_ops.py`, `tests/test_brushing.py`, `tests/test_annotation_ops.py` | DBG4 |
| `examples/*.py` (all 7) | DBG5 |

`view_ops.py` is also owned (a different function, `remove_average`) by
nothing currently active -- DBG2 touches only `set_interaction_mode`,
so no collision with round 2's history.

## Package briefs

### DBG1 -- debug core (sonnet)
- `lafigure/debug.py` (new): `enable_debug_mode(log_path=None) -> str`.
  - Resolves `log_path` (default `os.path.abspath('lafigure_debug.log')`
    in the CURRENT working directory, not the package directory --
    that's where a user running an example actually looks).
  - Opens it in `'w'` mode (overwritten every run, per the user's
    choice), attaches a `logging.FileHandler` and a `logging.StreamHandler`
    (stderr) to the root `'lafigure'` logger, level `DEBUG`, format
    `"%(asctime)s %(levelname)s %(name)s: %(message)s"`.
  - `faulthandler.enable(file=<the same log file object>, all_threads=True)`
    -- the one thing that can leave ANY trace of a native crash with no
    Python traceback (exactly the class of bug CLAUDE.md's own bug #20
    and this round's Edit-Text crash both are).
  - Wraps `sys.excepthook`: logs `logger.critical(..., exc_info=(exc_type,
    exc_value, exc_tb))` then still calls whatever hook was previously
    installed (don't swallow the normal terminal behavior).
  - `QtCore.qInstallMessageHandler(...)`: routes every Qt
    warning/critical/fatal message through the same logger (Qt's own
    C++-side diagnostics are often the only hint before a native crash --
    see this round's own investigation, which relied on very similar
    manual instrumentation to find the GL/focus crash).
  - Idempotent: calling it twice must not attach duplicate handlers (a
    second call is a no-op, or replaces rather than adds -- your choice,
    tested either way).
  - `lafigure/__init__.py`: export `enable_debug_mode` from the public
    API (`lafigure.enable_debug_mode`).
- Acceptance tests (`tests/test_debug.py`, new): enabling creates/
  truncates the log file at the expected path; a message logged via
  `logging.getLogger('lafigure.somemodule').debug(...)` afterward
  appears in the file; a simulated uncaught exception is logged via the
  excepthook wrapper AND the previous hook still ran; a Qt warning
  (trigger one for real, e.g. via an invalid pyqtgraph call known to
  warn, or `QtCore.qWarning("test")` directly) is captured; calling
  `enable_debug_mode()` twice doesn't duplicate log lines for one
  subsequent message.
- Report the exact final log line FORMAT and logger-naming convention
  in your final report -- DBG2/DBG3/DBG4 are coding against your
  interface in parallel and the coordinator reconciles at merge time,
  but matching your actual format now avoids a needless mismatch.

### DBG2 -- mode changes + undo/redo (sonnet)
- `set_interaction_mode(mode)` (`view_ops.py`): log
  `logger.debug("mode: %s -> %s", old, new)` (or equivalent), only on an
  actual change.
- `_push_history(undo_fn, redo_fn, ...)` (`history.py`): log that an
  entry was pushed -- stack depth after push, and whether it's inside an
  `undo_group()` (nested groups collapse to one entry on the *outer*
  group's close, per the existing `undo_group` mechanism -- read it
  first, log at the point an entry actually lands on the stack, not per
  inner `_push_history` call swallowed by an open group, if that
  distinction exists in the current code).
- `undo()`/`redo()`: log which one ran and the resulting stack depth (or
  that the stack was empty and nothing happened).
- Logger name: `logging.getLogger('lafigure.history')` for history.py's
  own lines, `logging.getLogger('lafigure.view_ops')` for the mode
  change.
- Acceptance tests: attach a plain list-based logging handler (or
  caplog-equivalent -- this project has no pytest, so build a small
  `logging.Handler` subclass that appends `record.getMessage()` to a
  list, add/remove it around the assertion) to `logging.getLogger
  ('lafigure')` and assert a record appears for a mode change, a
  `_push_history` call, an `undo()`, and a `redo()`.

### DBG3 -- click/selection dispatch (sonnet)
- Find the ONE central place a click's outcome is finally decided (per
  CLAUDE.md's "What worked well": "One central click dispatcher, one
  mode variable" -- `_on_scene_clicked` in `selection_ui.py`). Log one
  DEBUG line per dispatched click: the gesture (plain/shift/right/
  double), what was hit (subplot/curve/annotation/empty space, with a
  short identifying name), and the resulting selection (counts, or the
  focused item's name).
- Logger: `logging.getLogger('lafigure.selection_ui')`.
- Acceptance test: dispatch a few real clicks via the existing `_mouse`
  test helper (a plain click on a curve, a Shift+click adding a subplot,
  a click on empty space) and assert each produces a log record whose
  message contains the expected target description, using the same
  list-based test handler pattern as DBG2 (build your own small helper;
  if it turns out identical to DBG2's, that's fine -- small duplication
  across independent packages beats a shared file neither owns).

### DBG4 -- brushing + annotation placement gestures (sonnet)
- `brushing.py`: log a brush drag's start (subplot, additive or not) and
  end (rect in data coords, row count caught).
- `annotation_ops.py`: log an annotation placement gesture's start (kind,
  anchor) and its outcome (completed with final geometry, or cancelled --
  Esc, or a negligible-movement click falling back to the default
  extent).
- Loggers: `logging.getLogger('lafigure.brushing')` /
  `logging.getLogger('lafigure.annotation_ops')`.
- Acceptance tests: a real, correctly-paced brush drag (`_brush_drag`
  helper, CLAUDE.md bug #17's 12ms pacing) produces start/end log
  records with the right row count; placing a rect annotation via the
  real press-drag-release gesture (`eventFilter`) produces start/
  completion records; pressing Esc mid-placement produces a cancellation
  record.

### DBG5 -- examples (sonnet, merges after DBG1)
- Add, in every one of the 7 `examples/*.py` files, right after
  `import lafigure`: call `lafigure.enable_debug_mode()` and print the
  returned path so the user immediately sees where to find/copy it from
  (e.g. `print(f"Debug log: {log_path}")`). Keep each example's own
  existing docstring/behavior otherwise untouched -- this is a small,
  identical, one-line-plus-print addition per file.
- Since DBG1's branch won't exist yet when you start, write against the
  frozen signature in this plan (`enable_debug_mode(log_path=None) ->
  str`) -- don't invent a different name/signature. If DBG1's actual
  merged interface differs from this plan when you check, stop and
  report rather than guessing.
- No dedicated test file: examples aren't covered by `run_tests.py`
  today (CLAUDE.md is explicit that they're customer-facing runnable
  scripts, not test fixtures) -- don't add one. Just confirm each script
  still runs cleanly to completion under
  `QT_QPA_PLATFORM=offscreen python examples/<name>.py` (it should exit
  0; a couple may need `app.exec_()` skipped/short-circuited under
  offscreen the way they already are, if that's already handled -- check
  first, don't add new offscreen-specific branching if the example
  doesn't already have any).
