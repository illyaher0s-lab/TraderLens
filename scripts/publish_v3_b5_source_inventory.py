"""Publish the v3 B5 SW2021 source-inventory artifact."""
from __future__ import annotations

import json

from backend.services.v3_b5_source_inventory import DEFAULT_OUTPUT_ROOT, ROOT, publish_source_inventory


def main() -> int:
    result = publish_source_inventory(ROOT, DEFAULT_OUTPUT_ROOT)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
