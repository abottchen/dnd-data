---
name: build-prose
description: Drive a full dnd-data build end-to-end — runs `python -m build prepare`, dispatches one sub-agent per pending slice, then runs `python -m build apply`. Use when the user says "build prose", "drive a build", "/build-prose", or supplies a path under build/.run/. Does not touch build/authored/ directly; the apply step writes there.
allowed-tools:
  - Bash(.venv/bin/python -m build prepare*)
  - Bash(.venv/bin/python -m build apply *)
---

# build-prose

You are the loop driver for the dnd-data build's authoring step. You own all phases: kick off `prepare` to stage slices, get the publisher's sign-off on the plan for each session entry, dispatch a sub-agent per pending slice to write JSON results, run the editor loop on the drafts that call for one, dispatch an independent verify sub-agent to fact-check them, get the publisher's sign-off on each finished session entry, then kick off `apply` to validate, persist authored prose, and render the site.

The publisher is the user. Two stops in this procedure wait for them, and nothing that reaches a stop goes forward without their yes.

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
4. **Plan stop** (the first sign-off): the manifest has a top-level `plan` map keyed by transformer name (currently just `append-sessions`), each entry carrying `prompt_body`, `schema`, and `model`. For every pending slice whose `transformer` is a key in that map, before it is authored:
   - If `<run-dir>/context/<stem>.plan.json` already exists (a resumed run whose plan was approved), skip to step 5 with it.
   - Otherwise dispatch the planner, round `n` starting at 1:
     - `subagent_type: "general-purpose"`
     - `model`: `manifest["plan"][transformer]["model"]`.
     - **Prompt body** (for round 1, omit the last two files and the sentence about them):

           You are acting as the plan-sessions planner for the [transformer]
           transformer. Read these files only:

           - prompt body: <run-dir>/[plan.prompt_body]
           - schema: <run-dir>/[plan.schema]
           - slice input: <run-dir>/[pending]
           - the plan the publisher sent back: <run-dir>/results/[stem].plan-[n-1].json
           - the publisher's notes on it: <run-dir>/results/[stem].plan-[n-1].notes.json

           Plan again from the publisher's notes. Produce a single JSON
           object that conforms to the schema. Do not include any prose,
           markdown, or commentary — only the JSON document. Write it to:

           <run-dir>/results/[stem].plan-[n].json

           Do not edit any other file. Do not run any other tool besides
           Read (on the paths above) and Write (on the plan path).

   - Read the plan. If the file is missing or not valid JSON, log the slice in `<run-dir>/failures.json` (append), leave it pending, and move on.
   - Show the plan to the publisher as lines: line 1 the through-line, then one line per paragraph (`P<k>: <says>`, the planner's plain-words note of what the paragraph is there to tell the reader, verbatim), then one line for the silent roll, then one line saying whether the paragraph order is the log's order. Not `subject`, `built_from`, `opens_on` or `why_this_order`; the user can ask for them. These are bullet points of the story, not its prose: the prose is judged at the publisher stop. Never rewrite a `says` into a list of the log's events.
     - If the tool `mcp__chronicle-review__review` is available, call it with `title` ("Plan <n>: session <key>"), those `lines`, and `notes_path` = `<run-dir>/results/<stem>.plan-<n>.notes.json`. It opens a pane and returns at once. End the turn and wait. When the publisher presses Approve, Send back or Stop, the plugin writes `{verdict, notes:[{line, quote, note}]}` to `notes_path` and sends a prompt naming the verdict and the path; on that prompt, read the file and continue the procedure from here. `verdict` `approve` is Approve below, `notes` is Notes, `stop` is Stop.
     - Otherwise print the lines and ask with AskUserQuestion, one question, two options: **Approve** and **Stop**, worded so the user knows that typing under Other is notes for a new plan. On notes, write `{"verdict": "notes", "notes": [{"line": 0, "quote": "", "note": "<their text>"}]}` to the same `notes_path`.
   - **Approve**: copy the plan to `<run-dir>/context/<stem>.plan.json` (create `context/` if needed). This is the approved plan every later step reads.
   - **Notes**: the notes file is in place; dispatch the planner again as round `n+1`. There is no round limit; the publisher ends it.
   - **Stop**: leave the slice in `pending/` with no approved plan. It will be reported as pending by apply and picked up on resume.
   - A slice with no approved plan is not authored in this run.
5. **Author.** Dispatch sub-agents in batches of up to 5 in a single message:
   - `subagent_type: "general-purpose"`
   - `model`: the entry's `model` field (`sonnet`, `opus`, or `fable`).
   - **Prompt body** (substitute the bracketed fields):

         You are acting as the [transformer] transformer. Read these
         three files only:

         - prompt body: <run-dir>/[prompt_body]
         - schema: <run-dir>/[schema]
         - slice input: <run-dir>/[pending]

         Produce a single JSON object that conforms to the schema. Do
         not include any prose, markdown, or commentary — only the
         JSON document. Write it to:

         <run-dir>/[result]

         Do not edit any other file. Do not run any other tool besides
         Read (on the three paths above) and Write (on the result path).

     For a slice with an approved plan (any transformer in the `plan` map), the file list is four, not three. Add after the slice input:

         - the plan the publisher approved: <run-dir>/context/[stem].plan.json

     and say "four files" in place of "three files". For `append-sessions` only, also append this, because its brief tells the writer to ask when it cannot tell whether the company knows something in the reference:

         One exception: if the prompt body tells you to ask before using
         something, you may use AskUserQuestion, once, for that.

6. After every sub-agent in the batch returns, check `results/<stem>.json`:
   - If the file exists and parses as JSON, move `pending/<stem>.json` to `done/<stem>.json`.
   - If not, leave the pending file in place and log the slice in `<run-dir>/failures.json` (append, not overwrite).
7. Repeat batches until `pending/` only contains slices that have failed at least once or have no approved plan. Do not retry inside the same skill run — the user gets to decide whether to edit the slice or prompt first.
8. **Edit loop** (a reader's critique, which the author revises against): the manifest has a top-level `edit` map keyed by transformer name (currently just `append-sessions`), each entry carrying `prompt_body`, `schema`, `model`, and `max_rounds`. For every manifest slice whose `transformer` is a key in that map and which now has a `results/<stem>.json` file, run up to `max_rounds` rounds. In each round `n` (starting at 1):
   - **Critique.** Dispatch the editor:
     - `subagent_type: "general-purpose"`
     - `model`: `manifest["edit"][transformer]["model"]`.
     - **Prompt body** (the slice lives in `done/<stem>.json` once authored, else `pending/<stem>.json`; for round 1, omit the previous-critique line):

           You are the editor for the [transformer] transformer. You read
           in two stages, and the order matters: stage one is a reader's
           read, and you must not open the session slice until stage one
           is written to disk.

           Stage one. Read these files only, in this order:

           - editor prompt (your instructions): <run-dir>/[edit.prompt_body]
           - editor schema: <run-dir>/[edit.schema]
           - the chronicle so far (every earlier page): <run-dir>/[chronicle]
           - the plan the publisher approved: <run-dir>/context/[stem].plan.json
           - the previous round's critique: <run-dir>/results/[stem].edit-[n-1].json
           - the draft entry under review: <run-dir>/[result]

           Follow the editor prompt's stage one and write your critique,
           with `log_check` set to null, to:

           <run-dir>/results/[stem].edit-[n].json

           Stage two. Only after that file is written, read the session
           slice: <run-dir>/[slice path]. Follow the editor prompt's stage
           two, fill in `log_check`, and overwrite the critique path with
           the whole object. Do not change `through_line`. You may lower
           `verdict` to `redraft`, never raise it.

           Do not edit any other file. Use only Read (on the paths
           above) and Write (on the critique path).

     `[chronicle]` is the slice's `chronicle` field in the manifest
     (`context/<stem>.chronicle.json`), written by prepare for exactly this
     purpose.

   - Read the critique. If the file is missing or not valid JSON, keep the current draft and end the loop for this slice. If `verdict` is `accept`, end the loop for this slice.
   - **Revise.** If `verdict` is `revise`, dispatch the author again, with the same `model` as the authoring slice:

           You are acting as the [transformer] transformer, revising
           your own draft against an editor's notes. Read these six
           files only:

           - prompt body: <run-dir>/[prompt_body]
           - schema: <run-dir>/[schema]
           - slice input: <run-dir>/[slice path]
           - the plan the publisher approved: <run-dir>/context/[stem].plan.json
           - your draft: <run-dir>/[result]
           - the editor's notes: <run-dir>/results/[stem].edit-[n].json

           Revise the draft so that every note is addressed. Keep what
           the notes do not touch. The plan is the story, and every
           paragraph is one of its paragraphs. Every fact still comes
           from the slice, and nothing goes on the page the players do not
           have. Produce a single JSON object that conforms to the schema,
           the complete revised entry, not a reply to the notes, and
           overwrite:

           <run-dir>/[result]

           Do not edit any other file. Use only Read (on the six paths
           above) and Write (on the result path).

   - **Redraft.** If `verdict` is `redraft`, the shape is wrong and revision cannot fix it. Dispatch the author fresh, with the same `model` as the authoring slice:

           You are acting as the [transformer] transformer. Your last
           draft was rejected by the editor, and you are starting over.
           Read these six files only:

           - prompt body: <run-dir>/[prompt_body]
           - schema: <run-dir>/[schema]
           - slice input: <run-dir>/[slice path]
           - the plan the publisher approved: <run-dir>/context/[stem].plan.json
           - the rejected draft: <run-dir>/[result]
           - the editor's notes: <run-dir>/results/[stem].edit-[n].json

           The plan is the story this entry tells. Start from it and from
           the editor's first note, not from the rejected draft: do not
           keep its paragraphs or its opening. Follow the prompt body as
           if writing for the first time. Produce a single JSON object
           that conforms to the schema, the complete entry, and overwrite:

           <run-dir>/[result]

           Do not edit any other file. Use only Read (on the six paths
           above) and Write (on the result path). If the prompt body tells
           you to ask before using something, you may use AskUserQuestion,
           once, for that.

     If the revision or redraft returns nothing or invalid JSON, keep the previous draft and end the loop for this slice.
   - After `max_rounds` critiques the draft that stands goes forward to verify and then to the publisher, whatever the last verdict was. The publisher stop, not the editor, decides whether it ships. Critique files stay in `results/` for the record; `apply` never reads them.
   - Batch editor dispatches (and revision dispatches) across slices in the same batches-of-5 style; the rounds for one slice are sequential.
9. **Verify pass** (independent, same-build fact-check, after the edit loop has settled the prose): the manifest has a top-level `verify` map keyed by transformer name (currently just `append-sessions`). For every manifest slice whose `transformer` is a key in that map and which now has a `results/<stem>.json` file, dispatch one verify sub-agent (in the same batches-of-5 style):
   - `subagent_type: "general-purpose"`
   - `model`: `manifest["verify"][transformer]["model"]`.
   - **Prompt body** (substitute the bracketed fields; the slice lives in `done/<stem>.json` once authored, else `pending/<stem>.json`):

         You are the verify pass for the [transformer] transformer. Read
         these four files only:

         - verify prompt (your instructions): <run-dir>/[verify.prompt_body]
         - verify schema: <run-dir>/[verify.schema]
         - the session slice (source material): <run-dir>/[slice path]
         - the draft entry under review: <run-dir>/[result]

         Follow the verify prompt. It hands you the source material (the
         slice) and the draft entry. Return the FINAL entry as a single JSON
         object conforming to the verify schema — unchanged if the draft is
         accurate, corrected in the same voice if it is not. Overwrite the
         draft by writing your JSON to:

         <run-dir>/[result]

         Do not edit any other file. Use only Read (on the four paths above)
         and Write (on the result path).
   - The verified JSON replaces the draft in `results/<stem>.json`. If a verify sub-agent returns nothing or invalid JSON, leave the existing draft result in place. Verifying is idempotent, so a second `/build-prose <run-dir>` re-verifies safely.
10. **Publisher stop** (the second sign-off): for every slice whose `transformer` is a key in the `plan` map and which has a `results/<stem>.json` file, round `n` starting at 1:
    - Show the finished entry to the publisher as lines: the title, then one line per sentence of the summary with a blank line between paragraphs, then the silent roll one line each. Below it, one line per editor round with its verdict, and the run-dir path, where the critiques (`results/<stem>.edit-*.json`) and the plans sit until apply prunes the run.
      - If the tool `mcp__chronicle-review__review` is available, call it with `title` ("Entry: session <key>"), those `lines`, and `notes_path` = `<run-dir>/results/<stem>.publisher-<n>.json`. It returns at once; end the turn and wait for the plugin's prompt as in step 4, then read the file. Its `verdict` `approve` is Publish below, `notes` is Notes, `stop` is Stop.
      - Otherwise print the lines and ask with AskUserQuestion, one question, two options: **Publish** and **Stop**, worded so the user knows that typing under Other is notes for a revision. On notes, write `{"verdict": "notes", "notes": [{"line": 0, "quote": "", "note": "<their text>"}]}` to the same `notes_path`.
    - **Publish**: the result goes to apply as it stands.
    - **Notes**: read them. A note that is local to the sentence it quotes and supplies no new fact (name a thing the log names, cut a detail, reword a phrase) is applied by you, in place, in the result file, and the entry is shown again as round `n+1`: no writer run and no verify run for a change that cannot invent anything. Only when a note needs the record (a new fact, a reshaped paragraph, a scene retold) dispatch the author with the same `model` as the authoring slice:

          You are acting as the [transformer] transformer, revising
          your own entry against the publisher's notes. Read these six
          files only:

          - prompt body: <run-dir>/[prompt_body]
          - schema: <run-dir>/[schema]
          - slice input: <run-dir>/[slice path]
          - the plan the publisher approved: <run-dir>/context/[stem].plan.json
          - your entry: <run-dir>/[result]
          - the publisher's notes: <run-dir>/results/[stem].publisher-[n].json

          Revise the entry so that every note is addressed. Keep what the
          notes do not touch. The plan is the story. Every fact still comes
          from the slice, and nothing goes on the page the players do not
          have. Produce a single JSON object that conforms to the schema,
          the complete revised entry, and overwrite:

          <run-dir>/[result]

          Do not edit any other file. Use only Read (on the six paths
          above) and Write (on the result path).

      Then run the verify pass (step 9) on it again, and come back to this stop as round `n+1`. No sub-agent editor round: the publisher is the editor here. There is no round limit; the publisher ends it.
    - **Stop**: rename `results/<stem>.json` to `results/<stem>.held.json` and move `done/<stem>.json` back to `pending/<stem>.json`, so apply reports the slice pending and does not render. On resume, the approved plan in `context/` is reused and the slice is authored again from it; delete `context/<stem>.plan.json` first to be asked for a new plan.
11. **Apply**: run `.venv/bin/python -m build apply <run-dir>` via Bash. Always run it, even when some slices failed or were stopped — `apply` is safe to call with leftover pending slices (it just skips the render). Surface its stderr summary (applied / rejected / pending / marker / map / render) inline. On a fully successful run apply prunes the run dir, so everything the publisher might want to read has already been shown at the stops.
12. End with a one-line status:
   - All clean and render OK → `build complete`.
   - Anything rejected, stopped, or still pending → name what, and tell the user that `/build-prose <run-dir>` will resume from where it stopped.

## Constraints

- Never modify `build/authored/*.json`. The apply step does that.
- Never modify files under `<run-dir>/prompts/`. They are the frozen reference.
- Never write an editor critique, a plan, or publisher notes to a slice's result path. Critiques go to `results/<stem>.edit-<n>.json`, plans to `results/<stem>.plan-<n>.json` and `context/<stem>.plan.json`, publisher notes to `results/<stem>.plan-<n>.notes.json` and `results/<stem>.publisher-<n>.json`.
- Never author a planned slice without an approved plan, and never run apply with a planned slice's result in `results/<stem>.json` that the publisher has not said Publish to.
- Never run `build/render.py` directly. The apply step does that.
- If `manifest.json` is missing after prepare, print an error and exit.

## Failure handling

If a sub-agent returns nothing or returns invalid JSON, do not write a placeholder result. Leave the pending file in place. The apply step will report it as pending; the user can fix the prompt or slice and re-run `/build-prose <run-dir>` to resume.

If an editor or a revision sub-agent fails, the draft that already stands goes forward to verify and to the publisher stop. A failed critique never blocks a build; the publisher's stop is the gate.

A second `/build-prose <run-dir>` call is safe — it skips slices already moved to `done/`, reuses approved plans in `context/`, and retries anything still in `pending/`. Re-running the edit loop on an already-edited result starts the round count over, which is harmless.
