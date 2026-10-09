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
  a node or type id, not a person id. The manager's honours sit after their block:

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
  records, most likely — parse in a way the filler between them also satisfies,
  so they are kept out.

Competition ids in the career-history sections are save-internal ids, and no save stores a
competition name, so none of these records carries a name; naming needs the same
editor-database-id map the competition reader uses.
"""

from __future__ import annotations

import re
import struct

from fmsave._errors import CorruptSaveError
from fmsave.models.career_history import Award, CupEntry, Honour, ManagerSpell, PersonHistory

HALL_OF_FAME_SECTION = "hall_of_fame"
CUP_HISTORY_SECTION = "tc_cup_history_dt"
MANAGER_HISTORY_SECTION = "tc_manager_history_dt"
AWARD_SECTION = "award_year_hist_dt"

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
        if _MIN_CUP_SEASON <= start_season <= _MAX_YEAR and start_season <= end_season <= start_season + 2:
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


_AWARD_LEAD_BYTE = 2
_AWARD_FLAG_MAX = 0x4081
_AWARD_ID_MAX = 4700
_AWARD_HEAD_BYTES = 30
_AWARD_NO_CLUB_BYTES = 26
_AWARD_TAIL_BYTES = 11
_AGE_MIN = 13
_AGE_MAX = 95
_AWARD_REFERENCE_MAX = 2_500_000


def _award_head(row: bytes) -> Award | None:
    """The award record a 30-byte headed row holds, or None when the bytes fail it.

    A row runs `[02][u32 flags][u16 tag][u16 year][u16 award][u32 winner][u32 club]`
    plus the 11-byte trailing block. The checks are the sanity bounds the scan can
    hold a row to: small flags, a real year, a small award id, references below the
    unset value the placeholders carry, and an age byte in human range.
    """
    if len(row) < _AWARD_HEAD_BYTES or row[0] != _AWARD_LEAD_BYTE:
        return None
    flags = int.from_bytes(row[1:5], "little")
    if flags > _AWARD_FLAG_MAX:
        return None
    tag, season_year, award_id, winner_id, club_uid = struct.unpack_from("<HHHII", row, 5)
    age = row[19]
    if not (_MIN_YEAR <= season_year <= _MAX_YEAR and season_year != _NULL_YEAR):
        return None
    if award_id > _AWARD_ID_MAX or winner_id >= _AWARD_REFERENCE_MAX:
        return None
    if club_uid >= _AWARD_REFERENCE_MAX or not _AGE_MIN <= age <= _AGE_MAX:
        return None
    return Award(
        season_year=season_year,
        award_id=award_id,
        tag=tag,
        winner_id=winner_id,
        club_uid=club_uid,
        winner_age=age,
        tail=tuple(row[19 : 19 + _AWARD_TAIL_BYTES]),
    )


def _award_head_without_club(row: bytes) -> Award | None:
    """The award record a 26-byte headed row holds, the shape the club-history records carry.

    Some records — club-winner history rows and person winners (player awards)
    alike — name their winner in a
    u32 and then stop: `[02][u32 flags][u16 tag][u16 year][u16 award][u32 winner]`
    plus the trailing block, 26 bytes. The scan reads this shape only when the 30-byte
    shape fails, since the two agree on every byte the shorter one holds: under the
    longer shape the club field is the shorter record's first trailing bytes and the
    age byte sits four bytes on, so a sparse trailing block — zeros around an age, the
    shape the section's records carry — fails the longer shape and this one takes it.
    """
    if len(row) < _AWARD_NO_CLUB_BYTES or row[0] != _AWARD_LEAD_BYTE:
        return None
    flags = int.from_bytes(row[1:5], "little")
    if flags > _AWARD_FLAG_MAX:
        return None
    tag, season_year, award_id, winner_id = struct.unpack_from("<HHHI", row, 5)
    age = row[15]
    if not (_MIN_YEAR <= season_year <= _MAX_YEAR and season_year != _NULL_YEAR):
        return None
    if award_id > _AWARD_ID_MAX or winner_id >= _AWARD_REFERENCE_MAX:
        return None
    if not _AGE_MIN <= age <= _AGE_MAX:
        return None
    return Award(
        season_year=season_year,
        award_id=award_id,
        tag=tag,
        winner_id=winner_id,
        club_uid=None,
        winner_age=age,
        tail=tuple(row[15 : 15 + _AWARD_TAIL_BYTES]),
    )


def decode_awards(data: bytes) -> tuple[Award, ...]:
    """Every award row in the yearly award section that carries a season and award head.

    The section streams 26- and 30-byte records against each other, placeholders
    between them. The scan walks forward one byte at a time and takes the first
    shape that passes its checks at each position — the 30-byte shape, then the
    26-byte one that a record whose winner is a club itself carries — and a
    placeholder or other unmatched record is walked past, not parsed. This reads
    the records the (year, award) head identifies; the section's head-less records
    (its monthly-award records, most likely) are left for a later pass, because the
    checks that separate them from their filler do not hold yet.

    An award row's season year is the season's ending year, and `winner_age` is the
    winner's age on person-winner rows; both are confirmed on the ground-truth
    save's manager rows, where the six rows carry the biography's named awards with
    ages matching the manager's birth year.
    """
    awards: list[Award] = []
    seen: set[tuple[int, int, int, int, int]] = set()
    position = 0
    limit = len(data) - _AWARD_NO_CLUB_BYTES
    while position <= limit:
        record = _award_head(data[position : position + _AWARD_HEAD_BYTES])
        if record is None:
            record = _award_head_without_club(
                data[position : position + _AWARD_NO_CLUB_BYTES]
            )
        if record is not None:
            key = (
                record.season_year,
                record.award_id,
                record.winner_id,
                record.club_uid if record.club_uid is not None else -1,
                record.winner_age,
            )
            if key not in seen:
                seen.add(key)
                awards.append(record)
            position += (
                _AWARD_HEAD_BYTES if record.club_uid is not None else _AWARD_NO_CLUB_BYTES
            )
            continue
        position += 1
    return tuple(awards)