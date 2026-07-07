"""Refresh schemas must reject decision=rewrite with fields=null."""
import json
from pathlib import Path

import jsonschema
import pytest

PROMPTS = Path(__file__).resolve().parent.parent / ".claude" / "prompts"
REFRESH_SCHEMAS = sorted(PROMPTS.glob("refresh-*.schema.json"))


@pytest.mark.parametrize("schema_path", REFRESH_SCHEMAS, ids=lambda p: p.stem)
def test_rewrite_requires_fields_object(schema_path):
    schema = json.loads(schema_path.read_text())
    bad = {"decision": "rewrite", "fields": None, "reason": "r"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


@pytest.mark.parametrize("schema_path", REFRESH_SCHEMAS, ids=lambda p: p.stem)
def test_no_change_allows_null_fields(schema_path):
    schema = json.loads(schema_path.read_text())
    ok = {"decision": "no_change", "fields": None, "reason": "r"}
    jsonschema.validate(ok, schema)  # must not raise
