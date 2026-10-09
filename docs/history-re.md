# FM26 history sections: reverse-engineering notes

Working notes for decoding the ~55 section types fmsave 0.5.8 does not yet read.
Ground truth: a real career save (`Karl Hudgell - UnemployedNew.fm`, build 26.3.2+2329565)
that started as an FM24 save imported into FM26, in-game date 2037-12-04, one club
(St. Albans City, save club uid 716, database unique_id 717).

## Section header grammar

Every history section opens with `03 01 <4-char type tag>` (`tmc.` or `tad.` at least
so far), then tag/version-specific header words. fmsave does not parse these tags
(`_container.py` only opens the container itself, magic `02 01 'fmf.'`); the history
readers we write own this grammar.

## Section inventory (unmapped history content, by decompressed size)

| section | bytes | likely meaning |
|---|---:|---|
| player_stats_hist_dt | 876,453,136 | per-player statistical history |
| person_record_history_dt | 131,338,838 | per-person career records |
| injury_histories_dt | 42,729,512 | injury history arrays |
| tc_extended_club_records_history_dt | 30,306,680 | club records |
| tc_record_man | 22,737,139 | "tc" record manager (probably season table snapshots) |
| pl_hist_dt / non_pl_hist_dt (+_ls) | 14,308,688 / 5,749,108 | league hierarchy history |
| tc_best_eleven_history_dt | 13,466,112 | best XI per season |
| tc_league_history_dt | 8,370,152 | league history (past tables) |
| comp_history_dt | 4,554,063 | competition history |
| tc_history_dt | 3,192,197 | tc history |
| tc_cup_history_dt | 2,978,828 | cup history (campaign rows) |
| award_year_hist_dt | 2,579,646 | awards by year (29 St. Albans hits) |
| tc_extended_nation_records_history_dt | 2,256,752 | nation records |
| hall_of_fame | 951,133 | hall of fame |
| award_man / award_club_hist_dt | 842,684 / 23,984 | award definitions / club awards |
| tc_manager_history_dt | 799,746 | manager career history (all managers) |
| news | 40,657,499 | news items, contains readable strings |
| transfer_man | 53,306,010 | transfers |
| manager_manager | 5,735,697 | manager records (human manager among them) |
| humans | 27,604 | human-controlled people (player-manager etc.) |

Suffixes seen in save container: `_dt` (history/data-table), `_ls` (list), `_man` (manager).

## Decoded so far

### comp_history_dt — LAYOUT CRACKED (55-byte uniform rows)

File = `tmc.` header (52 B) + rows + tail. On the ground-truth save: 82,800 rows.

**Header (52 B):**
```
03 01 'tmc.' 03 00        (8 B)
u32 0
u32 0x768  = 1896         (earliest season in the table?)
u32 0xd6   = 214
u32 0xde   = 222
u32 0x1ab0d = 109,069
ff * 24                   (24 sentinel bytes, 6 x u32 -1)
```

**Rows:** stride is 55 B, but block start offsets VARY between regions of the file —
the section is a stream of variable-length groups, and within a group every row is
uniformly 55 B (one group showed 82,351 consecutive 55-gap record starts). A row:

```
[u16 y_a] [u16 y_b] [u16 small] [u16 y4]         8 B
[u32] * 11 slots                                44 B
[3-byte marker] [n] [type] [00]                  3 B   = LEAD of the NEXT record
```

Two record shapes, distinguished by the type byte in the 3-byte marker:

- **type 04** — league season rows (slot0+ = competition id / club list):
  e.g. season 1993/94: `12 | 1995 | 736 715 716 | ff...` (comp id 12, then clubs).
  The `xx 04 00` marker precedes each league row; 50,339 rows end in `00 04 00`.
- **type 02** — club/chain rows (club uid in slot 0):
  e.g. `716 | 2020 | 3486 | 263` (club 716, prev-year 2020, two reference ids).
  The u32s in slots 2-3 chain seasons (9498 and 4312 recur across rows as
  prev/next links); 22,317 type-02 candidate records found.

