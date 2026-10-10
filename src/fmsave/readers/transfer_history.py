"""Decoding the `transfer_man` section's season-record grid and wage ledger.

The section (a `tad.` container, one per save) holds the transfer and contract
ledgers the game's transfer screens read. Two slices are decoded here:

- the tail's player-move grid: a store of 73-byte rows grouped per season, one
  per dated move in a person's career, keyed by the person's history reference
  and naming the teams moved between. The rows sit in a clear region after the
  section's other record families, followed by one zstd-compressed block per
  older season, oldest first and the newest clear.
- the clear zone's wage ledger: uniform 28-byte money records interleaved in
  file order with 69-byte negotiation records, forming one global chronological
  log.

The rest of the section — the transfer-registration families and the
negotiation offers — is byte-mapped in the project's notes but not decoded
here: the section carries no transfer fee, and a fee-shaped money field read
anywhere in it is a wage or record-constant coincidence.

Layouts here were reverse-engineered on one save (`Karl Hudgell -
UnemployedNew.fm`, build 26.3.2, an FM24 career imported into FM26) and are not
verified across builds. The row reads are a pattern scan, so records a changed
build does not cover are missed rather than misread.
"""

from __future__ import annotations

import re
import struct
import sys
from collections.abc import Iterable, Mapping
from datetime import date

from fmsave._errors import CorruptSaveError
from fmsave._scan import decode_date
from fmsave.models.transfer_history import ClubPlayerMove, PlayerSeasonRecord, WageLedgerRecord

if sys.version_info >= (3, 14):
    from compression import zstd
else:
    from backports import zstd

TRANSFER_MAN_SECTION = "transfer_man"

_ROW_LENGTH = 73
# One 73-byte row: the head word, the person's history reference, three
# 00-null-separated u32 team ids and a fourth field, an 8-byte gap, the type
# byte, the date (a packed day word then the year), a status word, four trailing
# fields and an unset tail.
_ROW_FORMAT = struct.Struct("<4sIBIBIBI8sIBHHHIIII15s")
assert _ROW_FORMAT.size == _ROW_LENGTH

# The season rows follow the section's record families behind a 12-byte header:
# `03 01 'tad.' <u16 version> <u32 byte count>`.
_HEADER_SIZE = 12

# The zstd frame magic opens every compressed season block.
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

# The row's head word is `00 <u8 variant> <u8 variant> 07`.
_ROW_HEAD = re.compile(b"\x00[\x00\x01][\x00\x01]\x07")

# The row's date sits at this offset: the u16 day word, then the u16 year.
_ROW_DATE_OFFSET = 36

# The nullable fields carry 0xffffffff when unset.
_UNSET = 0xFFFF_FFFF

_YEAR_MIN = 2005
_YEAR_MAX = 2050
_NULL_YEAR = 1900

# A season block that fails to decompress after this many trailing-byte drops is
# not decoded: the compressed tail carries a one-byte block terminator the final
# block alone sits in, and a build may widen that tail a little.
_MAX_TAIL_DROP = 8

_WAGE_RECORD_LENGTH = 28
# The two tag bytes the wage ledger opens each record with.
_WAGE_MAGIC = b"\x11\x00"
# One wage-ledger record after the tag: the player reference, the kind byte, two
# money u32s each padded by a zero u32, a flag byte and the tail word.
_WAGE_FORMAT = struct.Struct("<IBIIIIBI")
assert _WAGE_FORMAT.size == _WAGE_RECORD_LENGTH - len(_WAGE_MAGIC)

# A wage record's kind byte is small; the ground-truth kinds are 2-8 and 17.
_WAGE_KIND_MAX = 32

# A wage record's money fields sit below one six-figure pound value each; the
# ground-truth maxima are ~301k and ~333k on the weekly-wage scale.
_WAGE_VALUE_A_MAX = 1_000_000
_WAGE_VALUE_B_MAX = 100_000_000


def _head_variant(head: bytes) -> tuple[int, int]:
    """The head word's variant bytes."""
    return head[1], head[2]


def _season_year_ok(year: int) -> bool:
    """Whether the season-year field is a calendar year or the null year.

    Rows carrying a 0xffff year all parse as one junk family (reference below 256, type 1,
    flags 0x01ff) on the layout save, so the sentinel is not accepted: keeping
    it admits ~90 pattern-noise rows per save and no proven real row.
    """
    return year == _NULL_YEAR or _YEAR_MIN <= year <= _YEAR_MAX


