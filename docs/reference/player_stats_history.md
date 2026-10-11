# Player Statistics History Reference

## Overview
`player_stats_hist_dt` keeps every player's past statistics: one 152-byte row per team a
player was registered with, per season, per competition type (league, cup, continental,
international, non-competitive). `Save.player_season_history(player_uids)` returns one
`fmsave.PlayerHistoryStats` per row for the players asked for; every field is registered
`unconfirmed`.

A row names no player. The rows are a pool, and an index the save directory does not list
holds one list of rows per player; each player's own `game_db` object stores the number of
his list.

`Save.history_person_season_history(references)` returns the same rows for people no
longer in `players()` (retired or released), by history reference: a person whose object
survives in full (`history_people()` form `"object"`) stores his list number the same way.

## Section Structure

### player_stats_hist_dt
An 8-byte head (`03 01 'tmc.' 06 00`) followed by 152-byte rows back to back (5,766,139 on
the ground-truth save, 876,453,136 bytes). Rows sit in pool order: neither by player, club
nor season.

```
+0    00
+1    u32 team id           Team.team_id (0xffffffff on a few rows)
+5    u16 competition id    the team's league that season, 0xffff for none
+7    i32 departure fee     money of the move that ended the spell; -1 (0xffffffff)
                            while the spell goes on or after a release (see below)
+11   u16 season year       the season's starting year (2036 = 2036/37)
+13   u16 rating total      ten times the summed match ratings
+15   u16 minutes
+17   u8 goals allowed      +18 penalties taken, +19 penalties scored, +20 red cards,
                            +21 yellow cards, +22 clean sheets
+24   u8 starts             +25 substitute appearances, +26 rated appearances,
                            +27 goals, +28 assists, +29 player of the match
+30   u8 spell code         0 permanent registration, 1 loan, 4 trial
+31   u8 kind               0 non-competitive, 1 league, 2 cup, 3 continental,
                            4 international (the season-statistics slot order)
+40.. u16 words             the season-statistics line words: a line word at line
                            offset k (k >= 27) sits at row offset k + 13
```

The u16 words, by row offset: passes attempted 40, completed 42; tackles attempted 44,
won 46; aerial challenges / saves held 48; headers won / saves parried 50; dribbles 52;
fouls made 54, against 56; shots 58, on target 60; distance (x10 km) 78; offsides 80;
saves tipped (keepers) 82; open-play crosses completed (outfield) 84; key passes 86, key
tackles 88, key headers 90, interceptions 92, clear-cut chances 94; blocks / shots on
target faced 96; possession lost 100, won 102; xG (x100) 104, xA (x100) 106; clearances
(outfield) 108; free-kick shots 112; goals outside the box 114; open-play crosses
attempted 122; shots outside the box 124; xG prevented (signed, x100) 126; sprints 128;
progressive passes 132; pressures attempted 134, completed 136; open-play key passes 138;
non-penalty xG (x100) 140; crosses attempted 144, completed 146; shots blocked 148. The
shared words read as saves on a natural goalkeeper's rows, as on the season-statistics
line.

### The pool index (unlisted frame)
One frame of the unlisted span region after `non_pl_hist_ls` (24,041,770 bytes
decompressed on the ground-truth save), in the per-person index grammar `pl_hist_ls`
also uses:

```
03 01 'tad.' 04 00
u32 free_count, free_count x u32     offsets of free rows (76,091)
u32 list_count, list_count x list    one list per owner (239,790): u32 n, n x u32
u32 empty_count, empty_count x u32   numbers of the empty lists (4,507)
u32 152, u16 6                       the dt row size and version
```

List values are delta-encoded like every `_ls` index: the m-th row sits at `value[m] +
value[m - 1]` bytes past the dt's 8-byte head (the first at `value[0]`). Free rows plus
listed rows (5,690,048) cover the dt exactly once. A list stores its rows in season order;
the lists themselves run in no player order.

