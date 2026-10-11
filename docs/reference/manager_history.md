# Manager History Reference

## Overview
`tc_manager_history_dt` stores one 31-byte row for every spell a manager has ended in
charge of a team since the game's history began (caretaker spells included);
`tc_manager_history_ls` groups the rows into one list per team. `Save.manager_spells()`
returns them as `fmsave.ManagerHistorySpell`, names each list's team where a manager's
career record (`person_record_manager`) pins it, and adds every manager's current job as
an open spell. `Save.manager_spells(staff_uid)` returns one person's spells. Every field
is registered `unconfirmed`. Reader: `src/fmsave/readers/manager_history.py`.

## dt layout

```
03 01 'tmc.' 02 00          8-byte head
N × 31-byte rows            appended in the order spells end (append-only)
```

| offset | type | field |
|---|---|---|
| +0 | u32 | `reference`: the manager's history reference (`ManagerCareerRecord.reference`) |
| +4 | date | `start_date`; day 0 (`00 00 e7 07`) or year 1900 = null (running before history began) |
| +8 | date | `end_date` |
| +12 | u32 | `unknown["word_12"]`, mostly `0xffffffff` |
| +16 | u32 | `unknown["word_16"]`, mostly `0xffffffff` |
| +20 | u16 ×3 | `wins`, `draws`, `losses` (`games` = their sum) |
| +26 | u8 | `kind`: 10 (8,261 rows, median 17 days / 2 games: caretaker-like), 2 (8,405), 3 (5,639), 0, 6, 5 |
| +27..+30 | u8 ×4 | `unknown["byte_27"]`..`["byte_30"]`: small counters, meaning open |

`date` = the 4-byte packed game date: `u16` with the day of year in the low 9 bits and a
time slot in the high bits, then `u16` year.

## ls layout

The shared history-index grammar (as `tc_league_history_ls`):

```
03 01 'tad.' 04 00
u32 free count (0), free entries
u32 list count (6,004 on the ground-truth save)
per list: u32 n, n × u32 values      row m at dt offset 8 + value[m] + value[m-1]
u32 0, u32 31 (row size), u16 2      trailer
```

Lists are numbered in the order their first row was written, so the number carries no
team identity. Every row is in exactly one list; the reader raises `CorruptSaveError`
when the index does not list every row exactly once, points between rows, or names
another row size.

## Naming a list's team
The index stores no team id. A manager's career record keeps his longest and shortest
club and national spells (team, start, end): when exactly one list holds a row with that
manager, start and end, the list is that team's. Lists two windows give different teams,
and teams two lists claim, stay unnamed (`team_id` None).

## Ground-truth results (`Karl Hudgell - UnemployedNew.fm`, 2037-12-04)
- 25,798 ended spells in 6,004 lists; 2,551 lists named (no conflicts), covering 21,564
  ended spells (83.6%). Unnamed lists are mostly one-row lists (3,080).
- Independent check against an older snapshot (`(v03)`, 2037-11-08): 230 rows were
  appended since. Naming lists from the snapshot-era rows only, 190 of the appended rows
  fall in a named list and belong to a manager whose current job in the snapshot is
  known: all 190 name that job's team (0 disagreements; 14 fall in unnamed lists, 26
  managers held no current job in the snapshot).
- Per-spell results reconcile: for the 5,724 managers whose rows plus current job sum to
  their career games, the summed wins and losses equal the career record's every time.
- Career-record windows reproduced exactly (team, start and end): longest club spell
  7,525 / 8,537 (88.1%), shortest 5,353 / 7,462 (71.7%). (The team half is partly
  circular, since these windows name the lists; the dates are not.) The misses are
  spells with no row: longest 848 ended before 2023, 127 began before the history and
  ended in it, 29 have no end date in the window, 8 other; shortest 1,521 / 397 / 69 /
  122. Among the "other" cases a caretaker spell that became the permanent job shows up
  as one row starting at the permanent appointment: no row is written for the caretaker
  part.
- The human manager (ref 328408): no ended spell; one open spell, St Albans first team
  603 from 2023-07-18, 741 games 391-131-219.
- 16,530 managers have at least one spell; 6,387 have more than one.

## Not covered
- Spells that ended before the history began; the career record's longest/shortest
  windows are the only trace of those.
- A caretaker spell that turns into the permanent job appears to write no row of its own
  (seen in examples, not counted).
- Teams of lists no career window pins (16% of the ended spells).
