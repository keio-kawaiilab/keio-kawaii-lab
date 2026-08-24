#!/usr/bin/env python3
"""Single source of truth for hosted-vs-external schedule classification."""
from __future__ import annotations

import re
import unicodedata

HOSTED = "kawaii-lab"
EXTERNAL = "external"
VALID_SCOPES = {HOSTED, EXTERNAL}

EXTERNAL_HINT_RE = re.compile(
    r"(?:FEST(?:IVAL)?|フェス|TGC|東京ガールズコレクション|RUNWAY|ランウェイ|"
    r"ROCK IN JAPAN|CDTV|AGESTOCK|atmoscon|TOMAKOMAI|MotoGP|マグロック|"
    r"GIFT|METALVERSE|STARフェス|CONTI[-‐‑‒–—―]?NeW|KAWAII KON)",
    re.I,
)
HOSTED_HINT_RE = re.compile(
    r"(?:KAWAII LAB\.?\s*(?:Christmas SESSION|COLLECTION|SESSION|主催)|"
    r"JAPAN (?:ARENA )?TOUR|ANNIVERSARY LIVE|生誕祭|BIRTHDAY|"
    r"大特典会|リリースイベント|発売記念イベント|オンライン(?:特典会|サイン会)|"
    r"ワンマン|単独(?:公演|ライブ)|ファンミーティング)",
    re.I,
)
KAWAII_LAB_HOSTED_RE = re.compile(r"KAWAII LAB\.?\s*(?:Christmas SESSION|COLLECTION|SESSION|主催)", re.I)


def normalized_text(event: dict) -> str:
    values = (
        event.get("eventTitle"), event.get("displayTitle"), event.get("title"),
        event.get("eventCategory"), event.get("ticketType"),
    )
    return unicodedata.normalize("NFKC", " ".join(str(value or "") for value in values))


def special_event_category(title: object) -> str | None:
    """Return the public special-event category encoded in an official title."""
    text = unicodedata.normalize("NFKC", str(title or ""))
    if "大特典会" in text:
        return "large-benefit"
    if re.search(r"リリースイベント|発売記念イベント", text):
        return "release-event"
    if re.search(r"オンライン(?:特典会|サイン会)", text):
        return "online-benefit"
    return None


def infer_event_scope(event: dict) -> str:
    """Classify conservatively: unknown appearances stay out of the default view."""
    explicit = str(event.get("eventScope") or "").strip().lower()
    if explicit in VALID_SCOPES:
        return explicit

    category = str(event.get("eventCategory") or "").lower()
    if category in {"online-benefit", "large-benefit", "release-event"}:
        return HOSTED

    text = normalized_text(event)
    if KAWAII_LAB_HOSTED_RE.search(text):
        return HOSTED
    if EXTERNAL_HINT_RE.search(text):
        return EXTERNAL
    if HOSTED_HINT_RE.search(text):
        return HOSTED
    group = unicodedata.normalize("NFKC", str(event.get("group") or ""))
    if group and group in text and re.search(r"\bLIVE\b", text, re.I):
        return HOSTED
    return EXTERNAL


def apply_event_scope(event: dict, *, overwrite: bool = False) -> dict:
    out = dict(event)
    if overwrite or str(out.get("eventScope") or "").lower() not in VALID_SCOPES:
        out["eventScope"] = infer_event_scope({key: value for key, value in out.items() if key != "eventScope"})
    return out
