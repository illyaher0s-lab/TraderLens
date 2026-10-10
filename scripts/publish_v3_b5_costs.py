"""Publish the v3-only base/stress transaction-cost artifact."""
from __future__ import annotations

import json

from backend.services.v3_b5_costs import build_cost_artifact


def main() -> None:
    result = build_cost_artifact()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
