# PLAN.md — fmhistory roadmap

Every session starts here. Work strictly top-down; do not start a new probe
until the item above it is landed (decoder integrated + validated + pushed) or
explicitly blocked with a checkpoint note in `docs/history-re.md`.

## Anti-digression rules

1. **The target is the career report**, not understanding for its own sake:
   `fmsave` must answer, per managed club and season — league position/results,
   honours, cup runs, awards, transfers, manager spells, best XI (names last).
2. An analysis script is allowed only if it changes a decoder decision. Every
   finding lands in a decoder or a `docs/history-re.md` checkpoint — never
   only in a scratch script.
3. Screenshots (`/mnt/SharedDownloads/BACKUP/screens/`) and the owner's k-world
   blog are **calibration only**: decode first, validate after.
4. Each landed decoder: model fields `unconfirmed`, tests, `docs/reference/`,
   status line here, commit + push.

## Definition of done

`Save.*` answers, per managed club and per season, from the save alone:

1. League: position, W/D/L/GF/GA/Pts
2. Honours: what was won, when
3. Cup runs: competition, seasons entered
4. Awards: who won what, which year
5. Transfers: arrivals/departures, wages
6. Manager: spell windows (start, end, club)
7. Best XI per season (player names in phase 3)

and the assembled **blind career report** produced from decoded data only,
validated against the k-world yearly reports (seasons 1–9) and screenshots.

## Phase 1 — make what's already decoded attributable

- [ ] **D1. `tc_league_history_ls` club-threading.** The league-history reader
      currently decodes 24-byte rows (339,481 on the GT save) but throws away
      the `tc_league_history_ls` index (1,473,106 B, `tad.` v4, count field
      `0x4c3a` = 19,514). Reverse it, thread rows to clubs, extend
      `LeagueHistorySeason` (or a by-club view). **Validate:** St Albans City
      (club 716) positions for every season vs the k-world blog.
      **Status (2026-10-10, checkpoint 5):** ls CRACKED and integrated — rows
      carry `history_index` (delta-encoded per-club lists, every row threaded).
      St Albans = list 351, every GT-pinned season matches; fills 2029/30 9th,
      2030/31 3rd. **Checkpoint 6:** `Save.club_league_history(uid)` pins a
      club's list from its league titles (honours → database id → title row);
      St Albans resolves from the save alone. Clubs without a post-import
      title stay unresolved. **Next:** validate vs k-world, then D2.
- [ ] **D2. Award names.** Map `career_awards`' `award_id` to award names from
      `award_man` (`tad.`, 842,938 B, partially mapped).
- [ ] **D3. Competition names.** Resolve competition_id → name for honours,
      cup entries and league rows (2821 competitions decode with names today;
      league tables carry `competition_name=None` — wire it through).

## Phase 2 — best-eleven, structurally (names deferred)

- [x] **D4. Integrate `tc_best_eleven_history_dt/ls`.** Grammar is pinned
      (checkpoint 2 in `docs/history-re.md`): 509-B cells = best-18 tables for
      a competition-season (id3), 18 units = players (internal pid space),
      ls = 2,724 bounded spell windows. Integrate model + reader + `Save.`
      method with ids documented as internal. **Outcome:** 1–6 + structural 7
      ⇒ assemble the **blind career report** and calibrate vs k-world.
      **Status (2026-10-10, checkpoint 4):** INTEGRATED as
      `Save.career_best_eleven()` (474,491 slot rows, players named via
      `history_player_references`: 96% for 2036). Framing corrected (the
      T/kind/id3 head closes its record) and ls decoded with the league
      delta grammar: one list per club, every record in exactly one list
      (St Albans = list 685, 2023–2036). **Next:** pin list → club uid.
      Retired players named via `Save.history_people()` → best-eleven
      `player_name` (98.1% of refs not in `players()`; history-re.md).

## Phase 3 — identities (names)

- [ ] **D5. `player_stats_hist_dt` (876 MB).** Pin the per-player record
      grammar; bind its key space to the best-eleven pid space (b59 confirmed
      the same pids occur there) and to `players()` uids. Names for best XI +
      award winners. Largest item — only start when D1–D4 are landed.
- [ ] **D6. Manager history ended spells + person refs.** Decode the ended-
      spell row shape in `tc_manager_history_dt` (only open spells decode
      today) and pin its person-reference encoding (not uid, not hof pid).

## Parked / closed (do not redo)

- Transfer fees: **closed** — no per-transfer fee store exists in the
  container (fee-hunt elimination arc, checkpoint 5 in history-re.md).
  Transfers themselves (arrivals/departures, named, dated):
  `Save.club_player_moves(club_uid)` (transfer_man checkpoint 8, 2026-10-10;
  127 bought reproduces exactly, sold/released split still open).
- `tc_best_eleven` id3=club: **dead** (checkpoint 2 corrects d8253b1).
- `tc_best_eleven` THE WALL / id3=competition-season / ls=spell-window:
  **dead** — artefacts of the off-by-one framing and undecoded ls deltas
  (checkpoint 4).
- Within-group (ls) cell overlap models: **dead** — the WALL measurement.
- Best-eleven pid→player via `players().uid`: dead — but pid = history
  reference = pindex + 1 (SOLVED 2026-10-10, `Save.history_player_references()`).

## Validation assets

- k-world yearly reports (blog.k-world.me.uk/football-manager/) — seasons 1–9
  expected values for St Albans; extract outside the repo, use as diff oracle.
- 421 screenshots — calibration only.
- Ground truth: `Karl Hudgell - UnemployedNew.fm`, St Albans City = club 716.