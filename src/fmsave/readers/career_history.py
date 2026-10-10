"""Decoding the career-history sections the other readers do not parse yet.

Three history sections have layouts reverse-engineered so far, each on one save
(`Karl Hudgell - UnemployedNew.fm`, build 26.3.2) whose ground truth is the real
career the save carries. None is a layout-walk like the older readers run: every
decoder here is a pattern scan over the section's bytes, and may miss entries the
pattern does not cover. They also read no names or uids beyond what the section
itself stores, and they never write a save.

What each section holds:

- `hall_of_fame` — person records with both names stored inline, and honours rows
  underneath them. The person block is

      [01|00] <u32 length "first"> <u32 length "last"> 00 00 00 00
      u16 dob_day_of_year  u16 birth_year  u32 shared  u32 person_uid  01
      u32 765 (`fd 02 00 00`) 04 03 03 00

  where 765 is a section-wide constant that also opens every honours row, so it is
  a section-wide node or type id, not a person id. The manager's honours sit after
  their block:

      <u32 club> 01 00 <u32 competition> fd 02 00 00 02 00
      u16 count 01 <01|04> 00 u16 count2 u16 season 03 03 00

  The scan anchors on the `fd 02 00 00` constant: at its start it expects the
  person block's fields walked backwards, and in a honours row it expects
  `02 00` in front and the season two bytes after the row's count.

- `tc_cup_history_dt` — a flat array of 18-byte rows after the 4-byte tag header,
  `[u32 club][u32 competition][u16 start_season][u16 end_season] 02 01 ff ff ff 00`,
  one per club cup campaign per stage. Every row decoded has the two seasons one
  year apart; that identity is the scan's own check.

- `tc_manager_history_dt` — one record per manager in the game world (the header
  count is the record count, and a little over 8,000 on the ground-truth save),
  whose internals are a record family not fully mapped. What is mapped is the
  spell-start row: `<u32 club> u16 day u16 season u16 u16 same-season ff ff ff ff
  ff ff ff ff`, the shape a spell whose end dates are unset carries. Spells that
  have ended store their end dates in a shape not decoded yet, so the spell table
  covers only open spells. Person references in this section are not the
  person uids the hall of fame stores, so rows cannot be tied to one manager yet;
  they are keyed by club.

- `award_year_hist_dt` — award rows across the game world, streamed as 26-byte
  and 30-byte records that sit directly against each other, with placeholder
  records (tags and winners unset) filling the slots between:

      [02] [u32 flags] [u16 tag] [u16 year] [u16 award] [u32 winner] [u32 club]
      [u8 age] [u16] [u16] [u16] [u16] [u8]           30 bytes with a club field

  The club field is absent on some records — club-winner rows and person winners
  (player awards) alike — which makes those records 26 bytes. The flags word holds small flag values (0x1, 0x40, 0x400,
  0x4000 seen), the tag word 0xffff on most rows with a run of category values on
  the rest, and the trailing block's first byte is the winner's age on
  person-winner rows. Records without the year/award head — the monthly-award
  rows, most likely, whose ages run a real player age curve — carry no season
  year, so they cannot sit in a year-keyed table and are left for a later pass.

- `tc_league_history_dt` — past league tables as butted 24-byte rows on an offset
  grid (`offset % 24 == 8`), one row per club per table per season:

      [u16 season][u16 competition][u8 position][u8 team count]
      u16 zero  u32 team reference
      u8 games u8 games-again u8 wins u8 draws u8 losses u8 zero
      u16 goals_for  u16 goals_against  u16 points

  A row carries no club identity (a post-import row's team reference is unset);
  `tc_league_history_ls` holds one delta-encoded list of row offsets per club, and
  the decoder stamps each row with its list number (`history_index`). The season
  is the season's ending year.

Competition ids in the career-history sections are save-internal ids, and no save stores a
competition name, so none of these records carries a name; naming needs the same
editor-database-id map the competition reader uses.
"""

