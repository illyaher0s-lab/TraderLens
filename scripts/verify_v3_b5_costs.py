"""Independently verify a v3-only base/stress transaction-cost artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.services.v3_b5_costs import ROOT, verify_cost_artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_cost_artifact(ROOT, args.artifact_dir), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
