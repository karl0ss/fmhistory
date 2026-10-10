# League History Reference

## Overview
The league history sections (`tc_league_history_dt` and `tc_league_history_ls`) store performance data for clubs across seasons. This reference document describes the data structures and decoded fields.

## Data Model

### LeagueHistorySeason Dataclass

The record's fields and their meanings are documented on `fmsave.LeagueHistorySeason`
itself (see `fmsave.models.career_history`); every field is registered
`unconfirmed`. In short: one row is one club's line of one past league table, keyed
by the season's ending year and the competition's save-internal id, with the 0-based
position, table size and the P/W/D/L/GF/GA/Pts block.

## Section Structure

### tc_league_history_dt
Contains the actual league history data in 24-byte blocks:
- Each block represents one season's league performance for a club
- Blocks are located at offsets ≡ 8 mod 24 (starting at offset 8)
- Each 24-byte block contains:
  - `season_year` (u16, little-endian, offset +0)
  - `competition_id` (u16, little-endian, offset +2)
  - `position` (u8, offset +4) - 0-based league position
  - `total_teams` (u8, offset +5) - number of teams in league
  - `padding` (u16, offset +6) - typically 0x0000
  - `ref` (u32, offset +8) - 0xffffffff on most rows; an alias/predecessor id on some pre-1930 spans, not the owning club
  - `games_played` (u8, offset +12) - P (duplicated at offset +13)
  - `games_again` (u8, offset +13) - equals games_played on post-import rows, 0 on rows imported from FM24
  - `wins` (u8, offset +14) - W
  - `draws` (u8, offset +15) - D
  - `losses` (u8, offset +16) - L
  - `padding` (u8, offset +17) - typically 0x00
  - `goals_for` (u16, offset +18) - GF
  - `goals_against` (u16, offset +20) - GA
  - `points` (u16, offset +22) - Pts

### tc_league_history_ls
One list of row offsets per club with league history (the `_ls` grammar every
`*_ls` section shares):

```
03 01 'tad.' 04 00                       tag + version
u32 0, u32 list_count                    (19,514 on the ground-truth save)
list_count x { u32 n ; n x u32 value }
u32 0, u32 24, u16 1                     trailer: zero, dt record size, dt header version
```

Values are delta-encoded: row `m` of a list sits at `value[m] + value[m - 1]`
bytes past the dt section's 8-byte header (row 0 at `value[0]`). Decoded, each
list is one club's rows in season order, and on the ground-truth save every dt
row belongs to exactly one list.

The index stores no club uid. Lists run in club uid order among clubs that have
league history (clubs with none get no list), and clubs whose first league
season came after an imported career are appended at the end in the order they
first appeared. On the ground-truth save St Albans City (uid 716) is list 351.
Which clubs have a list is not stored, so lists are pinned to clubs from evidence
elsewhere in the save (`Save.league_history_clubs()`, one `LeagueHistoryClub` per
pinned list, its `method` saying which evidence):

