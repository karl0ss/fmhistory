"""Decoding manager career statistics from the `person_record_manager` section.

The section (`03 01 'tad.'`, version 30 on the ground-truth save) holds two parts:

- the human managers' event logs (entries `[u8 type] 15 ff ff ff ff ff ff [u32 reference]
  00 [u32 team] [date] ...`, variable length), not decoded here;
- then, butted to the section's end, one fixed 367-byte record per person who has
  managed in the game world, in ascending reference order, and a 4-byte `ff ff ff ff`
  trailer.

A record (offsets from its start; `date` = the 4-byte packed game date, `ff..` = unset):

    +0    u32 reference, u32 reference (again), u8 01
    +9    fee: highest fee paid over the career
    +32   fee: highest fee received over the career
            fee = [u32 player reference][date][u32 fee £][u16][u32 from team][u8][u32 to team]
    +55   4 spell slots x 13 B: longest club, shortest club, longest national,
          shortest national; slot = [u8][u32 team][date start][date end]
    +107  u64 money spent  +115 u64 money received  +123 u64 agent fees
    +131  u32 goals for    +135 u32 goals against
    +147  u16 cups  u16 league titles  (+151..+161 six u16 counters, unknown)
    +163  u16 games  u16 wins  u16 losses  (+169..+177 five u16 counters, unknown)
    +193  u16 awards  (+195, +197 unknown)  +199 u16 bought  u16 sold  u16 released
    +209  u8 club jobs  u8 national jobs
    current-job block:
    +215  [u32 from team][u8][u32 to team][u32 player][date][u32 fee] highest paid
    +238  [u32 from team][u8][u32 to team][u32 player][date][u32 fee] highest received
    +260  date job start   +264 date (the save's current date)
    +269  u32 team         +286 u64 money spent  +294 u64 money received
    +302  u32 goals for    +306 u32 goals against  (+318 u16 unknown)
    +320  u16 cups  u16 league titles  u16 games  u16 wins  u16 losses  u16 awards
    +332  u16 bought  +336 u16 sold  +338 u16 released  (+340 u16 unknown)

Draws are stored nowhere: the game shows games minus wins minus losses. The layout
was reverse-engineered on one save (`Karl Hudgell - UnemployedNew.fm`, build 26.3.2)
and is not verified across builds.
"""

from __future__ import annotations

import struct

from fmsave._errors import CorruptSaveError
from fmsave._frozen import FrozenMapping
from fmsave._scan import decode_date
from fmsave.models.career_history import (
    ManagerCareerRecord,
    ManagerCurrentJob,
    ManagerFee,
    ManagerSpellWindow,
)

PERSON_RECORD_MANAGER_SECTION = "person_record_manager"

RECORD_BYTES = 367
TRAILER = b"\xff\xff\xff\xff"
_RECORD_MARK = 1
_UNSET = 0xFFFFFFFF

_U8 = struct.Struct("<B")
_U16 = struct.Struct("<H")
_U32 = struct.Struct("<I")
_U64 = struct.Struct("<Q")

# Career block.
_PAID_AT = 9
_RECEIVED_AT = 32
_SPELLS_AT = 55
_SPELL_BYTES = 13
_SPENT_AT = 107
_RECEIVED_MONEY_AT = 115
_AGENT_FEES_AT = 123
_GOALS_FOR_AT = 131
_GOALS_AGAINST_AT = 135
_CUPS_AT = 147
_LEAGUE_TITLES_AT = 149
_GAMES_AT = 163
_WINS_AT = 165
_LOSSES_AT = 167
_AWARDS_AT = 193
_BOUGHT_AT = 199
_SOLD_AT = 201
_RELEASED_AT = 203
_CLUB_JOBS_AT = 209
_NATIONAL_JOBS_AT = 210

# Current-job block.
_JOB_PAID_AT = 215
_JOB_RECEIVED_AT = 238
_JOB_START_AT = 260
_JOB_TEAM_AT = 269
_JOB_SPENT_AT = 286
_JOB_RECEIVED_MONEY_AT = 294
_JOB_GOALS_FOR_AT = 302
_JOB_GOALS_AGAINST_AT = 306
_JOB_CUPS_AT = 320
_JOB_LEAGUE_TITLES_AT = 322
_JOB_GAMES_AT = 324
_JOB_WINS_AT = 326
_JOB_LOSSES_AT = 328
_JOB_AWARDS_AT = 330
_JOB_BOUGHT_AT = 332
_JOB_SOLD_AT = 336
_JOB_RELEASED_AT = 338

_UNKNOWN_WORD_OFFSETS = tuple(
    int(key.removeprefix("word_")) for key in ManagerCareerRecord.UNKNOWN_KEYS
)


def _u16(data: bytes, offset: int) -> int:
    value: int = _U16.unpack_from(data, offset)[0]
    return value


def _u32(data: bytes, offset: int) -> int:
    value: int = _U32.unpack_from(data, offset)[0]
    return value


def _u64(data: bytes, offset: int) -> int:
    value: int = _U64.unpack_from(data, offset)[0]
    return value


def _team(data: bytes, offset: int) -> int | None:
    team = _u32(data, offset)
    return None if team == _UNSET else team


def _career_fee(data: bytes, offset: int) -> ManagerFee | None:
    """`[u32 player][date][u32 fee][u16][u32 from][u8][u32 to]`, None when unset."""
    player = _u32(data, offset)
    if player == _UNSET:
        return None
    return ManagerFee(
        player_reference=player,
        transfer_date=decode_date(data, offset + 4),
        fee=_u32(data, offset + 8),
        from_team_id=_team(data, offset + 14),
        to_team_id=_team(data, offset + 19),
    )


