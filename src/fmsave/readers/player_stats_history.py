"""Decoding the per-player statistics history: `player_stats_hist_dt` and its pool index.

`player_stats_hist_dt` (`03 01 'tmc.' 06 00`, then 152-byte rows back to back) is a pool of
rows, one per player per team per season per competition type, holding that line's
statistics. A row names no player. Its owners live in a pool index the directory does not
list: one unlisted frame of the span region, in the per-person index grammar
`pl_hist_ls` also uses,

    03 01 'tad.' 04 00
    u32 free_count, free_count x u32      offsets of free (unowned) rows
    u32 list_count, list_count x list     one list per owner: u32 n, n x u32 values
    u32 empty_count, empty_count x u32    numbers of the lists that are empty
    u32 152, u16 6                        the dt row size and section version

A list's values are delta-encoded as in every `_ls` index: its m-th row sits at
`value[m] + value[m - 1]` bytes past the dt's 8-byte head (the first at `value[0]`). On the
ground-truth save the free offsets and the lists' rows together cover every one of the
dt's 5,766,139 rows exactly once.

A list is bound to its player by his own `game_db` object: the u32 stored 21 bytes before
his person block's start (the first-name id) is his list's number, or 0xffffffff when he
has no history list. On the ground-truth save every one of the 223,569 player records has
a person block, 217,876 store a distinct in-range list number and 5,693 store 0xffffffff.
A retired or released player whose `game_db` object survives in full stores his number the
same way (`history_person_list_numbers`); one cut down to a stub keeps no list.

A row (offsets from its start):

    +0   00
    +1   u32 team id         `Team.team_id` the line is for (0xffffffff on a few rows)
    +5   u16 competition id  the team's league competition that season, 0xffff for none
    +7   i32 departure fee   the money of the move that ended the player's spell at
                             the team, on every row of the spell's last season; -1
                             (0xffffffff) while the spell goes on or when it ended in
                             a release
    +11  u16 season year     the season's starting year
    +13  u16 rating total    ten times the summed match ratings
    +15  u16 minutes
    +30  u8 spell code       0 permanent, 1 loan, 4 trial
    +31  u8 kind             the season-statistics slot order: 0 non-competitive,
                             1 league, 2 cup, 3 continental, 4 international

and the statistic words of `_FIELDS`. The words are the current season's
statistics-line words (`SEASON_STATS` in the layouts): from offset 27 of the line on, a
history row stores a line word 13 bytes later than the line does; the small counts before
it are reordered. Like the season-statistics line, a few words hold a goalkeeper's saves on
a natural goalkeeper's row and other statistics on everyone else's.
"""

from __future__ import annotations

import struct
from array import array
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from fmsave._container import ContainerIndex, read_region_frame, region_frame_heads
from fmsave.models.player_stats_history import PlayerHistoryStats
from fmsave.models.season_stats import SeasonStatsKind
from fmsave.readers._common import SPAN_REGION
from fmsave.readers.persons import PersonBlockDecoder

PLAYER_STATS_HISTORY_DT_SECTION = "player_stats_hist_dt"

DT_HEAD_BYTES = 8
ROW_BYTES = 152
INDEX_VERSION = 6
INDEX_TAG = b"\x03\x01tad.\x04\x00"
_INDEX_TRAILER = struct.Struct("<IH")
_U32 = struct.Struct("<I")
_NO_LIST = 0xFFFF_FFFF
_NO_TEAM = 0xFFFF_FFFF
_NO_COMPETITION = 0xFFFF
# The list number sits this many bytes before the person block's start.
LIST_NUMBER_BEFORE_BLOCK = 21

_KINDS = (
    SeasonStatsKind.NON_COMPETITIVE,
    SeasonStatsKind.LEAGUE,
    SeasonStatsKind.CUP,
    SeasonStatsKind.CONTINENTAL,
    SeasonStatsKind.INTERNATIONAL,
)

