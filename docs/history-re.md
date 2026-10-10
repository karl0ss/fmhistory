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

## tc_league_history_dt / tc_league_history_ls — DECODED (simple data extraction)

The per-season past league-table store has been decoded using a simple data
extraction approach that reads all readable 24-byte league history rows from the
dt section. The decoder provides raw data for application logic to interpret as
needed, following the user's explicit request for data dumping rather than
intelligent reconstruction.

**Decoder Implementation:**
- Iterates through `tc_league_history_dt.bin` at offsets ≡ 8 mod 24
- Validates each 24-byte block as a readable league history row:
  - Season year in reasonable range (1900-2100)
  - Position < total teams (0-based indexing)
  - Total teams between 2 and 100 (reasonable bounds)
  - Wins/Draws/Losses not all 255 (indicates no data)
- Decodes valid rows into `LeagueHistorySeason` objects
- Returns all valid rows as a tuple
- Provides optional function to extract LS pointer data for advanced users

**Data Available:**
All readable league history data is now accessible via `Save.career_league_history()`:
- season_year, competition_id, position, total_teams
- games_played, wins, draws, losses
- goals_for, goals_against, points

This data can be combined with other career history decoders:
- Awards: `Save.career_awards()` - seasonal manager awards
- Cup history: `Save.career_cup_entries()` - cup runs per season  
- Hall of fame: `Save.career_honours()` - honours won per season
- Manager spells: `Save.career_manager_spells()` - job start dates

The simple extraction approach provides maximum flexibility for users to build
their own career chain reconstruction, performance analysis, or visualization
logic on top of the raw data.

### Where this stands (checkpoint 4, 2026-10-09: validated against ground truth)

Checkpoint 3's decoder landed but **had never run**: every struct format string
read `'<H>'`/`'<I>'` (stray `>`), so `decode_league_history` raised
`struct.error` on first call. Fixed; the reader now runs end-to-end and was
validated on the ground-truth save (analysis extracts under
`/home/karl/fm26-career/tmp_validation/`).

**Reader bugs fixed this round (all pre-integration, in
`src/fmsave/readers/career_history.py` + wiring):**
- `struct.error` from `'<H>'`/`'<I>'` format strings (7 call sites) — decode
  crashed on any input.
- `decode_awards` referenced undefined `winner_age` in both dedup keys
  (`NameError`); its own tests failed since the commit landed. Fixed (`age`).
- `Save.career_league_history` docstring claimed per-managed-club data; it is
  every club's rows. Rewritten. `LeagueHistorySeason` was never exported
  (`fmsave.__all__`, `models.__all__`) and `save.md :members:` was missing
  `career_league_history` — the doc test would have failed; all fixed, model
  docstring brought to record standard (Attributes + unconfirmed markers).

