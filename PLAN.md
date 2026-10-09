# Implementation Plan: tc_league_history_dt Decoder (Simple Data Extraction)

## Phase 1: Data Structure Design

### Model: LeagueHistorySeason
```python
@dataclass(frozen=True, slots=True)
class LeagueHistorySeason:
    """One season of league table performance for a club."""
    season_year: int          # Season ending year (e.g. 2025 for 2024/25)
    competition_id: int       # Save-internal competition id
    position: int             # 0-based league position
    total_teams: int          # Number of teams in league that season
    games_played: int         # P
    wins: int                 # W
    draws: int                # D
    losses: int               # L
    goals_for: int            # GF
    goals_against: int        # GA
    points: int               # Pts
```

All fields marked `unconfirmed=` per decoder integration checklist.

## Phase 2: Reader Implementation

### Core Algorithm: Simple Data Extraction
1. **Iterate through dt section** at offsets ≡ 8 mod 24 (starting at offset 8)
2. **Validate each 24-byte block** as a readable league history row:
   - Season year in reasonable range (1900-2100)
   - Position < total teams (0-based indexing)
   - Total teams between 2 and 100 (reasonable bounds)
   - Wins/Draws/Losses not all 255 (indicates no data)
3. **Decode valid rows** into `LeagueHistorySeason` objects
4. **Return all valid rows** as a tuple
5. **Provide optional function** to extract LS pointer data for advanced users

### Key Functions
- `decode_league_history(dt_data: bytes, ls_data: bytes) -> tuple[LeagueHistorySeason, ...]`: Main extraction function
- `_is_valid_league_history_row(dt_data: bytes, offset: int) -> bool`: Row validation logic
- `_decode_league_history_row(dt_data: bytes, offset: int) -> LeagueHistorySeason`: Row decoding logic
- `decode_league_history_ls_pointers(ls_data: bytes) -> tuple[int, ...]`: Optional LS pointer extraction

## Phase 3: Integration Points

### In src/fmsave/_save.py
```python
def career_league_history(self) -> Table[LeagueHistorySeason]:
    """League table performance history for the managed club.
    
    Returns one record per season containing the season ending year,
    competition id, league position, number of teams, games played,
    wins, draws, losses, goals for, goals against, and points.
    All data is read from the tc_league_history_dt and tc_league_history_ls
    sections by extracting all readable league history rows.
    """
```

### In src/fmsave/models/career_history.py
- Add `LeagueHistorySeason` dataclass
- Register field statuses with `unconfirmed=()`

### CLI Exposure
- Existing `fmsave career-history` command will automatically include this data

## Phase 4: Validation

### Ground Truth Verification
Verify that reasonable data is extracted from known ground-truth save:
- Check that known anchor rows from docs/ground-truth.md are present in the extracted data
- Verify data integrity and reasonableness of values
- Ensure no regressions in existing functionality

## Documentation

### Completed
- Add reference entry in `docs/reference/league_history.md`
- Update `docs/history-re.md` with new checkpoint (after league history section)

### Remaining
- Application logic: Users can now build career history websites, chain reconstruction algorithms, or performance analysis tools on top of the raw data
- Future enhancements: Optional advanced decoders for chain reconstruction could be built as separate layers on top of the simple data extraction

## Implementation Notes

- Follows explicit user request for data dumping rather than intelligent reconstruction
- Provides maximum flexibility for application logic to interpret the data
- Uses existing patterns from other career history decoders (awards, hall of fame, etc.)
- Integrates cleanly with existing fmsave framework and validation