# The row head: [00][u32 team id][u16 competition id][i32 departure fee][u16 season year]
# [u16 rating total]; the spell and kind bytes sit at `_SPELL_OFFSET` and `_KIND_OFFSET`.
_HEAD = struct.Struct("<xIHiHH")
_NO_FEE = -1
_SPELL_OFFSET = 30
_KIND_OFFSET = 31
# (field, row offset, struct code, stored units per public unit)
_FIELDS: tuple[tuple[str, int, str, int], ...] = (
    ("minutes", 15, "H", 1),
    ("goals_allowed", 17, "B", 1),
    ("penalties_taken", 18, "B", 1),
    ("penalties_scored", 19, "B", 1),
    ("red_cards", 20, "B", 1),
    ("yellow_cards", 21, "B", 1),
    ("clean_sheets", 22, "B", 1),
    ("starts", 24, "B", 1),
    ("substitute_appearances", 25, "B", 1),
    ("rated_appearances", 26, "B", 1),
    ("goals", 27, "B", 1),
    ("assists", 28, "B", 1),
    ("player_of_the_match", 29, "B", 1),
    ("passes_attempted", 40, "H", 1),
    ("passes_completed", 42, "H", 1),
    ("tackles_attempted", 44, "H", 1),
    ("tackles_completed", 46, "H", 1),
    ("dribbles", 52, "H", 1),
    ("fouls_made", 54, "H", 1),
    ("fouls_against", 56, "H", 1),
    ("shots", 58, "H", 1),
    ("shots_on_target", 60, "H", 1),
    ("distance_km", 78, "H", 10),
    ("offsides", 80, "H", 1),
    ("key_passes", 86, "H", 1),
    ("key_tackles", 88, "H", 1),
    ("key_headers", 90, "H", 1),
    ("interceptions", 92, "H", 1),
    ("clear_cut_chances_created", 94, "H", 1),
    ("possession_lost", 100, "H", 1),
    ("possession_won", 102, "H", 1),
    ("expected_goals", 104, "H", 100),
    ("expected_assists", 106, "H", 100),
    ("free_kick_shots", 112, "H", 1),
    ("goals_outside_box", 114, "H", 1),
    ("open_play_crosses_attempted", 122, "H", 1),
    ("shots_outside_box", 124, "H", 1),
    ("expected_goals_prevented", 126, "h", 100),
    ("high_intensity_sprints", 128, "H", 1),
    ("progressive_passes", 132, "H", 1),
    ("pressures_attempted", 134, "H", 1),
    ("pressures_completed", 136, "H", 1),
    ("open_play_key_passes", 138, "H", 1),
    ("non_penalty_expected_goals", 140, "H", 100),
    ("crosses_attempted", 144, "H", 1),
    ("crosses_completed", 146, "H", 1),
    ("shots_blocked", 148, "H", 1),
)
OUTFIELD_FIELDS: tuple[tuple[str, int, str, int], ...] = (
    ("aerial_challenges_attempted", 48, "H", 1),
    ("headers_won", 50, "H", 1),
    ("open_play_crosses_completed", 84, "H", 1),
    ("blocks", 96, "H", 1),
    ("clearances", 108, "H", 1),
)
GOALKEEPER_FIELDS: tuple[tuple[str, int, str, int], ...] = (
    ("saves_held", 48, "H", 1),
    ("saves_parried", 50, "H", 1),
    ("saves_tipped", 82, "H", 1),
    ("shots_on_target_faced", 96, "H", 1),
)
_ALL_FIELDS = _FIELDS + OUTFIELD_FIELDS + GOALKEEPER_FIELDS
_ROW_STRUCTS = tuple(struct.Struct("<" + code) for _, _, code, _ in _ALL_FIELDS)
_OUTFIELD_NAMES = frozenset(name for name, *_ in OUTFIELD_FIELDS)
_GOALKEEPER_NAMES = frozenset(name for name, *_ in GOALKEEPER_FIELDS)


