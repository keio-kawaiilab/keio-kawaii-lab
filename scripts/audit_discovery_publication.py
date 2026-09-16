"""Compare source observations with the final public entities, after all guards."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from update_live_events import JST


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
                    if all(offer.get(key) == expected.get(key) for key in ("ticketType", "applyStart", "applyEnd")):
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
