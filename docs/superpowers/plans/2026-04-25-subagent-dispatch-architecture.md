# Subagent Dispatch Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `hydrate-ledger`'s monolithic context loading with a slice-helper + parallel-subagent dispatch model so the orchestrator's context stays roughly constant as the campaign grows.

**Architecture:** A new gitignored `helpers.py` module exposes parameterless CLI subcommands (`append-*`, `refresh-*`). Each helper introspects upstream + authored state, writes per-entity slice JSON to a per-run temp directory, and prints only metadata to stdout. The skill iterates the metadata, dispatches one subagent per non-empty slice in a single parallel batch via the Agent tool, validates each subagent's returned JSON decision object, and writes results to `authored/*.json`. Final step: `build.py` runs as today.

**Tech Stack:** Python 3 (existing `.venv` with Jinja2), pytest for the helper tests, bash for the manual smoke harness, Claude Code Agent tool for parallel subagent dispatch.

**Spec:** `docs/superpowers/specs/2026-04-25-subagent-dispatch-architecture-design.md`

---

## File Structure

| Path | Status | Versioned | Purpose |
|---|---|---|---|
| `tests/fixtures/sample_party.json` | new | yes | synthetic party for helper tests |
| `tests/fixtures/sample_session_log.json` | new | yes | synthetic session log |
| `tests/fixtures/sample_dicex_rolls.json` | new | yes | minimal dice file (helpers don't need rolls but `load_data` requires the file) |
| `tests/fixtures/sample_authored/*.json` | new | yes | minimal authored entries for diffing |
| `tests/test_helpers.py` | new | yes | pytest cases for helper subcommands; skips if skill absent |
| `.claude/skills/hydrate-ledger/helpers.py` | new | no | CLI module; one subcommand per category |
| `.claude/skills/hydrate-ledger/dispatch/append-kills.md` | new | no | append-pass agent prompts |
| `.claude/skills/hydrate-ledger/dispatch/append-sessions.md` | new | no | "" |
| `.claude/skills/hydrate-ledger/dispatch/append-chapters.md` | new | no | "" |
| `.claude/skills/hydrate-ledger/dispatch/append-npcs.md` | new | no | "" |
| `.claude/skills/hydrate-ledger/dispatch/append-characters.md` | new | no | "" |
| `.claude/skills/hydrate-ledger/dispatch/refresh-chapters.md` | new | no | refresh-pass agent prompts |
| `.claude/skills/hydrate-ledger/dispatch/refresh-npcs.md` | new | no | "" |
| `.claude/skills/hydrate-ledger/dispatch/refresh-characters.md` | new | no | "" |
| `.claude/skills/hydrate-ledger/dispatch/refresh-road-ahead.md` | new | no | "" |
| `.claude/skills/hydrate-ledger/dispatch/refresh-intro-epithet.md` | new | no | "" |
| `.claude/skills/hydrate-ledger/test_harness.sh` | new | no | manual smoke harness |
| `.claude/skills/hydrate-ledger/SKILL.md` | modify | no | rewrite Workflow + Error handling sections; remove evolvable-entry data-context table |

---

## Conventions used in this plan

- **Helper module path:** `.claude/skills/hydrate-ledger/helpers.py` (referred to as `HELPERS` below). Tests dynamically import via `sys.path` insertion.
- **Repo root in helpers:** computed as `Path(__file__).resolve().parents[3]` (the file lives at `<repo>/.claude/skills/hydrate-ledger/helpers.py`, so `parents[3]` is `<repo>`).
- **Temp dir:** `tempfile.mkdtemp(prefix="hydrate-")` per CLI invocation. Path is reported on stdout in the metadata. Tests pass an explicit temp dir.
- **Output schema (every subcommand):** `{"slices": [{"key": str, "path": str, "count": int}, ...]}` printed as a single JSON line to stdout.
- **Build orientation:** Helpers `import build` from the repo root (added to `sys.path` at module load) so loaders aren't duplicated.
- **Commit messages:** prefix each commit per existing repo style: `feat:`, `test:`, `docs:`, `chore:`.

---

## Phase 1 — Scaffolding

### Task 1: Test fixtures + skip-aware test entry

**Goal:** Versioned synthetic data + a `tests/test_helpers.py` that imports the (gitignored) helpers module if present, skips otherwise.

**Files:**
- Create: `tests/fixtures/sample_party.json`
- Create: `tests/fixtures/sample_session_log.json`
- Create: `tests/fixtures/sample_dicex_rolls.json`
- Create: `tests/fixtures/sample_authored/kills.json`
- Create: `tests/fixtures/sample_authored/sessions.json`
- Create: `tests/fixtures/sample_authored/chapters.json`
- Create: `tests/fixtures/sample_authored/npcs.json`
- Create: `tests/fixtures/sample_authored/characters.json`
- Create: `tests/fixtures/sample_authored/site.json`
- Create: `tests/test_helpers.py`

- [ ] **Step 1: Create `tests/fixtures/sample_party.json`**

```json
{
  "members": [
    {
      "id": "anton",
      "name": "Anton Truebranch",
      "image": "anton-truebranch.png",
      "race": "Halfling",
      "class": "Bard",
      "kills": [
        {"date": "2026-04-19", "creature": "Goblin", "method": "Vicious Mockery"},
        {"date": "2026-04-23", "creature": "Bandit", "method": "Vicious Mockery"}
      ],
      "skills": {"Persuasion": {"mod": 5}}
    },
    {
      "id": "vex",
      "name": "Vex Stormcaller",
      "image": "vex-stormcaller.png",
      "race": "Tiefling",
      "class": "Fighter",
      "kills": [
        {"date": "2026-04-19", "creature": "Goblin", "method": "Longsword"}
      ],
      "skills": {"Athletics": {"mod": 4}}
    }
  ]
}
```

- [ ] **Step 2: Create `tests/fixtures/sample_session_log.json`**

```json
{
  "entries": [
    {"day": 1, "realDate": "04/19/2026", "iuDay": "1", "iuMonth": "Kythorn", "iuYear": "1494",
     "text": "The company met Azlund the merchant in Daggerford. Two goblins fell at the gate."},
    {"day": 2, "realDate": "04/23/2026", "iuDay": "5", "iuMonth": "Kythorn", "iuYear": "1494",
     "text": "Bandits ambushed at the crossroads. --- Chapter II --- The road south opens."}
  ]
}
```

- [ ] **Step 3: Create `tests/fixtures/sample_dicex_rolls.json`**

```json
{"players": {}, "exportedAt": "2026-04-23T00:00:00Z"}
```

- [ ] **Step 4: Create `tests/fixtures/sample_authored/kills.json`**

```json
[
  {"character": "anton", "date": "2026-04-19", "creature": "Goblin", "method": "Vicious Mockery",
   "verse": "A goblin, undone by a halfling's whispered scorn.",
   "annotation": "Vicious Mockery — the only kill drawn with words alone."}
]
```

(Note: only Anton's first kill is authored. Anton's second kill, Vex's kill, and any new sessions/chapters/NPCs are unauthored — driving the append-pass tests.)

- [ ] **Step 5: Create `tests/fixtures/sample_authored/sessions.json`**

```json
[
  {"session": "I", "date": "2026-04-19", "title": "First Light",
   "summary": "The company gathered in Daggerford.", "silent_roll": []}
]
```

- [ ] **Step 6: Create `tests/fixtures/sample_authored/chapters.json`**

```json
[
  {"id": 1, "starts_at_session": "I", "title": "The Gathering", "epigraph": "Where the road begins."}
]
```

- [ ] **Step 7: Create `tests/fixtures/sample_authored/npcs.json`**

```json
[]
```

- [ ] **Step 8: Create `tests/fixtures/sample_authored/characters.json`**

```json
[
  {"id": "anton", "epithet": "of the Halflings, whose tongue cuts sharper than his blade",
   "reliquary_header": "Fallen by his tongue",
   "constellation_epithet": "his rolls yet unwritten",
   "distinction_title": "Sharpest Tongue",
   "distinction_subtitle": "the only kill drawn with words alone",
   "distinction_detail": "<b>1</b> kill &middot; Vicious Mockery"}
]
```

(Vex is in `party.json` fixture but not in authored — drives `append-characters` test.)

- [ ] **Step 9: Create `tests/fixtures/sample_authored/site.json`**

```json
{
  "intro_epithet": "A small ledger.",
  "page_title": "The Test Saga",
  "page_subtitle": "by the test fellowship",
  "road_ahead": {
    "known": [{"name": "Azlund's offer", "gloss": "the merchant's pitch awaits answer"}],
    "was_known": [],
    "direction": "south, eventually"
  },
  "gm": {"name": "GM", "epithet": "behind the screen", "meta": ""},
  "known_npcs": ["Azlund"],
  "footnote": "fixtures only",
  "refreshed_through_session": 1
}
```

- [ ] **Step 10: Create `tests/test_helpers.py` with skip-aware import**

```python
"""Tests for the hydrate-ledger slice helpers.

The helpers live in a gitignored skill directory so a fresh clone (or CI
without the skill installed) gracefully skips these tests. When the skill
IS installed, the helpers module is imported by manipulating sys.path —
the helpers themselves do the same dance for `import build`.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPERS_PATH = REPO_ROOT / ".claude/skills/hydrate-ledger/helpers.py"
FIXTURES = REPO_ROOT / "tests/fixtures"

if not HELPERS_PATH.exists():
    pytest.skip("hydrate-ledger skill not installed", allow_module_level=True)


def run_helper(subcommand: str, data_dir: Path, authored_dir: Path, temp_dir: Path) -> dict:
    """Run a helper subcommand as a subprocess (matches real invocation) and
    return parsed stdout JSON. data_dir / authored_dir / temp_dir override the
    helper's default repo-relative paths via env vars."""
    env = {
        "HYDRATE_DATA_DIR": str(data_dir),
        "HYDRATE_AUTHORED_DIR": str(authored_dir),
        "HYDRATE_TEMP_DIR": str(temp_dir),
        "PATH": "/usr/bin:/bin",
    }
    result = subprocess.run(
        [sys.executable, str(HELPERS_PATH), subcommand],
        capture_output=True, text=True, env=env, check=True,
    )
    return json.loads(result.stdout)


@pytest.fixture
def helper_env(tmp_path):
    """Materialize a writable copy of the fixture data + authored store +
    temp dir under tmp_path, so each test gets clean state."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(FIXTURES / "sample_party.json", data_dir / "party.json")
    shutil.copy(FIXTURES / "sample_session_log.json", data_dir / "session-log.json")
    shutil.copy(FIXTURES / "sample_dicex_rolls.json", data_dir / "dicex-rolls-2026-04-23.json")

    authored_dir = tmp_path / "authored"
    authored_dir.mkdir()
    for f in (FIXTURES / "sample_authored").iterdir():
        shutil.copy(f, authored_dir / f.name)

    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    return {"data_dir": data_dir, "authored_dir": authored_dir, "temp_dir": temp_dir}


def test_skill_directory_present():
    """Sanity check that the skip guard would have triggered if absent."""
    assert HELPERS_PATH.exists()
```

- [ ] **Step 11: Run the smoke test**

Run: `.venv/bin/pytest tests/test_helpers.py -v`
Expected: 1 test passes (`test_skill_directory_present`) OR all tests skip if helpers.py doesn't exist yet. Either is acceptable at this stage. We're confirming the skip-guard mechanic works.

- [ ] **Step 12: Commit**

```bash
git add tests/fixtures tests/test_helpers.py
git commit -m "test: scaffolding for hydrate-ledger slice helpers"
```

---

### Task 2: Helper module skeleton

**Goal:** Empty CLI dispatch, env-var-driven path overrides for tests, repo-root sys.path manipulation. No subcommands implemented yet — just the plumbing.

**Files:**
- Create: `.claude/skills/hydrate-ledger/helpers.py`
- Modify: `tests/test_helpers.py` (add a CLI smoke test)

- [ ] **Step 1: Write the failing test (CLI dispatch)**

Append to `tests/test_helpers.py`:

```python
def test_helpers_cli_unknown_subcommand_exits_nonzero(helper_env):
    result = subprocess.run(
        [sys.executable, str(HELPERS_PATH), "no-such-subcommand"],
        env={"HYDRATE_DATA_DIR": str(helper_env["data_dir"]),
             "HYDRATE_AUTHORED_DIR": str(helper_env["authored_dir"]),
             "HYDRATE_TEMP_DIR": str(helper_env["temp_dir"]),
             "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )
    assert result.returncode != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_helpers.py::test_helpers_cli_unknown_subcommand_exits_nonzero -v`
Expected: FAIL — file doesn't exist yet, subprocess raises FileNotFoundError or returns 127.

- [ ] **Step 3: Create the helper module skeleton**

Create `.claude/skills/hydrate-ledger/helpers.py`:

```python
#!/usr/bin/env python3
"""Slice helpers for the hydrate-ledger skill.

Each subcommand introspects upstream + authored state with no parameters,
writes per-entity slice JSON to a temp dir, and prints metadata to stdout.

Test override env vars:
  HYDRATE_DATA_DIR     — directory containing party.json / session-log.json / dicex-rolls-*.json
  HYDRATE_AUTHORED_DIR — directory containing kills.json / sessions.json / ... / site.json
  HYDRATE_TEMP_DIR     — directory to write slice files into (default: tempfile.mkdtemp)
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
import build  # noqa: E402


def _data_dir() -> Path:
    return Path(os.environ.get("HYDRATE_DATA_DIR", REPO_ROOT))


def _authored_dir() -> Path:
    return Path(os.environ.get("HYDRATE_AUTHORED_DIR", REPO_ROOT / "authored"))


def _temp_dir() -> Path:
    override = os.environ.get("HYDRATE_TEMP_DIR")
    if override:
        return Path(override)
    return Path(tempfile.mkdtemp(prefix="hydrate-"))


def _load_authored() -> dict:
    """Load all authored/*.json files, keyed by stem (kills, sessions, ...).

    site.json is loaded as a dict; the rest are lists.
    """
    auth_dir = _authored_dir()
    out = {}
    for stem in ("kills", "sessions", "chapters", "npcs", "characters"):
        out[stem] = json.loads((auth_dir / f"{stem}.json").read_text())
    out["site"] = json.loads((auth_dir / "site.json").read_text())
    return out


def _emit(slices: list[dict]) -> None:
    """Print metadata to stdout as a single JSON line."""
    print(json.dumps({"slices": slices}))


SUBCOMMANDS: dict[str, callable] = {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="hydrate-ledger slice helpers")
    parser.add_argument("subcommand", choices=sorted(SUBCOMMANDS.keys()) or ["__none__"])
    args = parser.parse_args(argv)
    if args.subcommand not in SUBCOMMANDS:
        parser.error(f"unknown subcommand: {args.subcommand}")
        return 2
    return SUBCOMMANDS[args.subcommand]()


if __name__ == "__main__":
    sys.exit(main())
```

Make it executable: `chmod +x .claude/skills/hydrate-ledger/helpers.py`

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_helpers.py -v`
Expected: both tests pass (`test_skill_directory_present`, `test_helpers_cli_unknown_subcommand_exits_nonzero`).

- [ ] **Step 5: Commit**

```bash
chmod +x .claude/skills/hydrate-ledger/helpers.py
git add tests/test_helpers.py
# helpers.py is gitignored; nothing to add for it.
git commit -m "test: helper module CLI smoke test"
```

---

## Phase 2 — Append-pass helpers + dispatch templates

Each task in this phase follows the same pattern: write a failing test, implement the helper subcommand, write the dispatch template, smoke-verify, commit.

The helper subcommands are registered by calling `SUBCOMMANDS["name"] = fn`. We add one entry per task.

---

### Task 3: `append-kills` helper + template

**Files:**
- Modify: `.claude/skills/hydrate-ledger/helpers.py` (add `cmd_append_kills`)
- Create: `.claude/skills/hydrate-ledger/dispatch/append-kills.md`
- Modify: `tests/test_helpers.py` (add test for `append-kills`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_helpers.py`:

```python
def test_append_kills_emits_slice_per_session_with_new_kills(helper_env):
    """Fixture has 3 kills total (Anton: Goblin Apr 19, Anton: Bandit Apr 23,
    Vex: Goblin Apr 19) and 1 authored kill (Anton's Goblin). Expect:
      - one slice for 2026-04-19 with count=1 (Vex's Goblin)
      - one slice for 2026-04-23 with count=1 (Anton's Bandit)
    """
    out = run_helper("append-kills", **helper_env)
    slices = out["slices"]
    by_key = {s["key"]: s for s in slices}
    assert set(by_key) == {"2026-04-19", "2026-04-23"}
    assert by_key["2026-04-19"]["count"] == 1
    assert by_key["2026-04-23"]["count"] == 1

    # Slice file for 04-19 should describe Vex's Goblin and contain narrative.
    body = json.loads(Path(by_key["2026-04-19"]["path"]).read_text())
    assert body["session"] == "I"
    assert body["real_date"] == "2026-04-19"
    assert any(k["character"] == "vex" and k["creature"] == "Goblin" for k in body["kills"])
    assert "Daggerford" in body["narrative"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_helpers.py::test_append_kills_emits_slice_per_session_with_new_kills -v`
Expected: FAIL — `append-kills` is not a registered subcommand.

- [ ] **Step 3: Implement the subcommand**

Add to `.claude/skills/hydrate-ledger/helpers.py` above the `SUBCOMMANDS` dict:

```python
from collections import defaultdict


def cmd_append_kills() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    auth_keys = {build.kill_key(k["character"], k["date"], k["creature"], k["method"])
                 for k in authored["kills"]}

    sessions_by_date = {e["date"]: e for e in data["session_log"]["entries"]}
    new_by_date: dict[str, list[dict]] = defaultdict(list)
    for member in data["party"]["members"]:
        char = member["id"]
        for k in member.get("kills", []):
            key = build.kill_key(char, k["date"], k["creature"], k["method"])
            if key in auth_keys:
                continue
            new_by_date[k["date"]].append({
                "character": char,
                "creature": k["creature"],
                "method": k["method"],
                "date": k["date"],
            })

    temp = _temp_dir()
    slices = []
    for date in sorted(new_by_date.keys()):
        kills = new_by_date[date]
        session = sessions_by_date.get(date)
        if session is None:
            continue
        slice_data = {
            "session": session.get("session"),
            "iu_date": f"{session.get('iu_day','')} {session.get('iu_month','')} {session.get('iu_year','')} DR".strip(),
            "real_date": date,
            "narrative": session.get("text", ""),
            "kills": kills,
        }
        path = temp / f"append_kills_{date}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": date, "path": str(path), "count": len(kills)})

    _emit(slices)
    return 0


SUBCOMMANDS["append-kills"] = cmd_append_kills
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_helpers.py::test_append_kills_emits_slice_per_session_with_new_kills -v`
Expected: PASS.

- [ ] **Step 5: Write the dispatch template**

Create `.claude/skills/hydrate-ledger/dispatch/append-kills.md`:

```markdown
You are authoring kill verses for the dnd-data site, one entry per kill.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice describes one session and the new kills landed in it. For each kill,
write a `verse` (single sentence, ~12 words max) and an `annotation` (~14 words
max naming the method and adding one beat).

Voice rules (from voice samples): saga fragment, gravestone epitaph. Concrete,
evocative, third person. No "Ye Olde", no second person, no meta-commentary.
Unique per kill — repetition dilutes the ledger.

Authorial restraint: do not invent specifics the slice's narrative does not
contain. The session log narrates outcomes; if it does not name a weapon, do
not name a weapon. Vague-but-true beats fabricated specific.

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object below. No prose, no markdown fence.

{{
  "fields": {{
    "<character>__<date>__<creature>__<method>": {{
      "verse": "...",
      "annotation": "..."
    }}
    /* one entry per kill in the slice */
  }},
  "reason": "one short sentence"
}}
```

(The `{{` / `}}` doubled braces are Jinja-safe escapes if templates are rendered
through Jinja; if the orchestrator uses plain `str.format`, simplify the literal
example. Decide during the SKILL.md task; keep this template content stable
either way.)

- [ ] **Step 6: Smoke-verify the template substitutes**

Run:
```bash
python3 -c "
from pathlib import Path
t = Path('.claude/skills/hydrate-ledger/dispatch/append-kills.md').read_text()
print(t.format(slice_path='/tmp/x.json', voice_samples_path='/tmp/v.md'))
" | head -5
```
Expected: prints the first 5 lines of the rendered prompt with the paths substituted in. No `KeyError`.

- [ ] **Step 7: Commit**

```bash
git add tests/test_helpers.py
git commit -m "feat: append-kills slice helper + dispatch template"
```

---

### Task 4: `append-sessions` helper + template

**Files:**
- Modify: `.claude/skills/hydrate-ledger/helpers.py`
- Create: `.claude/skills/hydrate-ledger/dispatch/append-sessions.md`
- Modify: `tests/test_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_append_sessions_emits_slice_per_unauthored_session(helper_env):
    """Fixture: session log has sessions I and II; authored has only I.
    Expect one slice for session II."""
    out = run_helper("append-sessions", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "II"
    assert slices[0]["count"] == 1

    body = json.loads(Path(slices[0]["path"]).read_text())
    assert body["session"] == "II"
    assert body["real_date"] == "2026-04-23"
    assert "crossroads" in body["narrative"]
    assert body["chapter_marker"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_helpers.py::test_append_sessions_emits_slice_per_unauthored_session -v`
Expected: FAIL.

- [ ] **Step 3: Implement the subcommand**

Add to `helpers.py`:

```python
def cmd_append_sessions() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    auth_sessions = {s["session"] for s in authored["sessions"]}

    temp = _temp_dir()
    slices = []
    for entry in data["session_log"]["entries"]:
        sid = entry.get("session")
        if sid in auth_sessions:
            continue
        slice_data = {
            "session": sid,
            "real_date": entry.get("date"),
            "iu_date": f"{entry.get('iu_day','')} {entry.get('iu_month','')} {entry.get('iu_year','')} DR".strip(),
            "narrative": entry.get("text", ""),
            "chapter_marker": entry.get("chapter_marker", False),
        }
        path = temp / f"append_sessions_{sid}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": sid, "path": str(path), "count": 1})

    _emit(slices)
    return 0


SUBCOMMANDS["append-sessions"] = cmd_append_sessions
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_helpers.py::test_append_sessions_emits_slice_per_unauthored_session -v`
Expected: PASS.

- [ ] **Step 5: Write the dispatch template**

Create `.claude/skills/hydrate-ledger/dispatch/append-sessions.md`:

```markdown
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
```

- [ ] **Step 6: Smoke-verify**

```bash
python3 -c "
from pathlib import Path
t = Path('.claude/skills/hydrate-ledger/dispatch/append-sessions.md').read_text()
print(t.format(slice_path='/tmp/x.json', voice_samples_path='/tmp/v.md'))
" | head -5
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_helpers.py
git commit -m "feat: append-sessions slice helper + dispatch template"
```

---

### Task 5: `append-chapters` helper + template

**Files:**
- Modify: `.claude/skills/hydrate-ledger/helpers.py`
- Create: `.claude/skills/hydrate-ledger/dispatch/append-chapters.md`
- Modify: `tests/test_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_append_chapters_emits_slice_per_unauthored_marker(helper_env):
    """Fixture: session II has '--- Chapter II ---' marker; authored has chapter 1.
    Expect one slice keyed "2" (the next chapter id)."""
    out = run_helper("append-chapters", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "2"
    body = json.loads(Path(slices[0]["path"]).read_text())
    assert body["starts_at_session"] == "II"
    assert "crossroads" in body["narrative"]
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — subcommand not registered.

- [ ] **Step 3: Implement**

Add to `helpers.py`:

```python
def cmd_append_chapters() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    auth_chapter_starts = {c["starts_at_session"] for c in authored["chapters"]}
    next_id = max((c["id"] for c in authored["chapters"]), default=0) + 1

    temp = _temp_dir()
    slices = []
    for entry in data["session_log"]["entries"]:
        if not entry.get("chapter_marker"):
            continue
        sid = entry.get("session")
        if sid in auth_chapter_starts:
            continue
        slice_data = {
            "starts_at_session": sid,
            "real_date": entry.get("date"),
            "narrative": entry.get("text", ""),
        }
        key = str(next_id)
        path = temp / f"append_chapters_{key}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": key, "path": str(path), "count": 1})
        next_id += 1

    _emit(slices)
    return 0


