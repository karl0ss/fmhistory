# Transfer-Man Records Reference

## Overview
The `transfer_man` section (53 MB on the ground-truth save) stores the transfer
and contract ledgers the game's transfer screens read. Two slices of it are
decoded: the tail's 73-byte move rows — one row per dated move in a person's
career (transfer, loan, free move, youth intake, release, staff appointment),
grouped per season — described below, and the clear zone's 28-byte wage-ledger
records (`Save.transfer_man_wage_ledger()`). `Save.club_player_moves(club_uid)`
joins one club's move rows to players and clubs. The section's remaining record
families (negotiation offers, the `03` family) are byte-mapped in
`docs/history-re.md` but not decoded here: **the section carries no transfer
fee** (see `docs/history-re.md`, checkpoints 4 and 5).

Every record family in the section names people by the **history reference**
(`Save.history_player_references()` maps it to a player uid; it is the player's
`pindex + 1`). Earlier notes read the same 32-bit word as a `(club uid << 8 |
squad slot)` handle; that reading was wrong (`docs/history-re.md`, transfer_man
checkpoint 8).

## Data Model

### PlayerSeasonRecord Dataclass
The record's fields and their meanings are documented on
`fmsave.PlayerSeasonRecord` itself (see `fmsave.models.transfer_history`);
every field is registered `unconfirmed`. The class name is historical. In
short: one row is one career move of the person named by `player_reference`,
from team `value_b` to team `value_a` (both `Team.team_id`, None for no club),
on `date`, with a row-type byte giving the kind of move.

Row types, calibrated on the manager's club (St Albans City, first team 603):

| type | meaning (calibrated) | St Albans rows since 18/7/2023 |
|---|---|---|
| 1 | transfer between clubs | 31 in, 25 out |
| 3 | loan | 5 in, 182 out |
| 4 | free move: to no club, from no club, or between clubs | 54 in, 100 out |
| 5 | signing; occurs only at the human manager's club (42 rows game-wide) | 42 in |
| 7 | trial | 212 in |
| 14 | youth intake (no origin team) | 224 in |
| 24 | release to no club (on the ground truth mostly youth-intake players) | 60 out |
| 37 | retirement | 1 out |
| 6 / 9 | staff appointment / departure (references are non-players) | 112 in, 28 out / 11 out |

### ClubPlayerMove Dataclass
`Save.club_player_moves(club_uid)` returns `fmsave.models.transfer_history.ClubPlayerMove`
rows: each move row whose origin or destination team is one of the club's own
teams, with `direction` ("in", "out", "internal"), the resolved `player_uid` and
`player_name` (None for staff and players no longer in `players()`), and both
teams' club uids and names. Moves are in date order. No fees.

### WageLedgerRecord Dataclass
`Save.transfer_man_wage_ledger()` reads the section's first (clear) zone: one
global chronological log whose wage-ledger records — `fmsave.WageLedgerRecord`,
all fields `unconfirmed` — sit interleaved in file order with 69-byte
negotiation records. Each 28-byte record:

- `11 00` tag
- `player_reference` (u32) — the player's history reference, the same id the
  move rows carry (93% of ground-truth records resolve to a player, against 24%
  for random ids in the same range)
- `kind` (u8) — ground-truth kinds 4 (two thirds of records), 7, 5, 2, 3, 8 and
  17
- `value_a` (u32) — money field on the raw-£ weekly-wage scale
- zero u32
- `value_b` (u32) — second money field, same scale; often a small multiple of
  `value_a`
- zero u32
- `flags` (u8) — 0 on 97% of records; on every remaining record `value_b` is
  exactly five times `value_a`
- `tail_flags` (u32) — trailing bitfield (ground-truth set bits: 4, 8, 64,
  128, 1024, 2048, 4096, 32768)

Ground truth: 32,235 records.

## Section Structure

### transfer_man

The section opens with a 12-byte header: `03 01 'tad.' <u16 version>` then a
u32 byte count. On the ground-truth save the u32 is 11,560,192 and the section
then spans:

- a clear region of record families (zone 1, ~17.7 MB — the wage ledger here
  is decoded, the transfer-registration and negotiation families are not),
- the clear move-row region: 73-byte rows in runs at stride 73, with
  ~1 KB story/TLV chunks (plain-text and base64 strings) interleaved between
  runs,
- 13 concatenated zstd frames, one per older season, oldest first (seasons
  2022–2034 on the ground truth); the clear region covers the newest seasons
  (2035–2037). Only the final frame carries a 1-byte section tail past its
  zstd terminator.

Each 73-byte row contains (all little-endian):

- `head` (4 bytes) — `00 <u8 variant_a> <u8 variant_b> 07`; the 0x07 anchors
  pattern scans
- `player_reference` (u32) — the moving person's history reference; the
  wildcard 0xffffffff marks rows naming no one (always row type 33)
