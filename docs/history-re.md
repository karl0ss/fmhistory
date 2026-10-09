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

### tc_manager_history_dt (tmc., 799,746 B, header count field 0x1f30 = 7,984) —
#### spell-start rows INTEGRATED (`Save.career_manager_spells()`)
- Header: `03 01 'tmc.' 02 00 30 1f 00 00 01 00`, records follow (12-byte header).
- One record per manager in the game world: the wire pattern `00 0a 00 00 00 00`
  occurs 8,178 times against the header count of 7,984 (a handful of extra
  occurrences inside record bodies). Only the spell-start row is decoded:
  `<u32 club> u16 day u16 season u16 u16 same-season ff*8` — the all-unset tail is
  the shape a spell still open carries. Spells that HAVE ended use an undecoded
  shape, so `career_manager_spells` covers open spells only (195 rows on the
  ground truth, every one season 2022-2024 — an import-boundary artifact, since
  only pre-import-era spells carry that shape by 2037).
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
- Club references here use uid 717 for Stafford Rangers (club uid 717/unique_id 718)?
  no — see correction: `unique_id = uid + 1` holds for EVERY club (fmsave Club rows:
  St. Albans cid 716 unique 717, Stafford 717/718), so a u32 717 in tc_record_man is
  simply the club AFTER St. Albans in uid space (Stafford Rangers). The St. Albans
  rows are the 47 u32-716 hits in the same `… 00 08 01 00 00 00 …` record grammar.
- u32 payloads (record ids like 2593, 3486) appear as bytes only ~100-183 times each
  across 22.7 MB — u16 collision-level noise, so they are NOT raw literals there;
  likely indexes into offset-sized arrays or reconstructed at load.
- 12-byte record grammar in the appended end region (current season, ids ~235,300):
  `[u32 club][u32 id][u8 m][u8 n][0x4f][0x00]` — ids globally sequential across
  clubs (710…724 around club 716; a run of 115 records decodes: ids 235,286-235,400,
  modes m mostly 1, occasionally 2/3/4/5/7; n ∈ {50…100} in 5-steps). Club 716's 13
  records run 100→80 descending in 5-steps — a percentage meter (fan/board
  confidence?) updated per match: 13 records ≈ the matches to the in-game date.
  The `4f` byte is constant in this family; n's 5-step quantisation looks like a
  0-100 scale value. Semantics unconfirmed.
- The 47 scattered u32-716 hits elsewhere use wider record families (context shows
  `[u32 club][u16 ?][u16 year]` with years 2032-2037 around, and the club byte before
  the u32 varying) — a full tc_record_man decode is its own project.

### hall_of_fame — INTEGRATED (persons + honours decoders live in the package)

