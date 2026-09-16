import unittest

import audit_ticket_sources as audit


class AuditTicketSourcesTests(unittest.TestCase):
    def test_history_accepts_registered_source_subdomain(self):
        registry = {
            "sources": {
                "promoter": {
                    "label": "Promoter",
                    "kind": "promoter",
                    "publishPolicy": "direct",
                }
            },
            "hostRules": {"red-hot.ne.jp": "promoter"},
        }
        history = {
            "entries": [{
                "id": "general-sale",
                "group": "CANDY TUNE",
                "eventDate": "2026-10-08",
                "ticketType": "一般発売",
                "applyStart": "2026-09-12T10:00",
                "sourceKey": "promoter",
                "sourceUrl": "https://www.red-hot.ne.jp/play/detail.php?pid=example",
                "publishable": True,
                "windowCompleteness": "start-only",
            }]
        }

        errors, report = audit.audit_history(registry, history)

        self.assertEqual(errors, [])
        self.assertEqual(report["bySource"], {"promoter": 1})


if __name__ == "__main__":
    unittest.main()
