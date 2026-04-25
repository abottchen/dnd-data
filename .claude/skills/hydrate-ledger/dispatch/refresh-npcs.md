You are evaluating whether an NPC's epithet still fits the data.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice contains every session-log mention of this NPC and the existing
epithet + allegiance. Decide whether the existing prose still fits, given any
newly-landed mentions.

Standing rule: *"If the existing prose is still consistent with the data and
still good prose by the voice rules, return it unchanged. Only rewrite if a
fact has shifted, a stronger angle exists, or the line has gone stale."*

Authorial restraint: every claim in the new epithet must trace to a line in
the mentions. If you cannot point to a line, return `no_change`.

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object. No prose, no markdown fence.

If unchanged:
{{
  "decision": "no_change",
  "fields": null,
  "reason": "one short sentence"
}}

If rewriting:
{{
  "decision": "rewrite",
  "fields": {{ "epithet": "...", "allegiance": "with" | "against" }},
  "reason": "one short sentence"
}}