def _row(bytes_at: bytes, offset: int) -> PlayerSeasonRecord | None:
    """The record the 73 bytes at `offset` hold, or None they hold no row.

    A row is `00 <u8 variant> <u8 variant> 07` plus three zero null-separators
    around its team fields, a season year inside the layout's bounds, and unset
    sentinels where null.
    """
    head = bytes_at[offset : offset + 4]
    if not _ROW_HEAD.match(head):
        return None
    if bytes_at[offset + 8] != 0 or bytes_at[offset + 13] != 0 or bytes_at[offset + 18] != 0:
        return None
    record = _ROW_FORMAT.unpack(bytes_at[offset : offset + _ROW_LENGTH])
    year = record[12]
    if not _season_year_ok(year):
        return None
    variant_a, variant_b = _head_variant(head)
    return PlayerSeasonRecord(
        player_reference=record[1],
        variant_a=variant_a,
        variant_b=variant_b,
        value_a=None if record[3] == _UNSET else record[3],
        value_b=None if record[5] == _UNSET else record[5],
        value_c=None if record[7] == _UNSET else record[7],
        value_d=None if record[9] == _UNSET else record[9],
        record_type=record[10],
        tick=record[11],
        season_year=year,
        date=decode_date(bytes_at, offset + _ROW_DATE_OFFSET),
        flags=record[13],
        value_e=None if record[14] == _UNSET else record[14],
        count=record[15],
        value_f=None if record[16] == _UNSET else record[16],
        value_g=None if record[17] == _UNSET else record[17],
    )


def decode_player_season_records(data: bytes) -> tuple[PlayerSeasonRecord, ...]:
    """Every readable season-record row the section keeps, in file order.

    The rows come from the clear season region that follows the section's record
    families and from the compressed season blocks that follow it, one block per
    older season. A block whose bytes decompress under none of the accepted
    trailing-byte trims is skipped, so a build that changes the compressed-tail
    framing still returns the clear rows.
    """
    frame_positions = []
    position = data.find(_ZSTD_MAGIC, _HEADER_SIZE)
    while position != -1:
        frame_positions.append(position)
        position = data.find(_ZSTD_MAGIC, position + 4)

    clear_end = frame_positions[0] if frame_positions else len(data)
    records: list[PlayerSeasonRecord] = _region_rows(data, _HEADER_SIZE, clear_end)
    index = 0
    while index < len(frame_positions):
        frame_start = frame_positions[index]
        next_index = index + 1
        # A magic inside one block's compressed bytes would end a segment early;
        # the frame then fails to decompress, and the scan retries the segment
        # extended over the next magic's frame.
        while True:
            frame_end = (
                frame_positions[next_index] if next_index < len(frame_positions) else len(data)
            )
            frame_bytes = _decompress_frame(data[frame_start:frame_end])
            if frame_bytes is not None or next_index >= len(frame_positions):
                break
            next_index += 1
        if frame_bytes is not None:
            records.extend(_region_rows(frame_bytes, 0, len(frame_bytes)))
        # A retry that extended the segment over false magics consumed more than
        # one of the frame positions; otherwise only this frame is done.
        index = next_index if next_index > index + 1 else index + 1
    return tuple(records)


def _region_rows(bytes_at: bytes, start: int, limit: int) -> list[PlayerSeasonRecord]:
    """The rows a season region carries, read at every head-word match.

    Rows butt at stride 73 inside the store's tables, with other data (story
    text, block tails) between tables, so the scan re-anchors on every head
    word's own position rather than one store-wide grid offset; a match that
    misses the row's bounds is not a row.
    """
    records_by_position: dict[int, PlayerSeasonRecord] = {}
    for head_at in _ROW_HEAD.finditer(bytes_at, start, limit):
        position = head_at.start()
        record = _row(bytes_at, position)
        if record is not None:
            records_by_position[position] = record
    return [records_by_position[position] for position in sorted(records_by_position)]


def _decompress_frame(compressed: bytes) -> bytes | None:
    """The bytes one season block decompresses to, or None if no trim works.

    Season blocks are one zstd frame with a short section tail after the last
    one, so the scan accepts a block when dropping 0 to 8 of its trailing bytes
    decompresses to a whole frame.
    """
    for drop in range(_MAX_TAIL_DROP + 1):
        candidate = compressed[: len(compressed) - drop] if drop else compressed
        try:
            return zstd.decompress(candidate)
        except (zstd.ZstdError, ValueError):
            continue
    return None


def raise_when_unreadable(rows: int, data: bytes) -> None:
    """A gate that keeps a wholly different section's bytes from reading as rows.

    The section always carries a career's worth of season rows on a save the game
    wrote; if none parse, the section's layout is not the one this decoder reads.
    """
    if rows == 0:
        raise CorruptSaveError(
            f"transfer_man with {len(data)} bytes holds no readable season-record rows"
        )


