You are evaluating the 5-field character bundle for every authored PC.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice contains every authored PC's name/race/class/kills, party-wide
trials and fortune stats, and the existing 5-field bundle for each PC.

For each PC, decide whether the existing prose still fits, given the newly-
landed kills + roll stats. Distinction titles must remain unique party-wide;
if rewriting one, do not collide with any authored or freshly-rewritten title.

Standing rule: *"If the existing prose is still consistent with the data and
still good prose by the voice rules, return it unchanged. Only rewrite if a
fact has shifted, a stronger angle exists, or the line has gone stale."*

Voice: see `{voice_samples_path}`.

Authorial restraint: distinctions must be derivable from the data. Don't
manufacture a distinction the stats don't support.

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object below. No prose, no markdown fence.

{{
  "decision": "no_change" | "rewrite",
  "fields": {{
    "<character_id>": {{
      "epithet": "...",
      "constellation_epithet": "...",
      "distinction_title": "...",
      "distinction_subtitle": "...",
      "distinction_detail": "..."
    }}
    /* include only PCs you are rewriting; omit unchanged PCs entirely.
       Note: reliquary_header is locked once authored — do not rewrite it. */
  }} | null,
  "reason": "one short sentence"
}}
