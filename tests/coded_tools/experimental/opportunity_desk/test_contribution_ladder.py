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
from datetime import timedelta
from typing import Any
from unittest import TestCase

from coded_tools.experimental.opportunity_desk.contribution_ladder import ContributionLadder

TODAY: date = date(2026, 10, 31)


class TestContributionLadder(TestCase):
    """
    The ladder makes waiting the default; each rung is pinned so it cannot drift into nagging.
    """

    @staticmethod
    def _item(kind: str, days: int, state: str = "open", merged: bool = False, comments: int = 0) -> dict[str, Any]:
        """Build a contribution opened the given number of days before TODAY."""
        opened: str = f"{(TODAY - timedelta(days=days)).isoformat()}T10:00:00Z"
        return {"kind": kind, "state": state, "merged": merged, "comments": comments, "opened_at": opened}

    def test_pull_request_rungs(self):
        """Wait, then line up a second contribution, then one question, then move on."""
        self.assertIn("wait, silence is normal", ContributionLadder.verdict(self._item("pull_request", 10), TODAY))
        self.assertIn("second contribution", ContributionLadder.verdict(self._item("pull_request", 20), TODAY))
        self.assertIn("once", ContributionLadder.verdict(self._item("pull_request", 40), TODAY))
        self.assertIn("stalled", ContributionLadder.verdict(self._item("pull_request", 60), TODAY))

    def test_finished_pull_requests(self):
        """A merge is a credential; a close needs the reviewer's reason read first."""
        merged = self._item("pull_request", 5, state="closed", merged=True)
        self.assertTrue(ContributionLadder.verdict(merged, TODAY).startswith("merged"))
        closed = self._item("pull_request", 5, state="closed")
        self.assertIn("read the reviewer's reason", ContributionLadder.verdict(closed, TODAY))

    def test_issues_never_get_a_reminder(self):
        """An unanswered issue's next move is a pull request, not a ping."""
        self.assertIn("waiting for a maintainer", ContributionLadder.verdict(self._item("issue", 3), TODAY))
        stale = ContributionLadder.verdict(self._item("issue", 20), TODAY)
        self.assertIn("do not ping", stale)
        self.assertIn("2 comment(s)", ContributionLadder.verdict(self._item("issue", 20, comments=2), TODAY))
        self.assertEqual(ContributionLadder.verdict(self._item("issue", 20, state="closed"), TODAY), "closed")

    def test_missing_date_counts_as_new(self):
        """A record without an opening date is treated as day 0, never as stalled."""
        item = {"kind": "pull_request", "state": "open", "opened_at": ""}
        self.assertIn("open 0 day(s)", ContributionLadder.verdict(item, TODAY))
