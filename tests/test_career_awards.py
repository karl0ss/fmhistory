"""Tests for the yearly award history decoder (`decode_awards` / `Save.career_awards`)."""

from __future__ import annotations

import struct

from fmsave.readers.career_history import AWARD_SECTION, decode_awards

_FLAGS = bytes([0, 0, 0, 0])
# A trailing block in the sparse shape the real rows carry: an age with values around it.
_TAIL = bytes([39, 46, 0, 100, 0, 50, 0, 10, 0, 6, 0])


def head_row(tag: int, year: int, award: int, winner: int, club: int, tail: bytes) -> bytes:
    """One 30-byte headed record."""
    return b"\x02" + _FLAGS + struct.pack("<HHHII", tag, year, award, winner, club) + tail


def head_row_without_club(tag: int, year: int, award: int, winner: int, tail: bytes) -> bytes:
    """One 26-byte headed record, the shape a record whose winner is a club itself carries."""
    return b"\x02" + _FLAGS + struct.pack("<HHHI", tag, year, award, winner) + tail


def placeholder_row(tag: int = 0xFFFF) -> bytes:
    """One 26-byte placeholder record: winner and club unset, trailing block zeroed."""
    return b"\x02" + _FLAGS + struct.pack("<H", tag) + b"\xff" * 8 + b"\x00" * 11


def test_head_row_decodes_every_field() -> None:
    tail = bytes([39, 46, 0, 100, 0, 50, 0, 10, 0, 6, 0])
    data = head_row(0x8B, 2031, 99, 328408, 716, tail)
    awards = decode_awards(data)
    (award,) = awards
    assert award.season_year == 2031
    assert award.award_id == 99
    assert award.tag == 0x8B
    assert award.winner_id == 328408
    assert award.club_uid == 716
    assert award.winner_age == 39
    assert award.tail == tuple(tail)


def test_club_winner_row_carries_no_club_field() -> None:
    # A 26-byte record whose winner is the club itself, seen on the club-history rows: its
    # trailing block runs an age with zeros around it, so the 30-byte read of it fails.
    tail = bytes([21, 0, 0, 0, 0, 25, 0, 0, 0, 0, 0])
    awards = decode_awards(head_row_without_club(0xFFFF, 1937, 4, 716, tail))
    (award,) = awards
    assert award.club_uid is None
    assert award.winner_id == 716
    assert award.season_year == 1937
    assert award.award_id == 4


def test_records_butt_against_each_other_in_file_order() -> None:
    first = head_row(0xFFFF, 2026, 144, 328408, 716, _TAIL)
    second = head_row_without_club(0xFFFF, 1937, 4, 716, bytes([21, 0, 0, 0, 0, 25, 0, 0, 0, 0, 0]))
    third = head_row(0, 2031, 99, 1234, 216, _TAIL)
    awards = decode_awards(first + second + third)
    assert [(award.season_year, award.award_id, award.winner_id, award.club_uid) for award in awards] == [
        (2026, 144, 328408, 716),
        (1937, 4, 716, None),
        (2031, 99, 1234, 216),
    ]


def test_headless_record_is_kept_out() -> None:
    # The monthly-award records carry no year/award head; keep them out rather than
    # misread them. The scan walks past one in a stream without losing alignment.
    headless = b"\x02" + _FLAGS + struct.pack("<H", 0x8B) + struct.pack(
        "<II", 328408, 716
    ) + bytes([39, 0, 46, 0, 0, 0, 0, 0, 0, 0, 0])
    next_row = head_row(0xFFFF, 2031, 99, 1234, 216, _TAIL)
    awards = decode_awards(headless + next_row)
    assert len(awards) == 1
    assert awards[0].season_year == 2031


def test_placeholder_records_are_walked_past() -> None:
    awards = decode_awards(placeholder_row() * 3)
    assert awards == ()


def test_unmatched_filler_between_records_does_not_break_alignment() -> None:
    gap = bytes([0x07, 0x00, 0xFF, 0x14, 0, 0]) + placeholder_row()
    row = head_row(0xFFFF, 2026, 144, 328408, 716, _TAIL)
    awards = decode_awards(gap + row + gap)
    assert len(awards) == 1


def test_row_outside_the_year_bounds_is_rejected() -> None:
    tail = bytes([45, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    # 1900 is the null-year sentinel these sections use elsewhere; years before 1850 and
    # past the 2050 in-game horizon are junk. The edge years both sides of the band read.
    assert all(decode_awards(head_row(0xFFFF, year, 99, 328408, 716, tail)) == () for year in (1849, 1900, 2051))
    assert len(decode_awards(head_row(0xFFFF, 1850, 99, 328408, 716, tail))) == 1
    assert len(decode_awards(head_row(0xFFFF, 2050, 99, 328408, 716, tail))) == 1


def test_award_id_above_the_instance_band_is_rejected() -> None:
    rows = b"".join(
        head_row(0xFFFF, 2031, award_id, 328408, 716, bytes([45, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]))
        for award_id in (4700, 4701)
    )
    awards = decode_awards(rows)
    assert [award.award_id for award in awards] == [4700]


def test_winner_or_club_at_the_unset_sentinel_is_rejected() -> None:
    unset_winner = b"\x02" + _FLAGS + struct.pack("<HHH", 0xFFFF, 2031, 99) + struct.pack(
        "<II", 0xFFFFFFFF, 716
    ) + bytes([45, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    assert decode_awards(unset_winner) == ()


def test_age_outside_human_range_is_rejected() -> None:
    row_head = b"\x02" + _FLAGS + struct.pack("<HHH", 0xFFFF, 2031, 99) + struct.pack(
        "<II", 328408, 716
    )
    for age in (10, 96):
        assert decode_awards(row_head + bytes([age, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])) == ()
    assert len(decode_awards(row_head + bytes([13, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]))) == 1


def test_large_flags_word_is_rejected() -> None:
    row = b"\x02" + struct.pack("<I", 0x4082) + struct.pack(
        "<HHH", 0xFFFF, 2031, 99
    ) + struct.pack("<II", 328408, 716) + bytes([45, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    assert decode_awards(row) == ()


def test_section_name_is_the_award_year_section() -> None:
    assert AWARD_SECTION == "award_year_hist_dt"