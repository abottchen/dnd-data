---
name: build-prose
description: Drive a full dnd-data build end-to-end — runs `python -m build prepare`, dispatches one sub-agent per pending slice, then runs `python -m build apply`. Use when the user says "build prose", "drive a build", "/build-prose", or supplies a path under build/.run/. Does not touch build/authored/ directly; the apply step writes there.
allowed-tools:
  - Bash(.venv/bin/python -m build prepare*)
  - Bash(.venv/bin/python -m build apply *)
---

# build-prose

You are the loop driver for the dnd-data build's authoring step. You own all three phases: kick off `prepare` to stage slices, dispatch a sub-agent per pending slice to write JSON results, then kick off `apply` to validate, persist authored prose, and render the site.

## Inputs

The user invokes you one of two ways:
- `/build-prose` (no arg) — the common case. Run `prepare` to stage a fresh run dir, then proceed.
- `/build-prose build/.run/2026-05-17T14-32-08` — resume an existing run dir (e.g. after fixing a failed slice). Skip `prepare` and use this dir.

A valid run directory contains `manifest.json`, `pending/`, `results/`, `done/`, and `prompts/`.

## Procedure

1. **Prepare** (skip if the user passed a run-dir):
   - Run `.venv/bin/python -m build prepare` via Bash from the repo root.
   - The first stdout line is the run-dir path; use that as `<run-dir>` below.
   - If the command exits non-zero, print its stderr and stop.
2. Read `<run-dir>/manifest.json`.
3. Filter `slices` to entries whose `pending/<stem>.json` still exists (i.e. not yet authored). If the list is empty, skip straight to the apply step — `apply` still needs to run to render the site / bump the marker on a refresh-only build.
4. Dispatch sub-agents in batches of up to 5 in a single message:
   - `subagent_type: "general-purpose"`
   - `model`: the entry's `model` field (`sonnet` or `opus`).
   - **Prompt body** (substitute the bracketed fields):

         You are acting as the [transformer] transformer. Read these
         two files only:

         - prompt body: <run-dir>/[prompt_body]
         - schema: <run-dir>/[schema]

         The slice input is:

         <inline the entire contents of <run-dir>/[pending]>

         Produce a single JSON object that conforms to the schema. Do
         not include any prose, markdown, or commentary — only the
         JSON document. Write it to:

         <run-dir>/[result]

         Do not edit any other file. Do not run any other tool besides
         Read (on the two paths above) and Write (on the result path).
5. After every sub-agent in the batch returns, check `results/<stem>.json`:
   - If the file exists and parses as JSON, move `pending/<stem>.json` to `done/<stem>.json`.
   - If not, leave the pending file in place and log the slice in `<run-dir>/failures.json` (append, not overwrite).
6. Repeat batches until `pending/` only contains slices that have failed at least once. Do not retry inside the same skill run — the user gets to decide whether to edit the slice or prompt first.
7. **Apply**: run `.venv/bin/python -m build apply <run-dir>` via Bash. Always run it, even when some slices failed — `apply` is safe to call with leftover pending slices (it just skips the render). Surface its stderr summary (applied / rejected / pending / marker / render) inline.
8. End with a one-line status:
   - All clean and render OK → `build complete`.
   - Anything rejected or still pending → name what failed and tell the user that `/build-prose <run-dir>` will resume from where it stopped after they fix the prompt or slice.

## Constraints

- Never modify `build/authored/*.json`. The apply step does that.
- Never modify files under `<run-dir>/prompts/`. They are the frozen reference.
- Never run `build/render.py` directly. The apply step does that.
- If `manifest.json` is missing after prepare, print an error and exit.

## Failure handling

If a sub-agent returns nothing or returns invalid JSON, do not write a placeholder result. Leave the pending file in place. The apply step will report it as pending; the user can fix the prompt or slice and re-run `/build-prose <run-dir>` to resume.

A second `/build-prose <run-dir>` call is safe — it skips slices already moved to `done/` and retries anything still in `pending/`.
