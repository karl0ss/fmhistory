"""Decoding manager career statistics from the `person_record_manager` section.

The section (`03 01 'tad.'`, version 30 on the ground-truth save) holds two parts:

- the human managers' event logs (entries `[u8 type] 15 ff ff ff ff ff ff [u32 reference]
  00 [u32 team] [date] ...`, variable length), decoded by `readers/manager_events.py`;
- then, butted to the section's end, one record per person who has managed in the
  game world, and a 4-byte `ff ff ff ff` trailer.

A record is a doubled u32 reference, three slots, and a 152-byte current-job tail. A
slot is a u8 flag and, when the flag is 01, a 204-byte career block: the first slot is
the men's career, the second the women's (FM26; a save carried over from an older
career has only men's blocks), the third has never been seen filled. So a record runs
163 + 204 per present block bytes. Records are in ascending reference order on the
ground-truth save, but a save started in FM26 has some out of order.

The ground-truth save's records all have a men's block alone (367 bytes), and the
offsets below are in that layout; other records are rebuilt into it to decode.

A record (offsets from its start; `date` = the 4-byte packed game date, `ff..` = unset):

    +0    u32 reference, u32 reference (again), u8 01 (men's block present)
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
    +213  u8 women's slot flag (00)  +214 u8 third slot flag (00)
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
and is not verified across builds; the slots on a save started in FM26 (5,631
records: 3,235 men's only, 1,776 men's and women's, 458 women's only, 162 neither).
"""

from __future__ import annotations

import re
import struct
from dataclasses import fields, replace

from fmsave._errors import CorruptSaveError
from fmsave._frozen import FrozenMapping
from fmsave._scan import decode_date
from fmsave.models.career_history import (
    ManagerCareerRecord,
    ManagerCareerTotals,
    ManagerCurrentJob,
    ManagerFee,
    ManagerSpellWindow,
)

PERSON_RECORD_MANAGER_SECTION = "person_record_manager"

RECORD_BYTES = 367
BLOCK_BYTES = 204
TAIL_BYTES = 152
TRAILER = b"\xff\xff\xff\xff"
_SLOT_COUNT = 3
# A doubled reference and a slot flag; a lookahead, so heads may overlap.
_RECORD_HEAD = re.compile(rb"(?=(.{4})\1[\x00\x01])", re.DOTALL)
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
    """One record in the ground-truth save's 367-byte layout (see the module notes)."""
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
        womens_career=None,
        unknown=FrozenMapping(
            {f"word_{offset}": _u16(record, offset) for offset in _UNKNOWN_WORD_OFFSETS}
        ),
    )


_UNSET_FEE = (
    b"\xff" * 4
    + b"\x01\x00\x6c\x07"
    + b"\xff" * 4
    + b"\x00\x00"
    + b"\xff" * 4
    + b"\x00"
    + b"\xff" * 4
)
_UNSET_SPELL = b"\x00" + b"\xff" * 4 + b"\x01\x00\x6c\x07" * 2
# A block with nothing in it, for a record without a men's block.
_EMPTY_BLOCK = (_UNSET_FEE * 2 + _UNSET_SPELL * 4).ljust(BLOCK_BYTES, b"\x00")
_TOTALS_FIELDS = tuple(field.name for field in fields(ManagerCareerTotals))


def _record_end(data: bytes, offset: int, end: int) -> int | None:
    """Where the record opening at `offset` ends, or None when none opens there."""
    if offset + 8 > end:
        return None
    first, second = struct.unpack_from("<II", data, offset)
    if first != second or first == 0:
        return None
    position = offset + 8
    for _ in range(_SLOT_COUNT):
        if position >= end or data[position] > 1:
            return None
        position += 1 + data[position] * BLOCK_BYTES
    position += TAIL_BYTES
    return position if position <= end else None


def _walk(data: bytes, start: int, end: int) -> tuple[int, ...] | None:
    offsets: list[int] = []
    position = start
    while position < end:
        record_end = _record_end(data, position, end)
        if record_end is None:
            return None
        offsets.append(position)
        position = record_end
    return tuple(offsets)


def locate_manager_career_records(data: bytes) -> tuple[int, ...]:
    """The offsets of the career records, in file order.

    The records run back to back from the end of the event logs to 4 bytes before the
    section's end (the `ff ff ff ff` trailer), each as long as its present slots make
    it. They are found as the first doubled reference from which a walk of whole
    records ends exactly at the trailer; none means the section holds no records.

    Raises:
        CorruptSaveError: The section does not end with the trailer.
    """
    if not data.endswith(TRAILER):
        raise CorruptSaveError(
            f"{PERSON_RECORD_MANAGER_SECTION} does not end with the ff ff ff ff trailer "
            f"({len(data)} bytes, tail {data[-4:].hex()}): the record layout has moved"
        )
    end = len(data) - len(TRAILER)
    for match in _RECORD_HEAD.finditer(data, 0, end):
        offsets = _walk(data, match.start(), end)
        if offsets is not None:
            return offsets
    return ()


def _block_at(data: bytes, position: int) -> tuple[bytes | None, int]:
    """The slot at `position`: its block (None when absent) and where the next starts."""
    if data[position]:
        return data[position + 1 : position + 1 + BLOCK_BYTES], position + 1 + BLOCK_BYTES
    return None, position + 1


def _decode_at(data: bytes, offset: int) -> ManagerCareerRecord:
    position = offset + 8
    mens, position = _block_at(data, position)
    womens, position = _block_at(data, position)
    _, position = _block_at(data, position)  # the third slot: never seen filled
    head = data[offset : offset + 8]
    tail = data[position : position + TAIL_BYTES]
    record = decode_manager_career_record(_canonical(head, mens or _EMPTY_BLOCK, tail))
    if womens is None:
        return record
    totals = decode_manager_career_record(_canonical(head, womens, tail))
    return replace(
        record,
        womens_career=ManagerCareerTotals(
            **{name: getattr(totals, name) for name in _TOTALS_FIELDS}
        ),
    )


def _canonical(head: bytes, block: bytes, tail: bytes) -> bytes:
    """The record laid out as the ground-truth save stores it: one block, then the tail."""
    return head + b"\x01" + block + b"\x00\x00" + tail


def decode_manager_career_records(data: bytes) -> tuple[ManagerCareerRecord, ...]:
    """Every career record in the section, in file order."""
    return tuple(_decode_at(data, offset) for offset in locate_manager_career_records(data))
