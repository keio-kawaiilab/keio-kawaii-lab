import unittest

import clean_pia_refresh as c


class CleanPiaRefreshTests(unittest.TestCase):
    def test_fresh_pia_replaces_old_derived_pia_in_same_group(self):
        events = [
            {"id": "official", "group": "CANDY TUNE", "sourceType": "auto", "url": "https://candytune.asobisystem.com/news/1"},
            {"id": "old", "group": "CANDY TUNE", "sourceType": "derived", "primarySource": "pia", "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=OLD"},
            {"id": "fresh", "group": "CANDY TUNE", "sourceType": "pia", "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=NEW"},
        ]
        kept, removed = c.clean(events)
        self.assertEqual({x["id"] for x in kept}, {"official", "fresh"})
        self.assertEqual(removed, ["old"])

    def test_no_fresh_group_keeps_previous_pia_for_retention(self):
        events = [
            {"id": "old", "group": "MORE STAR", "sourceType": "derived", "primarySource": "pia", "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=OLD"},
        ]
        kept, removed = c.clean(events)
        self.assertEqual([x["id"] for x in kept], ["old"])
        self.assertEqual(removed, [])


if __name__ == "__main__":
    unittest.main()