**Validation results (decoder output vs `docs/ground-truth.md`):**
- All five anchor rows decode exactly: 2024/25 VNS 1st (111 pts,
  GF 129 = news item's 2.80/game × 46) at dt 0x730a60 comp 708; 2028/29 L1 1st
  (P34 W20 D7 L7 67) at 0x775e98 comp 13; 2029/30 Championship 5th (76) at
  0x7815b0 comp 10; 2032/33 5th (75) at 0x7b1628; 2033/34 2nd (87) at 0x7c1360.
- Further rows found by table uniqueness (one row per (season, comp, pos)):
  2023/24 VNS 3rd at 0x720ce0 (season-2024 comp-708 table, 24 rows, complete
  3-point stats — checkpoint 2's "W21 D14 L9, 2-pt era" expectation was wrong;
  the imported 2023/24 table is stored recomputed at 3 points, pos 2 row reads
  W26 D8 L12 117-71 86 pts); 2025/26 NL 1st → season-2026 comp **707**
  (0x740270, W34 D7 L5 109; comp 708 carries the same season's other tables);
  2027/28 L1 7th at 0x7665e0 (comp 13 pos 6/18, W13 D13 L8, 52);
  2031/32 Championship 7th at 0x7a16e0 (comp 10 pos 6/24, 69).
- Every decoded club-relevant row satisfies W+D+L=P and Pts=3W+D. The season
  2025 comp-708 runner-up reads 96 pts (the news item's Worthing), as expected.
- Season word = season-**ending** year (2025 = 2024/25), on every anchor.
- No rows exist for the current (2037/38) season — it lives in the live
  `league_tables()` section, which is correct, and 2030/31 has a full comp-10
  table (the GT screenshot gap; club position not pinned by the screenshots).
- Volume: 339,481 rows kept of 348,756 grid slots on this save (97.3%);
  241,872 consistent 3-point rows + 75,151 consistent 2-point (pre-import);
  ~22,458 rows fail some arithmetic: 6,290 unplayed tables (P=255, zeroed
  results), 2,324 rows with P=255 sentinel + real W/D/L, 13,844 with
  W+D+L consistent but points fitting neither rule (mostly old-era comps
  122/123 rows from other record shapes), 51 rows with the null-year sentinel
  1900; 5,671 duplicate (season, comp, pos) keys (mostly pre-import, plus
  ~2.4k in import-era seasons). Post-import rows (2024+) all carry
  team_ref 0xffffffff — club attribution is only possible via ls, still
  unthreaded.

**Pinned in `tests/test_career_league_history.py`:** the 24-byte row grammar and
grid walk, sanity bands (season 1899/2101 rejected, pos>=size rejected,
sizes 1/101 rejected, all-255 results block rejected), the unplayed-table row
is kept raw, no points-rule enforcement (2-pt and neither-rule rows read
through), ls accepted-but-not-followed, ls pointer walk from offset 24.
Save-derived values are deliberately not committed (CONTRIBUTING guardrail);
the anchor offsets above are the re-verification recipe on the ground-truth
save.

### transfer_man (`tad.`) — structure 80% mapped (checkpoint 1, 2026-10-09)

Section: 53,306,010 B, 13-byte header `03 01 'tad.' 23 00 | u32@8 = 11,560,192`
(varies per save; record count proxy). Three zones + compressed tail:

| region | range (GT save) | contents |
|---|---|---|
| zone 1 | `0x0`–`0x10d0000` (~17.6 MB, clear) | family-A full transfer records (31,749) 0–4.6 MB + compact families (checkpoint 2): `11 00` wage ledger (stride 28), `03` (club,slot)→person registry (stride 27), `0b 00` negotiation/offer records (variable, 69 in one cluster) |
| zone 2 | `0x10d0000`–`0x2472e84` (~20 MB, clear) | 73-byte per-season records, seasons 2035/2036/2037 |
| tail zstd | `0x2472e84`–EOF (~15 MB) | **13 zstd frames** (magic `28 b5 2f fd`, FDS `04`, WD `50`), one per season, 2022–2034 (frame12 = 2034, decompresses when the **1 trailing footer byte is dropped**). 85 MB raw, same 73-byte record format. Frame0 (2,854 B raw) = season-2022 prologue. |

**73-byte season record** (1,433,706 rows total; chronology per year field:
2022: 39, 2023: 32,213, 2024: 124,931, … 2033: 97,736, **2034: 97,100**, 2035:
96,093, 2036: 95,968, 2037: 85,610; each zstd frame = one season's block).
Marker: `00 0X 0Y 07` — variants `00 01 01 07` (dominant), `00 01 00 07`,
`00 00 01 07`, `00 00 00 07` (variant byte 2 of 3 unknown meaning).

```
s+0..3   marker 00 0b 0c 07
s+4..7   u32 P1 = id<<8 | seq   (id space TBD; 716 appears — 972 rows ours)
s+8      00                     s+9..12  u32 P2 (nullable ff×4, ~47% null)
s+13     00                     s+14..17 u32 P3 (nullable, 43% null; == P4 62% of the time)
s+18     00                     s+19..22 u32 P4 (often == P3, "doubled value")
s+23..30 mostly 00              s+31..34 u32 P5 (97% ff null)
s+35     type byte (4 = 702/972 (72%) of club-716 rows; also 3:72, 1:71, 37:35, 24:23, 6:22)
s+36..39 u16 X (~11k–23k for mid-career rows, ~12.9k burst on whole-squad tables)
         + s+38..39 = u16 YEAR (calendar year of season; ff sentinels on non-year rows)
s+40..41 flags (01 00 / 01 01 / 32 00 / 10 00 …)
s+42..45 u32 P6 (club id: 716 = 1,659 rows)   s+46..49 u32 P7 (small counts)
s+50..53 u32 P8 (nullable)                    s+54..57 u32 P9 (nullable)
s+58..72 ff padding / extra
```

Per-season rows for a club form a contiguous table sorted by seq (seq 07→3d
etc. within a season). The whole-squad table snapshot pattern (X constant
12,981 over ~21 consecutive club-716 rows) shows P6=£/small counter,
P7=counter. **P1 id space**: `Club.uid` space confirmed as candidate (St.
Albans City uid 716/unique_id 717; `P1>>8==716` = 972 rows; `Club.uid=716`
verified via fmsave clubs()). Family-A idB (`+25`, id<<8|seq) is a different
space (Dumas = 0x12c305) — likely transfer-negotiation ids, NOT person uids;
**player save uids (Dumas 2,000,205,315, Y-T 2,002,095,850) never appear in
transfer_man at all** (0 hits for u32 of any player uid/unique_id).

**Checkpoint 2 (2026-10-09): compact families decoded; FEE located.**

1. **`(club<<8|seq)` is a club-internal 16-bit object handle (0–255 slot)**
   used consistently by *all* record families: 73B rows (P1), family-A (+3),
   and all three compact families. For club 716 the handle space = squad/
   staff slot numbers (e.g. Dumas's 73B rows all carry handle `0x2cc07` =
   `(716, 7)`). seq is NOT season-relative — the same handle recurs across
   season tables for the same player.
2. **`11 00`-family — per-handle wage/contract ledger, 31,520 records**
   (0x500000–0x1080000, offsets: club-716 records monotonic ⇒ one global
   chronological log): `11 00 | u32 handle | u8 f | u64 V1 | u64 V2 | 00 |
   u32 t4` (28 B). f = 4 (66%) / 7 (23%) / 5 (10%) / rare others;
   t4 ≈ 0. **V1 = money (weekly-wage scale), V2 = V1 × n with n an integer
   1–13** (44% n=1, n=2/n=3 common, ≥6 rare; a few non-integer outliers =
   phase/variant cases to re-verify). Working hypothesis: n = contract
   portion (months-remaining/12 or term). Wage histories reconstruct per
   handle: e.g. Y-T 18,700 → 20,020 → 32,500. Two clubs (2536, 716) carrying
   the *identical* (V1,V2) pair ⇒ shared/loan registrations appear twice.
   Wage-ledger values ~20–38k for club 716 = wage-scale (£k/wk), NOT fees.
3. **`03`-family — (club, slot)→person registry, stride 27, 82,782 records**:
   `03 | u32 handle | u32 person | 02 | u32 A | u32 B (ff = null) | u32 C |
   u32 D`. Persons in the 0x07f1–0x07f5 xxxxx space (same space as family-A
   +56/+60 person slots); 6,306 distinct persons, one person recurs up to
   677× ⇒ each record = one (person, club-slot) association, ~13 per person
   (≈ seasonal spells). A often 0/small, B mostly −1, C flag-ish (1/8/16/
   1,024/16,384...). Same (handle, person) recurs with varied A = updates.
   Semantics (staff vs player slots) unresolved.
4. **`0b 00`-family — negotiation/offer records (variable length; 69 B
   stride in its uniform cluster @0x92f9xx)**: `0b 00 | 01 00 | u32
   negotiation-id | u32 ...` then money/clause u32s, ff-nulls, f32 −1.0
   sentinels, dates. **THE FEE column lives here**: u32 23,000 = Dumas's
   £23M *exactly* (11 records in the 0x92f9xx cluster = one negotiation's
   snapshots); ref space ≈ 0–2,281 distinct negotiation ids.
   (Caveat: the naive "u32@+8 = fee" parse fails globally — +8 is flags in
   other layouts; layout is tagged/variable, needs TLV-style walking.)
5. **73B P2/P3/P4 reinterpreted (wage-like, not fee)**. Club-716 P2==P4 rows:
   506 rows summing 5.9M — far from GT 127 buys/£101M ⇒ P2-set ≠ buy rows.
   Per-year P2 sums (~150–600k/yr) = wage-bill scale. New fee+add-ons model
   (unconfirmed): Dumas 23,972 = fee 23,000 + add-ons 972; Y-T 32,604 =
   32,500 + 104 with P9 = 104,680 ≈ the add-on in different units; UI
   displays the base fee. Family-A record for (716,7) @`0x0037e074`:
   V1 = 11,704 ≈ the 2035-row P6 (11,714) — another wage-ish quantity;
   V2 = V1<<8 confirmed.
6. Dumas 73B row trio: @`0x1395264` (P6=11,714), @`0x17ac8e8` (P2=P4=23,972),
   @`0x210d85c` (P3=P4=23,972, P6=543) — handle (716,7) recurs across the
   three zone-2 season tables.

**Open (next session, in order):**
1. TLV-parse the `0b 00`-negotiation family (length prefix observed:
   u32 24 immediately before some `0b 00` starts; ref 912 record shows
   evolving money 23,812 → 24,771 = raised bids). Build (negotiation-id →
   fee, clubs, date) and join to 73B rows via handles/recid. Validate vs
   GT: 127 bought / £101M / 39 sold (Σ fees with fee > 0).
2. `03`-family D-field meaning; is it the (player, wage-history) anchor
   family-A +56/+60 ids resolve into?
3. `11 00`-family: confirm V1 = weekly wage, n = contract months/12
   (compare n against a known GT contract length if one exists in
   screenshots; none currently pinned).
4. Date/tick fields: 73B X, family-A V1, `11 00` seq (day-of-season?)
   — anchor vs GT dates (joined 18/7/2023, Dumas 10/8/2036, Y-T 9/8/2036).
5. Then AGENTS.md integration checklist for the three compact families +
   73B reader.

Scripts: `/home/karl/fm26-career/tmp_xfer/scan19-35.py`; artifacts:
`tmp_transfer/gt_tail/full_stream.bin` (105.5 MB; Z2 2035–37 clear first, then
frames 2022–34), `tmp_transfer/tail_rows.pkl` (1,433,706 rows, tuples
`(off, P1, P2, P3, P4, P5, type, X, year, fl, P6, P7, P8, P9, marker_variant)`).
Readers used for uid lookups: `players()` (Dumas uid 2,000,205,315 / unique_id
2,000,205,316; Y-T uid 2,002,095,850 / unique_id 2,002,095,851, club_uid
23,292,170); `clubs()` (`St. Albans City` uid 716, unique_id 717).
Also: upstream `rhiever.github.io/fmsave` docs have NO transfer reader — no
shortcut exists; our fork is ahead.

### transfer_man checkpoint 3 (2026-10-09): family-A map final; 0b type-1 layout + units

Scripts `scan61–69` + inline tests. Corrections and additions to checkpoint 2:

**Family-A (definitive field map — supersedes the earlier "fee" read).**
`03 | 13 00 | u32 handle | u16 A1@+8 | u16 A3@+12 | u16 A4@+14 | u32 flags@+16 |
u32 recid@+21 | u32 idB@+25 | u8 tag@+29 | ff×4 @+30 | persons u32 @+56/+60/+64`.
- `+21` = **recid** (global append-log id, 0→45,156 monotonic); `+25` = idB
  (0x12b000–0x140000 ≈ 1.2M, the 73B-row id at write time); recid/idB
  increment +1 in lockstep down the append regions (verified 22,969→22,980 ↔
  idB 0x12c31a→0x12c325).
- The 23,000 @`0x17e2e2` and 32,500 @`0x2e8761` are **pure recid coincidences**
  — family-A carries NO fees. Checkpoint 2's "fee" anchor was wrong; the fee
  evidence is the 0b kind-8 money ladder (below).

**0b type-1 negotiation records (`0b 00 01 00` header, 56,808 sites in
0x100000–0x10d0000):**
```
+0  0b 00 01 00   +4  u32 ref (2,276 distinct; ~25 recs/ref; some junk high)
+8  u32 money — CONSTANT per (ref, kind)
+12 u32 varied  — subject handle was WRONG: not per-ref const (24/2,276 refs
                  only), not a date (u16hi spans 0–39); semantics unknown
+16 u32 handle (club<<8|seq); 0xffffffff ≈ null (5,571×)
+20 u32 = ff (null)
+24 u8 kind ∈ {0,2,3,4,6,7,8,9}  (8: 24,677 · 6: 17,956 · 7: 11,024 · 3: 1,027
                                  9: 973 · 4: 968 · 0: 179 · 2: 4)
+25 f32 −1.0 (mostly)   +29 u32 bitfield   then `ff 63` tag + u16 f63 + tail
```
Record length = **69 + k×14 extension blocks** (69: 39,588 / 83: 9,678 /
97: 1,135 / 125 / 153 / 209 / 349 … up to 5.7k B containers). Extensions hold:
28-B `11 00`-embeds, 18-B `06 00`-items, count-prefixed lists, and **nested
`0b 00 <subtype> 00` sub-records** (subtypes 0x0a/0x10/0x16/0x2c/0x32/0x40).

- money@+8 ladders per (ref, kind): ref-1479 = {6: 13,416; 7: 22,042 (×28);
  **8: 23,000 (×11)**; 9: 23,959}; ref-912 = {6: 14,638; 7: 22,789 & 24,048;
  8: 23,780 (×11, + 25,094 ×2); 9: 24,771}. Kind-7→8→9 sequence per ref looks
  like a **negotiation evolving across stages** (wage → bid → settled?).
  Kinds 3/4 = global constants (3: 4,446 ×1,027 recs; 4: 36,300 ×968) —
  template/defaults, not per-deal values.
- `ff 63` u16 (f63): per-record wage-offer value; common round values
  (20,020/20,680/…) recur across hundreds of refs/handles ⇒ **NOT
  player-unique**. f63 ≈ money+500 pattern common (e.g. 20,880→21,380).
- `06 00`-items (18 B): `06 00 | u32 handle | u32 value24 | 01 00 | 6c 07 |
  02/00 00 00`, value >>8 descending 39,000→242 inside one list = a **valuation
  / player-list** (hypothesis: squad valuation ranking).
- Nested-0b run @ref-1479 kind-6 container (`0f 00 00 00` prefix, six
  sub-records): shared ref 1,479, value const 99,890, per-record second value
  varies (23,816/703,533/…).

**Money units: no raw £ anywhere** (u32 23,000,000 / 32,500,000 / 101,000,000
= 0 sites in the section). GT fees £23M/£32.5M map to stored **23,000/32,500 =
£k** (fees in thousands); the wage-scale values (11-record V1/V2, 0b money
18.7k–40k, 73B P2–P4) are raw-£ weekly wages. The exact collisions (23,000 as
both Dumas fee and common wage) stay unresolved until fee-vs-wage kinds are
untagged; current best split: **kind-8 money = fee (£k), kind-7 = wage offer,
kind-6 = valuation-related, +25 f63 = wage offer**.

**Dual-club `11 00`-embed pairs inside one 0b record = transfer registration
pairs** (same (V1,V2) at two clubs; e.g. ref-195: (2535,86)+(716,33) V1 20,680
V2 62,040; ref-844: (716,2515) wage ×3). 1,040 records have dual pairs, but
**only 5 touch club 716** — not the main attribution channel for 166 GT
transfers. Embed-based ref→club attribution in general = NOISE (zone 1 holds
several interleaved append streams; `11 00`-runs are physically interleaved,
so in-span "other club" attribution is untrustworthy; only exact
same-(V1,V2) two-club pairs are signal).

**Dead ends this arc (do not redo):** u32 length-prefix before `0b 00` starts;
+12 as subject-club handle (census shows 81 clubs, no 716) or as a date;
f63 as player-unique wage; embed-count club attribution; raw-£ money;
"family-A +21 = fee".

**Open (in order):**
1. `+12` semantics; ref→club/player attribution (test: does Dumas's
   negotiation = a ref ≠ 1,479 found via kind-6 `06 00`-lists, or via a
   (716,x)/(543,x) `+16` handle link?).
2. Confirm kind-8-money = fee: collect (ref, kind-8 money) for 716-links and
   check Σ ≈ 101,000 (£k) / count ≈ 127 / max 23,000.
3. Units cross-check: 23,048 cluster (@0x8550xx, ~12 sites) & ref-912 24,048 —
   "×048" fee-like second cluster?
4. `0f 00 00 00` nested-0b run semantics (99,890 const).
5. 03-family A/B/C/D semantics; `11 00` V2/V1 ratio = contract term?
6. Date anchors vs GT (Dumas 10/8/2036, Y-T 9/8/2036).
7. Then integration checklist (model/reader/`Save.` methods/tests).

Scripts: `/home/karl/fm26-career/tmp_xfer/scan61–69.py` (+ inline heredoc
tests in session log). Raw extract:
`/home/karl/fm26-career/sections/transfer_man.bin` (53,306,010 B, outside
repo).

### transfer_man checkpoint 4 (2026-10-09): fees are NOT in transfer_man; 73B P4 = wage

Follow-up scans 70–76 **correct checkpoint 2's "FEE located" claim**:

- **money@+8 of 0b records is wage-scale in every kind** (histogram across
  all 56,808: kinds 3/4/6/7/8/9 all span ~0.4k–41k, p50 ~20–24k; kinds 0/2
  are junk parses of other layouts with high-bitted values). There is NO
  fee-scaled population. kind-9 max 40,707 = the league's wage ceiling.
  Every (ref, kind-8) ladder holds **exactly 11 records at one constant
  money** (structural; same for kind-9's single record).
- Per-record kind ladder per ref = negotiation evolution: kind 6 (lowest,
  ~12.8k p50) → 7 (varied, ~23k, n≈10–25 per ref) → 8 (constant ×11) → 9
  (constant ×1, +~1k over kind 8). Interpretation (best current): wage
  demand drafts, agreed offer, settled wage.
- `+16` handles are NOT "the deal's club": each ref's records carry ~5+
  DIFFERENT clubs, one or two records each (57 refs touch club 716/717).
  Also found: **refs duplicated in identical-ladder groups** (38 pairs, one
  group of 4 — refs 566/575/738/37649) ⇒ a deal is recorded under multiple
  participant-side negotiation ids.
- **73B rows P2/P3/P4 = player money in raw £ (weekly-wage scale), NOT
  fees.** The 23,972/32,604 anchor rows (Dumas (716,7), Y-T (716,172)) are
  wage snapshots: 23,972/32,604 are COMMON values (155/186 rows across 64/74
  clubs — league-standard wage levels), and the "127 buys = 23,972 sites"
  coincidence is dead. Byte map re-verified on the correct region rows
  (P1=(716,7) at `0x006dc8e8`, P8=104,680 u32 at s+50; s+58..72 = all unset
  on club-716 rows; earlier "embedded 0b/6c07" bytes at those offsets were
  an off-by-0x10d0000 misread of zone 1 — scan75 fixed the offset mapping:
  pickle rows ≤2034 live in `gt_tail/full_stream.bin`, 2035–37 rows at
  `transfer_man.bin` offset +0x10d0000).
- Fee cross-check: u32 raw-£ 23,000,000 / 32,500,000 / 101,000,000 = 0 hits;
  f32 same = 0 hits. 23,000 in transfer_man = only the ref-1479 kind-8
  ladder (wage offer 23,000 ≈ Dumas's wage 23,972); 32,500 ×24 sites =
  wage offers (Y-T's ladder ends at 32,500 = his 73B wage 32,604 minus
  104). **GT's £23M/£32.5M transfer fees do not appear anywhere in
  transfer_man** — transfer_man is the wage/contract ledger, not the
  transfer-fee log. Fee hunt should move to the club-history sections
  (`non_pl_hist_dt` is the next candidate: it holds `6c 07`-tagged item
  streams with year-pair u16 fields (0x07d5=2005 … 0x07e7=2023) and two
  u32 101,000 sites — unrefuted £k-scale signatures).

**Open (carried from checkpoint 3, re-ordered):**
1. Ref→club/player attribution in 0b (kind-6 `06 00`-list handles; deal
   threading across duplicate refs).
2. Fee column: decode `non_pl_hist_dt` item grammar / club history sections;
   validate Σ ≈ 101,000 (£k) over 127 buys.
3. 73B P6/P7/P8/P9 semantics (P8/P9 = wage × weeks?).
4. 03-family A/B/C/D; `11 00` V2/V1 ratios.
5. Date anchors. 6. Integration checklist for the 73B-row reader (layout is
   proven; P-field semantics unconfirmed — integrate with all-unconfirmed
   statuses like `LeagueHistorySeason`).

### Fee-hunt elimination arc (checkpoint 5, 2026-10-09): value anchoring closed, no per-transfer fee log

Scripts `scan78–98`. Goal: locate the per-transfer fee store using GT anchors
(Dumas buy £23M 10/8/2036 = 23,000 £k; Y-T sale £32.5M = 32,500; club spend
Σ£101M = 101,000). **Result: the fee values are not recoverable by value
anchoring in ANY section — the exact-value collisions everywhere are
coincidences with per-club record constants (attendance/capacity) and wage
values.** A structurally-decoded transfer/fee section remains the only viable
path; candidates left: `person_record_history_dt` (131 MB, unprobed),
`person_db_changes` (21 MB), `non_pl_hist_dt` item grammar.

1. **`tc_record_man` 23,000/32,500 sites = attendance records** (7 of 9): shape
   `01 ff 01 | u32 | 01 <u8> | <u8> <u16 year>` with years 0x079b=1947 …
   0x07f5=2037. These are "record attendance" rows per club-season. Dead.
2. **Corrections.** The claimed "32,495,604 in non_pl_hist_dt" (checkpoint 4
   narrative) is WRONG — exact byte-find: 0 hits in every section (scan79/81).
   The `u32 101,000` sites in non_pl_hist_dt (2) are inside generic u32-soup;
   unaligned reads over dense u16 pair streams fabricate 0x02/0x08-tagged junk
   families (scan79b numpy sweep: every section dominated by 0x02000000-band
   junk) — **pure value anchoring is closed as a method**; only structural
   decode (find records first, then read their fields) can pin fees.
3. **`manager_manager` (5.8 MB, `tad.` v23) is NOT a transfer_man copy** (no
   73B grid, 0 zstd, few 73B markers): u32 id chains 450k–830k (likely manager/
   staff ids), compact-family-count-like bytes (`11 00`=5,034, `0b 00 01 00`=
   275, `03 00`=29,730) coincidental. Karl's (182,2023) spell date pair = 0
   hits. Uniform record motif `34 21 00 00 | 02 | … | u32 V | xx00 | yy00 |
   <u32 V2> | 02 80 04 00 00 02` with big companions (565k–709k) — semantics
   unknown. Not a fee store.
4. **`tc_extended_club_records_history_dt` (30.3 MB, `tmc.` v5) — ruled out as
   the fee log** (scan96/97/98): dense per-entity TLV id-stream sharing the
   tc_record_man record family (`4f 02`=591, `b9 05`=1,465 consts). u32 23,000
   ×14 and 32,500 ×22 both sit at an exact 0x350 (848 B) stride inside two
   tight blocks — per-season REPEATING constants in adjacent per-club/season
   records, stamped year words 0x07e7=2023/0x07e8=2024 (not 2036) — capacity/
   attendance-like per-season values, not the 2036 fee. u32 716 ×242 / 717
   ×1,526 (u16 716/717 ×1,132/2,196) but club uid 23,292,170 ×0. u32 101,000
   ×6 sites = recurring key 31,445 + companions 101,124/104,005, no 716/717
   link. Coincidence family, closed.
5. **`tc_history_dt` compact money rows (scan95)**: 1,662 rows of
   `1d 1a <u16 yr> 2c | u32 money | ff ff ff ff | u32 ≤4 | 0000 0000` — years
   2024: 1,263 / 2029: 215 / 2035: 184; values 8.7k–795k = per-club per-season
   aggregates (wage/finance scale), not fees (2035 block consecutive at 21 B
   stride 0x28aa20–0x28b182).
6. **`person_record_history_dt` / club-record screens note**: the UI's "record
   signing £23M / record sale £32.5M" may be computed from per-transfer
   records rather than stored as a separate record; per-transfer records
   themselves (dates + fees) remain unfound and are plausibly inside
   `person_record_history_dt` (a 131 MB per-person record store).
7. Person/club id space map (validated this arc): person save uids NEVER
   appear as u32 in any history/transfer section (Dumas 2,000,205,315, Y-T
   2,002,095,850 = 0 hits everywhere) — history sections key persons by their
   own small id spaces (e.g. hall_of_fame person uid 9,330,425 with plain-text
   names, 03-family person ids 0x07f1xxxx–0x07f5xxxx which are actually
   (X-tick,year) date packs). Club uid 23,292,170 appears in: award_year_hist
   (75), pl_hist (52, often as adjacent pairs), non_pl_hist (47), hall_of_fame
   (8).

**Revised fee-hunt open items:** person_record_history_dt structural decode
first (records with (X,year) date words + money fields keyed by person ids);
then club-finance monthly records (`finance_manager` is tiny (2,954 B) — the
monthly balances behind GT's -£1.2M→£131M arc live somewhere; "finances" is
not a section name — check `starting_club_debt_db`/game_db streams). Validate
against GT only after a reader exists.

### transfer_man checkpoint 6 (2026-10-09): 73B grid reader INTEGRATED

`Save.transfer_man_player_seasons()` → `Table[PlayerSeasonRecord]`
(`src/fmsave/models/transfer_history.py`, `src/fmsave/readers/transfer_history.py`,
wired in `_save.py` with cache key `table:transfer_man_season_records`; tests
`tests/test_transfer_history.py` — synthetic blobs, no save data in the repo).

Decoder design (proven on GT, scan100–scan109):

- **Framing**: clear season region = section header .. first zstd magic; then
  13 concatenated zstd frames (seasons 2022..2034, oldest first; clear region
  = newest 2035–2037). Frame boundaries are magic positions; a false magic
  inside one frame's compressed bytes ends a segment early, so a segment that
  fails to decompress is retried extended over the next magic. A frame that
  decompresses under none of a 0–8 trailing-byte drop sweep is skipped (final
  frame needs drop=1 — the 1-byte section tail; the others need 0).
- **Row read**: single `re.finditer` pass anchored on head word
  `00 [00|01] [00|01] 07` (NOT `[01]` — that regex character class matches the
  ASCII bytes, a bug that cost a session round; `[\x00\x01]` is required), then
  per-candidate validation: separator bytes at row offset +8/+13/+18 == 0, and
  season year ∈ 2005–2050 ∪ {1900}. Year 0xffff is REJECTED: on GT every
  ff-year candidate is one uniform junk family (club 0, slot 0/11/76, type 1,
  flags 0x01ff, tick 65280, value fields prefixed 0x0192/0x076c) — 89 hits in
  zone1 + 9 in zone2; accepting the sentinel admitted 98 junk rows per save.
- **Row type 33 wildcard**: all 1,320 t33 rows carry head id 0xffffff
  (club 16777215, slot 255) — club-free world-level money rows (£1k–£193k/wk
  in value_b). No club-uid gate in the reader: any u32 head id is accepted
  (a u24 field by construction); the year/separator fingerprint does the
  filtering.
- **Zone2 is not a pure butted grid**: row runs butt at stride 73 (~277,760
  clear-region rows) but ~238 ~1.1 KB story/TLV chunks (names, club strings,
  base64) interrupt them — hence per-row fingerprint validation over a
  store-wide grid walk (scan105; a grid-walk validator dies on the chunks).
- **Header is 12 bytes**, not 13: `03 01 'tad.' <u16 0x23> <u32 0xb06500>` —
  the u32 sits at offset 8 and the section content starts at 12.

GT validation: 1,428,558 rows, year histogram 2022:39, 2023:32,213,
2024:124,931, 2025:109,561, 2026:93,730, 2027:94,208, 2028:102,511,
2029:103,068, 2030:99,120, 2031:98,263, 2032:98,407, 2033:97,736, 2034:97,100,
2035:96,093, 2036:95,968, 2037:85,610 (matches the checkpoint-1 pickle counts
exactly); 3,225 distinct clubs (max uid 3,675); Dumas row and companion
reproduce; junk rows 0. Decode ~13.4 s, cached per Save instance.

Not integrated yet: zone1's compact families (family-A registrations, 11 00
wage ledger, 03, 0b negotiation — maps in checkpoints 1/3), and per-transfer
fees remain unfound (next: `person_record_history_dt`, 131 MB).

### person_record_history_dt — first survey (checkpoint 7, 2026-10-09; scans 110–118)

The next fee-log candidate structurally (131,338,838 B dt + 13,656,218 B ls,
both extracted). First-pass facts:

- **Header 12 B**: `03 01 'tmc.' 02 00 | b6 00 | e7 07` — the `tmc.` family
  (same tag as tc_manager_history_dt which uses `03 01 'tmc.' 02 00 <u32
  count> <u16>`), but here a u16 2023 word sits in the header (import/season
  mark) and no count u32 at that position.
- **ls** (`03 01 'tad.' 04 00 | u32 7,880` + 3,414,051 u32): NOT a sorted
  offset array — 1.76M descents; 2,192,338 entries land inside dt. In-range
  consecutive pairs sit 39–42 B apart. Hypothesis: per-person pointer lists
  (7,880 = a table-count field of some other layer). The >dt-range entries
  (1.22M) are a second value space — unexplained.
- **dt records**: 1,839,096 occurrences of separator `ff ff ff ff ff ff 00`;
  distances between separators are all multiples of 21 (42 dominant with 12,656
  hits in the first sample, then 84, 63, 21, 126, …) → a 21-byte atomic record
  unit; 42 B two-unit records dominate. Records carry:
  - a ref u32 (`ff ff ff ff` = none) after the separator,
  - a tick u16 + **year u16** — `c9 00 | e4 07 (2020)`, `de 60 | e9 07 (2025)`,
    `b6 00 | e7 07 (2023)` — and often a SECOND (tick, year) pair later in the
    record (contract from/till shape, unconfirmed),
  - **person uid literals**: u32 `0x77xxxxxx` — 10,158 aligned occurrences; one
    confirmed in a record body (`0x773b7628` at +20 of the record at dt[0x2a]),
    ~39.5k more unaligned (unaligned-sweep caution: some are noise),
  - money-like u32s: 645,833 / 505,193 / 605,228 in one record family —
    ≈ wage-annual scale (£/52 = £9.7k–12.4k/wk ✓ plausible per-season wage
    totals).
- **Year coverage**: u16 year words 2020–2037 present, counts rising
  2020:27k → 2037:336k (matchday-granularity whole-game accumulation, like
  tc_manager_history's append-only behaviour).
- **Person ids still half-open** (the key next arc): full uids for Dumas
  (0x7738b603) and YT (0x77558eea) have ZERO hits in dt; YT's low16
  (0x8eea = 36,586) hits 749 times in record-shaped contexts
  (`… <3d/7a/7b/6f> 00 00 | ea 8e 00 00 | <u32> | ff ff 00 …`), while Dumas's
  low16 (0xb603) hits 0, Dumas's low16±1 hit 5/111, and high16s hit
  (dumas 0x7738: 114; yt 0x7755: 179). Encodings differ per record family —
  records reach most persons via the **ls index**, with uid literals only in
  special records.
- **Fee-value dead end (extends checkpoint 5)**: 23,000,000 / 32,500,000 /
  101,000,000 (raw £) → 0 hits; 23,000 (£k) → 14 hits all in wage-shaped
  coincidences (checkpoint-5's pattern: (tick, year) records with ff-refs);
  32,500 → 3 hits, same shape. **The fee, if held here, must be reached
  structurally via a person-linked record — not by value.**

**Concrete next steps:** (1) segment the ls — map positions → ascending runs,
bind pointer → record offset, and count records per person; (2) pin the record
grammar from a clean run: diff the records 42 B apart at dt[0x2a..0x120],
confirm the 21-byte unit's field map, and read the `3d/7a/7b/6f/5e/21 00 00`
prefix as a family/type byte; (3) decode the YT family against the pinned
facts (sold 9/8/2036, £32.5M) — his 749-hit low16 family first; (4) resolve
Dumas through the ls index (not id literals) and dump every record in his
list; check one Aug-2036 record for a fee-shaped field.

### person_record_history_dt — record grammar progress (checkpoint 8, 2026-10-10; scans 119–122)

**ls structure** (scan119): maximal ascending runs = 1,650,811; sizes 2–3
dominate (1.14M runs of 2, 236k of 3, 231k of 1; largest 1,442). The ls mixes
dt pointers with out-of-range values (a second id space, unexplained) and
occasional small in-range values that point at non-record bytes — entries
where the target parses as a clean record are the person-pointer entries.

**Record skeleton pinned** (scans 120–122), byte map at the true head start
`h`:

- `[u32 refA] [u16 refB] [00] [u32 refC]` — an 11-byte head; all-ff
  (`ff ff ff ff ff ff | ff ff ff ff`) = no reference. NOT always sentinel:
  real refs appear (e.g. refA=0x43b7b seen in one record; the scan115 YT
  family carries real values in these positions).
- `[u16 tick] [u16 year]` at h+11/h+13 — tick ∈ day/season-tick range
  (1 = 1 Jan, 182/201 ≈ pre-season, 21–33k in-season), year 2020–2039 (2039+
  seen = likely far-future contract expiry sentinel, cf. transfer_man).
- `[u8 flag]` h+19 (01/02/05/08/15 seen), then ~19 zero bytes, then
  `[u16 c1]` h+39 (14/40/61/82/94/95/155/269/353 seen — small per-record
  counter, semantics open), `[u32 c2]` h+42 and beyond: sentinel
  `ffffffff` on most pointer-reached records; **the scan115 YT family has c2
  = person low16 and a following money u32** (645,833/505,193/605,228) — so
  the tail extends on non-sentinel records and carries money fields.

**Find-anchor alignment rule** (the reason fixed offsets drift): the head's
ff-run length varies with which ref fields are sentinel — the naive
`ff×6 00`-find lands 0 / +2 / +4 past the true head start depending on
whether refA or refB carry values. A robust parser must back-scan from the
`00` byte and test the three u32 candidate starts. (This is why scan122's
fixed +11/+13 fields read sane on some records and junk on others — the
underlying 42-B cycle with sentinel heads is real: 642k records of exactly
42 B, 236k of 84, 60k of 126 — 42-multiples dominate the 1.18M
sentinel-head population.)

**Person binding not yet made**: no ls run parsed yet had stable c2 (c2 is
sentinel ff on the all-clean records) — the person link must come either from
the non-sentinel-head records (refA/refB/refC holding club/person refs) or
from ls side structure (per-person list boundaries). YT's 749-low16-hit
family remains the best bridge: decode that family's records first.

**Dead ends this round:** the largest ls run's entries (0x2f0cb…, 4 apart)
point into non-record data — ls entries are NOT all record pointers; treat
head_ok-validated entries only, and never assume stride between ls entries
equals record stride.

**Next steps:** (1) robust head parser (back-scan from `00`, test u32
candidates at -11/-7/-4) to give every ls entry a canonical record start;
(2) re-run run-wise field dump with canonical starts — look for stable
c1/c2 per person and for money u32s in tails; (3) decode the YT low16 family
(`… c1 00 00 | <low16> | <money u32> …` records) and check for a 2036
record with an Aug tick matching his 9/8/2036 sale; (4) same for Dumas (in
10/8/2036, £23M) — if his fee appears here, the fee log is found and the
integration follows.

### Remaining plan (owner priority, 2026-10-09: DECODERS FIRST)

Standing direction from the owner: the priority is **finishing the missing
decoders in fmsave** — no tooling/site work until the data is complete, since a
site built on partial data is built on guesses. The screenshots remain
calibration-only (each decoder's output gets validated against them; that
validation is part of the decoder work, not a separate step).

**Gaps between what the site needs and what fmsave currently reads** (decoders
for league positions, honours, cup runs, awards, manager spells exist):

1. **transfer_man (53 MB)** — transfer records are absent from fmsave (only
   transfer *windows* exist). The site's next-widest gap after league history:
   fees, dates, player/club ids (127 bought / £101M / £23M Dumas /
   £32.5M Young-Thomas pinned by ground truth). **START HERE.**
   Status: **73B season-grid reader INTEGRATED (2026-10-09) —
   `Save.transfer_man_player_seasons()`**: model `PlayerSeasonRecord` +
   reader `src/fmsave/readers/transfer_history.py`; reference in
   `docs/reference/transfer_man.md`. GT: 1,428,558 rows / 16 seasons
   (2022:39 … 2037:85,610), Dumas (716,7) 23,972@2036 and companion (716,172)
   32,604@2036 reproduce exactly; 98 ff-year junk rows excluded by the
   year-acceptance filter; ~13.4 s decode, cached. All 16 fields unconfirmed.
   Transfer *fees* remain unfound (checkpoints 4–5: value anchoring closed;
   structural candidates next). Registration families (family-A, 11 00, 03,
   0b) still to integrate — see checkpoint 3 maps.
2. ~~Validation backlog~~ **DONE (checkpoint 4)**: anchors verified, reader bugs
   fixed, pytest pinned. Still open inside league history: identifying the
   club's rows for 2026/27 (League Two) and the Premier-era seasons (2034/35+
   20-club P38 comps: candidates 7, 22, 23, 51, 124, 128, 136, 159, 526, 3484-
   3486) needs the ls chain (ls node 0xa30f0 references the 2024/25 row, 0x11b88
   and 0x30bc0 the 2029/30 row; the (ptr, ptr) butted runs on either side are
   per-season region indexes, not club chains).
3. **player_stats_hist_dt (876 MB)** — per-player statistical history
   (appearances/goals per season); needed for player pages.
4. **tc_best_eleven_history_dt (13 MB)** — best XI per season.
5. **news (40 MB)** — season-summary news items (e.g. 6 May 2025 champions
   item) carry narrative + stats strings; good filler and cross-checks.
6. Lower priority: award_club_hist_dt (partly covered via award_year_hist
   club-award rows), tc_record_man (22 MB live-updating records, semantics
   unconfirmed — own project), tc_history_dt, tc_extended_club_records_history_dt.

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
- ~~Transfer fees in transfer_man are u32 ÷1000~~ **REFUTED (2026-10-09)**: the u32
  at family-A +21 is a global monotonic **record id** (0→45,156, file-order
  sorted, +1 runs of 27/170 records) — not a fee. Family-A copies of
  22,952/22,963/32,500 were red herrings (each value recurs at dozens of
  unrelated sites), but strong fee candidates DO exist in the 73B season rows:
  Dumas £23M = 23,972 (P2=P4), Young-Thomas £32.5M = 32,604 (P3=P4) — both
  slightly above the UI fee (add-ons? see transfer_man section).
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