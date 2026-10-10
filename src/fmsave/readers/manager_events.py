"""Decoding the human managers' event logs at the head of `person_record_manager`.

The section (`03 01 'tad.'`, version 30 on the ground-truth save) opens with one event
log per human manager, before the 367-byte career records `manager_career` reads:

    +0    03 01 'tad.' u16 version
    +8    u8 (01 on the ground-truth save)
    +9    u32 number of logs
    then per log:
          u8 (01)  u32 manager history reference  u32 number of top-level entries
          entries

Every entry opens with the same 31-byte head (offsets from the entry start; `date` is the
4-byte packed game date `_scan.decode_date` reads):

    +0    u8 type        +1  u8 0x15 (every entry)
    +2    u16, u32       0xffff / 0xffffffff on most entries; a (small, ~271,6xx) pair
                         on some match, record and attendance entries (meaning open)
    +8    u32 manager history reference   +12 u8 0
    +13   u32 team (`Team.team_id` of the manager's team)
    +17   date (the event's date)          +21 u16 sub-type   +23 u16 importance
    +25   u8 0  +26 u8 (0, 5, 8, 13, 23 or 24; meaning open)  +27 u8 0  +28 u8 01
    +29   u16 season (the year the season starts)

followed by a payload whose length is fixed by the type (`PAYLOAD_BYTES`). Type 18 is a
group: its payload is a u32 child count, that many nested entries, and one closing byte.
There are no length fields, so an unknown type stops the walk (`CorruptSaveError`).

Payload fields read (offsets from the payload start):

    type 1   +0 u16 competition  +4 u16 value (honour counter / season points)
    type 2   +1 u32 from team  +6 u32 to team  +10 u32 player reference  +14 u32 fee £
             +20 date the move takes effect (null when immediate)
    type 4   +0 u16 competition  +10 u16 competition promoted to
    type 5   +0 u16 award index
    type 6   +0 u16 award index  +3 u32 player reference  +7 u32 value (award statistic)
    type 8   +1 u8 goals for  +2 u8 goals against  +18 u32 opponent team
    type 9   +0 u32 player reference  +4 u32 value

The layout was reverse-engineered on one save (`Karl Hudgell - UnemployedNew.fm`, build
26.3.2: one log, 141 top-level and 186 entries in all, ending exactly where the career
records start) and is not verified across builds.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import date

from fmsave._errors import CorruptSaveError
from fmsave._frozen import FrozenMapping
from fmsave._scan import decode_date
from fmsave.models.career_history import ManagerEvent

LOGS_COUNT_AT = 9
LOGS_AT = 13
HEAD_BYTES = 31
ENTRY_MARK = 0x15
GROUP_TYPE = 18

# Payload bytes after the 31-byte head, per entry type. Type 18 (a group) is variable.
PAYLOAD_BYTES: dict[int, int] = {
    1: 18,
    2: 27,
    3: 10,
    4: 13,
    5: 3,
    6: 16,
    7: 12,
    8: 54,
    9: 18,
    11: 20,
    13: 13,
    16: 18,
    17: 21,
}

_UNSET = 0xFFFFFFFF
_U16 = struct.Struct("<H")
_U32 = struct.Struct("<I")


def _u16(data: bytes, offset: int) -> int:
    value: int = _U16.unpack_from(data, offset)[0]
    return value


def _u32(data: bytes, offset: int) -> int:
    value: int = _U32.unpack_from(data, offset)[0]
    return value


def _team(data: bytes, offset: int) -> int | None:
    team = _u32(data, offset)
    return None if team == _UNSET else team


@dataclass(slots=True)
class _Typed:
    """The payload fields one entry type carries; everything else stays None."""

    player_reference: int | None = None
    from_team_id: int | None = None
    to_team_id: int | None = None
    fee: int | None = None
    effective_date: date | None = None
    award_index: int | None = None
    value: int | None = None
    competition_id: int | None = None
    to_competition_id: int | None = None
    opponent_team_id: int | None = None
    goals_for: int | None = None
    goals_against: int | None = None


def _typed_fields(event_type: int, payload: bytes) -> _Typed:
    typed = _Typed()
    if event_type == 1:
        typed.competition_id = _u16(payload, 0)
        typed.value = _u16(payload, 4)
    elif event_type == 2:
        typed.from_team_id = _team(payload, 1)
        typed.to_team_id = _team(payload, 6)
        typed.player_reference = _u32(payload, 10)
        typed.fee = _u32(payload, 14)
        typed.effective_date = decode_date(payload, 20)
    elif event_type == 4:
        typed.competition_id = _u16(payload, 0)
        typed.to_competition_id = _u16(payload, 10)
    elif event_type == 5:
        typed.award_index = _u16(payload, 0)
    elif event_type == 6:
        typed.award_index = _u16(payload, 0)
        typed.player_reference = _u32(payload, 3)
        typed.value = _u32(payload, 7)
    elif event_type == 8:
        typed.goals_for = payload[1]
        typed.goals_against = payload[2]
        typed.opponent_team_id = _team(payload, 18)
    elif event_type == 9:
        typed.player_reference = _u32(payload, 0)
        typed.value = _u32(payload, 4)
    return typed


class _LogWalker:
    """Walks one log's entries, appending each (groups before their children)."""

    def __init__(self, data: bytes, reference: int) -> None:
        self._data = data
        self._reference = reference
        self.events: list[ManagerEvent] = []

    def entry(self, offset: int, group_index: int | None) -> int:
        data = self._data
        if offset + HEAD_BYTES > len(data):
            raise CorruptSaveError(
                f"person_record_manager event log runs past the section end at {offset}"
            )
        event_type = data[offset]
        if data[offset + 1] != ENTRY_MARK:
            raise CorruptSaveError(
                f"person_record_manager event entry at {offset} does not carry the 0x15 "
                f"mark (type {event_type}, mark {data[offset + 1]:#x}): the layout has moved"
            )
        reference = _u32(data, offset + 8)
        if reference != self._reference:
            raise CorruptSaveError(
                f"person_record_manager event entry at {offset} names reference "
                f"{reference}, not its log's {self._reference}"
            )
        unknown = {
            "head_u16": _u16(data, offset + 2),
            "head_u32": _u32(data, offset + 4),
            "byte_26": data[offset + 26],
        }
        payload_at = offset + HEAD_BYTES
        index = len(self.events)
        if event_type == GROUP_TYPE:
            child_count = _u32(data, payload_at)
            self.events.append(self._event(offset, index, group_index, _Typed(), unknown))
            position = payload_at + 4
            for _ in range(child_count):
                position = self.entry(position, index)
            unknown["group_tail"] = data[position]
            payload = data[payload_at : payload_at + 4] + data[position : position + 1]
            self.events[index] = self._event(
                offset, index, group_index, _Typed(), unknown, payload, child_count
            )
            return position + 1
        size = PAYLOAD_BYTES.get(event_type)
        if size is None:
            raise CorruptSaveError(
                f"person_record_manager event entry at {offset} has type {event_type}, "
                "whose payload length is not known: the log cannot be walked past it"
            )
        payload = data[payload_at : payload_at + size]
        typed = _typed_fields(event_type, payload)
        self.events.append(self._event(offset, index, group_index, typed, unknown, payload))
        return payload_at + size

    def _event(
        self,
        offset: int,
        index: int,
        group_index: int | None,
        typed: _Typed,
        unknown: dict[str, int],
        payload: bytes = b"",
        child_count: int | None = None,
    ) -> ManagerEvent:
        data = self._data
        return ManagerEvent(
            reference=self._reference,
            index=index,
            group_index=group_index,
            event_type=data[offset],
            sub_type=_u16(data, offset + 21),
            importance=_u16(data, offset + 23),
            team_id=_team(data, offset + 13),
            event_date=decode_date(data, offset + 17),
            season=_u16(data, offset + 29),
            child_count=child_count,
            player_reference=typed.player_reference,
            from_team_id=typed.from_team_id,
            to_team_id=typed.to_team_id,
            fee=typed.fee,
            effective_date=typed.effective_date,
            award_index=typed.award_index,
            value=typed.value,
            competition_id=typed.competition_id,
            to_competition_id=typed.to_competition_id,
            opponent_team_id=typed.opponent_team_id,
            goals_for=typed.goals_for,
            goals_against=typed.goals_against,
            payload=tuple(payload),
            unknown=FrozenMapping(dict(unknown)),
        )


