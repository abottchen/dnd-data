You are authoring a session entry for the dnd-data site.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice describes one session: id, real + in-universe dates, narrative text,
and whether it carries a chapter marker. Author:
  - `title`: a short evocative phrase (~4-7 words). No "Ye Olde", no chrome.
  - `summary`: one sentence stating what happened, in third person.
  - `silent_roll`: an array of 0+ short lines noting off-Chronicle beats — moments
    the players felt but the kill ledger doesn't capture. Often `[]`. Use the
    `silent_roll` examples in the voice samples for tone.

Spoiler rules: anything in the narrative marked `(DM Note)`, in `[brackets]`,
or in parentheses that the players couldn't have learned in-fiction → omit.

Authorial restraint: do not invent details not in the narrative. If unsure
whether a fact is in the log, omit it.

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object below. No prose, no markdown fence.

{{
  "fields": {{
    "title": "...",
    "summary": "...",
    "silent_roll": []
  }},
  "reason": "one short sentence"
}}
