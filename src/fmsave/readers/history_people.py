"""Naming the people history sections reference who are no longer among `players()`.

History rows name people by a save-wide history reference. A person's `game_db` object
closes with the header `[u32 reference][u32 unique_id][u32 unique_id]`; a player's
reference is his record's pindex + 1 and his unique id his uid + 1. Objects sit in
ascending reference order (on the ground-truth save the references of every closing
header found rise with offset without exception), so every person who is not a current
player sits between two players' closing headers, with a reference and a unique id
between theirs. This module finds those headers and reads the name from the bytes just
before each, in one of three forms (see `HistoryPerson`):

    stub              10 00 [u32 first-name id][u32 surname id][4 flag bytes][u32]  18 B
    common-name stub  10 01 [u32 common-name id][4 flag bytes][u32]                 14 B
    object            a full person object: the last person block that validates
                      between the previous closing header and this one

Most retired players keep only the 18-byte stub. Nothing here is a layout-walk: the
headers are found by search, and a person whose header the search misses, or whose
name sits in none of the three forms, is absent or unnamed.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from itertools import pairwise

from fmsave.models.career_history import HistoryPerson
from fmsave.readers.names import NamePools
from fmsave.readers.persons import PersonBlockDecoder

FORM_STUB = "stub"
FORM_COMMON_NAME_STUB = "common_name_stub"
FORM_OBJECT = "object"

_HEADER = struct.Struct("<III")
_UNIQUE_IDS = struct.Struct("<II")
_U32 = struct.Struct("<I")
_HEADER_BYTES = _HEADER.size
_STUB_BYTES = 18
_STUB_TAG = b"\x10\x00"
_COMMON_STUB_BYTES = 14
_COMMON_STUB_TAG = b"\x10\x01"

# (header offset, reference, unique id)
type _Header = tuple[int, int, int]


def locate_player_headers(
    game_db: bytes,
    record_offsets: Sequence[int],
    pindexes: Sequence[int],
    uids: Sequence[int],
) -> list[_Header]:
    """Each player's closing header `[pindex + 1][uid + 1][uid + 1]`, in offset order.

    A record's header is searched for from the record's start up to the next record's
    start. Players whose header is not found there (a closing header with another
    reference, about 0.8% of players on the ground-truth save) are left out, which only
    widens the gap the people between their neighbours are searched in.
    """
    headers: list[_Header] = []
    find = game_db.find
    end_of_data = len(game_db)
    count = len(record_offsets)
    for position in range(count):
        start = record_offsets[position]
        end = record_offsets[position + 1] if position + 1 < count else end_of_data
        reference = pindexes[position] + 1
        unique_id = uids[position] + 1
        hit = find(_HEADER.pack(reference, unique_id, unique_id), start, end + _HEADER_BYTES)
        if hit != -1:
            headers.append((hit, reference, unique_id))
    headers.sort()
    return headers


def _non_player_headers(game_db: bytes, player_headers: Sequence[_Header]) -> list[_Header]:
    """The closing headers between each pair of neighbouring player headers.

    For every reference strictly between the pair's, the first occurrence after the
    previous header found is taken when the two words after it are equal and the unique
    id lies strictly between the pair's unique ids.
    """
    found: list[_Header] = []
    find = game_db.find
    unpack_ids = _UNIQUE_IDS.unpack_from
    pack = _U32.pack
    for (low_offset, low_reference, low_unique), (
        high_offset,
        high_reference,
        high_unique,
    ) in pairwise(player_headers):
        if high_reference - low_reference < 2 or high_unique - low_unique < 2:
            continue
        cursor = low_offset + _HEADER_BYTES
        limit = high_offset
        for reference in range(low_reference + 1, high_reference):
            needle = pack(reference)
            hit = find(needle, cursor, limit)
            while hit != -1:
                unique_id, copy = unpack_ids(game_db, hit + 4)
                if unique_id == copy and low_unique < unique_id < high_unique:
                    found.append((hit, reference, unique_id))
                    cursor = hit + _HEADER_BYTES
                    break
                hit = find(needle, hit + 1, limit)
    return found


def _join_name(first: str | None, last: str | None) -> str | None:
    joined = " ".join(part for part in (first, last) if part)
    return joined or None


def _read_person(
    game_db: bytes,
    header: _Header,
    previous_end: int,
    name_pools: NamePools,
    person_decoder: PersonBlockDecoder,
) -> HistoryPerson:
    offset, reference, unique_id = header
    stub_start = offset - _STUB_BYTES
    if stub_start >= previous_end and game_db.startswith(_STUB_TAG, stub_start):
        first_id, surname_id = _UNIQUE_IDS.unpack_from(game_db, stub_start + 2)
        first = name_pools.first_names.name_at(game_db, first_id)
        last = name_pools.surnames.name_at(game_db, surname_id)
        return HistoryPerson(
            reference, unique_id, FORM_STUB, _join_name(first, last), first, last, None
        )
    common_start = offset - _COMMON_STUB_BYTES
    if common_start >= previous_end and game_db.startswith(_COMMON_STUB_TAG, common_start):
        common_id = _U32.unpack_from(game_db, common_start + 2)[0]
        common = name_pools.common_names.name_at(game_db, common_id)
        return HistoryPerson(
            reference, unique_id, FORM_COMMON_NAME_STUB, common, None, None, common
        )
    person = person_decoder.decode_last(game_db, previous_end, offset + _HEADER_BYTES)
    if person is None:
        return HistoryPerson(reference, unique_id, FORM_OBJECT, None, None, None, None)
    name, first, last, common = person[0], person[1], person[2], person[3]
    return HistoryPerson(reference, unique_id, FORM_OBJECT, name, first, last, common)


def decode_history_people(
    game_db: bytes,
    record_offsets: Sequence[int],
    pindexes: Sequence[int],
    uids: Sequence[int],
    name_pools: NamePools,
    person_decoder: PersonBlockDecoder,
) -> tuple[HistoryPerson, ...]:
    """Every person between two players' closing headers, with the name the save keeps.

    Args:
        game_db: The `game_db` section.
        record_offsets: Player record offsets, ascending, as the player scan gives them.
        pindexes: Each record's pindex, aligned with record_offsets.
        uids: Each record's uid, aligned with record_offsets.
        name_pools: The save's name pools, for the stub forms' name ids.
        person_decoder: Decoder for the full-object form's person block.

    Returns:
        One `HistoryPerson` per closing header found, in ascending reference order.
        References of current players are never returned.
    """
    player_headers = locate_player_headers(game_db, record_offsets, pindexes, uids)
    player_references = {pindex + 1 for pindex in pindexes}
    people_headers = _non_player_headers(game_db, player_headers)
    # Tag each header with whether it closes a person to name, then walk them in offset
    # order so each name is read only from the bytes after the previous header.
    boundaries = sorted(
        [(header, False) for header in player_headers]
        + [(header, header[1] not in player_references) for header in people_headers]
    )
    people: list[HistoryPerson] = []
    previous_end = 0
    for header, is_person in boundaries:
        if is_person:
            people.append(_read_person(game_db, header, previous_end, name_pools, person_decoder))
        previous_end = header[0] + _HEADER_BYTES
    return tuple(people)
