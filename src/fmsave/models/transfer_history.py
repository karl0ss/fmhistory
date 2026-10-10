"""Records decoded from the transfer-history section.

The `transfer_man` section is a record store reverse-engineered on one save
(`Karl Hudgell - UnemployedNew.fm`, build 26.3.2, an FM24 career imported into FM26).
Two of its slices are decoded here:

- the season-record grid, 73-byte rows per (club, squad slot) grouped per season,
  holding money fields on the raw-£ weekly-wage scale;
- the wage ledger, uniform 28-byte records from the section's first (clear)
  zone: per (club, squad slot) money records in one global chronological log,
  interleaved in file with 69-byte negotiation records.

The section carries no transfer fee, so this model reads no transfer fees.

The layouts are not verified across builds, and no field's meaning is
confirmed, so every field of the models is registered unconfirmed in the reader.
"""

from __future__ import annotations

from dataclasses import dataclass

from fmsave._status import register_field_statuses


@dataclass(frozen=True, slots=True)
class PlayerSeasonRecord:
    """One 73-byte season-record-grid row, a player-club-season snapshot.

    The grid sits at the `transfer_man` section's tail (one clear block plus one
    zstd-compressed block per season) and stores rows for players at clubs across
    the whole game world. A row's club is the high half of its head id and the
    squad slot is the low byte, and those two identify the player inside the row's
    season block: the same (club, slot) handle recurs across a season's rows and
    across seasons. The money fields (`value_a`..`value_c`) sit on the raw-£
    weekly-wage scale — the amounts are 20k-40k on league-standard players — and
    the section holds no transfer fee, so a fee column read here would be a wage
    coincidence.

    On the ground-truth save the grid's row type byte takes t4 on 55% of all rows,
    t14, t3, t1, t37, t24, t9, t6 next, with a long tail of rare types; season years
    cover the seasons the store keeps (the 14 newest seasons of a career). Rows whose
    season year is 1900 are kept as null-year rows; rows whose season year is 0xffff
    parse as one uniform junk family (club 0, row type 1, flags 0x01ff) and are not
    kept.

    Attributes:
        club_uid: Save-internal club uid the row keys on (the head id's high 24
            bits), matching `Club.uid` (one less than the editor's unique id);
            the wildcard 0xffffff marks club-free rows, all of row type 33
            (unconfirmed).
        slot: The club-internal 16-bit object handle's low byte — the squad slot
            the row's player holds (unconfirmed).
        variant_a: First variant byte of the row's head word (unconfirmed).
        variant_b: Second variant byte of the row's head word (unconfirmed).
        value_a: The row's first money field; the same value as `value_b` more
            than half the time. Unset rows carry the 0xffffffff sentinel and read
            as None (unconfirmed).
        value_b: The row's second money field; the same unset sentinel
            (unconfirmed).
        value_c: The row's third money field, often equal to `value_b`; the same
            unset sentinel (unconfirmed).
        value_d: The row's fourth money field; unset on ~97% of rows, same
            sentinel (unconfirmed).
        record_type: The row's type byte (unconfirmed).
        tick: The row's tick word — a game-world X-axis value shared across
            sections, semantics unconfirmed (unconfirmed).
        season_year: Calendar year of the row's season; the scan keeps calendar
            years and 1900 null-year rows, and drops 0xffff rows as a junk
            family (unconfirmed).
        flags: The row's trailing status word (unconfirmed).
        value_e: Money or club id field; the same unset sentinel (unconfirmed).
        count: Small-count field kept raw; a u16-null-sentinel form 0xffff (with
            zero bytes above it) is seen (unconfirmed).
        value_f: Unset on most club rows; the same unset sentinel
            (unconfirmed).
        value_g: Unset on most club rows; the same unset sentinel
            (unconfirmed).
    """

    club_uid: int
    slot: int
    variant_a: int
    variant_b: int
    value_a: int | None
    value_b: int | None
    value_c: int | None
    value_d: int | None
    record_type: int
    tick: int
    season_year: int
    flags: int
    value_e: int | None
    count: int
    value_f: int | None
    value_g: int | None


register_field_statuses(
    PlayerSeasonRecord,
    unconfirmed=(
        "club_uid",
        "slot",
        "variant_a",
        "variant_b",
        "value_a",
        "value_b",
        "value_c",
        "value_d",
        "record_type",
        "tick",
        "season_year",
        "flags",
        "value_e",
        "count",
        "value_f",
        "value_g",
    ),
)


@dataclass(frozen=True, slots=True)
class WageLedgerRecord:
    """One 28-byte wage-ledger record from the `transfer_man` section's clear zone.

    The section's clear zone interleaves two append streams in chronological
    order: this uniform 28-byte record, here read as the per-player wage and
    contract ledger, and 69-byte negotiation records (not decoded). A record
    keys a player through the club uid and club-internal squad slot in its 32-bit
    handle — the same handle the season-record grid's head id carries — and
    carries two money fields on the raw-£ weekly-wage scale: on the ground-truth
    save the first money field spans 1.1k-301k and the second 440-333k, and the
    second field is often a small multiple of the first but not predictably so,
    so the pair is stored raw. A handful of records carry the same handle at two
    clubs with identical money, which reads as the two clubs' registrations of
    one shared/loan spell.

    The stream the records sit in is structurally interleaved with the
    negotiation records, and 28-byte records also appear embedded inside those
    negotiation records' bodies; the reader's pattern scan cannot tell an
    embedded copy apart from a standalone one, so both are read.

    Attributes:
        club_uid: Save-internal club uid the record keys on — the handle's high
            24 bits, matching `Club.uid` (one less than the editor's unique id)
            (unconfirmed).
        slot: The handle's low byte — the squad slot, the same value the
            season-record grid's head id carries for the same player
            (unconfirmed).
        kind: The record's kind byte. On the ground-truth save kinds 4, 7, 5,
            2, 3, 8 and 17 occur, by descending frequency; kind 4 alone is two
            thirds of all records. Kinds may be money kinds (raw wage vs
            contract total etc.) rather than record types (unconfirmed).
        value_a: The record's first money field, on the raw-£ weekly-wage scale
            (unconfirmed).
        value_b: The record's second money field, same scale; often a small
            integer multiple of `value_a` (unconfirmed).
        flags: The record's flag byte between the money fields and the tail —
            0 on 97% of the ground-truth records; on every remaining record the
            second money field is exactly five times the first, so the flag and
            the ×5 pair probably switch between two money-unit forms
            (unconfirmed).
        tail_flags: The record's trailing 32-bit word, a bitfield; set bit
            values on the ground-truth save are 4, 8, 64, 128, 1024, 2048,
            4096 and 32768 (unconfirmed).
    """

    club_uid: int
    slot: int
    kind: int
    value_a: int
    value_b: int
    flags: int
    tail_flags: int


register_field_statuses(
    WageLedgerRecord,
    unconfirmed=(
        "club_uid",
        "slot",
        "kind",
        "value_a",
        "value_b",
        "flags",
        "tail_flags",
    ),
)