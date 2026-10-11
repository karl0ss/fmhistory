"""Tests for the player statistics-history decoder (`readers.player_stats_history`)."""

from __future__ import annotations

import struct
from dataclasses import fields
from typing import cast

import pytest

from fmsave import PlayerHistoryStats, SeasonStatsKind, field_status
from fmsave.readers.persons import PersonBlockDecoder
from fmsave.readers.player_stats_history import (
    DT_HEAD_BYTES,
    INDEX_TAG,
    LIST_NUMBER_BEFORE_BLOCK,
    PLAYER_STATS_HISTORY_DT_SECTION,
    ROW_BYTES,
    decode_player_rows,
    decode_stats_history_index,
    history_person_list_numbers,
    index_covers_dt,
    player_list_numbers,
    team_season_competitions,
)

_DT_TAG = b"\x03\x01tmc.\x06\x00"


def row(
    *,
    team_id: int = 603,
    competition: int = 7,
    season: int = 2036,
    kind: int = 1,
    rating_total: int = 2191,
    minutes: int = 2348,
    starts: int = 28,
    subs: int = 3,
    rated: int = 31,
    goals: int = 16,
    assists: int = 3,
    word48: int = 40,
    word82: int = 9,
    expected_goals: int = 1234,
    xg_prevented: int = -51,
    fee: int = 0xFFFF_FFFF,
    spell: int = 0,
) -> bytes:
    """One 152-byte history row with the head and a few statistic words set."""
    data = bytearray(ROW_BYTES)
    struct.pack_into("<IHIH", data, 1, team_id, competition, fee, season)
    struct.pack_into("<HH", data, 13, rating_total, minutes)
    data[24:29] = bytes([starts, subs, rated, goals, assists])
    data[30] = spell
    data[31] = kind
    struct.pack_into("<H", data, 48, word48)
    struct.pack_into("<H", data, 82, word82)
    struct.pack_into("<H", data, 104, expected_goals)
    struct.pack_into("<h", data, 126, xg_prevented)
    return bytes(data)


def dt_blob(*rows: bytes) -> bytes:
    return _DT_TAG + b"".join(rows)


def index_blob(
    lists: list[list[int]],
    free: tuple[int, ...] = (),
    *,
    empties: list[int] | None = None,
    trailer: tuple[int, int] = (ROW_BYTES, 6),
) -> bytes:
    """A pool index listing dt row numbers per player, values delta-encoded."""
    body = struct.pack("<I", len(free)) + b"".join(struct.pack("<I", n * ROW_BYTES) for n in free)
    body += struct.pack("<I", len(lists))
    for numbers in lists:
        values: list[int] = []
        previous = 0
        for number in numbers:
            value = number * ROW_BYTES - previous
            values.append(value & 0xFFFF_FFFF)
            previous = value
        body += struct.pack(f"<I{len(values)}I", len(values), *values)
    if empties is None:
        empties = [n for n, numbers in enumerate(lists) if not numbers]
    body += struct.pack(f"<I{len(empties)}I", len(empties), *empties)
    return INDEX_TAG + body + struct.pack("<IH", *trailer)


def test_section_name() -> None:
    assert PLAYER_STATS_HISTORY_DT_SECTION == "player_stats_hist_dt"


def test_index_lists_decode_delta_encoded_rows_in_stored_order() -> None:
    index = decode_stats_history_index(index_blob([[0, 3, 1], [], [2]], free=(4,)))
    assert index is not None
    assert index.list_count == 3
    assert index.free_count == 1
    assert list(index.rows_of(0)) == [DT_HEAD_BYTES + n * ROW_BYTES for n in (0, 3, 1)]
    assert list(index.rows_of(1)) == []
    assert list(index.rows_of(2)) == [DT_HEAD_BYTES + 2 * ROW_BYTES]
    assert index_covers_dt(index, DT_HEAD_BYTES + 5 * ROW_BYTES)
    assert not index_covers_dt(index, DT_HEAD_BYTES + 6 * ROW_BYTES)


@pytest.mark.parametrize(
    "blob",
    [
        index_blob([[0]], trailer=(509, 6)),
        index_blob([[0]], trailer=(ROW_BYTES, 2)),
        index_blob([[0], []], empties=[0]),
        index_blob([[0]])[:-6] + b"\x00" * 4 + index_blob([[0]])[-6:],
        b"\x03\x01tmc.\x04\x00" + index_blob([[0]])[8:],
    ],
)
def test_index_that_does_not_parse_exactly_is_none(blob: bytes) -> None:
    assert decode_stats_history_index(blob) is None


def test_rows_decode_head_and_statistics_for_an_outfield_player() -> None:
    dt = dt_blob(row(), row(season=2037, kind=2, team_id=0xFFFF_FFFF, competition=0xFFFF))
    index = decode_stats_history_index(index_blob([[1, 0]]))
    assert index is not None
    first, second = decode_player_rows(dt, index, 0, 493490, goalkeeper=False)
    assert (second.season_year, second.kind, second.team_id, second.competition_id) == (
        2036,
        SeasonStatsKind.LEAGUE,
        603,
        7,
    )
    assert (first.season_year, first.kind, first.team_id, first.competition_id) == (
        2037,
        SeasonStatsKind.CUP,
        None,
        None,
    )
    assert (first.list_position, first.record_index, second.record_index) == (0, 1, 0)
    assert (second.minutes, second.starts, second.substitute_appearances) == (2348, 28, 3)
    assert (second.rated_appearances, second.goals, second.assists) == (31, 16, 3)
    assert second.average_rating == pytest.approx(2191 / 31 / 10)
    assert second.expected_goals == pytest.approx(12.34)
    assert second.expected_goals_prevented == pytest.approx(-0.51)
    assert second.aerial_challenges_attempted == 40
    assert second.saves_held is None and second.saves_tipped is None
    assert second.player_reference == 493490 and second.history_index == 0
    assert second.player_uid is None and second.club_uid is None


