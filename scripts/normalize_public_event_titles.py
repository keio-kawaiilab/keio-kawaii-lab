#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

DATA = Path("data/live-events.json")
PAGE = Path("schedule.html")

ANNOUNCEMENT_RE = re.compile(
    r"(?:出演|開催)決定|"
    r"(?:FC(?:会員)?|ファンクラブ|オフィシャル)?\s*(?:先行)?受付開始|"
    r"(?:先行|一般発売|チケット)[^!！。]{0,24}(?:受付|販売)(?:開始|スタート)|"
    r"(?:チケット|FC)[^!！。]{0,24}(?:お知らせ|ご案内)",
    re.I,
)
DATE_PREFIX_RE = re.compile(
    r"^(?:20\d{2}[.\/-]\d{1,2}[.\/-]\d{1,2}\s*)?"
    r"(?:20\d{2}年\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*)?"
)
COMPACT_RE = re.compile(r"[\s　!！・･|｜\-–—_\[\]()（）『』「」,，.。:：/／]+")


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _compact(value: Any) -> str:
    return COMPACT_RE.sub("", _text(value).casefold())


def _candidates(event: dict[str, Any]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for field in ("displayTitle", "eventTitle", "title"):
        value = _text(event.get(field))
        if value and value not in seen:
            seen.add(value)
            result.append((field, value))
    return result


def _is_announcement(value: str) -> bool:
    return bool(ANNOUNCEMENT_RE.search(value))


def _is_generic(value: str, group: str) -> bool:
    compact = _compact(value)
    group_compact = _compact(group)
    return not compact or compact in {group_compact, group_compact + "公演", "kawaiilab公演"}


def _source_score(source: dict[str, Any], field: str, value: str) -> tuple[int, int, int, int, str]:
    source_type = _text(source.get("sourceType")).casefold()
    primary = _text(source.get("primarySource")).casefold()
    field_score = {"displayTitle": 3, "eventTitle": 2, "title": 1}.get(field, 0)
    authority = 3 if source_type == "official-schedule" else 2 if primary == "official" else 1
    date_penalty = 0 if DATE_PREFIX_RE.match(value).end() == 0 else -1
    return (
        authority,
        field_score,
        date_penalty,
        len(_compact(value)),
        value,
    )


def choose_corroborated_title(
    public_event: dict[str, Any],
    source_index: dict[str, dict[str, Any]],
) -> tuple[str, str] | None:
    """Return a clean title only when another source corroborates it.

    We never invent or regex-trim a title.  A replacement must already exist on
    one of the source rows merged into the same physical performance, must not
    look like announcement copy, and its normalized text must be contained in
    the current announcement headline.
    """
    current = _text(
        public_event.get("displayTitle")
        or public_event.get("eventTitle")
        or public_event.get("title")
    )
    if not current or not _is_announcement(current):
        return None

    group = _text(public_event.get("group"))
    current_compact = _compact(current)
    choices: list[tuple[tuple[int, int, int, int, str], str, str]] = []
    for source_id in public_event.get("sourceRowIds") or []:
        source = source_index.get(_text(source_id))
        if not source:
            continue
        for field, candidate in _candidates(source):
            candidate_compact = _compact(candidate)
            if _is_announcement(candidate) or _is_generic(candidate, group):
                continue
            if not candidate_compact or candidate_compact == current_compact:
                continue
            if candidate_compact not in current_compact:
                continue
            choices.append((_source_score(source, field, candidate), candidate, _text(source_id)))

    if not choices:
        return None
    _, candidate, source_id = max(choices, key=lambda row: row[0])
    return candidate, source_id


def normalize_public_events(payload: dict[str, Any]) -> dict[str, str]:
    source_index = {
        _text(event.get("id")): event
        for event in payload.get("events") or []
        if isinstance(event, dict) and _text(event.get("id"))
    }
    corrected: dict[str, str] = {}
    for event in payload.get("publicEvents") or []:
        if not isinstance(event, dict) or event.get("entityType") != "performance":
            continue
        selected = choose_corroborated_title(event, source_index)
        if selected is None:
            continue
        title, source_id = selected
        original = _text(event.get("displayTitle") or event.get("eventTitle") or event.get("title"))
        event["title"] = title
        event["eventTitle"] = title
        event["displayTitle"] = title
        event["publicTitleOriginal"] = original
        event["publicTitleSourceRowId"] = source_id
        event["publicTitleNormalization"] = "corroborated-source-title"
        event_id = _text(event.get("id"))
        if event_id:
            corrected[event_id] = title
    return corrected


def _patch_snapshot(page: str, corrected: dict[str, str]) -> str:
    pattern = re.compile(r'(<script id="snapshot-data" type="application/json">)(.*?)(</script>)', re.S)
    match = pattern.search(page)
    if not match:
        raise RuntimeError("snapshot-data block is missing; cannot normalize public titles")
    snapshot = json.loads(match.group(2))
    for event in snapshot.get("events") or []:
        if not isinstance(event, dict):
            continue
        title = corrected.get(_text(event.get("id")))
        if not title:
            continue
        event["title"] = title
        event["eventTitle"] = title
        event["displayTitle"] = title
        event["publicTitleNormalization"] = "corroborated-source-title"
    encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return page[: match.start()] + match.group(1) + encoded + match.group(3) + page[match.end() :]


def _patch_static_cards(page: str, corrected: dict[str, str]) -> str:
    for event_id, title in corrected.items():
        escaped_id = re.escape(html.escape(event_id, quote=True))
        pattern = re.compile(
            rf'(<article\b[^>]*\bdata-event-id="{escaped_id}"[^>]*>.*?<h3>).*?(</h3>)',
            re.S,
        )
        replacement = lambda match, value=title: match.group(1) + "🎤 " + html.escape(value, quote=False) + match.group(2)
        page, count = pattern.subn(replacement, page, count=1)
        if count != 1:
            raise RuntimeError(f"could not patch static title for {event_id}")
    return page


def _verify_repository_case(payload: dict[str, Any], page: str) -> None:
    target_id = "performance-MORE-STAR-2026-10-17-time-16-30"
    target = next(
        (
            event
            for event in payload.get("publicEvents") or []
            if isinstance(event, dict) and event.get("id") == target_id
        ),
        None,
    )
    if target is None:
        return
    expected = "FM大阪 『Live or Treat 2026』 in Zepp Namba"
    actual = _text(target.get("displayTitle") or target.get("eventTitle") or target.get("title"))
    if actual != expected:
        raise RuntimeError(f"MORE STAR Live or Treat public title is not canonical: {actual!r}")
    if target.get("publicTitleNormalization") != "corroborated-source-title":
        raise RuntimeError("MORE STAR Live or Treat title lacks normalization provenance")

    raw = next(
        (
            event
            for event in payload.get("events") or []
            if isinstance(event, dict) and event.get("id") == "f054f2a8893de7de"
        ),
        None,
    )
    if raw is not None and "FC会員先行受付開始" not in _text(raw.get("title")):
        raise RuntimeError("raw acquisition title was unexpectedly rewritten")

    article = re.search(
        rf'<article\b[^>]*data-event-id="{re.escape(target_id)}"[^>]*>.*?</article>',
        page,
        re.S,
    )
    if not article:
        raise RuntimeError("MORE STAR Live or Treat static card is missing")
    card = article.group(0)
    if expected not in html.unescape(card):
        raise RuntimeError("MORE STAR Live or Treat static card lacks canonical title")
    if "FC会員先行受付開始" in html.unescape(card):
        raise RuntimeError("announcement copy still leaks into MORE STAR public card title")


def main() -> int:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    corrected = normalize_public_events(payload)
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    page = PAGE.read_text(encoding="utf-8")
    page = _patch_snapshot(page, corrected)
    page = _patch_static_cards(page, corrected)
    PAGE.write_text(page, encoding="utf-8")

    _verify_repository_case(payload, page)
    print(json.dumps({"normalizedPublicTitles": len(corrected), "ids": sorted(corrected)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
