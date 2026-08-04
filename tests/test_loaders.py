import json
from pathlib import Path

import pytest

from build import render
from build.render import load_data


def _dice_file(rolls: list[dict]) -> str:
    """A dicex export wrapping rolls under a single player named 'testplayer'."""
    return json.dumps({"players": {"u1": {"name": "testplayer", "rolls": rolls}}})


def _d20(ts: str, value: int) -> dict:
    return {"timestamp": ts, "notation": "1d20", "total": value,
            "dice": [{"type": "d20", "value": value}]}

def test_load_data_returns_party_dice_and_sessionlog(tmp_path: Path):
    (tmp_path / "party.json").write_text(json.dumps({"members": []}))
    (tmp_path / "dice").mkdir()
    (tmp_path / "dice" / "dicex-rolls-2026-04-23.json").write_text(json.dumps([{"player": "x"}]))
    (tmp_path / "session-log.json").write_text(json.dumps({"entries": []}))

    data = load_data(tmp_path)

    assert data["party"] == {"members": []}
    assert isinstance(data["dice_rolls"], list)
    assert data["dice_rolls"][0][0]["player"] == "x"
    assert data["session_log"] == {"entries": []}

def test_load_data_collects_all_dice_files(tmp_path: Path):
    (tmp_path / "party.json").write_text(json.dumps({}))
    (tmp_path / "session-log.json").write_text(json.dumps({}))
    (tmp_path / "dice").mkdir()
    (tmp_path / "dice" / "dicex-rolls-2026-04-01.json").write_text(json.dumps([{"r": 1}]))
    (tmp_path / "dice" / "dicex-rolls-2026-04-23.json").write_text(json.dumps([{"r": 2}]))

    data = load_data(tmp_path)

    assert len(data["dice_rolls"]) == 2

def test_load_data_dedups_overlapping_dice_exports_by_timestamp(tmp_path: Path, monkeypatch):
    """Successive dicex exports are not guaranteed disjoint — a later export can
    restate rolls already present in an earlier one. load_data must dedup by
    timestamp per slug so fortune stats aren't double-counted."""
    monkeypatch.setattr(render, "_load_dice_player_map", lambda: {"testplayer": "grieg"})

    a = _d20("2026-04-20T02:12:20.390Z", 20)
    b = _d20("2026-04-21T03:00:00.000Z", 5)
    c = _d20("2026-04-27T04:00:00.000Z", 11)

    (tmp_path / "party.json").write_text(json.dumps({"members": []}))
    (tmp_path / "session-log.json").write_text(json.dumps({"entries": []}))
    (tmp_path / "dice").mkdir()
    # Earlier export holds a, b. Later export restates a, b and adds c.
    (tmp_path / "dice" / "dicex-rolls-2026-04-23.json").write_text(_dice_file([a, b]))
    (tmp_path / "dice" / "dicex-rolls-2026-04-27.json").write_text(_dice_file([a, b, c]))

    rolls = load_data(tmp_path)["rolls_by_slug"]["grieg"]

    assert [e["timestamp"] for e in rolls] == [
        "2026-04-20T02:12:20.390Z",
        "2026-04-21T03:00:00.000Z",
        "2026-04-27T04:00:00.000Z",
    ]
    assert len(rolls) == 3  # not 5 — the overlapping a, b are taken once

def _party_with_kill(date: str) -> str:
    """A one-member party whose single kill carries `date`."""
    return json.dumps([{"name": "Chumble Crudluck", "id": "mike-warlock",
                        "kills": [{"creature": "Unarmed Salamander",
                                   "method": "Eldritch Blast", "date": date}]}])

def _log(*real_dates: str) -> str:
    return json.dumps({"entries": [{"day": i, "realDate": d, "text": ""}
                                   for i, d in enumerate(real_dates, start=1)]})

def test_load_data_snaps_kill_logged_the_morning_after_to_its_session_date(tmp_path: Path):
    """The GM logs a session's kills the next day, so the character-sheet export
    can stamp one with the following date. It belongs to the session that ran the
    night before, and every consumer keys kills on the raw date."""
    (tmp_path / "party.json").write_text(_party_with_kill("2026-07-27"))
    (tmp_path / "session-log.json").write_text(_log("07/26/2026"))
    (tmp_path / "dice").mkdir()

    data = load_data(tmp_path)

    assert data["party"]["members"][0]["kills"][0]["date"] == "2026-07-26"

def test_load_data_leaves_a_kill_dated_two_days_after_a_session_alone(tmp_path: Path):
    """The snap absorbs one day of logging drift, not an open-ended search back
    to the most recent session — a kill two days out stays where it is and is
    reported, rather than being silently attributed to the wrong session."""
    (tmp_path / "party.json").write_text(_party_with_kill("2026-07-28"))
    (tmp_path / "session-log.json").write_text(_log("07/26/2026"))
    (tmp_path / "dice").mkdir()

    data = load_data(tmp_path)

    assert data["party"]["members"][0]["kills"][0]["date"] == "2026-07-28"