def test_goalkeeper_rows_read_the_shared_words_as_saves() -> None:
    dt = dt_blob(row(kind=0, rated=0, rating_total=0))
    index = decode_stats_history_index(index_blob([[0]]))
    assert index is not None
    (keeper,) = decode_player_rows(dt, index, 0, 1, goalkeeper=True)
    assert keeper.kind is SeasonStatsKind.NON_COMPETITIVE
    assert keeper.average_rating is None
    assert (keeper.saves_held, keeper.saves_tipped) == (40, 9)
    assert keeper.aerial_challenges_attempted is None and keeper.clearances is None


def test_kind_code_outside_the_slot_order_has_no_kind() -> None:
    dt = dt_blob(row(kind=7))
    index = decode_stats_history_index(index_blob([[0]]))
    assert index is not None
    (unknown,) = decode_player_rows(dt, index, 0, 1, goalkeeper=False)
    assert unknown.kind_code == 7 and unknown.kind is None


def test_departure_fee_and_spell_code() -> None:
    dt = dt_blob(row(), row(fee=22_937_564), row(fee=0, spell=1), row(fee=0xFFFF_FFF6, spell=4))
    index = decode_stats_history_index(index_blob([[0, 1, 2, 3]]))
    assert index is not None
    rows = decode_player_rows(dt, index, 0, 1, goalkeeper=False)
    assert [r.departure_fee for r in rows] == [None, 22_937_564, 0, -10]
    assert [r.spell_code for r in rows] == [0, 0, 1, 4]


class _Blocks:
    """Stands in for a person decoder: a fixed block start per record window."""

    def __init__(self, starts: dict[int, int | None]) -> None:
        self.starts = starts

    def block_start(self, game_db: bytes, window_start: int, window_end: int) -> int | None:
        return self.starts[window_start]


def test_list_numbers_bind_by_the_u32_before_each_person_block() -> None:
    game_db = bytearray(400)
    # Records at 0, 100, 200, 300; blocks 60 bytes in (window starts at record + 10).
    numbers = {0: 5, 100: 0xFFFF_FFFF, 200: 9, 300: 2}
    for record, number in numbers.items():
        struct.pack_into("<I", game_db, record + 60 - LIST_NUMBER_BEFORE_BLOCK, number)
    decoder = _Blocks({record + 10: record + 60 for record in numbers})
    found = player_list_numbers(
        bytes(game_db),
        [300, 0, 100, 200],
        [30, 0, 10, 20],
        cast("PersonBlockDecoder", decoder),
        10,
        list_count=6,
    )
    # 0xffffffff (no list) and 9 (outside the 6 lists) are left out.
    assert found == {1: 5, 31: 2}


def test_a_list_number_two_players_claim_binds_neither() -> None:
    game_db = bytearray(200)
    for record in (0, 100):
        struct.pack_into("<I", game_db, record + 60 - LIST_NUMBER_BEFORE_BLOCK, 3)
    decoder = _Blocks({10: 60, 110: 160})
    found = player_list_numbers(
        bytes(game_db), [0, 100], [0, 1], cast("PersonBlockDecoder", decoder), 10, list_count=4
    )
    assert found == {}


def test_a_record_without_a_person_block_is_skipped() -> None:
    decoder = _Blocks({10: None})
    found = player_list_numbers(
        bytes(100), [0], [0], cast("PersonBlockDecoder", decoder), 10, list_count=4
    )
    assert found == {}


def test_history_people_bind_unclaimed_non_empty_lists_stored_once() -> None:
    index = decode_stats_history_index(index_blob([[0], [1], [], [2], [3], [4]]))
    assert index is not None
    candidates = [
        (11, 0),  # a current player owns list 0
        (12, 1),  # binds
        (13, 2),  # list 2 is empty
        (14, 3),  # list 3 is stored by two people: neither binds
        (15, 3),
        (16, 99),  # no such list
        (17, None),  # stub: no number
        (18, 4),  # binds
    ]
    assert history_person_list_numbers(candidates, index, {0}) == {12: 1, 18: 4}


def test_team_season_competitions_reads_every_row_and_drops_clashes() -> None:
    dt = dt_blob(
        row(team_id=603, competition=708, season=2024),
        row(team_id=603, competition=708, season=2024, kind=2),
        row(team_id=603, competition=150, season=2025),
        row(team_id=7, competition=10, season=2025),
        row(team_id=7, competition=11, season=2025),
        row(team_id=0xFFFF_FFFF, competition=10, season=2025),
        row(team_id=8, competition=0xFFFF, season=2025),
    )
    assert team_season_competitions(dt) == {(603, 2024): 708, (603, 2025): 150}


def test_every_field_is_unconfirmed() -> None:
    for field in fields(PlayerHistoryStats):
        assert field_status(PlayerHistoryStats, field.name) == "unconfirmed"
