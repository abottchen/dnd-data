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


# -- NPC circles -------------------------------------------------------------

def _schema(name: str) -> dict:
    return json.loads((PROMPTS / f"{name}.schema.json").read_text())


def _npc_fields(**over) -> dict:
    base = {"epithet": "of the guides", "circle": "guides"}
    base.update(over)
    return base


def test_append_npcs_requires_circle():
    schema = _schema("append-npcs")
    jsonschema.validate({"fields": _npc_fields(), "reason": "r"}, schema)
    bad = {"fields": {"epithet": "e"}, "reason": "r"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_append_npcs_allows_null_circle():
    jsonschema.validate({"fields": _npc_fields(circle=None), "reason": "r"},
                        _schema("append-npcs"))


@pytest.mark.parametrize("circle", [
    ["guides"],                # the retired list form
    "The Guides",              # not a slug
    "guides-",                 # trailing hyphen
    "",                        # blank
])
def test_append_npcs_rejects_malformed_circle(circle):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"fields": _npc_fields(circle=circle), "reason": "r"},
                            _schema("append-npcs"))


@pytest.mark.parametrize("name", ["append-npcs", "refresh-npcs"])
def test_npc_schemas_refuse_retired_fields(name):
    """allegiance and circles left the contract; a result carrying them is
    refused rather than silently stripped."""
    schema = _schema(name)
    for stale in ({"allegiance": "with"}, {"circles": ["guides"]}):
        bad = {"fields": _npc_fields(**stale), "reason": "r"}
        if name == "refresh-npcs":
            bad["decision"] = "rewrite"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


def test_refresh_npcs_rewrite_requires_circle():
    schema = _schema("refresh-npcs")
    jsonschema.validate({"decision": "rewrite", "fields": _npc_fields(), "reason": "r"},
                        schema)
    jsonschema.validate({"decision": "rewrite", "fields": _npc_fields(circle=None),
                         "reason": "r"}, schema)
    bad = {"decision": "rewrite", "fields": {"epithet": "e"}, "reason": "r"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_refresh_known_npcs_circles_are_optional():
    schema = _schema("refresh-known-npcs")
    jsonschema.validate({"decision": "rewrite",
                         "fields": {"known_npcs": ["Azlund"]}, "reason": "r"}, schema)


def test_refresh_known_npcs_accepts_circle_additions():
    schema = _schema("refresh-known-npcs")
    ok = {"decision": "rewrite", "reason": "r", "fields": {
        "known_npcs": ["Azlund", "Xhosala", "Acererak"],
        "circles": [
            {"key": "obanashi", "title": "The Obanashi", "members": ["Xhosala"]},
            {"key": "enemy", "title": "The Enemy", "billing": "principal",
             "members": ["Acererak"]},
        ],
    }}
    jsonschema.validate(ok, schema)


def _addition(**over):
    base = {"key": "obanashi", "title": "The Obanashi", "members": ["Xhosala"]}
    base.update(over)
    for k in [k for k, v in base.items() if v is None]:
        del base[k]
    return base


@pytest.mark.parametrize("circle", [
    _addition(billing="star"),               # not a billing
    _addition(kind="company"),               # the retired field
    _addition(title=""),                     # blank title
    _addition(title=None),                   # no title
    _addition(key="The Obanashi"),           # not a slug
    _addition(key=None),                     # no key
    _addition(members=None),                 # no members: who belongs?
    _addition(members=[]),                   # a circle nobody belongs to
    _addition(members="Xhosala"),            # not a list
    _addition(members=["Xhosala", "Xhosala"]),  # duplicate member
    _addition(note="x"),                     # extra prop
])
def test_refresh_known_npcs_rejects_malformed_circle_additions(circle):
    schema = _schema("refresh-known-npcs")
    bad = {"decision": "rewrite", "reason": "r",
           "fields": {"known_npcs": ["Azlund"], "circles": [circle]}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_refresh_known_npcs_rejects_duplicate_circle_additions():
    schema = _schema("refresh-known-npcs")
    c = _addition()
    bad = {"decision": "rewrite", "reason": "r",
           "fields": {"known_npcs": ["Azlund"], "circles": [c, dict(c)]}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
