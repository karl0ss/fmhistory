"""Tests for the transfer-man move-grid and wage-ledger decoders.

`decode_player_season_records` reads the `transfer_man` section's tail: a clear
region of 73-byte move rows followed by one zstd frame per older season. The
tests build synthetic section bytes — a header, rows and frame payloads — the
same way the ground-truth save lays them out.
"""

from __future__ import annotations

import struct
from datetime import date

import pytest

from fmsave._errors import CorruptSaveError
from fmsave.readers.transfer_history import (
    TRANSFER_MAN_SECTION,
    club_player_moves,
    decode_player_season_records,
    decode_wage_ledger_records,
    raise_when_ledger_unreadable,
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
    reference: int = 189608,
    value_a: int | None = 603,
    value_b: int | None = 706,
    value_c: int | None = 603,
    value_d: int | None = None,
    record_type: int = 1,
    tick: int = 11999,
    season_year: int = 2036,
    flags: int = 257,
    value_e: int | None = None,
    count: int = 0xFFFF,
    value_f: int | None = None,
    value_g: int | None = None,
) -> bytes:
    """One 73-byte move row: head word, person reference, team fields, tail.

    The defaults are the ground-truth Dumas row: reference 189608 moving from team
    706 to team 603 on 10 August 2036 (day word 11999: slot 23, day 223).
    """
    return _ROW.pack(
        bytes([0, variant_a, variant_b, 7]),
        reference,
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
    data = (
        _HEADER
        + row()
        + _STORY
        + row(reference=280836, value_a=None, value_b=603, value_c=603, record_type=4)
    )
    records = decode_player_season_records(data)
    assert len(records) == 2
    first, second = records
    assert first.player_reference == 189608
    assert (first.value_a, first.value_b, first.value_c) == (603, 706, 603)
    assert (first.record_type, first.season_year, first.flags) == (1, 2036, 257)
    assert second.player_reference == 280836
    assert (second.value_a, second.value_b, second.value_c) == (None, 603, 603)


def test_row_date_decodes_the_day_word_and_year() -> None:
    # The day word packs the day of the year in its low 9 bits; the bits above
    # are an intra-day slot the date ignores.
    first, second, null = decode_player_season_records(
        _HEADER + row() + row(tick=0x5CDD, season_year=2037) + row(season_year=1900, tick=0)
    )
    assert (first.tick, first.date) == (11999, date(2036, 8, 10))
    assert second.date == date(2037, 8, 9)
    assert null.date is None


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
    # Row type 33 carries a wildcard head id naming no one, money in value_b.
    data = _HEADER + row(
        reference=0xFFFF_FFFF,
        value_a=None,
        value_b=35459,
        value_c=None,
        record_type=33,
    )
    (kept,) = decode_player_season_records(data)
    assert (kept.player_reference, kept.value_b, kept.record_type) == (0xFFFF_FFFF, 35459, 33)


def test_junk_sentinel_year_rows_are_dropped() -> None:
    junk = row(
        variant_a=0,
        variant_b=0,
        reference=11,
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
    frame_a = _compress(row(season_year=2036) + row(reference=280836, season_year=2036))
    frame_b = _compress(row(season_year=2035, reference=458697) + b"\x00" * 11)
    # The tail sits after the last frame, one trailing byte on this layout.
    data = _HEADER + clear + frame_a + frame_b + b"\x00"
    records = decode_player_season_records(data)
    assert [(r.player_reference, r.season_year) for r in records] == [
        (189608, 2037),
        (189608, 2036),
        (280836, 2036),
        (458697, 2035),
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


# Wage-ledger records: `11 00` tag, then the 26-byte payload.
_WAGE = struct.Struct("<IBIIIIBI")

# A ground-truth pair of records carrying the same money for two players.
_REGISTER_MONEY = (20680, 62040)


def wage_record(
    *,
    reference: int = 183329,
    kind: int = 4,
    value_a: int = _REGISTER_MONEY[0],
    value_b: int = _REGISTER_MONEY[1],
    flags: int = 0,
    tail_flags: int = 0,
) -> bytes:
    """One 28-byte wage-ledger record."""
    return b"\x11\x00" + _WAGE.pack(reference, kind, value_a, 0, value_b, 0, flags, tail_flags)


def test_decodes_wage_records_in_file_order() -> None:
    data = (
        _HEADER
        + wage_record()
        + wage_record(reference=649302)
        + wage_record(
            reference=280836, kind=7, value_a=18700, value_b=18700, flags=2, tail_flags=2048
        )
    )
    records = decode_wage_ledger_records(data)
    assert [(r.player_reference, r.kind) for r in records] == [
        (183329, 4),
        (649302, 4),
        (280836, 7),
    ]
    assert [r.value_a for r in records] == [20680, 20680, 18700]
    assert [r.flags for r in records] == [0, 0, 2]
    assert [r.tail_flags for r in records] == [0, 0, 2048]


def test_wage_records_embedded_between_other_bytes_still_read() -> None:
    # The clear zone interleaves negotiation records; a wage record's tag sits at
    # its own position, and the scan does not depend on a store-wide grid.
    story = bytes(range(0, 16)) * 4
    data = _HEADER + story + wage_record() + story
    [record] = decode_wage_ledger_records(data)
    assert (record.player_reference, record.value_a, record.value_b) == (183329, 20680, 62040)


def test_wage_records_after_the_first_zstd_frame_are_not_read() -> None:
    frame = _compress(wage_record())
    data = _HEADER + wage_record() + frame
    [record] = decode_wage_ledger_records(data)
    assert record.player_reference == 183329


def test_wage_record_bytes_that_miss_the_layout_are_not_rows() -> None:
    bad_pad = bytearray(wage_record())
    bad_pad[13] = 1  # the first money field's zero pad
    assert decode_wage_ledger_records(_HEADER + bytes(bad_pad)) == ()

    bad_kind = bytearray(wage_record())
    bad_kind[6] = 32  # kind byte over the bound
    assert decode_wage_ledger_records(_HEADER + bytes(bad_kind)) == ()

    big_money = wage_record(value_a=1_000_001)
    assert decode_wage_ledger_records(_HEADER + big_money) == ()


def test_wage_record_tagged_family_is_dropped() -> None:
    # One tagged-record family interleaves in the same clear zone whose first
    # money u32 reads with the bytes `01 02` in the middle — a different grammar.
    tagged = b"\x11\x00" + _WAGE.pack(0x02010C24, 0x13, 0x00137813, 0, 50, 0, 0, 0)
    assert tagged[:4] == b"\x11\x00\x24\x0c"
    data = _HEADER + tagged + wage_record()
    [record] = decode_wage_ledger_records(data)
    assert record.value_a == 20680


def test_wage_ledger_gates() -> None:
    data = _HEADER + wage_record()
    assert decode_wage_ledger_records(data)
    raise_when_ledger_unreadable(1, data)
    with pytest.raises(CorruptSaveError):
        raise_when_ledger_unreadable(0, data)


# Club join: team 603 is the club's first team, 91751 its second; 706 another club's.
_CLUB_BY_TEAM = {603: 716, 91751: 716, 706: 828, 715: 840}
_CLUB_NAMES = {716: "St. Albans City", 828: "AS Saint-Etienne", 840: "En Avant Guingamp"}
_PLAYERS = {189608: 2000205315, 280836: 2002095850}
_NAMES = {2000205315: "Corentin Dumas", 2002095850: "Ben Young-Thomas"}


def _moves(data: bytes) -> tuple:
    return club_player_moves(
        decode_player_season_records(data), 716, _CLUB_BY_TEAM, _CLUB_NAMES, _PLAYERS, _NAMES
    )


def test_club_moves_join_players_and_clubs() -> None:
    data = (
        _HEADER
        + row()
        + row(
            reference=280836,
            value_a=20360,
            value_b=603,
            value_c=20360,
            tick=0x5CDD,
            season_year=2037,
        )
    )
    bought, sold = _moves(data)
    assert (bought.direction, bought.player_uid, bought.player_name) == (
        "in",
        2000205315,
        "Corentin Dumas",
    )
    assert (bought.from_club_name, bought.to_club_name, bought.date) == (
        "AS Saint-Etienne",
        "St. Albans City",
        date(2036, 8, 10),
    )
    assert (sold.direction, sold.player_name, sold.to_team_id, sold.to_club_uid) == (
        "out",
        "Ben Young-Thomas",
        20360,
        None,
    )


def test_club_moves_skip_other_clubs_and_sort_by_date() -> None:
    elsewhere = row(reference=458697, value_a=715, value_b=706, value_c=715)
    later = row(reference=458697, value_a=603, value_b=715, tick=200, season_year=2037)
    internal = row(reference=7, value_a=91751, value_b=603, tick=10, season_year=2030)
    released = row(reference=8, value_a=None, value_b=603, record_type=4, season_year=1900)
    moves = _moves(_HEADER + later + elsewhere + row() + internal + released)
    assert [(m.player_reference, m.direction) for m in moves] == [
        (8, "out"),
        (7, "internal"),
        (189608, "in"),
        (458697, "in"),
    ]
    unresolved = moves[0]
    assert (unresolved.player_uid, unresolved.player_name, unresolved.to_club_uid) == (
        None,
        None,
        None,
    )
