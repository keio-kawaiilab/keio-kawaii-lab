#!/usr/bin/env python3
from __future__ import annotations

import copy
import keikyu_official_train_evidence as parser


def word(text, x0, x1, y):
    return {"text": text, "x0": x0, "x1": x1, "top": y - 1.5, "bottom": y + 1.5}


def block(*, below_marker: str, before: str, after: str, number: str = "514T"):
    return [
        word("泉岳寺", 10, 60, 500),
        word("着", 62, 72, 500),
        word(before, 296, 304, 500),
        word("列車番号", 10, 75, 510),
        word(number, 296, 304, 510),
        word("泉岳寺", 10, 60, 520),
        word(below_marker, 62, 72, 520),
        word(after, 296, 304, 520),
    ]


def extract(words):
    rows = parser.extract_page_candidates(
        words,
        page_number=1,
        calendar="weekday",
        source_url="https://example.test/other_weekday.pdf",
    )
    assert len(rows) == 1, rows
    return rows[0]


def test_official_upper_panel_is_toei_to_keikyu():
    # Official upper panel: Toei/Keisei side reaches 泉岳寺着, then the
    # Keikyu section begins at 泉岳寺発.
    row = extract(block(below_marker="発", before="0524", after="0525"))
    assert row["direction"] == "toei-to-keikyu", row
    assert row["sourceBoundaryMinute"] == 324
    assert row["targetBoundaryMinute"] == 325


def test_official_lower_panel_is_keikyu_to_toei():
    # Official lower panel: Keikyu reaches 泉岳寺着; the following Toei-side
    # Sengakuji row is printed with 〃.
    row = extract(block(below_marker="〃", before="0459", after="0500", number="521T"))
    assert row["direction"] == "keikyu-to-toei", row
    assert row["sourceBoundaryMinute"] == 299
    assert row["targetBoundaryMinute"] == 300


def fragments_keikyu_to_toei():
    return [
        {
            "id": "keikyu:source",
            "railway": parser.KEIKYU_MAIN,
            "calendar": "odpt.Calendar:Weekday",
            "stops": [
                ["odpt.Station:Keikyu.Main.Shinagawa", 296, 296],
                ["odpt.Station:Keikyu.Main.Sengakuji", 299, 299],
            ],
        },
        {
            "id": "toei:target",
            "railway": parser.TOEI_ASAKUSA,
            "calendar": "odpt.Calendar:Weekday",
            "stops": [
                ["odpt.Station:Toei.Asakusa.Sengakuji", 300, 300],
                ["odpt.Station:Toei.Asakusa.Mita", 303, 303],
            ],
        },
    ]


def candidate_keikyu_to_toei():
    return {
        "id": "candidate:1",
        "calendar": "weekday",
        "direction": "keikyu-to-toei",
        "sourceBoundaryMinute": 299,
        "targetBoundaryMinute": 300,
        "boundaryTrainNumber": "521T",
        "boundaryId": parser.BOUNDARY_ID,
        "evidence": [
            "operator-official-connection-timetable",
            "same-printed-column-spans-both-sides-of-sengakuji",
        ],
    }


def test_correct_direction_attaches_correct_railway_pair():
    rows = parser.match_candidates_to_fragments(
        [candidate_keikyu_to_toei()],
        fragments_keikyu_to_toei(),
        minute_tolerance=0,
    )
    row = rows[0]
    assert row["matchStatus"] == "matched-singleton", row
    assert row["fromRailway"] == parser.KEIKYU_MAIN
    assert row["toRailway"] == parser.TOEI_ASAKUSA
    assert row["fromFragment"] == "keikyu:source"
    assert row["toFragment"] == "toei:target"


def test_one_minute_nearby_train_does_not_attach_by_default():
    data = fragments_keikyu_to_toei()
    data[0]["stops"][-1][1] = 298
    data[0]["stops"][-1][2] = 298
    rows = parser.match_candidates_to_fragments([candidate_keikyu_to_toei()], data)
    assert rows[0]["matchStatus"] == "unmatched", rows
    assert rows[0]["fromFragment"] is None


def test_ambiguity_fails_closed():
    data = fragments_keikyu_to_toei()
    duplicate = copy.deepcopy(data[1])
    duplicate["id"] = "toei:duplicate"
    data.append(duplicate)
    rows = parser.match_candidates_to_fragments([candidate_keikyu_to_toei()], data, minute_tolerance=0)
    assert rows[0]["matchStatus"] == "ambiguous", rows
    assert rows[0]["toFragment"] is None
    assert len(rows[0]["targetMatches"]) == 2


def test_time_only_never_creates_candidate():
    words = [
        word("泉岳寺", 10, 60, 500), word("着", 62, 72, 500), word("0524", 296, 304, 500),
        word("泉岳寺", 10, 60, 520), word("発", 62, 72, 520), word("0525", 296, 304, 520),
    ]
    assert parser.extract_page_candidates(words, page_number=1, calendar="weekday", source_url="x") == []


def test_same_column_required():
    words = [
        word("泉岳寺", 10, 60, 500), word("着", 62, 72, 500), word("0524", 296, 304, 500),
        word("列車番号", 10, 75, 510), word("514T", 296, 304, 510),
        word("泉岳寺", 10, 60, 520), word("発", 62, 72, 520), word("0525", 350, 358, 520),
    ]
    assert parser.extract_page_candidates(words, page_number=1, calendar="weekday", source_url="x") == []


def main():
    tests = [
        test_official_upper_panel_is_toei_to_keikyu,
        test_official_lower_panel_is_keikyu_to_toei,
        test_correct_direction_attaches_correct_railway_pair,
        test_one_minute_nearby_train_does_not_attach_by_default,
        test_ambiguity_fails_closed,
        test_time_only_never_creates_candidate,
        test_same_column_required,
    ]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("all Keikyu connection timetable tests passed")


if __name__ == "__main__":
    main()
