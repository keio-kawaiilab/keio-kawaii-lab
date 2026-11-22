#!/usr/bin/env python3
"""Update MV-only music gacha using six official YouTube channels.

Each weekly run checks 120 recent /videos uploads per channel with yt-dlp.
YouTube RSS is a fallback (only 15 recent items). Only unambiguous, explicitly
labeled official MVs can be added; unclear cases appear in workflow logs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# Verified official channels; include KAWAII LAB. for joint/group MVs.
CHANNELS = {
    "FRUITS ZIPPER": "UCQG8tNnV4hKetLhMb4MopHQ",
    "CANDY TUNE": "UCU0PgOXf0lxzVxN2TLzMJkw",
    "SWEET STEADY": "UC5s_kUbxX3P1q6lmDgygD-w",
    "CUTIE STREET": "UCEz-AFAg3EUKsxraad1puQA",
    "MORE STAR": "UCBkLxz038AbxBA8CMw6o9oA",
    "KAWAII LAB.": "UCW8Q9LBGGBgK6a-u0C0h95A",
}
MV_MARKER = re.compile(
    r"(?i)(?:[【\[（(]\s*(?:official\s+)?(?:mv|m/v|music\s*video)\s*[】\]）)]|"
    r"(?<![a-z])(?:official\s+)?music\s*video(?![a-z])|"
    r"(?<![a-z])official\s+mv(?![a-z]))"
)
EXCLUDE = re.compile(
    r"(?i)(?:teaser|trailer|preview|behind[ -]?the[ -]?scenes|making|"
    r"dance\s*(?:practice|video|performance)|performance\s*video|"
    r"lyric\s*video|live\s*(?:ver\.?|video|performance)|"
    r"instrumental|karaoke|cover\s*(?:ver\.?|song|video)|"
    r"short\s*ver\.?|(?:korean|english|special|acoustic|dance|remix)\s*ver\.?|reaction|remix|"
    r"メイキング|舞台裏|ティザー|予告|ダンスプラクティス|ダンプラ|"
    r"踊ってみた|ライブ映像|歌ってみた|歌詞動画|振付動画|切り抜き|"
    r"ショート版|ダイジェスト|韓国語版|日本語版|英語版|別バージョン)"
)
VIDEO_ID = re.compile(r"^[a-zA-Z0-9_-]{11}$")
QUOTED_TITLE = re.compile(r"[『「](.+?)[』」]")
ATOM_NS = "{http://www.w3.org/2005/Atom}"
YT_NS = "{http://www.youtube.com/xml/schemas/2015}"


def normalized(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


def parse_mv_title(raw: str, source: str) -> tuple[str, str] | None:
    """Return (group, song) only if the official video's title is unambiguous."""
    if not isinstance(raw, str) or not MV_MARKER.search(raw) or EXCLUDE.search(raw):
        return None
    cleaned = MV_MARKER.sub("", raw).strip(" \t\r\n-–—｜|:：")
    mentioned = [group for group in CHANNELS if group in cleaned.upper()]
    if source == "KAWAII LAB.":
        groups = [g for g in mentioned if g != "KAWAII LAB."]
        if len(groups) == 1:
            group = groups[0]
        elif len(groups) == 0 and re.search(r"(?i)^(?:TEAM\s+)?KAWAII\s+LAB\.", cleaned):
            group = "TEAM KAWAII LAB."
        else:
            return None
    else:
        if any(g != source and g != "KAWAII LAB." for g in mentioned):
            return None
        group = source
    quoted = QUOTED_TITLE.search(cleaned)
    if quoted:
        song = quoted.group(1).strip()
    else:
        prefix = re.escape(group if group != "TEAM KAWAII LAB." else "KAWAII LAB.")
        match = re.match(rf"(?i)^\s*(?:{prefix})\s*[-–—｜|:]\s*(.+)$", cleaned)
        if not match:
            return None
        song = match.group(1).strip()
    if not song or len(song) > 110:
        return None
    if re.search(r"(?i)(?:official|full\s*ver\.?|#\w+|\bmv\b|[\[\]【】])", song):
        return None
    return group, song