1. **Fixtures** (`league_history_fixture_pins`). Every played, scored fixture adds
   to both teams' record (P, W, D, L, GF, GA) for its season and competition, over
   the whole competition and over its stage alone (a history row can leave out
   play-offs or a later phase). A record held by exactly one team in that season
   and competition, equal to exactly one non-imported row of that competition in
   the fixtures' start year or the year after (calendar-year and split-year
   leagues), pins the row's list to the team; a list naming two teams, or a team
   naming two lists, is dropped. The team maps to its club through `clubs()`
   (affiliates' teams excluded). The save keeps fixtures for the last full season
   and the current one, so this names every club that played a league with
   fixtures then, and through its list all its earlier seasons too.
2. **Titles** (`resolve_league_history_indexes`): hall-of-fame league titles, as
   in checkpoint 6. Only honour club ids `clubs()` holds count (on the
   ground-truth save 321 of 878 honour rows carry an id that is no club uid). A
   title and a fixture pin that disagree drop the list and every list of both
   clubs.
3. **Uid order** (`resolve_league_history_clubs`). Lists holding imported rows run
   in club uid order. Between two pinned lists `i < j` (clubs `a < b`), when the
   clubs with uids strictly between `a` and `b` not pinned elsewhere are exactly
   `j - i - 1`, and the first-team ids of `a` and `b` have no unused id between
   them (`clubs()` does not list every club: an unused id could be a club that
   owns one of the lists), the lists take those clubs in uid order.

Ground-truth save: 2,791 lists pinned (2,077 fixtures, 714 uid order); every one of
the 55 usable title pins agrees; 0 lists claimed twice; 0 uid-order inversions
among pinned lists below the last imported list (19,276); St Albans = list 351
(fixtures, team 603). Uid-order fills reproduce 962/962 held-out fixture pins and
agree with the competition's nation on all 198 fills with post-import rows. Rows
named per season (non-imported rows): 76.6% (2023/24) rising to 84.3% (2036/37);
English tiers (VNS/VNN, National, L2, L1, Championship, PL) 90.2% rising to 100%.
The unnamed rows belong to clubs that left every league with fixtures before
2035/36 (e.g. six 2024/25 VNS clubs since relegated below the lowest stored
level) and to view-only leagues the save stores tables for but no fixtures.

## Decoder Implementation

`src/fmsave/readers/career_history.py`:

- `decode_league_history_lists(ls_data)` decodes the index into absolute dt row
  offsets per list. An index that does not parse exactly yields no lists.
- `decode_league_history(dt_data, ls_data)` walks the dt grid (offsets ≡ 8 mod 24),
  keeps rows that pass the sanity bounds (season 1900–2100, position < team count,
  2–100 teams, results block not all 255), and sets each row's `history_index`
  to its list number (None when the index does not cover it) and flags
  `imported` rows (second games byte 0 on a played table).
- `resolve_league_history_indexes(seasons, honours, competition_by_database_id)`
  pins club uids to list numbers through league titles.
- `league_history_fixture_pins(seasons, fixtures)` pins lists to team ids from
  fixture records, and `resolve_league_history_clubs(seasons, fixture_pins,
  title_indexes, clubs)` combines both with the uid-order fill into
  `LeagueHistoryClub` records. `Save.league_history_clubs()` wraps it (it reads
  `fixtures()`: about 40 s on the ground-truth save); `Save.club_league_history`
  and `Save.league_history_table` name rows through it (`club_uid`, `club_name`,
  `club_method`; None where the list is not pinned).

## Usage

Access league history data through the Save object:

```python
import fmsave

save = fmsave.open("my-career.fm")
league_history = save.career_league_history()

for row in save.league_history_table(2025, 708):  # 2024/25 National League South
    print(row.position + 1, row.club_name or "?", row.points, row.club_method)

for season in save.club_league_history(716):  # St Albans City on the ground-truth save
    print(f"{season.season_year}: Position {season.position + 1}/{season.total_teams}")
    print(f"  Record: {season.wins}-{season.draws}-{season.losses} ({season.points} pts)")
    print(f"  Goals: {season.goals_for}-{season.goals_against}")
```

## Integration with Other Career History Data

League history data can be combined with other career history decoders:

- **Awards**: `save.career_awards()` - season award placings (winner, runner-up, third)
- **Cup history**: `save.career_cup_entries()` / `save.club_cup_history(uid)` - how each
  cup campaign ended (stage, result, opponent team) per season
- **Hall of fame**: `save.career_honours()` - honours won per season
- **Manager spells**: `save.career_manager_spells()` - job start dates
- **Transfers** (future): transfer activity per season

## Field Status

All fields in `LeagueHistorySeason` are marked as unconfirmed, indicating they have been reverse-engineered from a single ground-truth save and require validation across different saves and builds.

## Notes

- Competition IDs are save-internal and require mapping to readable names using the same editor-database-ID map used by the competition reader
- An imported career can hold two rows for the same club and season: the FM24-era
  row (byte +13 = 0) and the row written after the import (byte +13 = games played).
  On the ground-truth save St Albans' 2023/24 reads 11th in the first and 3rd (the
  real finish) in the second.
- Each time a newer save is loaded, the career history extends automatically with new seasons