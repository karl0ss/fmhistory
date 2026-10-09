#!/usr/bin/env python3
"""Walk comp_history_dt's 55-byte rows and print the ones referencing a club uid.

Layout (confirmed on the ground-truth save, 82,800 rows):
  header 0..47:  `03 01 'tmc.' 03 00` + u32(0) + u32(first_season_year)
                 + u32 + u32 + u32(0x1ab0d)  then a sentinel ff run
  rows from offset 55, stride 55, 8-byte tail after the last row:
    [0]  u16 season_start_year        e.g. 1895
    [2]  u16 season_end_year          e.g. 1896
    [4]  u16 small                    e.g. 1, 63, 69, ...
    [6]  u16 year_or_1900             sentinel 1900 where unset
    [8]  11 x u32 slots               club uids / record ids / 0xffffffff
    [52] `00 04 00` 3-byte marker     constant per row?

Usage: decode_comp_history.py SECTION_BIN [--club UID] [--all-rows N]
"""

import argparse
import struct
import sys
from collections import Counter

ROW = 55
ROW0 = 55
ROW_BYTES = struct.Struct("<HHHH11I4s")  # 4 + 44 + 3 = 2 short + padding check below


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("section_bin")
    ap.add_argument("--club", type=int, default=716, help="club uid to filter on")
    ap.add_argument("--all-rows", type=int, default=0, help="print first N raw rows too")
    args = ap.parse_args()

    data = open(args.section_bin, "rb").read()
    body = len(data) - ROW0 - 8
    n_rows, tail = divmod(body, ROW)
    print(f"file {len(data)} B; {n_rows} rows from offset {ROW0}; tail {tail} B", file=sys.stderr)
    print("header:", data[:48].hex(" "), file=sys.stderr)

    rows = []
    for i in range(n_rows):
        off = ROW0 + i * ROW
        raw = data[off : off + ROW]
        y_a, y_b, small, y4 = struct.unpack_from("<HHHH", raw, 0)
        slots = struct.unpack_from("<11I", raw, 8)
        rows.append((off, y_a, y_b, small, y4, slots, raw))

    marker_ok = sum(1 for r in rows if r[6][52:] == b"\x00\x04\x00")
    print(f"rows ending with the 00 04 00 marker: {marker_ok}/{n_rows}", file=sys.stderr)

    hits = [r for r in rows if args.club in r[5]]
    print(f"rows with club {args.club}: {len(hits)}", file=sys.stderr)

    slots_pos = Counter(i for r in hits for i, v in enumerate(r[5]) if v == args.club)
    print("club-in-slot histogram:", dict(sorted(slots_pos.items())), file=sys.stderr)

    print(f"\n== rows for club {args.club} ==")
    for off, y_a, y_b, small, y4, slots, raw in hits:
        s = " ".join("ff" if v == 0xFFFFFFFF else str(v) for v in slots)
        print(f"@0x{off:07x} {y_a}/{y_b} small={small:<4d} y4={y4:<5d} slots: {s}")

    if args.all_rows:
        print(f"\n== first {args.all_rows} rows ==")
        for r in rows[: args.all_rows]:
            off, y_a, y_b, small, y4, slots, raw = r
            s = " ".join("ff" if v == 0xFFFFFFFF else str(v) for v in slots)
            print(f"@0x{off:07x} {y_a}/{y_b} small={small:<4d} y4={y4:<5d} slots: {s}")


if __name__ == "__main__":
    main()