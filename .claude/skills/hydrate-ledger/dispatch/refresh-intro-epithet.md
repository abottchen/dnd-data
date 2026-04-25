You are evaluating the campaign-spine intro epithet at the top of the page.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice contains:
  - `new_sessions`: every session that has landed since the last refresh
  - `road_ahead_known`: the current Road Ahead `known[]` list
  - `existing`: the current intro_epithet string

The intro_epithet is the tightest summary of the campaign's spine. Decide
whether newly-landed sessions or shifts in `road_ahead_known` make the
existing line stale.

Standing rule: *"If the existing prose is still consistent with the data and
still good prose by the voice rules, return it unchanged. Only rewrite if a
fact has shifted, a stronger angle exists, or the line has gone stale."*
This line is mostly stable; rewrite only on genuine spine shifts.

Voice: campaign-spine tier — names what the campaign DOES, places it,
names what it threatens. See `{voice_samples_path}`.

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object below. No prose, no markdown fence.

If unchanged:
{{
  "decision": "no_change",
  "fields": null,
  "reason": "one short sentence"
}}

If rewriting:
{{
  "decision": "rewrite",
  "fields": {{ "intro_epithet": "..." }},
  "reason": "one short sentence"
}}
