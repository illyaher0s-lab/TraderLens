"""Read-only command-line entry point for the existing B4 verifier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.run_v3_b4_is_once import verify_v3_b4_is_result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dir", type=Path)
    args = parser.parse_args()
    response = verify_v3_b4_is_result(args.result_dir)
    print(json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if response.get("status") != "verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
