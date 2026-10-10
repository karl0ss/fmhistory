"""Tests for the cup-history decoder (`decode_cup_entries` / `Save.career_cup_entries`)."""

from __future__ import annotations

import struct
from dataclasses import replace

import pytest

from fmsave._errors import CorruptSaveError
from fmsave.models.career_history import CupEntry, Honour
from fmsave.readers.career_history import (
    CUP_HISTORY_LS_SECTION,
    CUP_HISTORY_SECTION,
    decode_cup_entries,
    resolve_cup_history_indexes,
)

_HEAD = bytes.fromhex("03 01 74 6d 63 2e 01 00")
_UNSET = 0xFFFF_FFFF


def row(
    stage: int = 4491,
    start: int = 2024,
    end: int = 2025,
    result: int = 2,
    method: int = 1,
    word: int = 0xFFFF,
    position: int = 0xFF,
    opponent: int = 496,
) -> bytes:
    """One 18-byte row: [stage][start][end][result][method][word][position][0][opponent]."""
    return struct.pack("<IHHBBHBBI", stage, start, end, result, method, word, position, 0, opponent)


def ls_blob(*lists: list[int]) -> bytes:
    """A cup ls index over row numbers, delta-encoded like the league-history index."""
    body = b""
    for rows in lists:
        offsets = [18 * number for number in rows]
        values: list[int] = []
        previous = 0
        for offset in offsets:
            value = (offset - previous) & 0xFFFF_FFFF
            values.append(value)
            previous = value
        body += struct.pack(f"<I{len(values)}I", len(values), *values)
    return (
        b"\x03\x01tad.\x04\x00"
        + struct.pack("<II", 0, len(lists))
        + body
        + struct.pack("<IIH", 0, 18, 1)
    )


def dt(*rows: bytes) -> bytes:
    """A dt section of rows, padded to the ten rows the layout check needs."""
    padding = [row(stage=1, start=2030, end=2031)] * max(0, 10 - len(rows))
    return _HEAD + b"".join(rows) + b"".join(padding)


def test_sections_are_the_dt_and_ls_pair() -> None:
    assert CUP_HISTORY_SECTION == "tc_cup_history_dt"
    assert CUP_HISTORY_LS_SECTION == "tc_cup_history_ls"


def test_row_decodes_every_field_from_the_section_head_on() -> None:
    entry = decode_cup_entries(dt(row(4491, 2024, 2025, 3, 1, opponent=496)))[0]
    assert entry == CupEntry(
        stage_id=4491,
        start_year=2024,
        end_year=2025,
        result=3,
        method=1,
        unknown_word=None,
        position=None,
        opponent_team_id=496,
        history_index=None,
        competition_id=None,
    )


def test_league_format_row_keeps_position_and_no_opponent() -> None:
    entry = decode_cup_entries(
        dt(row(6988, 2024, 2025, 0, 0xFF, word=637, position=0, opponent=_UNSET))
    )[0]
    assert entry.position == 0
    assert entry.opponent_team_id is None
    assert entry.unknown_word == 637
    assert entry.method == 0xFF


def test_ls_lists_stamp_history_index() -> None:
    rows = [row(stage=number) for number in range(10)]
    entries = decode_cup_entries(dt(*rows), ls_blob([0, 3, 9], [1, 2, 4, 5, 6, 7, 8]))
    assert [entry.history_index for entry in entries] == [0, 1, 1, 0, 1, 1, 1, 1, 1, 0]


def test_unparseable_ls_leaves_indexes_unset() -> None:
    entries = decode_cup_entries(dt(row()), b"junk")
    assert {entry.history_index for entry in entries} == {None}


def test_section_off_the_row_grid_is_refused() -> None:
    with pytest.raises(CorruptSaveError):
        decode_cup_entries(dt(row()) + b"\x00")


def test_section_whose_rows_carry_no_seasons_is_refused() -> None:
    with pytest.raises(CorruptSaveError):
        decode_cup_entries(_HEAD + row(start=0, end=0) * 20)


def _entry(index: int, result: int, end: int, competition: int) -> CupEntry:
    entry = decode_cup_entries(dt(row(result=result, start=end - 1, end=end)))[0]
    return replace(entry, history_index=index, competition_id=competition)


def test_cup_honour_pins_the_winning_rows_list() -> None:
    entries = [
        _entry(7, 3, 2025, 151),
        _entry(8, 2, 2025, 151),
        _entry(9, 3, 2025, 664),
    ]
    honours = [Honour(club_uid=716, competition_id=109202, season=2025, count=1)]
    assert resolve_cup_history_indexes(entries, honours, {109202: 151}) == {716: 7}


def test_unmapped_or_unmatched_honour_pins_nothing() -> None:
    entries = [_entry(7, 3, 2025, 151)]
    assert resolve_cup_history_indexes(entries, [Honour(716, 999, 2025, 1)], {109202: 151}) == {}
    assert resolve_cup_history_indexes(entries, [Honour(716, 109202, 2026, 1)], {109202: 151}) == {}


def test_conflicting_claims_are_dropped() -> None:
    entries = [_entry(7, 3, 2025, 151), _entry(8, 3, 2026, 151)]
    # One club claiming two lists, and one list claimed by two clubs, both stay unresolved.
    two_lists = [Honour(716, 109202, 2025, 1), Honour(716, 109202, 2026, 2)]
    assert resolve_cup_history_indexes(entries, two_lists, {109202: 151}) == {}
    shared = [Honour(716, 109202, 2025, 1), Honour(717, 109202, 2025, 1)]
    assert resolve_cup_history_indexes(entries, shared, {109202: 151}) == {}
