"""Tests for the manager career-statistics reader (`person_record_manager`)."""

from __future__ import annotations

import dataclasses
import struct
from datetime import date

import pytest

from fmsave import field_status
from fmsave._errors import CorruptSaveError
from fmsave.models.career_history import (
    ManagerCareerRecord,
    ManagerCurrentJob,
    ManagerFee,
    ManagerSpellWindow,
)
from fmsave.readers.manager_career import (
    RECORD_BYTES,
    TRAILER,
    decode_manager_career_record,
    decode_manager_career_records,
    locate_manager_career_records,
)

_UNSET = 0xFFFFFFFF
_NULL_DATE = struct.pack("<HH", 1, 1900)


def packed_date(day: date) -> bytes:
    """The 4-byte game date: [u16 day of year (low 9 bits)][u16 year]."""
    return struct.pack("<HH", day.timetuple().tm_yday, day.year)


def career_fee(player: int, day: date, fee: int, from_team: int, to_team: int) -> bytes:
    """Career-block fee: [player][date][fee][u16][from][u8][to] (23 bytes)."""
    return (
        struct.pack("<I", player)
        + packed_date(day)
        + struct.pack("<IHIBI", fee, 0, from_team, 0, to_team)
    )


def job_fee(player: int, day: date, fee: int, from_team: int, to_team: int) -> bytes:
    """Current-job fee: [from][u8][to][player][date][fee] (21 bytes)."""
    return (
        struct.pack("<IBII", from_team, 0, to_team, player)
        + packed_date(day)
        + struct.pack("<I", fee)
    )


def spell(team: int, start: date | None, end: date | None) -> bytes:
    """A spell slot: [u8][u32 team][date start][date end] (13 bytes)."""
    return (
        b"\x00"
        + struct.pack("<I", team)
        + (_NULL_DATE if start is None else packed_date(start))
        + (_NULL_DATE if end is None else packed_date(end))
    )


def unset_spell() -> bytes:
    return b"\x00" + struct.pack("<I", _UNSET) + _NULL_DATE + _NULL_DATE


def record(reference: int, *, employed: bool = True) -> bytes:
    """A 367-byte career record with the ground-truth manager's numbers."""
    data = bytearray(RECORD_BYTES)
    struct.pack_into("<IIB", data, 0, reference, reference, 1)
    data[9:32] = career_fee(189608, date(2036, 8, 10), 22_937_564, 706, 603)
    data[32:55] = career_fee(280836, date(2037, 8, 9), 32_347_260, 603, 20360)
    data[55:68] = spell(603, date(2023, 7, 18), date(2037, 12, 4))
    data[68:81] = unset_spell()
    data[81:94] = unset_spell()
    data[94:107] = unset_spell()
    struct.pack_into("<QQQII", data, 107, 101_492_665, 97_733_168, 2_406_906, 1589, 1059)
    struct.pack_into("<HHH", data, 147, 1, 3, 5)
    struct.pack_into("<HHH", data, 163, 741, 391, 219)
    struct.pack_into("<H", data, 171, 21)
    struct.pack_into("<HHHHHH", data, 193, 19, 13, 5, 127, 39, 50)
    data[209] = 1
    data[210] = 0
    if employed:
        data[215:236] = job_fee(189608, date(2036, 8, 10), 22_937_564, 706, 603)
        data[238:259] = job_fee(280836, date(2037, 8, 9), 32_347_260, 603, 20360)
        data[260:264] = packed_date(date(2023, 7, 18))
        data[264:268] = packed_date(date(2037, 12, 4))
        struct.pack_into("<I", data, 269, 603)
    else:
        struct.pack_into("<IBII", data, 215, _UNSET, 0, _UNSET, _UNSET)
        struct.pack_into("<IBII", data, 238, _UNSET, 0, _UNSET, _UNSET)
        data[260:264] = _NULL_DATE
        struct.pack_into("<I", data, 269, _UNSET)
    struct.pack_into("<QQII", data, 286, 101_492_665, 97_733_168, 1589, 1059)
    struct.pack_into("<HHHHHHH", data, 320, 1, 3, 741, 391, 219, 19, 127)
    struct.pack_into("<HHH", data, 336, 39, 50, 5)
    return bytes(data)


def section(*records: bytes) -> bytes:
    """A section: head, an event-log stand-in, the records, the trailer."""
    head = b"\x03\x01tad.\x1e\x00" + b"\x15\xff\xff\xff\xff\xff\xff" * 3 + b"\x07\x00\x00\x00"
    return head + b"".join(records) + TRAILER


