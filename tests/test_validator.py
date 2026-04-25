import pytest
from build import ValidationError, KIND_MISSING, KIND_MALFORMED, KIND_ORPHAN

def test_validation_error_format_missing():
    e = ValidationError(KIND_MISSING, "kills", ("anton", "2026-04-23", "yuan-ti broodguard", "vicious mockery"))
    assert str(e) == "MISSING kills (anton, 2026-04-23, yuan-ti broodguard, vicious mockery)"

def test_validation_error_format_malformed():
    e = ValidationError(KIND_MALFORMED, "sessions", ("V",), field="title")
    assert str(e) == "MALFORMED sessions (V) field=title"

def test_validation_error_format_orphan():
    e = ValidationError(KIND_ORPHAN, "kills", ("anton", "2025-12-15", "gnoll", "scimitar"))
    assert str(e) == "ORPHAN kills (anton, 2025-12-15, gnoll, scimitar)"
