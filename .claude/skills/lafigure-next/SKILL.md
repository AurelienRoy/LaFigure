---
name: lafigure-next
description: Coordinate the LaFigure roadmap across sessions - read PLAN.md's status, merge finished work packages, run the suite, update CLAUDE.md/PLAN.md, and launch the next wave of lafigure-worker agents. Use when the user says /lafigure-next, "continue the plan", "next wave", or asks where the roadmap stands.
---

# LaFigure coordinator

You are the **coordinator**: the only session that edits `CLAUDE.md`,
`PLAN.md`, `lafigure/__init__.py` and `toolbar.py`, merges branches, and
launches workers. `PLAN.md` holds the procedure; this skill is the
checklist for running it. If the two disagree, `PLAN.md` wins — fix this
file.

## 1. Establish the facts (never from memory)

- Read `PLAN.md` (Status table, File ownership, per-package notes) and
  the Roadmap section of `CLAUDE.md`.
- Run `git status`, `git log --oneline -10`, `git branch --list "wp/*"`,
  `git worktree list`.
- Reconcile: a `running` package whose branch has new commits and no live
  agent is probably `review`; a branch with no commits and no agent was
  abandoned. Ask the user before deleting anything.

Report the state to the user in a few lines: merged, in review, running,
ready to launch, blocked (and on what).

## 2. Merge finished packages

Follow `PLAN.md` → "Merge protocol": one branch at a time, in table order;
apply the worker report's diffs for coordinator-owned files; run the full
suite after each merge
(`$env:QT_QPA_PLATFORM='offscreen'; python run_tests.py`, or
`smoke_test.py` before WP-01); a red suite is fixed before the next merge.
Then tick the CLAUDE.md roadmap items, set the package to `merged`, record
any lesson the worker reported in CLAUDE.md, and remove the worktree and
branch.

Commit only when the user has asked for commits in this session; say so
if merges are waiting on that.

## 3. Launch the next wave

Launchable = every dependency `merged`, and no owned file shared with a
package that is `running` or `review`. Show the user the list, with
models, and get a go-ahead before launching (each agent costs real time
and tokens).

Launch each with the Agent tool:
- `subagent_type: "lafigure-worker"`, `isolation: "worktree"`,
  `model:` from the Status table, `run_in_background: true`;
- a prompt filled from `PLAN.md`'s brief template: package id, goal (point
  to the roadmap items, don't restate them), owned files, interfaces
  consumed/provided, acceptance tests, the per-package note.

Set each to `running` in `PLAN.md`. Workers commit on their own branch;
you merge later.

## 4. While workers run

Don't predict their results. When one finishes, read its report: if it
lists unverified or partial work, keep it at `review` and tell the user.
To send a worker its failures, use SendMessage to that agent rather than
launching a new one.

## 5. End of session

Status table updated, the user told what's merged, what's running, and
what the next session should do first.
