#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from audit_schedule_release import audit

NOW = datetime(2026, 8, 23, 13, 30, tzinfo=timezone.utc)


def base_pia(**changes):
    event = {
        "id": "pia-1",
        "group": "CANDY TUNE",
        "eventScope": "kawaii-lab",
        "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
        "ticketType": "プレリザーブ",
        "applyStart": "2026-08-20T10:00",
        "applyEnd": "2026-08-25T23:59",
        "eventDate": "2026-11-10",
        "eventDates": ["2026-11-10", "2026-11-12"],
        "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=12345",
        "urls": ["https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=12345"],
        "sourceType": "pia",
        "primarySource": "pia",
        "applicationStatus": "open",
        "applicationWindowVerified": True,
        "deadlineVerified": True,
        "applicationDisplayMode": "band",
        "applicationWindowSource": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=12345",
        "deadlineSource": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=12345",
    }
    event.update(changes)
    return event


def base_release(**changes):
    official = "https://morestar.asobisystem.com/live_information/detail/44001"
    event = {
        "id": "release-1",
        "group": "MORE STAR",
        "eventScope": "kawaii-lab",
        "title": "MORE STAR 発売記念リリースイベント",
        "ticketType": "商品購入電子整理券（先着）",
        "applyStart": "2026-08-25T21:00",
        "applyEnd": "2026-08-26T09:00",
        "eventDate": "2026-08-26",
        "venue": "ららぽーと立川立飛 2Fイベント広場",
        "url": official,
        "urls": [official, "https://kawaiilab.goods-order.com"],
        "eventCategory": "release-event",
        "purchaseMethod": "アプリで整理券を取得して会場購入",
        "ticketIssueMethod": "KAWAII LAB. STOREアプリ",
        "product": "1stシングル 通常盤 ¥1,200（税込）",
        "salesStartTime": "10:00",
        "gatheringTime": "13:20",
        "startTime": "14:00",
        "numberedCallTimes": [{"numbers": "1〜200番", "time": "09:50"}],
        "sourceType": "official-special",
        "applicationStatus": "open",
        "applicationWindowVerified": True,
        "deadlineVerified": True,
        "applicationWindowSource": official,
        "deadlineSource": official,
    }
    event.update(changes)
    return event


def payload(events):
    return {"updatedAt": "2026-08-23T22:30:00+09:00", "events": events}


