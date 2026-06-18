"""Single source of truth for transformer wiring.

Each transformer is described once: the prompt name (matches
.claude/prompts/<name>.md), the pass it belongs to, the slice builder that
emits its slices, and the apply function that absorbs its results.

`prepare.py` iterates ALL to gather slices. `apply_cli.py` looks entries up
by name to dispatch the right apply function. Keeping the wiring here means
the two scripts cannot drift out of sync.
"""
from dataclasses import dataclass
from typing import Callable

from . import apply, slices


@dataclass(frozen=True)
class Transformer:
    name: str
    pass_name: str  # "discovery" | "append" | "refresh"
    slice_builder: Callable
    apply_fn: Callable


ALL: tuple[Transformer, ...] = (
    Transformer("refresh-known-npcs", "discovery",
                slices.refresh_known_npcs, apply.apply_refresh_known_npcs),

    Transformer("append-kills", "append",
                slices.append_kills, apply.apply_append_kills),
    Transformer("append-sessions", "append",
                slices.append_sessions, apply.apply_append_sessions),
    Transformer("append-chapters", "append",
                slices.append_chapters, apply.apply_append_chapters),
    Transformer("append-npcs", "append",
                slices.append_npcs, apply.apply_append_npcs),
    Transformer("append-characters", "append",
                slices.append_characters, apply.apply_append_characters),
    Transformer("append-sworn", "append",
                slices.append_sworn, apply.apply_append_sworn),

    Transformer("refresh-chapters", "refresh",
                slices.refresh_chapters, apply.apply_refresh_chapters),
    Transformer("refresh-npcs", "refresh",
                slices.refresh_npcs, apply.apply_refresh_npcs),
    Transformer("refresh-characters", "refresh",
                slices.refresh_characters, apply.apply_refresh_characters),
    Transformer("refresh-road-ahead", "refresh",
                slices.refresh_road_ahead, apply.apply_refresh_road_ahead),
    Transformer("refresh-intro-epithet", "refresh",
                slices.refresh_intro_epithet, apply.apply_refresh_intro_epithet),
    Transformer("refresh-ascent-read", "refresh",
                slices.refresh_ascent_read, apply.apply_refresh_ascent_read),
    Transformer("refresh-archetype-inscription", "refresh",
                slices.refresh_archetype_inscription,
                apply.apply_refresh_archetype_inscription),
)

_VALID_PASSES = {"discovery", "append", "refresh"}
assert all(t.pass_name in _VALID_PASSES for t in ALL), (
    "registry: unknown pass_name(s): "
    + str({t.pass_name for t in ALL} - _VALID_PASSES)
)

_BY_NAME = {t.name: t for t in ALL}


def by_name(name: str) -> Transformer:
    """Look up a transformer by name. Raises KeyError if missing."""
    return _BY_NAME[name]
