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

`person_record_manager` (manager career statistics) stores real game dates, which
its records carry as `datetime.date`. Every other date here is the (day-of-season,
season-year) pair the history sections store:
the day counts within a season that starts around 1 July, and 1900 marks a null date
elsewhere in these sections (never in a row we accept).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import ClassVar

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
    """One cup-history row: how one team's campaign in one competition ended.

    `tc_cup_history_dt` holds one 18-byte row per team per competition per season,
    and `tc_cup_history_ls` holds one list of row offsets per team, so a team's
    list is its cup history: the stage each campaign ended in, the team that ended
    it (or the beaten finalist, for a winner) and how. Rows name no team of their
    own; the list a row belongs to is `history_index`, and which team a list is
    goes unstored (`Save.club_cup_history` pins a club's list from its cup
    honours). Knockout stages and league-format stages (group stages, and youth
    leagues the game files under the same history) both appear.

    Codes as observed on the ground-truth save, checked against the scores of the
    fixtures still stored for 2034/35 to 2036/37 (all unconfirmed across builds):

    - `result`: 3 = won the competition (the row is the final and
      `opponent_team_id` the beaten finalist); 2 = knocked out by
      `opponent_team_id`; 0 with no opponent = finished a league-format stage at
      `position`; 1 = a tie the team won, meaning open; 0 with an opponent is rare
      and open.
    - `method`: 1 = decided in normal time; 2 = in extra time; 3 = on penalties
      (the stored fixture score is always a draw); 7 = over two legs; 8 (154 rows)
      open; 255 on league-format rows.

    Attributes:
        stage_id: Id of the stage the campaign ended in, in the `stages()` id space
            (unconfirmed).
        start_year: Calendar year the campaign's season starts, e.g. 2024 for
            2024/25; equal to `end_year` for a calendar-year competition
            (unconfirmed).
        end_year: Calendar year the campaign's season ends, e.g. 2025 for 2024/25:
            the year a cup honour is filed under (unconfirmed).
        result: How the campaign ended, see the codes above (unconfirmed).
        method: How the deciding tie was decided, see the codes above (unconfirmed).
        unknown_word: The u16 after `method`; None (0xffff) on almost every row, a
            small value such as 633/637/635/2610 on the rest, meaning open
            (unconfirmed).
        position: Placing in a league-format stage, None (0xff) on knockout rows;
            0 occurs, so most likely 0-based like the league history (unconfirmed).
        opponent_team_id: Team id (`Club.teams[].team_id`, not a club uid) of the
            team that ended the campaign, or the beaten finalist on a winning row;
            None (0xffffffff) on league-format rows (unconfirmed).
        history_index: Number of the `tc_cup_history_ls` list the row belongs to,
            one list per team; None when the index does not cover the row
            (unconfirmed).
        competition_id: Save-internal id of the competition the stage belongs to,
            joined from `stages()`; None when the stage is not in the save
            (unconfirmed).
    """

    stage_id: int
    start_year: int
    end_year: int
    result: int
    method: int
    unknown_word: int | None
    position: int | None
    opponent_team_id: int | None
    history_index: int | None
    competition_id: int | None


@dataclass(frozen=True, slots=True)
class Award:
    """One placing of one award in one season, from the yearly award history.

    `award_year_hist_dt` is a flat array of 82-byte records, one per award per
    season: the season year and award id, then three 26-byte placing slots (winner,
    runner-up, third). Every filled slot becomes one row; empty slots (winner unset)
    are left out. Monthly awards are not in this section at all.

    `award_id` is the award's position in the game's English award table (ordered
    by editor database id), so names come from an out-of-save map.

    Attributes:
        season_year: Season-ending year the award belongs to, e.g. 2031 for 2030/31
            (unconfirmed).
        award_id: Award index the record names (unconfirmed).
        placing: 0 for the winner, 1 for the runner-up, 2 for third; the
            ground-truth manager's biography runner-up award sits in slot 1
            (unconfirmed).
        tag: The slot's closing u16: 0xffff on many slots, a small value on the
            rest (0x8b on every English manager slot of the ground-truth save, most
            likely a nation id) (unconfirmed).
        winner_id: The placed person or club; a person is named in the history
            reference space (`Save.history_person_reference`) (unconfirmed).
        club_uid: Uid of the club the placing is recorded against, or None when the
            slot stores no club (unconfirmed).
        winner_age: The winner's age at the award, the slot's ninth byte; the
            ground-truth manager's slots carry his real age (unconfirmed).
        tail: The slot's 11 bytes from the age on, as ints; meaning beyond the age
            unconfirmed.
    """

    season_year: int
    award_id: int
    placing: int
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
    unconfirmed=(
        "stage_id",
        "start_year",
        "end_year",
        "result",
        "method",
        "unknown_word",
        "position",
        "opponent_team_id",
        "history_index",
        "competition_id",
    ),
)
register_field_statuses(
    Award,
    unconfirmed=(
        "season_year",
        "award_id",
        "placing",
        "tag",
        "winner_id",
        "club_uid",
        "winner_age",
        "tail",
    ),
)
register_field_statuses(
    ManagerSpell,
    unconfirmed=("club_uid", "start_day", "start_year"),
)