@dataclass(frozen=True, slots=True)
class StatsHistoryIndex:
    """The parsed pool index: every list's dt row offsets, flattened.

    List `n` owns `offsets[starts[n]:starts[n + 1]]`, absolute offsets into the dt section
    in the order the list stores them (season order). Never mutate the arrays: the index
    is cached and shared.
    """

    offsets: array[int]
    starts: array[int]
    free_count: int

    @property
    def list_count(self) -> int:
        """How many lists the index holds, empty ones included."""
        return len(self.starts) - 1

    def rows_of(self, list_number: int) -> array[int]:
        """The absolute dt offsets of one list's rows, in stored order."""
        return self.offsets[self.starts[list_number] : self.starts[list_number + 1]]


def decode_stats_history_index(data: bytes) -> StatsHistoryIndex | None:
    """Parse the pool index frame, or None when it is not exactly that grammar.

    The frame must open with the `tad.` index tag, walk to its trailer with nothing left
    over, close with the dt row size (152) and version (6), and list as empty exactly the
    lists that have no rows. Anything else yields None rather than a guess.
    """
    end = len(data) - _INDEX_TRAILER.size
    if end < len(INDEX_TAG) + 12 or not data.startswith(INDEX_TAG):
        return None
    if _INDEX_TRAILER.unpack_from(data, end) != (ROW_BYTES, INDEX_VERSION):
        return None
    offset = len(INDEX_TAG)
    free_count = _U32.unpack_from(data, offset)[0]
    offset += 4 + 4 * free_count
    if offset + 4 > end:
        return None
    list_count = _U32.unpack_from(data, offset)[0]
    offset += 4
    offsets = array("Q")
    starts = array("Q", [0])
    empty: set[int] = set()
    for list_number in range(list_count):
        if offset + 4 > end:
            return None
        count = _U32.unpack_from(data, offset)[0]
        offset += 4
        if offset + 4 * count > end:
            return None
        previous = 0
        for value in struct.unpack_from(f"<{count}I", data, offset):
            offsets.append(DT_HEAD_BYTES + ((value + previous) & 0xFFFF_FFFF))
            previous = value
        offset += 4 * count
        starts.append(len(offsets))
        if count == 0:
            empty.add(list_number)
    if offset + 4 > end:
        return None
    empty_count = _U32.unpack_from(data, offset)[0]
    offset += 4
    if offset + 4 * empty_count != end:
        return None
    if set(struct.unpack_from(f"<{empty_count}I", data, offset)) != empty:
        return None
    return StatsHistoryIndex(offsets=offsets, starts=starts, free_count=free_count)


def find_stats_history_index(
    container_index: ContainerIndex, dt_length: int
) -> StatsHistoryIndex | None:
    """The span region's pool-index frame for a dt of `dt_length` bytes, or None.

    Only frame heads are read to pick the candidates (bodies opening with the index tag);
    each candidate is decompressed and must parse exactly and cover the dt's rows. None
    when no frame, or more than one, does.
    """
    found: list[StatsHistoryIndex] = []
    for span, head in region_frame_heads(container_index, SPAN_REGION, len(INDEX_TAG)):
        if head != INDEX_TAG:
            continue
        index = decode_stats_history_index(read_region_frame(container_index, SPAN_REGION, span))
        if index is not None and index_covers_dt(index, dt_length):
            found.append(index)
    return found[0] if len(found) == 1 else None


def index_covers_dt(index: StatsHistoryIndex, dt_length: int) -> bool:
    """Whether the index's rows plus free rows add up to the dt's row count, all on the grid."""
    rows, remainder = divmod(dt_length - DT_HEAD_BYTES, ROW_BYTES)
    if remainder or len(index.offsets) + index.free_count != rows:
        return False
    return all(
        (row_offset - DT_HEAD_BYTES) % ROW_BYTES == 0 and row_offset + ROW_BYTES <= dt_length
        for row_offset in index.offsets
    )


