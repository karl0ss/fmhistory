# Best Eleven History Reference

## Overview
The best-eleven sections (`tc_best_eleven_history_dt` and `tc_best_eleven_history_ls`)
store every club's best eleven of each season: eighteen players (the eleven plus seven
substitutes) with their appearances, goals and rating total. `Save.career_best_eleven()`
returns one `fmsave.BestElevenEntry` per filled slot; its fields are documented on the
class and every one is registered `unconfirmed`.

## Section Structure

### tc_best_eleven_history_dt
An 8-byte head (`03 01 'tmc.' 02 00`, the tmc. family `tc_manager_history_dt` also
uses) followed by 509-byte records, back to back (26,456 on the ground-truth save):

```
+0    u16 season            the season's starting year (2036 = 2036/37)
+2    18 x 27-byte unit     slots 0-10 the eleven (goalkeeper first), 11-17 substitutes
+488  13-byte tail          undecoded
+501  u8 table type, u8 kind, 00, u32 table id, 04
```

The identity head **closes** its record. Read the other way round (head first, at
`k * 509`), the section's first units have no head and its last eight bytes are a head
with no units, and the head no longer tracks the club's division.

A unit:

```
+0   u32 player reference   pindex + 1 of the player record (0xffffffff = empty slot)
+4   u16 appearances
+6   u16 goals              0 on goalkeeper slots, highest on striker slots
+8   u32 rating total       sum of match ratings x 10; / appearances / 10 = average
+12  02 u32 natural positions     position bitmask
+17  02 u32 secondary positions   position bitmask, mostly 0
+22  02 u32 table position        the single bit the slot fills (1 = GK, 16384 = ST)
```

An empty slot carries reference 0xffffffff and zeros elsewhere (1,717 of 476,208 slots
on the ground-truth save, all in slots 11-17) and is not returned.

### tc_best_eleven_history_ls
The same list grammar as `tc_league_history_ls`: `03 01 'tad.' 04 00`, `u32 0`, `u32
list_count` (2,724), then `list_count x { u32 n ; n x u32 value }` and the trailer `u32
0, u32 509, u16 2`. Values are delta-encoded (`offset[m] = value[m] + value[m - 1]`,
past the dt head), and every dt record belongs to exactly one list. A list is one
club's tables in season order; the index stores no club uid. On the ground-truth save
St Albans City (uid 716) is list 685, one table per season 2023-2036, and its (table
type, kind) changes exactly where its league competition does.

## Usage

```python
import fmsave

with fmsave.open("career.fm") as save:
    rows = save.career_best_eleven()
    players = {player.uid: player for player in save.players()}
    for entry in rows:
        if entry.history_index == 685 and entry.season_year == 2036:
            name = players[entry.player_uid].name if entry.player_uid else "?"
            print(entry.slot, name, entry.appearances, entry.goals, entry.average_rating)
```

`player_uid` joins `player_reference` to `players()` through
`Save.history_player_references()`; players no longer in `players()` (most retired
players) keep None, so older seasons resolve less often (2036: 96%, 2023: 10% on the
ground-truth save). Those rows carry `player_name` instead, read by
`Save.history_people()` (see [history_people.md](history_people.md)): 98.1% of the
unresolved references are named on the ground-truth save, so a table names itself
without `players()`:

```python
name = players[entry.player_uid].name if entry.player_uid else entry.player_name
```
