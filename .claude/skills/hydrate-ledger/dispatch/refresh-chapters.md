You are evaluating whether a chapter's title + epigraph still fit the data.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice contains every session inside the chapter and the existing
`title` + `epigraph`. A new session has landed inside this chapter — decide
whether the existing prose still fits.

Standing rule: *"If the existing prose is still consistent with the data and
still good prose by the voice rules, return it unchanged. Only rewrite if a
fact has shifted, a stronger angle exists, or the line has gone stale."*

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
  "fields": {{ "title": "...", "epigraph": "..." }},
  "reason": "one short sentence"
}}