### Binding a list to a player
A player's `game_db` object stores his list number as the u32 21 bytes before his person
block's start (the first-name id): `[u32 list number][u32 undecoded][4-byte date][9 bytes]
[first-name id]...`. On the ground-truth save all 223,569 player records have a person
block; 217,876 store distinct in-range list numbers and 5,693 store 0xffffffff (no list).
The remaining ~21,900 non-empty lists belong to people no longer in `players()` (retired
players, mostly stubs) and are not bound.

## Validation (ground-truth save)

- **Best eleven.** For every best-eleven slot of a bound player, the player's rows of that
  season and team with kind league, cup or continental add up to the slot's appearances
  (rated appearances) and goals for 198,217 of 228,335 slots (86.8%). The misses are
  ~10% per season and concentrate in calendar-year leagues, whose best-eleven year is one
  after the history year (spot-checked: those match the previous history year).
- **St Albans 2036/37** (rated appearances / goals / rating total, league + cup):
  Tshongo 45/0/3119, Gumbs 34/16/2391, Robinho 41/12/2852, Young-Thomas 37/10/2591, Hodges
  26/4/1794, Dumas 37/11/2501 (his rows at team 603; he also has 2036 rows at his previous
  club) — every number equals `career_best_eleven()`.
- **Current season.** For 340 lines whose 2037 history row has the same minutes, starts and
  rated appearances as `player_season_stats()`, every mapped field agrees on 99-100% of
  lines (the rating total on 317/318). Most 2037 rows lag the live season figures.

## Notes

- Rows can repeat field for field inside a list: 29,965 of 5,690,048 listed rows (0.53%),
  mostly zero registration rows, 2,561 with minutes. Drop repeats before adding up.
- **Departure fee (+7, `departure_fee`).** When a player leaves a team, every row of his
  last season there (all competition kinds alike) stores the money of the move that took
  him away; earlier seasons of the spell, the current spell, and a spell that ended in a
  release or a contract running out keep -1 (`None`). On a permanent spell (spell code 0)
  it is the transfer fee, 0 for a free move: Dumas's 2036 rows at Saint-Etienne hold
  22,937,564 (the game shows £23M, `manager_career().highest_fee_paid` 22,937,564),
  Tshongo's at Guingamp 8,250,000. On loan spells it holds 0 or small sums (loan fees,
  unverified); the only trial-spell values seen repeat the fee of the transfer that
  followed. One loan row holds -10. `Save.club_player_moves(club_uid, fees=True)` joins
  the fee to each permanent move (`ClubPlayerMove.fee`, rule in
  `fmsave.readers.transfer_history.move_fee`).
- **Spell code (+30, `spell_code`).** At St Albans every row with code 1 has a loan of the
  player within the season or the next (both the loan club's rows and the lending club's
  rows of that season carry it), and every row with code 4 a trial; 0 elsewhere. One row
  of 8,984 checked holds 26.
- Timing on the ground-truth save: binding (index + every player's list number) about 8 s
  once per `Save`; each call decompresses the dt (about 3 s); peak RSS about 3 GB with
  `players()` loaded.

## Retired and released players

A person outside `players()` whose `game_db` object survives in full stores his list number
21 bytes before his last validated person block, as a current player does
(`HistoryPerson.stats_history_index`). `fmsave.readers.player_stats_history.
history_person_list_numbers` binds a number when it is a non-empty list, no current player
claims it, and no other person stores it. People cut down to a stub keep no number, and
their lists are gone from the index (their rows are among the free rows).

On the ground-truth save: 24,960 objects store a number; 16,637 bind, 95.6% of the 17,407
non-empty lists no current player owns. Of the bound people's 45,431 best-eleven seasons
with appearances, 41,225 (90.7%) match a team's league+cup+continental rows of that season
on (appearances, goals), against 86.8% for current players; the same bindings shuffled
match 0.6%. At St Albans 7 of the 44 retired best-eleven players bind (the rest are stubs)
and all 32 of their St Albans best-eleven seasons agree. Positions are not read for these
people: pass goalkeepers' references in `goalkeepers=` to read their saves words.

## Usage

```python
import fmsave

with fmsave.open("career.fm") as save:
    rows = save.player_season_history(player_uid)
    seen = set()
    for row in rows:
        key = (row.season_year, row.team_id, row.kind, row.minutes, row.rating_total)
        if key in seen:
            continue  # a stored repeat
        seen.add(key)
        print(row.season_year, row.team_id, row.kind, row.rated_appearances, row.goals)
```