from __future__ import annotations

import re
import struct
from collections import Counter
from collections.abc import Mapping, Sequence

from fmsave._errors import CorruptSaveError
from fmsave.models.career_history import (
    Award,
    CupEntry,
    Honour,
    LeagueHistorySeason,
    ManagerSpell,
    PersonHistory,
)

HALL_OF_FAME_SECTION = "hall_of_fame"
CUP_HISTORY_SECTION = "tc_cup_history_dt"
MANAGER_HISTORY_SECTION = "tc_manager_history_dt"
AWARD_SECTION = "award_year_hist_dt"
LEAGUE_HISTORY_DT_SECTION = "tc_league_history_dt"
LEAGUE_HISTORY_LS_SECTION = "tc_league_history_ls"

# The section-wide node id every honours row and most person record tails carry (u32 765).
_HONOURS_NODE = b"\xfd\x02\x00\x00"

_MIN_PERSON_UID = 1_000
_MIN_YEAR = 1850
_MAX_YEAR = 2050
# The year a null date carries, and the club value a row without a club carries.
_NULL_YEAR = 1900
_NO_CLUB = 0xFFFF_FFFF


def decode_hall_of_fame(data: bytes) -> tuple[tuple[PersonHistory, ...], tuple[Honour, ...]]:
    """Every person record and honours row the hall of fame stores, in file order.

    The persons come from `decode_persons`, the honours from `decode_honour_rows`; both
    are pattern scans, so a record whose shape a changed build does not cover is missed
    rather than misread.
    """
    return decode_persons(data), decode_honour_rows(data)


def decode_honour_rows(data: bytes) -> tuple[Honour, ...]:
    """Every honours row in the hall of fame bytes, whether or not a person block is near.

    A row runs `<u32 club> 01 00 <u32 competition> fd 02 00 00 02 00 <u16 count> 01
    01 00 <u16> <u16 season>`, its season thirteen bytes past its node id. What follows
    the season is not one tail the way a strict layout would have it — rows carry
    different bytes there — so the scan stops at the season and keeps a candidate whose
    club and season pass their bounds; the 1900 the history sections use as a null date
    is not kept. A candidate whose club, season or tail fail is not a row.
    """
    honours: list[Honour] = []
    seen: set[tuple[int, int, int]] = set()
    for match in re.finditer(b"\xfd\x02\x00\x00\x02\x00", data):
        anchor = match.start()
        if anchor < 10 or anchor + 15 > len(data):
            continue
        if data[anchor - 6 : anchor - 4] != b"\x01\x00":
            continue
        club = struct.unpack_from("<I", data, anchor - 10)[0]
        if club in (0, _NO_CLUB):
            continue
        competition = struct.unpack_from("<I", data, anchor - 4)[0]
        count = struct.unpack_from("<H", data, anchor + 6)[0]
        season = struct.unpack_from("<H", data, anchor + 13)[0]
        if not (_MIN_YEAR <= season <= _MAX_YEAR and season != _NULL_YEAR):
            continue
        key = (club, competition, season)
        if key in seen:
            continue
        seen.add(key)
        honours.append(
            Honour(
                club_uid=club,
                competition_id=competition,
                season=season,
                count=count,
            )
        )
    return tuple(honours)


