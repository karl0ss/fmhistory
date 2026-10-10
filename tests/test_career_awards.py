"""Tests for the yearly award history decoder (`decode_awards` / `Save.career_awards`)."""

from __future__ import annotations

import struct

import pytest

from fmsave._errors import CorruptSaveError
from fmsave.readers.career_history import AWARD_SECTION, decode_awards

_HEAD = bytes.fromhex("03 01 74 6d 63 2e 01 00")
_UNSET = 0xFFFF_FFFF
# A slot's 10 bytes after the age, in the sparse shape the real slots carry.
_STATS = bytes([35, 0, 46, 0, 129, 0, 59, 0, 6, 0])


def slot(
    winner: int = _UNSET,
    club: int = _UNSET,
    age: int = 0,
    flags: int = 0,
    tag: int = 0xFFFF,
    stats: bytes = _STATS,
) -> bytes:
    """One 26-byte placing slot: [winner][club][age][10 bytes][02][flags][tag]."""
    return (
        struct.pack("<II", winner, club)
        + bytes([age])
        + stats
        + b"\x02"
        + struct.pack("<IH", flags, tag)
    )


def record(year: int, award: int, *slots: bytes) -> bytes:
    """One 82-byte record: [year][award] and three slots, empty ones filled in."""
    filled = list(slots) + [slot(stats=bytes(10))] * (3 - len(slots))
    return struct.pack("<HH", year, award) + b"".join(filled)


def test_winner_slot_decodes_every_field() -> None:
    data = _HEAD + record(2031, 99, slot(328408, 716, 45, tag=0x8B))
    (award,) = decode_awards(data)
    assert award.season_year == 2031
    assert award.award_id == 99
    assert award.placing == 0
    assert award.tag == 0x8B
    assert award.winner_id == 328408
    assert award.club_uid == 716
    assert award.winner_age == 45
    assert award.tail == (45, *_STATS)


def test_runner_up_and_third_slots_become_rows_with_their_placing() -> None:
    data = _HEAD + record(
        2025, 2177, slot(1111, 700, 30), slot(328408, 716, 39, tag=0x8B), slot(2222, 701, 50)
    )
    awards = decode_awards(data)
    assert [(award.placing, award.winner_id, award.club_uid) for award in awards] == [
        (0, 1111, 700),
        (1, 328408, 716),
        (2, 2222, 701),
    ]


def test_empty_slots_are_left_out_and_records_keep_file_order() -> None:
    data = (
        _HEAD
        + record(2026, 144, slot(328408, 716, 40))
        + record(2027, 5)
        + record(1990, 4, slot(716, _UNSET, 0))
    )
    awards = decode_awards(data)
    assert [(award.season_year, award.award_id, award.club_uid) for award in awards] == [
        (2026, 144, 716),
        (1990, 4, None),
    ]


def test_header_only_section_has_no_rows() -> None:
    assert decode_awards(_HEAD) == ()


def test_section_off_the_record_grid_is_refused() -> None:
    with pytest.raises(CorruptSaveError):
        decode_awards(_HEAD + record(2031, 99, slot(1, 2, 30)) + b"\x00")


def test_wrong_head_is_refused() -> None:
    with pytest.raises(CorruptSaveError):
        decode_awards(b"\x03\x01tad.\x01\x00" + record(2031, 99, slot(1, 2, 30)))


def test_slot_without_its_mark_is_refused() -> None:
    bad = bytearray(_HEAD + record(2031, 99, slot(1, 2, 30)))
    bad[8 + 4 + 26 + 19] = 0
    with pytest.raises(CorruptSaveError):
        decode_awards(bytes(bad))


def test_section_name_is_the_award_year_section() -> None:
    assert AWARD_SECTION == "award_year_hist_dt"
