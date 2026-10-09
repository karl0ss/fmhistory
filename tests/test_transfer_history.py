"""Tests for the transfer-man season-record decoder.

`decode_player_season_records` reads the `transfer_man` section's tail: a clear
region of 73-byte season rows followed by one zstd frame per older season. The
tests build synthetic section bytes — a header, rows and frame payloads — the
same way the ground-truth save lays them out.
"""

from __future__ import annotations

import struct

import pytest

from fmsave._errors import CorruptSaveError
from fmsave.readers.transfer_history import (
    TRANSFER_MAN_SECTION,
    decode_player_season_records,
    raise_when_unreadable,
    _ZSTD_MAGIC,
)

try:  # the save container's own import guard, for building synthetic frames
    from compression import zstd
except ImportError:  # python < 3.14
    from backports import zstd

# The section header is 12 bytes: `03 01 'tad.' <u16 version> <u32 byte count>`.
_HEADER = struct.pack("<BB4sHI", 3, 1, b"tad.", 35, 0)

_ROW = struct.Struct("<4sIBIBIBI8sIBHHHIIII15s")
assert _ROW.size == 73

_UNSET = 0xFFFF_FFFF


def row(
    *,
    variant_a: int = 1,
    variant_b: int = 1,
    club: int = 716,
    slot: int = 7,
    value_a: int | None = 23972,
    value_b: int | None = None,
    value_c: int | None = 23972,
    value_d: int | None = None,
    record_type: int = 4,
    tick: int = 12291,
    season_year: int = 2036,
    flags: int = 257,
    value_e: int | None = None,
    count: int = 0xFFFF,
    value_f: int | None = None,
    value_g: int | None = None,
) -> bytes:
    """One 73-byte season row: head word, (club, slot) id, money fields, tail."""
    return _ROW.pack(
        bytes([0, variant_a, variant_b, 7]),
        club << 8 | slot,
        0,
        _UNSET if value_a is None else value_a,
        0,
        _UNSET if value_b is None else value_b,
        0,
        _UNSET if value_c is None else value_c,
        b"\x00" * 8,
        _UNSET if value_d is None else value_d,
        record_type,
        tick,
        season_year,
        flags,
        _UNSET if value_e is None else value_e,
        count,
        _UNSET if value_f is None else value_f,
        _UNSET if value_g is None else value_g,
        b"\x00\r" * 7 + b"\x00",
    )


# Story text between row runs: plain ASCII carries neither the head word's nulls
# nor its 0x07, so it never reads as a row.
_STORY = b"Carlos Campos Orlando City 2023 Superdraft 1st round"


def test_section_name_constant() -> None:
    assert TRANSFER_MAN_SECTION == "transfer_man"


def test_decodes_rows_across_a_story_chunk() -> None:
    data = _HEADER + row() + _STORY + row(club=1512, slot=3, value_a=None, value_b=32604, value_c=32604)
    records = decode_player_season_records(data)
    assert len(records) == 2
    first, second = records
    assert (first.club_uid, first.slot) == (716, 7)
    assert (first.value_a, first.value_b, first.value_c) == (23972, None, 23972)
    assert (first.record_type, first.season_year, first.flags) == (4, 2036, 257)
    assert (second.club_uid, second.slot) == (1512, 3)
    assert (second.value_a, second.value_b, second.value_c) == (None, 32604, 32604)


def test_unset_money_fields_read_as_none() -> None:
    data = _HEADER + row(value_e=486400, value_f=None, value_g=None)
    (first,) = decode_player_season_records(data)
    assert first.value_e == 486400
    assert (first.value_d, first.value_f, first.value_g) == (None, None, None)
    assert first.count == 0xFFFF


def test_head_variants_are_kept() -> None:
    data = _HEADER + row(variant_a=0, variant_b=1) + row(variant_a=1, variant_b=0)
    variants = [(r.variant_a, r.variant_b) for r in decode_player_season_records(data)]
    assert variants == [(0, 1), (1, 0)]


