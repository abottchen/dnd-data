import pytest
from build.render import (
    ValidationError, KIND_MISSING, KIND_MALFORMED, KIND_ORPHAN, validate_kills,
    validate_sessions, validate_chapters, validate_npcs, validate_characters, validate_site,
    validate_portraits, validate_dice_player_mapping,
    validate_distinction_basis, validate_distinction_uniqueness,
)

def test_validation_error_format_missing():
    e = ValidationError(KIND_MISSING, "kills", ("anton", "2026-04-23", "yuan-ti broodguard", "vicious mockery"))
    assert str(e) == "MISSING kills (anton, 2026-04-23, yuan-ti broodguard, vicious mockery)"

def test_validation_error_format_malformed():
    e = ValidationError(KIND_MALFORMED, "sessions", (5,), field="title")
    assert str(e) == "MALFORMED sessions (5) field=title"

def test_validation_error_format_orphan():
    e = ValidationError(KIND_ORPHAN, "kills", ("anton", "2025-12-15", "gnoll", "scimitar"))
    assert str(e) == "ORPHAN kills (anton, 2025-12-15, gnoll, scimitar)"


def make_party(kills):
    return {"members": [{"id": "anton", "kills": kills}]}

def test_validate_kills_passes_when_all_authored():
    party = make_party([{"date": "2026-04-23", "creature": "Goblin", "method": "Vicious Mockery"}])
    authored = [{
        "character": "anton", "date": "2026-04-23",
        "creature": "Goblin", "method": "Vicious Mockery",
        "verse": "v", "annotation": "a",
    }]
    errors = validate_kills(party, authored)
    assert errors == []

def test_validate_kills_reports_missing():
    party = make_party([{"date": "2026-04-23", "creature": "Goblin", "method": "Vicious Mockery"}])
    errors = validate_kills(party, [])
    assert len(errors) == 1
    assert errors[0].kind == "MISSING"

def test_validate_kills_reports_orphan():
    party = make_party([])
    authored = [{
        "character": "anton", "date": "2025-12-15",
        "creature": "Gnoll", "method": "Scimitar",
        "verse": "v", "annotation": "a",
    }]
    errors = validate_kills(party, authored)
    assert len(errors) == 1
    assert errors[0].kind == "ORPHAN"

def test_validate_kills_reports_malformed_missing_verse():
    party = make_party([{"date": "2026-04-23", "creature": "Goblin", "method": "Vicious Mockery"}])
    authored = [{
        "character": "anton", "date": "2026-04-23",
        "creature": "Goblin", "method": "Vicious Mockery",
        "annotation": "a",  # verse is missing
    }]
    errors = validate_kills(party, authored)
    assert len(errors) == 1
    assert errors[0].kind == "MALFORMED"
    assert errors[0].field == "verse"

def test_validate_kills_case_insensitive_creature_match():
    party = make_party([{"date": "2026-04-23", "creature": "Yuan-Ti Broodguard", "method": "Vicious Mockery"}])
    authored = [{
        "character": "anton", "date": "2026-04-23",
        "creature": "yuan-ti broodguard", "method": "vicious mockery",
        "verse": "v", "annotation": "a",
    }]
    errors = validate_kills(party, authored)
    assert errors == []


# --- Task 6: new validator tests ---

def test_validate_sessions_missing():
    log = {"entries": [{"session": 5, "date": "2026-04-23"}]}
    errors = validate_sessions(log, [])
    assert len(errors) == 1
    assert errors[0].kind == "MISSING"

def test_validate_sessions_malformed_missing_silent_roll():
    log = {"entries": [{"session": 5, "date": "2026-04-23"}]}
    authored = [{"session": 5, "title": "t", "summary": "s"}]  # silent_roll missing
    errors = validate_sessions(log, authored)
    assert any(e.field == "silent_roll" for e in errors)

def test_validate_chapters_missing():
    log = {"entries": [{"session": 1, "chapter_marker": True}]}
    errors = validate_chapters(log, [])
    assert any(e.kind == "MISSING" for e in errors)

