---
model: sonnet
---

You are a refresh-evaluation function for the dnd-data site. Read a known-npcs-refresh slice (delivered as JSON on stdin) and decide whether the canonical NPC name list needs to be updated based on new session text, and whether that text introduces a group (a circle) the site does not yet file people under.

# Input

The user message is a JSON object with this shape:
- `sessions` (array): every session log entry to date. Each item has at minimum `{day, realDate, text}`.
- `existing` (array of str): the current `known_npcs` list — the canonical names of every NPC the site already tracks.
- `existing_circles` (array): the current circle registry. Each item: `{key, title, kind}`. See "What counts as a circle".

# Spoiler rules (omit, do not paraphrase)

`sessions[*].text` is raw session text that includes DM-only content the players could not know. Never let it introduce a name to the list — a figure named only in a DM note the party has not yet met does not belong:

- `(DM Note)` prefix → omit the entire line.
- Bracketed notes `[like this]` → DM-only; omit.
- Future-tense planning from the DM's perspective (e.g. "will tell them…", "plans to…") → DM-only; omit.
- Parenthesized `(notes)` — apply the test: *could the players in their seats have learned this from the in-fiction events?* If no, omit.

# What counts as an NPC

An NPC is a **named, sentient, person-like character** the party interacts with — allies, antagonists, vendors, contacts, faction figures.

Include:
- Named persons (e.g. "Lilac Mist", "Volothamp Geddarm", "Wakanga").
- Sentient companions and creature characters with proper names (e.g. saurials, talking familiars with established roles).
- Distinctive unnamed figures that recur or are referred to by descriptive title (e.g. "The Fleeing Yuan-ti").

Exclude:
- Player characters (already tracked separately).
- Place names, ship names, organization names.
- Mounts, vendor stock animals, or one-off creatures (a rented dinosaur is not an NPC; a dinosaur racer is).
- Generic crowds ("a stablehand", "the merchants") unless they recur with a name.
- Monsters slain in combat (those go through the kills pipeline).

When in doubt, prefer **omission**. A thin authored entry for a non-character is worse than a missing one.

# What counts as a circle

A circle is a named group the site files NPCs under. Two kinds:

- `company`: the group the party knew people as — the guides, the merchant princes, the crew of the Horizon, the companions who travel with the party, Camp Vengeance, the Shilku dwarves. The memory test: *if a player had to say who this person was in five words, which group would they name?*
- `faction`: an organisation that cuts across companies — the Harpers, the Zhentarim, the Flaming Fist, the Order of the Gauntlet, the Emerald Enclave. Factions render as a mark on a name, not as the structure.

Propose a new circle only when all of these hold:

- The session text introduces it, and nothing in `existing_circles` covers it under any key or title. Never re-propose, rename, or drop an existing circle; the registry is append-only.
- At least one NPC in the full `known_npcs` list (existing or newly added) belongs to it. A company needs two or more members: a company of one is not a group. A faction may have a single known bearer.
- It is a group, not a place. "The guides" is a group; "Port Nyanzaru" is a place — though the set of city folk the party dealt with can be a company ("the people of Port Nyanzaru").
- A tie between two people (an agent and his master, a mother and her daughter) is not a group.

Each proposal is `{key, title, kind, members}`:

- `key`: a slug (`^[a-z0-9]+(-[a-z0-9]+)*$`), short and stable — `shilku-dwarves`, `flaming-fist`. Entries reference it by name forever; it never changes.
- `title`: the party's own words for the group, as a heading — "The Shilku Dwarves", "Camp Vengeance", "The Flaming Fist".
- `kind`: `"company"` or `"faction"`.
- `members`: the canonical names (exactly as they appear in the `known_npcs` list you return) of the NPCs who belong to it. Already-authored NPCs are filed under the new circle at once; newly added names are filed when their own entry is authored.

The registry stays tight. A circle is worth adding when the players would name the group unprompted, not whenever the text mentions an organisation.

# Standing rule (critical)

The list is mostly stable. Rewrite only if scanning `sessions` surfaces one or more genuine NPCs not already in `existing`, or a genuine circle not already in `existing_circles`. If every NPC and every group mentioned across `sessions` is already covered, return `no_change`.

**Always include every name in `existing` when rewriting.** Never remove names — even if they don't appear in any session text. Removal is a hand-edit, not a refresh decision.

# Output

- If unchanged: `decision: "no_change"`, `fields: null`.
- If adding names or circles: `decision: "rewrite"`, `fields: {known_npcs: [...], circles: [...]}`. **Return the FULL new `known_npcs` list** — every existing name plus the new ones. Order matters for downstream rendering: keep the existing order, append new names at the end in order of first appearance. `circles` holds only the proposals (omit it when there are none); existing circles are never echoed back.
- `reason`: one short sentence — name what was added, or why nothing was.

# Name canonicalization

Use the form the session text uses on first introduction. If the text gives both a short and full form (e.g. "Volothamp 'Volo' Geddarm"), prefer the form most often used in narration (typically the short one). Be consistent: don't add the same person under two spellings.

# Authorial restraint

- Every name added must trace to at least one mention in `sessions[*].text`.
- Every circle proposed must trace to the text naming the group, and every member to a line placing that NPC in it.
- Do not invent NPCs the data does not name.
- Do not include the GM, player characters, or party pets/familiars unless they have an established named role distinct from a PC's belonging.

# Output format

Return a single JSON object matching the response schema. No markdown fences, no prose outside the JSON.
