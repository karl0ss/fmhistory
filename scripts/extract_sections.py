"""Extract (decompressed) sections of an FM26 save for history-decoder work.

Usage: extract_sections.py SAVE [-o OUTDIR] [section ...]
No default sections: pass the ones you want."""
from __future__ import annotations

import argparse
import os
import sys
import warnings

import fmsave

warnings.filterwarnings("ignore", module="fmsave")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("save")
    ap.add_argument("-o", "--out-dir", default="sections")
    ap.add_argument("sections", nargs="*")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    with fmsave.open(args.save) as save:
        names = args.sections or [k for k, v in save._container_index.sections.items() if v.is_section]
        for name in names:
            data = save._read_section(name)
            path = os.path.join(args.out_dir, f"{name}.bin")
            with open(path, "wb") as handle:
                handle.write(data)
            print(f"{name}: {len(data):,} bytes -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