def test_validate_npcs_missing():
    npcs_in_log = ["Azlund"]
    errors = validate_npcs(npcs_in_log, [])
    assert any(e.kind == "MISSING" for e in errors)

def test_validate_characters_missing_constellation_epithet():
    party = {"members": [{"id": "anton"}]}
    authored = [{"id": "anton", "reliquary_header": "Fallen by his tongue"}]  # constellation_epithet missing
    errors = validate_characters(party, authored)
    assert any(e.field == "constellation_epithet" for e in errors)

def test_validate_site_required_keys():
    site = {"intro_epithet": "x", "refreshed_through_session": 0}
    errors = validate_site(site, latest_session=5)
    fields = {e.field for e in errors}
    assert "page_title" in fields
    assert "page_subtitle" in fields
    assert "intro_meta" not in fields  # intro_meta is now build-computed, not authored

def test_validate_site_missing_refreshed_through_session():
    site = {"intro_epithet": "x", "page_title": "t", "page_subtitle": "s"}
    errors = validate_site(site, latest_session=5)
    assert any(e.field == "refreshed_through_session" for e in errors)

def test_validate_site_negative_refreshed_through_session():
    site = {"intro_epithet": "x", "page_title": "t", "page_subtitle": "s",
            "refreshed_through_session": -1}
    errors = validate_site(site, latest_session=5)
    assert any(e.field == "refreshed_through_session" for e in errors)

def test_validate_site_refreshed_through_session_above_latest():
    site = {"intro_epithet": "x", "page_title": "t", "page_subtitle": "s",
            "refreshed_through_session": 6}
    errors = validate_site(site, latest_session=5)
    assert any(e.field == "refreshed_through_session" for e in errors)

def test_validate_site_rejects_bool_refreshed_through_session():
    site = {"intro_epithet": "x", "page_title": "t", "page_subtitle": "s",
            "refreshed_through_session": True}
    errors = validate_site(site, latest_session=5)
    assert any(e.field == "refreshed_through_session" for e in errors)

def test_validate_site_rejects_still_present_intro_meta():
    site = {"intro_epithet": "x", "page_title": "t", "page_subtitle": "s",
            "refreshed_through_session": 5, "intro_meta": "Five Sessions"}
    errors = validate_site(site, latest_session=5)
    assert any(e.field == "intro_meta" for e in errors)

def test_validate_site_passes_with_complete_singleton():
    site = {"intro_epithet": "x", "page_title": "t", "page_subtitle": "s",
            "refreshed_through_session": 5}
    errors = validate_site(site, latest_session=5)
    assert errors == []


# --- Portrait + dice-player-map validators ---