def test_load_data_keeps_a_kill_that_already_lands_on_a_session_date(tmp_path: Path):
    """Back-to-back session days: a kill on its own session's date must not be
    dragged onto the session before it just because one exists."""
    (tmp_path / "party.json").write_text(_party_with_kill("2026-07-26"))
    (tmp_path / "session-log.json").write_text(_log("07/25/2026", "07/26/2026"))
    (tmp_path / "dice").mkdir()

    data = load_data(tmp_path)

    assert data["party"]["members"][0]["kills"][0]["date"] == "2026-07-26"


def test_load_data_keeps_rolls_with_blank_timestamp(tmp_path: Path, monkeypatch):
    """A blank timestamp can't prove identity, so such rolls are never deduped —
    two timestamp-less rolls must both survive rather than collapse into one."""
    monkeypatch.setattr(render, "_load_dice_player_map", lambda: {"testplayer": "grieg"})
    blank = {"timestamp": "", "notation": "1d6", "total": 3,
             "dice": [{"type": "d6", "value": 3}]}

    (tmp_path / "party.json").write_text(json.dumps({"members": []}))
    (tmp_path / "session-log.json").write_text(json.dumps({"entries": []}))
    (tmp_path / "dice").mkdir()
    (tmp_path / "dice" / "dicex-rolls-2026-04-23.json").write_text(_dice_file([blank, blank]))

    rolls = load_data(tmp_path)["rolls_by_slug"]["grieg"]
    assert len(rolls) == 2


def test_load_data_scrubs_realname_ids_and_drops_player_field(tmp_path: Path):
    (tmp_path / "party.json").write_text(json.dumps([
        {"id": "simon-fighter", "name": "Grieg", "player": "Simon", "kills": []},
        {"id": "steve-wizard", "name": "Urida", "player": "Steve", "kills": []},
        {"id": "anton", "name": "Anton Truebranch", "player": "Quinn", "kills": []},
    ]))
    (tmp_path / "session-log.json").write_text(json.dumps({"entries": []}))

    data = load_data(tmp_path)
    members = data["party"]["members"]

    assert [m["id"] for m in members] == ["grieg", "urida", "anton"]
    assert all("player" not in m for m in members)


def test_load_data_loads_xp_log_when_present(tmp_path: Path):
    (tmp_path / "party.json").write_text('{"members": []}')
    (tmp_path / "session-log.json").write_text('{"entries": []}')
    (tmp_path / "dice").mkdir()
    (tmp_path / "xp-log.json").write_text(
        '{"entries": [{"id": "a", "date": "2026-04-19", "sessionId": "s1", '
        '"title": "T", "type": "combat", "perPc": 50}]}')
    data = load_data(tmp_path)
    assert data["xp_log"]["entries"][0]["perPc"] == 50


def test_load_data_tolerates_missing_xp_log(tmp_path: Path):
    (tmp_path / "party.json").write_text('{"members": []}')
    (tmp_path / "session-log.json").write_text('{"entries": []}')
    (tmp_path / "dice").mkdir()
    data = load_data(tmp_path)          # no xp-log.json on disk
    assert data["xp_log"] == {"entries": []}


def test_load_data_rejects_out_of_order_session_ordinals(tmp_path):
    """The refresh marker is a positional count; entry i must be session i."""
    (tmp_path / "party.json").write_text("[]")
    (tmp_path / "dice").mkdir()
    log = {"entries": [
        {"day": "1", "realDate": "04/19/2026", "text": ""},
        {"day": "3", "realDate": "04/23/2026", "text": ""},   # gap: entry 2 is session 3
    ]}
    (tmp_path / "session-log.json").write_text(json.dumps(log))
    with pytest.raises(ValueError, match="session ordinal"):
        render.load_data(tmp_path)


def test_resolve_dice_player_substring_hit():
    assert render._resolve_dice_player("Zebulon Marlowe", {"Zebulon": "vex"}) == "vex"


def test_resolve_dice_player_longest_pattern_first():
    mapping = {"Z": "wrong", "Zebulon": "vex"}
    assert render._resolve_dice_player("Zebulon Marlowe", mapping) == "vex"


def test_resolve_dice_player_no_match_returns_none():
    assert render._resolve_dice_player("Nobody Special", {"Quinn": "vex"}) is None


def test_resolve_dice_player_ignores_empty_pattern():
    assert render._resolve_dice_player("Anyone", {"": "oops"}) is None