def _job_fee(data: bytes, offset: int) -> ManagerFee | None:
    """`[u32 from][u8][u32 to][u32 player][date][u32 fee]`, None when unset."""
    player = _u32(data, offset + 9)
    if player == _UNSET:
        return None
    return ManagerFee(
        player_reference=player,
        transfer_date=decode_date(data, offset + 13),
        fee=_u32(data, offset + 17),
        from_team_id=_team(data, offset),
        to_team_id=_team(data, offset + 5),
    )


def _spell(data: bytes, offset: int) -> ManagerSpellWindow | None:
    team = _team(data, offset + 1)
    if team is None:
        return None
    return ManagerSpellWindow(
        team_id=team,
        start_date=decode_date(data, offset + 5),
        end_date=decode_date(data, offset + 9),
    )


def _current_job(data: bytes) -> ManagerCurrentJob | None:
    team = _team(data, _JOB_TEAM_AT)
    if team is None:
        return None
    games = _u16(data, _JOB_GAMES_AT)
    wins = _u16(data, _JOB_WINS_AT)
    losses = _u16(data, _JOB_LOSSES_AT)
    return ManagerCurrentJob(
        team_id=team,
        start_date=decode_date(data, _JOB_START_AT),
        highest_fee_paid=_job_fee(data, _JOB_PAID_AT),
        highest_fee_received=_job_fee(data, _JOB_RECEIVED_AT),
        money_spent=_u64(data, _JOB_SPENT_AT),
        money_received=_u64(data, _JOB_RECEIVED_MONEY_AT),
        goals_for=_u32(data, _JOB_GOALS_FOR_AT),
        goals_against=_u32(data, _JOB_GOALS_AGAINST_AT),
        games=games,
        wins=wins,
        draws=games - wins - losses,
        losses=losses,
        cups=_u16(data, _JOB_CUPS_AT),
        league_titles=_u16(data, _JOB_LEAGUE_TITLES_AT),
        awards=_u16(data, _JOB_AWARDS_AT),
        players_bought=_u16(data, _JOB_BOUGHT_AT),
        players_sold=_u16(data, _JOB_SOLD_AT),
        players_released=_u16(data, _JOB_RELEASED_AT),
    )


def decode_manager_career_record(record: bytes) -> ManagerCareerRecord:
    """One 367-byte career record (see the module notes for the layout)."""
    games = _u16(record, _GAMES_AT)
    wins = _u16(record, _WINS_AT)
    losses = _u16(record, _LOSSES_AT)
    spells = [_spell(record, _SPELLS_AT + slot * _SPELL_BYTES) for slot in range(4)]
    return ManagerCareerRecord(
        reference=_u32(record, 0),
        highest_fee_paid=_career_fee(record, _PAID_AT),
        highest_fee_received=_career_fee(record, _RECEIVED_AT),
        longest_club_spell=spells[0],
        shortest_club_spell=spells[1],
        longest_national_spell=spells[2],
        shortest_national_spell=spells[3],
        money_spent=_u64(record, _SPENT_AT),
        money_received=_u64(record, _RECEIVED_MONEY_AT),
        agent_fees=_u64(record, _AGENT_FEES_AT),
        goals_for=_u32(record, _GOALS_FOR_AT),
        goals_against=_u32(record, _GOALS_AGAINST_AT),
        games=games,
        wins=wins,
        draws=games - wins - losses,
        losses=losses,
        cups=_u16(record, _CUPS_AT),
        league_titles=_u16(record, _LEAGUE_TITLES_AT),
        awards=_u16(record, _AWARDS_AT),
        players_bought=_u16(record, _BOUGHT_AT),
        players_sold=_u16(record, _SOLD_AT),
        players_released=_u16(record, _RELEASED_AT),
        club_jobs=record[_CLUB_JOBS_AT],
        national_jobs=record[_NATIONAL_JOBS_AT],
        current_job=_current_job(record),
        unknown=FrozenMapping(
            {f"word_{offset}": _u16(record, offset) for offset in _UNKNOWN_WORD_OFFSETS}
        ),
    )


def _is_record_head(data: bytes, offset: int) -> bool:
    first, second = struct.unpack_from("<II", data, offset)
    return first == second and data[offset + 8] == _RECORD_MARK


def locate_manager_career_records(data: bytes) -> range:
    """The offsets of the career records: walked back from the trailer, 367 B at a time.

    The records end 4 bytes before the section's end (the `ff ff ff ff` trailer) and
    rise in reference towards it; the walk stops at the first slot that does not open
    with a doubled reference and the 01 mark, or whose reference does not fall. An
    empty range means the section holds no records.

    Raises:
        CorruptSaveError: The section does not end with the trailer.
    """
    if not data.endswith(TRAILER):
        raise CorruptSaveError(
            f"{PERSON_RECORD_MANAGER_SECTION} does not end with the ff ff ff ff trailer "
            f"({len(data)} bytes, tail {data[-4:].hex()}): the record layout has moved"
        )
    end = len(data) - len(TRAILER)
    start = end
    above: int | None = None
    while start - RECORD_BYTES >= 0:
        candidate = start - RECORD_BYTES
        if not _is_record_head(data, candidate):
            break
        reference = _u32(data, candidate)
        if above is not None and reference >= above:
            break
        above = reference
        start = candidate
    return range(start, end, RECORD_BYTES)


def decode_manager_career_records(data: bytes) -> tuple[ManagerCareerRecord, ...]:
    """Every career record in the section, in reference order."""
    return tuple(
        decode_manager_career_record(data[offset : offset + RECORD_BYTES])
        for offset in locate_manager_career_records(data)
    )
