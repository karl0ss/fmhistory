"""Tests for the league-history decoder (`decode_league_history` / `Save.career_league_history`)."""

from __future__ import annotations

import struct

from fmsave.readers.career_history import (
    LEAGUE_HISTORY_DT_SECTION,
    LEAGUE_HISTORY_LS_SECTION,
    decode_league_history,
    decode_league_history_ls_pointers,
)

# The dt section opens with an 8-byte tag header, so every row starts at an offset
# congruent to 8 modulo 24 and rows butt at stride 24 inside and across tables.
_HEADER = bytes.fromhex("03 01 74 61 64 2e 08 00")
_NO_TEAM = 0xFFFF_FFFF


def row(
    season: int,
    comp: int = 10,
    pos: int = 0,
    size: int = 20,
    played: int = 38,
    wins: int = 20,
    draws: int = 10,
    losses: int = 8,
    gf: int = 60,
    ga: int = 40,
    pts: int = 70,
    team_ref: int = _NO_TEAM,
) -> bytes:
    """One 24-byte league-history row: [season comp pos size] [00 00 team] [P P W D L 0] [GF GA Pts]."""
    return (
        struct.pack("<HHBB", season, comp, pos, size)
        + b"\x00\x00"
        + struct.pack("<I", team_ref)
        + bytes([played, played, wins, draws, losses, 0])
        + struct.pack("<HHH", gf, ga, pts)
    )


def dt_blob(*rows: bytes, header: bytes = _HEADER) -> bytes:
    """Rows butted on the 8-mod-24 grid behind the section header."""
    return header + b"".join(rows) + b"\x00" * (-len(b"".join(rows)) % 24)


def test_dt_and_ls_sections_are_the_inputs() -> None:
    assert LEAGUE_HISTORY_DT_SECTION == "tc_league_history_dt"
    assert LEAGUE_HISTORY_LS_SECTION == "tc_league_history_ls"


def test_one_row_decodes_every_field() -> None:
    (season,) = decode_league_history(dt_blob(row(2031, 13, 4, 18, 34, 20, 7, 7, 52, 33, 67)), b"")
    assert season.season_year == 2031
    assert season.competition_id == 13
    assert season.position == 4
    assert season.total_teams == 18
    assert season.games_played == 34
    assert season.wins == 20
    assert season.draws == 7
    assert season.losses == 7
    assert season.goals_for == 52
    assert season.goals_against == 33
    assert season.points == 67


def test_rows_butt_at_stride_24_in_file_order() -> None:
    # Tables butt against each other with no header, so consecutive grid slots hold
    # rows of different tables and eras without breaking the walk.
    seasons = decode_league_history(
        dt_blob(
            row(2029, 13, 0, 18, 34, 20, 7, 7, 52, 33, 67),
            row(2030, 10, 4, 24, 46, 21, 13, 12, 65, 49, 76),
            row(1901, 90, 0, 16, 30, 20, 4, 6, 68, 31, 44),
            row(2036, 8, 11, 20, 38, 13, 11, 14, 46, 48, 50),
        ),
        b"",
    )
    assert [(s.season_year, s.competition_id, s.position) for s in seasons] == [
        (2029, 13, 0),
        (2030, 10, 4),
        (1901, 90, 0),
        (2036, 8, 11),
    ]


def test_an_unplayed_table_still_reads_with_its_unset_results() -> None:
    # A table that was never played stores an unset played byte with zeroed results;
    # it passes the row check and reads back raw.
    seasons = decode_league_history(
        dt_blob(row(2032, 14, 6, 16, played=255, wins=0, draws=0, losses=0)), b""
    )
    (season,) = seasons
    assert season.games_played == 255
    assert (season.wins, season.draws, season.losses) == (0, 0, 0)


def test_the_results_block_all_unset_is_not_a_row() -> None:
    assert (
        decode_league_history(
            dt_blob(row(2031, 13, 0, 18, played=255, wins=255, draws=255, losses=255)), b""
        )
        == ()
    )


def test_out_of_grid_positions_hold_other_record_families_and_are_skipped() -> None:
    # Other record shapes share the file off the row grid; the walk reads only the
    # 8-mod-24 grid, and a grid slot junk bytes land on is dropped, not misread.
    junk = b"\xff" * 24
    first = row(2029, 13, 0, 18, 34, 20, 7, 7, 52, 33, 67)
    seasons = decode_league_history(
        dt_blob(first, junk, row(2030, 10, 4, 24, 46, 21, 13, 12, 65, 49, 76)), b""
    )
    assert [s.season_year for s in seasons] == [2029, 2030]


def test_season_outside_the_year_band_is_rejected() -> None:
    assert decode_league_history(dt_blob(row(1899)), b"") == ()
    assert decode_league_history(dt_blob(row(2101)), b"") == ()
    assert len(decode_league_history(dt_blob(row(1900)), b"")) == 1
    assert len(decode_league_history(dt_blob(row(2100)), b"")) == 1


def test_a_position_outside_its_table_is_rejected() -> None:
    assert decode_league_history(dt_blob(row(2031, 13, 18, 18)), b"") == ()
    assert len(decode_league_history(dt_blob(row(2031, 13, 17, 18)), b"")) == 1


def test_implausible_table_sizes_are_rejected() -> None:
    assert decode_league_history(dt_blob(row(2031, 13, 0, 1)), b"") == ()
    assert decode_league_history(dt_blob(row(2031, 13, 0, 101)), b"") == ()


def test_no_arithmetic_is_enforced_between_the_result_fields() -> None:
    # The 2-point era and rows the import recomputed both occur, so the reader keeps
    # rows whose points do not fit either points rule; the caller filters.
    two_point = row(1979, 294, 1, 16, 30, 20, 4, 6, 68, 31, 44)
    odd_points = row(1989, 122, 6, 20, 38, 13, 16, 9, 55, 39, 61)
    seasons = decode_league_history(dt_blob(two_point, odd_points), b"")
    assert [(s.points, s.wins, s.draws) for s in seasons] == [(44, 20, 4), (61, 13, 16)]


def test_the_unset_team_reference_reads_through() -> None:
    # A post-import row carries no team identity; a pre-import row stores a team id.
    post = decode_league_history(dt_blob(row(2031)), b"")
    assert post[0]  # a row where team_ref cannot be misread as a field decodes whole
    pre_import = decode_league_history(dt_blob(row(1979, 294, 1, 16, team_ref=20000)), b"")
    assert len(pre_import) == 1


def test_ls_content_is_not_followed() -> None:
    # The ls index is accepted but not walked: a row decodes the same whatever the
    # index holds.
    seasons = decode_league_history(
        dt_blob(row(2031, 13, 4, 18, 34, 20, 7, 7, 52, 33, 67)), b"\xff" * 64
    )
    assert len(seasons) == 1


def test_ls_pointers_read_as_words_from_after_the_index_header() -> None:
    # The real index opens with a 24-byte tag-and-counts header: 03 01 'tad.' 04 00
    # plus four u32s, so the word walk starts just past it.
    header = b"\x03\x01tad.\x04\x00" + struct.pack("<4I", 0, 9, 44, 0)
    words = struct.pack("<4I", 0, 1000, 2000, 0)
    assert decode_league_history_ls_pointers(header + words) == (0, 1000, 2000, 0)


def test_an_empty_dt_section_yields_no_rows() -> None:
    assert decode_league_history(_HEADER, b"") == ()
    assert decode_league_history(b"", b"") == ()
