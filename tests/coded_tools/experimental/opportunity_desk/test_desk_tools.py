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

import json
import os
from datetime import date
from unittest import IsolatedAsyncioTestCase
from unittest import mock

from coded_tools.experimental.opportunity_desk.check_evidence import CheckEvidence
from coded_tools.experimental.opportunity_desk.desk_clock import DeskClock
from coded_tools.experimental.opportunity_desk.desk_store import DeskStore
from coded_tools.experimental.opportunity_desk.digest_mailer import DigestMailer
from coded_tools.experimental.opportunity_desk.outreach_gate import OutreachGate
from coded_tools.experimental.opportunity_desk.pipeline_tracker import PipelineTracker
from coded_tools.experimental.opportunity_desk.record_outreach import RecordOutreach
from coded_tools.experimental.opportunity_desk.scan_boards import ScanBoards
from coded_tools.experimental.opportunity_desk.send_digest import SendDigest
from coded_tools.experimental.opportunity_desk.track_contributions import TrackContributions
from tests.coded_tools.experimental.opportunity_desk.desk_test_environment import DeskTestEnvironment
from tests.coded_tools.experimental.opportunity_desk.fake_page_source import FakePageSource
from tests.coded_tools.experimental.opportunity_desk.test_board_parser import GITHUB_SEARCH
from tests.coded_tools.experimental.opportunity_desk.test_board_parser import GREENHOUSE_RESPONSE
from tests.coded_tools.experimental.opportunity_desk.test_board_parser import LEVER_RESPONSE

BOARDS: list[dict] = [
    {"provider": "greenhouse", "slug": "acme", "company": "Acme AI"},
    {"provider": "lever", "slug": "leverdemo", "company": "Lever"},
    {"provider": "ashby", "slug": "gone", "company": "Gone Inc"},
]
UPSTREAM: list[str] = ["cognizant-ai-lab/neuro-san-studio"]
PAGE: str = "Cognizant AI Lab reports that MAKER solved over one million LLM steps with zero errors."


