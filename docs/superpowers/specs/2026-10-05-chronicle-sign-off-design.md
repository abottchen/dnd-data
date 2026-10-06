# Chronicle sign-off

2026-10-05

## Why

Session 28's entry shipped as the session log in the log's order with a
bestiary paragraph inserted, one sentence lifted nearly verbatim from the
log, and two `revise` verdicts from the editor sub-agent that the pipeline
published anyway because `max_rounds` had run out. The run dir was pruned
on success, so the critiques were gone before the publisher could read
them. Nothing in the pipeline required an accept.

## What

The publisher (the user) signs off twice on every session entry, in the
`/build-prose` skill, before `apply` runs.

1. **Plan stop.** A new `plan-sessions` prompt pair, frozen by `prepare`
   and recorded in the manifest's `plan` map (`build/prepare.py:PLAN_FOR`).
   The planner reads the writer's slice and returns the story the page
   will tell: `through_line`, `opens_on`, `paragraphs` (one `subject` each
   and what each is `built_from`), `why_this_order`, `silent_roll`,
   `left_out`. The skill prints it and asks Approve / Stop, with free text
   as notes for a new plan. The approved plan is `context/<stem>.plan.json`
   and is an input to the writer, the editor, and every revision.
2. **Publisher stop.** After the editor loop and verify, the skill prints
   the finished entry and asks Publish / Stop, with free text as notes.
   Notes go to the writer, verify runs again, and it comes back. No
   sub-agent editor round in between: the publisher is the editor here.
   Stop holds the result (`results/<stem>.held.json`) and returns the slice
   to pending, so apply skips the render.

`apply` is unchanged. It still prunes a fully successful run, which now can
only happen after the publisher has said Publish.

## Editor changes

- Stage one reads the approved plan. The through-line is the plan's. A draft
  whose paragraphs are not the plan's is `redraft`.
- Round n reads round n-1's critique. An unaddressed note is `redraft`.
- Stage two may lower the verdict to `redraft`, never raise it. It records
  `lifted`: sentences that are the log's with a few words changed.

## Standard

The publisher's notes on session 28 are added to `publisher-notes.md`
verbatim with the passages they were about.

## Not done

No `clean` command and no change to when the run dir is pruned: the
publisher sees everything at the stops, and cleanup after sign-off is what
was asked for.
