"""Career history records read from the save's history sections.

These come from the `hall_of_fame`, `tc_cup_history_dt`, `tc_manager_history_dt`,
`award_year_hist_dt`, `tc_league_history_*` and `tc_best_eleven_history_*` sections,
whose binary layout fmsave's older readers do not parse.
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
        competition_id: The row's second u32, read as a cup competition id; on the
            ground-truth save every value under the managed club falls in one foreign
            cup's stage list, so it is not a competition or stage id and must not be
            joined to `competitions()` or named (unconfirmed).
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


@dataclass(frozen=True, slots=True)
class LeagueHistorySeason:
    """One 24-byte league-history row, a single club's table line for one season.

    `tc_league_history_dt` stores past league tables as butted 24-byte rows on an
    offset grid (`offset % 24 == 8`); a row is `[u16 season][u16 competition]
    [u8 position][u8 team count] [u16 zero][u32 team reference] [u8 games][u8 games
    again][u8 wins][u8 draws][u8 losses][u8 zero] [u16 goals for][u16 goals
    against][u16 points]`. The reader walks the grid and keeps a row whose fields
    pass sanity bounds, so it holds every readable line of every stored table. A row
    carries no club identity itself (a post-import row stores the unset team
    reference 0xffffffff); the `tc_league_history_ls` index lists each club's rows,
    and `history_index` is the number of the list a row belongs to, so all of one
    club's rows share it.

    The season a row stores is the season's ending year (a 2024/25 season stores
    2025), the position is 0-based, and on the ground-truth save every readable
    post-import row satisfies games = wins + draws + losses and points =
    3 x wins + draws (rows imported from an FM24 save satisfy points =
    2 x wins + draws instead). The current season stores no history rows at all:
    they come from the live `league_tables()` reader instead.

    Attributes:
        season_year: Season-ending year the row belongs to, e.g. 2025 for the
            2024/25 season (unconfirmed).
        competition_id: Save-internal competition id the table was played in; the
            ids are stable across seasons for one competition on the ground-truth
            save (e.g. one id covers the Championship across the whole career), but
            they join to nothing fmsave reads reliably (unconfirmed).
        position: The club's 0-based finishing position in that table (unconfirmed).
        total_teams: Number of teams the table held that season (unconfirmed).
        games_played: Games played; stored twice, once at each of the row's two
            game bytes, and read from the first (unconfirmed).
        wins: Wins (unconfirmed).
        draws: Draws (unconfirmed).
        losses: Losses (unconfirmed).
        goals_for: Goals scored (unconfirmed).
        goals_against: Goals conceded (unconfirmed).
        points: Points; rows of an imported older save may carry the 2-point-era
            value 2 x wins + draws (unconfirmed).
        imported: Whether the row was carried over from an imported older save: its
            second games byte is 0 although the table was played. Rows the game
            wrote itself repeat games played there; an imported career can hold
            both kinds for the same club and season (unconfirmed).
        history_index: Number of the `tc_league_history_ls` list holding the row:
            one list per club with league history, in club uid order, with clubs
            whose first league season came after an imported career appended at
            the end. Neither section stores which club uid a list belongs to. None
            when the index does not cover the row (unconfirmed).
    """

    season_year: int
    competition_id: int
    position: int
    total_teams: int
    games_played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    points: int
    imported: bool = False
    history_index: int | None = None


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
        "imported",
        "history_index",
    ),
)


@dataclass(frozen=True, slots=True)
class BestElevenEntry:
    """One player of one club's season best-eleven table, from the best-eleven history.

    `tc_best_eleven_history_dt` is an 8-byte section head followed by 509-byte
    records, `[u16 season][18 units of 27 B][13 B tail][u8 table type][u8 kind][00]
    [u32 table id][04]`; a unit is `[u32 player reference][u16 appearances][u16
    goals][u32 rating total][02 u32 natural positions][02 u32 secondary positions][02
    u32 table position]`. A record's identity head sits at its end, after its units.
    `tc_best_eleven_history_ls` lists every record exactly once, one delta-encoded
    list per club (the league-history index grammar), so `history_index` groups one
    club's tables across seasons; neither section stores which club uid a list is.
    On the ground-truth save St Albans City's list (685) runs one record per season
    from 2023 to 2036, while its league-history rows (season-ending years) run 2024
    to 2037: the year reads as the season's starting year. Paired that way, the
    table type and kind change exactly where the club's league competition does
    (six leagues, six pairs), so the pair reads as a league identifier.

    Slots 0-10 hold the eleven, goalkeeper first, and slots 11-17 the substitutes;
    `table_position` is one position bit (1 on the goalkeeper slot, 16384 on the
    striker slots), and `goals` peaks on the striker slots. An empty slot (player
    reference 0xffffffff, every other field zero) is not a row.

    Attributes:
        record_index: Number of the 509-byte record within the section, from 0
            (unconfirmed).
        season_year: Season year the record stores, which reads as the season's
            starting year, e.g. 2036 for the 2036/37 season (unconfirmed).
        table_type: First byte of the record's identity head (unconfirmed).
        kind: Second byte of the record's identity head; with `table_type` it
            follows the club's division (unconfirmed).
        table_id: u32 id in the record's identity head; it changes every season
            for one club and joins to nothing fmsave reads (unconfirmed).
        slot: Unit number within the table, 0-17 (unconfirmed).
        player_reference: The player's history reference id, `pindex + 1` of his
            player record (unconfirmed).
        appearances: Appearances counted for the table (unconfirmed).
        goals: Goals, read from the unit's second count; zero on goalkeeper slots
            and highest on striker slots (unconfirmed).
        rating_total: Sum of match ratings x 10 over the appearances (unconfirmed).
        average_rating: `rating_total / appearances / 10`, the average match rating,
            or None with no appearances (unconfirmed).
        natural_positions: Position bitmask of the positions the player plays
            (unconfirmed).
        secondary_positions: A second position bitmask, zero on most units
            (unconfirmed).
        table_position: The single position bit the slot fills in the table
            (unconfirmed).
        history_index: Number of the `tc_best_eleven_history_ls` list holding the
            record: one list per club. None when the index does not cover the record
            (unconfirmed).
        player_uid: Uid of the player in `players()`, joined through
            `Save.history_player_references()`. None for a player no longer in
            `players()`, which covers most retired players (unconfirmed).
    """

    record_index: int
    season_year: int
    table_type: int
    kind: int
    table_id: int
    slot: int
    player_reference: int
    appearances: int
    goals: int
    rating_total: int
    average_rating: float | None
    natural_positions: int
    secondary_positions: int
    table_position: int
    history_index: int | None = None
    player_uid: int | None = None


register_field_statuses(
    BestElevenEntry,
    unconfirmed=(
        "record_index",
        "season_year",
        "table_type",
        "kind",
        "table_id",
        "slot",
        "player_reference",
        "appearances",
        "goals",
        "rating_total",
        "average_rating",
        "natural_positions",
        "secondary_positions",
        "table_position",
        "history_index",
        "player_uid",
    ),
)
