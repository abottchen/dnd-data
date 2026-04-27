"""One-shot: merge dicedata.txt chat-log rolls back into dicex-rolls-2026-04-27.json.

Replaces all 2026-04-27 rolls per player with rolls reconstructed from the chat
paste; pre-2026-04-27 rolls are left untouched. Run from repo root.
"""
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

LINE_RE = re.compile(r'^\[(\d+):(\d+):(\d+) (AM|PM)\] - Dicex')
ROLL_RE = re.compile(r'•\s+(?:🔒\s+)?(.+?)\s+rolled\s+\((.+?)\)\s+for\s+\*\*(-?\d+)\*\*!')
SESSION_LOCAL = datetime(2026, 4, 26)
PDT_OFFSET = timedelta(hours=7)
TODAY_PREFIX = "2026-04-27"


def parse_dice_content(content: str):
    blocks = re.split(r',\s*(?=\d+d\d+\s*→)', content)
    dice = []
    spec_strs = []
    mod_val = 0
    has_mod = False
    for block in blocks:
        m = re.match(r'(\d+)d(\d+)\s*→\s*(.+)', block.strip())
        n, sides, rest = int(m.group(1)), int(m.group(2)), m.group(3)
        vals = [int(v) for v in re.findall(r'\[(?:💀|⭐)?\s*(-?\d+)\s*\]', rest)]
        for v in vals:
            dice.append({"type": f"d{sides}", "value": v})
        spec_strs.append(f"{n}d{sides}")
        mod_m = re.search(r'\]\s*([+-])\s*(\d+)\s*$', rest)
        if mod_m:
            sign = -1 if mod_m.group(1) == '-' else 1
            mod_val = sign * int(mod_m.group(2))
            has_mod = True
    if has_mod:
        dice.append({"type": "mod", "value": mod_val})
    if spec_strs == ["1d100", "1d10"]:
        notation = "1d100"
    else:
        notation = "+".join(spec_strs)
        if has_mod:
            notation += ("+" if mod_val >= 0 else "") + str(mod_val)
    return dice, notation


def parse_log(path: Path):
    events = []
    ts = None
    for line in path.read_text().splitlines():
        line = line.strip()
        m = LINE_RE.match(line)
        if m:
            h, mi, s, ap = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            if ap == 'PM' and h != 12:
                h += 12
            elif ap == 'AM' and h == 12:
                h = 0
            local_dt = SESSION_LOCAL.replace(hour=h, minute=mi, second=s)
            ts = (local_dt + PDT_OFFSET).replace(tzinfo=timezone.utc)
            continue
        rm = ROLL_RE.match(line)
        if rm and ts is not None:
            player, content, total = rm.group(1).strip(), rm.group(2).strip(), int(rm.group(3))
            dice, notation = parse_dice_content(content)
            sumv = sum(d['value'] for d in dice)
            assert sumv == total, f"sum mismatch on {player} {notation} {dice} expected {total}"
            ts_str = ts.strftime('%Y-%m-%dT%H:%M:%S') + '.000Z'
            events.append({
                'player_name': player,
                'event': {
                    'dice': dice,
                    'total': total,
                    'notation': notation,
                    'timestamp': ts_str,
                },
            })
            ts = None
    return events


def main():
    repo = Path(__file__).resolve().parent.parent
    log_path = repo / 'data' / 'dicedata.txt'
    file_path = repo / 'data' / 'dicex-rolls-2026-04-27.json'

    events = parse_log(log_path)
    print(f"Parsed {len(events)} events from {log_path.name}")

    data = json.loads(file_path.read_text())

    # Pick one UUID per player name to receive new today-rolls: prefer the UUID that
    # already has any 2026-04-27 roll. Fallback to first matching UUID.
    name_to_uuid = {}
    for uuid, pdata in data['players'].items():
        nm = pdata['name']
        has_today = any(r['timestamp'].startswith(TODAY_PREFIX) for r in pdata['rolls'])
        if has_today or nm not in name_to_uuid:
            name_to_uuid[nm] = uuid

    # Strip today-rolls from every UUID
    stripped_total = 0
    for uuid, pdata in data['players'].items():
        before = len(pdata['rolls'])
        pdata['rolls'] = [r for r in pdata['rolls'] if not r['timestamp'].startswith(TODAY_PREFIX)]
        stripped_total += before - len(pdata['rolls'])
    print(f"Stripped {stripped_total} pre-existing today-rolls")

    # Append chat-log events to the chosen UUID per player name
    added_per = {}
    for ev in events:
        nm = ev['player_name']
        uuid = name_to_uuid.get(nm)
        if uuid is None:
            print(f"  skipping unknown player: {nm}")
            continue
        data['players'][uuid]['rolls'].append(ev['event'])
        added_per[nm] = added_per.get(nm, 0) + 1

    # Sort each player's rolls by timestamp
    for pdata in data['players'].values():
        pdata['rolls'].sort(key=lambda r: r['timestamp'])

    print("Added per player:")
    for nm, n in sorted(added_per.items()):
        print(f"  {nm}: +{n}")

    # Bump exportedAt to reflect the merge (keeps semantics: 'last seen' time)
    data['exportedAt'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"

    file_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Wrote {file_path}")


if __name__ == '__main__':
    main()
