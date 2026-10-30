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

import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest import mock

from coded_tools.experimental.opportunity_desk.desk_profile import EXAMPLE_PROFILE
from coded_tools.experimental.opportunity_desk.desk_profile import PROFILE_ENV
from coded_tools.experimental.opportunity_desk.desk_profile import DeskProfile


class TestDeskProfile(TestCase):
    """
    The profile is the owner's private configuration; a bad one must fail loudly and say where.
    """

    def test_falls_back_to_the_example_and_says_so(self):
        """With no variable set, the fictional example loads and is marked as such."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(PROFILE_ENV, None)
            profile = DeskProfile.load()
        self.assertTrue(profile.is_example())
        self.assertIn("python", profile.skills())
        self.assertEqual(profile.graduation_year(), 2025)

    def test_example_contacts_are_fictional(self):
        """The committed example must never name a real person: only example.com addresses."""
        profile = DeskProfile.load(str(EXAMPLE_PROFILE))
        for contact_id in profile.contact_ids():
            self.assertTrue(contact_id.startswith("example-"))
            self.assertTrue(profile.contact(contact_id).get("email", "x@example.com").endswith("@example.com"))

    def test_missing_and_malformed_files_name_the_path(self):
        """The operator needs the path to fix it."""
        with self.assertRaisesRegex(ValueError, "nowhere.json"):
            DeskProfile.load("/nonexistent/nowhere.json")
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not valid JSON"):
                DeskProfile.load(str(broken))
            listed = Path(directory) / "list.json"
            listed.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                DeskProfile.load(str(listed))

    def test_outreach_policy_defaults(self):
        """An empty profile still has safe outreach rules: one unanswered message, a cooldown, a word cap."""
        policy = DeskProfile({}).outreach_policy()
        self.assertEqual(policy.get("max_unanswered"), 1)
        self.assertEqual(policy.get("cooldown_days"), 7)
        self.assertIn("referral", policy.get("role_terms"))

    def test_known_history_is_validated(self):
        """A bad history entry fails loudly rather than silently allowing a message."""
        profile = DeskProfile(
            {"contacts": {"c": {"history": [{"direction": "forwarded", "happened_on": "2026-10-01"}]}}}
        )
        with self.assertRaises(ValueError):
            profile.known_history("c")
        dated = DeskProfile({"contacts": {"c": {"history": [{"direction": "sent", "happened_on": "Oct 1"}]}}})
        with self.assertRaises(ValueError):
            dated.known_history("c")
        self.assertEqual(DeskProfile({}).known_history("nobody"), [])
