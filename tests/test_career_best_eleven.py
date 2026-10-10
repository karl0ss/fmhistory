"""Tests for the best-eleven decoder (`decode_best_eleven` / `Save.career_best_eleven`)."""

from __future__ import annotations

import struct

import pytest

from fmsave import field_status
from fmsave.models.career_history import BestElevenEntry
from fmsave.readers.career_history import (
    BEST_ELEVEN_DT_SECTION,
    BEST_ELEVEN_LS_SECTION,
    decode_best_eleven,
)

# The dt section opens with an 8-byte tag header; 509-byte records follow it back to back.
_HEADER = b"\x03\x01tmc.\x02\x00"
_RECORD = 509
_EMPTY = 0xFFFF_FFFF


def unit(
    reference: int = 1000,
    apps: int = 30,
    goals: int = 2,
    rating_total: int = 2040,
    natural: int = 4,
    secondary: int = 0,
    position: int = 4,
) -> bytes:
    """One 27-byte unit: [ref][apps][goals][rating total] 02 [natural] 02 [secondary] 02 [slot]."""
    return struct.pack(
        "<IHHIBIBIBI", reference, apps, goals, rating_total, 2, natural, 2, secondary, 2, position
    )


def empty_unit() -> bytes:
    """The unit an unfilled slot carries: reference unset, every count zero, tags kept."""
    return unit(_EMPTY, 0, 0, 0, 0, 0, 0)


def record(
    season: int = 2036,
    units: list[bytes] | None = None,
    table_type: int = 0,
    kind: int = 18,
    table_id: int = 98390,
    tail: bytes = bytes(13),
) -> bytes:
    """One 509-byte record: [season] 18 units [13 B tail] [type][kind] 00 [table id] 04."""
    units = units if units is not None else [unit(1000 + slot) for slot in range(18)]
    assert len(units) == 18
    body = struct.pack("<H", season) + b"".join(units) + tail
    return body + bytes([table_type, kind, 0]) + struct.pack("<I", table_id) + b"\x04"


def dt_blob(*records: bytes) -> bytes:
    """Records butted behind the 8-byte section header, as the real section stores them."""
    return _HEADER + b"".join(records)


def ls_blob(*club_records: tuple[int, ...]) -> bytes:
    """A `tc_best_eleven_history_ls` index listing record numbers per club (delta-encoded)."""
    body = b""
    for numbers in club_records:
        values: list[int] = []
        previous = 0
        for number in numbers:
            value = number * _RECORD - previous
            values.append(value)
            previous = value
        body += struct.pack(f"<I{len(values)}I", len(values), *values)
    head = b"\x03\x01tad.\x04\x00" + struct.pack("<II", 0, len(club_records))
    return head + body + struct.pack("<IIH", 0, _RECORD, 2)


def test_dt_and_ls_sections_are_the_inputs() -> None:
    assert BEST_ELEVEN_DT_SECTION == "tc_best_eleven_history_dt"
    assert BEST_ELEVEN_LS_SECTION == "tc_best_eleven_history_ls"


def test_a_record_is_509_bytes() -> None:
    assert len(record()) == _RECORD
    assert len(unit()) == 27


def test_one_unit_decodes_every_field() -> None:
    units = [unit(458697, 48, 0, 3120, 1, 0, 1)] + [empty_unit()] * 17
    (entry,) = decode_best_eleven(dt_blob(record(2036, units, 0, 18, 98390)), b"")
    assert entry == BestElevenEntry(
        record_index=0,
        season_year=2036,
        table_type=0,
        kind=18,
        table_id=98390,
        slot=0,
        player_reference=458697,
        appearances=48,
        goals=0,
        rating_total=3120,
        average_rating=6.5,
        natural_positions=1,
        secondary_positions=0,
        table_position=1,
        history_index=None,
        player_uid=None,
    )


def test_the_identity_head_closes_the_record_not_the_next_one() -> None:
    dt = dt_blob(record(2035, kind=13, table_id=111), record(2036, kind=18, table_id=222))
    entries = decode_best_eleven(dt, b"")
    assert {(e.record_index, e.season_year, e.kind, e.table_id) for e in entries} == {
        (0, 2035, 13, 111),
        (1, 2036, 18, 222),
    }


def test_every_filled_slot_is_a_row_in_record_then_slot_order() -> None:
    dt = dt_blob(record(2035), record(2036))
    entries = decode_best_eleven(dt, b"")
    assert len(entries) == 36
    assert [(e.record_index, e.slot) for e in entries] == [
        (index, slot) for index in range(2) for slot in range(18)
    ]
    assert [e.player_reference for e in entries[:18]] == list(range(1000, 1018))


def test_empty_slots_are_skipped() -> None:
    units = [unit(1000 + slot) for slot in range(11)] + [empty_unit()] * 7
    entries = decode_best_eleven(dt_blob(record(units=units)), b"")
    assert [e.slot for e in entries] == list(range(11))


def test_average_rating_is_the_rating_total_per_appearance_over_ten() -> None:
    units = [unit(1, 30, 0, 2040), unit(2, 0, 0, 0)] + [empty_unit()] * 16
    first, second = decode_best_eleven(dt_blob(record(units=units)), b"")
    assert first.average_rating == pytest.approx(6.8)
    assert second.appearances == 0
    assert second.average_rating is None


def test_a_record_that_fails_its_check_is_skipped() -> None:
    good = record(2036)
    bad_end = good[:-1] + b"\x05"
    bad_zero = good[:-6] + b"\x01" + good[-5:]
    bad_tag = good[:14] + b"\x03" + good[15:]
    bad_year = struct.pack("<H", 1700) + good[2:]
    for bad in (bad_end, bad_zero, bad_tag, bad_year):
        entries = decode_best_eleven(dt_blob(bad, good), b"")
        assert {e.record_index for e in entries} == {1}


def test_a_truncated_last_record_and_short_sections_are_not_read() -> None:
    dt = dt_blob(record(2036), record(2037))
    assert {e.season_year for e in decode_best_eleven(dt[:-1], b"")} == {2036}
    assert decode_best_eleven(_HEADER, b"") == ()
    assert decode_best_eleven(b"", b"") == ()
    assert decode_best_eleven(_HEADER + b"\x00" * 100, b"") == ()


def test_records_carry_their_club_list_number() -> None:
    dt = dt_blob(record(2034), record(2034), record(2035), record(2035))
    entries = decode_best_eleven(dt, ls_blob((0, 2), (1, 3)))
    by_record = {e.record_index: e.history_index for e in entries}
    assert by_record == {0: 0, 1: 1, 2: 0, 3: 1}


def test_an_index_that_does_not_parse_leaves_records_unthreaded() -> None:
    dt = dt_blob(record(2036))
    good = ls_blob((0,))
    for ls in (b"", b"\xff" * 64, good[:-1], good + b"\x00" * 4):
        assert {e.history_index for e in decode_best_eleven(dt, ls)} == {None}
    assert {e.history_index for e in decode_best_eleven(dt, good)} == {0}


def test_every_field_is_unconfirmed() -> None:
    for name in BestElevenEntry.__dataclass_fields__:
        assert field_status(BestElevenEntry, name) == "unconfirmed"
