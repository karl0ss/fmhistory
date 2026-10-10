"""Tests for the human manager event-log reader (`person_record_manager` head)."""

from __future__ import annotations

import dataclasses
import struct
from datetime import date

import pytest

from fmsave import field_status
from fmsave._errors import CorruptSaveError
from fmsave.models.career_history import ManagerEvent
from fmsave.readers.manager_events import (
    HEAD_BYTES,
    PAYLOAD_BYTES,
    decode_manager_event_logs,
)

_REFERENCE = 328408
_TEAM = 603
_UNSET = 0xFFFFFFFF
_NULL_DATE = struct.pack("<HH", 1, 1900)
_SECTION_HEAD = b"\x03\x01tad.\x1e\x00\x01"


def packed_date(day: date) -> bytes:
    """The 4-byte game date: [u16 day of year (low 9 bits)][u16 year]."""
    return struct.pack("<HH", day.timetuple().tm_yday, day.year)


def head(
    event_type: int,
    day: date,
    sub: int,
    importance: int,
    *,
    season: int = 2036,
    linked: tuple[int, int] = (0xFFFF, _UNSET),
    reference: int = _REFERENCE,
    mark: int = 0x15,
) -> bytes:
    """The 31-byte entry head."""
    data = (
        struct.pack("<BBHII", event_type, mark, linked[0], linked[1], reference)
        + b"\x00"
        + struct.pack("<I", _TEAM)
        + packed_date(day)
        + struct.pack("<HH", sub, importance)
        + b"\x00\x00\x00\x01"
        + struct.pack("<H", season)
    )
    assert len(data) == HEAD_BYTES
    return data


def transfer(
    day: date,
    sub: int,
    player: int,
    from_team: int,
    to_team: int,
    fee: int,
    effective: date | None = None,
) -> bytes:
    payload = (
        struct.pack("<BIBIII", 0, from_team, 0, to_team, player, fee)
        + b"\x00\x00"
        + (_NULL_DATE if effective is None else packed_date(effective))
        + b"\x00\x00\x00"
    )
    assert len(payload) == PAYLOAD_BYTES[2]
    return head(2, day, sub, 50) + payload


def award(day: date, award_index: int) -> bytes:
    return head(5, day, 22, 85) + struct.pack("<HB", award_index, 1)


def honour(day: date, competition: int, counter: int) -> bytes:
    payload = struct.pack("<HHHIIHBB", competition, 139, counter, 68184, 67340, 2, 1, 1)
    return head(1, day, 1, 100) + payload


def promotion(day: date, from_competition: int, to_competition: int) -> bytes:
    payload = struct.pack("<HHIHHB", from_competition, 139, 0, 1, to_competition, 0)
    return head(4, day, 2, 100) + payload


def player_award(day: date, award_index: int, player: int, value: int) -> bytes:
    payload = struct.pack("<HBII", award_index, 1, player, value) + bytes(5)
    return head(6, day, 31, 70) + payload


def match(day: date, goals_for: int, goals_against: int, opponent: int) -> bytes:
    payload = bytearray(PAYLOAD_BYTES[8])
    payload[0:3] = bytes([1, goals_for, goals_against])
    struct.pack_into("<I", payload, 4, _TEAM)
    payload[8:12] = packed_date(day)
    struct.pack_into("<I", payload, 13, _TEAM)
    struct.pack_into("<I", payload, 18, opponent)
    return head(8, day, 97, 70, linked=(83, 271672)) + bytes(payload)


def group(day: date, children: list[bytes], tail: int = 1) -> bytes:
    return (
        head(18, day, 90, 50)
        + struct.pack("<I", len(children))
        + b"".join(children)
        + bytes([tail])
    )


def section(entries: list[bytes], *, reference: int = _REFERENCE) -> bytes:
    """Section head, one log, the entries, and a 4-byte tail standing in for the records."""
    return (
        _SECTION_HEAD
        + struct.pack("<I", 1)
        + b"\x01"
        + struct.pack("<II", reference, len(entries))
        + b"".join(entries)
        + b"\xff\xff\xff\xff"
    )


