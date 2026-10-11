"""Tests for the manager-history reader (`tc_manager_history_dt` / `_ls`)."""

from __future__ import annotations

import dataclasses
import struct
from datetime import date

import pytest

from fmsave import ManagerHistorySpell, field_status
from fmsave._errors import CorruptSaveError
from fmsave.models.career_history import (
    ManagerCareerRecord,
    ManagerCurrentJob,
    ManagerSpellWindow,
)
from fmsave.readers.manager_history import (
    DT_HEAD,
    ROW_BYTES,
    current_job_spells,
    decode_manager_history,
    decode_manager_history_lists,
    manager_spells,
    resolve_manager_history_teams,
)

_NO_DATE = struct.pack("<HH", 0, 2023)


def packed_date(day: date, slot: int = 0) -> bytes:
    """The 4-byte game date: [u16 day of year | slot << 9][u16 year]."""
    return struct.pack("<HH", day.timetuple().tm_yday | (slot << 9), day.year)


def row(
    reference: int,
    start: date | None,
    end: date,
    wdl: tuple[int, int, int] = (0, 0, 0),
    kind: int = 2,
    counters: bytes = b"\x00\x00\x00\x00",
) -> bytes:
    """A 31-byte ended-spell row."""
    data = (
        struct.pack("<I", reference)
        + (_NO_DATE if start is None else packed_date(start, slot=60))
        + packed_date(end, slot=27)
        + struct.pack("<II", 0xFFFFFFFF, 0x1F8)
        + struct.pack("<HHHB", *wdl, kind)
        + counters
    )
    assert len(data) == ROW_BYTES
    return data


def dt(*rows: bytes) -> bytes:
    return b"\x03\x01tmc.\x02\x00" + b"".join(rows)


def ls(*lists: list[int], row_bytes: int = ROW_BYTES) -> bytes:
    """The index: tag, no free entries, delta-encoded lists of row numbers, trailer."""
    body = b"\x03\x01tad.\x04\x00" + struct.pack("<II", 0, len(lists))
    for numbers in lists:
        offsets = [number * ROW_BYTES for number in numbers]
        values: list[int] = []
        previous = 0
        for offset in offsets:
            value = (offset - previous) & 0xFFFFFFFF
            values.append(value)
            previous = value
        body += struct.pack(f"<I{len(values)}I", len(values), *values)
    return body + struct.pack("<IIH", 0, row_bytes, 2)


def career(
    reference: int,
    *,
    longest: ManagerSpellWindow | None = None,
    shortest: ManagerSpellWindow | None = None,
    job: ManagerCurrentJob | None = None,
) -> ManagerCareerRecord:
    return ManagerCareerRecord(
        reference=reference,
        highest_fee_paid=None,
        highest_fee_received=None,
        longest_club_spell=longest,
        shortest_club_spell=shortest,
        longest_national_spell=None,
        shortest_national_spell=None,
        money_spent=0,
        money_received=0,
        agent_fees=0,
        goals_for=0,
        goals_against=0,
        games=0,
        wins=0,
        draws=0,
        losses=0,
        cups=0,
        league_titles=0,
        awards=0,
        players_bought=0,
        players_sold=0,
        players_released=0,
        club_jobs=1,
        national_jobs=0,
        current_job=job,
        unknown={},
    )


def current_job(team: int, start: date, games: int, wins: int, losses: int) -> ManagerCurrentJob:
    return ManagerCurrentJob(
        team_id=team,
        start_date=start,
        highest_fee_paid=None,
        highest_fee_received=None,
        money_spent=0,
        money_received=0,
        goals_for=0,
        goals_against=0,
        games=games,
        wins=wins,
        draws=games - wins - losses,
        losses=losses,
        cups=0,
        league_titles=0,
        awards=0,
        players_bought=0,
        players_sold=0,
        players_released=0,
    )


# Two teams: list 0 holds rows 0 and 2 (manager 15164, then caretaker 15195), list 1
# holds row 1 (manager 7, whose start predates the history).
_ROWS = (
    row(15164, date(2023, 10, 27), date(2025, 7, 11), (33, 17, 26), counters=b"\x01\x00\x01\x00"),
    row(7, None, date(2023, 7, 5), (4, 6, 15)),
    row(15195, date(2025, 7, 11), date(2025, 7, 30), (0, 2, 2), kind=10),
)
_DT = dt(*_ROWS)
_LS = ls([0, 2], [1])


def test_lists_decode_delta_encoded_offsets() -> None:
    assert decode_manager_history_lists(len(_DT), _LS) == (
        (DT_HEAD, DT_HEAD + 2 * ROW_BYTES),
        (DT_HEAD + ROW_BYTES,),
    )


