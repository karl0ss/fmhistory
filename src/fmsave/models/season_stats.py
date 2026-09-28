"""Season statistics: what one player did for one team this season, by kind of match.

The save keeps one record per player holding his season so far: a line per kind of match for
the team he is registered with, the same lines for any other team he has turned out for this
season (a B team and its first team, or a club he has left), and two calendar-year lines. Each
line is what the player profile's statistics panel shows on the row of the same name: `LEAGUE`,
`CUP`, `CONTINENTAL`, `INTERNATIONAL` and `NON_COMPETITIVE`, and `OVERALL` for its "Overall
(Club)" row, which is the league, cup and continental lines added up and is the season total
the squad statistics screen shows.

The save stores no season year. A line covers the season in progress for the competitions the
player's team plays in, and the calendar-year lines the year of the save's own date.

Only counts are stored; the game computes every per-90 figure and ratio it displays from them.
Pass completion is `passes_completed / passes_attempted`, a per-90 figure is a count times 90
divided by `minutes`, the save ratio is `(saves_held + saves_parried + saves_tipped) /
shots_on_target_faced`, and the shots-on-target ratio is `shots_on_target / shots`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from fmsave._status import register_field_statuses


class SeasonStatsKind(StrEnum):
    """The kind of match a season line counts, named as the player profile names its row.

    `OVERALL` is the profile's "Overall (Club)" row and the squad screen's season total. The two
    calendar-year kinds count the calendar year of the save's date: they restart on 1 January
    while every other line runs to the end of the season. Another team's lines carry the first
    six kinds only.
    """

    NON_COMPETITIVE = "non_competitive"
    LEAGUE = "league"
    CUP = "cup"
    CONTINENTAL = "continental"
    INTERNATIONAL = "international"
    OVERALL = "overall"
    CALENDAR_YEAR_OVERALL = "calendar_year_overall"
    CALENDAR_YEAR_INTERNATIONAL = "calendar_year_international"


@dataclass(frozen=True, slots=True)
class PlayerSeasonStats:
    """One line of one player's season: one kind of match, for one team.

    A line the save does not hold builds no row, so a player who has played no cup match has no
    `CUP` row. Six words of a line hold different statistics for a goalkeeper: on a natural
    goalkeeper's line (one whose natural positions include GK) the save counts saves there, so
    `saves_held`, `saves_parried`, `saves_tipped` and `shots_on_target_faced` are filled and
    `aerial_challenges_attempted`, `headers_won`, `open_play_crosses_completed`, `blocks` and
    `clearances` are None; on everyone else's line it is the other way round. The game makes the
    same split: nothing in a line says which kind it is, and a player who has played in both
    roles reads by his natural position alone.

    Attributes:
        player_uid: Uid of the player the record belongs to.
        player_name: Denormalised name of player_uid.
        kind: The kind of match the line counts.
        team_id: The team the line is for: the player's current team for his own lines, or
            the other team's id for a team he has also played for this season.
        club_uid: Uid of the club whose team list holds team_id, or None when no club lists it.
        club_name: Denormalised name of club_uid, or None when the team does not resolve.
        club_short_name: Denormalised short name of club_uid, or None when the team does not
            resolve.
        team_slot: The team's slot in its club's team list, 0 for the first entry, or None when
            the team does not resolve (unconfirmed).
        starts: Appearances from the start.
        substitute_appearances: Appearances from the bench.
        minutes: Minutes played.
        rated_appearances: Appearances the game rated, which average_rating averages over.
        average_rating: Average match rating, unrounded (the game shows it to two decimals), or
            None when no appearance was rated.
        player_of_the_match: Player of the match awards (unconfirmed).
        goals: Goals.
        assists: Assists.
        expected_goals: Expected goals (xG).
        expected_assists: Expected assists (xA).
        shots: Shots.
        shots_on_target: Shots on target.
        shots_outside_box: Shots from outside the box.
        goals_outside_box: Goals from outside the box (unconfirmed).
        free_kick_shots: Shots from free kicks (unconfirmed).
        penalties_taken: Penalties taken (unconfirmed).
        penalties_scored: Penalties scored (unconfirmed).
        passes_attempted: Passes attempted.
        passes_completed: Passes completed.
        progressive_passes: Progressive passes.
        key_passes: Key passes.
        open_play_key_passes: Key passes in open play.
        clear_cut_chances_created: Clear-cut chances created; the game's "chances created per
            90" is this count per 90.
        crosses_attempted: Crosses attempted.
        crosses_completed: Crosses completed.
        open_play_crosses_attempted: Crosses attempted in open play (unconfirmed).
        open_play_crosses_completed: Crosses completed in open play; None on a goalkeeper's
            line (unconfirmed).
        dribbles: Dribbles made.
        offsides: Offsides.
        distance_km: Distance covered, in kilometres to one decimal (the game may display it in
            miles).
        high_intensity_sprints: High intensity sprints.
        aerial_challenges_attempted: Aerial challenges attempted; None on a goalkeeper's line.
        headers_won: Headers won; None on a goalkeeper's line.
        key_headers: Key headers (unconfirmed).
        tackles_attempted: Tackles attempted.
        tackles_completed: Tackles completed.
        key_tackles: Key tackles (unconfirmed).
        interceptions: Interceptions.
        possession_won: Times the player won possession.
        pressures_attempted: Pressures attempted.
        pressures_completed: Pressures completed.
        blocks: Blocks; None on a goalkeeper's line (unconfirmed).
        shots_blocked: Shots blocked while defending (unconfirmed).
        clearances: Clearances; None on a goalkeeper's line.
        fouls_made: Fouls made.
        fouls_against: Fouls suffered.
        yellow_cards: Yellow cards.
        red_cards: Red cards (unconfirmed).
        mistakes_leading_to_goal: Mistakes leading to a goal (unconfirmed).
        clean_sheets: Clean sheets; 0 for an outfield player (unconfirmed).
        goals_allowed: Goals the player conceded as goalkeeper; 0 for an outfield player
            (unconfirmed).
        saves_held: Saves held; None on an outfield player's line (unconfirmed).
        saves_parried: Saves parried; None on an outfield player's line (unconfirmed).
        saves_tipped: Saves tipped; None on an outfield player's line (unconfirmed).
        shots_on_target_faced: Shots on target the goalkeeper faced, which the game divides his
            saves by for his save ratio; None on an outfield player's line (unconfirmed).
        expected_goals_prevented: Expected goals prevented (xGP), negative when a goalkeeper
            conceded more than expected (unconfirmed).
    """

    player_uid: int
    player_name: str | None
    kind: SeasonStatsKind
    team_id: int | None
    club_uid: int | None
    club_name: str | None
    club_short_name: str | None
    team_slot: int | None
    starts: int
    substitute_appearances: int
    minutes: int
    rated_appearances: int
    average_rating: float | None
    player_of_the_match: int
    goals: int
    assists: int
    expected_goals: float
    expected_assists: float
    shots: int
    shots_on_target: int
    shots_outside_box: int
    goals_outside_box: int
    free_kick_shots: int
    penalties_taken: int
    penalties_scored: int
    passes_attempted: int
    passes_completed: int
    progressive_passes: int
    key_passes: int
    open_play_key_passes: int
    clear_cut_chances_created: int
    crosses_attempted: int
    crosses_completed: int
    open_play_crosses_attempted: int
    open_play_crosses_completed: int | None
    dribbles: int
    offsides: int
    distance_km: float
    high_intensity_sprints: int
    aerial_challenges_attempted: int | None
    headers_won: int | None
    key_headers: int
    tackles_attempted: int
    tackles_completed: int
    key_tackles: int
    interceptions: int
    possession_won: int
    pressures_attempted: int
    pressures_completed: int
    blocks: int | None
    shots_blocked: int
    clearances: int | None
    fouls_made: int
    fouls_against: int
    yellow_cards: int
    red_cards: int
    mistakes_leading_to_goal: int
    clean_sheets: int
    goals_allowed: int
    saves_held: int | None
    saves_parried: int | None
    saves_tipped: int | None
    shots_on_target_faced: int | None
    expected_goals_prevented: float


register_field_statuses(
    PlayerSeasonStats,
    verified=(
        "player_uid",
        "player_name",
        "kind",
        "team_id",
        "club_uid",
        "club_name",
        "club_short_name",
        "starts",
        "substitute_appearances",
        "minutes",
        "rated_appearances",
        "average_rating",
        "goals",
        "assists",
        "expected_goals",
        "expected_assists",
        "shots",
        "shots_on_target",
        "shots_outside_box",
        "passes_attempted",
        "passes_completed",
        "progressive_passes",
        "key_passes",
        "open_play_key_passes",
        "clear_cut_chances_created",
        "crosses_attempted",
        "crosses_completed",
        "dribbles",
        "offsides",
        "distance_km",
        "high_intensity_sprints",
        "aerial_challenges_attempted",
        "headers_won",
        "tackles_attempted",
        "tackles_completed",
        "interceptions",
        "possession_won",
        "pressures_attempted",
        "pressures_completed",
        "clearances",
        "fouls_made",
        "fouls_against",
        "yellow_cards",
    ),
    unconfirmed=(
        "team_slot",
        "player_of_the_match",
        "goals_outside_box",
        "free_kick_shots",
        "penalties_taken",
        "penalties_scored",
        "open_play_crosses_attempted",
        "open_play_crosses_completed",
        "key_headers",
        "key_tackles",
        "blocks",
        "shots_blocked",
        "red_cards",
        "mistakes_leading_to_goal",
        "clean_sheets",
        "goals_allowed",
        "saves_held",
        "saves_parried",
        "saves_tipped",
        "shots_on_target_faced",
        "expected_goals_prevented",
    ),
)