**St. Albans club-league block** (contiguous, offset 0x1340f2, ~30 rows, type 02):
covers seasons 1991 → 2021/22 and then stops — exactly matching the ground truth
that after the FM24→FM26 import the manager-history screens say "data only valid
from 26/12/2024". So comp_history_dt holds the pre-import (originally FM24) season
chain, and post-import seasons must live in other sections — the search target for
the 2023/24 onward league rows.

The u16 y_a/y_b pairs in the block: single-season rows show y_a==y_b (e.g.
2021/2021), multi-year spans show (1975,1976), (1977,1978), (1993,1994),
(1995,1996), (2018,2019) — so the pair is a spell start/end, not per-season rows.

### tc_manager_history_dt (tmc., 799,746 B, header count field 0x1f30 = 7,984)
- Header: `03 01 'tmc.' 02 00 30 1f 00 00 01 00`, records follow (12-byte header).
- APPEND-ONLY confirmed by diffing saves 10 matchdays apart (Nov 14 → Dec 4 2037):
  the old 793,856 B section is an exact byte prefix of the new 799,746 B one
  (+5,890 B of appended records, ~1.1 KB per matchday: rows for every new spell/result
  in the game world).
- Year words are u16 LE right in the data (e.g. `e6 07` = 2022, `98 00` = day 152
  ≈ June 1, `b6 00` = 182 ≈ July 1 — season start dates).
- 31-byte record model (from appended records and the managed-spell row @0x36c4):
  `[u32 id/ref][u16 day][u16 year][u16 counter][u16 year2][00 ff x8 sentinels][u16 x4][00 00 00]`
- The managed-spell row: `00 0a 00 00 00 00 | cc 02 00 00 (club 716) | b6 00 (day 182)
  | e7 07 (2023) | 4e 6f | e7 07 (2023) | ff ff ff ff ff ff ff ff | 05 00 06 00 08 00 02 00
  | b9 4a 00 00 | ce 3b 00 00 ...` — joined 18/7/2023 matches day 182/2023.
- Year-word frequency 2022..2037 ≈ 3,000-4,000 records/year → rows for every managed
  spell per manager per season, whole game world.
- Persons here are NOT referenced by their 0x775648bf-style uid or by the pids from
  hall_of_fame (searched, zero hits) — reference encoding still unknown.

### tc_cup_history_dt
- Repeating 16-byte campaign rows:
  `<u32 club_or_comp_id> <u16 start_year> <u16 end_year> <u16> <u32> <u32 club_uid>`
  e.g. `4d 15 00 00 e8 07 e9 07 02 01 ff ff ff 00` (year pair 2024/2025)
  with St. Albans (716) as one of the two clubs — 20 rows = 14ish seasons of entries.

### tc_record_man (tad., 22,737,139 B)
- Header: `03 01 'tad.' 18 00 | u32 5 | ff * 24 | u32 22 | u32 ... | u32 6 ...`
- Body is a stream of small records with a repeating 17-byte unit:
  `03 00 00 00 | 00 | 01 00 | 6c 07 | 01 00 | 6c 07 | 00 00 00 00`
  (u32 = 3, then u16 pairs where 1900 = the null-year sentinel from comp_history).
- NOT append-only: save-diff v03 (Nov 8 2037) → v02 (Nov 14) → Dec 3 → Dec 4 shows
  a mid-file insertion (+204 B between Nov 8 and Nov 14; +1,067 B Nov 14 → Dec 3;
  Dec 3 → Dec 4 byte-identical). Post-import seasons (2023/24 → 2037/38) accumulate
  here at matchday granularity.
- 11-byte appended event records (from the diffs):
  `84/85/8c/9e 87 00 00 | e4..f1 af 03 00 (incrementing seq u16 base 0xafe4) | 01|02 | value u16s (~20,3xx; 50/32 for zeroed) | 84 …`.
- Club references here use uid **717** (the database unique_id; 189 hits) rather than
  the save uid 716 (47 hits) — club-row records: repeating
  `cd 02 00 00 01 00 08 01 00 00 00 <u32 id> … <date u16s … f4 07 = 2036 / f5 07 = 2037>`.
