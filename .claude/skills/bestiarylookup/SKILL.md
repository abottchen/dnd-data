---
name: bestiarylookup
description: Look up a creature name in the 5etools bestiary source data and return the correct 5e.tools URL for it.
argument-hint: <creature name> (e.g., "Dragon Turtle" or "vegepygmies")
allowed-tools: Bash, Read, Grep
model: sonnet
context: fork
---

# 5etools Bestiary Lookup

Given a creature name in `$ARGUMENTS`, look it up in the 5etools bestiary source data and return the correct URL.

## Path resolution (required — do this before any Read/Grep)

This skill references external data via `{{DATA_ROOT}}`. Resolve it once at skill start:

```bash
(cd .claude/ext/5etools-src && pwd -P)
```

Substitute the printed absolute path for every `{{DATA_ROOT}}` below when calling Read or Grep. For Bash/jq, you may use the relative path `.claude/ext/5etools-src/...` directly — `$PWD` is the project root. If the `cd` fails, the symlink is missing; tell the user to set it up per `.claude/ext/README.md` and stop.

## Data Location

The 5etools source bestiary files are at:
```
{{DATA_ROOT}}/data/bestiary/
```

Each file contains a `monster` array with objects like `{"name": "Dragon Turtle", "source": "XMM", ...}`.

## Lookup Procedure

### 1. Search for the creature

Use jq to search across bestiary files. The creature name match should be **case-insensitive**. Search ALL bestiary files at once:

```bash
for f in {{DATA_ROOT}}/data/bestiary/bestiary-*.json; do
  jq --arg n "<creature_name>" \
    '.monster[] | select(.name | ascii_downcase == ($n | ascii_downcase)) | {name, source}' "$f" 2>/dev/null
done
```

If no exact match is found, try a partial/fuzzy match:
```bash
for f in {{DATA_ROOT}}/data/bestiary/bestiary-*.json; do
  jq --arg n "<creature_name>" \
    '.monster[] | select(.name | ascii_downcase | contains($n | ascii_downcase)) | {name, source}' "$f" 2>/dev/null
done
```

### 2. Select the best source

A creature may appear in multiple sourcebooks (reprints). Choose the source in this priority order:

1. **XMM** (2024 Monster Manual) — preferred, most current
2. **ToA** (Tomb of Annihilation) — module-specific creatures
3. **MPMM** (Mordenkainen Presents: Monsters of the Multiverse) — reprints of older content
4. **VGM** (Volo's Guide to Monsters)
5. **MM** (2014 Monster Manual) — fallback

If the creature exists in XMM, always use that. If it only exists in ToA, use ToA. If it was in ToA but was reprinted in MPMM, prefer MPMM (since 5etools may not resolve the older _toa hash for reprinted creatures).

### 3. Build the URL

From the matched `name` and `source` fields:

1. **Lowercase** the name
2. **Replace spaces** with `%20`
3. **Encode parentheses**: `(` → `%28`, `)` → `%29`
4. **Lowercase** the source
5. Construct: `https://5e.tools/bestiary.html#<encoded_name>_<source>`

**Examples:**
| Name | Source | URL |
|---|---|---|
| Dragon Turtle | XMM | `https://5e.tools/bestiary.html#dragon%20turtle_xmm` |
| Vegepygmy | MPMM | `https://5e.tools/bestiary.html#vegepygmy_mpmm` |
| Aldani (Lobsterfolk) | ToA | `https://5e.tools/bestiary.html#aldani%20%28lobsterfolk%29_toa` |
| Yuan-ti Malison (Type 1) | MM | `https://5e.tools/bestiary.html#yuan-ti%20malison%20%28type%201%29_mm` |
| Faerie Dragon (Green) | MM | `https://5e.tools/bestiary.html#faerie%20dragon%20%28green%29_mm` |

### 4. Handle plural input

The user may provide a plural creature name (e.g., "vegepygmies", "ghouls", "winter wolves"). The bestiary always uses the **singular** stat block name. If the initial search finds no match:

- Try removing trailing "s", "es", or "ies" → "y"
- Try common irregular plurals: "wolves" → "wolf", "mice" → "mouse"
- Report the singular name that was matched

### 5. Handle variant creatures

Some creatures have variants distinguished by parenthetical suffixes:
- **Faerie Dragon** has color variants: (Blue), (Green), (Indigo), (Orange), (Red), (Violet), (Yellow)
- **Yuan-ti Malison** has type variants: (Type 1), (Type 2), (Type 3)

If the user provides just the base name (e.g., "faerie dragon"), list all available variants and their URLs.

## Output

Report:
1. **Matched name** (exact name from the bestiary data)
2. **Source** (sourcebook abbreviation)
3. **URL** (the full 5e.tools bestiary URL)
4. **Markdown link** (ready to paste): `[Creature Name](url)`

If multiple sources exist, show all matches with the recommended one marked.

If no match is found, say so clearly and suggest checking the spelling or trying alternate names.
