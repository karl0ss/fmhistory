"""Tests for naming the people history rows reference (`decode_history_people`)."""

from __future__ import annotations

import struct

import pytest

from fmsave import field_status
from fmsave.models.career_history import BestElevenEntry, HistoryPerson
from fmsave.readers.history_people import (
    FORM_COMMON_NAME_STUB,
    FORM_OBJECT,
    FORM_STUB,
    decode_history_people,
    locate_player_headers,
)
from fmsave.readers.names import locate_name_pools
from tests.test_persons import (
    FILE_NAME,
    PLAYER_A_BLOCK,
    PLAYER_B_BLOCK,
    build_decoder,
    game_db_prefix,
    registered_name_pool_layout,
)

# Name pools in `game_db_prefix()`: first names Alex, Sam; surnames Example, Sample;
# common names Exo, Pim.
_FLAGS = b"\x01\x22\x58\x10"


def header(reference: int, unique_id: int) -> bytes:
    """A closing header: [reference][unique id][unique id]."""
    return struct.pack("<III", reference, unique_id, unique_id)


def stub(first_id: int, surname_id: int) -> bytes:
    """The 18-byte name stub: 10 00 [first-name id][surname id][flags][u32 4]."""
    return b"\x10\x00" + struct.pack("<II", first_id, surname_id) + _FLAGS + struct.pack("<I", 4)


def common_stub(common_id: int) -> bytes:
    """The 14-byte common-name stub: 10 01 [common-name id][flags][u32 4]."""
    return b"\x10\x01" + struct.pack("<I", common_id) + _FLAGS + struct.pack("<I", 4)


class _Body:
    """A game_db built from the fixture prefix with player and people objects after it."""

    def __init__(self) -> None:
        self.data = bytearray(game_db_prefix())
        self.record_offsets: list[int] = []
        self.pindexes: list[int] = []
        self.uids: list[int] = []

    def player(self, pindex: int, uid: int) -> None:
        self.record_offsets.append(len(self.data))
        self.pindexes.append(pindex)
        self.uids.append(uid)
        self.data += bytes(40) + header(pindex + 1, uid + 1)

    def add(self, chunk: bytes) -> None:
        self.data += chunk

    def decode(self) -> tuple[HistoryPerson, ...]:
        game_db = bytes(self.data)
        name_pools = locate_name_pools(game_db, registered_name_pool_layout(), FILE_NAME)
        return decode_history_people(
            game_db,
            self.record_offsets,
            self.pindexes,
            self.uids,
            name_pools,
            build_decoder(game_db),
        )


def test_all_three_name_forms_between_two_players() -> None:
    body = _Body()
    body.player(9, 100)
    body.add(stub(1, 0) + header(11, 102))
    body.add(common_stub(1) + header(12, 103))
    body.add(PLAYER_A_BLOCK + bytes(8) + header(13, 104))
    body.player(19, 199)
    people = body.decode()
    assert [(p.reference, p.unique_id, p.form, p.name) for p in people] == [
        (11, 102, FORM_STUB, "Sam Example"),
        (12, 103, FORM_COMMON_NAME_STUB, "Pim"),
        (13, 104, FORM_OBJECT, "Alex Example"),
    ]
    assert (people[0].first_name, people[0].last_name, people[0].common_name) == (
        "Sam",
        "Example",
        None,
    )
    assert people[1].common_name == "Pim"
    assert people[1].first_name is None


def test_object_form_takes_the_last_block_before_its_header() -> None:
    """An unfound object between two headers must not lend its block to the next person."""
    body = _Body()
    body.player(9, 100)
    body.add(PLAYER_A_BLOCK + bytes(8) + PLAYER_B_BLOCK + bytes(8) + header(11, 102))
    body.player(19, 199)
    game_db = bytes(body.data)
    decoder = build_decoder(game_db)
    b_start = game_db.find(PLAYER_B_BLOCK)
    expected = decoder.decode(game_db, b_start, len(game_db))
    assert expected is not None
    (person,) = body.decode()
    assert person.name == expected[0]
    assert person.name != "Alex Example"


def test_header_without_a_readable_name_is_kept_unnamed() -> None:
    body = _Body()
    body.player(9, 100)
    body.add(bytes(64) + header(11, 102))
    body.player(19, 199)
    (person,) = body.decode()
    assert (person.reference, person.form, person.name) == (11, FORM_OBJECT, None)


@pytest.mark.parametrize(
    "chunk",
    [
        pytest.param(stub(1, 0) + header(11, 300), id="unique-id-above-the-bracket"),
        pytest.param(stub(1, 0) + header(11, 50), id="unique-id-below-the-bracket"),
        pytest.param(stub(1, 0) + struct.pack("<III", 11, 102, 103), id="ids-not-doubled"),
        pytest.param(stub(1, 0) + header(25, 102), id="reference-outside-the-bracket"),
    ],
)
def test_headers_outside_the_player_bracket_are_not_people(chunk: bytes) -> None:
    body = _Body()
    body.player(9, 100)
    body.add(chunk)
    body.player(19, 199)
    assert body.decode() == ()


def test_a_current_players_reference_is_never_returned() -> None:
    """A player whose own header is not found leaves a gap, but his reference stays his."""
    body = _Body()
    body.player(9, 100)
    body.add(stub(1, 0) + header(11, 102))
    # Player pindex 11 (reference 12) whose closing header carries another unique id.
    body.record_offsets.append(len(body.data))
    body.pindexes.append(11)
    body.uids.append(149)
    body.add(bytes(40) + stub(0, 1) + header(12, 103))
    body.player(19, 199)
    assert [p.reference for p in body.decode()] == [11]


def test_locate_player_headers_skips_a_record_without_its_header() -> None:
    body = _Body()
    body.player(9, 100)
    body.record_offsets.append(len(body.data))
    body.pindexes.append(10)
    body.uids.append(150)
    body.add(bytes(40))
    body.player(19, 199)
    found = locate_player_headers(bytes(body.data), body.record_offsets, body.pindexes, body.uids)
    assert [(reference, unique_id) for _offset, reference, unique_id in found] == [
        (10, 101),
        (20, 200),
    ]


def test_history_person_and_best_eleven_name_fields_are_unconfirmed() -> None:
    for name in HistoryPerson.__dataclass_fields__:
        assert field_status(HistoryPerson, name) == "unconfirmed"
    assert field_status(BestElevenEntry, "player_name") == "unconfirmed"