def test_transfer_entry_decodes_teams_player_fee() -> None:
    data = section([transfer(date(2036, 8, 10), 3, 189608, 706, 603, 22_937_564)])
    (event,) = decode_manager_event_logs(data, len(data) - 4)
    assert event.reference == _REFERENCE
    assert event.event_type == 2
    assert event.sub_type == 3
    assert event.importance == 50
    assert event.team_id == _TEAM
    assert event.event_date == date(2036, 8, 10)
    assert event.season == 2036
    assert event.player_reference == 189608
    assert (event.from_team_id, event.to_team_id) == (706, 603)
    assert event.fee == 22_937_564
    assert event.effective_date is None
    assert event.award_index is None
    assert event.group_index is None
    assert event.unknown["head_u32"] == _UNSET


def test_unset_from_team_and_effective_date() -> None:
    entry = transfer(date(2024, 4, 12), 3, 67295, _UNSET, 603, 0, effective=date(2024, 5, 5))
    (event,) = decode_manager_event_logs(section([entry]))
    assert event.from_team_id is None
    assert event.fee == 0
    assert event.effective_date == date(2024, 5, 5)


def test_group_holds_the_following_entries() -> None:
    children = [
        transfer(date(2023, 7, 28), 3, 174962, _UNSET, 603, 0),
        transfer(date(2023, 8, 31), 3, 67779, _UNSET, 603, 0),
    ]
    data = section([group(date(2023, 7, 28), children, tail=1), award(date(2023, 12, 1), 2181)])
    events = decode_manager_event_logs(data, len(data) - 4)
    assert [event.event_type for event in events] == [18, 2, 2, 5]
    assert [event.index for event in events] == [0, 1, 2, 3]
    assert events[0].child_count == 2
    assert events[0].unknown["group_tail"] == 1
    assert [event.group_index for event in events] == [None, 0, 0, None]
    assert events[3].award_index == 2181


def test_typed_fields_per_type() -> None:
    entries = [
        honour(date(2025, 5, 11), 151, 53),
        promotion(date(2027, 4, 24), 10, 9),
        player_award(date(2024, 5, 6), 2186, 63174, 29),
        match(date(2036, 1, 30), 3, 2, 615),
    ]
    events = decode_manager_event_logs(section(entries))
    honour_event, promotion_event, award_event, match_event = events
    assert (honour_event.competition_id, honour_event.value) == (151, 53)
    assert (promotion_event.competition_id, promotion_event.to_competition_id) == (10, 9)
    assert (award_event.award_index, award_event.player_reference, award_event.value) == (
        2186,
        63174,
        29,
    )
    assert (match_event.goals_for, match_event.goals_against) == (3, 2)
    assert match_event.opponent_team_id == 615
    assert (match_event.unknown["head_u16"], match_event.unknown["head_u32"]) == (83, 271672)
    assert len(match_event.payload) == PAYLOAD_BYTES[8]


def test_untyped_entry_keeps_its_payload() -> None:
    payload = bytes.fromhex("ffff0500000000000000")
    data = section([head(3, date(2028, 7, 17), 42, 85) + payload])
    (event,) = decode_manager_event_logs(data)
    assert event.event_type == 3
    assert event.payload == tuple(payload)
    assert event.player_reference is None and event.value is None


def test_unknown_type_raises() -> None:
    with pytest.raises(CorruptSaveError, match="type 99"):
        decode_manager_event_logs(section([head(99, date(2030, 1, 1), 1, 50) + bytes(10)]))


def test_missing_mark_raises() -> None:
    entry = head(5, date(2030, 1, 1), 22, 85, mark=0x16) + b"\x63\x00\x01"
    with pytest.raises(CorruptSaveError, match="0x15"):
        decode_manager_event_logs(section([entry]))


def test_foreign_reference_raises() -> None:
    entry = head(5, date(2030, 1, 1), 22, 85, reference=7) + b"\x63\x00\x01"
    with pytest.raises(CorruptSaveError, match="reference 7"):
        decode_manager_event_logs(section([entry]))


def test_logs_must_end_where_the_records_start() -> None:
    data = section([award(date(2026, 5, 10), 144)])
    with pytest.raises(CorruptSaveError, match="not where the career records start"):
        decode_manager_event_logs(data, len(data))


def test_no_logs() -> None:
    data = _SECTION_HEAD + struct.pack("<I", 0) + b"\xff\xff\xff\xff"
    assert decode_manager_event_logs(data, len(data) - 4) == ()


def test_fields_are_registered_unconfirmed() -> None:
    for model_field in dataclasses.fields(ManagerEvent):
        assert field_status(ManagerEvent, model_field.name) == "unconfirmed"
