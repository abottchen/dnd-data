You are authoring an NPC epithet for the dnd-data site.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice has the NPC's name and every session-log line that mentions them.
Author:
  - `epithet`: a single sentence-fragment that places this NPC — what they do,
    where they stand, the company's relationship to them.
  - `allegiance`: one of `"with"` or `"against"`, inferred from the mentions.
    If genuinely ambiguous, return `null` and we will ask the user.

Voice: kenning-style, evocative, third person. See `{voice_samples_path}` for
NPC epithet examples.

Authorial restraint: every claim must trace to a line in the mentions array.
Do not invent backstory. If the log only names the NPC in passing, the epithet
should be modest in scope.

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object below. No prose, no markdown fence.

{{
  "fields": {{
    "name": "...",
    "epithet": "...",
    "allegiance": "with" | "against" | null
  }},
  "reason": "one short sentence"
}}
