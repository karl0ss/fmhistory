"""Decoding every manager's spells from `tc_manager_history_dt` and `tc_manager_history_ls`.

`tc_manager_history_dt` (`03 01 'tmc.' 02 00`, 8 bytes) is followed by fixed 31-byte
rows, appended in the order spells end; nothing else is in the section. A row
(offsets from its start; `date` = the 4-byte packed game date, low 9 bits of the
first u16 the day of year, high bits a time slot):

    +0   u32 manager history reference
    +4   date start (day 0 or year 1900 = null: running before the history begins)
    +8   date end
    +12  u32, u32   (mostly 0xffffffff; meaning open)
    +20  u16 wins  u16 draws  u16 losses
    +26  u8 kind    (10 on caretaker-like short spells; meaning open)
    +27  u8 x 4     (small counters; meaning open)

`tc_manager_history_ls` uses the shared history-index grammar: `03 01 'tad.' 04 00`,
u32 free count (0) and that many u32s, u32 list count, then per list a u32 count and
that many u32 values, then a 10-byte trailer (u32 0, u32 row size 31, u16 2). Values
are delta-encoded as in the league history: the m-th row of a list sits
`value[m] + value[m - 1]` bytes past the dt head. There is one list per team, numbered
in the order the teams' first rows were written, and every row is in exactly one list.
The index names no team, so lists are pinned to teams through the managers' career
records (`resolve_manager_history_teams`).

Open spells are not rows: `manager_spells` adds each manager's current job from his
career record. The layout was reverse-engineered on one save
(`Karl Hudgell - UnemployedNew.fm`, build 26.3.2) and is not verified across builds.
"""

from __future__ import annotations

import struct
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from fmsave._errors import CorruptSaveError
from fmsave._frozen import FrozenMapping
from fmsave._scan import decode_date
from fmsave.models.career_history import ManagerCareerRecord, ManagerHistorySpell

MANAGER_HISTORY_DT_SECTION = "tc_manager_history_dt"
MANAGER_HISTORY_LS_SECTION = "tc_manager_history_ls"

DT_TAG = b"\x03\x01tmc."
DT_HEAD = 8
ROW_BYTES = 31
LS_TAG = b"\x03\x01tad."
_LS_COUNTS_AT = 8
_LS_TRAILER = 10

_ROW = struct.Struct("<I4s4sIIHHHBBBBB")
_U32 = struct.Struct("<I")


def decode_manager_history_lists(dt_size: int, ls_data: bytes) -> tuple[tuple[int, ...], ...]:
    """The dt row offsets of every team's list in `tc_manager_history_ls`.

    Args:
        dt_size: Length of the `tc_manager_history_dt` section the offsets point into.
        ls_data: The `tc_manager_history_ls` section.

    Returns:
        One tuple of absolute dt offsets per list, in list-number order.

    Raises:
        CorruptSaveError: The index does not parse exactly: wrong tag, a count running
            past the trailer, bytes left over, a trailer naming another row size, or an
            offset that is not a row start inside the dt section.
    """
    if not ls_data.startswith(LS_TAG) or len(ls_data) < _LS_COUNTS_AT + 8 + _LS_TRAILER:
        raise CorruptSaveError(f"{MANAGER_HISTORY_LS_SECTION} does not open with the index tag")
    end = len(ls_data) - _LS_TRAILER
    row_bytes = _U32.unpack_from(ls_data, end + 4)[0]
    if row_bytes != ROW_BYTES:
        raise CorruptSaveError(
            f"{MANAGER_HISTORY_LS_SECTION} names {row_bytes}-byte rows, not {ROW_BYTES}"
        )
    free_count = _U32.unpack_from(ls_data, _LS_COUNTS_AT)[0]
    offset = _LS_COUNTS_AT + 4 + 4 * free_count
    if offset + 4 > end:
        raise CorruptSaveError(f"{MANAGER_HISTORY_LS_SECTION} free list runs past its end")
    list_count = _U32.unpack_from(ls_data, offset)[0]
    offset += 4
    lists: list[tuple[int, ...]] = []
    for _ in range(list_count):
        if offset + 4 > end:
            raise CorruptSaveError(f"{MANAGER_HISTORY_LS_SECTION} lists run past its end")
        count = _U32.unpack_from(ls_data, offset)[0]
        offset += 4
        if offset + 4 * count > end:
            raise CorruptSaveError(f"{MANAGER_HISTORY_LS_SECTION} lists run past its end")
        values = struct.unpack_from(f"<{count}I", ls_data, offset)
        offset += 4 * count
        rows: list[int] = []
        previous = 0
        for value in values:
            row = DT_HEAD + ((value + previous) & 0xFFFF_FFFF)
            if (row - DT_HEAD) % ROW_BYTES or row + ROW_BYTES > dt_size:
                raise CorruptSaveError(
                    f"{MANAGER_HISTORY_LS_SECTION} points at {row}, not a row of "
                    f"{MANAGER_HISTORY_DT_SECTION}"
                )
            rows.append(row)
            previous = value
        lists.append(tuple(rows))
    if offset != end:
        raise CorruptSaveError(f"{MANAGER_HISTORY_LS_SECTION} has bytes after its lists")
    return tuple(lists)


