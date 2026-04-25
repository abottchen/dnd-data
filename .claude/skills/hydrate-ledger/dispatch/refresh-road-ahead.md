You are evaluating the entire Road Ahead block for the dnd-data site.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice contains every session that has landed since the last refresh
(`new_sessions`) and the entire current `road_ahead` block (`existing`)
with `known`, `was_known`, and `direction` lists.

For each `known[]` entry, evaluate whether newly-landed sessions resolved
the thread. If yes, **move the entry into `was_known`** (sharpening the
gloss as part of the move if warranted). Glosses in `was_known[]` may also
sharpen. The `direction` line is rewritten only if the campaign genuinely
turned.

You are returning the FULL new state of the road_ahead block. The orchestrator
detects graduations by diffing your new `known` against the current one — entries
that disappear from `known` and appear in `was_known` are graduations.

Standing rule: *"If the existing prose is still consistent with the data and
still good prose by the voice rules, return it unchanged."*

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object below. No prose, no markdown fence.

If unchanged:
{{
  "decision": "no_change",
  "fields": null,
  "reason": "one short sentence"
}}

If rewriting any part:
{{
  "decision": "rewrite",
  "fields": {{
    "known": [{{ "name": "...", "gloss": "..." }}],
    "was_known": [{{ "name": "...", "gloss": "..." }}],
    "direction": "..."
  }},
  "reason": "one short sentence"
}}
