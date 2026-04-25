import pytest
from build import (
    ValidationError, KIND_MISSING, KIND_MALFORMED, KIND_ORPHAN, validate_kills,
    validate_sessions, validate_chapters, validate_npcs, validate_characters, validate_site,
)

def test_validation_error_format_missing():
    e = ValidationError(KIND_MISSING, "kills", ("anton", "2026-04-23", "yuan-ti broodguard", "vicious mockery"))
    assert str(e) == "MISSING kills (anton, 2026-04-23, yuan-ti broodguard, vicious mockery)"

def test_validation_error_format_malformed():
    e = ValidationError(KIND_MALFORMED, "sessions", ("V",), field="title")
    assert str(e) == "MALFORMED sessions (V) field=title"

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
    log = {"entries": [{"session": "V", "date": "2026-04-23"}]}
    errors = validate_sessions(log, [])
    assert len(errors) == 1
    assert errors[0].kind == "MISSING"

def test_validate_sessions_malformed_missing_silent_roll():
    log = {"entries": [{"session": "V", "date": "2026-04-23"}]}
    authored = [{"session": "V", "title": "t", "summary": "s"}]  # silent_roll missing
    errors = validate_sessions(log, authored)
    assert any(e.field == "silent_roll" for e in errors)

def test_validate_chapters_missing():
    log = {"entries": [{"session": "I", "chapter_marker": True}]}
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
