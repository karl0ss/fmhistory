"""A player's past statistics: one row per team, season and competition type.

Decoded from `player_stats_hist_dt` and its unlisted pool index by
`fmsave.readers.player_stats_history`; see `docs/reference/player_stats_history.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from fmsave._status import register_field_statuses
from fmsave.models.season_stats import SeasonStatsKind


@dataclass(frozen=True, slots=True)
class PlayerHistoryStats:
    """One player's statistics for one team, season and competition type, from his history.

    The game keeps one row per team a player was registered with, per season and per
    competition type he has a line for (league, cup, continental, international, and
    non-competitive games); a registration with no games keeps a row of zeros. The current,
    unfinished season has rows too, but the game refreshes them only now and then:
    `player_season_stats()` is the live figure for it. Rows come in the order the player's
    history list stores them, which is season order.

    Some rows are stored twice in one player's list, field for field: on the ground-truth
    save 29,965 of 5,690,048 listed rows (0.53%) repeat an earlier row of their list, most of
    them zero rows and 2,561 with minutes. The reader returns every stored row, so drop
    repeats before adding rows up.

    Goalkeepers get `saves_held`, `saves_parried`, `saves_tipped` and
    `shots_on_target_faced`; everyone else gets `aerial_challenges_attempted`,
    `headers_won`, `open_play_crosses_completed`, `blocks` and `clearances`, which share
    their stored words. The other set is None. A player counts as a goalkeeper when GK is one
    of his natural positions now.

    Attributes:
        player_uid: Uid of the player in `players()` (unconfirmed).
        player_reference: The player's history reference id, pindex + 1 (unconfirmed).
        history_index: Number of the pool-index list holding the row: one list per player
            (unconfirmed).
        list_position: The row's position in the player's list, from 0 (unconfirmed).
        record_index: Number of the 152-byte row within `player_stats_hist_dt`, from 0
            (unconfirmed).
        season_year: The season's starting year, e.g. 2036 for 2036/37 (unconfirmed).
        team_id: The `Team.team_id` the row is for, or None (unconfirmed).
        club_uid: Uid of the club whose team list holds `team_id`, or None when no club
            lists it (unconfirmed).
        competition_id: The team's league competition that season, or None; one id for all
            of a team's rows in a season, whatever their `kind` (unconfirmed).
        kind_code: The stored competition-type byte, 0-4 (unconfirmed).
        kind: The competition type, in the season-statistics slot order: non-competitive,
            league, cup, continental, international; None for a code outside 0-4
            (unconfirmed).
        rating_total: Ten times the sum of the player's match ratings (unconfirmed).
        average_rating: `rating_total / rated_appearances / 10`, or None without rated
            appearances (unconfirmed).
        minutes: Minutes played (unconfirmed).
        starts: Appearances from the start (unconfirmed).
        substitute_appearances: Appearances from the bench (unconfirmed).
        rated_appearances: Appearances that got a match rating; the count the best-eleven
            tables show (unconfirmed).
        goals: Goals scored (unconfirmed).
        assists: Assists (unconfirmed).
        player_of_the_match: Player-of-the-match awards (unconfirmed).
        goals_allowed: Goals the team conceded with the player on the pitch (unconfirmed).
        clean_sheets: Clean sheets (unconfirmed).
        penalties_taken: Penalties taken (unconfirmed).
        penalties_scored: Penalties scored (unconfirmed).
        yellow_cards: Yellow cards (unconfirmed).
        red_cards: Red cards (unconfirmed).
        shots: Shots (unconfirmed).
        shots_on_target: Shots on target (unconfirmed).
        shots_outside_box: Shots from outside the box (unconfirmed).
        goals_outside_box: Goals from outside the box (unconfirmed).
        free_kick_shots: Shots from direct free kicks (unconfirmed).
        expected_goals: Expected goals (unconfirmed).
        non_penalty_expected_goals: Expected goals without penalties (unconfirmed).
        expected_assists: Expected assists (unconfirmed).
        passes_attempted: Passes attempted (unconfirmed).
        passes_completed: Passes completed (unconfirmed).
        progressive_passes: Progressive passes (unconfirmed).
        key_passes: Key passes (unconfirmed).
        open_play_key_passes: Key passes from open play (unconfirmed).
        clear_cut_chances_created: Clear-cut chances created (unconfirmed).
        crosses_attempted: Crosses attempted (unconfirmed).
        crosses_completed: Crosses completed (unconfirmed).
        open_play_crosses_attempted: Open-play crosses attempted (unconfirmed).
        open_play_crosses_completed: Open-play crosses completed; None for a goalkeeper
            (unconfirmed).
        dribbles: Dribbles made (unconfirmed).
        offsides: Offsides (unconfirmed).
        distance_km: Distance covered, in kilometres (unconfirmed).
        high_intensity_sprints: High-intensity sprints (unconfirmed).
        aerial_challenges_attempted: Aerial challenges attempted; None for a goalkeeper
            (unconfirmed).
        headers_won: Headers won; None for a goalkeeper (unconfirmed).
        key_headers: Key headers (unconfirmed).
        tackles_attempted: Tackles attempted (unconfirmed).
        tackles_completed: Tackles won (unconfirmed).
        key_tackles: Key tackles (unconfirmed).
        interceptions: Interceptions (unconfirmed).
        possession_won: Possession won (unconfirmed).
        possession_lost: Possession lost (unconfirmed).
        pressures_attempted: Pressures attempted (unconfirmed).
        pressures_completed: Pressures completed (unconfirmed).
        blocks: Blocks; None for a goalkeeper (unconfirmed).
        shots_blocked: Shots blocked (unconfirmed).
        clearances: Clearances; None for a goalkeeper (unconfirmed).
        fouls_made: Fouls made (unconfirmed).
        fouls_against: Fouls against (unconfirmed).
        expected_goals_prevented: Expected goals prevented (unconfirmed).
        saves_held: Saves held; None for an outfield player (unconfirmed).
        saves_parried: Saves parried; None for an outfield player (unconfirmed).
        saves_tipped: Saves tipped; None for an outfield player (unconfirmed).
        shots_on_target_faced: Shots on target faced; None for an outfield player
            (unconfirmed).
    """

    player_reference: int
    history_index: int
    list_position: int
    record_index: int
    season_year: int
    team_id: int | None
    competition_id: int | None
    kind_code: int
    kind: SeasonStatsKind | None
    rating_total: int
    average_rating: float | None
    minutes: int
    starts: int
    substitute_appearances: int
    rated_appearances: int
    goals: int
    assists: int
    player_of_the_match: int
    goals_allowed: int
    clean_sheets: int
    penalties_taken: int
    penalties_scored: int
    yellow_cards: int
    red_cards: int
    shots: int
    shots_on_target: int
    shots_outside_box: int
    goals_outside_box: int
    free_kick_shots: int
    expected_goals: float
    non_penalty_expected_goals: float
    expected_assists: float
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
    possession_lost: int
    pressures_attempted: int
    pressures_completed: int
    blocks: int | None
    shots_blocked: int
    clearances: int | None
    fouls_made: int
    fouls_against: int
    expected_goals_prevented: float
    saves_held: int | None
    saves_parried: int | None
    saves_tipped: int | None
    shots_on_target_faced: int | None
    player_uid: int | None = None
    club_uid: int | None = None


register_field_statuses(
    PlayerHistoryStats,
    unconfirmed=tuple(field.name for field in fields(PlayerHistoryStats)),
)