def decode_persons(data: bytes) -> tuple[PersonHistory, ...]:
    """Every person record the hall of fame stores, in file order.

    A person record is names written inline, both u32-length-prefixed, followed by
    four zero bytes, the birth date (a day-of-year u16 and a year u16), a shared u32
    that is not always a person id and can be unset, and a person uid. The scan walks
    forward from every `(flag, first length)` pair that a record's start could sit at,
    and keeps a candidate whose fields all pass their sanity bounds: names that
    decode, a birth date in range, and a uid above the small ids the records that
    carry unset references use instead. Two records for one person are possible: an
    import from an older FM save keeps one record per source record.
    """

    def u32(offset: int) -> int:
        return int.from_bytes(data[offset : offset + 4], "little")

    persons_by_uid: dict[tuple[str, str, int, int], PersonHistory] = {}
    last = len(data) - 40
    position = 0
    while position < last:
        if data[position] not in (0, 1):
            position += 1
            continue
        first_length = u32(position + 1)
        if not 2 <= first_length <= 32:
            position += 1
            continue
        last_length_offset = position + 5 + first_length
        last_length = u32(last_length_offset)
        if not 2 <= last_length <= 32:
            position += 1
            continue
        tail_offset = last_length_offset + 4 + last_length
        if tail_offset + 16 > len(data):
            break
        # The four zero bytes at tail_offset separate the names from the record's fields,
        # so read past them; an unpack past the section end ends the scan.
        dob, birth_year, _, person_uid = struct.unpack_from("<HHII", data, tail_offset + 4)
        if not (0 < dob <= 366 and _MIN_YEAR <= birth_year <= _MAX_YEAR):
            position += 1
            continue
        if not (_MIN_PERSON_UID <= person_uid <= 0x7FFF_FFFF):
            position += 1
            continue
        try:
            first = data[position + 5 : last_length_offset].decode()
            name_last = data[tail_offset - last_length : tail_offset].decode()
        except UnicodeDecodeError:
            position += 1
            continue
        if not (first.isprintable() and name_last.isprintable()):
            position += 1
            continue
        person = PersonHistory(
            first_name=first,
            last_name=name_last,
            dob_day_of_year=dob,
            birth_year=birth_year,
            person_uid=person_uid,
        )
        key = (first, name_last, dob, person_uid)
        if key not in persons_by_uid:
            persons_by_uid[key] = person
        position = tail_offset + 16
    return tuple(persons_by_uid.values())


_CUP_ROW_BYTES = 18
_MIN_CUP_SEASON = _MIN_YEAR
_VALID_ROWS_NEEDED = 0.99


def decode_cup_entries(data: bytes) -> tuple[CupEntry, ...]:
    """Every cup history row the section stores, as a `CupEntry`.

    The section is one flat 18-byte row array from just after the tag header. A row's
    seasons are a span: the end season is usually the start season plus one, but same-
    year rows exist and a few spans cover two years, so the check accepts any end up to
    two past the start. Rows exist that carry the club sentinel 0xffffffff, which is a
    competition-without-club record, not one club's entry. A section where fewer than
    99 rows in 100 pass the span test is not read at all: the row layout has moved and
    none of the rows can be trusted.
    """
    rows: list[tuple[int, int, int, int]] = []
    valid = 0
    for row_offset in range(4, len(data) - _CUP_ROW_BYTES + 1, _CUP_ROW_BYTES):
        club, competition, start_season, end_season = struct.unpack_from("<IIHH", data, row_offset)
        rows.append((club, competition, start_season, end_season))
        if (
            _MIN_CUP_SEASON <= start_season <= _MAX_YEAR
            and start_season <= end_season <= start_season + 2
        ):
            valid += 1
    if len(rows) < 10 or valid < len(rows) * _VALID_ROWS_NEEDED:
        raise CorruptSaveError(
            f"tc_cup_history_dt does not hold the 18-byte row layout "
            f"({valid} of {len(rows)} rows pass it)"
        )
    return tuple(
        CupEntry(
            club_uid=club,
            competition_id=competition,
            start_season=start_season,
            end_season=end_season,
        )
        for club, competition, start_season, end_season in rows
    )


