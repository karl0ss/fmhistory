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
Which clubs have a list is not stored, so a club's list number is found from its
league titles: `resolve_league_history_indexes` maps each hall-of-fame honour's
competition (an editor database id) to the internal id, finds the single
first-place row the game wrote for that season and competition, and takes its
list. Clubs with no post-import league title stay unresolved. On the ground-truth
save this pins 63 clubs with no conflicts, matches uid order, and agrees 18/18 with
an independent live-table check.

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
  pins club uids to list numbers through league titles; `Save.club_league_history`
  uses it and returns an empty table for a club it cannot pin.

## Usage

Access league history data through the Save object:

```python
import fmsave

save = fmsave.open("my-career.fm")
league_history = save.career_league_history()

for season in save.club_league_history(716):  # St Albans City on the ground-truth save
    print(f"{season.season_year}: Position {season.position + 1}/{season.total_teams}")
    print(f"  Record: {season.wins}-{season.draws}-{season.losses} ({season.points} pts)")
    print(f"  Goals: {season.goals_for}-{season.goals_against}")
```

## Integration with Other Career History Data

League history data can be combined with other career history decoders:

- **Awards**: `save.career_awards()` - seasonal manager awards
- **Cup history**: `save.career_cup_entries()` - cup runs per season
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