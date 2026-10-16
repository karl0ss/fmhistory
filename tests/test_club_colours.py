from __future__ import annotations

import struct

import fmsave
from fmsave import ClubColours, Kit
from fmsave._layouts import fm26_26_3_2
from fmsave._reader_stats import ClubColourStats
from fmsave.readers.club_colours import read_club_colours

LAYOUT = fm26_26_3_2.CLUB_COLOURS
WHITE, RED, NAVY = 0x7FFF, 0x7C00, 0x000F


def block_head(index: int, values: tuple[int, ...] = (700, 701)) -> bytes:
    """A club block's head: its index, the counted u32s, a flagged tail and three dates."""
    head = struct.pack("<I", index) + bytes((5, 5, 0, len(values), 0))
    head += b"".join(struct.pack("<I", value) for value in values)
    head += b"\x01" + bytes(9)  # flag 1: ten bytes from the flag
    head += struct.pack("<HHHHHH", 122, 2026, 174, 2025, 214, 2025)
    return head + struct.pack("<HH", 1, 1900) * 3


def kit(colours: tuple[int, ...], kit_set: int, part: int, pair: int = -1) -> bytes:
    body = b"\x01\x01" + struct.pack("<5H", *colours) + b"\x01"
    return body + struct.pack("<ii", pair, pair) + bytes((0, 0, kit_set, part, 0, 1))


def kit_list(kits: list[bytes], first: tuple[int, int, int], second: tuple[int, int, int]) -> bytes:
    handle = struct.pack("<HH", 1, 1892) + b"\xff" * 4 + b"\x3c\x00" + struct.pack("<I", 0)
    colours = b"\xff" + bytes(first) + b"\xff" + bytes(second)
    return handle + bytes((len(kits),)) + b"".join(kits) + colours + bytes(16)


def read(game_db: bytes, indexes: dict[int, int]) -> tuple[list[ClubColours], ClubColourStats]:
    names = {uid: f"Club {uid}" for uid in indexes.values()}
    return read_club_colours(game_db, indexes, names, LAYOUT)


def test_a_list_takes_the_nearest_block_head_before_it() -> None:
    # Club 2 stores no kits, but its block sits between club 1's list and club 3's own head.
    game_db = (
        bytes(64)
        + block_head(1)
        + bytes(40)
        + kit_list([kit((WHITE, RED, WHITE, WHITE, 0), 0, 1)], (207, 28, 44), (250, 250, 250))
        + block_head(2)
        + bytes(80)
        + block_head(3, values=(1, 2, 3, 4))
        + bytes(24)
        + kit_list(
            [kit((WHITE, NAVY, WHITE, 0, 0), 0, 1, pair=11), kit((RED, NAVY, 0, 0, 0), 1, 1)],
            (38, 72, 139),
            (250, 250, 250),
        )
    )
    rows, stats = read(game_db, {1: 501, 2: 502, 3: 503})

    assert [row.club_uid for row in rows] == [501, 503]
    assert (rows[0].first_colour, rows[0].second_colour) == ("#CF1C2C", "#FAFAFA")
    assert rows[0].kits == (Kit(0, 1, ("#FFFFFF", "#FF0000", "#FFFFFF", "#FFFFFF", None), 1),)
    assert rows[1].first_colour == "#26488B"
    assert [(k.kit_set, k.colours[1]) for k in rows[1].kits] == [(0, "#00007B"), (1, "#00007B")]
    assert (stats.kit_lists, stats.placed, stats.clubs) == (2, 2, 3)


def test_a_jump_past_the_window_is_bridged_and_a_list_without_a_head_is_left_out() -> None:
    far = LAYOUT.index_window + 30
    lonely = kit_list([kit((WHITE, RED, 0, 0, 0), 0, 1)], (0, 0, 0), (250, 250, 250))
    game_db = (
        bytes(64)
        + block_head(1)
        + kit_list([kit((RED, WHITE, 0, 0, 0), 0, 1)], (207, 28, 44), (250, 250, 250))
        + bytes(32)
        + lonely
        + block_head(far)
        + kit_list([kit((NAVY, WHITE, 0, 0, 0), 0, 1)], (38, 72, 139), (250, 250, 250))
    )
    rows, stats = read(game_db, {1: 501, far: 600})

    assert [row.club_uid for row in rows] == [501, 600]
    assert (stats.kit_lists, stats.placed) == (3, 2)


def test_club_colours_are_exported() -> None:
    assert fmsave.ClubColours is ClubColours
    assert fmsave.field_status(Kit, "part") == "unconfirmed"
