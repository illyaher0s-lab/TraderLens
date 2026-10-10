"""Standalone verifier for the immutable v3 historical scope freeze."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.publish_v3_historical_scope import (
    DEFAULT_CALENDAR_DIR,
    DEFAULT_CALENDAR_REPO_PATH,
    verify_scope,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope-dir", type=Path, required=True)
    parser.add_argument("--calendar-dir", type=Path, default=DEFAULT_CALENDAR_DIR)
    parser.add_argument("--calendar-repo-path", default=DEFAULT_CALENDAR_REPO_PATH)
    args = parser.parse_args()
    result = verify_scope(
        args.scope_dir,
        calendar_dir=args.calendar_dir,
        calendar_repo_path=args.calendar_repo_path,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
