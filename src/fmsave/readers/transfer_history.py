"""Decoding the `transfer_man` section's season-record grid.

The section (a `tad.` container, one per save) holds the transfer and contract
ledgers the game's transfer screens read. Its tail is the slice this module
reads: a store of 73-byte rows keyed per (club, squad slot) and grouped per
season — per-player-per-club season snapshots whose money fields sit on the raw-£
weekly-wage scale. The rows sit in a clear region after the section's other
record families, followed by one zstd-compressed block per older season, oldest
first and the newest clear.

The rest of the section — the transfer-registration families, the wage ledger
and the negotiation offers — is byte-mapped in the project's notes but not
decoded here: the section carries no transfer fee, and a fee-shaped money field
read anywhere in it is a wage or record-constant coincidence.

Layouts here were reverse-engineered on one save (`Karl Hudgell -
UnemployedNew.fm`, build 26.3.2, an FM24 career imported into FM26) and are not
verified across builds. The row reads are a pattern scan, so rows a changed
build does not cover are missed rather than misread.
"""

from __future__ import annotations

import re
import struct
import sys

from fmsave._errors import CorruptSaveError
from fmsave.models.transfer_history import PlayerSeasonRecord

if sys.version_info >= (3, 14):
    from compression import zstd
else:
    from backports import zstd

TRANSFER_MAN_SECTION = "transfer_man"

_ROW_LENGTH = 73
# One 73-byte row: the head word, the head id, three 00-null-separated u32
# money fields and a fourth, an 8-byte gap, the type byte, a tick word, the
# season year, a status word, four trailing fields and an unset tail.
_ROW_FORMAT = struct.Struct("<4sIBIBIBI8sIBHHHIIII15s")
assert _ROW_FORMAT.size == _ROW_LENGTH

# The season rows follow the section's record families behind a 12-byte header:
# `03 01 'tad.' <u16 version> <u32 byte count>`.
_HEADER_SIZE = 12

# The zstd frame magic opens every compressed season block.
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

# The row's head word is `00 <u8 variant> <u8 variant> 07`.
_ROW_HEAD = re.compile(b"\x00[\x00\x01][\x00\x01]\x07")

# The nullable fields carry 0xffffffff when unset.
_UNSET = 0xFFFF_FFFF

_YEAR_MIN = 2005
_YEAR_MAX = 2050
_NULL_YEAR = 1900

# A season block that fails to decompress after this many trailing-byte drops is
# not decoded: the compressed tail carries a one-byte block terminator the final
# block alone sits in, and a build may widen that tail a little.
_MAX_TAIL_DROP = 8


def _head_variant(head: bytes) -> tuple[int, int]:
    """The head word's variant bytes."""
    return head[1], head[2]


def _season_year_ok(year: int) -> bool:
    """Whether the season-year field is a calendar year or the null year.

    Rows carrying a 0xffff year all parse as one junk family (club 0, type 1,
    flags 0x01ff) on the layout save, so the sentinel is not accepted: keeping
    it admits ~90 pattern-noise rows per save and no proven real row.
    """
    return year == _NULL_YEAR or _YEAR_MIN <= year <= _YEAR_MAX


def _row(bytes_at: bytes, offset: int) -> PlayerSeasonRecord | None:
    """The record the 73 bytes at `offset` hold, or None they hold no row.

    A row is `00 <u8 variant> <u8 variant> 07` plus three zero null-separators
    around its money fields, a handle and season year inside the layout's
    bounds, and unset sentinels where null.
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
        club_uid=record[1] >> 8,
        slot=record[1] & 0xFF,
        variant_a=variant_a,
        variant_b=variant_b,
        value_a=None if record[3] == _UNSET else record[3],
        value_b=None if record[5] == _UNSET else record[5],
        value_c=None if record[7] == _UNSET else record[7],
        value_d=None if record[9] == _UNSET else record[9],
        record_type=record[10],
        tick=record[11],
        season_year=year,
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