def _wage_record(data: bytes, offset: int) -> WageLedgerRecord | None:
    """The wage-ledger record the 28 bytes at `offset` hold, or None it holds none.

    A record is the `11 00` tag, a player reference below 2**28, the
    kind byte below 32, two money u32s each padded by a zero u32, a flag byte
    and the tail word. The money bound also drops one tagged-record family that
    interleaves in the same clear zone and whose money positions carry a
    different grammar: its first money u32 reads with the bytes `01 02` in the
    middle.
    """
    reference, kind, value_a, pad_a, value_b, pad_b, flags, tail_flags = _WAGE_FORMAT.unpack_from(
        data, offset + 2
    )
    if reference >> 24 >= 0x10 or kind >= _WAGE_KIND_MAX:
        return None
    if pad_a != 0 or pad_b != 0:
        return None
    if (value_a >> 8) & 0xFFFF == 0x0201:
        return None
    if value_a >= _WAGE_VALUE_A_MAX or value_b >= _WAGE_VALUE_B_MAX:
        return None
    return WageLedgerRecord(
        player_reference=reference,
        kind=kind,
        value_a=value_a,
        value_b=value_b,
        flags=flags,
        tail_flags=tail_flags,
    )


def decode_wage_ledger_records(data: bytes) -> tuple[WageLedgerRecord, ...]:
    """Every readable wage-ledger record the section's clear zone keeps, in file order.

    The clear zone runs from the header to the section's first zstd frame magic;
    every wage-ledger record the save logs sits there, interleaved in file order
    with the negotiation records it shares the chronological log with. The scan
    re-anchors on every tag's own position, and 28-byte records embedded inside
    a negotiation record's body read as standalone ones because the scan cannot
    tell them apart.
    """
    zone_limit = len(data)
    first_frame = data.find(_ZSTD_MAGIC, _HEADER_SIZE)
    if first_frame != -1:
        zone_limit = first_frame

    records_by_position: dict[int, WageLedgerRecord] = {}
    position = data.find(_WAGE_MAGIC, _HEADER_SIZE, zone_limit)
    while position != -1:
        record = _wage_record(data, position)
        if record is not None:
            records_by_position[position] = record
        position = data.find(_WAGE_MAGIC, position + 2, zone_limit)
    return tuple(records_by_position[position] for position in sorted(records_by_position))


def raise_when_ledger_unreadable(rows: int, data: bytes) -> None:
    """A gate that keeps a wholly different section's bytes from reading as ledger rows.

    The section always carries the wage ledger the world's contract writes feed on
    a save the game wrote; if no record parses, the section's layout is not the one
    this decoder reads.
    """
    if rows == 0:
        raise CorruptSaveError(
            f"transfer_man with {len(data)} bytes holds no readable wage-ledger records"
        )


def club_player_moves(
    records: Iterable[PlayerSeasonRecord],
    club_uid: int,
    club_by_team: Mapping[int, int],
    club_names: Mapping[int, str | None],
    player_by_reference: Mapping[int, int],
    player_names: Mapping[int, str | None],
) -> tuple[ClubPlayerMove, ...]:
    """The move-grid rows that move a person into or out of one club, joined.

    A row belongs to the club when its destination (`value_a`) or origin
    (`value_b`) team is one of the club's own teams, read off `club_by_team`
    (team id to the uid of the club whose own team list holds it). Each kept row
    resolves its person's reference to a player uid and name, and both teams to
    their clubs; anything that does not resolve reads as None. Moves come back in
    date order, null-year rows first, and file order within a date.
    """
    moves: list[ClubPlayerMove] = []
    for record in records:
        to_club = None if record.value_a is None else club_by_team.get(record.value_a)
        from_club = None if record.value_b is None else club_by_team.get(record.value_b)
        moving_in = to_club == club_uid
        moving_out = from_club == club_uid
        if not moving_in and not moving_out:
            continue
        player_uid = player_by_reference.get(record.player_reference)
        moves.append(
            ClubPlayerMove(
                date=record.date,
                record_type=record.record_type,
                direction="internal" if moving_in and moving_out else "in" if moving_in else "out",
                player_reference=record.player_reference,
                player_uid=player_uid,
                player_name=None if player_uid is None else player_names.get(player_uid),
                from_team_id=record.value_b,
                to_team_id=record.value_a,
                from_club_uid=from_club,
                to_club_uid=to_club,
                from_club_name=None if from_club is None else club_names.get(from_club),
                to_club_name=None if to_club is None else club_names.get(to_club),
            )
        )
    moves.sort(key=lambda move: move.date or date.min)
    return tuple(moves)
