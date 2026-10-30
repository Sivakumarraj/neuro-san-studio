# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT

import tempfile
from unittest import TestCase

from coded_tools.experimental.opportunity_desk.desk_store import DeskStore
from coded_tools.experimental.opportunity_desk.fit_result import FitResult
from coded_tools.experimental.opportunity_desk.posting import Posting


class TestDeskStore(TestCase):
    """
    The store's job is to remember: what was seen, what the owner did, and what the tools decided.
    """

    def setUp(self):
        """A fresh database per test."""
        # Cleaned up in tearDown, which unittest pairs with setUp.
        self._directory = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.store = DeskStore(self._directory.name)

    def tearDown(self):
        """Remove the database."""
        self._directory.cleanup()

    @staticmethod
    def _posting(number: int) -> Posting:
        """Build a posting with a distinct id."""
        return Posting(
            posting_id=f"lever:acme:{number}",
            kind="role",
            source="lever",
            title=f"AI Engineer {number}",
            company="Acme",
            location="Bengaluru",
            url=f"https://jobs.lever.co/acme/{number}",
            description="Python",
            posted_at="",
        )

    def test_a_posting_is_new_only_once_and_keeps_its_status(self):
        """A second scan neither duplicates a posting nor resets what the owner did with it."""
        fit = FitResult(score=70, eligible=True, reasons=("title matches 'ai engineer'",))
        first = self.store.save_new([(self._posting(1), fit)], "2026-10-29T00:00:00+00:00")
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].get("reasons"), ["title matches 'ai engineer'"])
        self.assertTrue(
            self.store.update_status("lever:acme:1", "applied", "sent via portal", "2026-10-29T01:00:00+00:00")
        )

        again = self.store.save_new([(self._posting(1), fit), (self._posting(2), fit)], "2026-10-30T00:00:00+00:00")
        self.assertEqual([row.get("opportunity_id") for row in again], ["lever:acme:2"])
        self.assertEqual(self.store.get_opportunity("lever:acme:1").get("status"), "applied")

    def test_unknown_status_and_direction_are_refused(self):
        """Values the rest of the desk does not understand never enter the store."""
        with self.assertRaises(ValueError):
            self.store.update_status("lever:acme:1", "ghosted", "", "2026-10-30T00:00:00+00:00")
        with self.assertRaises(ValueError):
            self.store.record_outreach("c", "forwarded", "2026-10-30", "")
        with self.assertRaises(ValueError):
            self.store.record_outreach("c", "sent", "30/10/2026", "")

    def test_listing_puts_eligible_and_higher_scores_first(self):
        """The best matches lead, and the since filter limits to new rows."""
        self.store.save_new([(self._posting(1), FitResult(90, False, ()))], "2026-10-28T00:00:00+00:00")
        self.store.save_new([(self._posting(2), FitResult(60, True, ()))], "2026-10-30T00:00:00+00:00")
        rows = self.store.list_opportunities()
        self.assertEqual([row.get("opportunity_id") for row in rows], ["lever:acme:2", "lever:acme:1"])
        recent = self.store.list_opportunities(since="2026-10-29T00:00:00+00:00")
        self.assertEqual(len(recent), 1)

    def test_outreach_history_is_in_date_order(self):
        """The cadence rules read history oldest first."""
        self.store.record_outreach("c", "received", "2026-10-20", "they wrote")
        self.store.record_outreach("c", "sent", "2026-10-10", "first note")
        self.assertEqual([event.get("direction") for event in self.store.outreach_history("c")], ["sent", "received"])

    def test_only_delivered_digests_move_the_window(self):
        """An undelivered digest must not swallow the matches it failed to send."""
        self.store.record_digest("2026-10-29T00:00:00+00:00", 3, delivered=True)
        self.store.record_digest("2026-10-30T00:00:00+00:00", 2, delivered=False)
        self.assertEqual(self.store.last_digest_at(), "2026-10-29T00:00:00+00:00")

    def test_audit_log_reads_newest_first(self):
        """The audit tail shows the latest decision first."""
        self.store.log("scan", {"new": 1}, "2026-10-29T00:00:00+00:00")
        self.store.log("outreach_blocked", {"contact_id": "c"}, "2026-10-30T00:00:00+00:00")
        self.assertEqual([entry.get("action") for entry in self.store.audit_tail()], ["outreach_blocked", "scan"])
