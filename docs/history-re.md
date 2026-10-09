# FM26 history sections: reverse-engineering notes

Working notes for decoding the ~55 section types fmsave 0.5.8 does not yet read.
Ground truth: a real career save (`Karl Hudgell - UnemployedNew.fm`, build 26.3.2+2329565)
that started as an FM24 save imported into FM26, in-game date 2037-12-04, one club
(St. Albans City, save club uid 716, database unique_id 717).

## Section inventory (unmapped history content, by decompressed size)

| section | bytes | likely meaning |
|---|---:|---|
| player_stats_hist_dt | 876,453,136 | per-player statistical history |
| person_record_history_dt | 131,338,838 | per-person career records |
| injury_histories_dt | 42,729,512 | injury history arrays |
| tc_extended_club_records_history_dt | 30,306,680 | club records |
| tc_record_man | 22,737,139 | "tc" record manager |
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
| transfer_man | 53,264,554 | transfers |
| manager_manager | 5,735,697 | manager records (human manager among them) |
| humans | 27,604 | human-controlled people (player-manager etc.) |

Suffixes seen in save container: `_dt` (history/data-table), `_ls` (list), `_man` (manager).
`humans` header magic is `tad.`; `tc_manager_history_dt` header magic is `tmc.`
(headers: `03 01 <magic> <u16> <u32 count> <u16 ...>`).

## Decoded so far

### tc_manager_history_dt (tmc., 799,746 B, header count field 0x1f30 = 7,984)
- Header: `03 01 'tmc.' 02 00 30 1f 00 00 01 00`, records follow.
- Year words are u16 LE right in the data (e.g. `e6 07` = 2022, `98 00` = 0x98 = day 152
  ≈ June 1, `b6 00` = 182 ≈ July 1 — season start dates).
- 8 bytes of `0xff` (-1 sentinels) inside records: unset end refs.
- One u32 literal of our club uid (716) in the whole file => one record per spell?
  The spell row sits around offset 0x36c4:
  `00 0a 00 00 00 00 | cc 02 00 00 | b6 00 | e7 07 | 4e 6f | e7 07 | ff ff ff ff ff ff ff ff`
  i.e. something(0x0a), club_uid(716), day 182, year 2023, ..., followed by small u16
  fields `05 00 06 00 08 00 02 00` and further u32s (`b9 4a 00 00`, `ce 3b 00 00`, ...).
- Year-word frequency 2022..2037 ≈ 3,000-4,000 records/year → rows for every managed
  spell per manager per season, whole game world.

### tc_cup_history_dt
- Repeating 16-byte campaign rows:
  `<u32 club_or_comp_id> <u16 start_year> <u16 end_year> <u16> <u32> <u32 club_uid>`
  e.g. `4d 15 00 00 e8 07 e9 07 02 01 ff ff ff 00` (year pair 2024/2025 = season 2024/25?)
  with St. Albans (716) as one of the two clubs — 20 rows = 14ish seasons of cup entries.

### award_year_hist_dt
- Rows keyed on club uid 716 (29 hits) with small u32s after
  (`15 00 00 00`, `19 00 00 00` = 21, 25 — award index / year offset pairs).

### comp_history_dt
- 55-byte stride blocks around 0x1340fa..0x13420d, ascending years, St. Albans row each
  season (2032→2037 visible), two u32 fields per row (values 263..9,490) — likely
  points/position/goals-ish aggregates. Needs ground truth to pin down.

### hall_of_fame
- Records reference a person (0x2fd = 765) + club 716 + flag bytes — 4 St. Albans rows.

## Method notes
- Names live in `game_db`; history sections reference people/clubs by uid (u32 LE),
  often with the doubled/sound-header encoding fmsave uses for persons.
- `fmsave.open(save)._read_section(name)` gives the decompressed bytes — good enough
  for analysis; extracted copies in analysis workdir are not committed.
- For FM24-imported careers: game_db carries duplicated player records (old + new copy);
  see `src/fmsave/readers/player_scan.py` dedup fork (keep the latest copy, warn).