#!/usr/bin/env python3
"""Decode hall_of_fame: person records with inline names + honours rows.

Person record (verified on ground truth; the manager block sits just after an
`04 03 03 00` flag run):

    01 04 00 00 00 "Karl" 07 00 00 00 "Hudgell"
    00 00 00 00
    u16 dob_day_of_year        (0x4c = 76 = 17 March)
    u16 birth_year             (0x07c2 = 1986)
    u32 shared/unknown         (same value 0x008e56e3 for different persons - not an id)
    u32 person_uid             (0x775648bf = manager; = fmsave club/staff uid + 1 encoding)
    01
    u32 765                    (`fd 02 00 00`, every row and person block)
    04 03 03 00

Honours rows referenced afterwards (and interleaved with other persons' rows):

    cc 02 00 00 01 00 <u32 comp_id> fd 02 00 00 02 00 <u16 n>
    01 <01|04> 00 <u16 x> <u16 season_year> 03 03 00

On the ground truth the manager has exactly 4 such rows: (comp 5,123,055, 2025),
(109,202, 2025), (109,201, 2026), (13, 2029) - matching the FA Trophy + Vanarama
South title 2025, National League title 2026, League One title 2029.

Usage: decode_hall_of_fame.py SECTION_BIN [--names first|last|both]
"""

import argparse
import re
import struct

NAME_RE = re.compile(rb"\x04\x00\x00\x00([A-Za-z\x20'-]{2,16})\x07\x00\x00\x00([A-Za-z\x20'-]{2,24})")
ROW_TAIL = b"\x03\x03\x00"


def find_rows(data: bytes):
    """Honours rows: [club u32][01 00][comp u32][fd 02 00 00][02 00][u16 n][5 bytes][year u16]..."""
    rows = []
    for m in re.finditer(b"\xfd\x02\x00\x00\x02\x00", data):
        base = m.start()  # the 765 + 02 00 anchor; comp u32 is 4 before the anchor's fd byte
        if base < 10:
            continue
        club_off = base - 10
        club = struct.unpack_from("<I", data, club_off)[0]
        if data[club_off + 4 : club_off + 6] != b"\x01\x00":
            continue
        comp = struct.unpack_from("<I", data, base - 4)[0]
        n = struct.unpack_from("<H", data, base + 6)[0]
        year_off = base + 13
        if year_off + 2 > len(data):
            continue
        year = struct.unpack_from("<H", data, year_off)[0]
        if not (1850 <= year <= 2050):
            continue
        rows.append((club_off, club, comp, n, year))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("section_bin")
    ap.add_argument("--person", type=int, default=0, help="person uid to filter (e.g. 2002143423)")
    args = ap.parse_args()

    with open(args.section_bin, "rb") as handle:
        data = handle.read()

    # person blocks
    print("== person blocks ==")
    pos = 0
    found = 0
    while found < 400:
        m = NAME_RE.search(data, pos)
        if not m:
            break
        pos = m.end()
        found += 1
        # dob + birth year are the two u16s right after the 00 00 00 00 that follows names
        # names, then 00 00 00 00, then dob, yr, refs
        tail = data[m.end() : m.end() + 40]
        zero = tail.find(b"\x00\x00\x00\x00")
        dob, yr = struct.unpack_from("<HH", tail, zero + 4)
        ref, uid = struct.unpack_from("<II", tail, zero + 8)
        if 1850 <= yr <= 2050 and 0 < dob <= 366:
            print(f"  {m.group(1).decode():12s} {m.group(2).decode():20s} dob_day {dob} born {yr} "
                  f"uid 0x{uid:08x} ref 0x{ref:08x}")

    # honours rows
    print("== honours rows ==")
    rows = find_rows(data)
    by_club = {}
    for off, club, comp, n, year in rows:
        by_club.setdefault(club, []).append((comp, n, year, off))
    for club in sorted(by_club):
        rows_c = sorted(by_club[club], key=lambda r: r[3])
        print(f"club {club} (uid 0x{club:x}): {len(rows_c)} honours rows")
        for comp, n, year, off in rows_c:
            print(f"   @0x{off:07x} comp {comp} (0x{comp:x}) year {year} n {n}")


if __name__ == "__main__":
    main()