- u32 payloads (record ids like 2593, 3486) appear as bytes only ~100-183 times each
  across 22.7 MB — u16 collision-level noise, so they are NOT raw literals there;
  likely indexes into offset-sized arrays or reconstructed at load.

### hall_of_fame — person records with INLINE names + honours rows (partially decoded)

`03 01 'tad.' 0a 00 ...`. Somewhere inside are self-contained person records:

```
[00|01] 04 00 00 00 "Karl" 07 00 00 00 "Hudgell"   <- u32 length-prefixed first/last names, inline
00 00 00 00
u16 0x4c (76)      <- dob day-of-year (76 = 17 March)
u16 0x7c2 (1986)   <- birth year
u32 ...            <- shared/non-person value (see caveat below)
u32 0x775648bf     <- PERSON UID (raw, this is the manager's)
01
fd 02 00 00        <- u32 765; appears in EVERY honours row and after each person block
                      (section-wide constant — node/type id, NOT a person id)
04 03 03 00        <- flags/count
```

- The manager's honours follow (4 rows, all club 716):

| comp id | season | matches ground truth |
|---|---|---|
| 0x4e2bef = 5,121,759 | 2025 (`e9 07`) | Vanarama NLS title (recreated-comp id space) |
| 0x1aa92 = 109,202 | 2025 | FA Trophy |
| 0x1aa91 = 109,201 | 2026 | Vanarama National League title |
| 0x0d = 13 | 2029 | Sky Bet League One title |

Row shape: `cc 02 00 00 | 01 00 | <comp_id u32> | fd 02 00 00 | 02 00 | <u16: 46/53/72/107> | 01 | <01|04 00> <u16> | <year u16> | 03 03 00` — the increasing u16 (46, 53, 72, 107) may be a running honour/award counter.

- The value 0x8e56e3 = 9,331,427 sits where an "internal person id" was expected BUT
  it is shared by two unrelated persons (manager b.1986 + a 2024-born newgen, "Azmil
  Mohd Ali") — NOT a person id. True person uids are the 0x77xxxxxx u32s.
- uid convention: hall_of_fame stores the manager uid as 0x775648bf; game_db stores
  0x775648be (fmsave person_id = selector − 1 offset). Search history sections for
  the +1 variant.
- Inline names exist here (`04 00 00 00`="Karl", `07 00 00 00`="Hudgell"), so person
  blocks in "tad." sections can embed names directly; other sections reference by uid.

### award_year_hist_dt
- 29 club-716 hits; rows are records containing club uid + season year u16 + award
  ids (`91 07 04 00` = award id 1937 + u16 4, e.g.). Person-765 (`fd 02 00 00`) hits
  = 87, same record family — so this section stores per-person/per-club award
  histories; record boundaries not yet pinned. Recurring u16 constants: 0x8b (139),
  0xaf (175), 0x8f (143), 0xa7 (167) — award-type/category tags (tbd).

## Method notes
- Names live in `game_db`; history sections reference people/clubs by uid (u32 LE),
  often with the doubled/sound-header encoding fmsave uses for persons.
- `fmsave.open(save)._read_section(name)` gives the decompressed bytes — good enough
  for analysis; extracted copies in analysis workdir are not committed.
- For FM24-imported careers: game_db carries duplicated player records (old + new copy);
  see `src/fmsave/readers/player_scan.py` dedup fork (keep the latest copy, warn).
- `scripts/decode_comp_history.py` walks comp_history_dt rows (stride 55 from offset 55)
  and prints rows matching a club uid.
- FM24-import artefact boundary: club season chains in comp_history_dt end at
  season 2021/22; pl_hist_dt carries the pre-career league chain 2004–2023 as a
  frozen, byte-identical blob across saves 10 matchdays apart (it is untouched post
  import). Anything from later seasons must come from other sections
  (tc_*_history / tc_record_man / tc_manager_history_dt).
- Manager uid in history sections = the game_db value + 1 (0x775648bf here); when a
  person's uid is 2002143422 in fmsave, search history sections for 2002143423.