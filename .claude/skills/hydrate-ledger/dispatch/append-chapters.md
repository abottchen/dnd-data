You are authoring a chapter title and epigraph for the dnd-data site.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice describes the session that opens this chapter: its session id and
narrative text. Author 2-3 candidate `title` + `epigraph` pairs. The user
will pick. Each candidate:
  - `title`: short evocative phrase, ~3-6 words. Names the chapter's spine.
  - `epigraph`: one short sentence, the saga-fragment caption that opens
    the chapter on the page.

Voice: see `{voice_samples_path}`. Cool, compact, slightly elegiac. No chrome.

Authorial restraint: do not invent plot beyond what the slice narrative names.

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object below. No prose, no markdown fence.

{{
  "fields": {{
    "candidates": [
      {{ "title": "...", "epigraph": "..." }},
      {{ "title": "...", "epigraph": "..." }}
    ]
  }},
  "reason": "one short sentence"
}}