class TestDeskTools(IsolatedAsyncioTestCase):
    """
    Each coded tool run as neuro-san runs it: through async_invoke, against a temporary
    profile and store, with recorded responses in place of the network.
    """

    def setUp(self):
        """Serve recorded pages instead of the network."""
        FakePageSource.responses = {
            "https://boards-api.greenhouse.io/v1/boards/acme/": GREENHOUSE_RESPONSE,
            "https://api.lever.co/v0/postings/leverdemo": LEVER_RESPONSE,
            "https://lab.example.com/maker": PAGE,
            "https://api.github.com/search/issues": GITHUB_SEARCH,
        }
        self._patches = [
            mock.patch.object(ScanBoards, "source_class", FakePageSource),
            mock.patch.object(CheckEvidence, "source_class", FakePageSource),
            mock.patch.object(TrackContributions, "source_class", FakePageSource),
        ]
        for patch in self._patches:
            patch.start()

    def tearDown(self):
        """Put the real source back."""
        for patch in self._patches:
            patch.stop()

    async def test_scan_stores_new_postings_and_reports_failed_sources(self):
        """A broken board is named in the result; the good ones still load, and only once."""
        with DeskTestEnvironment(boards=BOARDS, contribution_repos=[]):
            result = json.loads(await ScanBoards().async_invoke({}, {}))
            self.assertEqual(result.get("postings_seen"), 2)
            self.assertEqual(result.get("new_postings"), 2)
            self.assertEqual(len(result.get("sources_failed")), 1)
            self.assertIn("ashby/gone", result.get("sources_failed")[0])
            # The Bengaluru RAG role matches; the 3+ year Atlanta role does not.
            self.assertEqual(
                [match.get("opportunity_id") for match in result.get("matches")], ["greenhouse:acme:4011"]
            )

            again = json.loads(await ScanBoards().async_invoke({}, {}))
            self.assertEqual(again.get("new_postings"), 0)

    async def test_scan_with_every_source_failing_is_an_error(self):
        """Nothing loaded must not look like nothing new."""
        with DeskTestEnvironment(boards=[{"provider": "lever", "slug": "gone"}], contribution_repos=[]):
            result = await ScanBoards().async_invoke({}, {})
        self.assertTrue(result.startswith("Error: every source failed"))

    async def test_evidence_verdict_is_computed_in_code(self):
        """One good claim out of two is below the 0.7 threshold, so the verdict is ESCALATE."""
        claims = [
            {
                "claim": "MAKER ran a million steps without error",
                "source_url": "https://lab.example.com/maker",
                "quote": "MAKER solved over one million LLM steps with zero errors",
            },
            {
                "claim": "It used GPT-5",
                "source_url": "https://lab.example.com/maker",
                "quote": "the experiments were all run on the largest frontier model",
            },
        ]
        with DeskTestEnvironment():
            result = json.loads(await CheckEvidence().async_invoke({"claims": claims}, {}))
            self.assertEqual(result.get("verdict"), "ESCALATE")
            self.assertEqual([claim.get("status") for claim in result.get("claims")], ["verified", "quote_not_found"])
            supported = json.loads(await CheckEvidence().async_invoke({"claims": claims[:1]}, {}))
            self.assertEqual(supported.get("verdict"), "SUPPORTED")
            self.assertEqual(DeskStore().audit_tail(1)[0].get("action"), "evidence_checked")

    async def test_evidence_dead_link_fails_only_its_claim(self):
        """An unreachable source marks that claim fetch_failed rather than failing the check."""
        claims = [{"claim": "x", "source_url": "https://dead.example.com/", "quote": "one two three four five six"}]
        with DeskTestEnvironment():
            result = json.loads(await CheckEvidence().async_invoke({"claims": claims}, {}))
        self.assertEqual(result.get("claims")[0].get("status"), "fetch_failed")
        self.assertEqual(result.get("verdict"), "ESCALATE")

    async def test_gate_clears_once_then_blocks_until_a_reply_is_recorded(self):
        """The full loop: draft, owner records the send, next draft blocked, reply recorded, allowed again."""
        args = {
            "contact_id": "example-reply-only",
            "subject": "Evidence checker",
            "body": "Thanks for your note; it is built.",
        }
        with DeskTestEnvironment():
            blocked = await OutreachGate().async_invoke(args, {})
            self.assertTrue(blocked.startswith("Error: Blocked."), blocked)

            await RecordOutreach().async_invoke({"contact_id": "example-reply-only", "direction": "received"}, {})
            cleared = await OutreachGate().async_invoke(args, {})
            self.assertTrue(
                cleared.startswith("CLEARED\nTo: Robin Reply <robin@example.com>\nSubject: Evidence checker")
            )

            await RecordOutreach().async_invoke({"contact_id": "example-reply-only", "direction": "sent"}, {})
            self.assertTrue((await OutreachGate().async_invoke(args, {})).startswith("Error: Blocked."))
            actions = [entry.get("action") for entry in DeskStore().audit_tail(10)]
            self.assertIn("outreach_cleared", actions)
            self.assertIn("outreach_blocked", actions)

    async def test_gate_reads_history_from_the_profile(self):
        """A fresh store still knows from the profile that the last message is unanswered."""
        with DeskTestEnvironment():
            result = await OutreachGate().async_invoke({"contact_id": "example-awaiting", "body": "A new result."}, {})
        self.assertTrue(result.startswith("Error: Blocked."), result)
        self.assertIn("2026-09-02", result)

    async def test_gate_and_recorder_refuse_unknown_contacts(self):
        """Nobody outside the profile can be written to or recorded."""
        with DeskTestEnvironment():
            gate = await OutreachGate().async_invoke({"contact_id": "someone", "body": "hello there"}, {})
            recorder = await RecordOutreach().async_invoke({"contact_id": "someone", "direction": "sent"}, {})
        self.assertIn("Known contacts:", gate)
        self.assertIn("example-maintainer", gate)
        self.assertTrue(recorder.startswith("Error:"))

    async def test_tracker_lists_updates_and_validates(self):
        """Status changes are checked in code and audited."""
        with DeskTestEnvironment(boards=BOARDS[:1], contribution_repos=[]):
            await ScanBoards().async_invoke({}, {})
            listed = json.loads(await PipelineTracker().async_invoke({"action": "list"}, {}))
            self.assertEqual(listed.get("count"), 1)
            moved = await PipelineTracker().async_invoke(
                {"action": "update", "opportunity_id": "greenhouse:acme:4011", "status": "shortlisted"}, {}
            )
            self.assertIn("shortlisted", moved)
            bad = await PipelineTracker().async_invoke(
                {"action": "update", "opportunity_id": "greenhouse:acme:4011", "status": "ghosted"}, {}
            )
            self.assertTrue(bad.startswith("Error: unknown status"))
            audit = json.loads(await PipelineTracker().async_invoke({"action": "audit"}, {}))
            self.assertEqual(audit.get("entries")[0].get("action"), "status_changed")

    async def test_digest_without_mail_returns_text_and_keeps_the_window_open(self):
        """Unsent matches stay pending for the next delivered digest."""
        with DeskTestEnvironment(boards=BOARDS[:1], contribution_repos=[]):
            await ScanBoards().async_invoke({}, {})
            with mock.patch.object(DigestMailer, "is_configured", return_value=False):
                text = await SendDigest().async_invoke({}, {})
            self.assertIn("AI Engineer at Acme AI", text)
            self.assertIsNone(DeskStore().last_digest_at())

    async def test_digest_sends_only_new_matches_to_the_owner(self):
        """After a delivered digest, the same matches are not sent again."""
        with DeskTestEnvironment(boards=BOARDS[:1], contribution_repos=[]):
            await ScanBoards().async_invoke({}, {})
            with (
                mock.patch.object(DigestMailer, "is_configured", return_value=True),
                mock.patch.object(DigestMailer, "send") as send,
                mock.patch.object(DeskClock, "now_iso", return_value="2999-01-01T00:00:00+00:00"),
            ):
                sent = await SendDigest().async_invoke({}, {})
                self.assertIn("Emailed a digest of 1", sent)
                self.assertEqual(send.call_count, 1)
                second = await SendDigest().async_invoke({}, {})
            self.assertIn("nothing to send", second)

    async def test_contribution_tracker_reports_changes_once_with_verdicts(self):
        """First check tracks everything; an unchanged second check reports no changes."""
        with (
            DeskTestEnvironment(github_user="Sivakumarraj", upstream_repos=UPSTREAM),
            mock.patch.object(DeskClock, "today", return_value=date(2026, 10, 31)),
        ):
            first = json.loads(await TrackContributions().async_invoke({}, {}))
            self.assertEqual(first.get("tracked"), 2)
            self.assertEqual(len(first.get("changes")), 2)
            verdicts = {item.get("number"): item.get("verdict") for item in first.get("items")}
            self.assertTrue(verdicts.get(1297).startswith("merged"))
            self.assertIn("waiting for a maintainer", verdicts.get(1550))
            again = json.loads(await TrackContributions().async_invoke({}, {}))
            self.assertEqual(again.get("changes"), [])

    async def test_contribution_tracker_needs_a_login(self):
        """The example profile names nobody, so there is nothing to track."""
        with DeskTestEnvironment():
            result = await TrackContributions().async_invoke({}, {})
        self.assertTrue(result.startswith("Error: the profile has no github_user"))

    async def test_digest_carries_contribution_updates(self):
        """A digest with no new matches still goes out when upstream work changed."""
        with DeskTestEnvironment(
            boards=[], contribution_repos=[], github_user="Sivakumarraj", upstream_repos=UPSTREAM
        ):
            await TrackContributions().async_invoke({}, {})
            with mock.patch.object(DigestMailer, "is_configured", return_value=False):
                text = await SendDigest().async_invoke({}, {})
        self.assertIn("Your upstream pull requests and issues that changed", text)
        self.assertIn("Next: merged", text)

    async def test_recorder_defaults_to_today(self):
        """Without a date the event is recorded for today."""
        with (
            DeskTestEnvironment(),
            mock.patch.object(DeskClock, "today", return_value=date(2026, 10, 30)),
        ):
            result = await RecordOutreach().async_invoke({"contact_id": "example-recruiter", "direction": "sent"}, {})
        self.assertIn("2026-10-30 sent", result)

    def test_environment_is_restored(self):
        """The test environment must not leak a profile into other tests."""
        with DeskTestEnvironment() as environment:
            self.assertEqual(os.environ.get("OPPORTUNITY_DESK_DATA_DIR"), environment.data_dir)
        self.assertNotEqual(os.environ.get("OPPORTUNITY_DESK_DATA_DIR"), environment.data_dir)
