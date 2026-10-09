"""Career history records read from the save's history sections.

These come from the `hall_of_fame`, `tc_cup_history_dt`, `tc_manager_history_dt` and
`award_year_hist_dt` sections, whose binary layout fmsave's older readers do not parse.
Their layouts were
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
class Award:
    """One award row the yearly award history stores, one per (award, season, winner).

    The section streams 26 and 30-byte award records; the reader accepts the records
    that carry a season and award head, whether they carry a club field or not — the
    club-less shape carries club-winner rows and person winners (player awards)
    alike. The section's monthly-award rows carry no season year, so they cannot
    sit in a year-keyed table and are kept out.

    `award_id` is an award instance id that the game's award-definition section keys
    its records on; award names are not stored in a save, so an id cannot be named
    from the save alone.

    Attributes:
        season_year: Season-ending year the award belongs to, e.g. 2031 for 2030/31
            (unconfirmed).
        award_id: Award instance id the row names; the ids an award-definition
            section keys its records on (unconfirmed).
        tag: The record's leading category word, 0xffff on most rows (unconfirmed).
        winner_id: Winner the row records, a person or club id in this section's
            reference space, which joins to no table fmsave reads (unconfirmed).
        club_uid: Uid of the club the row is under, or None on the records that
            store no club field — the club-winner rows and the person winners alike
            (unconfirmed).
        winner_age: The winner's age at the award, read off the row's trailing
            block; the value the ground-truth save's manager rows carry is their
            real age (unconfirmed).
        tail: The row's trailing bytes as ints, the season and winner data the
            section stores around the award row; their meaning is unconfirmed.
    """

    season_year: int
    award_id: int
    tag: int
    winner_id: int
    club_uid: int | None
    winner_age: int
    tail: tuple[int, ...]


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
    Award,
    unconfirmed=("season_year", "award_id", "tag", "winner_id", "club_uid", "winner_age", "tail"),
)
register_field_statuses(
    ManagerSpell,
    unconfirmed=("club_uid", "start_day", "start_year"),
)

register_field_statuses(
    LeagueHistorySeason,
    unconfirmed=(
        "season_year",
        "competition_id",
        "position",
        "total_teams",
        "games_played",
        "wins",
        "draws",
        "losses",
        "goals_for",
        "goals_against",
        "points",
    ),
)


@dataclass(frozen=True, slots=True)
class LeagueHistorySeason:
    """One season of league table performance for a club."""
    season_year: int          # Season ending year (e.g. 2025 for 2024/25)
    competition_id: int       # Save-internal competition id
    position: int             # 0-based league position
    total_teams: int          # Number of teams in league that season
    games_played: int         # P
    wins: int                 # W
    draws: int                # D
    losses: int               # L
    goals_for: int            # GF
    goals_against: int        # GA
    points: int               # Pts