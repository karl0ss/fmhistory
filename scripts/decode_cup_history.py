#!/usr/bin/env python3
"""Decode tc_cup_history_dt: one 18-byte row per (club, competition, season) cup entry.

Verified against the ground-truth save (section 2,978,828 B):
  header `03 01 'tmc.' 01 00`, then a flat 18-byte row array from offset 4:
  [u32 club][u32 comp][u16 y1][u16 y2] `02 01` `ff ff` `ff 00`
  (165,490 rows; 61,034 of them carry club 0xffffffff, a competition record without
  a club). The span y1->y2 is usually one season but same-year rows exist and a few
  spans cover two years: 99.95 percent of rows have y2 in y1..y1+2.

Usage: decode_cup_history.py SECTION_BIN [--club UID] [--comp COMP] [--years N]
"""

import argparse
import struct
import sys
from collections import Counter

ROW = 18
ROW0 = 4


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("section_bin")
    ap.add_argument("--club", type=int, default=716)
    ap.add_argument("--comp", type=int, default=0, help="filter on competition id")
    ap.add_argument("--min-year", type=int, default=1900)
    args = ap.parse_args()

    with open(args.section_bin, "rb") as handle:
        data = handle.read()
    n = (len(data) - ROW0) // ROW
    rows = []
    for i in range(n):
        off = ROW0 + i * ROW
        cl, comp, y1, y2 = struct.unpack_from("<IIHH", data, off)
        flags = data[off + 12 : off + 16]
        rows.append((off, cl, comp, y1, y2, flags))

    sane = sum(1 for r in rows if 1850 <= r[3] <= 2050 and r[3] <= r[4] <= r[3] + 2)
    print(f"rows: {n} (span-valid: {sane})", file=sys.__stderr__)
    print(f"header: {data[:16].hex(' ')}", file=sys.__stderr__)

    hits = [
        r
        for r in rows
        if r[1] == args.club and r[3] >= args.min_year and (not args.comp or r[2] == args.comp)
    ]
    print(f"rows for club {args.club}: {len(hits)}")

    comp_counts = Counter(r[2] for r in hits)
    for comp, cnt in sorted(comp_counts.items()):
        seasons = sorted(f"{y1}/{y1 + 1}" for _, _, c, y1, _, _ in hits if c == comp)
        print(f"comp 0x{comp:x} ({comp}): {cnt} rows  {', '.join(seasons)}")


if __name__ == "__main__":
    main()