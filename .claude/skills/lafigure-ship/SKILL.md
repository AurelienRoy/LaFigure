---
name: lafigure-ship
description: Wrap up a finished LaFigure change - run the offscreen suite, sync the "?" help dialog and CLAUDE.md with what changed, then commit only this session's files. Use when the user says /lafigure-ship, "commit", "wrap up", or a requested feature/fix is done.
---

# Wrap up a LaFigure change

A checklist, in order. Don't skip a step because it "probably" doesn't
apply; check.

## 1. Tests
- Every behavior change has a test in the matching `tests/test_<module>.py`
  (a real Qt event via `tests/helpers.py` when the behavior depends on Qt's
  or pyqtgraph's event routing).
- Run the full suite: `QT_QPA_PLATFORM=offscreen python run_tests.py`
  (Bash) or `$env:QT_QPA_PLATFORM='offscreen'; python run_tests.py`
  (PowerShell). It must end with `ALL OK`; report the count.

## 2. The "?" help dialog (`lafigure/help.py`)
Update it whenever a mouse gesture, key, menu entry, toolbar button or
interaction mode was added, removed, renamed or changed meaning. It is
the user-facing doc; a stale line there is a bug.

## 3. `CLAUDE.md`
- The feature list (and the Roadmap, if an item landed): what changed,
  where it lives (module / function), and any product decision the user
  made, marked as theirs.
- The package tree, for a new module.
- A numbered lesson under "What was buggy", only for a real bug whose root
  cause generalizes. Symptom, root cause, lesson; not a changelog.

## 4. Commit (only when the user asked for it)
- `git status` first. Stage **only files this session changed**, by name
  or by folder (`lafigure tests CLAUDE.md`), never `git add -A`.
- Files the user edited themselves (e.g. `.gitignore`) go in a **separate
  commit** if asked, or stay out. Untracked editor files
  (`LaFigure.code-workspace`) stay out unless asked.
- Write the message to a scratchpad file and use `git commit -F <file>`
  (multi-line heredocs break in this shell). A summary line, then bullets
  per user-visible change, then the test count, then the attribution line.
- Current branch is fine unless the user says otherwise; never push
  unless asked.

## 5. Report
What changed for the user, anything that behaves differently from what
they might expect, the test count, and the commit hash(es).
