"""Tests for pinning league-history lists to clubs (`Save.league_history_clubs`)."""

from __future__ import annotations

from fmsave.models.career_history import (
    LeagueHistoryClub,
    LeagueHistoryClubMethod,
    LeagueHistorySeason,
)
from fmsave.models.clubs import Club, Team
from fmsave.models.fixtures import Fixture
from fmsave.readers.career_history import (
    league_history_fixture_pins,
    resolve_league_history_clubs,
)

LEAGUE = 7
FIXTURES = LeagueHistoryClubMethod.FIXTURES
TITLE = LeagueHistoryClubMethod.TITLE
UID_ORDER = LeagueHistoryClubMethod.UID_ORDER


def fixture(
    home: int,
    away: int,
    home_goals: int,
    away_goals: int,
    *,
    start_year: int = 2036,
    competition: int = LEAGUE,
    stage: int | None = 1,
    played: bool = True,
) -> Fixture:
    """A played league fixture: only the fields the resolver reads carry meaning."""
    return Fixture(
        stage_id=stage,
        competition_id=competition,
        competition_name=None,
        round=None,
        round_index=None,
        date=None,
        kick_off_time=None,
        season_start_year=start_year,
        home_team_id=home,
        home_club_uid=None,
        home_club_name=None,
        home_club_short_name=None,
        home_team_slot=None,
        away_team_id=away,
        away_club_uid=None,
        away_club_name=None,
        away_club_short_name=None,
        away_team_slot=None,
        home_goals=home_goals,
        away_goals=away_goals,
        played=played,
        is_neutral_venue=False,
        stadium_uid=None,
        stadium_name=None,
        match_record_id=None,
        match_rules_template=(),
        unknown={},
    )


def history_row(
    history_index: int,
    record: tuple[int, int, int, int, int, int],
    *,
    season: int = 2037,
    competition: int = LEAGUE,
    position: int = 0,
    imported: bool = False,
) -> LeagueHistorySeason:
    """A league-history row with the given (P, W, D, L, GF, GA) record."""
    played, wins, draws, losses, scored, conceded = record
    return LeagueHistorySeason(
        season_year=season,
        competition_id=competition,
        position=position,
        total_teams=3,
        games_played=played,
        wins=wins,
        draws=draws,
        losses=losses,
        goals_for=scored,
        goals_against=conceded,
        points=3 * wins + draws,
        imported=imported,
        history_index=history_index,
    )


def club(uid: int, *team_ids: int, affiliate: int | None = None) -> Club:
    """A club fielding the given own teams (first team first), plus an affiliate's team."""
    teams = tuple(Team(team_id, slot, uid, False) for slot, team_id in enumerate(team_ids))
    if affiliate is not None:
        teams += (Team(affiliate, len(teams), uid, True),)
    return Club(uid, f"Club {uid}", f"C{uid}", 1, 1, None, teams, None, None, None, None)


# Three teams, one round: team 1 beats 2 and 3, team 2 draws 3. Records (P W D L GF GA):
# team 1 (2, 2, 0, 0, 5, 1), team 2 (2, 0, 1, 1, 2, 4), team 3 (2, 0, 1, 1, 1, 3).
ROUND = (fixture(1, 2, 3, 1), fixture(3, 1, 0, 2), fixture(2, 3, 1, 1))
TABLE = (
    history_row(10, (2, 2, 0, 0, 5, 1), position=0),
    history_row(11, (2, 0, 1, 1, 2, 4), position=1),
    history_row(12, (2, 0, 1, 1, 1, 3), position=2),
)


def test_each_teams_fixture_record_pins_the_one_row_that_equals_it() -> None:
    assert league_history_fixture_pins(TABLE, ROUND) == {10: 1, 11: 2, 12: 3}


def test_a_calendar_year_season_matches_its_own_start_year() -> None:
    table = tuple(
        history_row(row.history_index or 0, _record(row), season=2036, position=row.position)
        for row in TABLE
    )
    assert league_history_fixture_pins(table, ROUND) == {10: 1, 11: 2, 12: 3}


def test_unplayed_unscored_and_other_competition_fixtures_add_nothing() -> None:
    noise = (
        fixture(1, 2, 0, 0, played=False),
        fixture(1, 3, 9, 0, competition=99),
        fixture(2, 3, 4, 4, start_year=2030),
    )
    assert league_history_fixture_pins(TABLE, ROUND + noise) == {10: 1, 11: 2, 12: 3}


def test_a_record_two_teams_share_pins_neither() -> None:
    # Teams 1 and 2 both finish (2, 0, 2, 0, 1, 1): neither can be told apart.
    level = (fixture(1, 2, 1, 1), fixture(3, 1, 0, 0), fixture(2, 3, 0, 0))
    table = (
        history_row(10, (2, 0, 2, 0, 1, 1)),
        history_row(11, (2, 0, 2, 0, 1, 1)),
        history_row(12, (2, 0, 2, 0, 0, 0)),
    )
    assert league_history_fixture_pins(table, level) == {12: 3}


def test_two_rows_with_the_same_record_pin_nothing() -> None:
    twin = history_row(13, (2, 2, 0, 0, 5, 1), position=1, competition=LEAGUE)
    assert league_history_fixture_pins((*TABLE, twin), ROUND) == {11: 2, 12: 3}


def test_imported_rows_are_never_matched() -> None:
    imported = tuple(
        history_row(row.history_index or 0, _record(row), imported=True) for row in TABLE
    )
    assert league_history_fixture_pins(imported, ROUND) == {}