- separator `00` bytes at row offsets +8, +13 and +18 around the team fields
- `value_a` (u32) — destination `Team.team_id`; `0xffffffff` when unset (move
  to no club)
- `value_b` (u32) — origin team id; same sentinel (youth intake, free agent)
- `value_c` (u32) — a third team id: the destination on transfers and loans,
  the origin on moves to no club; same sentinel
- `value_d` (u32) — loan-row field; unset on most rows
- 8 zero bytes
- `record_type` (u8) — the move kind (table above); on the ground truth t4 is
  55% of rows, then t14, t3, t1, t24, t37, t6, t9, with a long tail of rare types
- `tick` (u16) + `season_year` (u16) at row offset +36 — one 4-byte game date:
  day of the year in the tick's low 9 bits (intra-day slot above), then the
  year; every ground-truth row decodes (`date`)
- `flags` (u16) — status word
- `value_e`, `count`, `value_f`, `value_g` (u32 × 4) — trailing fields;
  `value_f` / `value_g` are the history references of the destination / origin
  club's manager at the time (328,408 = the human manager on every St Albans
  row)

## Decoder Implementation

`decode_player_season_records` and `decode_wage_ledger_records` in
`src/fmsave/readers/transfer_history.py` implement pattern scans (not layout
walks — records a changed build does not cover are missed rather than misread):

1. Splits the section at the zstd frame magics; the clear region runs from the
   header to the first magic, and each segment is one frame. A false magic
   inside one frame's compressed bytes ends a segment early, so a segment that
   fails to decompress is retried extended over the next magic.
2. Decompresses each frame with a 0–8 trailing-byte drop sweep (the final
   frame carries a one-byte section tail); an undecompressable segment is
   skipped, so a changed framing still returns the clear rows.
3. Reads rows at every head-word match, validating: zero separators at +8,
   +13 and +18, and a season year on the calendar range (2005–2050) or the
   1900 null year. Rows whose year is 0xffff parse as one uniform junk family
   (reference below 256, type 1, flags 0x01ff) and are dropped.

`raise_when_unreadable` gates the `Save.` method for the season rows, and
`raise_when_ledger_unreadable` the wage-ledger one: a section that yields no
records raises `CorruptSaveError`, keeping a wholly different section's bytes
from reading as an empty table.

The wage-ledger scan reads the clear zone only (header to the first zstd frame
magic) and validates each candidate on: the `11 00` tag, the reference's high
byte below 16, the kind byte below 32, two zero pad words around the money
fields, both money fields under their scale bounds, and the absence of an
interleaved tagged family's `01 02` marker inside the first money field's
middle bytes.

## Usage

Access the data through the Save object:

```python
import fmsave

save = fmsave.open("my-career.fm")
for move in save.club_player_moves(716):
    print(move.date, move.record_type, move.direction, move.player_name,
          move.from_club_name, move.to_club_name)
for record in save.transfer_man_player_seasons():
    print(record.date, record.player_reference, record.value_b, record.value_a)
for record in save.transfer_man_wage_ledger():
    print(record.player_reference, record.value_a, record.value_b)
```

## Ground-Truth Numbers

Measured on `Karl Hudgell - UnemployedNew.fm` (build 26.3.2, an FM24 career
imported into FM26): **1,428,558 rows across 16 seasons** — 2022: 39,
2023: 32,213, 2024: 124,931, 2025: 109,561, 2026: 93,730, 2027: 94,208,
2028: 102,511, 2029: 103,068, 2030: 99,120, 2031: 98,263, 2032: 98,407,
2033: 97,736, 2034: 97,100, 2035: 96,093, 2036: 95,968, 2037: 85,610. Every
row's date decodes. Validation anchors (ground truth from the manager's
profile): Corentin Dumas (reference 189,608) moves from AS Saint-Etienne (team
706) to St Albans City (team 603) on 10/8/2036 as a type-1 row; Ben Young-Thomas
(280,836) moves from St Albans to Shanghai Port (team 20,360) on 9/8/2037.

`Save.club_player_moves(716)` returns 1,087 moves, 683 naming a current player.
Since the manager took over (18/7/2023) the incoming type-1, type-4 and type-5
rows number **127 — the profile's "127 players bought", exactly**. The outgoing
side does not reproduce the profile's 39 sold / 50 released by type alone:
type 1 out = 25 (46 with type-4 moves to another club), type 24 out = 60 (50
of them naming a current player), type-4 moves to no club = 79.

The wage ledger decodes to **32,235 records**, and the kind-4 share is 66%.
`value_a` spans 0–301,424 (p50 22,440), `value_b` 0–332,640, on the raw-£
weekly-wage scale.

## Field Status

All fields in `PlayerSeasonRecord`, `ClubPlayerMove` and `WageLedgerRecord` are marked
unconfirmed: reverse-engineered from a single ground-truth save, pending
validation across saves and builds.