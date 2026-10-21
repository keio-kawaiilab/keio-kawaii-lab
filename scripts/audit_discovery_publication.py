"""Compare source observations with the final public entities, after all guards."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def _same_ticket_kind(expected, offer, entity):
    if offer.get("ticketType") == expected.get("ticketType"):
        return True
    # The source collector calls these リセール; the source-priority guard
    # deliberately labels the same verified window 公式リセール. Require the
    # original article provenance and an explicit resale channel, not just a
    # similar title, so a genuinely missing/different sale stays degraded.
    aliases = {"リセール", "公式リセール"}
    source_urls = [entity.get("url"), *(entity.get("urls") or []),
                   offer.get("url"), *(offer.get("urls") or []),
                   offer.get("applicationWindowSource"), offer.get("deadlineSource")]
    if (expected.get("ticketType") in aliases and offer.get("ticketType") in aliases
            and (offer.get("provider") == "resale" or offer.get("saleFamily") == "resale")
            and expected.get("url") in source_urls):
        return True
    # Central KAWAII LAB. discovery and a group's collector can name the same
    # official reception "KAWAII LAB. FC先行" and "FC先行".  Treat only that
    # exact label pair as equivalent, with the same official article still
    # attached to the public entity/offer.  Date, performance time and the full
    # application window are compared by audit() outside this helper.
    fc_aliases = {"FC先行", "KAWAII LAB. FC先行"}
    expected_url = str(expected.get("url") or "")
    return (expected.get("ticketType") in fc_aliases
            and offer.get("ticketType") in fc_aliases
            and "/news/detail/" in expected_url
            and expected_url in source_urls)


def audit(state, payload, history=None):
    public = payload.get("publicEvents", [])
    missing, represented, archived = [], 0, 0
    for observation in state.get("observations", []):
        for expected in observation.get("expectedOffers", []):
            if str(expected.get("eventDate") or "") < datetime.now(JST).date().isoformat():
                continue
            end = str(expected.get("applyEnd") or "")
            if end and end[:10] < datetime.now(JST).date().isoformat():
                if any(all(entry.get(key) == expected.get(key) for key in ("group", "eventDate", "ticketType", "applyStart", "applyEnd"))
                       for entry in (history or {}).get("entries", [])):
                    archived += 1
                    continue
            found = False
            for entity in public:
                if entity.get("group") != expected.get("group") or entity.get("eventDate") != expected.get("eventDate"):
                    continue
                if expected.get("startTime") and entity.get("startTime") != expected["startTime"]:
                    continue
                for offer in entity.get("offers", [entity]):
                    if (_same_ticket_kind(expected, offer, entity)
                            and all(offer.get(key) == expected.get(key) for key in ("applyStart", "applyEnd"))):
                        found = True
                        break
                if found:
                    break
            if found:
                represented += 1
            else:
                missing.append(expected)
    return {"checkedAt": datetime.now(JST).isoformat(timespec="seconds"),
            "status": "degraded" if missing or state.get("failureCount") or state.get("pendingReview") else "ok",
            "representedOffers": represented, "archivedEndedOffers": archived, "missingOffers": missing,
            "sourceFailures": state.get("failures", []), "pendingArticles": state.get("pendingReview", 0)}


def main():
    state_path = Path("data/official-discovery-state.json")
    state = json.loads(state_path.read_text()) if state_path.exists() else {"failureCount": 1, "failures": [{"error": "No discovery state"}]}
    history_path = Path("data/ticket-history.json")
    history = json.loads(history_path.read_text()) if history_path.exists() else {}
    report = audit(state, json.loads(Path("data/live-events.json").read_text()), history)
    Path("data/discovery-publication-health.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if report["missingOffers"]:
        # Persist the failed handoff as work for the next scheduled pass. Healthy
        # unrelated observations still publish instead of rolling back the lot.
        missing_urls = {row["url"] for row in report["missingOffers"]}
        for observation in state.get("observations", []):
            if observation["url"] in missing_urls:
                observation["status"] = "publication-missing"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        print(f'::warning::{len(report["missingOffers"])} collected offers absent after publication guards; retained for retry')
    print(json.dumps({key: value for key, value in report.items() if key not in ("missingOffers", "sourceFailures")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