def decode_awards(data: bytes) -> tuple[Award, ...]:
    """Every award row in the yearly award section that carries a season and award head.

    The section streams 26- and 30-byte records against each other, placeholders
    between them. The scan walks forward one byte at a time and takes the first
    shape that passes its checks at each position — the 30-byte shape, then the
    26-byte one that a record whose winner is a club itself carries — and a
    placeholder or other unmatched record is walked past, not parsed. This reads
    the records the (year, award) head identifies. The section also holds head-less
    records — the monthly-award rows, most likely, and their ages run a real player
    age curve — but they carry no season year, so they cannot sit in a year-keyed
    table and are left for a later pass.

    An award row's season year is the season's ending year, and `winner_age` is the
    winner's age on person-winner rows; both are confirmed on the ground-truth
    save's manager rows, where the six rows carry the biography's named awards with
    ages matching the manager's birth year.
    """
    awards: list[Award] = []
    seen: set[tuple[int, int, int, int, int | None, int]] = set()
    position = 0
    limit = len(data) - 26  # _AWARD_NO_CLUB_BYTES
    while position <= limit:
        # Try 30-byte header first
        if position + 30 <= len(data):
            record = data[position : position + 30]
            if record[0] == 2:  # _AWARD_LEAD_BYTE
                flags = int.from_bytes(record[1:5], "little")
                if flags <= 0x4081:  # _AWARD_FLAG_MAX
                    tag, season_year, award_id, winner_id, club_uid = struct.unpack_from(
                        "<HHHII", record, 5
                    )
                    age = record[19]
                    if (
                        _MIN_YEAR <= season_year <= _MAX_YEAR
                        and season_year != _NULL_YEAR
                        and award_id <= 4700  # _AWARD_ID_MAX
                        and winner_id < 2_500_000  # _AWARD_REFERENCE_MAX
                        and (club_uid == 0xFFFF_FFFF or club_uid < 2_500_000)
                        and 13 <= age <= 95
                    ):  # _AGE_MIN, _AGE_MAX
                        tail = tuple(record[19:30])
                        key = (
                            season_year,
                            award_id,
                            tag,
                            winner_id,
                            club_uid if club_uid != 0xFFFF_FFFF else None,
                            age,
                        )
                        if key not in seen:
                            seen.add(key)
                            awards.append(
                                Award(
                                    season_year=season_year,
                                    award_id=award_id,
                                    tag=tag,
                                    winner_id=winner_id,
                                    club_uid=club_uid if club_uid != 0xFFFF_FFFF else None,
                                    winner_age=age,
                                    tail=tail,
                                )
                            )
                        position += 30
                        continue
        # Try 26-byte header (no club field)
        if position + 26 <= len(data):
            record = data[position : position + 26]
            if record[0] == 2:  # _AWARD_LEAD_BYTE
                flags = int.from_bytes(record[1:5], "little")
                if flags <= 0x4081:  # _AWARD_FLAG_MAX
                    tag, season_year, award_id, winner_id = struct.unpack_from("<HHHI", record, 5)
                    age = record[15]
                    if (
                        _MIN_YEAR <= season_year <= _MAX_YEAR
                        and season_year != _NULL_YEAR
                        and award_id <= 4700  # _AWARD_ID_MAX
                        and winner_id < 2_500_000  # _AWARD_REFERENCE_MAX
                        and 13 <= age <= 95
                    ):  # _AGE_MIN, _AGE_MAX
                        tail = tuple(record[15:26])
                        key = (
                            season_year,
                            award_id,
                            tag,
                            winner_id,
                            -1,  # club_uid as -1 for None
                            age,
                        )
                        if key not in seen:
                            seen.add(key)
                            awards.append(
                                Award(
                                    season_year=season_year,
                                    award_id=award_id,
                                    tag=tag,
                                    winner_id=winner_id,
                                    club_uid=None,
                                    winner_age=age,
                                    tail=tail,
                                )
                            )
                        position += 26
                        continue
        position += 1
    return tuple(awards)


_SPELL_SENTINELS = b"\xff" * 8


