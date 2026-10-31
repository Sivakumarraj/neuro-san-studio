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
from unittest import mock

from coded_tools.experimental.opportunity_desk.desk_clock import DeskClock
from coded_tools.experimental.opportunity_desk.desk_profile import EXAMPLE_PROFILE
from coded_tools.experimental.opportunity_desk.desk_profile import DeskProfile
from coded_tools.experimental.opportunity_desk.fit_assessor import FitAssessor
from coded_tools.experimental.opportunity_desk.fit_result import FitResult
from coded_tools.experimental.opportunity_desk.posting import Posting


class TestFitAssessor(TestCase):
    """
    The assessor decides fit in code, so its hard requirements must hold whatever the score.
    """

    def setUp(self):
        """Use the bundled example profile: 2025 graduate, at most 1 year, Bengaluru or remote."""
        self.assessor = FitAssessor(DeskProfile.load(str(EXAMPLE_PROFILE)))

    @staticmethod
    def _role(title: str, description: str, location: str = "Bengaluru, India") -> Posting:
        """Build a careers-board posting."""
        return Posting(
            posting_id="lever:acme:1",
            kind="role",
            source="lever",
            title=title,
            company="Acme",
            location=location,
            url="https://jobs.lever.co/acme/1",
            description=description,
            posted_at="",
        )

    def test_strong_entry_level_match_is_eligible(self):
        """Skills, title, location and an entry-level signal all count, with a reason each."""
        result: FitResult = self.assessor.assess(
            self._role("AI Engineer", "Fresher role. Python, FastAPI, LangChain, RAG and LLM agents with Docker.")
        )
        self.assertTrue(result.eligible)
        self.assertGreaterEqual(result.score, 90)
        self.assertTrue(any("title matches" in reason for reason in result.reasons))
        self.assertTrue(any("entry-level" in reason for reason in result.reasons))

    def test_years_of_experience_blocks_however_good_the_match(self):
        """A 3+ year requirement makes a perfect skills match ineligible for a 1-year limit."""
        result: FitResult = self.assessor.assess(
            self._role("AI Engineer", "3+ years of experience. Python, FastAPI, LangChain, RAG, LLM, Docker.")
        )
        self.assertFalse(result.eligible)
        self.assertIn("asks for 3+ years of experience (your limit is 1)", result.reasons)

    def test_batch_restriction_blocks_other_graduation_years(self):
        """A posting for the 2026 batch only is not open to a 2025 graduate."""
        result: FitResult = self.assessor.assess(self._role("Graduate Engineer Trainee", "Open to 2026 batch only."))
        self.assertFalse(result.eligible)
        self.assertTrue(any("2026 batch" in reason for reason in result.reasons))

    def test_batch_year_after_the_word_also_blocks(self):
        """Seen on a real Lever board in Oct 2026: 'CA pass -out 2026'."""
        result: FitResult = self.assessor.assess(self._role("Assistant Manager - Finance | CA pass -out 2026", ""))
        self.assertTrue(any("2026 batch" in reason for reason in result.reasons))
        own_batch: FitResult = self.assessor.assess(self._role("Graduate Trainee", "Batch of 2025 welcome."))
        self.assertFalse(any("batch" in reason for reason in own_batch.reasons))

    def test_batch_list_including_the_owner_is_allowed(self):
        """A batch list that includes the owner's year does not block."""
        result: FitResult = self.assessor.assess(self._role("Python Developer", "2024/2025 graduates welcome."))
        self.assertFalse(any("batch" in reason for reason in result.reasons))

    def test_senior_title_blocks(self):
        """Senior titles are out of reach for an entry-level owner."""
        result: FitResult = self.assessor.assess(self._role("Senior ML Engineer", "Python and LLMs."))
        self.assertFalse(result.eligible)

    def test_excluded_term_blocks(self):
        """A term the owner excluded rules the posting out."""
        result: FitResult = self.assessor.assess(self._role("AI Engineer", "Python. Two-year service bond applies."))
        self.assertFalse(result.eligible)

    def test_skills_match_whole_words_only(self):
        """'rag' must not match 'drag', or every UI posting would look like a RAG role."""
        result: FitResult = self.assessor.assess(self._role("Frontend Developer", "Drag and drop builder."))
        self.assertIn("mentions none of your skills", result.reasons)

    def test_unlisted_location_scores_nothing_for_location(self):
        """A location the owner did not list earns no location points and says so."""
        result: FitResult = self.assessor.assess(self._role("AI Engineer", "Python.", location="Berlin"))
        self.assertIn("location 'Berlin' is not one you listed", result.reasons)

    @staticmethod
    def _issue(claimed_by: str = "", maintainer: bool = True, opened: str = "2026-10-25T00:00:00Z") -> Posting:
        """Build an open repository issue."""
        return Posting(
            posting_id="github:org/repo:7",
            kind="contribution",
            source="github",
            title="Add retries to the web search tool",
            company="org/repo",
            location="open source",
            url="https://github.com/org/repo/issues/7",
            description="Python change in a coded tool; 5 years of history in this file.",
            posted_at=opened,
            claimed_by=claimed_by,
            filed_by_maintainer=maintainer,
        )

    def test_fresh_unclaimed_maintainer_issue_scores_high(self):
        """The issue most likely to be merged: wanted, free and recent. No seniority bar applies."""
        with mock.patch.object(DeskClock, "today", return_value=date(2026, 10, 31)):
            result: FitResult = self.assessor.assess(self._issue())
        self.assertTrue(result.eligible)
        self.assertGreaterEqual(result.score, 60)
        self.assertIn("filed by a maintainer, so the fix is wanted", result.reasons)
        self.assertIn("opened 6 day(s) ago", result.reasons)

    def test_claimed_issue_is_not_open_work(self):
        """Someone else is on it: ineligible, and the reason names them."""
        result: FitResult = self.assessor.assess(self._issue(claimed_by="someone"))
        self.assertFalse(result.eligible)
        self.assertIn("already assigned to someone", result.reasons)

    def test_old_outside_issue_scores_lower(self):
        """Without the maintainer and freshness signals the same issue ranks lower."""
        with mock.patch.object(DeskClock, "today", return_value=date(2026, 10, 31)):
            fresh: FitResult = self.assessor.assess(self._issue())
            old: FitResult = self.assessor.assess(self._issue(maintainer=False, opened="2026-01-01T00:00:00Z"))
        self.assertLess(old.score, fresh.score)
