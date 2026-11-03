---
name: write-chronicle
description: Use when a newly logged session in data/session-log.json needs its Chronicle entry, when the user asks for the session N story, chapter, write-up or next Volo chapter, when a chronicle draft needs the DM's review comments applied, or when build/render.py fails with a MISSING sessions.json entry.
---

# write-chronicle

Each Chronicle entry is one chapter of a novel narrated by Volothamp Geddarm, built from a single session's log and transcript and continuing the chapters already published in `build/authored/sessions.json`. The DM reviews a draft before anything touches the authored store. Form and voice are in `voice.md`; facts the DM has ruled on are in `facts.md`. Read both before drafting.

## Sources

| Source | Use it for |
|---|---|
| `data/session-log.json`, the entry whose `day` is the session | What happened, in order. The authority when sources disagree. `realDate` is the entry date; `iuDay`/`iuMonth`/`iuYear` the in-world date. |
| `data/transcripts/session-<realDate>.txt` | Texture, the table's reasoning, and the actual spoken lines. Read all of it. It is full of real first names and family details; none may carry into the draft. |
| `data/party.json` | Roster, classes, features, and each character's kills for the date. |
| `build/authored/sessions.json` | What the reader already knows. Grep it before introducing a name, place or device as new. The latest entry is the chapter being continued. |
| `build/.chronicle/session-<N-1>/story.md` | The previous chapter in full markdown form. Match its structure. |
| `facts.md` and `build/.chronicle/rulings.jsonl` | DM answers from earlier reviews. Check before stating a motive, a location or a timeline. |
| `.claude/ext/5etools-src/data/bestiary/*.json` | Stat blocks for named NPCs and creatures (Dragonbait, Artus Cimber, the monsters killed): gear, size, what their attacks look like. Use the `bestiarylookup` skill or grep the JSON. Never a stat as a number. |
| `.claude/ext/dnd-toa/docs/*.md` | Read-aloud description of places and creatures, for what the company saw. Never a name, motive or secret the company has not learned. `dm-notes-general.md` is never a source. |

## Procedure

1. Read every source above. Note each question a reader would ask that the sources do not answer, including staging (who was in which room, who heard what). Those go to the DM as questions, not into the prose as guesses; until answered, write only what the sources state.
2. Draft `build/.chronicle/session-<N>/story.md` in the chapter form in `voice.md`. Alongside it keep `build/.chronicle/session-<N>/quotes.md`, the quotes ledger: one line per quotation in the draft, giving the transcript timestamp, the words as transcribed, and the recast line. A quotation that cannot be given a timestamp is not a quotation; narrate the beat or cut it. The recast may change wording, never add a clause the transcript does not have.
3. Run `python3 .claude/skills/write-chronicle/scripts/check_story.py build/.chronicle/session-<N>/story.md` and fix every line it reports. Then read the whole draft once as the DM would, against the checklist at the end of `voice.md`.
4. Render the review page: `python3 .claude/skills/write-chronicle/scripts/md2review.py build/.chronicle/session-<N>/story.md build/.chronicle/session-<N>/review.html --session <N>`. Publish `review.html` as a private artifact (claude-artifacts `publish_files`, title = the chapter title) and give the DM the link.
5. For each DM comment: fix `story.md`, re-run the check, re-render, republish the same artifact, reply on the thread, resolve it. When a comment corrects a fact about the world or the party, record it in `facts.md` (standing) or `build/.chronicle/rulings.jsonl` (session-specific) so it is never re-invented.
6. Only when the DM says the chapter is final: `python3 .claude/skills/write-chronicle/scripts/story2entry.py build/.chronicle/session-<N>/story.md --session <N> --date <realDate>` writes the entry into `build/authored/sessions.json`. Then run `.venv/bin/python build/render.py`: the only validation errors allowed are `MISSING kills` for the new session, which `/build-prose` authors next. A `MISSING`, `ORPHAN` or `MALFORMED` sessions error means the entry is wrong; fix it before handing off. The DM then runs `/build-prose` for the kills, NPCs and refreshes, and commits.

## Hard rules

- `sessions.json` is written by `story2entry.py`, on the DM's word, never by hand and never before.
- No real player name, handle or family detail from any source.
- Nothing the company has not learned: no decoded scents, no hidden identities, no DM notes.