def decode_manager_event_logs(data: bytes, end: int | None = None) -> tuple[ManagerEvent, ...]:
    """Every entry of every human manager's event log, in log and file order.

    A group entry (type 18) comes before its children, which carry its `index` as
    `group_index`. `index` counts within one log.

    Args:
        data: The `person_record_manager` section.
        end: Where the logs must end (the first career record), or None to skip
            that check.

    Raises:
        CorruptSaveError: The logs cannot be walked (an unknown entry type, an entry
            without the 0x15 mark, a reference that is not the log's) or do not end
            at `end`.
    """
    if len(data) < LOGS_AT:
        raise CorruptSaveError(
            f"person_record_manager is {len(data)} bytes, too short for its log head"
        )
    log_count = _u32(data, LOGS_COUNT_AT)
    position = LOGS_AT
    events: list[ManagerEvent] = []
    for _ in range(log_count):
        if position + 9 > len(data):
            raise CorruptSaveError(
                f"person_record_manager event log head at {position} runs past the section"
            )
        reference = _u32(data, position + 1)
        entry_count = _u32(data, position + 5)
        walker = _LogWalker(data, reference)
        position += 9
        for _ in range(entry_count):
            position = walker.entry(position, None)
        events.extend(walker.events)
    if end is not None and position != end:
        raise CorruptSaveError(
            f"person_record_manager event logs end at {position}, not where the career "
            f"records start ({end}): the log layout has moved"
        )
    return tuple(events)
