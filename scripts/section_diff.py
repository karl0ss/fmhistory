#!/usr/bin/env python3
"""Extract a section from a save and hexdump-diff it against an older snapshot.

Usage: section_diff.py SAVE_NEW SAVE_OLD SECTION [--find-hex HXPATTERN]
Extracts from both, prints the lengths, and (optionally) locates records
matching HXPATTERN in both and shows the local context diff windows.
"""

import argparse
import os
import sys

sys.path.insert(0, "/home/karl/fm26-career/fs")
import fmsave


def extract(save_path: str, section: str) -> bytes:
    save = fmsave.open(save_path)
    try:
        return save._read_section(section)
    finally:
        save.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("save_new")
    ap.add_argument("save_old")
    ap.add_argument("section")
    ap.add_argument("--dump-dir", default="/home/karl/fm26-career/sections")
    ap.add_argument("--old-dump-dir", default="/home/karl/fm26-career/sections_old")
    ap.add_argument("--find-hex", default="")
    ap.add_argument("--window", type=int, default=96)
    args = ap.parse_args()

    for d in (args.dump_dir, args.old_dump_dir):
        os.makedirs(d, exist_ok=True)
    new = extract(args.save_new, args.section)
    old = extract(args.save_old, args.section)
    with open(os.path.join(args.dump_dir, args.section + ".bin"), "wb") as handle:
        handle.write(new)
    with open(os.path.join(args.old_dump_dir, args.section + ".bin"), "wb") as handle:
        handle.write(old)
    print(f"{args.section}: new {len(new)} B / old {len(old)} B (delta {len(new)-len(old):+d})")

    if args.find_hex:
        pat = bytes.fromhex(args.find_hex.replace(" ", ""))
        for label, data in (("NEW", new), ("OLD", old)):
            pos, hits = 0, []
            while True:
                h = data.find(pat, pos)
                if h < 0:
                    break
                pos = h + 1
                hits.append(h)
                if len(hits) > 200:
                    break
            print(f"{label}: {len(hits)} hits")
            for h in hits[:12]:
                print(f"  @0x{h:07x}: {data[h: h + args.window].hex(' ')}")


if __name__ == "__main__":
    main()