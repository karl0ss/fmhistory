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
  - `team_ref` (u32, offset +8) - reference to team/club
  - `games_played` (u8, offset +12) - P (duplicated at offset +13)
  - `padding` (u8, offset +13) - should equal games_played
  - `wins` (u8, offset +14) - W
  - `draws` (u8, offset +15) - D
  - `losses` (u8, offset +16) - L
  - `padding` (u8, offset +17) - typically 0x00
  - `goals_for` (u16, offset +18) - GF
  - `goals_against` (u16, offset +20) - GA
  - `points` (u16, offset +22) - Pts

### tc_league_history_ls
Contains linking/index data:
- Starts with a 4-byte tag header
- Followed by an array of u32 values starting at offset 24
- Each u32 value can represent:
  - A pointer to a dt row start minus 8 (i.e., points to the 24-byte block header)
  - Another ls offset (for chaining/indexing)
  - Invalid/unused values

## Decoder Implementation

The `decode_league_history` function in `src/fmsave/readers/career_history.py` implements a simple data extraction approach:

1. Iterates through the dt section at offsets ≡ 8 mod 24
2. Validates each 24-byte block as a readable league history row:
   - Season year in range 1900-2100
   - Position < total teams (0-based indexing)
   - Total teams between 2 and 100 (reasonable bounds)
   - Wins/Draws/Losses not all 255 (indicates no data)
3. Decodes valid rows into `LeagueHistorySeason` objects
4. Returns all valid rows as a tuple

An optional function `decode_league_history_ls_pointers` is provided to extract all u32 values from the ls section for users who want to implement their own chain reconstruction logic.

## Usage

Access league history data through the Save object:

```python
import fmsave

save = fmsave.open("my-career.fm")
league_history = save.career_league_history()

for season in league_history:
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
- The simple data extraction approach provides maximum flexibility for application logic to interpret the data
- Users can implement their own career chain reconstruction algorithms on top of the raw data
- Each time a newer save is loaded, the career history extends automatically with new seasons