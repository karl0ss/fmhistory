# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `tactics()` reads stored preset and alternate tactics and checks every team's declared list, including empty lists.
- `tactics()` and `set_pieces()` read additional continued careers. Incomplete tactic lists cannot borrow records from the trailing tactic library; validation now includes `tactic_records_count_matching`.
- `stadiums()` stops at the table's closing header, avoiding a spurious ground row.
- `staff_lists()` keeps valid members when a list contains an empty reference.
- Player and staff readers recognize complete allocated-person header variants, recovering their contracts and season-stat joins. Staff discovery excludes contract-like bytes inside closed club objects.
- Contract assembly no longer presents retained records without substantive terms as a current paid contract when registration is explicitly absent and no independent current end date exists. Raw contract chains remain available.
- `competition_rules()` reads an additional interstitial record shape when the complete declared calendar can be decoded, recovering previously missed rounds.
- `competition_rules()` recognizes complete indexed calendars without treating an unidentified word as a fixture count. The legacy `match_count` field retains its raw value. Calendar retries wait for following frames when more bytes are needed.
- `fixtures()` recovers missing scores from additional counted match summaries, preserving existing results and rejecting ambiguous or conflicting joins.
- `fixtures()` recovers previously skipped calendar rows through complete counted paths between recognized records, including paths split across frames. Calendar selection retains its original anchors; inferred neutral-venue flags use the additional fixtures.
- `fixtures()` decodes scores stored in counted packets belonging to the following calendar record. Physical ownership distinguishes duplicate-looking fixtures; existing scores, conflicting evidence and unplayed matches remain protected. Optional final scores are handled separately from penalty figures.
- `fixtures()` reads played status from each fixture's prefix when a complete sibling path proves ownership. This corrects shifted statuses, retains terminal fixtures without borrowing bytes from the next collection, and recovers omitted unplayed fixtures.
- `player_match_stats()` walks complete counted histories with the correct performance-record length and requires every declared team list before returning matches. Missing team references no longer hide complete sibling lists. Unrelated player fields no longer appear as matches, incomplete histories fail an independent completeness check, and malformed nested headers cannot trigger repeated suffix scans.
- `player_match_stats()` locates each player's owned nullable history field. Validation accepts empty output when every player explicitly has no stored history, while incomplete or unresolved histories remain detectable.
- `suspensions()` reads entries with an attached match record when their entire counted list is structurally complete.
- `sponsorships()` reads each club's primary counted list, including explicit empty lists, and retains valid historical contracts predating the old scan's year cutoff. Later sponsor-shaped data cannot replace an empty or invalid primary list.

## [0.5.3] - 2026-09-29

### Fixed

- `set_pieces()` retains previously missed routines, including multiple user routines in a slot, and checks that all routine groups were read completely.
- `players()` decodes structurally complete records with zero current ability, keeping their contracts out of the staff reader.
- Fixture validation distinguishes stored stub-team references from missing club joins without lowering its join threshold. The corresponding checks are now named `set_piece_blocks_complete` and `fixture_club_teams_resolved`.

## [0.5.2] - 2026-09-29

### Added

- `Club.unique_id` helps match clubs across separate careers. `Club.uid` still joins records within a save.

### Fixed

- `stages()` and its dependent readers can find stage tables further back in continued careers.

## [0.5.1] - 2026-09-28

### Added

- `player_season_stats()` rows now include the per-90 and percentage figures the game shows, such as `expected_goals_per_90`, `pass_completion_percent` and `save_percent`: 44 in all. They are worked out from the counts when read, so they add no memory, and every export includes them.

## [0.5.0] - 2026-09-28

### Added

- `player_season_stats()` and the `player-season-stats` export table: each player's stats for the current season, as the squad and player screens show them. There is one row per competition type (league, cup, continental, international, non-competitive, overall, and two calendar-year totals) for each team the player played for. It covers 56 stats, among them minutes, rating, xG, xA, shots, passes, tackles, distance, sprints, cards and goalkeeper saves.

## [0.4.8] - 2026-09-28

### Fixed

- Saves from a career started before a game update open again: fmsave checked the build the career was started on as well as the build that saved the file, and failed with "game_info does not match build" whenever the two differed.
- `stages()` and every reader joined through the stage table find the table on a save that holds more data after it than 2 MB. The search now widens to 16 MB before the table counts as missing, and a save whose table sits near the end pays for the first 2 MB alone.

## [0.4.7] - 2026-09-27

### Fixed

- `finances()` no longer labels every month one month early on a save taken on a month's last day.

## [0.4.6] - 2026-09-27

### Fixed

- `finances()`, `sponsorships()` and `facilities()` no longer come back empty on a career saved
  in its first two months, when each club keeps only one or two months of finances. A club that
  starts keeping finances partway through a career is now read in its first two months as well.
  A series that short is read only where every month balances and money moved in at least one
  of them. Every row read before is read exactly as before.
