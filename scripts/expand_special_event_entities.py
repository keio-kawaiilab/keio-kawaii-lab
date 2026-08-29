#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

DATA_PATH = Path("data/live-events.json")


def stable_offer_id(parent_id: str, offer: dict) -> str:
    if offer.get("sourceRowId"):
        return str(offer["sourceRowId"])
    marker = json.dumps(
        [offer.get("provider"), offer.get("ticketType"), offer.get("applyStart"), offer.get("applyEnd"), offer.get("url")],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return parent_id + "-offer-" + hashlib.sha1(marker.encode("utf-8")).hexdigest()[:10]


def expand_entity(event: dict) -> list[dict]:
    if event.get("entityType") != "special-event" or event.get("specialEventEntityVersion") != 1:
        return [copy.deepcopy(event)]

    parent = copy.deepcopy(event)
    offers = [dict(value) for value in parent.pop("offers", []) if isinstance(value, dict)]
    parent.pop("specialEventNormalization", None)
    parent["id"] = str(event.get("id") or "special") + "-schedule"
    parent["ticketType"] = "現在受付なし"
    parent["applicationStatus"] = "none"
    parent["applicationDisplayMode"] = "schedule-only"
    for field in ("ticketProvider", "applyStart", "applyEnd", "resultDate", "paymentEnd", "applicationWindowVerified"):
        parent.pop(field, None)

    rows = [parent]
    parent_urls = [str(value) for value in event.get("urls") or [] if value]
    official_urls = [u for u in parent_urls if "asobisystem.com" in u or "x.com/" in u]
    for offer in offers:
        row = copy.deepcopy(parent)
        row["id"] = stable_offer_id(str(event.get("id") or "special"), offer)
        row.pop("entityType", None)
        row.pop("specialEventEntityVersion", None)
        row.pop("sourceRowIds", None)
        row["applicationDisplayMode"] = "sale"
        for key, value in offer.items():
            if key in {"sourceRowId", "provider"}:
                continue
            if value not in (None, "", [], {}):
                row[key] = copy.deepcopy(value)
        provider = str(offer.get("provider") or offer.get("ticketProvider") or "official")
        row["ticketProvider"] = provider
        if provider != "official":
            row["primarySource"] = provider
        offer_urls = [str(value) for value in offer.get("urls") or [] if value]
        if offer.get("url") and str(offer["url"]) not in offer_urls:
            offer_urls.insert(0, str(offer["url"]))
        combined = []
        for value in offer_urls + official_urls:
            if value and value not in combined:
                combined.append(value)
        if combined:
            row["urls"] = combined
            row["url"] = str(offer.get("url") or combined[0])
        rows.append(row)
    return rows


def expand_payload(payload: dict) -> tuple[dict, dict]:
    output = []
    entity_count = 0
    offer_count = 0
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        if event.get("entityType") == "special-event" and event.get("specialEventEntityVersion") == 1:
            entity_count += 1
            offer_count += len([value for value in event.get("offers") or [] if isinstance(value, dict)])
        output.extend(expand_entity(event))
    out = dict(payload)
    out["events"] = output
    out.pop("specialEventNormalization", None)
    return out, {
        "expandedSpecialEntities": entity_count,
        "expandedOfferRows": offer_count,
        "outputRows": len(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand canonical special-event entities into legacy collector rows")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.data.read_text(encoding="utf-8"))
    expanded, report = expand_payload(payload)
    target = args.output or args.data
    target.write_text(json.dumps(expanded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
