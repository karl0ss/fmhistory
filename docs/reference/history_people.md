# History People Reference

## Overview
History sections (best elevens, award winners, transfer and person-record rows) name
people by a save-wide **history reference**. For a current player that is his record's
`pindex + 1` (`Save.history_player_references()`), but a player who retires or is
released leaves `players()` while keeping his reference in every history row.
`Save.history_people()` names those people from what the save keeps of their objects in
`game_db`, one `fmsave.HistoryPerson` per person; every field is registered
`unconfirmed`. `Save.career_best_eleven()` uses it to fill `player_name` on rows whose
`player_uid` is None.

## Layout

A person's `game_db` object closes with a 12-byte header:

```
[u32 reference][u32 unique_id][u32 unique_id]     unique_id = uid + 1
```

Objects are stored in ascending reference order (on the ground-truth save, every
closing header found rises in reference with offset, without exception), so the
headers of people who are not players lie between two players' closing headers, with
a reference and a unique id strictly between theirs. The reader finds the players'
headers from the player scan, then, gap by gap, searches each in-between reference
and keeps its first occurrence whose next two words are equal and in the unique-id
bracket.

The name is read from the bytes right before the header, in one of three forms:

```
stub (18 B)              10 00 [u32 first-name id][u32 surname id][4 flag bytes][u32]
common-name stub (14 B)  10 01 [u32 common-name id][4 flag bytes][u32]
object                   a full person object: the last person block that validates
                         between the previous closing header and this one
```

Name ids index the `game_db` name pools players use. The flag bytes (e.g. `01 22 58
10`) and the trailing word (mostly 4) are undecoded. The object form takes the
**last** validated block: the first can belong to an object between the two headers
whose own header was not found.

## Ground-truth save

- 632,378 people in 8.7 s (after the player scan): 437,582 stubs, 18,487 common-name
  stubs, 176,309 objects; 45,480 unnamed (objects whose block does not validate).
- Hall-of-fame check: `career_persons().person_uid` equals `unique_id`, and all
  4,539 people named here who also hold a hall-of-fame record agree by first name
  and surname (the other 49 joined people are unnamed here).
- Best eleven: 63,684 of the 64,886 references `players()` does not cover are named
  (98.1%; 98.2–99.4% per season).

## Usage

```python
import fmsave

with fmsave.open("career.fm") as save:
    names = {person.reference: person.name for person in save.history_people()}
    for entry in save.career_best_eleven():
        if entry.history_index == 685 and entry.season_year == 2024:
            print(entry.slot, entry.player_name or entry.player_uid, entry.appearances)
```