def decode_manager_spells(data: bytes) -> tuple[ManagerSpell, ...]:
    """Every spell-start row in the manager history section that the scan accepts.

    The section is one record per manager, whose interiors hold a family of record
    shapes of which only the spell-start row is decoded: `<u32 club> u16 day u16
    season u16 u16 same-season` followed by eight unset bytes, which is the shape a
    spell still open carries. Rows for ended spells and every other shape are left
    out, so the table does not cover a manager's whole record; a club whose spells
    are all absent is expected, and so is more than one row for one spell as the
    record family grows.
    """
    spells: list[ManagerSpell] = []
    seen: set[tuple[int, int, int]] = set()
    for offset in range(len(data) - 20):
        club, day, season, _, season_again = struct.unpack_from("<IHHHH", data, offset)
        if not (1 <= club <= 5_000_000 and day <= 366 and _MIN_YEAR <= season <= _MAX_YEAR):
            continue
        if season_again != season or data[offset + 12 : offset + 20] != _SPELL_SENTINELS:
            continue
        key = (club, day, season)
        if key in seen:
            continue
        seen.add(key)
        spells.append(ManagerSpell(club_uid=club, start_day=day, start_year=season))
    return tuple(spells)


# League history: the dt rows, threaded to clubs through the ls index

# The ls index opens with the shared `tad.` tag (03 01 'tad.' + u16 version), a zero
# word and the list count, and closes with a 10-byte trailer (u32 0, u32 dt record
# size, u16 dt header version).
_LS_TAG = b"\x03\x01tad."
_LS_HEAD = 16
_LS_TRAILER = 10
_LEAGUE_ROW = 24
_LEAGUE_DT_HEAD = 8
# The games byte of a table that was never played.
_UNPLAYED = 0xFF


def _is_valid_league_history_row(dt_data: bytes, offset: int) -> bool:
    """Whether the 24 bytes at a grid offset read as a league-history row.

    A row sits at an offset congruent to 8 modulo 24, its season is a real year, its
    position fits inside its table, the table has a plausible size, and the row is
    not one whose whole results block is unset. Rows whose results are zeroed but
    whose played-games byte is unset (a table that was never played) still pass: they
    are part of the section, and separating them is the caller's job.
    """
    if offset + _LEAGUE_ROW > len(dt_data) or offset % _LEAGUE_ROW != _LEAGUE_DT_HEAD:
        return False
    season = struct.unpack_from("<H", dt_data, offset)[0]
    pos = dt_data[offset + 4]
    size = dt_data[offset + 5]
    if not (1900 <= season <= 2100) or pos >= size or not (2 <= size <= 100):
        return False
    w, d, l = dt_data[offset + 14 : offset + 17]
    return not (w == 255 and d == 255 and l == 255)


def _decode_league_history_row(
    dt_data: bytes, offset: int, history_index: int | None
) -> LeagueHistorySeason:
    """Decode the league-history row at a grid offset."""
    season, comp, pos, size = struct.unpack_from("<HHBB", dt_data, offset)
    goals_for, goals_against, points = struct.unpack_from("<3H", dt_data, offset + 18)
    return LeagueHistorySeason(
        season_year=season,
        competition_id=comp,
        position=pos,
        total_teams=size,
        games_played=dt_data[offset + 12],
        wins=dt_data[offset + 14],
        draws=dt_data[offset + 15],
        losses=dt_data[offset + 16],
        goals_for=goals_for,
        goals_against=goals_against,
        points=points,
        imported=dt_data[offset + 13] == 0 and dt_data[offset + 12] != _UNPLAYED,
        history_index=history_index,
    )