`src/fmsave/readers/career_history.py` (exposed via `Save.career_persons()`,
`Save.career_honours()` and the `fmsave career-history` command) reads:
- 5,413 person records with inline names, birth dates and person uids.
- 897 honours rows (99 pass only with looser tail rules; both keep club 716's four).

**Person records** (variable-length names, walked forward from every
`flag + u32 length` pair whose tail passes the bounds):

```
[01|00] u32 len1 "first" u32 len2 "last"
00 00 00 00                     <- 4 zero bytes
u16 dob_day_of_year             (0x4c = 76 = 17 March for the manager)
u16 birth_year                  (0x7c2 = 1986)
u32 shared/non-id               (0x1f6442 = 2,057,282 for the manager's FM24 copy,
                                 0xffffffff for some records — unset)
u32 person_uid                  (0x775648bf manager; 0x77554473 for the FM24 copy)
01 fd 02 00 00 07 03 03 ...     <- node id 765 + varying tail bytes
```

- Person blocks vary after the birth fields: some carry an 8-byte ff sentinel +
  `00 <u32 node>` instead of a ref/uid pair, and node ids other than 765 exist
  (f3 02 = 755 seen), so the forward names+fields scan keys on the birth-date pair,
  not on the node constant.
- Both manager records decode (Karl Hudgell, dob 76/1986, uids 0x77554473 and
  0x775648bf) alongside 5,400+ historical people (Dave Bassett, John Coleman...).

**Honours rows** — refined grammar (the earlier "3 03 00 tail" note only covered 101
of the rows): `<u32 club> 01 00 <u32 comp> fd 02 00 00 02 00 <u16 count> 01 [01 00 |
04 01 00] <u16s> <u16 season@node+13> <varies>`, 897 rows, 426 clubs. The season is
ALWAYS the u16 at node id + 13, and it is the year the honour was won (2025 = the
2024/25 season). The bytes after the season differ row to row (03 03 00 only 284 of
897; 00 00 00, 02 00 00, 0a 00 00 ... also appear) — do not anchor on a tail.
One arithmetic correction: comp 0x4e2bef = **5,123,055**, not 5,121,759 as an earlier
note had it.

- The manager's honours follow (4 rows, all club 716):

| comp id | season | matches ground truth |
|---|---|---|
| 0x4e2bef = 5,123,055 | 2025 (`e9 07`) | Vanarama NLS title (recreated-comp id space) |
| 0x1aa92 = 109,202 | 2025 | FA Trophy |
| 0x1aa91 = 109,201 | 2026 | Vanarama National League title |
| 0x0d = 13 | 2029 | Sky Bet League One title |

(The season year stored is the year the honour was won — the season's final year:
2025 = the 2024/25 season.)

- The value 0x8e56e3 = 9,331,427 is NOT a person id (shared by two unrelated
  persons). True person uids are the 0x77xxxxxx u32s.
- uid convention: hall_of_fame stores the manager uid as 0x775648bf; game_db stores
  0x775648be (fmsave person_id = selector − 1 offset). Search history sections for
  the +1 variant.
- Inline names exist here (`04 00 00 00`="Karl", `07 00 00 00`="Hudgell"), so person
  blocks in "tad." sections can embed names directly; other sections reference by uid.

### tc_cup_history_dt — FULL TABLE DECODED (18-byte rows)
- INTEGRATED (`Save.career_cup_entries()`, `fmsave career-history`): `03 01 'tmc.' 01 00`,
  then a flat 18-byte row array from offset 4:
  `[u32 club][u32 comp][u16 y1][u16 y2] 02 01 ff ff` — 165,490 rows, 99.95% with
  y2 in y1..y1+2 (same-year rows common, two-year spans rare). 61,034 rows carry
  club 0xffffffff = competition records without a club. `scripts/decode_cup_history.py`
  walks it.
- Club 716: exactly 20 rows, seasons 2024/25 → 2034/35 (none in 2026/27, 2029/30,
  2030/31 and none in 2023/24 — that season lives in the FM24 blob):
  comp 0x154d (5,453) → 13 rows; 0x154e (5,454) → 5; 0x16e3 (5,859) → 1 (2024/25);
  0x1617 (5,655) → 1 (2031/32). Multiple rows per season = per-round/per-stage
  entries, ids unresolved (competitions are NOT named in the save — see fmsave note
  on database_id maps).

### non_pl_hist_dt — manager spells (pre-career chain)
- Records: `01 0b 00 00 | <u32 subject> | <u16 day1> <u16 year1> | <u16 day2> <u16
  year2> | 01 00 6c 07` (1900 end-sentinel when spell not ended).
- St. Albans spells from FM24-era data appear here (`cc 02 00 00 | day/year …`),
  e.g. spells ending 2022 (`f5 00 e0 07 00 00 e6 07` = 272→356 2016, 2022…). This
  section carries the non-league/pre-import manager chains.

### award_year_hist_dt — INTEGRATED (`Save.career_awards()`, tag-bearing records)
- `03 01 'tmc.' 01 00` header then a stream of 26/30-byte records that sit directly
  against each other, placeholders between them:

  ```
  30-byte (winner + club):  [02][u32 flags][u16 tag][u16 year][u16 award][u32 winner]
                            [u32 club][u8 age][u16 a][u16 b][u16 c][u16 d][u8 e]
  26-byte no-club:         same minus the club u32, e.g. person-winner (player
                            award) rows — 2,314 of them, (year, award, winner) keys that
                            never collide with the club-bearing rows, real-age trailing
                            blocks (36/34/47/21/20...), award ids 4 and 0 the commonest,
                            tag 0xffff on 1,341 — and the club-winner history rows (the
                            winner is the club itself), e.g. (1937, 4, 716)
  26-byte placeholder:      [02][u32 0][u16 tag ff ff|8b][u32 ff*4][u32 ff*4][00*11]
                            — ~19,744 in the file
  ```

  Flags seen: 0x1, 0x40, 0x400, 0x4000. The tag u16 is 0xffff on most records; a
  minority carry a category value (0x8b, 0xaf, 0x9f...). The tail's first byte is the
  winner's age: all six manager rows carry 39/40/41/43/45/48 for seasons 2024/25→2033/34
  (manager born 1986). The tail u16s are unconfirmed (manager rows carry ~46-48 in
  tail[2], 84-129 in tail[3]; year-less player rows carry a different pattern).

- The (year, award) pairs are unique for 22,749 of the 22,894 club-bearing rows and
  2,269 of the 2,314 no-club rows; award ids are
  stable instances (0–7 band ×24–37 rows = monthly instances; 1,000–3,400 bands one
  row per (award, season); 4 and 405 = old honours running ~146–148 rows each since the
  1880s). The year is the season-ending year: 2031 = 2030/31, 2034 = 2033/34.
- The six manager records: winner id 328,408 = the manager in this section's space (also
  used in manager_manager.bin, person_record_manager.bin, transfer_man.bin). Award ids:
  144 = Vanarama National League Manager of the Year (2025/26), 103 = League Two MoS
  (2026/27), 101 = League One MoS (2028/29), 99 = Championship MoS in BOTH 2030/31 and
  2033/34 — "(twice)" per the biography ✓. Each id also appears exactly once in
  award_man as a definition record.