class LeagueHistoryClubMethod(StrEnum):
    """How a `tc_league_history_ls` list was pinned to a club.

    Attributes:
        FIXTURES: A team's league fixtures of one season, summed to played, won,
            drawn, lost, goals for and against, equal exactly one history row of that
            season and competition, and no other team's sums equal them.
        TITLE: A league title the hall of fame records names the club, and exactly one
            first-place row the game wrote matches that season and competition.
        UID_ORDER: The list sits between two lists pinned by fixtures or titles, and
            the clubs between those two clubs in uid order are exactly as many as the
            lists between them, with no gap in the clubs' first-team ids where a club
            the save does not list could sit. Relies on lists running in club uid
            order, which every pinned pair on the ground-truth save follows.
    """

    FIXTURES = "fixtures"
    TITLE = "title"
    UID_ORDER = "uid_order"


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
        club_uid: Uid of the club whose list holds the row, as
            `league_history_clubs()` pins it; None from `career_league_history()`
            (which does not resolve clubs) and wherever the list is not pinned
            (unconfirmed).
        club_name: Denormalised name of club_uid (unconfirmed).
        club_method: How the list was pinned to club_uid, or None when it is not
            (unconfirmed).
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
    club_uid: int | None = None
    club_name: str | None = None
    club_method: LeagueHistoryClubMethod | None = None


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
        "club_uid",
        "club_name",
        "club_method",
    ),
)


@dataclass(frozen=True, slots=True)
class LeagueHistoryClub:
    """One `tc_league_history_ls` list pinned to the club it belongs to.

    The league-history index stores one row list per club but never the club's uid;
    `league_history_clubs()` pins lists from evidence elsewhere in the save, and a
    list it cannot pin exactly has no record rather than a guess.

    Attributes:
        history_index: Number of the list, as `LeagueHistorySeason.history_index`
            carries it (unconfirmed).
        club_uid: Uid of the club the list belongs to (unconfirmed).
        club_name: Denormalised name of club_uid (unconfirmed).
        method: The evidence that pinned the list (unconfirmed).
        team_id: The team whose fixtures matched, for a list pinned by fixtures;
            None otherwise (unconfirmed).
    """

    history_index: int
    club_uid: int
    club_name: str
    method: LeagueHistoryClubMethod
    team_id: int | None = None


register_field_statuses(
    LeagueHistoryClub,
    unconfirmed=("history_index", "club_uid", "club_name", "method", "team_id"),
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
        player_name: Name of a player no longer in `players()`, from
            `Save.history_people()`. None when `player_uid` is set (join `players()`
            for his name) or when the save keeps no readable name for him
            (unconfirmed).
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
    player_name: str | None = None


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
        "player_name",
    ),
)


