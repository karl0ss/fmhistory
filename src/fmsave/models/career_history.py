"""Career history records read from the save's history sections.

These come from the `hall_of_fame`, `tc_cup_history_dt` and `tc_manager_history_dt`
sections, whose binary layout fmsave's older readers do not parse. Their layouts were
reverse-engineered on one save (`Karl Hudgell - UnemployedNew.fm`, build 26.3.2,
FM24 save imported into FM26) and are not yet verified across builds, so every field
is unconfirmed. The decoders are pattern scans, not layout-walks: a field is read
from the bytes a record shows around itself, and the scans may miss entries the
pattern does not cover.

The competition ids these records carry are save-internal ids in the stage id space
(the ids `competitions()` stores) except on import-created competitions, and no save
stores a competition name, so see the reader module's notes on naming.

Every date here is the (day-of-season, season-year) pair the history sections store:
the day counts within a season that starts around 1 July, and 1900 marks a null date
elsewhere in these sections (never in a row we accept).
"""

from __future__ import annotations

from dataclasses import dataclass

from fmsave._status import register_field_statuses


@dataclass(frozen=True, slots=True)
class PersonHistory:
    """A person record the hall of fame keeps, with both names written inline.

    The hall of fame stores historical hall entries for many people across the game
    world; a person who played their career inside the save's own history appears the
    same way. `person_uid` is a save-internal person uid, not the `Staff.uid` or
    `Player.uid` the older tables store: on the ground-truth save the human manager's
    hall-of-fame uid is their staff uid plus one (the same plus-one encoding other
    readers know). Import from an older FM save left one person per source record, so
    one real person can hold two records.

    Attributes:
        first_name: The person's first name, stored inline (unconfirmed).
        last_name: The person's last name, stored inline (unconfirmed).
        dob_day_of_year: Day of year of the person's date of birth, 1..366 (unconfirmed).
        birth_year: The person's year of birth (unconfirmed).
        person_uid: Save-internal person uid; joins to nothing fmsave reads yet (unconfirmed).
    """

    first_name: str
    last_name: str
    dob_day_of_year: int
    birth_year: int
    person_uid: int


@dataclass(frozen=True, slots=True)
class Honour:
    """One competition won by one club, as the hall of fame records it.

    Rows are per person honour, and a club's rows group under the club uid that
    precedes the row. The season is the year the honour was won; a cup spanning two
    calendar years is recorded once under its final year. `count` is an increasing
    per-club counter the rows carry whose meaning is unconfirmed (possibly a running
    honours index). `competition_id` is a save-internal competition id; on the
    ground-truth save it matches ids in the id ranges `competitions()` reads for
    rebuilt competitions (Vanarama and FA Trophy ids) but not always an id that table
    exposes, so it joins to nothing reliably yet.

    Attributes:
        club_uid: Uid of the club that won the competition (unconfirmed).
        competition_id: Save-internal competition id the honour was won in (unconfirmed).
        season: Season-ending year the honour was won, e.g. 2029 for 2028/29 (unconfirmed).
        count: Per-row counter the section stores, meaning unconfirmed (unconfirmed).
    """

    club_uid: int
    competition_id: int
    season: int
    count: int


@dataclass(frozen=True, slots=True)
class CupEntry:
    """One cup-history row: a (club, competition, season span) record.

    The section is a flat array of 18-byte rows, one per club cup campaign where the
    club is set; a club's cup run can hold several rows per season (per stage). A row
    with the club sentinel 0xffffffff is a competition record without a club. A span
    usually covers one season (`end_season` = `start_season` plus one), but same-year
    rows exist and a few spans cover two years, so nothing narrower is claimed.

    Attributes:
        club_uid: Uid of the club the row's campaign is for; 0xffffffff for a
            competition record without a club (unconfirmed).
        competition_id: Save-internal cup competition id (unconfirmed).
        start_season: Season-ending year the span starts on (unconfirmed).
        end_season: Season-ending year the span ends on; usually `start_season` plus
            one (unconfirmed).
    """

    club_uid: int
    competition_id: int
    start_season: int
    end_season: int


@dataclass(frozen=True, slots=True)
class ManagerSpell:
    """A spell a manager holds at a club, from the manager history section.

    The section stores one record per manager in the game world; inside some of those
    records sits a spell row naming the club, the day the spell began and its season
    year. The scan only finds spell rows in the still-open shape, whose end date is
    two unset u32s: spells that have ended are stored in a shape not decoded yet, so
    the table covers only open spells and misses everything older. On a career with
    clubs found, the row for the human manager's club carries their join date.

    Attributes:
        club_uid: Uid of the club the spell is at (unconfirmed).
        start_day: Day-of-season the spell began; 182 is early July on the
            ground-truth save (unconfirmed).
        start_year: Season year the spell began (unconfirmed).
    """

    club_uid: int
    start_day: int
    start_year: int


register_field_statuses(
    PersonHistory,
    unconfirmed=("first_name", "last_name", "dob_day_of_year", "birth_year", "person_uid"),
)
register_field_statuses(
    Honour,
    unconfirmed=("club_uid", "competition_id", "season", "count"),
)
register_field_statuses(
    CupEntry,
    unconfirmed=("club_uid", "competition_id", "start_season", "end_season"),
)
register_field_statuses(
    ManagerSpell,
    unconfirmed=("club_uid", "start_day", "start_year"),
)