def test_a_regular_stage_matches_when_the_row_leaves_out_play_offs() -> None:
    play_off = fixture(1, 2, 0, 1, stage=2)
    # Over the whole competition teams 1 and 2 add the play-off; their rows hold stage 1.
    assert league_history_fixture_pins(TABLE, (*ROUND, play_off)) == {10: 1, 11: 2, 12: 3}
    whole = history_row(11, (3, 1, 1, 1, 3, 4), position=1)
    assert league_history_fixture_pins((TABLE[0], whole), (*ROUND, play_off)) == {10: 1, 11: 2}


def test_a_team_matching_two_lists_pins_neither() -> None:
    # Team 1's record equals one row in 2036 (start year) and one in 2037.
    rows = (
        history_row(10, (2, 2, 0, 0, 5, 1), season=2036),
        history_row(20, (2, 2, 0, 0, 5, 1), season=2037),
    )
    assert league_history_fixture_pins(rows, ROUND[:2]) == {}


def _record(row: LeagueHistorySeason) -> tuple[int, int, int, int, int, int]:
    return (
        row.games_played,
        row.wins,
        row.draws,
        row.losses,
        row.goals_for,
        row.goals_against,
    )


def ordered(*indexes: int) -> tuple[LeagueHistorySeason, ...]:
    """One imported row per list: lists holding imported rows run in uid order."""
    return tuple(
        history_row(index, (2, 1, 0, 1, 2, 2), season=2000, imported=True) for index in indexes
    )


def test_fixture_and_title_pins_name_clubs_and_agree() -> None:
    clubs = [club(100, 1, 51), club(200, 2), club(300, 3)]
    pins = resolve_league_history_clubs((), {10: 1, 11: 51}, {200: 12, 300: 10}, clubs)
    # A title says list 10 is club 300's, fixtures say club 100's: list 10 is dropped,
    # and so is list 11, which club 100's second team (51) claims.
    assert pins == (LeagueHistoryClub(12, 200, "Club 200", TITLE),)
    pins = resolve_league_history_clubs((), {10: 1}, {100: 10, 200: 12}, clubs)
    assert pins == (
        LeagueHistoryClub(10, 100, "Club 100", FIXTURES, 1),
        LeagueHistoryClub(12, 200, "Club 200", TITLE),
    )


def test_a_list_two_clubs_claim_and_unknown_ids_are_dropped() -> None:
    clubs = [club(100, 1), club(200, 2)]
    # List 10: fixtures say club 100, a title says club 200. Club id 999 is no club.
    pins = resolve_league_history_clubs((), {10: 1, 11: 77}, {200: 10, 999: 12}, clubs)
    assert pins == ()


def test_affiliate_teams_do_not_name_the_controlling_club() -> None:
    clubs = [club(100, 1, affiliate=5), club(500, 5)]
    pins = resolve_league_history_clubs((), {10: 5}, {}, clubs)
    assert pins == (LeagueHistoryClub(10, 500, "Club 500", FIXTURES, 5),)


def test_a_run_between_two_pinned_lists_takes_the_clubs_between_in_uid_order() -> None:
    clubs = [club(100, 1), club(150, 2), club(170, 3), club(200, 4)]
    pins = resolve_league_history_clubs(ordered(0, 1, 2, 3), {0: 1, 3: 4}, {}, clubs)
    assert pins == (
        LeagueHistoryClub(0, 100, "Club 100", FIXTURES, 1),
        LeagueHistoryClub(1, 150, "Club 150", UID_ORDER),
        LeagueHistoryClub(2, 170, "Club 170", UID_ORDER),
        LeagueHistoryClub(3, 200, "Club 200", FIXTURES, 4),
    )


def test_a_club_pinned_elsewhere_is_skipped_by_the_fill() -> None:
    clubs = [club(100, 1), club(150, 2), club(170, 3), club(200, 4)]
    pins = resolve_league_history_clubs(ordered(0, 1, 2), {0: 1, 2: 4, 9: 2}, {}, clubs)
    assert LeagueHistoryClub(1, 170, "Club 170", UID_ORDER) in pins


def test_the_fill_needs_an_exact_count_and_no_unused_team_id() -> None:
    clubs = [club(100, 1), club(150, 2), club(170, 3), club(200, 4)]
    # Three lists between, two clubs: the run cannot be split exactly.
    too_many = resolve_league_history_clubs(ordered(0, 1, 2, 3, 4), {0: 1, 4: 4}, {}, clubs)
    assert {pin.method for pin in too_many} == {FIXTURES}
    # Team id 4 is unused between the anchors' first teams 1 and 5: a club fmsave does
    # not list could own one of the lists.
    gapped = [club(100, 1), club(150, 2), club(170, 3), club(200, 5)]
    unsafe = resolve_league_history_clubs(ordered(0, 1, 2, 3), {0: 1, 3: 5}, {}, gapped)
    assert {pin.method for pin in unsafe} == {FIXTURES}


def test_lists_past_the_imported_ones_are_never_filled() -> None:
    clubs = [club(100, 1), club(150, 2), club(200, 3)]
    # Only list 0 holds imported rows, so lists 1-2 are appended clubs, not uid-ordered.
    pins = resolve_league_history_clubs(ordered(0), {0: 1, 2: 3}, {}, clubs)
    assert {pin.method for pin in pins} == {FIXTURES}
