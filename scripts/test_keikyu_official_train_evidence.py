#!/usr/bin/env python3
from __future__ import annotations

import copy
import keikyu_official_train_evidence as parser


def word(text, x0, x1, y):
    return {"text": text, "x0": x0, "x1": x1, "top": y - 1.5, "bottom": y + 1.5}


def extract(direction):
    if direction == "keikyu-to-toei":
        upper = [word("泉岳寺", 10, 60, 500), word("発", 62, 72, 500), word("0701", 296, 304, 500)]
        lower = [word("泉岳寺", 10, 60, 520), word("着", 62, 72, 520), word("0702", 296, 304, 520)]
        number = "701K"
    else:
        upper = [word("泉岳寺", 10, 60, 500), word("〃", 62, 72, 500), word("0700", 296, 304, 500)]
        lower = [word("泉岳寺", 10, 60, 520), word("着", 62, 72, 520), word("0701", 296, 304, 520)]
        number = "1200H"
    words = upper + [word("列車番号", 10, 75, 510), word(number, 296, 304, 510)] + lower
    rows = parser.extract_page_candidates(words, page_number=1, calendar="weekday", source_url="https://example.test/other_weekday.pdf")
    assert len(rows) == 1, rows
    return rows[0]


def test_extract_both_directions():
    south = extract("keikyu-to-toei")
    assert south["direction"] == "keikyu-to-toei"
    assert south["sourceBoundaryMinute"] == 421 and south["targetBoundaryMinute"] == 422
    assert south["boundaryTrainNumber"] == "701K"
    north = extract("toei-to-keikyu")
    assert north["direction"] == "toei-to-keikyu"
    assert north["sourceBoundaryMinute"] == 420 and north["targetBoundaryMinute"] == 421


def fragments():
    return [
        {"id":"keikyu:source","railway":parser.KEIKYU_MAIN,"calendar":"odpt.Calendar:Weekday","trainNumber":"","stops":[["odpt.Station:Keikyu.Main.Shinagawa",418,418],["odpt.Station:Keikyu.Main.Sengakuji",421,421]]},
        {"id":"toei:target","railway":parser.TOEI_ASAKUSA,"calendar":"odpt.Calendar:Weekday","trainNumber":"DIFFERENT","stops":[["odpt.Station:Toei.Asakusa.Sengakuji",422,422],["odpt.Station:Toei.Asakusa.Mita",425,425]]},
    ]


def candidate():
    return {"id":"candidate:1","calendar":"weekday","direction":"keikyu-to-toei","sourceBoundaryMinute":421,"targetBoundaryMinute":422,"boundaryTrainNumber":"701K","boundaryId":parser.BOUNDARY_ID,"evidence":["operator-official-connection-timetable","same-printed-column-spans-both-sides-of-sengakuji"]}


def test_singleton_and_train_number_not_identity():
    rows = parser.match_candidates_to_fragments([candidate()], fragments(), minute_tolerance=1)
    assert rows[0]["matchStatus"] == "matched-singleton", rows
    assert rows[0]["fromFragment"] == "keikyu:source" and rows[0]["toFragment"] == "toei:target"


def test_ambiguity_fails_closed():
    data = fragments()
    duplicate = copy.deepcopy(data[1]); duplicate["id"] = "toei:duplicate"; data.append(duplicate)
    rows = parser.match_candidates_to_fragments([candidate()], data, minute_tolerance=1)
    assert rows[0]["matchStatus"] == "ambiguous", rows
    assert rows[0]["toFragment"] is None and len(rows[0]["targetMatches"]) == 2


def test_time_only_never_creates_candidate():
    words = [word("泉岳寺",10,60,500),word("発",62,72,500),word("0701",296,304,500),word("泉岳寺",10,60,520),word("着",62,72,520),word("0702",296,304,520)]
    assert parser.extract_page_candidates(words,page_number=1,calendar="weekday",source_url="x") == []


def test_same_column_required():
    words = [word("泉岳寺",10,60,500),word("発",62,72,500),word("0701",296,304,500),word("列車番号",10,75,510),word("701K",296,304,510),word("泉岳寺",10,60,520),word("着",62,72,520),word("0702",350,358,520)]
    assert parser.extract_page_candidates(words,page_number=1,calendar="weekday",source_url="x") == []


def main():
    tests = [test_extract_both_directions,test_singleton_and_train_number_not_identity,test_ambiguity_fails_closed,test_time_only_never_creates_candidate,test_same_column_required]
    for test in tests:
        test(); print("PASS", test.__name__)
    print("all Keikyu connection timetable tests passed")


if __name__ == "__main__":
    main()
