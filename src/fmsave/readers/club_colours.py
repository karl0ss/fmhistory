"""Club colours and kits, from the second club blocks in `game_db`.

The blocks sit far past the club records, in club index order, and nothing points to them. A
kit list is recognised by its kits' fixed shape, the two club colours by the bytes after it,
and the club by its index at the head of the block, looked for before the list: see
`ClubColourLayout` for the shapes. The kit and colour bytes are found on their own; only the
link to a club rests on the walk, which is why it is counted.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Mapping

from fmsave._layouts import ClubColourLayout, find_layout
from fmsave._reader_stats import ClubColourStats
from fmsave.models.club_colours import ClubColours, Kit
from fmsave.readers._common import GAME_DB_SECTION

_UINT16 = struct.Struct("<H")
_UINT32 = struct.Struct("<I")
_DATE = struct.Struct("<HH")


def find_club_colour_layout(schema: int | None, build: str) -> ClubColourLayout:
    """Look up the club-colour layout for a `game_db` schema, falling back to the build."""
    return find_layout(ClubColourLayout, GAME_DB_SECTION, schema, build).layout


def _rgb555(value: int) -> str | None:
    if value == 0:
        return None
    red, green, blue = (value >> 10) & 31, (value >> 5) & 31, value & 31
    return f"#{red * 255 // 31:02X}{green * 255 // 31:02X}{blue * 255 // 31:02X}"


def _kit_pattern(layout: ClubColourLayout) -> re.Pattern[bytes]:
    gap = layout.kit_pair_offset - len(layout.kit_marker)
    return re.compile(
        re.escape(layout.kit_marker) + b".{%d}(.{4})\\1\x00\x00" % gap,
        re.DOTALL,
    )


def _is_kit(game_db: bytes, at: int, layout: ClubColourLayout) -> bool:
    pair_at = at + layout.kit_pair_offset
    zero_at = at + layout.kit_zero_offset
    return (
        game_db.startswith(layout.kit_marker, at)
        and game_db[pair_at : pair_at + 4] == game_db[pair_at + 4 : pair_at + 8]
        and game_db[zero_at : zero_at + 2] == b"\x00\x00"
    )


def find_kit_lists(game_db: bytes, layout: ClubColourLayout) -> list[tuple[int, int]]:
    """(first kit offset, kit count) of every kit list whose count byte matches its kits and
    whose club colours follow it, in file order."""
    size = layout.kit_bytes
    found: list[tuple[int, int]] = []
    for match in _kit_pattern(layout).finditer(game_db):
        start = match.start()
        if start < 1 or _is_kit(game_db, start - size, layout):
            continue  # not the list's first kit
        count = game_db[start - 1]
        end = start + size * count
        if not all(_is_kit(game_db, start + size * k, layout) for k in range(count)):
            continue
        if _is_kit(game_db, end, layout) or end + 8 > len(game_db):
            continue
        if game_db[end] != layout.colour_marker or game_db[end + 4] != layout.colour_marker:
            continue
        found.append((start, count))
    return found


def _block_head_at(game_db: bytes, at: int, layout: ClubColourLayout) -> bool:
    """Whether a club block opens at `at`: the count, the u32s, the flagged tail and dates."""
    count = game_db[at + layout.head_count_offset]
    if game_db[at + layout.head_zero_offset] != 0 or count > layout.head_count_maximum:
        return False
    flag_at = at + layout.head_values_offset + 4 * count
    if flag_at >= len(game_db) or game_db[flag_at] > 1:
        return False
    dates_at = flag_at + layout.tail_bytes[game_db[flag_at]]
    if dates_at + 12 > len(game_db):
        return False
    lowest, highest = layout.year_range
    return all(
        lowest <= _DATE.unpack_from(game_db, dates_at + 4 * k)[1] <= highest for k in range(3)
    )


def _nearest_head(
    game_db: bytes,
    after: int,
    before: int,
    last_index: int,
    window: int,
    club_indexes: set[int],
    layout: ClubColourLayout,
) -> tuple[int, int] | None:
    """(offset, index) of the head nearest `before` for one of the `window` indexes after
    `last_index`, searching `[after, before)`."""
    best: tuple[int, int] | None = None
    for index in range(last_index + 1, last_index + window + 1):
        if index not in club_indexes:
            continue
        needle = _UINT32.pack(index)
        at = game_db.rfind(needle, after, before)
        while at >= 0 and not _block_head_at(game_db, at, layout):
            at = game_db.rfind(needle, after, at)
        if at >= 0 and (best is None or at > best[0]):
            best = (at, index)
    return best


def _place_lists(
    game_db: bytes,
    lists: list[tuple[int, int]],
    club_indexes: set[int],
    layout: ClubColourLayout,
) -> list[tuple[int, int]]:
    """(list number, club index) for each list the walk places, in list order."""
    placed: list[tuple[int, int]] = []
    last_index = 0
    previous_end = 0
    for number, (start, count) in enumerate(lists):
        best = _nearest_head(
            game_db, previous_end, start, last_index, layout.index_window, club_indexes, layout
        )
        if best is None:
            best = _nearest_head(
                game_db,
                previous_end,
                start,
                last_index,
                layout.wide_index_window,
                club_indexes,
                layout,
            )
        if best is not None:
            last_index = best[1]
            placed.append((number, best[1]))
        previous_end = start + layout.kit_bytes * count
    return placed


def _kits(game_db: bytes, start: int, count: int, layout: ClubColourLayout) -> tuple[Kit, ...]:
    kits: list[Kit] = []
    for k in range(count):
        at = start + layout.kit_bytes * k
        colours = tuple(
            _rgb555(_UINT16.unpack_from(game_db, at + layout.kit_colours_offset + 2 * c)[0])
            for c in range(5)
        )
        pattern_at = at + layout.kit_colours_offset + 10
        kits.append(
            Kit(
                kit_set=game_db[at + layout.kit_zero_offset + 2],
                part=game_db[at + layout.kit_zero_offset + 3],
                colours=colours,
                pattern=game_db[pattern_at],
            )
        )
    return tuple(kits)


def _colour(game_db: bytes, at: int) -> str:
    red, green, blue = game_db[at + 1 : at + 4]
    return f"#{red:02X}{green:02X}{blue:02X}"


def read_club_colours(
    game_db: bytes,
    uid_by_club_index: Mapping[int, int],
    name_by_uid: Mapping[int, str],
    layout: ClubColourLayout,
) -> tuple[list[ClubColours], ClubColourStats]:
    """Every club the walk places, with its two colours and kits, in club index order."""
    lists = find_kit_lists(game_db, layout)
    placed = _place_lists(game_db, lists, set(uid_by_club_index), layout)
    rows: list[ClubColours] = []
    for number, index in placed:
        start, count = lists[number]
        end = start + layout.kit_bytes * count
        uid = uid_by_club_index[index]
        rows.append(
            ClubColours(
                club_uid=uid,
                club_name=name_by_uid[uid],
                first_colour=_colour(game_db, end),
                second_colour=_colour(game_db, end + 4),
                kits=_kits(game_db, start, count, layout),
            )
        )
    stats = ClubColourStats(kit_lists=len(lists), placed=len(placed), clubs=len(uid_by_club_index))
    return rows, stats