- The 2024/25 NLS MoS runner-up = a HEAD-LESS record (26 bytes: `[02][u32 flags]
  [u16 tag][u32 winner][u32 club][tail 11]`, no year/award head) — the tag
  0x8b row with winner 328,408, club 716, age 39. Head-less records stay out of the
  table because they carry no season year (a year-keyed table cannot place them).
  Under the reader's bounds they parse cleanly — 20,556 of them — and their age
  distribution is a textbook player-age curve (peak 27-28, tapering both ways), so
  these are the section's monthly **player** award rows: winner = player id, club =
  the winner's club. Tags: 0xffff on 2,099 rows and 178 small category values, the
  commonest 189 (×2,234), 187 (×878), 143, 131, 137, 170... Club 716 has 12 head-less
  rows (11 player rows + the manager's NLS row). Exactly ONE head-less row carries
  the manager id, so the manager's remaining ~12 monthly biography awards are NOT in
  this section — 19 biography awards vs 6 season rows + 1 monthly row here.
  (Earlier junk-B fears came from laxer bounds; with winner/club < 2.5M and the age
  check the parse is clean.)
- Pre-2023 = the import-time historical block (~1.47 MB, not year-ordered, no 2023+
  records), 2006/2023 = a pre-career player-award row; 2023+ = appended chronologically
  (club 716's rows: 2023:1, 2024:2, 2026:1×2..., all decoded).
- (2378, 4, 716) = the second club-history row; 2378 is above the reader's year bounds
  so that row is left out (the twin (1937, 4, 716) row is read). (2023, 1147, 716, 871)
  is read with tag 0x83 and club 871 — 871's meaning unresolved.

### award_man (tad., 842,938 B) — award definitions, partially read
- `03 01 'tad.' 0d 00` header; records `[6×00 01][u16 award id][u8 01][u32 count]
  [(u16 day, u16 year) presentation events...]` with (227, 2037)/(128, 2038) dates and
  `6c 07` (1900) null-year sentinels; ids up to ~3,400. The ids the award rows carry
  (99/101/103/144) each appear exactly once here as a record id — this joins the two
  sections. Award names are NOT stored: like competition names, they need an
  out-of-save map, here keyed on the award_man record id.

### award_club_hist_dt (23,984 B) — structure seen, not decoded
- Uniform ~37-byte records `[u16 year][u16 award][00][u16 club][ff-padded tail]`,
  years 2005→2037, ~640 records, no club-716 rows; ids and the club id space differ
  from award_year_hist_dt. Left undecoded (field level) for now.

## Method notes
- Names live in `game_db`; history sections reference people/clubs by uid (u32 LE),
  often with the doubled/sound-header encoding fmsave uses for persons.
- Competition names are NOT in the save (fmsave docs are explicit): the game renders
  them from the installed database. fmsave `competitions()` gives
  `Competition(id, database_id, name=None, stage_ids)` — any name mapping must come
  from the editor DB keyed on `database_id`.
- Club ids: `Club(uid, unique_id)` with `unique_id = uid + 1` for every club — the
  uid is one less than the editor's unique id everywhere (St. Albans 716/717,
  Stafford Rangers 717/718). Sections differ in which space they use: the club's
  own history rows use uid 716.
- Transfer fees in transfer_man are u32 **÷1000** (£32.5M sale found only as `32500`).
- Dates: many sections store (u16 day, u16 year) where day counts within a season
  starting ~1 July (182 ≈ 1 July), 1900 (`6c 07`) = null sentinel. Some serialized
  records embed dates as `… <u8> <u8> <u16 year>` word runs (year u16 last).
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