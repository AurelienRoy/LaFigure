---
name: lafigure-scope
description: Confirm the scope of a nontrivial LaFigure change with the user before writing any implementation code - which files/modules will change, what behavior changes, and what's explicitly out of scope. Use before starting any change that touches more than one file, adds/removes/changes user-visible behavior, or touches undo/history, the data model (DataSource/Series), or the annotation/selection/layout machinery. Also use when a request is ambiguous about how far it should reach. Skip for a single-line fix, a typo, a rename, or a change the user already scoped precisely themselves (exact file + exact change named).
---

# Confirm scope before a nontrivial change

Read enough of the relevant modules first to know, concretely, which files
and functions are actually involved -- a scope proposal built from
guessing is worse than useless. Then stop and confirm before writing any
implementation code.

## 1. What counts as "nontrivial" (needs this)
- Touches more than one file, or more than one mixin/module.
- Adds, removes, or changes any user-visible behavior (a gesture, a menu
  entry, a toolbar button, a keyboard shortcut, what gets pushed to undo).
- Touches undo/history, the data model (`DataSource`/`Series`/
  `SeriesKind`), or the annotation/selection/layout machinery -- the areas
  CLAUDE.md's own bug list shows are the easiest to get subtly wrong.
- The request is ambiguous about how far it should reach (e.g. "add X" 
  without saying whether Y, which currently works similarly to X, should
  change too).

## 2. What does NOT need this
- A single-line fix, a typo, a rename, a comment.
- A change the user already scoped precisely themselves: they named the
  exact file and the exact change, leaving nothing to propose.
- A follow-up inside a scope already confirmed this session (don't
  re-confirm the same perimeter twice).

## 3. The proposal
Write a short scope proposal -- not a full implementation plan, and not
code. Cover, concretely:
- **What changes**, file by file / function by function, naming real
  paths (`lafigure/annotations.py`'s `_on_endpoint_drag`, not "the resize
  handler").
- **What's explicitly out of scope**: adjacent things that look related
  but won't be touched, and why (so the user can catch a wrong boundary
  before code exists, not after).
- Any real judgement call worth flagging in one line -- but don't turn
  this into an interrogation; a genuine either-way design decision still
  goes through AskUserQuestion on its own, same as any other time you'd
  ask it.

Keep it tight enough to read in a few seconds; this is a perimeter check,
not a design document.

## 4. Wait for the go-ahead
Don't write implementation code until the user confirms (a plain "yes",
"go ahead", or an explicit edit to the proposed scope). If their reply
changes the scope, restate the updated scope in one line before
proceeding -- cheap, and it catches a misread before an hour of work does.

## 5. After confirmation
Proceed with the confirmed scope. If, while implementing, you discover
the real fix needs to reach outside it (a bug traces to a file you didn't
list), stop and say so in one line before continuing -- don't silently
expand the perimeter either.