def test_rows_decode_reference_dates_and_results() -> None:
    spells = decode_manager_history(_DT, _LS)

    first, second, third = spells
    assert first.reference == 15164
    assert (first.start_date, first.end_date) == (date(2023, 10, 27), date(2025, 7, 11))
    assert (first.games, first.wins, first.draws, first.losses) == (76, 33, 17, 26)
    assert first.history_index == 0
    assert first.team_id is None
    assert first.kind == 2
    assert first.unknown["word_12"] == 0xFFFFFFFF
    assert first.unknown["word_16"] == 0x1F8
    assert (first.unknown["byte_27"], first.unknown["byte_29"]) == (1, 1)
    assert set(first.unknown) == set(ManagerHistorySpell.UNKNOWN_KEYS)
    assert second.start_date is None
    assert second.history_index == 1
    assert (third.kind, third.history_index) == (10, 0)


def test_window_pins_list_to_team() -> None:
    spells = decode_manager_history(_DT, _LS)
    records = [
        career(15164, longest=ManagerSpellWindow(603, date(2023, 10, 27), date(2025, 7, 11))),
        # A window with no matching row names nothing.
        career(15195, longest=ManagerSpellWindow(999, date(2025, 7, 1), date(2025, 7, 30))),
    ]

    assert resolve_manager_history_teams(spells, records) == {0: 603}


def test_conflicting_windows_leave_list_unnamed() -> None:
    spells = decode_manager_history(_DT, _LS)
    records = [
        career(
            15164,
            longest=ManagerSpellWindow(603, date(2023, 10, 27), date(2025, 7, 11)),
            shortest=ManagerSpellWindow(604, date(2023, 10, 27), date(2025, 7, 11)),
        ),
    ]

    assert resolve_manager_history_teams(spells, records) == {}


def test_team_claimed_by_two_lists_is_dropped() -> None:
    data = dt(_ROWS[0], row(7, date(2022, 7, 1), date(2023, 7, 5)), _ROWS[2])
    spells = decode_manager_history(data, _LS)
    records = [
        career(15164, longest=ManagerSpellWindow(603, date(2023, 10, 27), date(2025, 7, 11))),
        career(7, longest=ManagerSpellWindow(603, date(2022, 7, 1), date(2023, 7, 5))),
    ]

    assert resolve_manager_history_teams(spells, records) == {}


def test_manager_spells_name_teams_and_add_current_jobs() -> None:
    spells = decode_manager_history(_DT, _LS)
    records = [
        career(
            15164,
            longest=ManagerSpellWindow(603, date(2023, 10, 27), date(2025, 7, 11)),
            job=current_job(716, date(2025, 8, 1), 20, 9, 6),
        ),
        career(328408, job=current_job(603, date(2023, 7, 18), 741, 391, 219)),
    ]

    table = manager_spells(spells, records)

    assert [(spell.reference, spell.team_id, spell.end_date) for spell in table] == [
        (7, None, date(2023, 7, 5)),
        (15164, 603, date(2025, 7, 11)),
        (15164, 716, None),
        (15195, 603, date(2025, 7, 30)),
        (328408, 603, None),
    ]
    karl = table[-1]
    assert (karl.start_date, karl.games, karl.wins, karl.draws, karl.losses) == (
        date(2023, 7, 18),
        741,
        391,
        131,
        219,
    )
    assert (karl.history_index, karl.kind, dict(karl.unknown)) == (None, None, {})


def test_unemployed_manager_has_no_open_spell() -> None:
    assert current_job_spells([career(7)]) == ()


def test_dt_with_partial_row_raises() -> None:
    with pytest.raises(CorruptSaveError, match="31-byte rows"):
        decode_manager_history(_DT[:-1], _LS)


def test_index_missing_a_row_raises() -> None:
    with pytest.raises(CorruptSaveError, match="lists 2 of 3 rows"):
        decode_manager_history(_DT, ls([0], [1]))


def test_index_listing_a_row_twice_raises() -> None:
    with pytest.raises(CorruptSaveError, match="twice"):
        decode_manager_history(_DT, ls([0, 2], [1, 2]))


def test_index_pointing_past_the_rows_raises() -> None:
    with pytest.raises(CorruptSaveError, match="not a row"):
        decode_manager_history(_DT, ls([0, 2], [1, 3]))


def test_index_with_other_row_size_raises() -> None:
    with pytest.raises(CorruptSaveError, match="names 30-byte rows"):
        decode_manager_history(_DT, ls([0, 2], [1], row_bytes=30))


def test_index_with_trailing_bytes_raises() -> None:
    data = _LS[:-10] + b"\x00\x00\x00\x00" + _LS[-10:]
    with pytest.raises(CorruptSaveError, match="bytes after"):
        decode_manager_history(_DT, data)


def test_fields_are_registered_unconfirmed() -> None:
    for name in (field.name for field in dataclasses.fields(ManagerHistorySpell)):
        assert field_status(ManagerHistorySpell, name) == "unconfirmed"
