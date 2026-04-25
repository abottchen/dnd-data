import pytest
from build import ValidationError, KIND_MISSING, KIND_MALFORMED, KIND_ORPHAN, validate_kills

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
