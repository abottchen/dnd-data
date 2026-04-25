You are authoring the character bundle (6 fields per PC) for one or more new
party members on the dnd-data site.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice contains:
  - `new_pcs`: list of unauthored PCs (id, name, race, class, kills)
  - `trials_per_char`: kill counts + methods + XP by character
  - `fortune_by_char`: rolls + averages + crits + fumbles by character
  - `existing_distinction_titles`: titles already taken by authored PCs — your
    chosen `distinction_title` for each new PC must not collide with these or
    with each other.

For each new PC, author the 6-field bundle:
  - `epithet`: the prose oneliner under the character's name. Kenning-style,
    evocative of race/lineage and signature trait.
  - `reliquary_header`: title for the kill-list panel. A short character-voice
    phrase ("Fallen by his tongue", "Slain by the storm").
  - `constellation_epithet`: one line for the constellation portrait caption.
  - `distinction_title`: short, unique party-wide. Must not collide with any
    title in `existing_distinction_titles`.
  - `distinction_subtitle`: one line elaborating the distinction.
  - `distinction_detail`: HTML-allowed string, e.g. "<b>3</b> kills &middot;
    Vicious Mockery". Names the supporting stat.

Voice: see `{voice_samples_path}`.

Authorial restraint: derive the distinction from the actual stats. Do not
manufacture flavor that the data does not support.

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object below. No prose, no markdown fence.

{{
  "fields": {{
    "<character_id>": {{
      "epithet": "...",
      "reliquary_header": "...",
      "constellation_epithet": "...",
      "distinction_title": "...",
      "distinction_subtitle": "...",
      "distinction_detail": "..."
    }}
    /* one entry per new PC */
  }},
  "reason": "one short sentence"
}}
