# Manager Event Log Reference

## Overview
`person_record_manager` opens with one **event log per human manager**, before the
367-byte career records (`docs/reference/manager_career.md`). The log is the game's
highlights record of his career: signings and sales with their fees, club record fees,
honours, promotions, the awards he and his players won, notable matches and milestones,
each with a date, a sub-type and an importance. It is pruned by importance (one of the
manager's monthly awards survives, every season award does), so it is not a complete
history. `Save.manager_events(staff_uid)` returns one manager's entries as
`fmsave.ManagerEvent`, in file order. Every field is registered `unconfirmed`.

## Section head and framing

```
+0    03 01 'tad.' u16 version (30)
+8    u8 (01)
+9    u32 number of logs (1 on the ground-truth save)
per log:
      u8 (01)  u32 manager history reference  u32 number of TOP-LEVEL entries
      entries
then  the 367-byte career records, then ff ff ff ff
```

There are no length fields. Every entry is a 31-byte head plus a payload whose length
is fixed by the entry type; **type 18 is a group**: payload = `u32 child count`, that
many nested entries, then one closing byte. On the ground-truth save the walk reads 141
top-level entries (186 in all, 45 of them inside 15 groups) and ends exactly at byte
10,807, where the first career record (reference 7) starts. The reader checks that end,
the `0x15` mark and the reference on every entry, and raises `CorruptSaveError` on an
entry type whose length it does not know.

## Entry head (31 bytes)

| offset | type | field |
|---|---|---|
| +0 | u8 | `event_type` |
| +1 | u8 | `0x15` on every entry |
| +2 | u16, u32 | `unknown["head_u16"]`, `unknown["head_u32"]`: `ffff` / `ffffffff` on most entries; a pair such as (83, 271672) on 16 match / attendance / record entries; the same pair can recur (meaning open) |
| +8 | u32 | `reference` (the manager) |
| +12 | u8 | 0 |
| +13 | u32 | `team_id` (the manager's team) |
| +17 | date | `event_date` (packed game date, `_scan.decode_date`) |
| +21 | u16 | `sub_type` |
| +23 | u16 | `importance` (25..100) |
| +25 | u8 | 0 |
| +26 | u8 | `unknown["byte_26"]` (0; 8 on importance-85 sub-45 matches; 13 on players leaving; 23/24 on type 17; 5 on type 13) |
| +27 | u8, u8 | 0, 1 |
| +29 | u16 | `season` (the year the season starts) |

## Payloads

Offsets from the payload start (head offset 31). Lengths: type 1 18, 2 27, 3 10, 4 13,
5 3, 6 16, 7 12, 8 54, 9 18, 11 20, 13 13, 16 18, 17 21 bytes; 18 variable.

| type | decoded fields | other bytes seen |
|---|---|---|
| 1 honour / season result | +0 u16 `competition_id`, +4 u16 `value` | +2 u16 139 (nation); sub 1: +6 u32, +10 u32 people refs, +14 u16 (meaning open) |
| 2 move | +1 u32 `from_team_id` (unset → None), +6 u32 `to_team_id`, +10 u32 `player_reference`, +14 u32 `fee`, +20 date `effective_date` | +0 u8 0; +5 u8 0; +18 u16 (20/2/16 on staff appointments); +24 three 0 bytes |
| 3 club milestone | — | +0 u16 (ffff / 139), +2 u32 value |
| 4 promotion | +0 u16 `competition_id`, +10 u16 `to_competition_id` | +2 u16 139 |
| 5 manager award | +0 u16 `award_index` | +2 u8 1 |
| 6 player award | +0 u16 `award_index`, +3 u32 `player_reference`, +7 u32 `value` | +2 u8 1 |
| 7 attendance / stadium | — | three u32: stadium?, old, new (e.g. 44689, 11711, 14628) |
| 8 match | +1 u8 `goals_for`, +2 u8 `goals_against`, +18 u32 `opponent_team_id` | +4 u32 own team, +8 date, +13 u32 own team, +22 4 × u8 home/away goals, +28 u32 match competition, +36 u8 venue (1 home, 2 away), +42 u32 stadium, +46 u16 own league, +48 u16 opponent's league, +50 u32 (100s on milestone matches) |
| 9 player milestone | +0 u32 `player_reference`, +4 u32 `value` | +16 u16 139 |
| 11, 13, 16, 17 | — | see `payload` |
| 18 group | `child_count` | `unknown["group_tail"]` = closing byte (0..3) |

## Types and sub-types (ground-truth readings)

The decoded fields were checked against other tables; the readings of sub-types are
what that save's entries suggest:

- **1**: sub 1 = honour won; `value` equals `Honour.count` of the matching
  `career_honours()` row (46, 53, 72, 107). Sub 17 `value` 111 on 4/5/2025 = the
  2024/25 VNS points total (ground truth: 111 points). Sub 10 and 33 seen once each.
- **2**: sub 3 = signing agreed (`effective_date` = day it takes effect, when later);
  sub 12 = signings grouped under a sub-88 group (loans and young players from big clubs);
  sub 4 = new club record fee paid (Ruff £20,000 → Tshongo £8,250,000 → Dumas
  £22,937,564); sub 58 = new club record fee received (O'Farrell £1,324,615 → Finch
  £13,569,109 → Olagunju £15,857,448 → Young-Thomas £32,347,260); sub 15 = player left;
  sub 11 / 57 = staff appointed (their `club_player_moves` rows are record type 6); sub 30
  = a late-June entry naming an earlier signing — its date is the entry's, not the
  transfer's (Young-Thomas £2,700,000 logged 24/6/2035; he joined 3/8/2034).
- **3**: sub 5 job start, 42 job anniversary (5, 10 years), 86 / 14 money amounts.
- **4**: sub 2 promotion, competition 10 → 9 (2027), 9 → 8 (2029), 8 → 7 (2034).
- **5**: sub 23 monthly award (2181, December 2023), sub 22 season award.
- **6**: award won by a player of his club; `value` is the statistic the award row's
  tail carries (goals etc.).
- **8**: sub 45 (cup ties against higher-league sides), 7 (every 100th game: +50 =
  100 … 700), 97 / 95 / 43.
- **18**: sub 90 groups of sub-3 signings, sub 88 groups of sub-12 signings.

## Ground-truth validation (Karl Hudgell, staff uid 2002143422, reference 328408)

186 entries: type 2 × 77, 8 × 39, 18 × 15, 3 × 12, 1 × 7, 5 × 6, 9 × 6, 6 × 5, 16 × 5,
7 × 4, 17 × 4, 4 × 3, 13 × 2, 11 × 1.

- **Moves**: 72 of 77 type-2 entries have a `club_player_moves(716)` row for the same
  player and destination on the entry's date or its `effective_date`. The five others:
  three sub-30 entries (dated at season end), Kitić's first entry (a pre-agreement for
  1/7/2037 superseded by the £93,501 move on 20/1/2037, which matches), and Zedníček
  (effective 1/1/2038, after the save's date).
- **Fees**: 17 distinct fee-carrying moves (21 entries; 4 are record-fee duplicates):

| date | player | from | to | fee £ | sub |
|---|---|---|---|---|---|
| 21/6/2024 | Charlie Ruff | Chelmsford City | St Albans | 20,000 | 3 (+4) |
| 11/7/2024 | Harry Sidwell | AFC Wimbledon | St Albans | 19,000 | 12 |
| 26/9/2024 | Andre Burley | Oxford City | St Albans | 60,000 | 3 |
| 1/9/2028 | Danny O'Farrell | St Albans | Coventry City | 1,324,615 | 58 |
| 4/2/2030 | Richard Thomas (staff) | Mansfield Town | St Albans | 67,160 | 11 |
| 6/1/2033 | Sonny Finch | St Albans | Beijing Guo'an | 13,569,109 | 58 |
| 20/7/2034 | Reunsley Schoop | Werder Bremen | St Albans | 3,132,169 | 3 |
| 20/1/2035 | Gerson González | Eintracht Frankfurt | St Albans | 1,445,149 | 3 |
| 23/1/2035 | Saheed Olagunju | St Albans | Shanghai Port | 15,857,448 | 15 (+58) |
| 24/6/2035 | Ben Young-Thomas | Cardiff City | St Albans | 2,700,000 | 30 (joined 3/8/2034) |
| 23/6/2036 | Marvin Tshongo | Guingamp | St Albans | 8,250,000 | 3 (+4) |
| 10/8/2036 | Corentin Dumas | Saint-Etienne | St Albans | 22,937,564 | 3 (+4) |
| 20/1/2037 | Stefan Kitić | Ajax | St Albans | 93,501 | 12 |
| 24/1/2037 | Saverio Bonatti | Molde | St Albans | 5,000,000 | 3 |
| 21/6/2037 | Pedro | SEP | St Albans | 9,851,914 | 3 |
| 9/8/2037 | Ben Young-Thomas | St Albans | Shanghai Port | 32,347,260 | 58 |
| 7/11/2037 | Jiří Zedníček | SPO | St Albans | 6,465,898 | 3 (effective 1/1/2038) |

  Every one except the two flagged dates matches a `club_player_moves` row on the same
  day; Dumas and Young-Thomas (out) equal the career record's highest fees.
- **Manager awards**: 2181 (1/12/2023, monthly) and 144 / 103 / 101 / 99 / 99 in seasons
  2025 … 2033 = the five `career_awards()` winner rows (season_year = `season` + 1). The
  2025 runner-up award (2177) is not in the log.
- **Player awards**: 2175 (ref 66672, 18), 2186 (63174, 29), 371 (209035, 23), 2190
  (208514, 3) match `career_awards()` rows with the same winner and that number in their
  tail; 370 (Sonny Finch, 25) also decodes.
- **Honours**: sub-1 entries 25/3/2025 (comp 708, counter 46), 11/5/2025 (151, 53),
  18/4/2026 (150, 72), 18/4/2029 (9, 107) = the four St Albans `career_honours()` rows by
  counter (competition ids are in a different id space there: 5123055, 109202, 109201,
  13).
- **Groups**: 15 groups, every child count equals the entries that follow.

**Open:** the head pair at +2, `byte_26`, the group closing byte, the type-1 people
references (+6/+10) and u16 (+14), the payloads of types 3, 7, 11, 13, 16, 17 beyond the
readings above, what competition id space the log uses (on this save the match entries'
own-league field runs 708 → 150 → 10 → 9 → 8 → 7 with St Albans' divisions: VNS, VNL,
League Two, League One, Championship, Premier League; 151 = FA Trophy by its honour date;
667 unresolved), and whether
the log layout holds on other builds and with several human managers.

## Usage

```python
import fmsave

with fmsave.open("career.fm") as save:
    manager = next(person for person in save.staff() if person.is_human_manager)
    for event in save.manager_events(manager.uid).where(event_type=2):
        if event.fee:
            print(event.event_date, event.player_reference, event.fee)
```