SUBCOMMANDS["append-chapters"] = cmd_append_chapters
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_helpers.py::test_append_chapters_emits_slice_per_unauthored_marker -v`
Expected: PASS.

- [ ] **Step 5: Write the dispatch template**

Create `.claude/skills/hydrate-ledger/dispatch/append-chapters.md`:

```markdown
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
```

(Note: append-chapters returns *candidates* — the user picks one before commit.
The orchestrator surfaces them for selection in the end-of-run report. This is
the only category that returns multiple options.)

- [ ] **Step 6: Smoke-verify**

```bash
python3 -c "
from pathlib import Path
t = Path('.claude/skills/hydrate-ledger/dispatch/append-chapters.md').read_text()
print(t.format(slice_path='/tmp/x.json', voice_samples_path='/tmp/v.md'))
" | head -5
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_helpers.py
git commit -m "feat: append-chapters slice helper + dispatch template"
```

---

### Task 6: `append-npcs` helper + template

**Files:**
- Modify: `.claude/skills/hydrate-ledger/helpers.py`
- Create: `.claude/skills/hydrate-ledger/dispatch/append-npcs.md`
- Modify: `tests/test_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_append_npcs_emits_slice_per_unauthored_npc(helper_env):
    """Fixture: site.known_npcs lists 'Azlund'; authored npcs is empty.
    Expect one slice for Azlund with the session-I narrative line."""
    out = run_helper("append-npcs", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "Azlund"
    body = json.loads(Path(slices[0]["path"]).read_text())
    assert body["name"] == "Azlund"
    assert any("Azlund" in m["line"] for m in body["mentions"])
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `helpers.py`:

```python
def cmd_append_npcs() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    auth_names = {n["name"] for n in authored["npcs"]}
    expected = build.collect_npcs_from_log(data["session_log"], authored["site"])
    missing = [name for name in expected if name not in auth_names]

    # Group mentions per NPC across all sessions.
    mentions_by_npc: dict[str, list[dict]] = {name: [] for name in missing}
    for entry in data["session_log"]["entries"]:
        text = entry.get("text", "")
        for name in missing:
            if name in text:
                mentions_by_npc[name].append({"session": entry.get("session"), "line": text})

    temp = _temp_dir()
    slices = []
    for name in missing:
        slice_data = {"name": name, "mentions": mentions_by_npc[name]}
        safe_key = name.replace(" ", "_").replace("/", "_")
        path = temp / f"append_npcs_{safe_key}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": name, "path": str(path), "count": len(mentions_by_npc[name])})

    _emit(slices)
    return 0


SUBCOMMANDS["append-npcs"] = cmd_append_npcs
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_helpers.py::test_append_npcs_emits_slice_per_unauthored_npc -v`
Expected: PASS.

- [ ] **Step 5: Write the dispatch template**

Create `.claude/skills/hydrate-ledger/dispatch/append-npcs.md`:

```markdown
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
```

- [ ] **Step 6: Smoke-verify**

```bash
python3 -c "
from pathlib import Path
t = Path('.claude/skills/hydrate-ledger/dispatch/append-npcs.md').read_text()
print(t.format(slice_path='/tmp/x.json', voice_samples_path='/tmp/v.md'))
" | head -5
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_helpers.py
git commit -m "feat: append-npcs slice helper + dispatch template"
```

---

### Task 7: `append-characters` helper + template

This is the **single bundled dispatch** for all unauthored PCs (so collisions on `distinction_title` can be avoided in one agent).

**Files:**
- Modify: `.claude/skills/hydrate-ledger/helpers.py`
- Create: `.claude/skills/hydrate-ledger/dispatch/append-characters.md`
- Modify: `tests/test_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_append_characters_emits_one_bundled_slice(helper_env):
    """Fixture: party has anton + vex; authored characters has only anton.
    Expect ONE slice with key='all' covering vex; existing anton's
    distinction_title surfaced for collision avoidance."""
    out = run_helper("append-characters", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "all"
    assert slices[0]["count"] == 1  # one new PC

    body = json.loads(Path(slices[0]["path"]).read_text())
    assert len(body["new_pcs"]) == 1
    assert body["new_pcs"][0]["id"] == "vex"
    assert "Sharpest Tongue" in body["existing_distinction_titles"]
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `helpers.py`:

```python
def cmd_append_characters() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    auth_ids = {c["id"] for c in authored["characters"]}

    new_pcs = []
    for member in data["party"]["members"]:
        cid = member["id"]
        if cid in auth_ids:
            continue
        # Compose the per-PC stat bundle. Use compute_trials + compute_fortune so the
        # agent has rankings + averages without needing to run them itself.
        new_pcs.append({
            "id": cid,
            "name": member.get("name"),
            "race": member.get("race"),
            "class": member.get("class"),
            "kills": member.get("kills", []),
        })

    if not new_pcs:
        _emit([])
        return 0

    # Use compute_trials/compute_fortune to derive rankings the agent can lean on.
    trials = build.compute_trials(data["party"])
    fortune = {
        m["id"]: build.compute_fortune(data["rolls_by_slug"].get(m["id"], []))
        for m in data["party"]["members"]
    }

    temp = _temp_dir()
    body = {
        "new_pcs": new_pcs,
        "trials_per_char": trials.get("per_char", {}),
        "fortune_by_char": fortune,
        "existing_distinction_titles": [c["distinction_title"] for c in authored["characters"]],
    }
    path = temp / "append_characters_all.json"
    path.write_text(json.dumps(body, indent=2))
    _emit([{"key": "all", "path": str(path), "count": len(new_pcs)}])
    return 0


SUBCOMMANDS["append-characters"] = cmd_append_characters
```

- [ ] **Step 4: Run the test to verify it passes**

Expected: PASS.

- [ ] **Step 5: Write the dispatch template**

Create `.claude/skills/hydrate-ledger/dispatch/append-characters.md`:

```markdown
You are authoring the character bundle (5 fields per PC) for one or more new
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

For each new PC, author the 5-field bundle:
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
```

- [ ] **Step 6: Smoke-verify**

```bash
python3 -c "
from pathlib import Path
t = Path('.claude/skills/hydrate-ledger/dispatch/append-characters.md').read_text()
print(t.format(slice_path='/tmp/x.json', voice_samples_path='/tmp/v.md'))
" | head -5
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_helpers.py
git commit -m "feat: append-characters bundled slice helper + dispatch template"
```

---

## Phase 3 — Refresh-pass helpers + dispatch templates

### Task 8: `refresh-chapters` helper + template

**Files:**
- Modify: `.claude/skills/hydrate-ledger/helpers.py`
- Create: `.claude/skills/hydrate-ledger/dispatch/refresh-chapters.md`
- Modify: `tests/test_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_refresh_chapters_count_zero_when_no_new_sessions(helper_env):
    """Fixture marker: refreshed_through_session=1, latest_session=2.
    Authored chapter 1 (starts at I). The new session II is inside chapter 1
    OR opens chapter 2 — either way, chapter 1 may merit re-evaluation if a
    new session sits inside it. count = sessions inside this chapter postdating
    the marker.
    """
    out = run_helper("refresh-chapters", **helper_env)
    slices = out["slices"]
    # one entry per authored chapter; count derives from new-session membership
    keys = {s["key"] for s in slices}
    assert "1" in keys
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — `refresh-chapters` not registered.

- [ ] **Step 3: Implement**

Add to `helpers.py`:

```python
def _session_index(roman: str, session_log: dict) -> int | None:
    """Return the 1-based ordinal of a session id within the log."""
    for i, e in enumerate(session_log["entries"], start=1):
        if e.get("session") == roman:
            return i
    return None


def _chapter_session_ids(chapter_id: int, chapters: list, session_log: dict) -> list[str]:
    """Return ordered list of session ids that belong to the given chapter."""
    chapters = sorted(chapters, key=lambda c: c["id"])
    starts = [c["starts_at_session"] for c in chapters]
    chapter = next(c for c in chapters if c["id"] == chapter_id)
    chapter_start_idx = _session_index(chapter["starts_at_session"], session_log)
    next_starts = [s for s in starts if _session_index(s, session_log) > chapter_start_idx]
    chapter_end_idx = (_session_index(next_starts[0], session_log) - 1) if next_starts else len(session_log["entries"])
    return [e["session"] for e in session_log["entries"][chapter_start_idx - 1:chapter_end_idx]]


def cmd_refresh_chapters() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    marker = authored["site"].get("refreshed_through_session", 0)

    temp = _temp_dir()
    slices = []
    for chapter in authored["chapters"]:
        sids = _chapter_session_ids(chapter["id"], authored["chapters"], data["session_log"])
        # Sessions postdating the marker that belong to this chapter
        new_sids = [s for s in sids if (_session_index(s, data["session_log"]) or 0) > marker]
        # Slice contains all sessions inside the chapter (for context), plus the
        # existing prose. Count = sessions postdating the marker.
        sessions_in_chapter = [
            e for e in data["session_log"]["entries"] if e.get("session") in sids
        ]
        slice_data = {
            "chapter_id": chapter["id"],
            "starts_at_session": chapter["starts_at_session"],
            "sessions": sessions_in_chapter,
            "existing": {"title": chapter["title"], "epigraph": chapter["epigraph"]},
        }
        key = str(chapter["id"])
        path = temp / f"refresh_chapters_{key}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": key, "path": str(path), "count": len(new_sids)})

    _emit(slices)
    return 0


SUBCOMMANDS["refresh-chapters"] = cmd_refresh_chapters
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_helpers.py::test_refresh_chapters_count_zero_when_no_new_sessions -v`
Expected: PASS.

- [ ] **Step 5: Write the dispatch template**

Create `.claude/skills/hydrate-ledger/dispatch/refresh-chapters.md`:

```markdown
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
```

- [ ] **Step 6: Smoke-verify**

```bash
python3 -c "
from pathlib import Path
t = Path('.claude/skills/hydrate-ledger/dispatch/refresh-chapters.md').read_text()
print(t.format(slice_path='/tmp/x.json', voice_samples_path='/tmp/v.md'))
" | head -5
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_helpers.py
git commit -m "feat: refresh-chapters slice helper + dispatch template"
```

---

### Task 9: `refresh-npcs` helper + template

**Files:**
- Modify: `.claude/skills/hydrate-ledger/helpers.py`
- Create: `.claude/skills/hydrate-ledger/dispatch/refresh-npcs.md`
- Modify: `tests/test_helpers.py`

- [ ] **Step 1: Write the failing test**

For this test we need an authored NPC. Update the fixture inline OR add to authored at runtime in the test setup. Cleaner: extend the test to write an Azlund NPC into the test's authored copy first, then run the helper.

```python
def test_refresh_npcs_count_reflects_mentions_since_marker(helper_env):
    """Add 'Azlund' to authored npcs (with allegiance + epithet), then ensure
    refresh-npcs reports a slice with count = mentions since marker.
    Fixture: marker=1; session I has 'Azlund the merchant', session II does not.
    Expect one slice with key='Azlund' and count=0 (no mentions postdate marker)."""
    npcs_path = helper_env["authored_dir"] / "npcs.json"
    npcs_path.write_text(json.dumps([
        {"name": "Azlund", "allegiance": "with",
         "epithet": "the merchant who brokers what others would not"}
    ]))
    out = run_helper("refresh-npcs", **helper_env)
    slices = {s["key"]: s for s in out["slices"]}
    assert "Azlund" in slices
    assert slices["Azlund"]["count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `helpers.py`:

```python
def cmd_refresh_npcs() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    marker = authored["site"].get("refreshed_through_session", 0)

    temp = _temp_dir()
    slices = []
    for npc in authored["npcs"]:
        name = npc["name"]
        all_mentions = []
        new_mentions = 0
        for entry in data["session_log"]["entries"]:
            if name not in entry.get("text", ""):
                continue
            sid_idx = _session_index(entry.get("session"), data["session_log"]) or 0
            mention = {"session": entry.get("session"), "line": entry.get("text", "")}
            all_mentions.append(mention)
            if sid_idx > marker:
                new_mentions += 1
        slice_data = {
            "name": name,
            "mentions": all_mentions,
            "existing": {"epithet": npc["epithet"], "allegiance": npc.get("allegiance")},
        }
        safe_key = name.replace(" ", "_").replace("/", "_")
        path = temp / f"refresh_npcs_{safe_key}.json"
        path.write_text(json.dumps(slice_data, indent=2))
        slices.append({"key": name, "path": str(path), "count": new_mentions})

    _emit(slices)
    return 0


SUBCOMMANDS["refresh-npcs"] = cmd_refresh_npcs
```

- [ ] **Step 4: Run the test to verify it passes**

Expected: PASS.

- [ ] **Step 5: Write the dispatch template**

Create `.claude/skills/hydrate-ledger/dispatch/refresh-npcs.md`:

```markdown
You are evaluating whether an NPC's epithet still fits the data.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice contains every session-log mention of this NPC and the existing
epithet + allegiance. Decide whether the existing prose still fits, given any
newly-landed mentions.

Standing rule: *"If the existing prose is still consistent with the data and
still good prose by the voice rules, return it unchanged. Only rewrite if a
fact has shifted, a stronger angle exists, or the line has gone stale."*

Authorial restraint: every claim in the new epithet must trace to a line in
the mentions. If you cannot point to a line, return `no_change`.

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object. No prose, no markdown fence.

If unchanged:
{{
  "decision": "no_change",
  "fields": null,
  "reason": "one short sentence"
}}

If rewriting:
{{
  "decision": "rewrite",
  "fields": {{ "epithet": "...", "allegiance": "with" | "against" }},
  "reason": "one short sentence"
}}
```

- [ ] **Step 6: Smoke-verify**

```bash
python3 -c "
from pathlib import Path
t = Path('.claude/skills/hydrate-ledger/dispatch/refresh-npcs.md').read_text()
print(t.format(slice_path='/tmp/x.json', voice_samples_path='/tmp/v.md'))
" | head -5
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_helpers.py
git commit -m "feat: refresh-npcs slice helper + dispatch template"
```

---

### Task 10: `refresh-characters` helper + template

Single all-PC bundle (mirrors `append-characters`).

**Files:**
- Modify: `.claude/skills/hydrate-ledger/helpers.py`
- Create: `.claude/skills/hydrate-ledger/dispatch/refresh-characters.md`
- Modify: `tests/test_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_refresh_characters_emits_one_bundle_slice(helper_env):
    """Fixture: anton authored, vex unauthored. refresh-characters cares about
    authored PCs only — it always emits one bundle slice covering authored PCs,
    with party rankings included. Expect one slice keyed 'all' with count=1
    (one authored PC under refresh)."""
    out = run_helper("refresh-characters", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "all"
    body = json.loads(Path(slices[0]["path"]).read_text())
    assert any(c["id"] == "anton" for c in body["pcs"])
    assert "trials_per_char" in body
    assert "fortune_by_char" in body
    assert "existing" in body
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `helpers.py`:

```python
def cmd_refresh_characters() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    pcs = []
    for member in data["party"]["members"]:
        if not any(c["id"] == member["id"] for c in authored["characters"]):
            continue
        pcs.append({
            "id": member["id"],
            "name": member.get("name"),
            "race": member.get("race"),
            "class": member.get("class"),
            "kills": member.get("kills", []),
        })

    if not pcs:
        _emit([])
        return 0

    trials = build.compute_trials(data["party"])
    fortune = {
        m["id"]: build.compute_fortune(data["rolls_by_slug"].get(m["id"], []))
        for m in data["party"]["members"]
    }
    existing = {c["id"]: c for c in authored["characters"]}

    body = {
        "pcs": pcs,
        "trials_per_char": trials.get("per_char", {}),
        "fortune_by_char": fortune,
        "existing": existing,
    }
    temp = _temp_dir()
    path = temp / "refresh_characters_all.json"
    path.write_text(json.dumps(body, indent=2))
    _emit([{"key": "all", "path": str(path), "count": len(pcs)}])
    return 0


SUBCOMMANDS["refresh-characters"] = cmd_refresh_characters
```

- [ ] **Step 4: Run the test to verify it passes**

Expected: PASS.

- [ ] **Step 5: Write the dispatch template**

Create `.claude/skills/hydrate-ledger/dispatch/refresh-characters.md`:

```markdown
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
    /* include only PCs you are rewriting; omit unchanged PCs entirely */
  }} | null,
  "reason": "one short sentence"
}}
```

(Note: `reliquary_header` is not in the refresh field set — it's locked per
spec. Five fields evolve per PC.)

- [ ] **Step 6: Smoke-verify**

```bash
python3 -c "
from pathlib import Path
t = Path('.claude/skills/hydrate-ledger/dispatch/refresh-characters.md').read_text()
print(t.format(slice_path='/tmp/x.json', voice_samples_path='/tmp/v.md'))
" | head -5
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_helpers.py
git commit -m "feat: refresh-characters bundled slice helper + dispatch template"
```

---

### Task 11: `refresh-road-ahead` helper + template

**Files:**
- Modify: `.claude/skills/hydrate-ledger/helpers.py`
- Create: `.claude/skills/hydrate-ledger/dispatch/refresh-road-ahead.md`
- Modify: `tests/test_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_refresh_road_ahead_emits_singleton(helper_env):
    """Always emits one slice; count = sessions postdating the marker."""
    out = run_helper("refresh-road-ahead", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "all"
    # marker=1, latest=2 → 1 new session
    assert slices[0]["count"] == 1
    body = json.loads(Path(slices[0]["path"]).read_text())
    assert "new_sessions" in body
    assert "existing" in body
    assert "Azlund's offer" in {e["name"] for e in body["existing"]["known"]}
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `helpers.py`:

```python
def cmd_refresh_road_ahead() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    marker = authored["site"].get("refreshed_through_session", 0)

    new_sessions = [
        e for i, e in enumerate(data["session_log"]["entries"], start=1)
        if i > marker
    ]
    body = {
        "new_sessions": new_sessions,
        "existing": authored["site"]["road_ahead"],
    }
    temp = _temp_dir()
    path = temp / "refresh_road_ahead.json"
    path.write_text(json.dumps(body, indent=2))
    _emit([{"key": "all", "path": str(path), "count": len(new_sessions)}])
    return 0


SUBCOMMANDS["refresh-road-ahead"] = cmd_refresh_road_ahead
```

- [ ] **Step 4: Run the test to verify it passes**

Expected: PASS.

- [ ] **Step 5: Write the dispatch template**

Create `.claude/skills/hydrate-ledger/dispatch/refresh-road-ahead.md`:

```markdown
You are evaluating the entire Road Ahead block for the dnd-data site.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice contains every session that has landed since the last refresh
(`new_sessions`) and the entire current `road_ahead` block (`existing`)
with `known`, `was_known`, and `direction` lists.

For each `known[]` entry, evaluate whether newly-landed sessions resolved
the thread. If yes, **move the entry into `was_known`** (sharpening the
gloss as part of the move if warranted). Glosses in `was_known[]` may also
sharpen. The `direction` line is rewritten only if the campaign genuinely
turned.

You are returning the FULL new state of the road_ahead block. The orchestrator
detects graduations by diffing your new `known` against the current one — entries
that disappear from `known` and appear in `was_known` are graduations.

Standing rule: *"If the existing prose is still consistent with the data and
still good prose by the voice rules, return it unchanged."*

Read only `{slice_path}` and `{voice_samples_path}`. Do not explore other files.

Return only the JSON object below. No prose, no markdown fence.

If unchanged:
{{
  "decision": "no_change",
  "fields": null,
  "reason": "one short sentence"
}}

If rewriting any part:
{{
  "decision": "rewrite",
  "fields": {{
    "known": [{{ "name": "...", "gloss": "..." }}],
    "was_known": [{{ "name": "...", "gloss": "..." }}],
    "direction": "..."
  }},
  "reason": "one short sentence"
}}
```

- [ ] **Step 6: Smoke-verify**

```bash
python3 -c "
from pathlib import Path
t = Path('.claude/skills/hydrate-ledger/dispatch/refresh-road-ahead.md').read_text()
print(t.format(slice_path='/tmp/x.json', voice_samples_path='/tmp/v.md'))
" | head -5
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_helpers.py
git commit -m "feat: refresh-road-ahead slice helper + dispatch template"
```

---

### Task 12: `refresh-intro-epithet` helper + template

**Files:**
- Modify: `.claude/skills/hydrate-ledger/helpers.py`
- Create: `.claude/skills/hydrate-ledger/dispatch/refresh-intro-epithet.md`
- Modify: `tests/test_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_refresh_intro_epithet_emits_singleton(helper_env):
    out = run_helper("refresh-intro-epithet", **helper_env)
    slices = out["slices"]
    assert len(slices) == 1
    assert slices[0]["key"] == "all"
    body = json.loads(Path(slices[0]["path"]).read_text())
    assert "new_sessions" in body
    assert "road_ahead_known" in body
    assert body["existing"] == "A small ledger."
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `helpers.py`:

```python
def cmd_refresh_intro_epithet() -> int:
    data = build.load_data(_data_dir())
    authored = _load_authored()
    marker = authored["site"].get("refreshed_through_session", 0)

    new_sessions = [
        e for i, e in enumerate(data["session_log"]["entries"], start=1)
        if i > marker
    ]
    body = {
        "new_sessions": new_sessions,
        "road_ahead_known": authored["site"]["road_ahead"]["known"],
        "existing": authored["site"]["intro_epithet"],
    }
    temp = _temp_dir()
    path = temp / "refresh_intro_epithet.json"
    path.write_text(json.dumps(body, indent=2))
    _emit([{"key": "all", "path": str(path), "count": len(new_sessions)}])
    return 0


SUBCOMMANDS["refresh-intro-epithet"] = cmd_refresh_intro_epithet
```

- [ ] **Step 4: Run the test to verify it passes**

Expected: PASS.

- [ ] **Step 5: Write the dispatch template**

Create `.claude/skills/hydrate-ledger/dispatch/refresh-intro-epithet.md`:

```markdown
You are evaluating the campaign-spine intro epithet at the top of the page.

Your input:
- Slice file: {slice_path}
- Voice samples: {voice_samples_path}

The slice contains:
  - `new_sessions`: every session that has landed since the last refresh
  - `road_ahead_known`: the current Road Ahead `known[]` list
  - `existing`: the current intro_epithet string

The intro_epithet is the tightest summary of the campaign's spine. Decide
whether newly-landed sessions or shifts in `road_ahead_known` make the
existing line stale.

Standing rule: *"If the existing prose is still consistent with the data and
still good prose by the voice rules, return it unchanged. Only rewrite if a
fact has shifted, a stronger angle exists, or the line has gone stale."*
This line is mostly stable; rewrite only on genuine spine shifts.

Voice: campaign-spine tier — names what the campaign DOES, places it,
names what it threatens. See `{voice_samples_path}`.

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
  "fields": {{ "intro_epithet": "..." }},
  "reason": "one short sentence"
}}
```

- [ ] **Step 6: Smoke-verify**

```bash
python3 -c "
from pathlib import Path
t = Path('.claude/skills/hydrate-ledger/dispatch/refresh-intro-epithet.md').read_text()
print(t.format(slice_path='/tmp/x.json', voice_samples_path='/tmp/v.md'))
" | head -5
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_helpers.py
git commit -m "feat: refresh-intro-epithet slice helper + dispatch template"
```

---

## Phase 4 — SKILL.md rewrite (orchestration)

This is the cutover. Until this task lands, the existing skill workflow is unchanged. After this task, the skill uses helpers + parallel dispatch.

### Task 13: SKILL.md — workflow + orchestration

**Files:**
- Modify: `.claude/skills/hydrate-ledger/SKILL.md` (rewrite the Workflow section, add a Dispatch section, remove the evolvable-entries data-context table)

- [ ] **Step 1: Read the current SKILL.md**

```bash
cat .claude/skills/hydrate-ledger/SKILL.md | head -100
```

Familiarize yourself with the existing structure. We are replacing the **Workflow** and **Refresh pass** sections; spoiler/voice/scrubbing/restraint sections stay verbatim.

- [ ] **Step 2: Replace the Workflow section**

The new Workflow section (replace existing steps 1-8 in SKILL.md):

```markdown
## Workflow

The skill is an orchestrator. It does not load narrative data. Slice helpers
introspect upstream + authored state; dispatch subagents author prose.

1. **Read authored state.** Read `authored/*.json` and the marker
   `site.refreshed_through_session`.
2. **Append pass — gather slices.** Invoke each `append-*` helper in turn:
   ```bash
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py append-kills
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py append-sessions
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py append-chapters
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py append-npcs
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py append-characters
   ```
   For each, parse the stdout `{"slices": [...]}` and collect entries with
   `count > 0`. **Do not read the slice files.**
3. **Append pass — dispatch.** Issue all collected append dispatches in a
   single Agent-tool message (parallel). For each dispatch, the prompt is
   the matching `dispatch/<category>.md` template with `{slice_path}`,
   `{voice_samples_path}`, and (for append) `{existing}` (empty string)
   substituted. Voice samples path is
   `.claude/skills/hydrate-ledger/voice-samples.md`.
4. **Append pass — apply.** For each returned JSON object, validate against
   the append schema (`fields` present, `reason` present). Append entries to
   the appropriate `authored/*.json` file. For `append-chapters` (which
   returns candidates), surface candidates to the user and apply their
   selection.
5. **Refresh pass — trigger check.** Compute `latest_session = len(session_log.entries)`.
   If `latest_session == site.refreshed_through_session`, skip the refresh pass.
6. **Refresh pass — gather slices.** Invoke each `refresh-*` helper:
   ```bash
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py refresh-chapters
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py refresh-npcs
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py refresh-characters
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py refresh-road-ahead
   .venv/bin/python .claude/skills/hydrate-ledger/helpers.py refresh-intro-epithet
   ```
   Drop `count == 0` entries.
7. **Refresh pass — dispatch.** Issue all remaining refresh dispatches in a
   single parallel Agent-tool message. Templates use the refresh return schema
   (`decision: "no_change" | "rewrite"`).
8. **Refresh pass — apply.** For each return:
   - `no_change` → skip.
   - `rewrite` → swap fields in the appropriate authored file.
   For `refresh-road-ahead`, write the new `known` / `was_known` / `direction`
   state and compute graduations (keys removed from `known`, added to
   `was_known`) for the report.
9. **Bump marker on full refresh success.** If every refresh dispatch
   succeeded (after retries), set `site.refreshed_through_session = latest_session`.
   Partial failure → leave marker untouched.
10. **Build.** Run `.venv/bin/python build.py`. On `MISSING <type> <key>` or
    `MALFORMED <type> <key> field=<f>`: targeted single-dispatch for the
    offending entity (max 3 iterations).
11. **Report.** Print the end-of-run report (see below).
```

- [ ] **Step 3: Replace the Refresh pass section**

Remove the existing "Refresh pass" data-context table (it's now embodied in helpers + dispatch templates). Replace with a brief pointer:

```markdown
## Refresh pass

The refresh pass evaluates evolvable entries against newly-landed data.
Trigger: `latest_session > site.refreshed_through_session`. Categories,
slice contents, and dispatch templates are defined in `helpers.py` and
`dispatch/refresh-*.md`. See spec
`docs/superpowers/specs/2026-04-25-subagent-dispatch-architecture-design.md`
for the full contract.
```

- [ ] **Step 4: Verify SKILL.md still has voice/spoiler/scrubbing/restraint sections intact**

```bash
grep -E "^## (Spoiler|Voice|Scrubbing|Authorial|Voice anchoring)" .claude/skills/hydrate-ledger/SKILL.md
```
Expected: 4-5 lines listing those headings (none deleted).

- [ ] **Step 5: Commit**

```bash
# SKILL.md is gitignored; nothing to git-add for it.
# This commit captures any spec / fixture refinements that landed alongside.
git status
git commit --allow-empty -m "docs: SKILL.md cutover — orchestrator workflow rewrite"
```

(Empty commit because SKILL.md is gitignored. The commit message documents the
cutover for the project log.)

---

### Task 14: SKILL.md — error handling + end-of-run report

**Files:**
- Modify: `.claude/skills/hydrate-ledger/SKILL.md` (add Error Handling and End-of-Run Report sections)

- [ ] **Step 1: Add the Error Handling section**

Insert before the Voice rules section in SKILL.md:

```markdown
## Error handling

| Failure | Response |
|---|---|
| Helper exits non-zero or stdout is not valid JSON | Surface, abort the run. Helpers are deterministic — investigate before retrying. |
| Subagent returns malformed JSON | Re-dispatch once with a corrective re-prompt: *"Your last response was not valid JSON. Return only the JSON object — no prose, no markdown fence."* Second failure → surface the temp file path and the raw response so the user can author the entry manually. |
| Subagent returns valid JSON that fails the schema (wrong fields, invalid `decision`) | Same as malformed: re-dispatch once with a corrective re-prompt naming the schema violation. |
| `build.py` reports `MISSING <type> <key>` or `MALFORMED <type> <key> field=<f>` | Targeted single-dispatch for the offending entity. Max 3 iterations of build → fix → rebuild. |
| Partial refresh-pass failure (some agents succeeded, some failed after retry) | Apply the agents that succeeded. **Do not bump** `site.refreshed_through_session`. Surface failures with temp-file paths. |
| Helper produces an empty `slices` array | Treat as "nothing to do" for that category. Not an error. |

The temp directory is cleaned only on **full success**: every dispatch succeeded,
every authored write succeeded, `build.py` exited zero. On any failure, the
temp dir is preserved and its path printed in the report so the user can inspect
exactly what each agent saw.
```

- [ ] **Step 2: Add the End-of-Run Report section**

Append at the bottom of SKILL.md (above any final notes):

```markdown
## End-of-run report

Print, in order:

1. **Append additions** — per category, by entity key.
2. **Refresh decisions** — per category, by entity key, with `reason`.
3. **Graduations** — `road_ahead.known` → `was_known` (computed by diffing
   keys before/after the refresh-road-ahead apply step).
4. **Marker state** — old → new value of `site.refreshed_through_session`,
   or "unchanged" with the reason (no new sessions, partial failure, etc.).
5. **Temp directory path** — and whether it was cleaned or preserved.

`reason` strings come straight from the agents' return objects.
```

- [ ] **Step 3: Verify the file lints cleanly**

```bash
wc -l .claude/skills/hydrate-ledger/SKILL.md
```
Expected: file size grew (added two new sections).

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "docs: SKILL.md error handling and end-of-run report sections"
```

---

## Phase 5 — Manual harness + smoke run

### Task 15: `test_harness.sh` — manual sanity check

**Files:**
- Create: `.claude/skills/hydrate-ledger/test_harness.sh`

- [ ] **Step 1: Create the harness**

```bash
cat > .claude/skills/hydrate-ledger/test_harness.sh <<'EOF'
#!/usr/bin/env bash
# Runs each helper subcommand against the current real upstream data
# and prints the metadata array + slice-file sizes for each entry.
# Use this when modifying helpers to sanity-check that slices look right.
set -euo pipefail

HELPERS=".claude/skills/hydrate-ledger/helpers.py"
PYTHON="${PYTHON:-.venv/bin/python}"

for sub in append-kills append-sessions append-chapters append-npcs append-characters \
           refresh-chapters refresh-npcs refresh-characters refresh-road-ahead refresh-intro-epithet; do
    echo "=== $sub ==="
    out=$("$PYTHON" "$HELPERS" "$sub")
    echo "$out" | python3 -m json.tool
    # Print slice file sizes
    python3 -c "
import json, os, sys
data = json.loads('''$out''')
for s in data['slices']:
    if os.path.exists(s['path']):
        print(f\"  {s['key']}: {os.path.getsize(s['path'])} bytes\")
    else:
        print(f\"  {s['key']}: <path missing>\")
"
    echo
done
EOF
chmod +x .claude/skills/hydrate-ledger/test_harness.sh
```

- [ ] **Step 2: Run the harness**

```bash
.claude/skills/hydrate-ledger/test_harness.sh
```
Expected: 10 sections, each printing the metadata JSON for one subcommand and the byte size of each slice file. No exceptions.

If a subcommand errors out, fix the helper before proceeding.

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "chore: manual smoke harness for slice helpers"
```

---

### Task 16: End-to-end skill smoke run

**Files:**
- (no files modified; this validates the full flow)

- [ ] **Step 1: Capture the current `index.html` state**

```bash
cp index.html /tmp/index-before.html
```

- [ ] **Step 2: Invoke the hydrate-ledger skill against current real data**

In a fresh Claude Code session: invoke `/hydrate-ledger` (or however the user invokes the skill in this repo) against the current real upstream files. Expected behavior:
- All `append-*` helpers report empty slices (the existing authored store is up to date for the current session log).
- Refresh trigger is checked: if `refreshed_through_session == latest_session`, refresh pass is skipped silently.
- Otherwise, refresh helpers report counts and dispatches go out.
- Build runs, exit 0.
- End-of-run report printed.

- [ ] **Step 3: Diff `index.html`**

```bash
diff /tmp/index-before.html index.html
```
Expected: no diff if there were no genuine prose changes; only-prose-field diffs if a refresh actually rewrote something. **No structural HTML changes**, no template/build.py changes — those were not in scope.

- [ ] **Step 4: Run the existing pytest suite**

```bash
.venv/bin/pytest tests/ -v
```
Expected: all existing tests pass, plus all new helper tests pass.

- [ ] **Step 5: Visual page check**

Start the local preview:
```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory .
```
Open `http://127.0.0.1:8765/` and verify the page renders identically to the pre-cutover state (or with only the expected prose changes from the refresh pass).

- [ ] **Step 6: Commit (if any prose changed)**

If `authored/*.json` changed legitimately during the run:

```bash
git add authored
git commit -m "chore: end-to-end smoke run on subagent dispatch architecture"
```

If nothing changed, skip this step.

---

## Self-review

Run after the plan is complete to catch gaps before execution. This is a checklist for the human reading the plan, not a subagent dispatch.

**Spec coverage:** Each spec section maps to:
- Architecture (3 layers) → Tasks 2-12 (helpers), Task 13 (orchestrator)
- Core invariant (orchestrator never reads slices) → Task 13 (workflow step 2 explicit)
- Slice helper contract → Tasks 3-12
- Dispatch contract (templates, return schema) → Tasks 3-12 (templates), Task 13 (apply step)
- Append pass orchestration → Task 13
- Refresh pass orchestration → Task 13
- Error handling → Task 14
- End-of-run report → Task 14
- Voice consistency → Tasks 3-12 (every template references voice-samples.md)
- Scrubbing → covered by `build.load_data` (existing scrubber) which the helpers call; no new code needed
- Testing posture → Task 1 (test fixtures), Tasks 3-12 (per-helper tests), Task 15 (manual harness), Task 16 (e2e)
- Migration → Task 13 + 14 (SKILL.md cutover)
- Out of scope → respected: no template / build.py rendering changes anywhere

**Placeholder scan:** No "TBD", "TODO", "implement later" in any task body. Every code block is complete python or markdown. Smoke commands have explicit expected outputs.

**Type consistency check:**
- `_emit(slices)` always called with a list of `{key, path, count}` dicts. ✓
- Helper return path patterns: `<temp>/<category>_<key>.json`. ✓
- Subagent return schema discriminator: `decision: "no_change" | "rewrite"` for refresh; absent for append. ✓
- `SUBCOMMANDS` registry mutated in each helper task; argparse picks up names dynamically. ✓
- `_session_index` and `_chapter_session_ids` are private helpers, defined once in Task 8 and reused if needed in later tasks (none currently do, but the imports stay valid). ✓

**Note on a known gap:** `append-chapters` returns *candidate* title/epigraph pairs (the user picks). The orchestrator must surface them to the user and accept a selection before writing to `authored/chapters.json`. This is called out in Task 13 step 4 and in the dispatch template (Task 5 step 5). No additional task needed — it's an orchestration nuance documented in SKILL.md.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-25-subagent-dispatch-architecture.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach?
