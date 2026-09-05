#!/usr/bin/env python3
from __future__ import annotations

import copy

import keikyu_official_train_evidence as parser


def word(text, x0, x1, y):
    return {"text": text, "x0": x0, "x1": x1, "top": y - 1.5, "bottom": y + 1.5}


def test_extract_keikyu_to_toei():
    words = [
        word("列車番号", 10, 80, 100),
        word("1234H", 296, 304, 100),
        word("5678", 326, 334, 100),
        word("泉岳寺", 10, 65, 500),
        word("着", 68, 80, 500),
        word("0701", 296, 304, 500),
        word("0711", 326, 334, 500),
        word("列車番号", 10, 80, 525),
        word("701K", 296, 304, 525),
    ]
    rows = parser.extract_page_candidates(
        words, page_number=44, calendar="weekday", source_url="https://example.test/weekday.pdf"
    )
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["direction"] == "keikyu-to-toei", row
    assert row["boundaryMinute"] == 7 * 60 + 1, row
    assert row["localKeikyuTrainNumber"] == "1234H", row
    assert row["continuationTrainNumber"] == "701K", row
    assert row["boundaryTimeKind"] == "arrival", row


def test_extract_toei_to_keikyu():
    words = [
        word("列車番号", 10, 80, 100),
        word("1200H", 296, 304, 100),
        word("列車番号", 10, 80, 300),
        word("1101T", 296, 304, 300),
        word("泉岳寺", 10, 65, 325),
        word("発", 68, 80, 325),
        word("0610", 296, 304, 325),
    ]
    rows = parser.extract_page_candidates(
        words, page_number=3, calendar="weekday", source_url="https://example.test/weekday.pdf"
    )
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["direction"] == "toei-to-keikyu", row
    assert row["boundaryMinute"] == 6 * 60 + 10, row
    assert row["localKeikyuTrainNumber"] == "1200H", row
    assert row["continuationTrainNumber"] == "1101T", row
    assert row["boundaryTimeKind"] == "departure", row


def fragments_for_match():
    minute = 7 * 60 + 1
    return [
        {
            "id": "keikyu:source",
            "sourceKind": "station-timetable-reconstruction",
            "railway": parser.KEIKYU_MAIN,
            "calendar": "odpt.Calendar:Weekday",
            "trainNumber": "",
            "stops": [
                ["odpt.Station:Keikyu.Main.Shinagawa", minute - 3, minute - 3],
                ["odpt.Station:Keikyu.Main.Sengakuji", minute, minute],
            ],
        },
        {
            "id": "toei:target",
            "sourceKind": "exact-train-timetable",
            "railway": parser.TOEI_ASAKUSA,
            "calendar": "odpt.Calendar:Weekday",
            "trainNumber": "701K",
            "stops": [
                ["odpt.Station:Toei.Asakusa.Sengakuji", minute + 1, minute + 1],
                ["odpt.Station:Toei.Asakusa.Mita", minute + 4, minute + 4],
            ],
        },
    ]


def candidate_for_match():
    return {
        "id": "candidate:1",
        "calendar": "weekday",
        "direction": "keikyu-to-toei",
        "boundaryMinute": 7 * 60 + 1,
        "localKeikyuTrainNumber": "1234H",
        "continuationTrainNumber": "701K",
        "boundaryId": parser.BOUNDARY_ID,
    }


def test_fragment_match_singleton():
    rows = parser.match_candidates_to_fragments(
        [candidate_for_match()], fragments_for_match(), minute_tolerance=2
    )
    assert rows[0]["matchStatus"] == "matched-singleton", rows
    assert rows[0]["fromFragment"] == "keikyu:source", rows
    assert rows[0]["toFragment"] == "toei:target", rows


def test_fragment_match_ambiguous_fails_closed():
    fragments = fragments_for_match()
    duplicate = copy.deepcopy(fragments[1])
    duplicate["id"] = "toei:target-duplicate"
    fragments.append(duplicate)
    rows = parser.match_candidates_to_fragments(
        [candidate_for_match()], fragments, minute_tolerance=2
    )
    assert rows[0]["matchStatus"] == "ambiguous", rows
    assert rows[0]["toFragment"] is None, rows
    assert len(rows[0]["targetMatches"]) == 2, rows


def test_fragment_train_number_is_only_consistency_check():
    fragments = fragments_for_match()
    fragments[1]["trainNumber"] = "DIFFERENT"
    rows = parser.match_candidates_to_fragments(
        [candidate_for_match()], fragments, minute_tolerance=2
    )
    assert rows[0]["matchStatus"] == "unmatched", rows
    assert not rows[0]["targetMatches"], rows


def test_time_alone_never_creates_candidate():
    words = [
        word("列車番号", 10, 80, 100),
        word("1234H", 296, 304, 100),
        word("泉岳寺", 10, 65, 500),
        word("着", 68, 80, 500),
        word("0701", 296, 304, 500),
    ]
    rows = parser.extract_page_candidates(
        words, page_number=44, calendar="weekday", source_url="https://example.test/weekday.pdf"
    )
    assert rows == [], rows


def main():
    tests = [
        test_extract_keikyu_to_toei,
        test_extract_toei_to_keikyu,
        test_fragment_match_singleton,
        test_fragment_match_ambiguous_fails_closed,
        test_fragment_train_number_is_only_consistency_check,
        test_time_alone_never_creates_candidate,
    ]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("all Keikyu official evidence tests passed")


if __name__ == "__main__":
    main()
