# Manager Career Reference

## Overview
`person_record_manager` keeps one career-statistics record for every
person who has managed in the game world, keyed by his **history reference** (the id
`Save.history_person_reference(staff_uid)` finds). The record holds the in-game
"Managerial Stats" screen: whole-career totals, the career's record transfer fees, the
longest and shortest club and national spells, job counts, and a current-job block.
FM26 added women's football: a record can hold a men's career, a women's career, both,
or neither (`ManagerCareerRecord.womens_career`, a `fmsave.ManagerCareerTotals`).
`Save.career_manager_records()` returns all of them as `fmsave.ManagerCareerRecord`;
`Save.manager_career(staff_uid)` picks one. Every field is registered `unconfirmed`.

## Section layout

```
03 01 'tad.' 1e 00 ...      head (version 30 on the ground-truth save)
human event logs            [u8 type] 15 ff×6 [u32 reference] 00 [u32 team] [date] ...
                            (variable length; `Save.manager_events`, see manager_events.md)
N records                   back to back from the logs' end to the trailer
ff ff ff ff                 trailer
```

A record is `[u32 reference][u32 reference]`, three slots, then a 152-byte current-job
tail. A slot is a `u8` flag and, when the flag is `01`, a 204-byte career block:

| slot | block |
|---|---|
| 1 | men's career (the fields of `ManagerCareerRecord`) |
| 2 | women's career (`womens_career`), same block layout |
| 3 | never seen filled |

So a record is 163 + 204 × (present blocks) bytes. The reader finds the first doubled
(non-zero) reference from which a walk of whole records lands exactly on the trailer.
That needs no help from the event logs, and `Save.manager_events` checks the logs end
where the records start. A section that does not end with the trailer raises
`CorruptSaveError`.

| save | records | men's only | men's + women's | women's only | neither |
|---|---|---|---|---|---|
| ground truth (career from FM24) | 11,945 | 11,945 | 0 | 0 | 0 |
| Fethiyespor (started in FM26, pre-season) | 5,631 | 3,235 | 1,776 | 458 | 162 |

On the FM26-started save the records are not all in reference order. The women's blocks
there name women's teams (Montpellier HSC Féminines, FC Como Women, Sassuolo
2018–2024 for a manager whose men's spells end in 2012).

## Record layout

Offsets are for a record with the men's block alone (the ground-truth save's 367 bytes);
other records are rebuilt into this shape to decode. Offsets from the record start. `date` = the 4-byte packed game date (`u16`, low 9 bits
day of year, high bits a time slot; `u16` year; year 1900 = unset). `team` = a
`Team.team_id`; `0xffffffff` = unset.

| offset | type | field |
|---|---|---|
| +0 | u32, u32, u8 | reference, reference again, `01` (men's block present) |
| +9 | fee (23 B) | `highest_fee_paid` (career) |
| +32 | fee (23 B) | `highest_fee_received` (career) |
| +55 | 4 × spell (13 B) | longest club, shortest club, longest national, shortest national |
| +107 | u64 | `money_spent` (£) |
| +115 | u64 | `money_received` (£; meaning open, see below) |
| +123 | u64 | `agent_fees` (£) |
| +131 | u32, u32 | `goals_for`, `goals_against` |
| +147 | u16, u16 | `cups`, `league_titles` |
| +151..+161 | 6 × u16 | unknown (`word_151` … `word_161`) |
| +163 | u16 × 3 | `games`, `wins`, `losses` (draws derived) |
| +169..+177 | 5 × u16 | unknown (`word_169` … `word_177`) |
| +193 | u16 | `awards` |
| +195, +197 | u16 | unknown |
| +199 | u16 × 3 | `players_bought`, `players_sold`, `players_released` |
| +209 | u8, u8 | `club_jobs`, `national_jobs` |
| +213, +214 | u8, u8 | women's and third slot flags (`00`) |
| +215 | job fee (21 B) | current job's highest fee paid |
| +238 | job fee (21 B) | current job's highest fee received |
| +260 | date | current job start |
| +264 | date | the save's current date |
| +269 | u32 | current job team (unset = no job → `current_job` None) |
| +286 | u64, u64 | current job money spent, received |
| +302 | u32, u32 | current job goals for, against |
| +318 | u16 | unknown (`word_318`) |
| +320 | u16 × 6 | current job cups, league titles, games, wins, losses, awards |
| +332 | u16 | current job players bought |
| +336 | u16, u16 | current job players sold, released |
| +340 | u16 | unknown (`word_340`) |

```
fee      [u32 player reference][date][u32 fee £][u16][u32 from team][u8][u32 to team]
job fee  [u32 from team][u8][u32 to team][u32 player reference][date][u32 fee £]
spell    [u8][u32 team][date start][date end]
```

Draws are stored nowhere: the game shows games − wins − losses. Player references
resolve through `Save.history_player_references()` (current players) or
`Save.history_people()`.

## Ground-truth save (Karl Hudgell, staff uid 2002143422, reference 328408)

All 11,945 records decode in 0.5 s. Against the Managerial Stats / profile screens:

| screen | decoded |
|---|---|
| 1 club job, 0 national jobs | `club_jobs` 1, `national_jobs` 0 |
| Longest time at club 5,253 days | longest club spell 18/7/2023 → 4/12/2037 = 5,253 days |
| Shortest time at club 0 days | `shortest_club_spell` None |
| Awards 19 | 19 |
| Players bought 127, total £101M | 127, £101,492,665 |
| Players sold 39 | 39 |
| Released 50 | 50 |
| Highest fee spent £23M, Corentin Dumas, 10/8/2036 | £22,937,564, ref 189608 = Dumas, 10/8/2036, St-Etienne → St Albans |
| Highest fee received £32.5M, Ben Young-Thomas, 9/8/20.. | £32,347,260, ref 280836 = Young-Thomas, 9/8/2037, St Albans → Shanghai Port |
| Agent fees £2.4M | £2,406,906 |
| Games 741, W 391, D 131, L 219 | 741 / 391 / 131 (derived) / 219 |
| GF 1589, GA 1059 | 1589 / 1059 |
| Cups 1, League Wins 3 | 1 / 3 |
| Current club St. Albans, same totals | team 603 (St. Albans City), start 18/7/2023, identical totals |

Population checks over all 11,945 records: wins + losses ≤ games everywhere; the
current-job games never exceed the career games; the longest club spell is never
shorter than the shortest (7,550 records with both); slots 3–4 hold non-club (national)
teams in 228 of 229 filled cases; the current-job team equals `Staff.team_id` for
1,096 of 1,138 staff whose record has one (the rest hold another staff role).

**Open:** the screen shows "Total Sold Transfer Value £0" while `money_received` holds
£97,733,168, so that field's meaning is unconfirmed. The unknown words on the ground-truth
record are `word_151` 5 (plausibly promotions: 5 since 2025), `word_155` 3, `word_159` 1,
`word_171` 21, `word_173` 42, `word_177` 18, `word_195` 13, `word_197` 5, `word_318`
2600, `word_340` 5; the screen rows below "League Wins" were not captured to pin them.

## Usage

```python
import fmsave

with fmsave.open("career.fm") as save:
    manager = next(person for person in save.staff() if person.is_human_manager)
    career = save.manager_career(manager.uid)
    print(career.games, career.wins, career.draws, career.losses)
    print(career.highest_fee_paid.fee, career.highest_fee_paid.transfer_date)
```