def test_validate_portraits_missing_file(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    party = {"members": [{"id": "anton", "image": "anton.png"}]}
    errors = validate_portraits(party, images_dir)
    assert len(errors) == 1
    assert errors[0].kind == "MISSING"
    assert errors[0].kind_type == "portraits"
    assert errors[0].key == ("anton",)
    assert "anton.png" in errors[0].field
    assert "site/images/" in errors[0].field

def test_validate_portraits_passes_when_file_present(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "anton.png").write_bytes(b"")
    party = {"members": [{"id": "anton", "image": "anton.png"}]}
    assert validate_portraits(party, images_dir) == []

def test_validate_portraits_skips_gm(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    party = {"members": [{"id": "gm", "image": "GM.png"}]}
    assert validate_portraits(party, images_dir) == []

def test_validate_portraits_skips_member_without_image(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    party = {"members": [{"id": "anton"}]}
    assert validate_portraits(party, images_dir) == []

def test_validate_dice_player_mapping_reports_unmapped():
    errors = validate_dice_player_mapping(["NewPlayer"])
    assert len(errors) == 1
    assert errors[0].kind == "MISSING"
    assert errors[0].kind_type == "dice_player_map"
    assert errors[0].key == ("NewPlayer",)
    assert "build/dice-players.json" in errors[0].field

def test_validate_dice_player_mapping_passes_when_empty():
    assert validate_dice_player_mapping([]) == []


def _fp(**atoms):
    """A one-PC fact pack for id 'a' plus a second PC 'b'."""
    base = {"a": {"is_party_luckiest": True, "kill_count": 5, "all_distinct_creatures": True},
            "b": {"is_party_luckiest": True, "kill_count": 2, "all_distinct_creatures": False}}
    base["a"].update(atoms)
    return base

def test_basis_mechanical_match_is_clean():
    authored = [{"id": "a", "distinction_basis": {"kind": "mechanical",
                 "atom": "is_party_luckiest", "value": True}}]
    errs = validate_distinction_basis(authored, _fp())
    assert errs == []

def test_basis_mechanical_mismatch_is_malformed():
    authored = [{"id": "a", "distinction_basis": {"kind": "mechanical",
                 "atom": "kill_count", "value": 99}}]
    errs = validate_distinction_basis(authored, _fp())
    assert len(errs) == 1
    assert errs[0].kind == "MALFORMED"

def test_basis_unknown_atom_is_malformed():
    authored = [{"id": "a", "distinction_basis": {"kind": "mechanical",
                 "atom": "no_such_atom", "value": 1}}]
    errs = validate_distinction_basis(authored, _fp())
    assert len(errs) == 1
    assert errs[0].kind == "MALFORMED"

def test_basis_narrative_skips_factpack_check():
    authored = [{"id": "a", "distinction_basis": {"kind": "narrative",
                 "sessions": [12], "note": "bargained with a devil"}}]
    errs = validate_distinction_basis(authored, _fp())
    assert errs == []

def test_basis_absent_is_tolerated():
    """Pre-migration characters without a basis must not fail the render."""
    authored = [{"id": "a", "distinction_title": "Foo"}]
    errs = validate_distinction_basis(authored, _fp())
    assert errs == []

def test_uniqueness_flags_shared_basis_atom():
    authored = [
        {"id": "a", "distinction_title": "Luck of A",
         "distinction_basis": {"kind": "mechanical", "atom": "is_party_luckiest", "value": True}},
        {"id": "b", "distinction_title": "Luck of B",
         "distinction_basis": {"kind": "mechanical", "atom": "is_party_luckiest", "value": True}},
    ]
    errs = validate_distinction_uniqueness(authored)
    assert any("is_party_luckiest" in (e.field or "") for e in errs)


import inspect
from build import render as _render

def test_validate_all_accepts_fact_pack_kwarg():
    sig = inspect.signature(_render.validate_all)
    assert "fact_pack" in sig.parameters


import json as _json
from pathlib import Path as _Path
import jsonschema

_PROMPTS = _Path(__file__).resolve().parent.parent / ".claude/prompts"

def _append_char_schema():
    return _json.loads((_PROMPTS / "append-characters.schema.json").read_text())

def test_append_char_schema_requires_basis():
    schema = _append_char_schema()
    good = {"reason": "r", "fields": {"a": {
        "epithet": "e", "reliquary_header": "r", "constellation_epithet": "c",
        "distinction_title": "t", "distinction_subtitle": "s", "distinction_detail": "d",
        "distinction_basis": {"kind": "mechanical", "atom": "kill_count", "value": 0}}}}
    jsonschema.validate(good, schema)
    bad = dict(good)
    bad["fields"] = {"a": {k: v for k, v in good["fields"]["a"].items() if k != "distinction_basis"}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)

def _refresh_char_schema():
    return _json.loads((_PROMPTS / "refresh-characters.schema.json").read_text())

def test_refresh_char_schema_requires_basis_on_rewrite():
    schema = _refresh_char_schema()
    good = {"decision": "rewrite", "reason": "r", "fields": {"a": {
        "epithet": "e", "constellation_epithet": "c", "distinction_title": "t",
        "distinction_subtitle": "s", "distinction_detail": "d",
        "distinction_basis": {"kind": "mechanical", "atom": "is_party_luckiest", "value": True}}}}
    jsonschema.validate(good, schema)  # must not raise

    bad = {"decision": "rewrite", "reason": "r", "fields": {"a": {
        "epithet": "e", "constellation_epithet": "c", "distinction_title": "t",
        "distinction_subtitle": "s", "distinction_detail": "d"}}}  # no basis
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
