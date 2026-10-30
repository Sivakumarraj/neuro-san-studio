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

from datetime import date
from unittest import TestCase

from coded_tools.experimental.opportunity_desk.desk_profile import EXAMPLE_PROFILE
from coded_tools.experimental.opportunity_desk.desk_profile import DeskProfile
from coded_tools.experimental.opportunity_desk.outreach_decision import OutreachDecision
from coded_tools.experimental.opportunity_desk.outreach_rules import OutreachRules

TODAY: date = date(2026, 10, 30)
BODY: str = "I added an evidence checker to my research desk; the repository has the details."


class TestOutreachRules(TestCase):
    """
    The cadence and wording rules are the point of the gate, so each one is pinned here.
    """

    def setUp(self):
        """Rules from the example profile: one unanswered message, 7-day cooldown, 180 words."""
        self.profile = DeskProfile.load(str(EXAMPLE_PROFILE))
        self.rules = OutreachRules(self.profile.outreach_policy())

    def _review(self, contact_id: str, history: list[dict], body: str = BODY) -> OutreachDecision:
        """Review a draft to one of the example contacts."""
        return self.rules.review(self.profile.contact(contact_id), history, body, TODAY)

    def test_first_message_to_open_contact_passes(self):
        """No history and a clean body: allowed."""
        decision = self._review("example-recruiter", [])
        self.assertTrue(decision.allowed, decision.reasons)

    def test_unknown_contact_is_blocked(self):
        """Nobody outside the profile can be written to."""
        decision = self.rules.review(None, [], BODY, TODAY)
        self.assertFalse(decision.allowed)

    def test_do_not_contact_is_blocked(self):
        """do_not_contact holds even with no history at all."""
        decision = self._review("example-paused", [])
        self.assertFalse(decision.allowed)
        self.assertTrue(any("do_not_contact" in reason for reason in decision.reasons))

    def test_second_unanswered_message_is_blocked_by_default(self):
        """The default limit is one message, then wait for a reply."""
        contact = {"name": "Default", "status": "open"}
        decision = self.rules.review(contact, [{"direction": "sent", "happened_on": "2026-10-01"}], BODY, TODAY)
        self.assertFalse(decision.allowed)
        self.assertTrue(any("wait for them to answer" in reason for reason in decision.reasons))

    def test_reply_resets_the_count(self):
        """After they answer, a reply is allowed the same day."""
        history = [
            {"direction": "sent", "happened_on": "2026-10-20"},
            {"direction": "received", "happened_on": "2026-10-30"},
        ]
        contact = {"name": "Default", "status": "open"}
        self.assertTrue(self.rules.review(contact, history, BODY, TODAY).allowed)

    def test_follow_up_allowed_by_override_still_waits_for_cooldown(self):
        """example-recruiter allows two unanswered messages, but not two in one week."""
        too_soon = self._review("example-recruiter", [{"direction": "sent", "happened_on": "2026-10-27"}])
        self.assertFalse(too_soon.allowed)
        self.assertTrue(any("wait at least 7" in reason for reason in too_soon.reasons))
        later = self._review("example-recruiter", [{"direction": "sent", "happened_on": "2026-10-20"}])
        self.assertTrue(later.allowed, later.reasons)

    def test_reply_only_contact_needs_them_to_write_last(self):
        """reply_only blocks a cold message and allows an answer."""
        self.assertFalse(self._review("example-reply-only", []).allowed)
        answered = self._review("example-reply-only", [{"direction": "received", "happened_on": "2026-10-29"}])
        self.assertTrue(answered.allowed, answered.reasons)

    def test_technical_only_contact_gets_no_hiring_language(self):
        """A technical contact stays technical: role words are refused."""
        decision = self._review(
            "example-maintainer", [], "Is there an opening on your team? Happy to share my resume."
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(any("opening" in reason and "resume" in reason for reason in decision.reasons))
        self.assertTrue(self._review("example-maintainer", []).allowed)

    def test_banned_phrase_markdown_and_length_are_refused(self):
        """Wording rules apply to every contact."""
        self.assertFalse(self._review("example-recruiter", [], "Just checking in again about my note.").allowed)
        self.assertFalse(self._review("example-recruiter", [], "**Update**: the checker works.").allowed)
        self.assertFalse(self._review("example-recruiter", [], "word " * 181).allowed)