def test_row_bytes_that_miss_the_layout_are_not_rows() -> None:
    # A byte flip breaks the head word and the separators' nulls in turn:
    # each broken candidate must be skipped, not misread.
    good = row()
    bad_head = bytearray(good)
    bad_head[0] = 1  # head word: first byte no longer the 00 anchor
    assert decode_player_season_records(_HEADER + bytes(bad_head)) == ()

    bad_sep = bytearray(good)
    bad_sep[8] = 1  # separator null no longer zero
    assert decode_player_season_records(_HEADER + bytes(bad_sep)) == ()


def test_wildcard_head_id_rows_are_kept() -> None:
    # Row type 33 carries a wildcard head id: no club, money in value_b.
    data = _HEADER + row(
        club=0xFF_FF_FF,
        slot=0xFF,
        value_a=None,
        value_b=35459,
        value_c=None,
        record_type=33,
    )
    (kept,) = decode_player_season_records(data)
    assert (kept.club_uid, kept.slot, kept.value_b, kept.record_type) == (0xFF_FF_FF, 0xFF, 35459, 33)


def test_junk_sentinel_year_rows_are_dropped() -> None:
    junk = row(
        variant_a=0,
        variant_b=0,
        club=0,
        slot=11,
        value_a=26411008,
        value_b=318328064,
        value_c=4294967055,
        record_type=1,
        tick=65280,
        season_year=0xFFFF,
        flags=511,
        count=133599287,
    )
    data = _HEADER + junk + row()
    records = decode_player_season_records(data)
    [kept] = records
    assert kept.season_year == 2036


def test_null_year_rows_are_kept() -> None:
    data = _HEADER + row(season_year=1900)
    (kept,) = decode_player_season_records(data)
    assert kept.season_year == 1900


def test_year_out_of_bounds_is_dropped() -> None:
    for year in (2004, 2051, 0):
        assert decode_player_season_records(_HEADER + row(season_year=year)) == ()


def _compress(payload: bytes) -> bytes:
    return zstd.compress(payload)


def test_frames_decode_in_order_after_the_clear_region() -> None:
    clear = row(season_year=2037)
    frame_a = _compress(row(season_year=2036) + row(club=1512, slot=3, season_year=2036))
    frame_b = _compress(row(season_year=2035, club=1773) + b"\x00" * 11)
    # The tail sits after the last frame, one trailing byte on this layout.
    data = _HEADER + clear + frame_a + frame_b + b"\x00"
    records = decode_player_season_records(data)
    assert [(r.club_uid, r.slot, r.season_year) for r in records] == [
        (716, 7, 2037),
        (716, 7, 2036),
        (1512, 3, 2036),
        (1773, 7, 2035),
    ]


def test_a_false_magic_inside_a_frame_is_skipped() -> None:
    # A 4-byte zstd magic inside one frame's compressed bytes would end the
    # framing scan's segment early, so the scan retries the segment extended
    # over the false magic. The frame here is stored raw (level 0), so its
    # bytes carry the literal magic of a row-identifying word.
    false_magic_row = row(record_type=1)
    false_magic_row = false_magic_row[:20] + _ZSTD_MAGIC + false_magic_row[24:]
    assert _ZSTD_MAGIC in false_magic_row[5:]
    frame = zstd.compress(false_magic_row, level=0)
    frame_b = _compress(row(season_year=2035))
    clear = row()
    data = _HEADER + clear + frame + frame_b + b"\x00"
    records = decode_player_season_records(data)
    seasons = [r.season_year for r in records]
    assert seasons == [2036, 2036, 2035]


def test_a_frame_that_will_not_decompress_is_skipped() -> None:
    data = _HEADER + row() + _compress(row(season_year=2036)) + b"junk frame " * 4
    records = decode_player_season_records(data)
    [kept] = records
    assert kept.season_year == 2036


def test_no_rows_raises() -> None:
    data = _HEADER + _STORY
    assert decode_player_season_records(data) == ()
    with pytest.raises(CorruptSaveError):
        raise_when_unreadable(0, data)


def test_rows_raise_nothing() -> None:
    raise_when_unreadable(1, _HEADER + row())