- Saves from a smaller game database, such as FM26 Console saves, now give most competitions a
  database id. `competitions()` had given one to about 1 in 60 of them, and `fmsave validate`
  reported the competitions reader as failed. Saves from a full database read exactly as before.

## [0.4.5] - 2026-09-26

### Fixed

- Saves whose in-game year is close enough to 2048 that the years fmsave searches reach it,
  from 2040 on for fixtures, no longer fail with kick-off years that "do not share one high
  byte". That stop blocked `fixtures()` and `league_tables()`, and `player_match_stats()` would
  have failed the same way from 2047 on. Saves that already opened read exactly as before.

## [0.4.4] - 2026-09-26

### Added

- `Player.unique_id` and `Staff.unique_id`: each person's Unique ID in the game database. It is the
  same in every new game started from that database, so it is the key for matching people across
  separate careers. The game can give the id of a person it has deleted to one it creates later.
  The column comes right after `uid` in exports.

### Fixed

- `Player.uid` and `Staff.uid` no longer claim to be the game database's id. They are the Unique
  ID of the person stored just before, so they differ between new games started from the same
  database. Their values are unchanged, and every table still joins on them.

## [0.4.3] - 2026-09-25

### Fixed

- Saves whose last `game_info` build number sits a few bytes away from where fmsave expected no
  longer fail with "game_info does not match build". This showed up on Windows saves, including
  FM26 Console saves. Saves that already opened read exactly as before.
- Saves with a smaller game database, such as FM26 Console saves, no longer fail with a name pool
  that has "fewer than the 50000 a full save holds". That stop blocked `players()`, `contracts()`,
  `staff()` and every other reader that resolves names. Each name entry's id and length are still
  checked.

## [0.4.2] - 2026-09-24

### Fixed

- Saves whose stage table can also be read one byte early no longer fail with a stage id that
  "appears in two stage rows". That misread blocked `stages()`, `competitions()`, `fixtures()`,
  `league_tables()` and `player_match_stats()`, and it showed up on saves with many playable
  nations. Saves that already opened read exactly as before.

## [0.4.1] - 2026-09-21

### Fixed

- Pre-Continue saves now use the summary date when the normal in-game clock is absent.
- Fresh saves no longer fail reader checks for their player attribute distribution, complete join
  dates, or match records without statistics.

### Changed

- Local whole-save analysis is supported for single-player careers; `--all` remains explicit,
  save-derived data stays out of the repository, and support never accepts save uploads.

## [0.4.0] - 2026-09-18

The first public release. Nothing before it was ever published, so this entry says what fmsave is rather than what changed.

### Added

- `fmsave.open(path)`, a read-only view of a Football Manager 26 save, used as a context manager. `Save.info` carries the game, the build, the database version and the in-game date.
- Twenty-six readers, each returning a `Table` of records: `players()`, `contracts()`, `suspensions()`, `staff()` and `staff_lists()`; `clubs()`, `managed_clubs()`, `finances()`, `sponsorships()`, `facilities()`, `stadiums()`, `affiliates()` and `job_vacancies()`; `stages()`, `competitions()`, `fixtures()`, `league_tables()`, `competition_rules()`, `transfer_windows()` and `player_match_stats()`; `injury_types()` and `injuries()`; and `training()`, `mentoring()`, `tactics()` and `set_pieces()`, which only the club you manage stores.
- `Table`, an immutable sequence with `where()`, `filter()`, `sorted_by()`, `find()`, `by_uid()`, `by_id()` and `coverage`, and export through `to_dicts()`, `to_columns()`, `to_pandas()`, `to_polars()`, `write_csv()`, `write_json()` and `write_jsonl()`. A slice of a table is a table, and records keep working after the save is closed.
- `fmsave.field_status`, which says whether a field's meaning is verified against the game or still unconfirmed, and a flat output schema versioned as `fmsave.OUTPUT_SCHEMA_VERSION`.
- Competition names from a map you supply, through `fmsave.open(path, competition_names=...)` and `fmsave.read_competition_names()`, keyed on the editor database id every outside name source uses.
- Reader checks that measure a decode against loose bounds drawn from a couple of careers. A missed bound is a warning and the table is returned anyway; `fmsave.open(path, strict=True)` raises instead. `fmsave.validate_save` reports checks, counts and coverage, holding no names, uids or text from the save.
- The `fmsave info`, `fmsave export` and `fmsave validate` commands, and optional `pandas` and `polars` extras.

### Notes

- fmsave needs Python 3.12 or newer. It is read-only: it never modifies a save, makes no network connection, and reads nothing from your game install.
- This is a 0.x release and the names it exports may still move. fmsave has read one game build, so the dispatch that would carry it across a change of format has not yet had to work, and a 1.0.0 would promise a stability nothing has tested. That promise is earned rather than scheduled.
- A value fmsave cannot read is `None` rather than a guess, money stays in the unit the save stores it in, and a number the game never displayed ships as a raw number rather than as a label fmsave invented.
- Names the game renders from its own installed database, which is most competition, league, nation, city and ground names, are not in a save and none are shipped. The README has the rest of what a save keeps only in part.
