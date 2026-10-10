# Transfer-Man Season Records Reference

## Overview
The `transfer_man` section (53 MB on the ground-truth save) stores the transfer
and contract ledgers the game's transfer screens read. Two slices of it are
decoded: the tail's 73-byte per-season rows — one row per (club, squad slot) per
season — described below, and the clear zone's 28-byte wage-ledger records
(`Save.transfer_man_wage_ledger()`). The section's remaining record families
(transfer registrations, negotiation offers) are byte-mapped in
`docs/history-re.md` but not decoded here: **the section carries no transfer
fee**, and every fee-shaped money value read anywhere in it is a wage or
record-constant coincidence (see `docs/history-re.md`, checkpoints 4 and 5).

## Data Model

### PlayerSeasonRecord Dataclass
The record's fields and their meanings are documented on
`fmsave.PlayerSeasonRecord` itself (see `fmsave.models.transfer_history`);
every field is registered `unconfirmed`. In short: one row is one
player-club-season snapshot keyed by the save-internal club uid and the club's
squad slot, with three to six money fields on the raw-£ weekly-wage scale
(20k–40k on league-standard players), a row-type byte, a tick word and the
season year.

### WageLedgerRecord Dataclass
`Save.transfer_man_wage_ledger()` reads the section's first (clear) zone: one
global chronological log whose wage-ledger records — `fmsave.WageLedgerRecord`,
all fields `unconfirmed` — sit interleaved in file order with 69-byte
negotiation records. Each 28-byte record:

- `11 00` tag
- `handle` (u32) — the club uid in the high 24 bits, the club's squad slot in
  the low byte; the same handle the season rows key on
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

Ground truth: 32,235 records across 2,011 club uids; the manager's club (716)
carries 28, led by the dual-club registration pair (716 slot 33 / club 2536
slot 86) both carrying 20,680/62,040.

## Section Structure

### transfer_man

The section opens with a 12-byte header: `03 01 'tad.' <u16 version>` then a
u32 byte count. On the ground-truth save the u32 is 11,560,192 and the section
then spans:

- a clear region of record families (zone 1, ~17.7 MB — the wage ledger here
  is decoded, the transfer-registration and negotiation families are not),
- the clear season-record region: 73-byte rows in runs at stride 73, with
  ~1 KB story/TLV chunks (plain-text and base64 strings) interleaved between
  runs,
- 13 concatenated zstd frames, one per older season, oldest first (seasons
  2022–2034 on the ground truth); the clear region covers the newest seasons
  (2035–2037). Only the final frame carries a 1-byte section tail past its
  zstd terminator.

Each 73-byte row contains (all little-endian):

- `head` (4 bytes) — `00 <u8 variant_a> <u8 variant_b> 07`; the 0x07 anchors
  pattern scans
- `head_id` (u32) — the club uid in the high 24 bits, the squad slot in the
  low byte; the wildcard 0xffffff marks club-free rows (always row type 33)
- separator `00` bytes at row offsets +8, +13 and +18 around the money fields
- `value_a` (u32) — money field; `0xffffffff` when unset
- `value_b` (u32) — money field; same sentinel
- `value_c` (u32) — money field, often equal to `value_b`; same sentinel
- `value_d` (u32) — money field; unset on ~97% of rows
- 8 zero bytes
- `record_type` (u8) — on the ground truth t4 is 55% of rows, then t14, t3,
  t1, t24, t37, t6, t9, with a long tail of rare types
- `tick` (u16) — a game-world X-axis value shared across sections
- `season_year` (u16) — calendar year of the season
- `flags` (u16) — status word
- `value_e`, `count`, `value_f`, `value_g` (u32 × 4) — trailing fields, unset
  on most rows

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
   (club 0, type 1, flags 0x01ff) and are dropped.

`raise_when_unreadable` gates the `Save.` method for the season rows, and
`raise_when_ledger_unreadable` the wage-ledger one: a section that yields no
records raises `CorruptSaveError`, keeping a wholly different section's bytes
from reading as an empty table.

The wage-ledger scan reads the clear zone only (header to the first zstd frame
magic) and validates each candidate on: the `11 00` tag, the handle's club-high
byte below 16, the kind byte below 32, two zero pad words around the money
fields, both money fields under their scale bounds, and the absence of an
interleaved tagged family's `01 02` marker inside the first money field's
middle bytes.

## Usage

Access the data through the Save object:

```python
import fmsave

save = fmsave.open("my-career.fm")
for record in save.transfer_man_player_seasons():
    if record.record_type == 4:
        print(record.season_year, record.club_uid, record.value_a)
for record in save.transfer_man_wage_ledger():
    print(record.club_uid, record.slot, record.value_a, record.value_b)
```

## Ground-Truth Numbers

Measured on `Karl Hudgell - UnemployedNew.fm` (build 26.3.2, an FM24 career
imported into FM26): **1,428,558 rows across 16 seasons** — 2022: 39,
2023: 32,213, 2024: 124,931, 2025: 109,561, 2026: 93,730, 2027: 94,208,
2028: 102,511, 2029: 103,068, 2030: 99,120, 2031: 98,263, 2032: 98,407,
2033: 97,736, 2034: 97,100, 2035: 96,093, 2036: 95,968, 2037: 85,610 — across
3,225 distinct club uids. Validation anchors: manager-row pair (Dumas,
club 716 slot 7) carries 23,972 in `value_a` and `value_c` in season 2036, and
the companion club row (slot 172) carries 32,604 in `value_b` and `value_c`,
matching the values decoded from the wage-ledger families in checkpoint 4.

The wage ledger decodes to **32,235 records across 2,011 club uids**; the
manager's club (716) carries 28, and the kind-4 share is 66%. `value_a` spans
0–301,424 (p50 22,440), `value_b` 0–332,640, on the raw-£ weekly-wage scale.

## Field Status

All fields in `PlayerSeasonRecord` and `WageLedgerRecord` are marked
unconfirmed: reverse-engineered from a single ground-truth save, pending
validation across saves and builds.