@dataclass(frozen=True, slots=True)
class HistoryPerson:
    """A person history sections name by reference who is not among `players()`.

    History sections (best elevens, award winners, transfer and person-record rows)
    name people by a save-wide history reference. A person's `game_db` object closes
    with the header `[u32 reference][u32 unique_id][u32 unique_id]`, and objects sit
    in ascending reference order, so a header between two players' closing headers,
    with a reference and a unique id between theirs, closes a person who is not a
    current player: a retired or released player, a staff member, any other person.
    The name is read from the bytes just before that header, in one of three forms:

    - `"stub"`: an 18-byte remnant `10 00 [u32 first-name id][u32 surname id]
      [4 flag bytes][u32 small]`, the form most retired players keep;
    - `"common_name_stub"`: a 14-byte remnant `10 01 [u32 common-name id][4 flag
      bytes][u32 small]`, for players known by one name;
    - `"object"`: a full person object, named by the last person block that
      validates between the previous header and this one.

    On the ground-truth save 131 of these people also hold a hall-of-fame record
    whose `person_uid` equals `unique_id`, and all 131 names agree.

    Attributes:
        reference: The history reference id history rows name the person by
            (unconfirmed).
        unique_id: The doubled id of the closing header; the hall of fame's
            `person_uid` (unconfirmed).
        form: Which of the three forms the name was read from (unconfirmed).
        name: Display name: the common name when there is one, else first name and
            surname. None when the object's person block does not validate
            (unconfirmed).
        first_name: First name, None for a common-name stub (unconfirmed).
        last_name: Surname, None for a common-name stub (unconfirmed).
        common_name: Common name, when the person has one (unconfirmed).
    """

    reference: int
    unique_id: int
    form: str
    name: str | None
    first_name: str | None
    last_name: str | None
    common_name: str | None


register_field_statuses(
    HistoryPerson,
    unconfirmed=(
        "reference",
        "unique_id",
        "form",
        "name",
        "first_name",
        "last_name",
        "common_name",
    ),
)


@dataclass(frozen=True, slots=True)
class ManagerFee:
    """One record transfer fee a manager's career record keeps (highest paid or received).

    Attributes:
        player_reference: History reference of the player moved; `history_people()` or
            `history_player_references()` names him (unconfirmed).
        transfer_date: The day the transfer went through (unconfirmed).
        fee: The fee in whole pounds as stored; the game displays it rounded (e.g.
            22,937,564 shows as £23M) (unconfirmed).
        from_team_id: `Team.team_id` of the selling team (unconfirmed).
        to_team_id: `Team.team_id` of the buying team (unconfirmed).
    """

    player_reference: int
    transfer_date: date | None
    fee: int
    from_team_id: int | None
    to_team_id: int | None


@dataclass(frozen=True, slots=True)
class ManagerSpellWindow:
    """A spell window a manager's career record keeps (longest or shortest job).

    Attributes:
        team_id: `Team.team_id` of the team managed (unconfirmed).
        start_date: First day of the spell (unconfirmed).
        end_date: Last day of the spell; an open spell carries the save's current date
            (unconfirmed).
    """

    team_id: int
    start_date: date | None
    end_date: date | None


@dataclass(frozen=True, slots=True)
class ManagerCurrentJob:
    """The current-job half of a manager's career record (the profile's "Current Club").

    Attributes:
        team_id: `Team.team_id` of the team the manager runs now (unconfirmed).
        start_date: The day the manager took the job (unconfirmed).
        highest_fee_paid: The highest fee paid in this job, or None.
        highest_fee_received: The highest fee received in this job, or None.
        money_spent: Total transfer fees paid in this job, whole pounds (unconfirmed).
        money_received: The stored total of fees received in this job, whole pounds
            (unconfirmed).
        goals_for: Goals scored in this job (unconfirmed).
        goals_against: Goals conceded in this job (unconfirmed).
        games: Games managed in this job (unconfirmed).
        wins: Games won (unconfirmed).
        draws: Games drawn: `games - wins - losses`, since the record stores no draw
            count (unconfirmed).
        losses: Games lost (unconfirmed).
        cups: Cups won (unconfirmed).
        league_titles: League titles won (unconfirmed).
        awards: Awards won (unconfirmed).
        players_bought: Players bought (unconfirmed).
        players_sold: Players sold (unconfirmed).
        players_released: Players released (unconfirmed).
    """

    team_id: int
    start_date: date | None
    highest_fee_paid: ManagerFee | None
    highest_fee_received: ManagerFee | None
    money_spent: int
    money_received: int
    goals_for: int
    goals_against: int
    games: int
    wins: int
    draws: int
    losses: int
    cups: int
    league_titles: int
    awards: int
    players_bought: int
    players_sold: int
    players_released: int


