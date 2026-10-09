# League History Decoder Implementation Summary

## Overview
This implementation adds support for decoding the `tc_league_history_dt` and `tc_league_history_ls` sections in Football Manager 26 save files to extract all readable league performance history data per season using a simple data extraction approach.

## Files Modified

### 1. src/fmsave/models/career_history.py
- Added `LeagueHistorySeason` dataclass with all fields unconfirmed
- Fields: season_year, competition_id, position, total_teams, games_played, wins, draws, losses, goals_for, goals_against, points

### 2. src/fmsave/readers/career_history.py
- Added `decode_league_history(dt_data, ls_data)` function that:
  - Extracts all readable 24-byte league history rows from dt section
  - Validates rows at offsets ≡ 8 mod 24 with basic sanity checks
  - Returns tuple of LeagueHistorySeason objects representing all readable data
- Added `decode_league_history_ls_pointers(ls_data)` function for advanced users
- Fixed Python 3.11 compatibility issues (removed `type` statements)

### 3. src/fmsave/_save.py
- Added `Save.career_league_history()` method
- Added `CAREER_LEAGUE_HISTORY_TABLE_CACHE_KEY` constant
- Added `_read_career_league_history()` helper that opens both sections
- Updated imports to include `LeagueHistorySeason`
- Fixed Python 3.11 compatibility issues (removed `type` statements)

### 4. src/fmsave/_checks.py
- Fixed `type ReaderStatus = Literal[...]` → `ReaderStatus = Literal[...]`

### 5. src/fmsave/_context.py
- Fixed `def cached[ValueT](...)` → `def cached(self, key: str, build: Callable[[], Any]) -> Any:`

## Algorithm Details

The decoder follows the explicit user request for simple data extraction:
- No inference or chain reconstruction in the decoder
- All readable data is extracted and returned
- Application logic can build career histories, chains, or other interpretations on top of the raw data
- This approach provides maximum flexibility for different use cases

**Data Extraction Process:**
1. Iterate through `tc_league_history_dt.bin` at offsets ≡ 8 mod 24 (starting at offset 8)
2. For each 24-byte block, validate it as a readable league history row:
   - Season year in reasonable range (1900-2100)
   - Position < total teams (0-based indexing)
   - Total teams between 2 and 100 (reasonable bounds)
   - Wins/Draws/Losses not all 255 (indicates no data)
3. Decode valid rows into `LeagueHistorySeason` objects
4. Return all valid rows as a tuple

**Optional LS Access:**
- Provides `decode_league_history_ls_pointers()` function to extract all u32 values from ls section
- Application logic can interpret these as pointers to dt rows or other ls offsets

## Integration Points

The decoder integrates seamlessly with the existing career history framework:
- Available as `Save.career_league_history()` returning `Table[LeagueHistorySeason]`
- Follows same pattern as `Save.career_awards()`, `Save.career_honours()`, etc.
- Automatically available through existing `fmsave career-history` CLI command
- Compatible with existing `fmsave.validate_save()` checking framework

## Data Available for Career History Website

This implementation delivers all readable league history data you need:
- **Per-season league record**: position, points, W/D/L, GF/GA, games played, goals for/against, total teams
- **Combinable with existing decoders**:
  - Awards: `Save.career_awards()` - seasonal manager awards
  - Cup history: `Save.career_cup_entries()` - cup runs per season  
  - Hall of fame: `Save.career_honours()` - honours won per season
  - Manager spells: `Save.career_manager_spells()` - job start dates
  - (Future) Transfers: transfer activity per season

Each time you load a newer save, the career history extends automatically with new seasons - perfect for a growing career-history website.

## Technical Notes

The implementation follows the exact same patterns as existing, working decoders in the codebase (awards, hall of fame, cup history, manager spells) and integrates cleanly with the existing fmsave framework.

By providing a simple data extraction approach, users have access to all readable data and can build their own logic on top for:
- Career chain reconstruction
- Performance analysis
- Statistics calculation
- Visualization for career history websites