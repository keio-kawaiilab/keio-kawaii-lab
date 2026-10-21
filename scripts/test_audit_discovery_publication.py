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

    def test_verified_resale_label_alias_is_represented(self):
        state, payload = self.fixture()
        report = audit(state, payload)
        self.assertEqual("ok", report["status"])
        self.assertEqual(1, report["representedOffers"])

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

    def test_alias_does_not_hide_real_missing_or_changed_offer(self):
        state, payload = self.fixture()
        for field, value in (("applyEnd", "2099-11-13T20:00"), ("provider", "pia"), ("ticketType", "FC先行")):
            changed = copy.deepcopy(payload)
            changed["publicEvents"][0]["offers"][0][field] = value
            self.assertEqual(1, len(audit(state, changed)["missingOffers"]), field)
        payload["publicEvents"][0]["urls"] = []
        self.assertEqual(1, len(audit(state, payload)["missingOffers"]))

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