def load_channel_videos(channel: str, channel_id: str, limit: int = 120) -> tuple[list[dict], str]:
    """Scan /videos; use verified-channel RSS only if the larger scan fails."""
    try:
        import yt_dlp
        opts = {
            "extract_flat": "in_playlist", "playlistend": limit,
            "quiet": True, "no_warnings": True, "skip_download": True,
            "ignoreerrors": False, "socket_timeout": 25,
            "retries": 1, "extractor_retries": 1,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(
                f"https://www.youtube.com/channel/{channel_id}/videos", download=False
            )
        records = []
        for item in (result or {}).get("entries") or []:
            if not item:
                continue
            video_id = item.get("id")
            if VIDEO_ID.fullmatch(video_id or "") and item.get("title"):
                if item.get("channel_id") not in (None, channel_id):
                    continue
                records.append({"id": video_id, "title": item["title"]})
        if records:
            return records, "yt-dlp"
        raise RuntimeError("no titled videos returned")
    except Exception as exc:
        print(f"WARNING {channel}: full scan failed ({exc}); trying YouTube RSS", file=sys.stderr)

    req = urllib.request.Request(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
        headers={"User-Agent": "Mozilla/5.0 (compatible; KawaiiLabMVSync/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        root = ET.fromstring(response.read())
    feed_channel = root.findtext(f"{YT_NS}channelId")
    if feed_channel != channel_id:
        raise RuntimeError(f"RSS channel mismatch for {channel}: {feed_channel!r}")
    records = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        video_id = entry.findtext(f"{YT_NS}videoId")
        title = entry.findtext(f"{ATOM_NS}title")
        if VIDEO_ID.fullmatch(video_id or "") and title:
            records.append({"id": video_id, "title": title})
    if not records:
        raise RuntimeError(f"No RSS items returned for {channel}")
    return records, "rss-limited"


def build_updates(data: dict, channels: dict[str, list[dict]]) -> tuple[dict, list[dict], list[dict]]:
    songs = data.get("songs")
    if not isinstance(songs, list) or not songs:
        raise ValueError("Expected an existing nonempty songs array")
    ids, keys, seq = set(), set(), 0
    for song in songs:
        if song.get("videoType") != "MV" or not VIDEO_ID.fullmatch(song.get("youtubeId", "")):
            raise ValueError("Existing catalog contains a malformed MV")
        if song["youtubeId"] in ids:
            raise ValueError("Duplicate existing YouTube ID")
        ids.add(song["youtubeId"])
        key = (song["group"], normalized(song["title"]))
        if key in keys:
            raise ValueError("Duplicate existing song")
        keys.add(key)
        m = re.fullmatch(r"kwl-mv-(\d+)", song["id"])
        if not m:
            raise ValueError("Unexpected catalog ID")
        seq = max(seq, int(m.group(1)))

    added, ignored = [], []
    for channel in CHANNELS:
        for video in channels.get(channel, []):
            video_id, video_title = video.get("id", ""), video.get("title", "")
            if not VIDEO_ID.fullmatch(video_id) or video_id in ids:
                continue
            parsed = parse_mv_title(video_title, channel)
            if parsed is None:
                if MV_MARKER.search(video_title) and not EXCLUDE.search(video_title):
                    ignored.append({"channel": channel, "title": video_title, "id": video_id})
                continue
            group, title = parsed
            key = (group, normalized(title))
            if key in keys:
                continue
            seq += 1
            song = {
                "id": f"kwl-mv-{seq:03d}", "group": group,
                "title": title, "youtubeId": video_id, "videoType": "MV",
            }
            songs.append(song)
            added.append(song)
            ids.add(video_id)
            keys.add(key)
    if added:
        counts = {}
        for song in songs:
            counts[song["group"]] = counts.get(song["group"], 0) + 1
        metadata = data.setdefault("metadata", {})
        metadata["count"] = len(songs)
        old_counts = metadata.get("countsByGroup") or {}
        metadata["countsByGroup"] = {
            group: counts.pop(group, 0) for group in old_counts
        } | counts
        metadata["lastAutoUpdateUTC"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return data, added, ignored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("data/music-gacha.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    data = json.loads(args.catalog.read_text(encoding="utf-8"))
    channels, failed = {}, []
    for group, channel_id in CHANNELS.items():
        try:
            videos, method = load_channel_videos(group, channel_id)
            channels[group] = videos
            print(f"{group}: scanned {len(videos)} videos via {method}")
        except Exception as exc:
            failed.append(f"{group}: {exc}")
    if failed:
        for error in failed:
            print(f"ERROR {error}", file=sys.stderr)
        print("Refusing to publish an incomplete scan.", file=sys.stderr)
        return 1
    result, added, ignored = build_updates(data, channels)
    for song in added:
        print(f"ADD {song['group']} / {song['title']} https://youtu.be/{song['youtubeId']}")
    for video in ignored:
        print(f"REVIEW {video['channel']} / {video['title']} https://youtu.be/{video['id']}")
    print(f"Added {len(added)} MV(s), ambiguous candidates: {len(ignored)}")
    if added and not args.dry_run:
        args.catalog.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
