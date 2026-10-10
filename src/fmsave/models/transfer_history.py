"""Records decoded from the transfer-history section.

The `transfer_man` section is a record store reverse-engineered on one save
(`Karl Hudgell - UnemployedNew.fm`, build 26.3.2, an FM24 career imported into FM26).
Two of its slices are decoded here:

- the player-move grid, 73-byte rows grouped per season: one row per move in a
  person's career (a transfer, loan, free move, youth intake, release), keyed by
  the person's history reference and naming the teams involved;
- the wage ledger, uniform 28-byte records from the section's first (clear)
  zone: per-player money records in one global chronological log, interleaved
  in file with 69-byte negotiation records.

Both slices name people by the save-wide history reference
(`Save.history_player_references()`), not by uid. The section carries no
transfer fee, so this model reads no transfer fees.

The layouts are not verified across builds, and no field's meaning is
confirmed, so every field of the models is registered unconfirmed in the reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fmsave._status import register_field_statuses


@dataclass(frozen=True, slots=True)
class PlayerSeasonRecord:
    """One 73-byte row of the `transfer_man` grid: one move in a person's career.

    The grid sits at the `transfer_man` section's tail (one clear block plus one
    zstd-compressed block per season) and stores rows for people across the whole
    game world. The class name is historical: a row is not a season snapshot but one
    dated career move — a transfer, a loan, a free move, a youth intake, a release —
    keyed by the moving person's history reference and naming the teams it moves
    him between by `Team.team_id`. Players' references resolve through
    `Save.history_player_references()`; row types 6 and 9 key non-player staff, and
    rows of players no longer in `players()` (retired, mostly) do not resolve. The
    section holds no transfer fee.

    On the ground-truth save every row's tick and season-year words decode as a
    game date, and the row types read, calibrated on the manager's club: 1 a
    transfer between clubs, 3 a loan, 4 a free move (to or from no club, or between
    clubs), 5 a signing seen only at the human manager's club, 14 a youth intake
    (no origin team), 24 a youth release, 7 a trial, 37 a retirement, 6 and 9 a
    staff appointment and departure. Rows whose season year is 1900 are kept as
    null-year rows; rows whose season year is 0xffff parse as one uniform junk
    family (reference 0..255, row type 1, flags 0x01ff) and are not kept.

    Attributes:
        player_reference: History reference of the person the row moves: the head
            id's 32 bits, matched to a player's uid by
            `Save.history_player_references()`. Row type 33 carries the wildcard
            0xffffffff and names no one (unconfirmed).
        variant_a: First variant byte of the row's head word (unconfirmed).
        variant_b: Second variant byte of the row's head word (unconfirmed).
        value_a: The team the person moves to, as a `Team.team_id`; None when the
            move leaves him without a club (a release or a contract running out).
            Unset fields carry the 0xffffffff sentinel and read as None
            (unconfirmed).
        value_b: The team the person moves from, as a `Team.team_id`; None for a
            youth intake or a free agent's signing (unconfirmed).
        value_c: A third team id: the destination team on a transfer or loan, the
            origin team on a move to no club (unconfirmed).
        value_d: Loan-row field, unset on most rows (unconfirmed).
        record_type: The row's type byte; the calibrated meanings are in the class
            docstring (unconfirmed).
        tick: The row's date word: day of the year in its low 9 bits and the intra-day
            slot above them, the same packing `date` decodes (unconfirmed).
        season_year: The year word of the row's date (unconfirmed).
        date: The game date the move took effect, decoded from `tick` and
            `season_year`; None for a null-year row (unconfirmed).
        flags: The row's trailing status word (unconfirmed).
        value_e: Unset on loans, intakes and staff rows; a three-to-four-digit value
            on transfers and free moves (unconfirmed).
        count: Small-count field kept raw; a u16-null-sentinel form 0xffff (with
            nonzero bytes above it on loans) is seen (unconfirmed).
        value_f: History reference of the destination club's manager at the time of
            the move; the same unset sentinel (unconfirmed).
        value_g: History reference of the origin club's manager at the time of the
            move; the same unset sentinel (unconfirmed).
    """

    player_reference: int
    variant_a: int
    variant_b: int
    value_a: int | None
    value_b: int | None
    value_c: int | None
    value_d: int | None
    record_type: int
    tick: int
    season_year: int
    date: date | None
    flags: int
    value_e: int | None
    count: int
    value_f: int | None
    value_g: int | None


register_field_statuses(
    PlayerSeasonRecord,
    unconfirmed=(
        "player_reference",
        "variant_a",
        "variant_b",
        "value_a",
        "value_b",
        "value_c",
        "value_d",
        "record_type",
        "tick",
        "season_year",
        "date",
        "flags",
        "value_e",
        "count",
        "value_f",
        "value_g",
    ),
)


@dataclass(frozen=True, slots=True)
class ClubPlayerMove:
    """One move in or out of a club, joined to the player and the clubs it names.

    `Save.club_player_moves()` builds these from the `transfer_man` move grid
    (`PlayerSeasonRecord`): every row naming one of the club's own teams as the
    origin or the destination, with the moving person's reference resolved to a
    player and both teams resolved to their clubs. Fees are not stored in the save.

    Attributes:
        date: The game date the move took effect; None for a null-year row
            (unconfirmed).
        record_type: The grid row's type byte: 1 transfer, 3 loan, 4 free move, 5 a
            signing seen only at the human manager's club, 14 youth intake, 24 youth
            release, 7 trial, 37 retirement, 6/9 staff appointment/departure
            (unconfirmed).
        direction: "in" when the destination team is the club's, "out" when the
            origin team is, "internal" when both are (unconfirmed).
        player_reference: History reference of the person moving (unconfirmed).
        player_uid: Uid of the player the reference resolves to, or None when it
            resolves to no player in `players()` (staff, retired players)
            (unconfirmed).
        player_name: Denormalised name of player_uid; None wherever player_uid is
            (unconfirmed).
        from_team_id: Team the person moves from, or None (unconfirmed).
        to_team_id: Team the person moves to, or None (unconfirmed).
        from_club_uid: Uid of the club whose own team list holds from_team_id, or
            None (unconfirmed).
        to_club_uid: Uid of the club whose own team list holds to_team_id, or None
            (unconfirmed).
        from_club_name: Denormalised name of from_club_uid (unconfirmed).
        to_club_name: Denormalised name of to_club_uid (unconfirmed).
    """

    date: date | None
    record_type: int
    direction: str
    player_reference: int
    player_uid: int | None
    player_name: str | None
    from_team_id: int | None
    to_team_id: int | None
    from_club_uid: int | None
    to_club_uid: int | None
    from_club_name: str | None
    to_club_name: str | None


register_field_statuses(
    ClubPlayerMove,
    unconfirmed=(
        "date",
        "record_type",
        "direction",
        "player_reference",
        "player_uid",
        "player_name",
        "from_team_id",
        "to_team_id",
        "from_club_uid",
        "to_club_uid",
        "from_club_name",
        "to_club_name",
    ),
)


@dataclass(frozen=True, slots=True)
class WageLedgerRecord:
    """One 28-byte wage-ledger record from the `transfer_man` section's clear zone.

    The section's clear zone interleaves two append streams in chronological
    order: this uniform 28-byte record, here read as the per-player wage and
    contract ledger, and 69-byte negotiation records (not decoded). A record
    keys a player by his history reference — the same id the move grid's rows
    carry, resolved by `Save.history_player_references()` (93% of ground-truth
    records resolve, against 24% for random ids in the same range) — and carries
    two money fields on the raw-£ weekly-wage scale: on the ground-truth save the
    first money field spans 1.1k-301k and the second 440-333k, and the second field
    is often a small multiple of the first but not predictably so, so the pair is
    stored raw.

    The stream the records sit in is structurally interleaved with the
    negotiation records, and 28-byte records also appear embedded inside those
    negotiation records' bodies; the reader's pattern scan cannot tell an
    embedded copy apart from a standalone one, so both are read.

    Attributes:
        player_reference: History reference of the player the record keys on
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

    player_reference: int
    kind: int
    value_a: int
    value_b: int
    flags: int
    tail_flags: int


register_field_statuses(
    WageLedgerRecord,
    unconfirmed=(
        "player_reference",
        "kind",
        "value_a",
        "value_b",
        "flags",
        "tail_flags",
    ),
)
