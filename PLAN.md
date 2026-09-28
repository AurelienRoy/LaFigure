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
| I1 | Kinds: scatter, stairs, area, hist | 3 | H | sonnet | todo |
| I2 | Kinds: bar, errorbar | 3 | H | sonnet | todo |
| I3 | Kind: heatmap/imshow + colorbar | 3 | H | sonnet | todo |
| J  | Brushing on every kind, hide/show brushed, derived columns (Phase 3) | 3 | H | opus | todo |
| K1 | Groups model: hierarchy, common label, HSL color offsets (Phase 2b) | 3 | H | sonnet | todo |
| K2 | Curve browser tab + bottom property editor (Phase 2b) | 4 | D, K1 | sonnet | todo |
| L  | Console panel + datatip + `src.filter` wiring (Phase 2) | 3 | H | sonnet | todo |
| M  | HTML export via plotly + decimation popup (Phase 4) | 4 | E, I1, I2, I3 | sonnet | todo |
| N  | Controls & reactive tables in grid cells / separate window (Phase 5) | 3 | A, F | sonnet | todo |
| O  | 3D integration: `axes_type='3d'`, kinds, projected brushing (Phase 6) | 4 | A, G, H, J | opus | todo |

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
| `figure.py`, `series.py`, `axes.py` (new), `clip_ops.py`, `view_ops.py` | H → I*/J/K1 |
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