def decode_league_history_lists(ls_data: bytes) -> tuple[tuple[int, ...], ...]:
    """The dt row offsets of every club-history list in `tc_league_history_ls`.

    The index holds one list per club with league history: a u32 count, then that
    many u32 values. The values are delta-encoded: the m-th row sits at
    `value[m] + value[m - 1]` bytes past the dt section's 8-byte header (the first
    at `value[0]`), so each decoded list is one club's rows in season order. On the
    ground-truth save every dt row belongs to exactly one list. The offsets returned
    are absolute dt offsets, ready for `decode_league_history`'s grid.

    An index that does not parse exactly (wrong tag, a count running past the end,
    or bytes left over beyond the trailer) yields no lists rather than a guess.
    """
    if len(ls_data) < _LS_HEAD + _LS_TRAILER or not ls_data.startswith(_LS_TAG):
        return ()
    list_count = struct.unpack_from("<I", ls_data, 12)[0]
    end = len(ls_data) - _LS_TRAILER
    offset = _LS_HEAD
    lists: list[tuple[int, ...]] = []
    for _ in range(list_count):
        if offset + 4 > end:
            return ()
        count = struct.unpack_from("<I", ls_data, offset)[0]
        offset += 4
        if offset + 4 * count > end:
            return ()
        values = struct.unpack_from(f"<{count}I", ls_data, offset)
        offset += 4 * count
        rows: list[int] = []
        previous = 0
        for value in values:
            rows.append(_LEAGUE_DT_HEAD + ((value + previous) & 0xFFFF_FFFF))
            previous = value
        lists.append(tuple(rows))
    if offset != end:
        return ()
    return tuple(lists)


def decode_league_history(dt_data: bytes, ls_data: bytes) -> tuple[LeagueHistorySeason, ...]:
    """Every readable past league-table row the dt section stores, in file order.

    The dt section holds past league tables as butted 24-byte rows on an offset grid
    (`offset % 24 == 8`); the walk stops at every grid offset and keeps the rows that
    pass the row check. Rows carry no club identity themselves: the ls index ties
    each row to one club-history list, whose number becomes the row's
    `history_index` (None when the index does not parse or does not cover the row).
    List numbers run in club uid order among clubs that have league history, with
    clubs whose first league season came after an imported career appended at the
    end; which uid a number belongs to is not stored in either section.

    Returns:
        One `LeagueHistorySeason` per readable row, in file order.
    """
    owner: dict[int, int] = {}
    for index, offsets in enumerate(decode_league_history_lists(ls_data)):
        for row_offset in offsets:
            owner[row_offset] = index
    return tuple(
        _decode_league_history_row(dt_data, offset, owner.get(offset))
        for offset in range(_LEAGUE_DT_HEAD, len(dt_data) - _LEAGUE_ROW + 1, _LEAGUE_ROW)
        if _is_valid_league_history_row(dt_data, offset)
    )


def resolve_league_history_indexes(
    seasons: Sequence[LeagueHistorySeason],
    honours: Sequence[Honour],
    competition_by_database_id: Mapping[int, int],
) -> dict[int, int]:
    """The league-history list number of every club a league title pins down.

    An honours row names its competition by editor database id, so it first maps to
    the save-internal id the league rows use. A league title then has exactly one
    first-place row for that season and competition among the rows the save itself
    wrote (imported rows can repeat a table, so they are left out); that row's list is
    the club's. A club is resolved only when every title it has that matches such a
    row names the same list, and a list claimed by two clubs is dropped for both, so
    clubs without a post-import league title stay unresolved rather than guessed.

    Returns:
        Club uid to list number, for the clubs the titles pin down.
    """
    champions: dict[tuple[int, int], set[int]] = {}
    for season in seasons:
        if season.position == 0 and season.history_index is not None and not season.imported:
            key = (season.season_year, season.competition_id)
            champions.setdefault(key, set()).add(season.history_index)
    claims: dict[int, set[int]] = {}
    for honour in honours:
        competition_id = competition_by_database_id.get(honour.competition_id)
        if competition_id is None:
            continue
        owners = champions.get((honour.season, competition_id), set())
        if len(owners) == 1:
            claims.setdefault(honour.club_uid, set()).update(owners)
    resolved = {club: next(iter(lists)) for club, lists in claims.items() if len(lists) == 1}
    holders = Counter(resolved.values())
    return {club: index for club, index in resolved.items() if holders[index] == 1}