def test_record_decodes_the_managerial_stats_screen() -> None:
    career = decode_manager_career_record(record(328408))

    assert career.reference == 328408
    assert (career.games, career.wins, career.draws, career.losses) == (741, 391, 131, 219)
    assert (career.goals_for, career.goals_against) == (1589, 1059)
    assert (career.cups, career.league_titles, career.awards) == (1, 3, 19)
    assert (career.players_bought, career.players_sold, career.players_released) == (127, 39, 50)
    assert (career.money_spent, career.money_received, career.agent_fees) == (
        101_492_665,
        97_733_168,
        2_406_906,
    )
    assert (career.club_jobs, career.national_jobs) == (1, 0)
    assert career.highest_fee_paid == ManagerFee(189608, date(2036, 8, 10), 22_937_564, 706, 603)
    assert career.highest_fee_received == ManagerFee(
        280836, date(2037, 8, 9), 32_347_260, 603, 20360
    )
    assert career.longest_club_spell == ManagerSpellWindow(
        603, date(2023, 7, 18), date(2037, 12, 4)
    )
    assert career.shortest_club_spell is None
    assert career.longest_national_spell is None
    assert career.shortest_national_spell is None
    assert career.unknown["word_151"] == 5
    assert career.unknown["word_171"] == 21
    assert set(career.unknown) == set(ManagerCareerRecord.UNKNOWN_KEYS)


def test_current_job_block() -> None:
    job = decode_manager_career_record(record(328408)).current_job

    assert job is not None
    assert (job.team_id, job.start_date) == (603, date(2023, 7, 18))
    assert job.highest_fee_paid == ManagerFee(189608, date(2036, 8, 10), 22_937_564, 706, 603)
    assert job.highest_fee_received == ManagerFee(280836, date(2037, 8, 9), 32_347_260, 603, 20360)
    assert (job.games, job.wins, job.draws, job.losses) == (741, 391, 131, 219)
    assert (job.goals_for, job.goals_against) == (1589, 1059)
    assert (job.cups, job.league_titles, job.awards) == (1, 3, 19)
    assert (job.players_bought, job.players_sold, job.players_released) == (127, 39, 50)
    assert (job.money_spent, job.money_received) == (101_492_665, 97_733_168)


def test_unemployed_manager_has_no_current_job() -> None:
    assert decode_manager_career_record(record(7, employed=False)).current_job is None


def test_unset_fee_reads_none() -> None:
    data = bytearray(record(7))
    struct.pack_into("<I", data, 9, _UNSET)
    assert decode_manager_career_record(bytes(data)).highest_fee_paid is None


def test_section_walk_reads_every_record_in_reference_order() -> None:
    data = section(record(7), record(1001), record(328408))

    records = decode_manager_career_records(data)

    assert [career.reference for career in records] == [7, 1001, 328408]
    assert locate_manager_career_records(data).stop == len(data) - len(TRAILER)


def test_walk_stops_where_references_stop_falling() -> None:
    data = section(record(5000), record(7), record(1001))

    assert [career.reference for career in decode_manager_career_records(data)] == [7, 1001]


def test_walk_stops_at_a_slot_without_the_record_head() -> None:
    broken = bytearray(record(7))
    broken[8] = 0
    data = section(bytes(broken), record(1001))

    assert [career.reference for career in decode_manager_career_records(data)] == [1001]


def test_empty_table_reads_no_records() -> None:
    assert decode_manager_career_records(section()) == ()


def test_missing_trailer_raises() -> None:
    with pytest.raises(CorruptSaveError, match="trailer"):
        decode_manager_career_records(section(record(7))[:-1])


def test_fields_are_registered_unconfirmed() -> None:
    for model in (ManagerCareerRecord, ManagerCurrentJob, ManagerFee, ManagerSpellWindow):
        for name in (field.name for field in dataclasses.fields(model)):
            if name in {
                "highest_fee_paid",
                "highest_fee_received",
                "longest_club_spell",
                "shortest_club_spell",
                "longest_national_spell",
                "shortest_national_spell",
                "current_job",
            }:
                continue
            assert field_status(model, name) == "unconfirmed"
    assert field_status(ManagerCareerRecord, "current_job.games") == "unconfirmed"
    assert field_status(ManagerCareerRecord, "highest_fee_paid.fee") == "unconfirmed"