class AuditScheduleReleaseTests(unittest.TestCase):
    def test_unchanged_good_release_passes(self):
        old = payload([base_pia()])
        errors, warnings, report = audit(old, copy.deepcopy(old), NOW)
        self.assertEqual([], errors)
        self.assertEqual("ok", report["status"])

    def test_active_future_item_cannot_disappear(self):
        old = payload([base_pia()])
        errors, _, _ = audit(old, payload([]), NOW)
        self.assertTrue(any("disappeared" in error for error in errors))

    def test_redundant_christmas_group_row_may_be_replaced_by_joint_event(self):
        old = payload([{
            "id": "more-summary", "group": "MORE STAR", "eventScope": "kawaii-lab",
            "title": "★MORE STAR チケット先行情報★", "ticketType": "現在受付なし",
            "eventDate": "2026-12-12", "url": "https://morestar.asobisystem.com/news/detail/1",
        }])
        joint = {
            "id": "christmas", "group": "KAWAII LAB.合同", "participants": ["MORE STAR"],
            "eventScope": "kawaii-lab", "title": "KAWAII LAB. Christmas SESSION 2026",
            "ticketType": "現在受付なし", "eventDate": "2026-12-12",
            "url": "https://morestar.asobisystem.com/live_information/detail/2",
        }
        errors, warnings, _ = audit(old, payload([joint]), NOW)
        self.assertEqual([], errors)
        self.assertTrue(any("replaced by joint" in warning for warning in warnings))

    def test_deadline_moving_earlier_is_blocked(self):
        old = payload([base_pia()])
        new = payload([base_pia(applyEnd="2026-08-24T11:00")])
        errors, _, _ = audit(old, new, NOW)
        self.assertTrue(any("deadline moved earlier" in error for error in errors))

    def test_verified_deadline_extension_is_allowed(self):
        old = payload([base_pia()])
        new = payload([base_pia(applyEnd="2026-08-27T23:59")])
        errors, warnings, _ = audit(old, new, NOW)
        self.assertEqual([], errors)
        self.assertTrue(any("deadline extended" in warning for warning in warnings))

    def test_duplicate_pia_lot_is_blocked(self):
        first = base_pia(id="a")
        second = base_pia(id="b")
        errors, _, _ = audit(payload([]), payload([first, second]), NOW)
        self.assertTrue(any("duplicate Pia lot" in error for error in errors))

    def test_reversed_application_window_is_blocked(self):
        event = base_pia(applyStart="2026-08-26T10:00", applyEnd="2026-08-25T23:59")
        errors, _, _ = audit(payload([]), payload([event]), NOW)
        self.assertTrue(any("application window reversed" in error for error in errors))

    def test_pia_fc_or_upgrade_is_blocked(self):
        event = base_pia(ticketType="FC先行")
        errors, _, _ = audit(payload([]), payload([event]), NOW)
        self.assertTrue(any("FC/upgrade-only" in error for error in errors))

    def test_online_sale_requires_sukisuki_product_url(self):
        event = {
            "id": "online-1",
            "group": "CANDY TUNE",
            "eventScope": "kawaii-lab",
            "title": "CANDY TUNE オンライン特典会",
            "ticketType": "オンライン特典会・先着販売",
            "applyStart": "2026-08-23T20:00",
            "applyEnd": "2026-08-24T12:00",
            "eventDate": "2026-08-24",
            "url": "https://example.com/not-sukisuki",
            "eventCategory": "online-benefit",
            "applicationStatus": "open",
        }
        errors, _, _ = audit(payload([]), payload([event]), NOW)
        self.assertTrue(any("no SUKISUKI product URL" in error for error in errors))

    def test_future_performance_date_cannot_silently_vanish(self):
        old = payload([base_pia(eventDates=["2026-11-10", "2026-11-12"])])
        new = payload([base_pia(eventDates=["2026-11-10"])])
        errors, _, _ = audit(old, new, NOW)
        self.assertTrue(any("performance dates disappeared" in error for error in errors))

    def test_complete_release_event_passes(self):
        event = base_release()
        errors, _, _ = audit(payload([event]), payload([copy.deepcopy(event)]), NOW)
        self.assertEqual([], errors)

    def test_canonical_special_event_with_verified_offer_passes(self):
        official = "https://candytune.asobisystem.com/news/detail/88915"
        event = base_release(
            id="canonical-benefit",
            group="CANDY TUNE",
            eventCategory="large-benefit",
            title="CANDY TUNE 大特典会",
            eventDate="2026-09-22",
            venue="東京流通センター 第二展示場 Fホール",
            url=official,
            urls=[official, "https://tower.jp/article/feature_item/example"],
            entityType="special-event",
            specialEventEntityVersion=1,
            ticketType="現在受付なし",
            applicationStatus="none",
            applicationDisplayMode="offers",
            applyStart=None,
            applyEnd=None,
            applicationWindowVerified=None,
            applicationWindowSource=official,
            deadlineSource=official,
            deadlineVerified=True,
            parts=[{
                "part": "第1部", "content": "2ショットチェキ撮影会",
                "start": "10:00", "end": "11:00",
                "receptionStart": "09:45", "receptionEnd": "10:40",
            }],
            offers=[{
                "sourceRowId": "tower-offer",
                "provider": "tower",
                "ticketProvider": "tower",
                "ticketType": "対象商品予約（参加権付き・先着）",
                "applyStart": "2026-09-02T20:00",
                "applyEnd": "2026-09-04T23:59",
                "applicationStatus": "open",
                "applicationWindowVerified": True,
                "url": "https://tower.jp/article/feature_item/example",
                "urls": [official, "https://tower.jp/article/feature_item/example"],
            }],
        )
        errors, _, _ = audit(payload([]), payload([event]), NOW)
        self.assertEqual([], errors)

    def test_canonical_special_event_rejects_unverified_offer(self):
        official = "https://candytune.asobisystem.com/news/detail/88915"
        event = base_release(
            id="canonical-bad",
            entityType="special-event",
            specialEventEntityVersion=1,
            ticketType="現在受付なし",
            applicationStatus="none",
            applicationDisplayMode="offers",
            applyStart=None,
            applyEnd=None,
            applicationWindowVerified=None,
            applicationWindowSource=official,
            deadlineSource=official,
            deadlineVerified=True,
            offers=[{
                "provider": "tower",
                "ticketType": "対象商品予約",
                "url": "https://tower.jp/article/feature_item/example",
            }],
        )
        errors, _, _ = audit(payload([]), payload([event]), NOW)
        self.assertTrue(any("offer has no verified" in error for error in errors))

    def test_schedule_only_special_event_passes_while_details_are_unannounced(self):
        event = {
            "id": "schedule-benefit", "group": "SWEET STEADY", "eventScope": "kawaii-lab",
            "title": "SWEET STEADY 大特典会", "ticketType": "現在受付なし",
            "eventDate": "2026-09-06", "venue": "東京都 ベルサール汐留",
            "url": "https://sweetsteady.asobisystem.com/live_information/detail/43898",
            "sourceType": "official-schedule", "eventCategory": "large-benefit",
            "specialDetailsStatus": "awaiting-details", "applicationDisplayMode": "schedule-only",
            "applicationStatus": "none",
        }
        errors, _, _ = audit(payload([event]), payload([copy.deepcopy(event)]), NOW)
        self.assertEqual([], errors)

    def test_release_event_missing_gathering_time_is_blocked(self):
        errors, _, _ = audit(payload([]), payload([base_release(gatheringTime=None)]), NOW)
        self.assertTrue(any("sales/gathering/start time" in error for error in errors))

    def test_release_event_invalid_call_time_is_blocked(self):
        event = base_release(numberedCallTimes=[{"numbers": "1〜200番", "time": "25:10"}])
        errors, _, _ = audit(payload([]), payload([event]), NOW)
        self.assertTrue(any("invalid numbered-call time" in error for error in errors))

    def test_large_benefit_event_missing_parts_is_blocked(self):
        official = "https://candytune.asobisystem.com/news/detail/87439"
        event = base_release(
            id="benefit-1",
            group="CANDY TUNE",
            eventCategory="large-benefit",
            url=official,
            urls=[official, "https://r10.to/example"],
            applicationWindowSource=official,
            deadlineSource=official,
            parts=[],
        )
        errors, _, _ = audit(payload([]), payload([event]), NOW)
        self.assertTrue(any("no part schedule" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