@dataclass(frozen=True, slots=True)
class ManagerCareerRecord:
    """One manager's career statistics record from `person_record_manager`.

    The section keeps one fixed 367-byte record for every person who has managed in
    the game world (11,945 on the ground-truth save), keyed by the person's history
    reference — the same id `history_person_reference` finds for a staff uid. The
    record holds the "Managerial Stats" profile screen: whole-career totals, the
    career's record transfer fees, the longest and shortest club and national spells,
    and a current-job block. Draws are not stored; `draws` is derived. Every field was
    calibrated on the ground-truth save's human manager and is unconfirmed.

    Attributes:
        reference: The manager's history reference (unconfirmed).
        highest_fee_paid: The career's highest fee paid, or None.
        highest_fee_received: The career's highest fee received, or None.
        longest_club_spell: The longest club job, or None.
        shortest_club_spell: The shortest club job, or None when the manager has had
            one club job only (the game then shows 0 days).
        longest_national_spell: The longest national-team job, or None.
        shortest_national_spell: The shortest national-team job, or None.
        money_spent: Total transfer fees paid over the career, whole pounds
            (unconfirmed).
        money_received: The stored career total of fees received, whole pounds; on the
            ground-truth save the game's "Total Sold Transfer Value" shows £0 while this
            holds £97.7M, so its meaning is open (unconfirmed).
        agent_fees: Total fees paid to agents, whole pounds (unconfirmed).
        goals_for: Goals scored over the career (unconfirmed).
        goals_against: Goals conceded over the career (unconfirmed).
        games: Games managed over the career (unconfirmed).
        wins: Games won (unconfirmed).
        draws: Games drawn: `games - wins - losses` (unconfirmed).
        losses: Games lost (unconfirmed).
        cups: Cups won (unconfirmed).
        league_titles: League titles won (unconfirmed).
        awards: Awards won (unconfirmed).
        players_bought: Players bought (unconfirmed).
        players_sold: Players sold (unconfirmed).
        players_released: Players released (unconfirmed).
        club_jobs: Number of club manager jobs (unconfirmed).
        national_jobs: Number of national manager jobs (unconfirmed).
        current_job: The current-job block, or None when the manager holds no job.
        unknown: Counters the record stores whose meaning is not pinned, keyed
            `word_<offset>` by their byte offset in the record (unconfirmed).
    """

    reference: int
    highest_fee_paid: ManagerFee | None
    highest_fee_received: ManagerFee | None
    longest_club_spell: ManagerSpellWindow | None
    shortest_club_spell: ManagerSpellWindow | None
    longest_national_spell: ManagerSpellWindow | None
    shortest_national_spell: ManagerSpellWindow | None
    money_spent: int
    money_received: int
    agent_fees: int
    goals_for: int
    goals_against: int
    games: int
    wins: int
    draws: int
    losses: int
    cups: int
    league_titles: int
    awards: int
    players_bought: int
    players_sold: int
    players_released: int
    club_jobs: int
    national_jobs: int
    current_job: ManagerCurrentJob | None
    unknown: Mapping[str, int]

    UNKNOWN_KEYS: ClassVar[tuple[str, ...]] = (
        "word_151",
        "word_153",
        "word_155",
        "word_157",
        "word_159",
        "word_161",
        "word_169",
        "word_171",
        "word_173",
        "word_175",
        "word_177",
        "word_195",
        "word_197",
        "word_318",
        "word_340",
    )


register_field_statuses(
    ManagerFee,
    unconfirmed=("player_reference", "transfer_date", "fee", "from_team_id", "to_team_id"),
)
register_field_statuses(
    ManagerSpellWindow,
    unconfirmed=("team_id", "start_date", "end_date"),
)
register_field_statuses(
    ManagerCurrentJob,
    unconfirmed=(
        "team_id",
        "start_date",
        "money_spent",
        "money_received",
        "goals_for",
        "goals_against",
        "games",
        "wins",
        "draws",
        "losses",
        "cups",
        "league_titles",
        "awards",
        "players_bought",
        "players_sold",
        "players_released",
    ),
)
register_field_statuses(
    ManagerCareerRecord,
    unconfirmed=(
        "reference",
        "money_spent",
        "money_received",
        "agent_fees",
        "goals_for",
        "goals_against",
        "games",
        "wins",
        "draws",
        "losses",
        "cups",
        "league_titles",
        "awards",
        "players_bought",
        "players_sold",
        "players_released",
        "club_jobs",
        "national_jobs",
        "unknown",
    ),
)
