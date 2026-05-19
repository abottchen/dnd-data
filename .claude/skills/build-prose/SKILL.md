---
name: build-prose
description: Drive a dnd-data build run by walking the pending/ slice queue in a run directory produced by `python -m build prepare`. Use when the user says "build prose", "drive a build", "/build-prose", or supplies a path under build/.run/. Dispatches one sub-agent per pending slice, each writing a JSON result file; does not touch build/authored/ directly.
---

# build-prose

You are the loop driver for the dnd-data build's authoring step. The deterministic Python around you has already done the slicing and will do the applying. Your single job: for every pending slice in the supplied run directory, dispatch a sub-agent that reads the slice and the prompt, produces JSON conforming to the schema, and writes it to `results/<stem>.json`.

## Inputs

The user invokes you with a path to a run directory, e.g.:
- `/build-prose build/.run/2026-05-17T14-32-08`
- `/build-prose` (no arg) — pick the alphabetically maximal subdirectory of `build/.run/`.

A valid run directory contains `manifest.json`, `pending/`, `results/`, `done/`, and `prompts/`.

## Procedure

1. Read `<run-dir>/manifest.json`.
2. Filter `slices` to entries whose `pending/<stem>.json` still exists (i.e. not yet authored).
3. Dispatch sub-agents in batches of up to 5 in a single message:
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
4. After every sub-agent in the batch returns, check `results/<stem>.json`:
   - If the file exists and parses as JSON, move `pending/<stem>.json` to `done/<stem>.json`.
   - If not, leave the pending file in place and log the slice in `<run-dir>/failures.json` (append, not overwrite).
5. Repeat batches until `pending/` only contains slices that have failed at least once. Do not retry inside the same skill run — the user gets to decide whether to edit the slice or prompt first.
6. Print a one-line summary per slice (applied / failed) and the next-step command:
   ```
   python -m build apply <run-dir>
   ```

## Constraints

- Never modify `build/authored/*.json`. The apply step does that.
- Never modify files under `<run-dir>/prompts/`. They are the frozen reference.
- Never run `build/render.py`. The apply step does that.
- If `manifest.json` is missing, print an error and exit.
- If the run dir has no pending slices, print `nothing to do` and exit.

## Failure handling

If a sub-agent returns nothing or returns invalid JSON, do not write a placeholder result. Leave the pending file in place. The next `python -m build apply <run-dir>` will report it as pending; the user can fix the prompt or slice and re-run `/build-prose`.

A second `/build-prose <run-dir>` call is safe to run — it skips slices already moved to `done/` and retries anything still in `pending/`.
