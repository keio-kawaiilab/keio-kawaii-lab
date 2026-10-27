import copy
import unittest

from audit_discovery_publication import audit


class DiscoveryPublicationTest(unittest.TestCase):
    def fixture(self):
        expected = {"group": "FRUITS ZIPPER", "eventDate": "2099-11-14",
                    "ticketType": "リセール", "applyStart": "2099-11-12T10:00",
                    "applyEnd": "2099-11-13T23:59", "url": "https://fruitszipper.asobisystem.com/news/detail/88139"}
        entity = {"group": expected["group"], "eventDate": expected["eventDate"],
                  "urls": [expected["url"]], "offers": [{"provider": "resale", "ticketType": "公式リセール",
                  "applyStart": expected["applyStart"], "applyEnd": expected["applyEnd"]}]}
        return {"observations": [{"expectedOffers": [expected]}]}, {"publicEvents": [entity]}

    def test_schedule_only_official_announcement_is_not_missing_ticket(self):
        state = {"observations": [{"expectedOffers": [
            {"group": "FRUITS ZIPPER", "eventDate": "2099-01-19",
             "ticketType": "現在受付なし", "url": "https://fruitszipper.asobisystem.com/news/detail/new"}
        ]}]}
        report = audit(state, {"publicEvents": []})
        self.assertEqual([], report["missingOffers"])
        self.assertEqual("ok", report["status"])

    def test_verified_resale_label_alias_is_represented(self):
        state, payload = self.fixture()
        report = audit(state, payload)
        self.assertEqual("ok", report["status"])
        self.assertEqual(1, report["representedOffers"])

    def test_joint_external_entity_represents_participant_offer(self):
        state, payload = self.fixture()
        payload["publicEvents"][0]["group"] = "KAWAII LAB.合同"
        payload["publicEvents"][0]["participants"] = ["FRUITS ZIPPER", "CANDY TUNE"]
        report = audit(state, payload)
        self.assertEqual("ok", report["status"])
        self.assertEqual(1, report["representedOffers"])

    def test_joint_nonparticipant_date_still_represents_group_fc_sales_route(self):
        source = "https://sweetsteady.asobisystem.com/news/detail/93737"
        expected = {
            "group": "SWEET STEADY", "eventDate": "2099-04-03",
            "startTime": "17:00", "ticketType": "SWEET STEADY FC先行",
            "applyStart": "2098-10-26T12:00", "applyEnd": "2098-11-09T23:59",
            "url": source,
        }
        entity = {
            "group": "KAWAII LAB.合同", "eventDate": expected["eventDate"],
            "startTime": expected["startTime"],
            "participants": ["FRUITS ZIPPER", "CANDY TUNE", "CUTIE STREET", "MORE STAR"],
            "offers": [{
                "ticketType": expected["ticketType"],
                "applyStart": expected["applyStart"], "applyEnd": expected["applyEnd"],
                "url": source, "applicationWindowSource": source,
            }],
        }
        state = {"observations": [{"expectedOffers": [expected]}]}
        report = audit(state, {"publicEvents": [entity]})
        self.assertEqual([], report["missingOffers"])
        self.assertEqual(1, report["representedOffers"])

        unrelated = copy.deepcopy(entity)
        unrelated["offers"][0]["url"] = "https://example.com/not-the-official-article"
        unrelated["offers"][0]["applicationWindowSource"] = unrelated["offers"][0]["url"]
        self.assertEqual(1, len(audit(state, {"publicEvents": [unrelated]})["missingOffers"]))

    def test_verified_central_fc_label_alias_is_represented(self):
        expected = {
            "group": "SWEET STEADY", "eventDate": "2099-03-04",
            "startTime": "18:30", "ticketType": "KAWAII LAB. FC先行",
            "applyStart": "2098-10-16T12:00", "applyEnd": "2098-10-26T23:59",
            "url": "https://kawaiilab.asobisystem.com/news/detail/92955",
        }
        state = {"observations": [{"expectedOffers": [expected]}]}
        entity = {
            "group": expected["group"], "eventDate": expected["eventDate"],
            "startTime": expected["startTime"], "urls": [expected["url"]],
            "offers": [{"ticketType": "FC先行", "applyStart": expected["applyStart"],
                        "applyEnd": expected["applyEnd"]}],
        }
        report = audit(state, {"publicEvents": [entity]})
        self.assertEqual("ok", report["status"])
        self.assertEqual(1, report["representedOffers"])

        wrong_source = copy.deepcopy(entity)
        wrong_source["urls"] = ["https://sweetsteady.asobisystem.com/news/detail/other"]
        self.assertEqual(1, len(audit(state, {"publicEvents": [wrong_source]})["missingOffers"]))

        distinct_window = copy.deepcopy(entity)
        distinct_window["offers"][0]["applyStart"] = "2098-10-17T12:00"
        self.assertEqual(1, len(audit(state, {"publicEvents": [distinct_window]})["missingOffers"]))

    def test_verified_same_day_ticket_detail_is_represented(self):
        source = "https://candytune.asobisystem.com/news/detail/94161"
        expected = {
            "group": "CANDY TUNE", "eventDate": "2099-10-27",
            "startTime": "18:30", "ticketType": "当日券",
            "applyStart": "2099-10-27T17:30", "applyEnd": None,
            "url": source,
        }
        entity = {
            "group": expected["group"], "eventDate": expected["eventDate"],
            "startTime": expected["startTime"],
            "offers": [{
                "ticketType": "当日券（注釈付き指定席・会場販売）",
                "applyStart": expected["applyStart"], "applyEnd": None,
                "url": source, "applicationWindowVerified": True,
            }],
        }
        state = {"observations": [{"expectedOffers": [expected]}]}
        self.assertEqual([], audit(state, {"publicEvents": [entity]})["missingOffers"])

        wrong_source = copy.deepcopy(entity)
        wrong_source["offers"][0]["url"] = "https://example.com/other"
        self.assertEqual(1, len(audit(state, {"publicEvents": [wrong_source]})["missingOffers"]))

        unverified = copy.deepcopy(entity)
        unverified["offers"][0]["applicationWindowVerified"] = False
        self.assertEqual(1, len(audit(state, {"publicEvents": [unverified]})["missingOffers"]))

        changed_window = copy.deepcopy(entity)
        changed_window["offers"][0]["applyStart"] = "2099-10-27T18:00"
        self.assertEqual(1, len(audit(state, {"publicEvents": [changed_window]})["missingOffers"]))

    def test_alias_does_not_hide_real_missing_or_changed_offer(self):
        state, payload = self.fixture()
        for field, value in (("applyEnd", "2099-11-13T20:00"), ("provider", "pia"), ("ticketType", "FC先行")):
            changed = copy.deepcopy(payload)
            changed["publicEvents"][0]["offers"][0][field] = value
            self.assertEqual(1, len(audit(state, changed)["missingOffers"]), field)
        payload["publicEvents"][0]["urls"] = []
        self.assertEqual(1, len(audit(state, payload)["missingOffers"]))

    def test_generic_schedule_ticket_is_represented_by_verified_special_event_offer(self):
        expected = {
            "group": "MORE STAR", "eventDate": "2099-11-03", "startTime": "10:00",
            "ticketType": "チケット受付", "applyStart": "2099-10-23T21:00",
            "applyEnd": "2099-10-27T23:59",
            "url": "https://morestar.asobisystem.com/live_information/detail/46447",
        }
        entity = {
            "group": "MORE STAR", "eventDate": "2099-11-03", "startTime": "10:00",
            "entityType": "special-event", "urls": [expected["url"]],
            "offers": [{
                "ticketType": "対象商品予約（参加権付き・先着／予約受付）",
                "applyStart": expected["applyStart"], "applyEnd": expected["applyEnd"],
                "applicationWindowVerified": True,
            }],
        }
        state = {"observations": [{"expectedOffers": [expected]}]}
        self.assertEqual([], audit(state, {"publicEvents": [entity]})["missingOffers"])

        wrong_source = copy.deepcopy(entity)
        wrong_source["urls"] = ["https://morestar.asobisystem.com/live_information/detail/other"]
        self.assertEqual(1, len(audit(state, {"publicEvents": [wrong_source]})["missingOffers"]))

        unverified = copy.deepcopy(entity)
        unverified["offers"][0]["applicationWindowVerified"] = False
        self.assertEqual(1, len(audit(state, {"publicEvents": [unverified]})["missingOffers"]))

        changed_window = copy.deepcopy(entity)
        changed_window["offers"][0]["applyEnd"] = "2099-10-27T20:00"
        self.assertEqual(1, len(audit(state, {"publicEvents": [changed_window]})["missingOffers"]))

    def test_other_day_or_start_time_is_not_the_same_performance(self):
        state, payload = self.fixture()
        payload["publicEvents"][0]["eventDate"] = "2099-11-15"
        self.assertEqual(1, len(audit(state, payload)["missingOffers"]))
        payload["publicEvents"][0]["eventDate"] = "2099-11-14"
        state["observations"][0]["expectedOffers"][0]["startTime"] = "18:00"
        payload["publicEvents"][0]["startTime"] = "13:00"
        self.assertEqual(1, len(audit(state, payload)["missingOffers"]))

    def test_source_failure_still_degrades_even_if_every_offer_is_present(self):
        state, payload = self.fixture()
        state["failureCount"] = 1
        self.assertEqual("degraded", audit(state, payload)["status"])
