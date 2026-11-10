---
name: chronicle
description: Write the Chronicle entry for a session as a Volo-narrated story chapter, put it up as an artifact for review, apply the review comments, and write it into build/authored/sessions.json. Use when the user says "write the chronicle", "chronicle session N", "/chronicle", or asks for the story of the last session. Takes an optional session number; defaults to the latest session in the log.
---

# chronicle

Write one session's Chronicle entry, get it reviewed, and put it in place. Three phases: draft, review, write into place. Stop after each of the first two and wait for the user.

The target session is the argument if one was given, otherwise the last entry in `data/session-log.json`. Call it N below.

## 1. Draft

Read, in this order:

- The session N entry in `data/session-log.json`. This says what the party did. It is the authority on events when it and the transcript disagree.
- The previous session's entry in `build/authored/sessions.json`. This is the voice, the length, and the place the story left off.
- `data/party.json` for the current party.
- The table transcript for the session's real date: `data/transcripts/session-YYYY-MM-DD.txt`, or `../dnd-toa/scribe/transcripts/` if it has not been copied over yet. Read all of it. It supplies specific detail and quotable lines.
- The source material in `../dnd-toa` for the places, NPCs and events the session touched: `data/5etools/adventure-toa.json` (Tomb of Annihilation), `docs/Lost City of Mezro.md`, `docs/A City on the Edge.md`. Search it for the session's names; don't read it whole. Work out where the party stands in each storyline.

Then write the chapter:

- A compelling narrative of everything the party did in the session, in the form of an action-oriented fantasy novel like The Lord of the Rings. Paint a vivid picture of the world and treat the characters as the epic heroes of the story.
- Narrated by Volo, with his voice, flourishes and asides, as in the previous entry. Signed `V.G.` on its own last line.
- It picks up where the previous entry left off, as the next section of one long story. Characters, items and concepts the reader has already met are not re-introduced.
- No game-mechanic language. Translate dice, spells-as-rules, hit points, turns and saves into narrative.
- Quotes come from the transcript, recast into the chronicle's diction (no contractions, table chatter removed), with substance and tone preserved.
- About the same length as the previous entry.
- The session log shows what they did; the source material fleshes out the world around it. Use the source for colour, never to reveal what the party has not learned. Volo may hint that he knows more and promise it for a later chapter.
- Nothing from DM-only material: `../dnd-toa/dm-notes-*.md`, the log's "DM notes" sections, or anything in the log marked as not reached this session.
- No real player names anywhere (see Privacy in `CLAUDE.md`).
- Plain paragraphs separated by blank lines, no headings. A major scene change gets a paragraph of `* * *`.

Save it as `build/.chronicle/session-N/story.md`: a `# Title` line, the paragraphs, then `## Silent roll` with `- ` items or `(none)`.

If something is unclear, ask the user rather than guessing. When the draft is done, report where the party stands in each storyline, the judgement calls you made, and anything you could not pin down.

## 2. Review

Build `build/.chronicle/session-N/review.html` from `story.md` and publish it with the Artifact tool: a single reading column with each paragraph numbered in the margin so the user can cite one. Give the user the link.

The user reviews by commenting on the artifact. For each comment sent to you: read the thread, make the change in `story.md` and in the page, republish to the same link, and resolve the thread. `story.md` stays the source of truth.

Wait for the user to say the draft is good before going on.

## 3. Write into place

Append the entry to `build/authored/sessions.json`, in the shape `CLAUDE.md` gives under "Chronicle session entries":

```json
{"session": N, "date": "YYYY-MM-DD", "title": "…", "summary": "…", "silent_roll": []}
```

- `date` is the session's real date from the log.
- `summary` is the paragraphs of `story.md` joined with blank lines, title line excluded, `V.G.` included.
- Keep the file's existing formatting: `indent=2`, `ensure_ascii=False`, trailing newline.

Then check it with `validators.validate_sessions(load_data(Path("data"))["session_log"], entries)` and confirm it returns no errors. Don't render, commit or push; `/build-prose` and the user do that.