def decode_manager_history_row(
    dt_data: bytes, offset: int, history_index: int | None
) -> ManagerHistorySpell:
    """The ended spell stored in the 31-byte row at `offset`, with no team."""
    (
        reference,
        _start,
        _end,
        word_12,
        word_16,
        wins,
        draws,
        losses,
        kind,
        byte_27,
        byte_28,
        byte_29,
        byte_30,
    ) = _ROW.unpack_from(dt_data, offset)
    return ManagerHistorySpell(
        reference=reference,
        team_id=None,
        start_date=decode_date(dt_data, offset + 4),
        end_date=decode_date(dt_data, offset + 8),
        games=wins + draws + losses,
        wins=wins,
        draws=draws,
        losses=losses,
        history_index=history_index,
        kind=kind,
        unknown=FrozenMapping(
            {
                "word_12": word_12,
                "word_16": word_16,
                "byte_27": byte_27,
                "byte_28": byte_28,
                "byte_29": byte_29,
                "byte_30": byte_30,
            }
        ),
    )


def decode_manager_history(dt_data: bytes, ls_data: bytes) -> tuple[ManagerHistorySpell, ...]:
    """Every ended spell the section stores, in row order, with its list number.

    `team_id` is None on every spell; `resolve_manager_history_teams` names the teams
    it can.

    Raises:
        CorruptSaveError: The dt section is not the tagged head plus whole 31-byte
            rows, the index does not parse exactly, or a row is listed twice or not
            at all.
    """
    if not dt_data.startswith(DT_TAG) or (len(dt_data) - DT_HEAD) % ROW_BYTES:
        raise CorruptSaveError(
            f"{MANAGER_HISTORY_DT_SECTION} is not an 8-byte head plus {ROW_BYTES}-byte rows"
        )
    lists = decode_manager_history_lists(len(dt_data), ls_data)
    index_by_row: dict[int, int] = {}
    for history_index, rows in enumerate(lists):
        for row in rows:
            if row in index_by_row:
                raise CorruptSaveError(f"{MANAGER_HISTORY_LS_SECTION} lists row {row} twice")
            index_by_row[row] = history_index
    row_count = (len(dt_data) - DT_HEAD) // ROW_BYTES
    if len(index_by_row) != row_count:
        raise CorruptSaveError(
            f"{MANAGER_HISTORY_LS_SECTION} lists {len(index_by_row)} of {row_count} rows"
        )
    return tuple(
        decode_manager_history_row(dt_data, offset, index_by_row[offset])
        for offset in range(DT_HEAD, len(dt_data), ROW_BYTES)
    )


def resolve_manager_history_teams(
    spells: Iterable[ManagerHistorySpell], records: Iterable[ManagerCareerRecord]
) -> dict[int, int]:
    """The team of every manager-history list a career record pins down.

    A career record keeps its manager's longest and shortest club and national spells
    with team, start and end, in men's and (FM26) women's football. When exactly one list holds a row of that manager with
    the same start and end, that list is the team's. A list is resolved only when
    every window that claims it names the same team, and a team claimed by two lists
    is dropped for both, so lists no window reaches stay unresolved rather than
    guessed.

    Returns:
        List number to `Team.team_id`.
    """
    by_window: dict[tuple[int, object, object], set[int]] = {}
    for spell in spells:
        if spell.history_index is None or spell.start_date is None:
            continue
        key = (spell.reference, spell.start_date, spell.end_date)
        by_window.setdefault(key, set()).add(spell.history_index)
    claims: dict[int, set[int]] = {}
    for record in records:
        windows = [
            window
            for career in (record, record.womens_career)
            if career is not None
            for window in (
                career.longest_club_spell,
                career.shortest_club_spell,
                career.longest_national_spell,
                career.shortest_national_spell,
            )
        ]
        for window in windows:
            if window is None or window.start_date is None:
                continue
            owners = by_window.get((record.reference, window.start_date, window.end_date))
            if owners is not None and len(owners) == 1:
                claims.setdefault(next(iter(owners)), set()).add(window.team_id)
    resolved = {index: next(iter(teams)) for index, teams in claims.items() if len(teams) == 1}
    holders = Counter(resolved.values())
    return {index: team for index, team in resolved.items() if holders[team] == 1}


def current_job_spells(records: Iterable[ManagerCareerRecord]) -> tuple[ManagerHistorySpell, ...]:
    """Each manager's open spell: the current job his career record holds."""
    spells: list[ManagerHistorySpell] = []
    for record in records:
        job = record.current_job
        if job is None:
            continue
        spells.append(
            ManagerHistorySpell(
                reference=record.reference,
                team_id=job.team_id,
                start_date=job.start_date,
                end_date=None,
                games=job.games,
                wins=job.wins,
                draws=job.draws,
                losses=job.losses,
                history_index=None,
                kind=None,
                unknown=FrozenMapping({}),
            )
        )
    return tuple(spells)


def manager_spells(
    ended: Sequence[ManagerHistorySpell],
    records: Sequence[ManagerCareerRecord],
    teams: Mapping[int, int] | None = None,
) -> tuple[ManagerHistorySpell, ...]:
    """Ended spells named with their teams, plus every current job, per manager.

    Args:
        ended: `decode_manager_history` output.
        records: Every manager's career record.
        teams: List number to team id; resolved from `records` when None.

    Returns:
        Spells grouped by manager reference; one manager's ended spells in the order
        they ended, then his current job.
    """
    if teams is None:
        teams = resolve_manager_history_teams(ended, records)
    named = [
        replace(spell, team_id=teams[spell.history_index])
        if spell.history_index is not None and spell.history_index in teams
        else spell
        for spell in ended
    ]
    keyed = [((spell.reference, False, position), spell) for position, spell in enumerate(named)]
    keyed.extend(((spell.reference, True, 0), spell) for spell in current_job_spells(records))
    keyed.sort(key=lambda item: item[0])
    return tuple(spell for _key, spell in keyed)
