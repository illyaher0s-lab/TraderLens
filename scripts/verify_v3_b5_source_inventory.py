"""Independently verify a v3 B5 SW2021 source-inventory artifact."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.services.v3_b5_source_inventory import ROOT, verify_source_inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    result = verify_source_inventory(ROOT, args.artifact_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