def player_list_numbers(
    game_db: bytes,
    record_offsets: Sequence[int],
    pindexes: Sequence[int],
    person_decoder: PersonBlockDecoder,
    window_start_offset: int,
    list_count: int,
) -> dict[int, int]:
    """Each player's history reference (pindex + 1) mapped to his stats-history list number.

    A player record's window runs from `record_offset + window_start_offset` to the next
    record's offset (the section end for the last). The list number is the u32 stored
    `LIST_NUMBER_BEFORE_BLOCK` bytes before the person block's start. A player with no
    person block, the 0xffffffff no-list value, or a number outside the index is left out,
    as is a number two players both claim.
    """
    found: dict[int, int] = {}
    claimed: dict[int, int] = {}
    order = sorted(range(len(record_offsets)), key=record_offsets.__getitem__)
    for position, record_index in enumerate(order):
        record_offset = record_offsets[record_index]
        window_end = (
            record_offsets[order[position + 1]] if position + 1 < len(order) else len(game_db)
        )
        block_start = person_decoder.block_start(
            game_db, record_offset + window_start_offset, window_end
        )
        if block_start is None or block_start < LIST_NUMBER_BEFORE_BLOCK:
            continue
        number = _U32.unpack_from(game_db, block_start - LIST_NUMBER_BEFORE_BLOCK)[0]
        if number == _NO_LIST or number >= list_count:
            continue
        reference = pindexes[record_index] + 1
        claimed[number] = claimed.get(number, 0) + 1
        found[reference] = number
    return {reference: number for reference, number in found.items() if claimed[number] == 1}


def history_person_list_numbers(
    candidates: Iterable[tuple[int, int | None]],
    index: StatsHistoryIndex,
    claimed_by_players: Collection[int],
) -> dict[int, int]:
    """Bind lists to people outside `players()`: reference mapped to list number.

    `candidates` pairs each person's history reference with the number his object stores
    (`HistoryPerson.stats_history_index`). A number binds when it is a non-empty list of the
    index, no current player claims it, and no other candidate stores it too.
    """
    found: dict[int, int] = {}
    claims: dict[int, int] = {}
    starts = index.starts
    for reference, number in candidates:
        if (
            number is None
            or number >= index.list_count
            or number in claimed_by_players
            or starts[number + 1] == starts[number]
        ):
            continue
        found[reference] = number
        claims[number] = claims.get(number, 0) + 1
    return {reference: number for reference, number in found.items() if claims[number] == 1}


def decode_player_rows(
    dt_data: bytes,
    index: StatsHistoryIndex,
    list_number: int,
    player_reference: int,
    *,
    goalkeeper: bool,
) -> tuple[PlayerHistoryStats, ...]:
    """One list's rows as `PlayerHistoryStats`, in stored (season) order.

    `goalkeeper` decides how the shared words read: as saves on a natural goalkeeper's rows
    and as the outfield statistics otherwise; the other set is None. The join fields
    (`player_uid`, `club_uid`) are left None for the caller to fill.
    """
    rows: list[PlayerHistoryStats] = []
    skip = _OUTFIELD_NAMES if goalkeeper else _GOALKEEPER_NAMES
    for list_position, row_offset in enumerate(index.rows_of(list_number)):
        team_id, competition_id, fee, season_year, rating_total = _HEAD.unpack_from(
            dt_data, row_offset
        )
        kind_code = dt_data[row_offset + _KIND_OFFSET]
        values: dict[str, Any] = {}
        for (name, field_offset, _, unit), reader in zip(_ALL_FIELDS, _ROW_STRUCTS, strict=True):
            if name in skip:
                values[name] = None
                continue
            raw = reader.unpack_from(dt_data, row_offset + field_offset)[0]
            values[name] = raw if unit == 1 else raw / unit
        rated = values["rated_appearances"]
        rows.append(
            PlayerHistoryStats(
                player_reference=player_reference,
                history_index=list_number,
                list_position=list_position,
                record_index=(row_offset - DT_HEAD_BYTES) // ROW_BYTES,
                season_year=season_year,
                team_id=None if team_id == _NO_TEAM else team_id,
                competition_id=None if competition_id == _NO_COMPETITION else competition_id,
                kind_code=kind_code,
                kind=_KINDS[kind_code] if kind_code < len(_KINDS) else None,
                departure_fee=None if fee == _NO_FEE else fee,
                spell_code=dt_data[row_offset + _SPELL_OFFSET],
                rating_total=rating_total,
                average_rating=rating_total / rated / 10 if rated else None,
                **values,
            )
        )
    return tuple(rows)
