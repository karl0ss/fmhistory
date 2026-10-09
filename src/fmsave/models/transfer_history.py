"""Records decoded from the transfer-history section.

The `transfer_man` section is a record store reverse-engineered on one save
(`Karl Hudgell - UnemployedNew.fm`, build 26.3.2, an FM24 career imported into FM26).
Its season-record grid is the slice of the section proven to be 73-byte rows:
per (club, squad slot) rows grouped per season, holding money fields on the
raw-£ weekly-wage scale. The section's other families (transfer registrations,
wage ledger, negotiation offers) are mapped in the project notes but not decoded
here, so this model reads no transfer fees.

The row layout is not verified across builds, and no field's meaning is confirmed,
so every field of the model is registered unconfirmed in the reader.
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