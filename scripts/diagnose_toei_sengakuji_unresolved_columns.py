#!/usr/bin/env python3
"""Print every non-singleton official Sengakuji -> Toei mother-set match."""
from __future__ import annotations

import json
from pathlib import Path

from audit_toei_sengakuji_official_columns import TOEI_FILE, audit, load
from keikyu_official_train_evidence import DEFAULT_HOLIDAY_URL, DEFAULT_WEEKDAY_URL, extract_pdf, fetch_pdf


def main() -> int:
    candidates = []
    for calendar, url in (("weekday", DEFAULT_WEEKDAY_URL), ("holiday", DEFAULT_HOLIDAY_URL)):
        candidates.extend(extract_pdf(fetch_pdf(url), calendar, url))
    payload = audit(candidates, load(TOEI_FILE))
    unresolved = [row for row in payload["results"] if row.get("toeiMatchStatus") != "matched-singleton"]
    print(json.dumps({
        "count": len(unresolved),
        "statusCounts": payload["statusCounts"],
        "rows": unresolved,
    }, ensure_ascii=False, indent=2))
    if len(unresolved) != 36:
        raise RuntimeError(f"current unresolved inventory changed: expected 36, got {len(unresolved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
