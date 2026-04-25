import json
from pathlib import Path
from build import load_data

def test_load_data_returns_party_dice_and_sessionlog(tmp_path: Path):
    (tmp_path / "party.json").write_text(json.dumps({"members": []}))
    (tmp_path / "dicex-rolls-2026-04-23.json").write_text(json.dumps([{"player": "x"}]))
    (tmp_path / "session-log.json").write_text(json.dumps({"entries": []}))

    data = load_data(tmp_path)

    assert data["party"] == {"members": []}
    assert isinstance(data["dice_rolls"], list)
    assert data["dice_rolls"][0][0]["player"] == "x"
    assert data["session_log"] == {"entries": []}

def test_load_data_collects_all_dice_files(tmp_path: Path):
    (tmp_path / "party.json").write_text(json.dumps({}))
    (tmp_path / "session-log.json").write_text(json.dumps({}))
    (tmp_path / "dicex-rolls-2026-04-01.json").write_text(json.dumps([{"r": 1}]))
    (tmp_path / "dicex-rolls-2026-04-23.json").write_text(json.dumps([{"r": 2}]))

    data = load_data(tmp_path)

    assert len(data["dice_rolls"]) == 2
